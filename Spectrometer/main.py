import ctypes
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.pyplot as plt
from matplotlib import font_manager
import threading
import queue
import subprocess
import time  # 新增导入 time 模块

# 设置中文字体
plt.rcParams['font.family'] = 'WenQuanYi Zen Hei'  # 使用 WenQuanYi Zen Hei 字体

# 卸载冲突的内核模块
def unload_kernel_modules():
    try:
        subprocess.run(["sudo", "rmmod", "ftdi_sio"], check=True)
        subprocess.run(["sudo", "rmmod", "usbserial"], check=True)
        print("内核模块卸载成功。")
    except subprocess.CalledProcessError as e:
        print(f"卸载内核模块失败: {e}")
        print("请手动执行以下命令：\n\nsudo rmmod ftdi_sio\nsudo rmmod usbserial")

# 加载共享库
libwrapper = ctypes.CDLL('/usr/local/lib/libwrapper.so', mode=ctypes.RTLD_GLOBAL)

# 定义函数原型
libwrapper.Init.argtypes = [ctypes.c_int]
libwrapper.Init.restype = ctypes.c_int

libwrapper.Open.argtypes = [ctypes.c_int]
libwrapper.Open.restype = ctypes.c_int

libwrapper.GetSerialNumber.argtypes = [ctypes.c_int, ctypes.POINTER(ctypes.c_char)]
libwrapper.GetSerialNumber.restype = ctypes.c_int

libwrapper.SetIntegrationTime.argtypes = [ctypes.c_int, ctypes.c_double]
libwrapper.SetIntegrationTime.restype = ctypes.c_int

libwrapper.SetAverageTime.argtypes = [ctypes.c_int, ctypes.c_int]
libwrapper.SetAverageTime.restype = ctypes.c_int

libwrapper.GetWavelengths.argtypes = [ctypes.c_int, ctypes.POINTER(ctypes.c_float)]
libwrapper.GetWavelengths.restype = ctypes.c_int

libwrapper.GetScopes.argtypes = [ctypes.c_int, ctypes.POINTER(ctypes.c_ushort)]
libwrapper.GetScopes.restype = ctypes.c_int

# 封装 C 库函数的 Python 类
class Wrapper:
    def __init__(self):
        pass

    def init(self, commType):
        return libwrapper.Init(commType)

    def open(self, index):
        return libwrapper.Open(index)

    def get_serial_number(self, index):
        serial_number = ctypes.create_string_buffer(8)
        ret = libwrapper.GetSerialNumber(index, serial_number)
        return ret, serial_number.value.decode()

    def set_integration_time(self, index, integration_time_ms):
        return libwrapper.SetIntegrationTime(index, integration_time_ms)

    def set_average_time(self, index, average_time):
        return libwrapper.SetAverageTime(index, average_time)

    def get_wavelengths(self, index):
        wls = (ctypes.c_float * 2048)()
        ret = libwrapper.GetWavelengths(index, wls)
        return ret, [wls[i] for i in range(2048)]

    def get_scopes(self, index):
        scopes = (ctypes.c_ushort * 2048)()
        ret = libwrapper.GetScopes(index, scopes)
        return ret, [scopes[i] for i in range(2048)]

# 创建 Wrapper 类的实例
wrapper = Wrapper()

# GUI 应用程序
class SpectrometerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("光谱仪控制程序")
        self.root.geometry("1000x850")  # 扩大窗口大小
        self.root.configure(bg="#f0f0f0")  # 设置背景颜色
        self.index = 0  # 默认设备索引
        self.update_interval = 100  # 默认更新间隔（毫秒）
        self.integration_time = 100  # 默认积分时间（毫秒）
        self.average_time = 5  # 默认平均次数
        self.last_wavelengths = None  # 上一次读取的波长数据
        self.last_scopes = None  # 上一次读取的光谱数据
        self.dark_spectrum = None  # 暗光谱数据
        self.plot_mode = "raw"  # 绘图模式，默认为原始数据

        # 创建 GUI 元素
        self.create_widgets()

        # 数据队列
        self.data_queue = queue.Queue()

        # 线程标志
        self.is_running = False

    def create_widgets(self):
        # 设置窗口大小
        self.root.geometry("1000x850")

        # 设备编号和序列号（右下角）
        self.info_frame = ttk.Frame(self.root)
        self.info_frame.place(relx=1.0, rely=1.0, anchor="se", x=-20, y=-20)  # 放置在右下角

        self.device_number_label = tk.Label(self.info_frame, text="设备编号: 无", font=("WenQuanYi Zen Hei", 12),
                                            bg="#f0f0f0", fg="#555555")
        self.device_number_label.pack(side="left", padx=10)

        self.serial_number_label = tk.Label(self.info_frame, text="序列号: 无", font=("WenQuanYi Zen Hei", 12),
                                            bg="#f0f0f0", fg="#555555")
        self.serial_number_label.pack(side="left", padx=10)

        # 积分时间输入框
        self.integration_time_label = tk.Label(self.root, text="积分时间 (ms):", font=("WenQuanYi Zen Hei", 12),
                                               bg="#f0f0f0", fg="#555555")
        self.integration_time_label.grid(row=1, column=0, padx=10, pady=5, sticky="e")
        self.integration_time_entry = ttk.Entry(self.root, width=10)
        self.integration_time_entry.insert(0, "100")
        self.integration_time_entry.grid(row=1, column=1, padx=10, pady=5, sticky="w")
        self.integration_time_entry.bind("<FocusOut>", self.update_integration_time)  # 绑定焦点离开事件

        # 平均次数输入框
        self.average_time_label = tk.Label(self.root, text="平均次数:", font=("WenQuanYi Zen Hei", 12), bg="#f0f0f0",
                                           fg="#555555")
        self.average_time_label.grid(row=1, column=2, padx=10, pady=5, sticky="e")
        self.average_time_entry = ttk.Entry(self.root, width=10)
        self.average_time_entry.insert(0, "5")
        self.average_time_entry.grid(row=1, column=3, padx=10, pady=5, sticky="w")
        self.average_time_entry.bind("<FocusOut>", self.update_average_time)  # 绑定焦点离开事件

        # 更新间隔输入框
        self.update_interval_label = tk.Label(self.root, text="更新间隔 (ms):", font=("WenQuanYi Zen Hei", 12),
                                              bg="#f0f0f0", fg="#555555")
        self.update_interval_label.grid(row=2, column=0, padx=10, pady=5, sticky="e")
        self.update_interval_entry = ttk.Entry(self.root, width=10)
        self.update_interval_entry.insert(0, "100")
        self.update_interval_entry.grid(row=2, column=1, padx=10, pady=5, sticky="w")
        self.update_interval_entry.bind("<FocusOut>", self.update_update_interval)  # 绑定焦点离开事件

        # 绘图模式选择
        self.plot_mode_label = tk.Label(self.root, text="绘图模式:", font=("WenQuanYi Zen Hei", 12), bg="#f0f0f0",
                                        fg="#555555")
        self.plot_mode_label.grid(row=2, column=2, padx=10, pady=5, sticky="e")
        self.plot_mode_var = tk.StringVar(value="raw")
        self.plot_mode_raw = ttk.Radiobutton(self.root, text="原始数据", variable=self.plot_mode_var, value="raw",
                                             command=self.update_plot_mode)
        self.plot_mode_raw.grid(row=2, column=3, padx=10, pady=5, sticky="w")
        self.plot_mode_dark = ttk.Radiobutton(self.root, text="减去暗光谱", variable=self.plot_mode_var, value="dark",
                                              command=self.update_plot_mode)
        self.plot_mode_dark.grid(row=2, column=4, padx=10, pady=5, sticky="w")

        # Matplotlib 图形
        self.fig, self.ax = plt.subplots(figsize=(10, 6))  # 扩大绘图区域
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.root)
        self.canvas.get_tk_widget().grid(row=3, column=0, columnspan=5, padx=20, pady=20)

        # 按钮
        self.init_button = ttk.Button(self.root, text="初始化设备", command=self.initialize_device)
        self.init_button.grid(row=4, column=0, padx=10, pady=10)

        self.open_button = ttk.Button(self.root, text="打开设备", command=self.open_device)
        self.open_button.grid(row=4, column=1, padx=10, pady=10)

        self.start_button = ttk.Button(self.root, text="开始读取数据", command=self.start_data_acquisition)
        self.start_button.grid(row=4, column=2, padx=10, pady=10)

        self.single_shot_button = ttk.Button(self.root, text="单次采集", command=self.read_data_once)  # 新增单次采集按钮
        self.single_shot_button.grid(row=4, column=3, padx=10, pady=10)

        self.clear_button = ttk.Button(self.root, text="清除数据", command=self.clear_data)
        self.clear_button.grid(row=4, column=4, padx=10, pady=10)

        self.save_button = ttk.Button(self.root, text="保存数据", command=self.save_data)
        self.save_button.grid(row=5, column=0, padx=10, pady=10)

        self.save_dark_button = ttk.Button(self.root, text="保存暗光谱", command=self.save_dark_spectrum)
        self.save_dark_button.grid(row=5, column=1, padx=10, pady=10)

    def update_integration_time(self, event=None):
        try:
            self.integration_time = float(self.integration_time_entry.get())
            # 调用共享库函数，设置积分时间
            ret = wrapper.set_integration_time(self.index, self.integration_time)
            if ret < 0:
                messagebox.showerror("错误", "设置积分时间失败。")
            else:
                messagebox.showinfo("成功", f"积分时间已成功设置为: {self.integration_time} ms")
                print(f"积分时间已更新为: {self.integration_time} ms")
        except ValueError:
            messagebox.showerror("错误", "请输入有效的积分时间。")

    def update_average_time(self, event=None):
        try:
            self.average_time = int(self.average_time_entry.get())
            # 调用共享库函数，设置平均次数
            ret = wrapper.set_average_time(self.index, self.average_time)
            if ret < 0:
                messagebox.showerror("错误", "设置平均次数失败。")
            else:
                messagebox.showinfo("成功", f"平均次数已成功设置为: {self.average_time}")
                print(f"平均次数已更新为: {self.average_time}")
        except ValueError:
            messagebox.showerror("错误", "请输入有效的平均次数。")

    def update_update_interval(self, event=None):
        try:
            self.update_interval = int(self.update_interval_entry.get())
            if self.update_interval < 0:
                messagebox.showerror("错误", "更新间隔不能为负数。")
            else:
                messagebox.showinfo("成功", f"更新间隔已成功设置为: {self.update_interval} ms")
                print(f"更新间隔已更新为: {self.update_interval} ms")
        except ValueError:
            messagebox.showerror("错误", "请输入有效的更新间隔。")

    def initialize_device(self):
        ret = wrapper.init(self.index)
        if ret < 0:
            messagebox.showerror("错误", "初始化设备失败。")
        else:
            self.device_number_label.config(text=f"设备编号: {ret}")
            messagebox.showinfo("成功", f"设备初始化成功。设备编号: {ret}")

    def open_device(self):
        ret = wrapper.open(self.index)
        if ret < 0:
            messagebox.showerror("错误", "打开设备失败。")
        else:
            messagebox.showinfo("成功", "设备打开成功。")
            # 获取并显示序列号
            self.update_serial_number()

    def update_serial_number(self):
        ret, serial_number = wrapper.get_serial_number(self.index)
        if ret < 0:
            messagebox.showerror("错误", "获取序列号失败。")
        else:
            self.serial_number_label.config(text=f"序列号: {serial_number}")

    def start_data_acquisition(self):
        if not self.is_running:
            # 检查更新间隔是否小于积分时间
            if self.update_interval < self.integration_time:
                messagebox.showerror("错误", "更新间隔不能小于积分时间。")
                return

            # 设置积分时间和平均次数
            ret = wrapper.set_integration_time(self.index, self.integration_time)
            if ret < 0:
                messagebox.showerror("错误", "设置积分时间失败。")
                return

            ret = wrapper.set_average_time(self.index, self.average_time)
            if ret < 0:
                messagebox.showerror("错误", "设置平均次数失败。")
                return

            self.is_running = True
            self.start_button.config(text="停止读取数据")
            threading.Thread(target=self.read_data, daemon=True).start()
        else:
            self.is_running = False
            self.start_button.config(text="开始读取数据")

    def read_data(self):
        while self.is_running:
            # 获取波长和光谱数据
            ret, wavelengths = wrapper.get_wavelengths(self.index)
            if ret < 0:
                print("获取波长数据失败。")
                break

            ret, scopes = wrapper.get_scopes(self.index)
            if ret < 0:
                print("获取光谱数据失败。")
                break

            # 保存上一次读取的数据
            self.last_wavelengths = wavelengths
            self.last_scopes = scopes

            # 将数据放入队列
            self.data_queue.put((wavelengths, scopes))

            # 更新界面
            self.root.after(0, self.update_plot)  # 立即更新界面

            # 等待指定的间隔时间（转换为秒）
            time.sleep(self.update_interval / 1000.0)

    def read_data_once(self):
        """单次采集数据"""
        # 获取波长和光谱数据
        ret, wavelengths = wrapper.get_wavelengths(self.index)
        if ret < 0:
            messagebox.showerror("错误", "获取波长数据失败。")
            return

        ret, scopes = wrapper.get_scopes(self.index)
        if ret < 0:
            messagebox.showerror("错误", "获取光谱数据失败。")
            return

        # 保存上一次读取的数据
        self.last_wavelengths = wavelengths
        self.last_scopes = scopes

        # 将数据放入队列
        self.data_queue.put((wavelengths, scopes))

        # 更新界面
        self.update_plot()

    def update_plot(self):
        if not self.data_queue.empty():
            wavelengths, scopes = self.data_queue.get()
            self.ax.clear()

            if self.plot_mode == "raw":
                # 只显示原始数据
                self.ax.plot(wavelengths, scopes, label="原始数据", color="#1f77b4")
            elif self.plot_mode == "dark" and self.dark_spectrum is not None:
                # 显示原始数据、暗光谱和减去暗光谱后的数据
                self.ax.plot(wavelengths, scopes, label="原始数据", color="#1f77b4")
                self.ax.plot(wavelengths, self.dark_spectrum, label="暗光谱", color="#ff7f0e", linestyle="--")
                corrected_scopes = [s - d for s, d in zip(scopes, self.dark_spectrum)]
                self.ax.plot(wavelengths, corrected_scopes, label="减去暗光谱", color="#2ca02c")

            self.ax.set_xlabel("波长 (nm)", fontsize=12)
            self.ax.set_ylabel("强度", fontsize=12)
            self.ax.set_title("光谱数据", fontsize=14)
            self.ax.legend()
            self.canvas.draw()

    def clear_data(self):
        self.ax.clear()
        self.canvas.draw()
        print("数据已清除。")

    def save_data(self):
        if self.last_wavelengths is not None and self.last_scopes is not None:
            file_path = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("Text Files", "*.txt")])
            if file_path:
                with open(file_path, "w") as f:
                    for wl, intensity in zip(self.last_wavelengths, self.last_scopes):
                        f.write(f"{wl:.2f}\t{intensity}\n")
                print(f"数据已保存到: {file_path}")
        else:
            print("没有数据可保存。")

    def save_dark_spectrum(self):
        if self.last_scopes is not None:
            self.dark_spectrum = self.last_scopes
            print("暗光谱已保存。")
        else:
            print("没有数据可保存为暗光谱。")

    def update_plot_mode(self):
        self.plot_mode = self.plot_mode_var.get()
        print(f"绘图模式已切换为: {self.plot_mode}")
        self.update_plot()  # 切换绘图模式后立即更新绘图

# 运行程序
if __name__ == "__main__":
    # 卸载内核模块
    unload_kernel_modules()

    # 启动 GUI 应用程序
    root = tk.Tk()
    app = SpectrometerApp(root)
    root.mainloop()