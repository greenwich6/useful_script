import serial
import serial.tools.list_ports
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import csv
from collections import deque
from datetime import datetime
import tkinter as tk
from tkinter import ttk
from threading import Thread

# 配置参数
MAX_DATA_POINTS = 500  # X 轴固定为 500 个点

# 初始化数据存储
data_queues = {}  # 用于存储每个数据的队列

# 串口对象
ser = None

# 实时更新绘图
def update_plot():
    if not data_queues:
        return

    # 更新每条曲线的数据
    for i, line in enumerate(lines):
        if i < len(data_queues):
            line.set_xdata(range(len(data_queues[f"data{i+1}"])))  # X 轴固定为 0-499
            line.set_ydata(data_queues[f"data{i+1}"])

    # 动态调整 Y 轴范围
    y_min = min(min(queue) for queue in data_queues.values())
    y_max = max(max(queue) for queue in data_queues.values())
    ax.set_ylim(y_min - 0.1 * abs(y_min), y_max + 0.1 * abs(y_max))  # 添加 10% 的边距

    # 重绘图
    canvas.draw()

# 读取串口数据
def read_serial():
    global ser
    while ser and ser.is_open:
        if ser.in_waiting > 0:
            # 读取串口数据
            data = ser.readline().decode('utf-8').strip()
            try:
                # 解析数据
                values = list(map(float, data.split(';')))  # 按分号分割并转换为浮点数
                if len(values) != len(data_queues):
                    print(f"数据长度不匹配！期望 {len(data_queues)} 个数据，实际收到 {len(values)} 个")
                    continue

                # 更新数据队列
                for i, value in enumerate(values):
                    data_queues[f"data{i+1}"].append(value)

                # 更新绘图
                update_plot()

                print(f"Data: {values}")

            except ValueError:
                print(f"Invalid data: {data}")

# 保存数据到 CSV 文件
def save_data():
    if not data_queues:
        print("没有数据可保存！")
        return

    # 生成文件名
    csv_filename = f"serial_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

    # 写入数据
    with open(csv_filename, mode='w', newline='') as file:
        writer = csv.writer(file)
        # 写入表头
        writer.writerow([f"data{i+1}" for i in range(len(data_queues))])
        # 写入数据
        for i in range(len(data_queues["data1"])):
            row = [data_queues[f"data{j+1}"][i] for j in range(len(data_queues))]
            writer.writerow(row)

    print(f"数据已保存到文件：{csv_filename}")

# 启动串口连接
def start_serial():
    global ser
    port = port_combobox.get()
    baudrate = baudrate_entry.get()

    try:
        baudrate = int(baudrate)  # 将波特率转换为整数
        ser = serial.Serial(port, baudrate, timeout=1)
        print(f"已连接串口：{port}，波特率：{baudrate}")
        start_button.config(state=tk.DISABLED)
        stop_button.config(state=tk.NORMAL)
        save_button.config(state=tk.NORMAL)

        # 初始化数据队列
        num_data_points = len(data_queues)
        for i in range(num_data_points):
            data_queues[f"data{i+1}"] = deque(maxlen=MAX_DATA_POINTS)  # 限制长度为 500

        # 启动线程读取串口数据
        thread = Thread(target=read_serial)
        thread.daemon = True
        thread.start()

    except ValueError:
        print("波特率必须是整数！")
    except Exception as e:
        print(f"无法打开串口：{e}")

# 停止串口连接
def stop_serial():
    global ser
    if ser and ser.is_open:
        ser.close()
        print("串口已关闭")
        start_button.config(state=tk.NORMAL)
        stop_button.config(state=tk.DISABLED)
        save_button.config(state=tk.DISABLED)

# 创建 GUI 界面
def create_gui():
    global port_combobox, baudrate_entry, start_button, stop_button, save_button, canvas, lines, ax

    root = tk.Tk()
    root.title("串口绘图上位机 - 实时调整 Y 轴")
    root.geometry("800x600")  # 设置窗口大小
    root.configure(bg="#f0f0f0")  # 设置背景色

    # 设置字体
    font_label = ("Arial", 12)
    font_button = ("Arial", 12, "bold")

    # 顶部框架（串口选择和按钮）
    top_frame = ttk.Frame(root, padding="10")
    top_frame.grid(row=0, column=0, sticky="ew")

    # 串口号选择
    port_label = ttk.Label(top_frame, text="选择串口号：", font=font_label)
    port_label.grid(row=0, column=0, padx=5, pady=5, sticky="w")

    ports = [port.device for port in serial.tools.list_ports.comports()]
    port_combobox = ttk.Combobox(top_frame, values=ports, font=font_label, width=15)
    port_combobox.grid(row=0, column=1, padx=5, pady=5)
    if ports:
        port_combobox.current(0)

    # 波特率输入
    baudrate_label = ttk.Label(top_frame, text="输入波特率：", font=font_label)
    baudrate_label.grid(row=0, column=2, padx=5, pady=5, sticky="w")

    baudrate_entry = ttk.Entry(top_frame, font=font_label, width=10)
    baudrate_entry.grid(row=0, column=3, padx=5, pady=5)
    baudrate_entry.insert(0, "9600")  # 默认波特率

    # 启动按钮
    start_button = ttk.Button(top_frame, text="启动", command=start_serial, style="TButton")
    start_button.grid(row=0, column=4, padx=5, pady=5)

    # 停止按钮
    stop_button = ttk.Button(top_frame, text="停止", command=stop_serial, style="TButton", state=tk.DISABLED)
    stop_button.grid(row=0, column=5, padx=5, pady=5)

    # 保存数据按钮
    save_button = ttk.Button(top_frame, text="保存数据", command=save_data, style="TButton", state=tk.DISABLED)
    save_button.grid(row=0, column=6, padx=5, pady=5)

    # 绘图区域
    fig, ax = plt.subplots()
    lines = [ax.plot([], [], label=f"data{i+1}")[0] for i in range(2)]  # 假设最多绘制 2 条曲线
    ax.set_xlim(0, MAX_DATA_POINTS - 1)  # 固定 X 轴范围为 0-499
    ax.set_autoscaley_on(False)  # 禁用自动 Y 轴缩放
    ax.grid()
    ax.legend()

    canvas = FigureCanvasTkAgg(fig, master=root)
    canvas.get_tk_widget().grid(row=1, column=0, padx=10, pady=10, sticky="nsew")

    # 配置布局权重
    root.grid_rowconfigure(1, weight=1)
    root.grid_columnconfigure(0, weight=1)

    root.mainloop()

# 主程序
if __name__ == "__main__":
    create_gui()