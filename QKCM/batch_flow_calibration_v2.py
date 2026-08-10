# -*- coding: utf-8 -*-
"""
夹管流量计批量自动标定软件

设备：
    标准流量控制器：Modbus RTU ID = 1
    待标定流量计：ID = 2~26，共25台

标准流量控制器：
    62026/62027  目标流量 float，ABCD，大端，高16位在前
    62016/62017  实际反馈 float，ABCD，大端，高16位在前

流量计：
    61004/61005  标准表实际流量 float，ABCD，大端，高16位在前
    6009         温度点，当前固定 1
    6010         流量点：0=5%，1=20%，2=40%，3=60%，4=80%，5=100%
    6003         标定标志：写1开始，从机标定完成后自动清0
    61022/61023  流量计反馈 float，用于标定完成后的结果观察

标定顺序：
    100% -> 80% -> 60% -> 40% -> 20% -> 5%
    即6010：5 -> 4 -> 3 -> 2 -> 1 -> 0

标定逻辑：
    1. 写ID1目标流量。
    2. 等待ID1实际反馈进入设定的 ±%F.S. 范围并连续稳定一段时间。
    3. 对所有有效流量计写：
           61004/61005 = ID1实际反馈
           6009 = 1
           6010 = 当前流量点
    4. 对所有有效流量计写6003=1启动当前点标定。
    5. 标定期间持续读取ID1 62016，并持续更新每台流量计61004/61005。
    6. 持续轮询各流量计6003；某台变0则该台当前点完成。
    7. 某台单独通信异常不会影响其他流量计；超过当前点超时仍未完成，
       则该台本轮标定判失败并从后续点剔除。
    8. 当前仍有效的流量计全部完成后，进入下一流量点。
    9. 最后5%点完成后，整批标定结束。
   10. ID1是标准与控制单元，若其目标无法写入或稳定等待超时，
       为避免错误标定，整批任务停止，不会继续拿错误标准值标定。

依赖：
    pip install pyserial

说明：
    软件按给定寄存器地址直接发Modbus地址，不自动-1。
"""

import csv
import math
import os
import queue
import struct
import threading
import time
from datetime import datetime
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

import serial
from serial.tools import list_ports


# ============================================================
# 设备和寄存器
# ============================================================

CONTROLLER_ID = 1
METER_IDS = list(range(2, 27))

REG_CONTROLLER_TARGET = 62026
REG_CONTROLLER_FEEDBACK = 62016

REG_METER_CAL_FLAG = 6003
REG_METER_ZERO = 6008               # 写1触发指定流量计调零
REG_METER_TEMP_POINT = 6009
REG_METER_FLOW_POINT = 6010
REG_METER_STANDARD_FLOW = 61004
REG_METER_FEEDBACK = 61022
REG_METER_CAL_DATA = 61028          # 61028~61039：6个float标定点

# (百分比, 6010写入值)
CAL_POINTS = [
    (100, 5),
    (80, 4),
    (60, 3),
    (40, 2),
    (20, 1),
    (5, 0),
]

MODBUS_RETRY = 2
CONTROLLER_WRITE_RETRY = 5
METER_CONSECUTIVE_ERROR_LIMIT = 3


# ============================================================
# Modbus基础
# ============================================================

def crc16_modbus(data: bytes) -> int:
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            if crc & 0x0001:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc & 0xFFFF


def append_crc(data: bytes) -> bytes:
    c = crc16_modbus(data)
    return data + bytes((c & 0xFF, (c >> 8) & 0xFF))


def float_to_regs_be(value: float):
    """float ABCD -> 高16位寄存器、低16位寄存器。"""
    return struct.unpack(">HH", struct.pack(">f", float(value)))


def regs_to_float_be(reg0: int, reg1: int) -> float:
    """高16位、低16位寄存器 -> float ABCD。"""
    return struct.unpack(
        ">f",
        struct.pack(">HH", reg0 & 0xFFFF, reg1 & 0xFFFF)
    )[0]


class ModbusRTUMaster:
    def __init__(self):
        self.ser = None
        self.lock = threading.Lock()
        self.timeout = 0.25
        self.retry_count = 2
        self.trace_callback = None

    @property
    def is_open(self):
        return self.ser is not None and self.ser.is_open

    def set_trace_callback(self, cb):
        self.trace_callback = cb

    def _trace(self, direction, frame=b"", note=""):
        if self.trace_callback is None:
            return
        try:
            self.trace_callback(direction, bytes(frame), note)
        except Exception:
            pass

    def open(self, port, baudrate, timeout):
        self.close()
        self.timeout = float(timeout)

        self.ser = serial.Serial(
            port=port,
            baudrate=int(baudrate),
            bytesize=8,
            parity=serial.PARITY_NONE,
            stopbits=1,
            timeout=self.timeout,
            write_timeout=self.timeout,
        )

        time.sleep(0.10)
        self.ser.reset_input_buffer()
        self.ser.reset_output_buffer()

    def close(self):
        if self.ser is not None:
            try:
                self.ser.close()
            except Exception:
                pass
        self.ser = None

    def _read_exact(self, size):
        if not self.is_open:
            raise RuntimeError("串口未打开")

        data = bytearray()
        deadline = time.monotonic() + self.timeout

        while len(data) < size and time.monotonic() < deadline:
            part = self.ser.read(size - len(data))
            if part:
                data.extend(part)

        if len(data) != size:
            raise TimeoutError(
                f"接收超时：需要{size}字节，实际收到{len(data)}字节"
            )

        return bytes(data)

    @staticmethod
    def _check_crc(frame):
        if len(frame) < 4:
            raise ValueError("Modbus响应长度不足")

        recv_crc = frame[-2] | (frame[-1] << 8)
        calc_crc = crc16_modbus(frame[:-2])

        if recv_crc != calc_crc:
            raise ValueError(
                f"CRC错误：recv=0x{recv_crc:04X}, calc=0x{calc_crc:04X}"
            )

    def read_holding_registers(self, slave_id, start_addr, count):
        if not self.is_open:
            raise RuntimeError("串口未打开")

        req = append_crc(
            struct.pack(
                ">BBHH",
                slave_id & 0xFF,
                0x03,
                start_addr & 0xFFFF,
                count & 0xFFFF,
            )
        )

        note = f"ID={slave_id} 03H READ addr={start_addr} count={count}"
        last_error = None

        with self.lock:
            for attempt in range(self.retry_count + 1):
                try:
                    self.ser.reset_input_buffer()

                    self._trace("TX", req, note)
                    self.ser.write(req)
                    self.ser.flush()

                    head = self._read_exact(3)
                    rid, func, third = head

                    if func & 0x80:
                        tail = self._read_exact(2)
                        frame = head + tail
                        self._trace("RX", frame, note)
                        self._check_crc(frame)

                        if rid != (slave_id & 0xFF):
                            raise ValueError(
                                f"从站ID不匹配：期望{slave_id}，收到{rid}"
                            )

                        raise RuntimeError(
                            f"Modbus异常响应，异常码=0x{third:02X}"
                        )

                    byte_count = third
                    tail = self._read_exact(byte_count + 2)
                    frame = head + tail

                    self._trace("RX", frame, note)
                    self._check_crc(frame)

                    if rid != (slave_id & 0xFF):
                        raise ValueError(
                            f"从站ID不匹配：期望{slave_id}，收到{rid}"
                        )

                    if func != 0x03:
                        raise ValueError(
                            f"功能码错误：期望03H，收到0x{func:02X}"
                        )

                    if byte_count != count * 2:
                        raise ValueError(
                            f"返回字节数错误：期望{count * 2}，收到{byte_count}"
                        )

                    return list(
                        struct.unpack(
                            ">" + "H" * count,
                            frame[3:-2]
                        )
                    )

                except Exception as exc:
                    last_error = exc
                    self._trace(
                        "ERR",
                        b"",
                        f"{note} attempt={attempt + 1} -> {exc}"
                    )
                    if attempt < self.retry_count:
                        time.sleep(0.02)

        raise last_error

    def write_multiple_registers(self, slave_id, start_addr, values):
        if not self.is_open:
            raise RuntimeError("串口未打开")

        values = [int(v) & 0xFFFF for v in values]

        if not 1 <= len(values) <= 123:
            raise ValueError("写寄存器数量必须为1~123")

        payload = struct.pack(
            ">" + "H" * len(values),
            *values
        )

        req = append_crc(
            struct.pack(
                ">BBHHB",
                slave_id & 0xFF,
                0x10,
                start_addr & 0xFFFF,
                len(values),
                len(payload),
            ) + payload
        )

        note = (
            f"ID={slave_id} 10H WRITE "
            f"addr={start_addr} count={len(values)}"
        )

        last_error = None

        with self.lock:
            for attempt in range(self.retry_count + 1):
                try:
                    self.ser.reset_input_buffer()

                    self._trace("TX", req, note)
                    self.ser.write(req)
                    self.ser.flush()

                    head = self._read_exact(2)
                    rid, func = head

                    if func & 0x80:
                        tail = self._read_exact(3)
                        frame = head + tail
                        self._trace("RX", frame, note)
                        self._check_crc(frame)

                        if rid != (slave_id & 0xFF):
                            raise ValueError(
                                f"从站ID不匹配：期望{slave_id}，收到{rid}"
                            )

                        raise RuntimeError(
                            f"Modbus异常响应，异常码=0x{frame[2]:02X}"
                        )

                    tail = self._read_exact(6)
                    frame = head + tail

                    self._trace("RX", frame, note)
                    self._check_crc(frame)

                    rid, func, resp_addr, resp_count = struct.unpack(
                        ">BBHH",
                        frame[:-2]
                    )

                    if rid != (slave_id & 0xFF):
                        raise ValueError(
                            f"从站ID不匹配：期望{slave_id}，收到{rid}"
                        )

                    if func != 0x10:
                        raise ValueError(
                            f"功能码错误：期望10H，收到0x{func:02X}"
                        )

                    if resp_addr != (start_addr & 0xFFFF):
                        raise ValueError(
                            f"写入响应地址错误：期望{start_addr}，收到{resp_addr}"
                        )

                    if resp_count != len(values):
                        raise ValueError(
                            f"写入响应数量错误：期望{len(values)}，收到{resp_count}"
                        )

                    return

                except Exception as exc:
                    last_error = exc
                    self._trace(
                        "ERR",
                        b"",
                        f"{note} attempt={attempt + 1} -> {exc}"
                    )
                    if attempt < self.retry_count:
                        time.sleep(0.02)

        raise last_error

    def read_u16(self, slave_id, addr):
        return self.read_holding_registers(
            slave_id,
            addr,
            1
        )[0]

    def write_u16(self, slave_id, addr, value):
        self.write_multiple_registers(
            slave_id,
            addr,
            [value]
        )

    def read_float_be(self, slave_id, addr):
        regs = self.read_holding_registers(
            slave_id,
            addr,
            2
        )
        return regs_to_float_be(regs[0], regs[1])

    def write_float_be(self, slave_id, addr, value):
        self.write_multiple_registers(
            slave_id,
            addr,
            float_to_regs_be(value)
        )


# ============================================================
# GUI
# ============================================================

class BatchCalibrationApp(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title("25台流量计批量自动标定软件")
        self.geometry("1420x880")
        self.minsize(1180, 720)

        self.mb = ModbusRTUMaster()
        self.mb.set_trace_callback(self._modbus_trace_callback)

        self.ui_queue = queue.Queue()
        self.stop_event = threading.Event()
        self.worker = None
        self.zeroing = False
        self.active_meter_ids = list(METER_IDS)
        self.device_gap_s = 0.02

        self._build_ui()
        self.refresh_ports()

        self.after(100, self._process_ui_queue)
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    # --------------------------------------------------------
    # UI
    # --------------------------------------------------------

    def _build_ui(self):
        params = ttk.LabelFrame(
            self,
            text="通信与标定参数",
            padding=8
        )
        params.pack(
            fill="x",
            padx=10,
            pady=8
        )

        ttk.Label(params, text="串口").grid(row=0, column=0, padx=3, pady=3)

        self.port_var = tk.StringVar()
        self.port_combo = ttk.Combobox(
            params,
            textvariable=self.port_var,
            width=13,
            state="readonly"
        )
        self.port_combo.grid(row=0, column=1, padx=4)

        ttk.Button(
            params,
            text="刷新",
            command=self.refresh_ports
        ).grid(row=0, column=2, padx=3)

        ttk.Label(params, text="波特率").grid(row=0, column=3, padx=3)

        self.baud_var = tk.StringVar(value="115200")
        ttk.Combobox(
            params,
            textvariable=self.baud_var,
            width=9,
            values=("9600", "19200", "38400", "57600", "115200")
        ).grid(row=0, column=4, padx=4)

        ttk.Label(params, text="量程 ml/min").grid(row=0, column=5, padx=3)

        self.range_var = tk.StringVar(value="3000")
        ttk.Entry(
            params,
            textvariable=self.range_var,
            width=9
        ).grid(row=0, column=6, padx=4)

        ttk.Label(params, text="温度点6009").grid(row=0, column=7, padx=3)

        self.temp_var = tk.StringVar(value="1")
        ttk.Entry(
            params,
            textvariable=self.temp_var,
            width=7
        ).grid(row=0, column=8, padx=4)

        ttk.Label(params, text="稳定容差 %F.S.").grid(row=1, column=0, padx=3)

        self.stable_tol_var = tk.StringVar(value="0.5")
        ttk.Entry(
            params,
            textvariable=self.stable_tol_var,
            width=9
        ).grid(row=1, column=1, padx=4)

        ttk.Label(params, text="连续稳定 s").grid(row=1, column=3, padx=3)

        self.stable_time_var = tk.StringVar(value="3.0")
        ttk.Entry(
            params,
            textvariable=self.stable_time_var,
            width=9
        ).grid(row=1, column=4, padx=4)

        ttk.Label(params, text="稳定等待超时 s").grid(row=1, column=5, padx=3)

        self.stable_timeout_var = tk.StringVar(value="120")
        ttk.Entry(
            params,
            textvariable=self.stable_timeout_var,
            width=9
        ).grid(row=1, column=6, padx=4)

        ttk.Label(params, text="单点标定超时 s").grid(row=1, column=7, padx=3)

        self.point_timeout_var = tk.StringVar(value="15")
        ttk.Entry(
            params,
            textvariable=self.point_timeout_var,
            width=7
        ).grid(row=1, column=8, padx=4)

        ttk.Label(params, text="标准值刷新间隔 s").grid(row=1, column=9, padx=3)

        self.std_update_var = tk.StringVar(value="0.2")
        ttk.Entry(
            params,
            textvariable=self.std_update_var,
            width=7
        ).grid(row=1, column=10, padx=4)

        self.zero_end_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            params,
            text="结束/停止后目标置0",
            variable=self.zero_end_var
        ).grid(row=1, column=11, padx=8)

        ttk.Label(params, text="标定流量计数量").grid(row=2, column=0, padx=3, pady=3)
        self.meter_count_var = tk.StringVar(value="25")
        ttk.Entry(params, textvariable=self.meter_count_var, width=9).grid(row=2, column=1, padx=4)
        ttk.Label(params, text="从ID2开始连续").grid(row=2, column=2, padx=3)

        ttk.Label(params, text="设备轮询间隔 ms").grid(row=2, column=3, padx=3)
        self.device_gap_ms_var = tk.StringVar(value="20")
        ttk.Entry(params, textvariable=self.device_gap_ms_var, width=9).grid(row=2, column=4, padx=4)

        ttk.Label(params, text="通讯失败重试次数").grid(row=2, column=5, padx=3)
        self.retry_count_var = tk.StringVar(value="2")
        ttk.Entry(params, textvariable=self.retry_count_var, width=9).grid(row=2, column=6, padx=4)

        self.connect_btn = ttk.Button(
            params,
            text="连接",
            command=self.toggle_connection
        )
        self.connect_btn.grid(row=0, column=9, padx=4)

        self.scan_btn = ttk.Button(
            params,
            text="扫描流量计",
            command=self.scan_devices
        )
        self.scan_btn.grid(row=0, column=10, padx=4)

        self.start_btn = ttk.Button(
            params,
            text="开始批量标定",
            command=self.start_calibration
        )
        self.start_btn.grid(row=0, column=11, padx=4)

        self.stop_btn = ttk.Button(
            params,
            text="停止",
            command=self.stop_calibration,
            state="disabled"
        )
        self.stop_btn.grid(row=0, column=12, padx=4)

        self.zero_btn = ttk.Button(
            params,
            text="流量计调零",
            command=self.open_zero_dialog
        )
        self.zero_btn.grid(row=0, column=13, padx=4)

        # 顶部状态
        status_frame = ttk.Frame(self)
        status_frame.pack(fill="x", padx=10)

        self.status_var = tk.StringVar(value="未连接 / 空闲")
        self.batch_var = tk.StringVar(value="有效流量计：-/25")
        self.point_var = tk.StringVar(value="当前点：-")
        self.controller_fb_var = tk.StringVar(value="标准反馈：-")

        ttk.Label(
            status_frame,
            textvariable=self.status_var
        ).pack(side="left")

        ttk.Label(
            status_frame,
            textvariable=self.batch_var
        ).pack(side="left", padx=20)

        ttk.Label(
            status_frame,
            textvariable=self.point_var
        ).pack(side="left", padx=20)

        ttk.Label(
            status_frame,
            textvariable=self.controller_fb_var
        ).pack(side="left", padx=20)

        self.progress = ttk.Progressbar(
            status_frame,
            maximum=100
        )
        self.progress.pack(
            side="right",
            fill="x",
            expand=True,
            padx=(20, 0)
        )

        # 主体
        body = ttk.Panedwindow(
            self,
            orient="horizontal"
        )
        body.pack(
            fill="both",
            expand=True,
            padx=10,
            pady=8
        )

        left = ttk.LabelFrame(
            body,
            text="流量控制器 / 流量计实时状态",
            padding=5
        )

        right = ttk.LabelFrame(
            body,
            text="日志",
            padding=5
        )

        body.add(left, weight=3)
        body.add(right, weight=2)

        columns = (
            "id",
            "online",
            "point",
            "temp_rb",
            "flowpoint_rb",
            "flag",
            "feedback",
            "result"
        )

        self.tree = ttk.Treeview(
            left,
            columns=columns,
            show="headings"
        )

        configs = (
            ("id", "ID", 48),
            ("online", "通信", 70),
            ("point", "当前标定点", 95),
            ("temp_rb", "6009读回", 78),
            ("flowpoint_rb", "6010读回", 78),
            ("flag", "6003", 60),
            ("feedback", "流量反馈", 105),
            ("result", "本轮结果", 135),
        )

        for col, title, width in configs:
            self.tree.heading(col, text=title)
            self.tree.column(
                col,
                width=width,
                anchor="center"
            )

        tree_scroll = ttk.Scrollbar(
            left,
            orient="vertical",
            command=self.tree.yview
        )

        self.tree.configure(
            yscrollcommand=tree_scroll.set
        )

        self.tree.pack(
            side="left",
            fill="both",
            expand=True
        )
        tree_scroll.pack(side="right", fill="y")

        # ID1 标准流量控制器放在第一行
        self.tree.insert(
            "",
            "end",
            iid="controller_1",
            values=(
                1,
                "未连接",
                "-",
                "-",
                "-",
                "-",
                "-",
                "标准流量控制器"
            )
        )

        # ID2~26 待标定流量计
        for sid in METER_IDS:
            self.tree.insert(
                "",
                "end",
                iid=f"meter_{sid}",
                values=(sid, "未扫描", "-", "-", "-", "-", "-", "-")
            )

        notebook = ttk.Notebook(right)
        notebook.pack(fill="both", expand=True)

        run_tab = ttk.Frame(notebook)
        serial_tab = ttk.Frame(notebook)
        caldata_tab = ttk.Frame(notebook)

        notebook.add(run_tab, text="运行日志")
        notebook.add(serial_tab, text="串口收发")
        notebook.add(caldata_tab, text="标定数据")

        cal_toolbar = ttk.Frame(caldata_tab)
        cal_toolbar.pack(fill="x")
        self.read_cal_data_btn = ttk.Button(
            cal_toolbar,
            text="读取标定数据 61028~61039",
            command=self.read_calibration_data
        )
        self.read_cal_data_btn.pack(side="left", padx=3, pady=3)
        ttk.Label(
            cal_toolbar,
            text="每两个寄存器大端float：5% / 20% / 40% / 60% / 80% / 100%"
        ).pack(side="left", padx=8)

        cal_columns = ("id", "p5", "p20", "p40", "p60", "p80", "p100", "state")
        self.caldata_tree = ttk.Treeview(caldata_tab, columns=cal_columns, show="headings")
        for col, title, width in (
            ("id", "ID", 42),
            ("p5", "5%", 88),
            ("p20", "20%", 88),
            ("p40", "40%", 88),
            ("p60", "60%", 88),
            ("p80", "80%", 88),
            ("p100", "100%", 88),
            ("state", "状态", 90),
        ):
            self.caldata_tree.heading(col, text=title)
            self.caldata_tree.column(col, width=width, anchor="center")

        cal_scroll = ttk.Scrollbar(caldata_tab, orient="vertical", command=self.caldata_tree.yview)
        self.caldata_tree.configure(yscrollcommand=cal_scroll.set)
        self.caldata_tree.pack(side="left", fill="both", expand=True)
        cal_scroll.pack(side="right", fill="y")

        for sid in METER_IDS:
            self.caldata_tree.insert(
                "", "end", iid=f"cal_{sid}",
                values=(sid, "-", "-", "-", "-", "-", "-", "未读取")
            )

        run_toolbar = ttk.Frame(run_tab)
        run_toolbar.pack(fill="x")

        ttk.Button(
            run_toolbar,
            text="清空",
            command=lambda: self.run_log.delete("1.0", "end")
        ).pack(side="right", padx=2, pady=2)

        self.run_log = tk.Text(
            run_tab,
            wrap="word"
        )

        run_scroll = ttk.Scrollbar(
            run_tab,
            orient="vertical",
            command=self.run_log.yview
        )

        self.run_log.configure(
            yscrollcommand=run_scroll.set
        )

        self.run_log.pack(
            side="left",
            fill="both",
            expand=True
        )
        run_scroll.pack(side="right", fill="y")

        serial_toolbar = ttk.Frame(serial_tab)
        serial_toolbar.pack(fill="x")

        ttk.Label(
            serial_toolbar,
            text="TX=发送  RX=接收  ERR=错误"
        ).pack(side="left", padx=3)

        ttk.Button(
            serial_toolbar,
            text="清空",
            command=lambda: self.serial_log.delete("1.0", "end")
        ).pack(side="right", padx=2, pady=2)

        serial_frame = ttk.Frame(serial_tab)
        serial_frame.pack(fill="both", expand=True)

        self.serial_log = tk.Text(
            serial_frame,
            wrap="none",
            font=("Consolas", 9)
        )

        sy = ttk.Scrollbar(
            serial_frame,
            orient="vertical",
            command=self.serial_log.yview
        )

        sx = ttk.Scrollbar(
            serial_frame,
            orient="horizontal",
            command=self.serial_log.xview
        )

        self.serial_log.configure(
            yscrollcommand=sy.set,
            xscrollcommand=sx.set
        )

        self.serial_log.grid(row=0, column=0, sticky="nsew")
        sy.grid(row=0, column=1, sticky="ns")
        sx.grid(row=1, column=0, sticky="ew")

        serial_frame.rowconfigure(0, weight=1)
        serial_frame.columnconfigure(0, weight=1)

        # 底部
        bottom = ttk.LabelFrame(
            self,
            text="说明",
            padding=8
        )
        bottom.pack(
            fill="x",
            padx=10,
            pady=(0, 10)
        )

        ttk.Label(
            bottom,
            text=(
                "顺序：100% → 80% → 60% → 40% → 20% → 5%。"
                " 单台流量计失败仅剔除该台；ID1标准控制单元异常则停止整批，避免误标。"
            )
        ).pack(side="left")

        self.csv_var = tk.StringVar(value="CSV：-")
        ttk.Label(
            bottom,
            textvariable=self.csv_var
        ).pack(side="right")

    # --------------------------------------------------------
    # UI辅助
    # --------------------------------------------------------

    def refresh_ports(self):
        ports = [
            p.device
            for p in list_ports.comports()
        ]

        self.port_combo["values"] = ports

        if ports and self.port_var.get() not in ports:
            self.port_var.set(ports[0])

    def _log(self, text):
        self.run_log.insert(
            "end",
            f"[{datetime.now().strftime('%H:%M:%S')}] {text}\n"
        )
        self.run_log.see("end")

        try:
            line_count = int(
                self.run_log.index("end-1c").split(".")[0]
            )
            if line_count > 3000:
                self.run_log.delete("1.0", "501.0")
        except Exception:
            pass

    def _modbus_trace_callback(self, direction, frame, note):
        self.ui_queue.put(
            ("serial", direction, frame, note)
        )

    def _append_serial(self, direction, frame, note):
        stamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]

        hex_text = (
            " ".join(f"{x:02X}" for x in frame)
            if frame
            else "-"
        )

        self.serial_log.insert(
            "end",
            f"[{stamp}] {direction:<3} {note}\n"
            f"    {hex_text}\n"
        )
        self.serial_log.see("end")

        try:
            line_count = int(
                self.serial_log.index("end-1c").split(".")[0]
            )
            if line_count > 6000:
                self.serial_log.delete("1.0", "1001.0")
        except Exception:
            pass

    def _set_controller_row(
        self,
        online=None,
        point=None,
        feedback=None,
        result=None
    ):
        iid = "controller_1"
        old = list(self.tree.item(iid, "values"))
        while len(old) < 8:
            old.append("-")
        if online is not None:
            old[1] = online
        if point is not None:
            old[2] = point
        old[3] = "-"
        old[4] = "-"
        old[5] = "-"
        if feedback is not None:
            old[6] = feedback
        if result is not None:
            old[7] = result
        self.tree.item(iid, values=tuple(old))


    def _set_meter_row(
        self,
        sid,
        online=None,
        point=None,
        temp_rb=None,
        flowpoint_rb=None,
        flag=None,
        feedback=None,
        result=None
    ):
        iid = f"meter_{sid}"
        old = list(self.tree.item(iid, "values"))
        while len(old) < 8:
            old.append("-")
        if online is not None:
            old[1] = online
        if point is not None:
            old[2] = point
        if temp_rb is not None:
            old[3] = temp_rb
        if flowpoint_rb is not None:
            old[4] = flowpoint_rb
        if flag is not None:
            old[5] = flag
        if feedback is not None:
            old[6] = feedback
        if result is not None:
            old[7] = result
        self.tree.item(iid, values=tuple(old))


    # --------------------------------------------------------
    # 串口连接
    # --------------------------------------------------------

    def toggle_connection(self):
        if self.mb.is_open:
            if self.worker and self.worker.is_alive():
                messagebox.showwarning(
                    "提示",
                    "标定运行中，请先停止。"
                )
                return

            self.mb.close()
            self.connect_btn.config(text="连接")
            self.status_var.set("未连接 / 空闲")
            self._set_controller_row(
                online="未连接",
                point="-",
                feedback="-",
                result="标准流量控制器"
            )
            self._log("串口已断开")
            return

        if not self.port_var.get():
            messagebox.showerror(
                "错误",
                "请选择串口。"
            )
            return

        try:
            self.mb.open(
                self.port_var.get(),
                int(self.baud_var.get()),
                float(self.timeout_from_ui())
            )

            self.connect_btn.config(text="断开")
            self.status_var.set(
                f"已连接 {self.port_var.get()} @ {self.baud_var.get()}"
            )
            self._set_controller_row(
                online="待检测",
                point="-",
                feedback="-",
                result="串口已连接"
            )
            self._log(
                f"串口连接成功：{self.port_var.get()} @ {self.baud_var.get()}"
            )

        except Exception as exc:
            messagebox.showerror(
                "连接失败",
                str(exc)
            )

    def timeout_from_ui(self):
        # 串口超时这里固定0.25s，避免和“单点标定超时”混淆。
        return 0.25

    def _apply_device_settings(self):
        meter_count = int(self.meter_count_var.get())
        device_gap_ms = float(self.device_gap_ms_var.get())
        retry_count = int(self.retry_count_var.get())
        if meter_count < 1 or meter_count > 25:
            raise ValueError("标定流量计数量必须为1~25")
        if device_gap_ms < 0:
            raise ValueError("设备轮询间隔不能小于0")
        if retry_count < 0 or retry_count > 10:
            raise ValueError("通讯失败重试次数建议设置为0~10")

        self.active_meter_ids = list(range(2, 2 + meter_count))
        self.device_gap_s = device_gap_ms / 1000.0
        self.mb.retry_count = retry_count

        active = set(self.active_meter_ids)
        for sid in METER_IDS:
            if sid not in active:
                self._set_meter_row(
                    sid, online="未参与", point="-", temp_rb="-", flowpoint_rb="-",
                    flag="-", feedback="-", result="未参与"
                )
                self.caldata_tree.item(
                    f"cal_{sid}",
                    values=(sid, "-", "-", "-", "-", "-", "-", "未参与")
                )
        return meter_count, device_gap_ms, retry_count

    def _device_gap_wait(self, index):
        if index > 0 and self.device_gap_s > 0:
            if self.stop_event.wait(self.device_gap_s):
                raise RuntimeError("用户停止")

    def read_calibration_data(self):
        if not self.mb.is_open:
            messagebox.showerror("错误", "请先连接串口。")
            return
        if self.worker and self.worker.is_alive():
            messagebox.showwarning("提示", "标定运行中，请标定结束后再读取标定数据。")
            return
        if self.zeroing:
            messagebox.showwarning("提示", "调零运行中，请等待调零结束。")
            return
        try:
            self._apply_device_settings()
        except Exception as exc:
            messagebox.showerror("参数错误", str(exc))
            return

        self.stop_event.clear()
        self.read_cal_data_btn.config(state="disabled")
        threading.Thread(
            target=self._read_calibration_data_worker,
            args=(list(self.active_meter_ids),),
            daemon=True
        ).start()

    def _read_calibration_data_worker(self, meter_ids):
        self.ui_queue.put(("log", "开始读取61028~61039六个标定点..."))
        for index, sid in enumerate(meter_ids):
            if self.stop_event.is_set():
                break
            try:
                self._device_gap_wait(index)
                regs = self.mb.read_holding_registers(sid, REG_METER_CAL_DATA, 12)
                values = [
                    regs_to_float_be(regs[i], regs[i + 1])
                    for i in range(0, 12, 2)
                ]
                if not all(math.isfinite(v) for v in values):
                    raise ValueError("返回的标定点包含NaN/Inf")
                self.ui_queue.put(("cal_data", sid, values, "读取成功"))
            except Exception as exc:
                self.ui_queue.put(("cal_data_error", sid, str(exc)))
        self.ui_queue.put(("cal_data_done",))

    # --------------------------------------------------------
    # 指定流量计调零
    # --------------------------------------------------------

    def open_zero_dialog(self):
        """
        弹出选择窗口，选择需要调零的流量计。
        调零命令：向6008写1。
        """
        if not self.mb.is_open:
            messagebox.showerror(
                "错误",
                "请先连接串口。"
            )
            return

        if self.worker and self.worker.is_alive():
            messagebox.showwarning(
                "提示",
                "标定运行中不能执行调零。"
            )
            return

        if self.zeroing:
            messagebox.showwarning(
                "提示",
                "调零任务正在执行。"
            )
            return

        try:
            meter_count, gap_ms, retry_count = self._apply_device_settings()
        except Exception as exc:
            messagebox.showerror(
                "参数错误",
                str(exc)
            )
            return

        dialog = tk.Toplevel(self)
        dialog.title("选择需要调零的流量计")
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()

        ttk.Label(
            dialog,
            text=(
                f"当前参与设备：ID{self.active_meter_ids[0]}"
                f"~ID{self.active_meter_ids[-1]}，共{meter_count}台\n"
                f"确认后将按当前轮询间隔 {gap_ms:.1f} ms，"
                f"向选中设备的6008写1。"
            ),
            justify="left"
        ).grid(
            row=0,
            column=0,
            columnspan=5,
            padx=12,
            pady=(10, 8),
            sticky="w"
        )

        vars_by_id = {}

        # 默认全部勾选当前参与设备
        for index, sid in enumerate(self.active_meter_ids):
            var = tk.BooleanVar(value=True)
            vars_by_id[sid] = var

            row = 1 + index // 5
            col = index % 5

            ttk.Checkbutton(
                dialog,
                text=f"ID{sid}",
                variable=var
            ).grid(
                row=row,
                column=col,
                padx=10,
                pady=5,
                sticky="w"
            )

        button_row = 1 + ((len(self.active_meter_ids) + 4) // 5)

        def select_all():
            for var in vars_by_id.values():
                var.set(True)

        def select_none():
            for var in vars_by_id.values():
                var.set(False)

        def confirm_zero():
            selected_ids = [
                sid
                for sid, var in vars_by_id.items()
                if var.get()
            ]

            if not selected_ids:
                messagebox.showwarning(
                    "提示",
                    "请至少选择一台流量计。",
                    parent=dialog
                )
                return

            dialog.grab_release()
            dialog.destroy()

            self.start_zeroing(selected_ids)

        ttk.Button(
            dialog,
            text="全选",
            command=select_all
        ).grid(
            row=button_row,
            column=0,
            padx=6,
            pady=10
        )

        ttk.Button(
            dialog,
            text="全不选",
            command=select_none
        ).grid(
            row=button_row,
            column=1,
            padx=6,
            pady=10
        )

        ttk.Button(
            dialog,
            text="确认调零",
            command=confirm_zero
        ).grid(
            row=button_row,
            column=3,
            padx=6,
            pady=10
        )

        ttk.Button(
            dialog,
            text="取消",
            command=dialog.destroy
        ).grid(
            row=button_row,
            column=4,
            padx=6,
            pady=10
        )

    def start_zeroing(self, selected_ids):
        """
        启动指定设备调零线程。
        """
        if self.zeroing:
            return

        try:
            self._apply_device_settings()
        except Exception as exc:
            messagebox.showerror(
                "参数错误",
                str(exc)
            )
            return

        self.zeroing = True
        self.stop_event.clear()

        self.zero_btn.config(state="disabled")
        self.scan_btn.config(state="disabled")
        self.start_btn.config(state="disabled")
        self.zero_btn.config(state="disabled")
        self.read_cal_data_btn.config(state="disabled")

        self._log(
            "开始指定流量计调零："
            + ",".join(f"ID{sid}" for sid in selected_ids)
            + "；向6008写1。"
        )

        for sid in selected_ids:
            self._set_meter_row(
                sid,
                result="准备调零"
            )

        threading.Thread(
            target=self._zero_worker,
            args=(list(selected_ids),),
            daemon=True
        ).start()

    def _zero_worker(self, selected_ids):
        success_ids = []
        failed_ids = []

        for index, sid in enumerate(selected_ids):
            if self.stop_event.is_set():
                break

            try:
                self._device_gap_wait(index)

                self.mb.write_u16(
                    sid,
                    REG_METER_ZERO,
                    1
                )

                success_ids.append(sid)

                self.ui_queue.put((
                    "zero_result",
                    sid,
                    True,
                    ""
                ))

            except Exception as exc:
                failed_ids.append(sid)

                self.ui_queue.put((
                    "zero_result",
                    sid,
                    False,
                    str(exc)
                ))

        self.ui_queue.put((
            "zero_done",
            success_ids,
            failed_ids
        ))


    # --------------------------------------------------------
    # 扫描
    # --------------------------------------------------------

    def scan_devices(self):
        if not self.mb.is_open:
            messagebox.showerror(
                "错误",
                "请先连接串口。"
            )
            return

        if self.worker and self.worker.is_alive():
            messagebox.showwarning(
                "提示",
                "标定运行中不能扫描。"
            )
            return
        if self.zeroing:
            messagebox.showwarning(
                "提示",
                "调零运行中不能扫描。"
            )
            return

        try:
            meter_count, gap_ms, retry_count = self._apply_device_settings()
        except Exception as exc:
            messagebox.showerror("参数错误", str(exc))
            return

        self._log(
            f"扫描：ID{self.active_meter_ids[0]}~ID{self.active_meter_ids[-1]}，"
            f"共{meter_count}台；轮询间隔={gap_ms:.1f}ms；重试={retry_count}次。"
        )

        self.stop_event.clear()
        self.scan_btn.config(state="disabled")
        self.start_btn.config(state="disabled")

        threading.Thread(
            target=self._scan_worker,
            daemon=True
        ).start()

    def _scan_worker(self):
        online_ids = []

        self.ui_queue.put(("log", "开始扫描ID2~26，并读取61022/61023流量反馈..."))

        for index, sid in enumerate(self.active_meter_ids):
            if self.stop_event.is_set():
                break

            self._device_gap_wait(index)

            try:
                # 先读取6003，确认设备在线
                flag = self.mb.read_u16(
                    sid,
                    REG_METER_CAL_FLAG
                )

                online_ids.append(sid)

                # 在线后继续读取61022/61023反馈流量
                try:
                    feedback = self.mb.read_float_be(
                        sid,
                        REG_METER_FEEDBACK
                    )

                    if not math.isfinite(feedback):
                        raise ValueError(
                            f"返回无效float：{feedback}"
                        )

                    feedback_text = f"{feedback:.3f}"
                    result_text = "待标定"

                except Exception as feedback_exc:
                    feedback_text = "-"
                    result_text = "反馈读取失败"

                    self.ui_queue.put((
                        "log",
                        f"ID{sid} 在线，但61022/61023反馈读取失败："
                        f"{feedback_exc}"
                    ))

                self.ui_queue.put((
                    "meter",
                    sid,
                    "在线",
                    "-",
                    str(flag),
                    feedback_text,
                    result_text
                ))

            except Exception:
                self.ui_queue.put((
                    "meter",
                    sid,
                    "离线",
                    "-",
                    "-",
                    "-",
                    "未参与"
                ))

        self.ui_queue.put((
            "scan_done",
            online_ids
        ))

    # --------------------------------------------------------
    # 标定入口
    # --------------------------------------------------------

    def start_calibration(self):
        if self.worker and self.worker.is_alive():
            return

        if self.zeroing:
            messagebox.showwarning(
                "提示",
                "调零运行中，请等待调零完成后再开始标定。"
            )
            return

        if not self.mb.is_open:
            messagebox.showerror(
                "错误",
                "请先连接串口。"
            )
            return

        try:
            flow_range = float(self.range_var.get())
            temp_point = int(self.temp_var.get())
            stable_tol_fs = float(self.stable_tol_var.get())
            stable_time = float(self.stable_time_var.get())
            stable_timeout = float(self.stable_timeout_var.get())
            point_timeout = float(self.point_timeout_var.get())
            std_update_interval = float(self.std_update_var.get())
            meter_count, device_gap_ms, retry_count = self._apply_device_settings()

            if flow_range <= 0:
                raise ValueError("量程必须大于0")
            if temp_point < 0 or temp_point > 65535:
                raise ValueError("温度点范围错误")
            if stable_tol_fs <= 0:
                raise ValueError("稳定容差必须大于0")
            if stable_time <= 0:
                raise ValueError("连续稳定时间必须大于0")
            if stable_timeout <= stable_time:
                raise ValueError("稳定等待超时必须大于连续稳定时间")
            if point_timeout < 6:
                raise ValueError("单点标定超时建议至少6秒")
            if std_update_interval < 0:
                raise ValueError("标准值刷新间隔不能小于0")

        except Exception as exc:
            messagebox.showerror(
                "参数错误",
                str(exc)
            )
            return

        self._log(
            f"本次标定：ID{self.active_meter_ids[0]}~ID{self.active_meter_ids[-1]}，"
            f"共{len(self.active_meter_ids)}台；轮询间隔={self.device_gap_s*1000.0:.1f}ms；"
            f"失败重试={self.mb.retry_count}次。"
        )

        filename = filedialog.asksaveasfilename(
            title="选择标定记录保存位置",
            defaultextension=".csv",
            initialfile=(
                "batch_calibration_"
                + datetime.now().strftime("%Y%m%d_%H%M%S")
                + ".csv"
            ),
            filetypes=[
                ("CSV文件", "*.csv"),
                ("所有文件", "*.*")
            ]
        )

        if not filename:
            return

        self.csv_var.set(f"CSV：{filename}")

        self.stop_event.clear()
        self.start_btn.config(state="disabled")
        self.scan_btn.config(state="disabled")
        self.zero_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.progress["value"] = 0

        self._set_controller_row(
            online="检测中",
            point="-",
            feedback="-",
            result="准备标定"
        )

        for sid in self.active_meter_ids:
            self._set_meter_row(
                sid, online="待检测", point="-", temp_rb="-", flowpoint_rb="-",
                flag="-", feedback="-", result="准备中"
            )

        args = (
            flow_range,
            temp_point,
            stable_tol_fs,
            stable_time,
            stable_timeout,
            point_timeout,
            std_update_interval,
            filename,
        )

        self.worker = threading.Thread(
            target=self._calibration_worker,
            args=args,
            daemon=True
        )
        self.worker.start()

    def stop_calibration(self):
        self.stop_event.set()
        self.status_var.set("正在停止...")

    # --------------------------------------------------------
    # 控制器辅助
    # --------------------------------------------------------

    def _write_controller_target_required(self, target):
        last_error = None

        for attempt in range(1, CONTROLLER_WRITE_RETRY + 1):
            if self.stop_event.is_set():
                raise RuntimeError("用户停止")

            try:
                self.mb.write_float_be(
                    CONTROLLER_ID,
                    REG_CONTROLLER_TARGET,
                    target
                )

                self.ui_queue.put((
                    "log",
                    f"ID1目标写入成功：{target:.3f} ml/min"
                ))

                return

            except Exception as exc:
                last_error = exc

                self.ui_queue.put((
                    "log",
                    f"ID1目标写入失败 "
                    f"({attempt}/{CONTROLLER_WRITE_RETRY})：{exc}"
                ))

                self.stop_event.wait(0.20)

        raise RuntimeError(
            f"ID1目标连续写入失败，停止整批标定：{last_error}"
        )

    def _wait_controller_stable(
        self,
        target,
        flow_range,
        tolerance_fs_percent,
        stable_seconds,
        timeout_seconds
    ):
        """
        判定：
            abs(反馈 - 目标) / 满量程 * 100 <= tolerance_fs_percent
        且连续满足 stable_seconds。
        """
        deadline = time.monotonic() + timeout_seconds
        stable_since = None
        last_feedback = math.nan

        allowed_abs_error = (
            flow_range
            * tolerance_fs_percent
            / 100.0
        )

        self.ui_queue.put((
            "log",
            f"等待标准流量稳定：目标={target:.3f}，"
            f"允许±{allowed_abs_error:.3f} ml/min "
            f"({tolerance_fs_percent:.3f}%F.S.)，"
            f"连续稳定{stable_seconds:.1f}s"
        ))

        while not self.stop_event.is_set():
            if time.monotonic() > deadline:
                raise RuntimeError(
                    f"ID1标准流量稳定等待超时：目标={target:.3f} ml/min，"
                    f"最后反馈={last_feedback}"
                )

            try:
                feedback = self.mb.read_float_be(
                    CONTROLLER_ID,
                    REG_CONTROLLER_FEEDBACK
                )

                if not math.isfinite(feedback):
                    raise ValueError(
                        f"标准反馈无效：{feedback}"
                    )

                last_feedback = feedback

                self.ui_queue.put((
                    "controller_fb",
                    feedback
                ))

                error = abs(feedback - target)

                if error <= allowed_abs_error:
                    if stable_since is None:
                        stable_since = time.monotonic()

                    stable_elapsed = (
                        time.monotonic()
                        - stable_since
                    )

                    self.ui_queue.put((
                        "status",
                        f"标准流量稳定计时 "
                        f"{stable_elapsed:.1f}/{stable_seconds:.1f}s"
                    ))

                    if stable_elapsed >= stable_seconds:
                        self.ui_queue.put((
                            "log",
                            f"标准流量已稳定：{feedback:.3f} ml/min"
                        ))
                        return feedback

                else:
                    stable_since = None

                    self.ui_queue.put((
                        "status",
                        f"等待标准流量稳定，"
                        f"当前={feedback:.3f} ml/min"
                    ))

            except Exception as exc:
                stable_since = None

                self.ui_queue.put((
                    "log",
                    f"读取ID1标准反馈失败：{exc}，继续等待恢复。"
                ))

            self.stop_event.wait(0.20)

        raise RuntimeError("用户停止")

    # --------------------------------------------------------
    # 单流量点标定
    # --------------------------------------------------------

    def _prepare_meter_for_point(
        self,
        sid,
        temp_point,
        point_code,
        standard_flow
    ):
        """
        先写标准流量，再一次写6009/6010，最后由外层统一写6003=1。
        """
        self.mb.write_float_be(
            sid,
            REG_METER_STANDARD_FLOW,
            standard_flow
        )

        # 6009和6010连续，一次0x10写入
        self.mb.write_multiple_registers(
            sid,
            REG_METER_TEMP_POINT,
            [temp_point, point_code]
        )

        # 写完马上读取6009/6010，显示在左侧并校验是否写正确。
        readback = self.mb.read_holding_registers(
            sid,
            REG_METER_TEMP_POINT,
            2
        )
        temp_read = readback[0]
        point_read = readback[1]
        self.ui_queue.put(("meter_setup", sid, temp_read, point_read))

        if temp_read != temp_point or point_read != point_code:
            raise RuntimeError(
                f"6009/6010读回不一致：期望{temp_point}/{point_code}，"
                f"读回{temp_read}/{point_read}"
            )
        return temp_read, point_read

    def _run_one_point(
        self,
        active_ids,
        percent,
        point_code,
        target,
        temp_point,
        point_timeout,
        std_update_interval,
        csv_writer,
        csv_file
    ):
        """
        返回：
            completed_ids, failed_ids
        """
        # 再读取一次真实标准流量，作为启动前标准值
        start_standard = self.mb.read_float_be(
            CONTROLLER_ID,
            REG_CONTROLLER_FEEDBACK
        )

        if not math.isfinite(start_standard):
            raise RuntimeError(
                "当前标准流量反馈无效，不能开始标定。"
            )

        self.ui_queue.put((
            "controller_fb",
            start_standard
        ))

        prepared_ids = []
        failed_ids = set()

        # 1. 准备每台流量计
        for device_index, sid in enumerate(sorted(active_ids)):
            if self.stop_event.is_set():
                raise RuntimeError("用户停止")
            self._device_gap_wait(device_index)

            try:
                self._prepare_meter_for_point(
                    sid,
                    temp_point,
                    point_code,
                    start_standard
                )

                prepared_ids.append(sid)

                self.ui_queue.put((
                    "meter",
                    sid,
                    "在线",
                    f"{percent}%",
                    "-",
                    "-",
                    "已准备"
                ))

            except Exception as exc:
                failed_ids.add(sid)

                self.ui_queue.put((
                    "meter",
                    sid,
                    "异常",
                    f"{percent}%",
                    "-",
                    "-",
                    "准备失败"
                ))

                self.ui_queue.put((
                    "log",
                    f"ID{sid} 当前点准备失败，剔除本轮标定：{exc}"
                ))

                self._write_csv_event(
                    csv_writer,
                    csv_file,
                    sid,
                    percent,
                    point_code,
                    target,
                    start_standard,
                    "",
                    "",
                    "FAIL",
                    "prepare failed"
                )

        # 2. 统一启动6003=1
        started_ids = []

        for device_index, sid in enumerate(prepared_ids):
            if sid in failed_ids:
                continue
            self._device_gap_wait(device_index)

            try:
                self.mb.write_u16(
                    sid,
                    REG_METER_CAL_FLAG,
                    1
                )

                started_ids.append(sid)

                self.ui_queue.put((
                    "meter",
                    sid,
                    "在线",
                    f"{percent}%",
                    "1",
                    "-",
                    "标定中"
                ))

            except Exception as exc:
                failed_ids.add(sid)

                self.ui_queue.put((
                    "meter",
                    sid,
                    "异常",
                    f"{percent}%",
                    "-",
                    "-",
                    "启动失败"
                ))

                self.ui_queue.put((
                    "log",
                    f"ID{sid} 6003启动失败，剔除本轮标定：{exc}"
                ))

                self._write_csv_event(
                    csv_writer,
                    csv_file,
                    sid,
                    percent,
                    point_code,
                    target,
                    start_standard,
                    "",
                    "",
                    "FAIL",
                    "6003 start failed"
                )

        pending = {
            sid
            for sid in started_ids
            if sid not in failed_ids
        }

        completed = set()

        consecutive_errors = {
            sid: 0
            for sid in pending
        }

        std_sum = 0.0
        std_count = 0

        point_start = time.monotonic()
        next_update = 0.0

        self.ui_queue.put((
            "log",
            f"{percent}%点已启动："
            f"{len(pending)}台进入5秒从机标定。"
        ))

        # 3. 标定期间持续更新61004并轮询6003
        while pending and not self.stop_event.is_set():
            elapsed = time.monotonic() - point_start

            if elapsed >= point_timeout:
                break

            # 读取一次标准表实际反馈
            try:
                standard_flow = self.mb.read_float_be(
                    CONTROLLER_ID,
                    REG_CONTROLLER_FEEDBACK
                )

                if not math.isfinite(standard_flow):
                    raise ValueError(
                        f"标准反馈无效：{standard_flow}"
                    )

                self.ui_queue.put((
                    "controller_fb",
                    standard_flow
                ))

                std_sum += standard_flow
                std_count += 1

            except Exception as exc:
                self.ui_queue.put((
                    "log",
                    f"当前点读取ID1标准反馈失败：{exc}；"
                    "暂不更新61004，继续尝试。"
                ))

                self.stop_event.wait(0.10)
                continue

            now = time.monotonic()

            # 标准值刷新
            if now >= next_update:
                next_update = (
                    now
                    + max(std_update_interval, 0.0)
                )

                for device_index, sid in enumerate(sorted(pending)):
                    self._device_gap_wait(device_index)
                    try:
                        self.mb.write_float_be(
                            sid,
                            REG_METER_STANDARD_FLOW,
                            standard_flow
                        )

                        consecutive_errors[sid] = 0

                    except Exception as exc:
                        consecutive_errors[sid] += 1

                        self.ui_queue.put((
                            "log",
                            f"ID{sid} 更新61004失败 "
                            f"{consecutive_errors[sid]}/"
                            f"{METER_CONSECUTIVE_ERROR_LIMIT}：{exc}"
                        ))

                        if (
                            consecutive_errors[sid]
                            >= METER_CONSECUTIVE_ERROR_LIMIT
                        ):
                            failed_ids.add(sid)
                            pending.discard(sid)

                            self.ui_queue.put((
                                "meter",
                                sid,
                                "异常",
                                f"{percent}%",
                                "-",
                                "-",
                                "标准值写入失败"
                            ))

                            self._write_csv_event(
                                csv_writer,
                                csv_file,
                                sid,
                                percent,
                                point_code,
                                target,
                                start_standard,
                                (
                                    std_sum / std_count
                                    if std_count
                                    else ""
                                ),
                                "",
                                "FAIL",
                                "61004 update failed"
                            )

            # 轮询6003
            for device_index, sid in enumerate(sorted(pending)):
                self._device_gap_wait(device_index)
                try:
                    flag = self.mb.read_u16(
                        sid,
                        REG_METER_CAL_FLAG
                    )

                    consecutive_errors[sid] = 0

                    self.ui_queue.put((
                        "meter_flag",
                        sid,
                        flag
                    ))

                    if flag == 0:
                        completed.add(sid)
                        pending.discard(sid)

                        # 当前点结束后读取一次流量计反馈，仅作为记录观察
                        try:
                            meter_feedback = self.mb.read_float_be(
                                sid,
                                REG_METER_FEEDBACK
                            )

                            if not math.isfinite(meter_feedback):
                                meter_feedback = math.nan

                        except Exception:
                            meter_feedback = math.nan

                        feedback_text = (
                            "-"
                            if math.isnan(meter_feedback)
                            else f"{meter_feedback:.3f}"
                        )

                        self.ui_queue.put((
                            "meter",
                            sid,
                            "在线",
                            f"{percent}%",
                            "0",
                            feedback_text,
                            "当前点完成"
                        ))

                        self._write_csv_event(
                            csv_writer,
                            csv_file,
                            sid,
                            percent,
                            point_code,
                            target,
                            start_standard,
                            (
                                std_sum / std_count
                                if std_count
                                else start_standard
                            ),
                            (
                                ""
                                if math.isnan(meter_feedback)
                                else meter_feedback
                            ),
                            "PASS",
                            "point complete"
                        )

                except Exception as exc:
                    consecutive_errors[sid] += 1

                    self.ui_queue.put((
                        "log",
                        f"ID{sid} 轮询6003失败 "
                        f"{consecutive_errors[sid]}/"
                        f"{METER_CONSECUTIVE_ERROR_LIMIT}：{exc}"
                    ))

                    if (
                        consecutive_errors[sid]
                        >= METER_CONSECUTIVE_ERROR_LIMIT
                    ):
                        failed_ids.add(sid)
                        pending.discard(sid)

                        self.ui_queue.put((
                            "meter",
                            sid,
                            "异常",
                            f"{percent}%",
                            "-",
                            "-",
                            "通信失败"
                        ))

                        self._write_csv_event(
                            csv_writer,
                            csv_file,
                            sid,
                            percent,
                            point_code,
                            target,
                            start_standard,
                            (
                                std_sum / std_count
                                if std_count
                                else ""
                            ),
                            "",
                            "FAIL",
                            "6003 polling communication failed"
                        )

            progress = min(
                elapsed / max(point_timeout, 0.001),
                1.0
            )

            self.ui_queue.put((
                "point_progress",
                progress,
                len(completed),
                len(started_ids)
            ))

            self.stop_event.wait(0.05)

        if self.stop_event.is_set():
            raise RuntimeError("用户停止")

        # 4. 超时仍pending的设备判失败
        for sid in list(pending):
            failed_ids.add(sid)

            self.ui_queue.put((
                "meter",
                sid,
                "异常",
                f"{percent}%",
                "-",
                "-",
                "标定超时"
            ))

            self._write_csv_event(
                csv_writer,
                csv_file,
                sid,
                percent,
                point_code,
                target,
                start_standard,
                (
                    std_sum / std_count
                    if std_count
                    else ""
                ),
                "",
                "FAIL",
                "point timeout"
            )

        self.ui_queue.put((
            "log",
            f"{percent}%点结束："
            f"完成{len(completed)}台，失败{len(failed_ids)}台。"
        ))

        return completed, failed_ids

    # --------------------------------------------------------
    # CSV
    # --------------------------------------------------------

    @staticmethod
    def _write_csv_event(
        writer,
        csv_file,
        sid,
        percent,
        point_code,
        target,
        standard_start,
        standard_average,
        meter_feedback,
        result,
        note
    ):
        writer.writerow([
            datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
            sid,
            percent,
            point_code,
            f"{target:.6f}" if isinstance(target, (int, float)) else target,
            (
                f"{standard_start:.6f}"
                if isinstance(standard_start, (int, float))
                else standard_start
            ),
            (
                f"{standard_average:.6f}"
                if isinstance(standard_average, (int, float))
                else standard_average
            ),
            (
                f"{meter_feedback:.6f}"
                if isinstance(meter_feedback, (int, float))
                else meter_feedback
            ),
            result,
            note,
        ])
        csv_file.flush()

    # --------------------------------------------------------
    # 主标定线程
    # --------------------------------------------------------

    def _calibration_worker(
        self,
        flow_range,
        temp_point,
        stable_tol_fs,
        stable_time,
        stable_timeout,
        point_timeout,
        std_update_interval,
        filename
    ):
        try:
            os.makedirs(
                os.path.dirname(filename) or ".",
                exist_ok=True
            )

            with open(
                filename,
                "w",
                newline="",
                encoding="utf-8-sig"
            ) as csv_file:

                writer = csv.writer(csv_file)

                writer.writerow([
                    "timestamp",
                    "meter_id",
                    "point_percent",
                    "6010_point_code",
                    "target_flow_ml_min",
                    "controller_feedback_start_ml_min",
                    "controller_feedback_average_ml_min",
                    "meter_feedback_after_ml_min",
                    "result",
                    "note",
                ])
                csv_file.flush()

                # ----------------------------------------------------
                # A. 先确认ID1可通信
                # ----------------------------------------------------
                self.ui_queue.put((
                    "status",
                    "检查标准流量控制器ID1..."
                ))

                controller_feedback = self.mb.read_float_be(
                    CONTROLLER_ID,
                    REG_CONTROLLER_FEEDBACK
                )

                if not math.isfinite(controller_feedback):
                    raise RuntimeError(
                        "ID1反馈不是有效浮点数。"
                    )

                self.ui_queue.put((
                    "controller_fb",
                    controller_feedback
                ))

                # ----------------------------------------------------
                # B. 自动扫描ID2~26
                # ----------------------------------------------------
                active_ids = set()

                self.ui_queue.put((
                    "log",
                    "自动扫描本次选择的待标定流量计..."
                ))

                for device_index, sid in enumerate(self.active_meter_ids):
                    if self.stop_event.is_set():
                        raise RuntimeError("用户停止")
                    self._device_gap_wait(device_index)

                    try:
                        flag = self.mb.read_u16(
                            sid,
                            REG_METER_CAL_FLAG
                        )

                        active_ids.add(sid)

                        self.ui_queue.put((
                            "meter",
                            sid,
                            "在线",
                            "-",
                            str(flag),
                            "-",
                            "待标定"
                        ))

                    except Exception:
                        self.ui_queue.put((
                            "meter",
                            sid,
                            "离线",
                            "-",
                            "-",
                            "-",
                            "未参与"
                        ))

                if not active_ids:
                    raise RuntimeError(
                        "本次选择的流量计均未检测到，无法开始标定。"
                    )

                self.ui_queue.put((
                    "batch",
                    len(active_ids)
                ))

                self.ui_queue.put((
                    "log",
                    f"扫描完成：{len(active_ids)}/{len(self.active_meter_ids)}台进入本轮标定。"
                ))

                originally_active = set(active_ids)
                failed_total = set()

                # ----------------------------------------------------
                # C. 六个流量点
                # ----------------------------------------------------
                total_points = len(CAL_POINTS)

                for point_index, (percent, point_code) in enumerate(CAL_POINTS):
                    if self.stop_event.is_set():
                        raise RuntimeError("用户停止")

                    if not active_ids:
                        raise RuntimeError(
                            "所有流量计均已标定失败，本批次停止。"
                        )

                    target = (
                        flow_range
                        * percent
                        / 100.0
                    )

                    self.ui_queue.put((
                        "point",
                        percent,
                        point_code,
                        target
                    ))

                    self.ui_queue.put((
                        "log",
                        "================================================"
                    ))

                    self.ui_queue.put((
                        "log",
                        f"开始 {percent}% 标定点："
                        f"6010={point_code}，目标={target:.3f} ml/min，"
                        f"当前有效{len(active_ids)}台。"
                    ))

                    # 1) 写控制器目标
                    self._write_controller_target_required(
                        target
                    )

                    # 2) 等反馈稳定
                    stable_feedback = self._wait_controller_stable(
                        target,
                        flow_range,
                        stable_tol_fs,
                        stable_time,
                        stable_timeout
                    )

                    # 进入当前点之前，再给UI一个稳定后的标准值
                    self.ui_queue.put((
                        "controller_fb",
                        stable_feedback
                    ))

                    # 3) 当前点标定
                    completed_ids, failed_ids = self._run_one_point(
                        active_ids,
                        percent,
                        point_code,
                        target,
                        temp_point,
                        point_timeout,
                        std_update_interval,
                        writer,
                        csv_file
                    )

                    # 当前点失败的设备不再参与后续点，
                    # 防止得到“缺一两个点”的假完整标定。
                    failed_total.update(failed_ids)
                    active_ids = set(completed_ids)

                    self.ui_queue.put((
                        "batch",
                        len(active_ids)
                    ))

                    # 六点总进度：当前点完成后更新
                    self.ui_queue.put((
                        "overall_progress",
                        (point_index + 1)
                        / total_points
                        * 100.0
                    ))

                # ----------------------------------------------------
                # D. 完成
                # ----------------------------------------------------
                passed_ids = sorted(active_ids)
                failed_ids = sorted(
                    originally_active - active_ids
                )

                for sid in passed_ids:
                    self.ui_queue.put((
                        "meter_result",
                        sid,
                        "六点标定完成"
                    ))

                for sid in failed_ids:
                    self.ui_queue.put((
                        "meter_result",
                        sid,
                        "本轮标定失败"
                    ))

                self.ui_queue.put((
                    "log",
                    "================================================"
                ))

                self.ui_queue.put((
                    "log",
                    f"整批标定结束：成功{len(passed_ids)}台，"
                    f"失败{len(failed_ids)}台。"
                ))

                self.ui_queue.put((
                    "log",
                    "成功ID："
                    + (
                        ",".join(str(x) for x in passed_ids)
                        if passed_ids
                        else "无"
                    )
                ))

                self.ui_queue.put((
                    "log",
                    "失败ID："
                    + (
                        ",".join(str(x) for x in failed_ids)
                        if failed_ids
                        else "无"
                    )
                ))

                # 追加批次汇总行
                writer.writerow([])
                writer.writerow([
                    "SUMMARY",
                    "PASS_IDS",
                    ",".join(str(x) for x in passed_ids)
                ])
                writer.writerow([
                    "SUMMARY",
                    "FAIL_IDS",
                    ",".join(str(x) for x in failed_ids)
                ])
                csv_file.flush()

                # 六点标定完成后，自动读取成功设备61028~61039用于核对。
                self.ui_queue.put(("log", "开始自动读取成功设备的六个标定点..."))
                for read_index, sid in enumerate(passed_ids):
                    if self.stop_event.is_set():
                        raise RuntimeError("用户停止")
                    try:
                        self._device_gap_wait(read_index)
                        regs = self.mb.read_holding_registers(sid, REG_METER_CAL_DATA, 12)
                        values = [regs_to_float_be(regs[i], regs[i + 1]) for i in range(0, 12, 2)]
                        self.ui_queue.put(("cal_data", sid, values, "标定后读取"))
                    except Exception as exc:
                        self.ui_queue.put(("cal_data_error", sid, str(exc)))

            # 正常结束后目标置0
            if self.zero_end_var.get() and self.mb.is_open:
                try:
                    self.mb.write_float_be(
                        CONTROLLER_ID,
                        REG_CONTROLLER_TARGET,
                        0.0
                    )
                    self.ui_queue.put((
                        "log",
                        "标定结束，ID1目标流量已置0。"
                    ))
                    self.ui_queue.put((
                        "controller_zero",
                    ))
                except Exception as exc:
                    self.ui_queue.put((
                        "log",
                        f"标定结束后目标置0失败：{exc}"
                    ))

            self.ui_queue.put((
                "finished",
                True,
                filename
            ))

        except Exception as exc:
            # 停止或异常时尽量将流量目标置0
            if self.zero_end_var.get() and self.mb.is_open:
                try:
                    self.mb.write_float_be(
                        CONTROLLER_ID,
                        REG_CONTROLLER_TARGET,
                        0.0
                    )
                except Exception:
                    pass

            stopped = (
                self.stop_event.is_set()
                or str(exc) == "用户停止"
            )

            if stopped:
                self.ui_queue.put((
                    "log",
                    "用户停止标定。"
                ))
                self.ui_queue.put((
                    "finished",
                    False,
                    filename
                ))
            else:
                self.ui_queue.put((
                    "fatal",
                    str(exc)
                ))

    # --------------------------------------------------------
    # UI队列
    # --------------------------------------------------------

    def _process_ui_queue(self):
        try:
            while True:
                msg = self.ui_queue.get_nowait()
                kind = msg[0]

                if kind == "serial":
                    self._append_serial(
                        msg[1],
                        msg[2],
                        msg[3]
                    )

                elif kind == "log":
                    self._log(msg[1])

                elif kind == "status":
                    self.status_var.set(msg[1])

                    status_text = str(msg[1])

                    if "标准流量稳定计时" in status_text:
                        self._set_controller_row(
                            online="在线",
                            result="流量稳定中"
                        )
                    elif "等待标准流量稳定" in status_text:
                        self._set_controller_row(
                            online="在线",
                            result="等待稳定"
                        )
                    elif "检查标准流量控制器ID1" in status_text:
                        self._set_controller_row(
                            online="检测中",
                            result="通信检测"
                        )

                elif kind == "batch":
                    self.batch_var.set(
                        f"当前有效流量计：{msg[1]}/{len(self.active_meter_ids)}"
                    )

                elif kind == "controller_fb":
                    self.controller_fb_var.set(
                        f"标准反馈：{msg[1]:.3f} ml/min"
                    )

                    self._set_controller_row(
                        online="在线",
                        feedback=f"{msg[1]:.3f}",
                        result="标准反馈正常"
                    )

                elif kind == "point":
                    percent, point_code, target = (
                        msg[1],
                        msg[2],
                        msg[3]
                    )

                    self.point_var.set(
                        f"当前点：{percent}% "
                        f"(6010={point_code}) "
                        f"{target:.3f} ml/min"
                    )

                    self._set_controller_row(
                        online="在线",
                        point=f"{percent}% / {target:.1f}",
                        result="控制/标准"
                    )

                    self.status_var.set(
                        f"正在标定 {percent}%"
                    )

                elif kind == "meter":
                    (
                        sid,
                        online,
                        point,
                        flag,
                        feedback,
                        result
                    ) = msg[1:]

                    self._set_meter_row(
                        sid,
                        online=online,
                        point=point,
                        flag=flag,
                        feedback=feedback,
                        result=result
                    )

                elif kind == "meter_setup":
                    sid, temp_read, point_read = msg[1], msg[2], msg[3]
                    self._set_meter_row(
                        sid,
                        temp_rb=str(temp_read),
                        flowpoint_rb=str(point_read)
                    )

                elif kind == "meter_flag":
                    sid, flag = msg[1], msg[2]

                    self._set_meter_row(
                        sid,
                        flag=str(flag)
                    )

                elif kind == "meter_result":
                    sid, result = msg[1], msg[2]

                    self._set_meter_row(
                        sid,
                        result=result
                    )

                elif kind == "point_progress":
                    fraction, complete_count, total_count = (
                        msg[1],
                        msg[2],
                        msg[3]
                    )

                    self.status_var.set(
                        f"{self.point_var.get()}："
                        f"{complete_count}/{total_count}台完成"
                    )

                elif kind == "overall_progress":
                    self.progress["value"] = msg[1]

                elif kind == "scan_done":
                    online_ids = msg[1]
                    total = len(self.active_meter_ids)
                    self.batch_var.set(f"扫描在线：{len(online_ids)}/{total}")
                    self._log(f"扫描完成：在线{len(online_ids)}/{total}台。")
                    self.scan_btn.config(state="normal")
                    self.start_btn.config(state="normal")
                    self.zero_btn.config(state="normal")

                elif kind == "cal_data":
                    sid, values, state = msg[1], msg[2], msg[3]
                    texts = [f"{v:.3f}" if math.isfinite(v) else "-" for v in values]
                    self.caldata_tree.item(
                        f"cal_{sid}",
                        values=(sid, *texts, state)
                    )

                elif kind == "cal_data_error":
                    sid, error = msg[1], msg[2]
                    self.caldata_tree.item(
                        f"cal_{sid}",
                        values=(sid, "-", "-", "-", "-", "-", "-", "读取失败")
                    )
                    self._log(f"ID{sid}读取61028~61039失败：{error}")

                elif kind == "cal_data_done":
                    self.read_cal_data_btn.config(state="normal")
                    self._log("标定数据读取完成。")

                elif kind == "zero_result":
                    sid, success, error = msg[1], msg[2], msg[3]

                    if success:
                        self._set_meter_row(
                            sid,
                            online="在线",
                            result="调零命令已发送"
                        )
                        self._log(
                            f"ID{sid}：6008写1成功。"
                        )
                    else:
                        self._set_meter_row(
                            sid,
                            online="异常",
                            result="调零失败"
                        )
                        self._log(
                            f"ID{sid}：6008写1失败：{error}"
                        )

                elif kind == "zero_done":
                    success_ids, failed_ids = msg[1], msg[2]

                    self.zeroing = False

                    self.zero_btn.config(state="normal")
                    self.scan_btn.config(state="normal")
                    self.start_btn.config(state="normal")
                    self.read_cal_data_btn.config(state="normal")

                    self.status_var.set("调零完成")

                    self._log(
                        f"指定流量计调零结束：成功{len(success_ids)}台，"
                        f"失败{len(failed_ids)}台。"
                    )

                    if success_ids:
                        self._log(
                            "调零成功ID："
                            + ",".join(str(x) for x in success_ids)
                        )

                    if failed_ids:
                        self._log(
                            "调零失败ID："
                            + ",".join(str(x) for x in failed_ids)
                        )

                elif kind == "controller_zero":
                    self._set_controller_row(
                        point="0% / 0.0",
                        result="目标已置0"
                    )

                elif kind == "finished":
                    success, filename = msg[1], msg[2]

                    self.start_btn.config(state="normal")
                    self.scan_btn.config(state="normal")
                    self.zero_btn.config(state="normal")
                    self.stop_btn.config(state="disabled")

                    if success:
                        self.status_var.set("批量标定完成")
                        self.progress["value"] = 100
                        self._set_controller_row(
                            online="在线",
                            point="完成",
                            result="标定完成"
                        )
                        self._log(
                            f"标定记录已保存：{filename}"
                        )
                    else:
                        self.status_var.set("标定已停止")
                        self._set_controller_row(
                            point="停止",
                            result="标定已停止"
                        )
                        self._log(
                            f"已保存停止前的标定记录：{filename}"
                        )

                elif kind == "fatal":
                    self.start_btn.config(state="normal")
                    self.scan_btn.config(state="normal")
                    self.zero_btn.config(state="normal")
                    self.stop_btn.config(state="disabled")

                    self.status_var.set("标定异常停止")
                    self._set_controller_row(
                        online="异常",
                        result="标准/控制异常"
                    )
                    self._log(
                        "标定异常停止："
                        + msg[1]
                    )

                    messagebox.showerror(
                        "标定异常",
                        msg[1]
                    )

        except queue.Empty:
            pass

        self.after(
            100,
            self._process_ui_queue
        )

    # --------------------------------------------------------
    # 关闭
    # --------------------------------------------------------

    def on_close(self):
        self.stop_event.set()

        try:
            if self.zero_end_var.get() and self.mb.is_open:
                try:
                    self.mb.write_float_be(
                        CONTROLLER_ID,
                        REG_CONTROLLER_TARGET,
                        0.0
                    )
                except Exception:
                    pass
        finally:
            self.mb.close()
            self.destroy()


if __name__ == "__main__":
    BatchCalibrationApp().mainloop()
