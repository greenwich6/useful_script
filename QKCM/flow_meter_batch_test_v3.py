# -*- coding: utf-8 -*-
"""
25台流量计 + 1台流量控制器 Modbus RTU 批量测试软件

依赖：
    pip install pyserial

设备：
    流量控制器 ID = 1
    流量计 ID = 2~26，共25台

寄存器：
    控制器目标流量：62026/62027，float ABCD，高16位在前
    控制器反馈流量：62016/62017，float ABCD，高16位在前
    流量计反馈流量：61022/61023，float ABCD，高16位在前

测试顺序：
    100% -> 80% -> 60% -> 40% -> 20% -> 5%
    完成后自动回到100%，无限循环，直到用户点击“停止”。

误差：
    每台流量计误差采用有符号满量程误差：
    Error(%F.S.) = (流量计反馈 - 控制器反馈) / 流量计满量程 * 100%

重要：
    1. 本程序按给定寄存器地址直接发送，不做 -1。
    2. 任意单台设备通信失败都不会终止整轮测试。
    3. ID1目标写入失败会重试，仍失败则记录错误并继续当前点和后续测试。
    4. “串口收发”页显示每次Modbus TX/RX的原始十六进制帧。
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


CONTROLLER_ID = 1
METER_IDS = list(range(2, 27))

REG_CONTROLLER_TARGET = 62026
REG_CONTROLLER_FEEDBACK = 62016
REG_METER_FEEDBACK = 61022

TEST_POINTS = [100, 80, 60, 40, 20, 5]

CONTROLLER_WRITE_RETRIES = 3


def crc16(data: bytes) -> int:
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            if crc & 0x0001:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc & 0xFFFF


def with_crc(data: bytes) -> bytes:
    c = crc16(data)
    return data + bytes((c & 0xFF, (c >> 8) & 0xFF))


def float_to_regs(value: float):
    return struct.unpack(">HH", struct.pack(">f", float(value)))


def regs_to_float(r0: int, r1: int) -> float:
    return struct.unpack(
        ">f",
        struct.pack(">HH", r0 & 0xFFFF, r1 & 0xFFFF)
    )[0]


class ModbusRTU:
    def __init__(self):
        self.ser = None
        self.lock = threading.Lock()
        self.timeout = 0.25
        self.retry_count = 2
        self.trace_callback = None

    @property
    def opened(self):
        return self.ser is not None and self.ser.is_open

    def set_trace_callback(self, callback):
        self.trace_callback = callback

    def _trace(self, direction, frame=b"", note=""):
        if self.trace_callback is not None:
            try:
                self.trace_callback(direction, bytes(frame), note)
            except Exception:
                pass

    def open(self, port, baud, timeout):
        self.close()
        self.timeout = float(timeout)

        self.ser = serial.Serial(
            port=port,
            baudrate=int(baud),
            bytesize=8,
            parity=serial.PARITY_NONE,
            stopbits=1,
            timeout=self.timeout,
            write_timeout=self.timeout
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

    def _read_exact(self, n):
        if not self.opened:
            raise RuntimeError("串口未打开")

        data = bytearray()
        end_time = time.monotonic() + self.timeout

        while len(data) < n and time.monotonic() < end_time:
            part = self.ser.read(n - len(data))
            if part:
                data.extend(part)

        if len(data) != n:
            raise TimeoutError(
                f"接收超时：需要{n}字节，实际收到{len(data)}字节"
            )

        return bytes(data)

    @staticmethod
    def _check_crc(frame):
        if len(frame) < 4:
            raise ValueError("Modbus响应过短")

        recv_crc = frame[-2] | (frame[-1] << 8)
        calc_crc = crc16(frame[:-2])

        if recv_crc != calc_crc:
            raise ValueError(
                f"CRC错误：recv=0x{recv_crc:04X}, calc=0x{calc_crc:04X}"
            )

    def read_regs(self, sid, addr, count):
        """0x03读取保持寄存器，失败后按retry_count重试。"""
        if not self.opened:
            raise RuntimeError("串口未打开")

        req = with_crc(
            struct.pack(
                ">BBHH",
                sid & 0xFF,
                0x03,
                addr & 0xFFFF,
                count & 0xFFFF
            )
        )

        note = f"ID={sid} 03H READ addr={addr} count={count}"
        last_error = None

        for attempt in range(self.retry_count + 1):
            try:
                with self.lock:
                    self.ser.reset_input_buffer()
                    self._trace(
                        "TX",
                        req,
                        note + f" try={attempt + 1}/{self.retry_count + 1}"
                    )
                    self.ser.write(req)
                    self.ser.flush()

                    head = self._read_exact(3)
                    rid, func, byte_count = head

                    if func & 0x80:
                        tail = self._read_exact(2)
                        frame = head + tail
                        self._trace("RX", frame, note)
                        self._check_crc(frame)
                        raise RuntimeError(
                            f"Modbus异常响应：ID={sid}, 异常码=0x{byte_count:02X}"
                        )

                    tail = self._read_exact(byte_count + 2)
                    frame = head + tail
                    self._trace("RX", frame, note)
                    self._check_crc(frame)

                    if rid != (sid & 0xFF):
                        raise ValueError(
                            f"从站ID不匹配：期望{sid}，收到{rid}"
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
                    f"{note} try={attempt + 1}/{self.retry_count + 1} -> {exc}"
                )
                if attempt < self.retry_count:
                    time.sleep(0.03)

        raise last_error


    def write_regs(self, sid, addr, values):
        """0x10写多个保持寄存器，失败后按retry_count重试。"""
        if not self.opened:
            raise RuntimeError("串口未打开")

        values = [int(v) & 0xFFFF for v in values]
        payload = struct.pack(
            ">" + "H" * len(values),
            *values
        )

        req = with_crc(
            struct.pack(
                ">BBHHB",
                sid & 0xFF,
                0x10,
                addr & 0xFFFF,
                len(values) & 0xFFFF,
                len(payload)
            ) + payload
        )

        note = f"ID={sid} 10H WRITE addr={addr} count={len(values)}"
        last_error = None

        for attempt in range(self.retry_count + 1):
            try:
                with self.lock:
                    self.ser.reset_input_buffer()
                    self._trace(
                        "TX",
                        req,
                        note + f" try={attempt + 1}/{self.retry_count + 1}"
                    )
                    self.ser.write(req)
                    self.ser.flush()

                    head = self._read_exact(2)
                    rid, func = head

                    if func & 0x80:
                        tail = self._read_exact(3)
                        frame = head + tail
                        self._trace("RX", frame, note)
                        self._check_crc(frame)
                        raise RuntimeError(
                            f"Modbus异常响应：ID={sid}, 异常码=0x{frame[2]:02X}"
                        )

                    tail = self._read_exact(6)
                    frame = head + tail
                    self._trace("RX", frame, note)
                    self._check_crc(frame)

                    rid, func, resp_addr, resp_count = struct.unpack(
                        ">BBHH",
                        frame[:-2]
                    )

                    if rid != (sid & 0xFF):
                        raise ValueError(
                            f"从站ID不匹配：期望{sid}，收到{rid}"
                        )

                    if func != 0x10:
                        raise ValueError(
                            f"功能码错误：期望10H，收到0x{func:02X}"
                        )

                    if resp_addr != (addr & 0xFFFF):
                        raise ValueError(
                            f"写入响应地址错误：期望{addr}，收到{resp_addr}"
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
                    f"{note} try={attempt + 1}/{self.retry_count + 1} -> {exc}"
                )
                if attempt < self.retry_count:
                    time.sleep(0.03)

        raise last_error


    def read_float(self, sid, addr):
        regs = self.read_regs(sid, addr, 2)
        return regs_to_float(regs[0], regs[1])

    def write_float(self, sid, addr, value):
        self.write_regs(
            sid,
            addr,
            float_to_regs(value)
        )


class App(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title("流量计批量测试软件")
        self.geometry("1320x840")
        self.minsize(1100, 700)

        self.mb = ModbusRTU()
        self.stop_evt = threading.Event()
        self.q = queue.Queue()
        self.worker = None
        self.active_meter_ids = list(METER_IDS)

        self.mb.set_trace_callback(
            self._modbus_trace_callback
        )

        self._build()
        self.refresh_ports()

        self.after(100, self._poll_ui)
        self.protocol("WM_DELETE_WINDOW", self.close_app)

    def _build(self):
        p = ttk.LabelFrame(
            self,
            text="通信与测试参数",
            padding=8
        )
        p.pack(fill="x", padx=10, pady=8)

        ttk.Label(p, text="串口").grid(row=0, column=0)

        self.port = tk.StringVar()
        self.port_cb = ttk.Combobox(
            p,
            textvariable=self.port,
            width=13,
            state="readonly"
        )
        self.port_cb.grid(row=0, column=1, padx=4)

        ttk.Button(
            p,
            text="刷新",
            command=self.refresh_ports
        ).grid(row=0, column=2, padx=3)

        ttk.Label(p, text="波特率").grid(row=0, column=3)

        self.baud = tk.StringVar(value="115200")
        ttk.Combobox(
            p,
            textvariable=self.baud,
            width=9,
            values=(
                "9600",
                "19200",
                "38400",
                "57600",
                "115200"
            )
        ).grid(row=0, column=4, padx=4)

        ttk.Label(p, text="量程 ml/min").grid(row=0, column=5)

        self.flow_range = tk.StringVar(value="3000")
        ttk.Entry(
            p,
            textvariable=self.flow_range,
            width=9
        ).grid(row=0, column=6, padx=4)

        ttk.Label(p, text="稳定等待 s").grid(row=1, column=0)

        self.settle = tk.StringVar(value="10")
        ttk.Entry(
            p,
            textvariable=self.settle,
            width=9
        ).grid(row=1, column=1, padx=4)

        ttk.Label(p, text="采集时间 s").grid(row=1, column=3)

        self.capture = tk.StringVar(value="10")
        ttk.Entry(
            p,
            textvariable=self.capture,
            width=9
        ).grid(row=1, column=4, padx=4)

        ttk.Label(p, text="整轮采样周期 s").grid(row=1, column=5)

        self.interval = tk.StringVar(value="1.0")
        ttk.Entry(
            p,
            textvariable=self.interval,
            width=9
        ).grid(row=1, column=6, padx=4)

        ttk.Label(p, text="超时 s").grid(row=1, column=7)

        self.timeout = tk.StringVar(value="0.25")
        ttk.Entry(
            p,
            textvariable=self.timeout,
            width=7
        ).grid(row=1, column=8, padx=4)

        self.zero_end = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            p,
            text="结束/停止后目标置0",
            variable=self.zero_end
        ).grid(row=1, column=9, padx=8)

        ttk.Label(p, text="测试流量计数量").grid(row=2, column=0)
        self.meter_count_var = tk.StringVar(value="25")
        ttk.Entry(
            p,
            textvariable=self.meter_count_var,
            width=9
        ).grid(row=2, column=1, padx=4)

        ttk.Label(p, text="从ID2开始连续").grid(row=2, column=2)

        ttk.Label(p, text="设备间通讯间隔 ms").grid(row=2, column=3)
        self.device_gap_ms_var = tk.StringVar(value="20")
        ttk.Entry(
            p,
            textvariable=self.device_gap_ms_var,
            width=9
        ).grid(row=2, column=4, padx=4)

        ttk.Label(p, text="通讯失败重试次数").grid(row=2, column=5)
        self.retry_count_var = tk.StringVar(value="2")
        ttk.Entry(
            p,
            textvariable=self.retry_count_var,
            width=9
        ).grid(row=2, column=6, padx=4)

        self.connect_btn = ttk.Button(
            p,
            text="连接",
            command=self.toggle_connect
        )
        self.connect_btn.grid(row=0, column=8, padx=4)

        self.start_btn = ttk.Button(
            p,
            text="开始测试",
            command=self.start
        )
        self.start_btn.grid(row=0, column=9, padx=4)

        self.stop_btn = ttk.Button(
            p,
            text="停止",
            command=self.stop,
            state="disabled"
        )
        self.stop_btn.grid(row=0, column=10, padx=4)

        s = ttk.Frame(self)
        s.pack(fill="x", padx=10)

        self.status = tk.StringVar(value="未连接 / 空闲")
        self.online = tk.StringVar(value="流量计在线：-/25")

        ttk.Label(s, textvariable=self.status).pack(side="left")
        ttk.Label(s, textvariable=self.online).pack(side="left", padx=30)

        self.progress = ttk.Progressbar(s, maximum=100)
        self.progress.pack(
            side="right",
            fill="x",
            expand=True,
            padx=(20, 0)
        )

        body = ttk.Panedwindow(self, orient="horizontal")
        body.pack(fill="both", expand=True, padx=10, pady=8)

        lf = ttk.LabelFrame(
            body,
            text="实时数据",
            padding=5
        )
        rf = ttk.LabelFrame(
            body,
            text="通信信息",
            padding=5
        )

        body.add(lf, weight=3)
        body.add(rf, weight=2)

        self.tree = ttk.Treeview(
            lf,
            columns=("id", "type", "flow", "error_fs", "state"),
            show="headings"
        )

        for col, title, width in (
            ("id", "ID", 60),
            ("type", "设备", 120),
            ("flow", "反馈流量 ml/min", 170),
            ("error_fs", "误差 %F.S.", 120),
            ("state", "状态", 120)
        ):
            self.tree.heading(col, text=title)
            self.tree.column(col, width=width, anchor="center")

        tree_scroll = ttk.Scrollbar(
            lf,
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
        tree_scroll.pack(
            side="right",
            fill="y"
        )

        self.tree.insert(
            "",
            "end",
            iid="c",
            values=(1, "流量控制器", "-", "-", "-")
        )

        for mid in METER_IDS:
            self.tree.insert(
                "",
                "end",
                iid=f"m{mid}",
                values=(mid, "流量计", "-", "-", "-")
            )

        notebook = ttk.Notebook(rf)
        notebook.pack(fill="both", expand=True)

        log_tab = ttk.Frame(notebook)
        serial_tab = ttk.Frame(notebook)

        notebook.add(log_tab, text="运行日志")
        notebook.add(serial_tab, text="串口收发")

        log_toolbar = ttk.Frame(log_tab)
        log_toolbar.pack(fill="x")

        ttk.Button(
            log_toolbar,
            text="清空",
            command=self._clear_run_log
        ).pack(side="right", padx=2, pady=2)

        self.log = tk.Text(log_tab, wrap="word")

        log_scroll = ttk.Scrollbar(
            log_tab,
            orient="vertical",
            command=self.log.yview
        )

        self.log.configure(
            yscrollcommand=log_scroll.set
        )

        self.log.pack(
            side="left",
            fill="both",
            expand=True
        )
        log_scroll.pack(side="right", fill="y")

        serial_toolbar = ttk.Frame(serial_tab)
        serial_toolbar.pack(fill="x")

        ttk.Label(
            serial_toolbar,
            text="TX=发送  RX=接收  ERR=通信错误"
        ).pack(side="left", padx=3)

        ttk.Button(
            serial_toolbar,
            text="清空",
            command=self._clear_serial_log
        ).pack(side="right", padx=2, pady=2)

        serial_text_frame = ttk.Frame(serial_tab)
        serial_text_frame.pack(fill="both", expand=True)

        self.serial_log = tk.Text(
            serial_text_frame,
            wrap="none",
            font=("Consolas", 9)
        )

        serial_y = ttk.Scrollbar(
            serial_text_frame,
            orient="vertical",
            command=self.serial_log.yview
        )

        serial_x = ttk.Scrollbar(
            serial_text_frame,
            orient="horizontal",
            command=self.serial_log.xview
        )

        self.serial_log.configure(
            yscrollcommand=serial_y.set,
            xscrollcommand=serial_x.set
        )

        self.serial_log.grid(
            row=0,
            column=0,
            sticky="nsew"
        )
        serial_y.grid(row=0, column=1, sticky="ns")
        serial_x.grid(row=1, column=0, sticky="ew")

        serial_text_frame.rowconfigure(0, weight=1)
        serial_text_frame.columnconfigure(0, weight=1)

        b = ttk.LabelFrame(
            self,
            text="当前测试点",
            padding=8
        )
        b.pack(fill="x", padx=10, pady=(0, 10))

        self.cycle_var = tk.StringVar(value="0")
        self.point = tk.StringVar(value="-")
        self.target = tk.StringVar(value="-")
        self.cfeedback = tk.StringVar(value="-")
        self.filevar = tk.StringVar(value="-")

        ttk.Label(b, text="循环次数:").grid(row=0, column=0)
        ttk.Label(
            b,
            textvariable=self.cycle_var,
            width=8
        ).grid(row=0, column=1)

        ttk.Label(b, text="百分比:").grid(row=0, column=2)
        ttk.Label(
            b,
            textvariable=self.point,
            width=8
        ).grid(row=0, column=3)

        ttk.Label(b, text="目标流量:").grid(row=0, column=4)
        ttk.Label(
            b,
            textvariable=self.target,
            width=14
        ).grid(row=0, column=5)

        ttk.Label(b, text="控制器反馈:").grid(row=0, column=6)
        ttk.Label(
            b,
            textvariable=self.cfeedback,
            width=14
        ).grid(row=0, column=7)

        ttk.Label(b, text="CSV:").grid(row=0, column=8)
        ttk.Label(
            b,
            textvariable=self.filevar
        ).grid(row=0, column=9, sticky="w")

        b.columnconfigure(9, weight=1)

    def refresh_ports(self):
        ports = [
            x.device
            for x in list_ports.comports()
        ]

        self.port_cb["values"] = ports

        if ports and self.port.get() not in ports:
            self.port.set(ports[0])

    def toggle_connect(self):
        if self.mb.opened:
            if self.worker and self.worker.is_alive():
                messagebox.showwarning(
                    "提示",
                    "请先停止测试"
                )
                return

            self.mb.close()
            self.connect_btn.config(text="连接")
            self.status.set("未连接 / 空闲")
            self._log("串口已断开")
            return

        if not self.port.get():
            messagebox.showerror(
                "连接失败",
                "请选择串口"
            )
            return

        try:
            self.mb.open(
                self.port.get(),
                int(self.baud.get()),
                float(self.timeout.get())
            )

            self.connect_btn.config(text="断开")
            self.status.set(
                f"已连接 {self.port.get()} @ {self.baud.get()}"
            )
            self._log(
                f"串口连接成功：{self.port.get()} @ {self.baud.get()}"
            )

        except Exception as e:
            messagebox.showerror(
                "连接失败",
                str(e)
            )

    def start(self):
        if self.worker and self.worker.is_alive():
            return

        if not self.mb.opened:
            messagebox.showerror(
                "错误",
                "请先连接串口"
            )
            return

        try:
            r = float(self.flow_range.get())
            st = float(self.settle.get())
            ct = float(self.capture.get())
            iv = float(self.interval.get())
            meter_count = int(self.meter_count_var.get())
            device_gap_ms = float(self.device_gap_ms_var.get())
            retry_count = int(self.retry_count_var.get())

            if r <= 0:
                raise ValueError("量程必须大于0")
            if st < 0:
                raise ValueError("稳定等待不能小于0")
            if ct <= 0:
                raise ValueError("采集时间必须大于0")
            if iv <= 0:
                raise ValueError("整轮采样周期必须大于0")
            if meter_count < 1 or meter_count > 25:
                raise ValueError("测试流量计数量必须为1~25")
            if device_gap_ms < 0:
                raise ValueError("设备间通讯间隔不能小于0")
            if retry_count < 0 or retry_count > 10:
                raise ValueError("通讯失败重试次数建议为0~10")

            self.active_meter_ids = list(range(2, 2 + meter_count))
            self.mb.retry_count = retry_count

        except Exception as e:
            messagebox.showerror(
                "参数错误",
                str(e)
            )
            return

        fn = filedialog.asksaveasfilename(
            defaultextension=".csv",
            initialfile=(
                "flow_test_"
                + datetime.now().strftime("%Y%m%d_%H%M%S")
                + ".csv"
            ),
            filetypes=[("CSV", "*.csv")]
        )

        if not fn:
            return

        self.filevar.set(fn)
        self.stop_evt.clear()

        self.start_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.progress["value"] = 0
        self.cycle_var.set("0")

        active_set = set(self.active_meter_ids)
        for mid in METER_IDS:
            self.tree.item(
                f"m{mid}",
                values=(
                    mid,
                    "流量计",
                    "-",
                    "-",
                    "待测试" if mid in active_set else "未参与"
                )
            )

        self.online.set(
            f"流量计在线：-/{len(self.active_meter_ids)}"
        )

        self._log(
            f"本次测试：ID{self.active_meter_ids[0]}~"
            f"ID{self.active_meter_ids[-1]}，"
            f"共{len(self.active_meter_ids)}台；"
            f"设备间通讯间隔={device_gap_ms:.1f}ms；"
            f"失败重试次数={retry_count}。"
        )

        self.worker = threading.Thread(
            target=self._run,
            args=(
                r,
                st,
                ct,
                iv,
                device_gap_ms / 1000.0,
                list(self.active_meter_ids),
                fn
            ),
            daemon=True
        )
        self.worker.start()

    def stop(self):
        self.stop_evt.set()
        self.status.set("正在停止...")

    def _write_controller_target_safe(self, target):
        last_error = ""

        for attempt in range(1, CONTROLLER_WRITE_RETRIES + 1):
            if self.stop_evt.is_set():
                return False

            try:
                self.mb.write_float(
                    CONTROLLER_ID,
                    REG_CONTROLLER_TARGET,
                    target
                )

                if attempt > 1:
                    self.q.put((
                        "log",
                        f"控制器目标写入第{attempt}次重试成功"
                    ))

                return True

            except Exception as exc:
                last_error = str(exc)

                self.q.put((
                    "log",
                    f"ID1目标写入失败 "
                    f"({attempt}/{CONTROLLER_WRITE_RETRIES})：{exc}"
                ))

                if attempt < CONTROLLER_WRITE_RETRIES:
                    self.stop_evt.wait(0.10)

        self.q.put((
            "log",
            "ID1目标流量写入最终失败，"
            "本测试点仍继续采集，不终止整体测试。"
            f" 错误：{last_error}"
        ))

        return False

    def _run(
        self,
        flow_range,
        settle,
        capture,
        interval,
        device_gap,
        active_meter_ids,
        filename
    ):
        headers = [
            "timestamp",
            "cycle",
            "point_percent",
            "target_flow_ml_min",
            "controller_target_write_ok",
            "controller_feedback_ml_min",
            "meter_online_count"
        ]

        for mid in active_meter_ids:
            headers.append(f"meter_{mid}_feedback_ml_min")
            headers.append(f"meter_{mid}_error_FS_percent")

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
            ) as f:
                writer = csv.writer(f)
                writer.writerow(headers)
                f.flush()

                cycle_count = 0

                while not self.stop_evt.is_set():
                    cycle_count += 1

                    self.q.put(("cycle", cycle_count))
                    self.q.put((
                        "log",
                        f"========== 第 {cycle_count} 循环开始 =========="
                    ))

                    for idx, pct in enumerate(TEST_POINTS):
                        if self.stop_evt.is_set():
                            break

                        target = flow_range * pct / 100.0

                        self.q.put(("point", pct, target))
                        self.q.put((
                            "log",
                            f"第{cycle_count}循环：设置测试点 "
                            f"{pct}% -> {target:.3f} ml/min"
                        ))

                        target_write_ok = (
                            self._write_controller_target_safe(target)
                        )

                        self.q.put((
                            "controller_write",
                            target_write_ok
                        ))

                        # 稳定等待
                        t0 = time.monotonic()

                        while (
                            time.monotonic() - t0 < settle
                            and not self.stop_evt.is_set()
                        ):
                            frac = min(
                                (time.monotonic() - t0)
                                / max(settle, 0.001),
                                1.0
                            )

                            # 无限循环模式下，进度条显示“当前这一循环”的进度
                            self.q.put((
                                "progress",
                                (
                                    idx + frac * 0.25
                                )
                                / len(TEST_POINTS)
                                * 100
                            ))

                            time.sleep(0.10)

                        if self.stop_evt.is_set():
                            break

                        self.q.put((
                            "log",
                            f"第{cycle_count}循环 {pct}% 开始采集"
                        ))

                        cap0 = time.monotonic()
                        sample_no = 0

                        while (
                            time.monotonic() - cap0 < capture
                            and not self.stop_evt.is_set()
                        ):
                            loop0 = time.monotonic()
                            sample_no += 1

                            # 读取流量控制器标准反馈
                            try:
                                controller_feedback = (
                                    self.mb.read_float(
                                        CONTROLLER_ID,
                                        REG_CONTROLLER_FEEDBACK
                                    )
                                )

                                if not math.isfinite(controller_feedback):
                                    raise ValueError(
                                        f"返回无效float：{controller_feedback}"
                                    )

                                controller_feedback_ok = True

                            except Exception as exc:
                                controller_feedback = math.nan
                                controller_feedback_ok = False

                                self.q.put((
                                    "log",
                                    f"ID1控制器反馈读取失败：{exc}；"
                                    "继续读取25台流量计。"
                                ))

                            values = {}
                            errors_fs = {}
                            online_count = 0
                            offline_ids = []

                            # 25台流量计逐台读取，任何一台失败都只影响该台
                            for meter_index, mid in enumerate(active_meter_ids):
                                if self.stop_evt.is_set():
                                    break

                                if meter_index > 0 and device_gap > 0:
                                    if self.stop_evt.wait(device_gap):
                                        break

                                try:
                                    value = self.mb.read_float(
                                        mid,
                                        REG_METER_FEEDBACK
                                    )

                                    if not math.isfinite(value):
                                        raise ValueError(
                                            f"返回无效float：{value}"
                                        )

                                    values[mid] = value
                                    online_count += 1

                                    # F.S.误差：
                                    # (流量计反馈 - 控制器标准反馈) / 满量程 * 100%
                                    if (
                                        controller_feedback_ok
                                        and flow_range > 0.0
                                    ):
                                        errors_fs[mid] = (
                                            (
                                                value
                                                - controller_feedback
                                            )
                                            / flow_range
                                            * 100.0
                                        )
                                    else:
                                        errors_fs[mid] = math.nan

                                except Exception:
                                    values[mid] = math.nan
                                    errors_fs[mid] = math.nan
                                    offline_ids.append(mid)

                            if offline_ids:
                                self.q.put((
                                    "log",
                                    "本次采样异常流量计ID："
                                    + ",".join(
                                        str(x)
                                        for x in offline_ids
                                    )
                                    + "；其余设备继续。"
                                ))

                            timestamp = (
                                datetime.now()
                                .strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                            )

                            row = [
                                timestamp,
                                cycle_count,
                                pct,
                                f"{target:.6f}",
                                1 if target_write_ok else 0,
                                (
                                    ""
                                    if math.isnan(controller_feedback)
                                    else f"{controller_feedback:.6f}"
                                ),
                                online_count
                            ]

                            # 每台流量计：反馈值 + %F.S.误差成对保存
                            for mid in active_meter_ids:
                                meter_value = values[mid]
                                meter_error = errors_fs[mid]

                                row.append(
                                    ""
                                    if math.isnan(meter_value)
                                    else f"{meter_value:.6f}"
                                )
                                row.append(
                                    ""
                                    if math.isnan(meter_error)
                                    else f"{meter_error:.6f}"
                                )

                            writer.writerow(row)
                            f.flush()

                            self.q.put((
                                "sample",
                                controller_feedback,
                                controller_feedback_ok,
                                target_write_ok,
                                values,
                                errors_fs,
                                online_count,
                                sample_no
                            ))

                            frac = min(
                                (time.monotonic() - cap0)
                                / capture,
                                1.0
                            )

                            self.q.put((
                                "progress",
                                (
                                    idx
                                    + 0.25
                                    + frac * 0.75
                                )
                                / len(TEST_POINTS)
                                * 100
                            ))

                            remain = (
                                interval
                                - (
                                    time.monotonic()
                                    - loop0
                                )
                            )

                            if remain > 0:
                                self.stop_evt.wait(remain)

                        self.q.put((
                            "log",
                            f"第{cycle_count}循环 {pct}% 采集完成"
                        ))

                    if self.stop_evt.is_set():
                        break

                    self.q.put((
                        "log",
                        f"========== 第 {cycle_count} 循环完成 =========="
                    ))
                    self.q.put(("progress", 0))

            if self.zero_end.get() and self.mb.opened:
                zero_ok = (
                    self._write_controller_target_safe(0.0)
                )

                if zero_ok:
                    self.q.put((
                        "log",
                        "控制器目标流量已置0"
                    ))
                else:
                    self.q.put((
                        "log",
                        "控制器目标置0失败"
                    ))

            self.q.put((
                "finished",
                not self.stop_evt.is_set(),
                filename
            ))

        except Exception as exc:
            self.q.put((
                "fatal",
                str(exc)
            ))

    def _modbus_trace_callback(
        self,
        direction,
        frame,
        note
    ):
        self.q.put((
            "serial",
            direction,
            frame,
            note
        ))

    def _poll_ui(self):
        try:
            while True:
                msg = self.q.get_nowait()
                kind = msg[0]

                if kind == "log":
                    self._log(msg[1])

                elif kind == "serial":
                    self._append_serial_log(
                        msg[1],
                        msg[2],
                        msg[3]
                    )

                elif kind == "progress":
                    self.progress["value"] = msg[1]

                elif kind == "cycle":
                    self.cycle_var.set(str(msg[1]))
                    self.status.set(
                        f"第{msg[1]}循环运行中"
                    )

                elif kind == "point":
                    self.point.set(f"{msg[1]}%")
                    self.target.set(f"{msg[2]:.3f}")
                    self.status.set(
                        f"第{self.cycle_var.get()}循环 测试 {msg[1]}%"
                    )

                elif kind == "controller_write":
                    ok = msg[1]

                    old = self.tree.item(
                        "c",
                        "values"
                    )

                    old_flow = (
                        old[2]
                        if len(old) > 2
                        else "-"
                    )

                    self.tree.item(
                        "c",
                        values=(
                            1,
                            "流量控制器",
                            old_flow,
                            "-",
                            (
                                "目标已写入"
                                if ok
                                else "目标写失败"
                            )
                        )
                    )

                elif kind == "sample":
                    (
                        controller_feedback,
                        controller_feedback_ok,
                        target_write_ok,
                        values,
                        errors_fs,
                        online_count,
                        sample_no
                    ) = msg[1:]

                    controller_text = (
                        "-"
                        if math.isnan(controller_feedback)
                        else f"{controller_feedback:.3f}"
                    )

                    self.cfeedback.set(controller_text)

                    if controller_feedback_ok and target_write_ok:
                        controller_state = "在线"
                    elif controller_feedback_ok and not target_write_ok:
                        controller_state = "目标写失败"
                    elif not controller_feedback_ok and target_write_ok:
                        controller_state = "反馈异常"
                    else:
                        controller_state = "写入/读取失败"

                    self.tree.item(
                        "c",
                        values=(
                            1,
                            "流量控制器",
                            controller_text,
                            "-",
                            controller_state
                        )
                    )

                    active_set = set(self.active_meter_ids)

                    for mid in METER_IDS:
                        if mid not in active_set:
                            self.tree.item(
                                f"m{mid}",
                                values=(mid, "流量计", "-", "-", "未参与")
                            )
                            continue

                        value = values.get(mid, math.nan)
                        error_fs = errors_fs.get(mid, math.nan)

                        self.tree.item(
                            f"m{mid}",
                            values=(
                                mid,
                                "流量计",
                                (
                                    "-"
                                    if math.isnan(value)
                                    else f"{value:.3f}"
                                ),
                                (
                                    "-"
                                    if math.isnan(error_fs)
                                    else f"{error_fs:+.3f}%"
                                ),
                                (
                                    "异常"
                                    if math.isnan(value)
                                    else "在线"
                                )
                            )
                        )

                    self.online.set(
                        f"流量计在线：{online_count}/{len(self.active_meter_ids)}"
                    )

                    self.status.set(
                        f"第{self.cycle_var.get()}循环 "
                        f"{self.point.get()} 采样#{sample_no}"
                    )

                elif kind == "finished":
                    success = msg[1]
                    filename = msg[2]

                    self.start_btn.config(state="normal")
                    self.stop_btn.config(state="disabled")

                    self.status.set(
                        "测试完成"
                        if success
                        else "已停止"
                    )

                    self._log(
                        (
                            "测试完成"
                            if success
                            else "测试停止"
                        )
                        + f"，数据：{filename}"
                    )

                elif kind == "fatal":
                    self.start_btn.config(state="normal")
                    self.stop_btn.config(state="disabled")

                    self.status.set("程序异常")
                    self._log("程序级异常：" + msg[1])

                    messagebox.showerror(
                        "程序异常",
                        msg[1]
                    )

        except queue.Empty:
            pass

        self.after(100, self._poll_ui)

    def _log(self, text):
        self.log.insert(
            "end",
            f"[{datetime.now().strftime('%H:%M:%S')}] {text}\n"
        )
        self.log.see("end")

        try:
            line_count = int(
                self.log.index("end-1c").split(".")[0]
            )
            if line_count > 2500:
                self.log.delete("1.0", "501.0")
        except Exception:
            pass

    def _append_serial_log(
        self,
        direction,
        frame,
        note
    ):
        timestamp = (
            datetime.now()
            .strftime("%H:%M:%S.%f")[:-3]
        )

        if frame:
            hex_text = " ".join(
                f"{b:02X}"
                for b in frame
            )
        else:
            hex_text = "-"

        self.serial_log.insert(
            "end",
            f"[{timestamp}] {direction:<3} {note}\n"
            f"    {hex_text}\n"
        )

        self.serial_log.see("end")

        try:
            line_count = int(
                self.serial_log.index("end-1c").split(".")[0]
            )
            if line_count > 5000:
                self.serial_log.delete("1.0", "1001.0")
        except Exception:
            pass

    def _clear_run_log(self):
        self.log.delete("1.0", "end")

    def _clear_serial_log(self):
        self.serial_log.delete("1.0", "end")

    def close_app(self):
        self.stop_evt.set()

        try:
            if self.zero_end.get() and self.mb.opened:
                try:
                    self.mb.write_float(
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
    App().mainloop()
