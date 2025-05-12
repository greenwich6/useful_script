import ctypes
from ctypes import c_int, c_char_p, c_double, c_ushort, POINTER, c_uint, c_ubyte
import tkinter as tk
from tkinter import messagebox, ttk
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from datetime import datetime

# 加载 DLL 文件（请替换为实际路径）
lib = ctypes.CDLL('NIR_M/easynirlib.dll')

# 定义函数签名（保持不变）
lib.enumerateDevices.argtypes = [POINTER(c_int)]
lib.enumerateDevices.restype = c_int
lib.openSpectrometer.argtypes = [c_int]
lib.openSpectrometer.restype = c_int
lib.closeSpectrometer.argtypes = []
lib.closeSpectrometer.restype = None
lib.getScanSectionNumber.argtypes = []
lib.getScanSectionNumber.restype = c_int
lib.getScanSectionName.argtypes = [c_int, c_char_p, c_uint]
lib.getScanSectionName.restype = c_int
lib.getScanSectionNameCfg.argtypes = [c_char_p, c_int, c_char_p, c_uint, POINTER(c_double),
                                     POINTER(c_ushort), POINTER(c_ushort), POINTER(c_ushort), POINTER(c_double)]
lib.getScanSectionNameCfg.restype = c_int
lib.setTgtCfg.argtypes = [c_char_p, c_int, c_char_p, c_ushort, c_ushort, c_double, c_ushort, c_double]
lib.setTgtCfg.restype = c_int
lib.getFormattedSpectrumLengths.argtypes = [POINTER(c_int)]
lib.getFormattedSpectrumLengths.restype = c_int
lib.getFormattedSpectrum.argtypes = [POINTER(c_double), POINTER(c_int), POINTER(c_int)]
lib.getFormattedSpectrum.restype = c_int
lib.setSpectrumAverageTime.argtypes = [c_ushort]
lib.setSpectrumAverageTime.restype = c_int
lib.setPGAGain.argtypes = [c_int, c_ubyte]
lib.setPGAGain.restype = c_int
lib.setActiveScanIndex.argtypes = [c_ubyte]
lib.setActiveScanIndex.restype = c_int
lib.getLastException.argtypes = []
lib.getLastException.restype = c_char_p

class SpectrometerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("光谱仪控制界面")
        self.device_open = False
        self.wavelengths = []
        self.intensities = []
        self.scan_configs = []

        # 主框架
        self.main_frame = ttk.Frame(root, padding="5")
        self.main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # 设备控制和状态区域
        self.top_frame = ttk.Frame(self.main_frame)
        self.top_frame.grid(row=0, column=0, columnspan=2, pady=5, sticky=(tk.W, tk.E))

        ttk.Button(self.top_frame, text="扫描设备", command=self.scan_devices, width=10).grid(row=0, column=0, padx=2)
        self.device_label = ttk.Label(self.top_frame, text="设备: 未扫描")
        self.device_label.grid(row=0, column=1, padx=5)
        ttk.Button(self.top_frame, text="打开设备", command=self.open_device, width=10).grid(row=0, column=2, padx=2)
        self.status_label = ttk.Label(self.top_frame, text="状态: 未打开")
        self.status_label.grid(row=0, column=3, padx=5)

        # 设置和操作按钮区域
        self.control_frame = ttk.Frame(self.main_frame)
        self.control_frame.grid(row=1, column=0, columnspan=2, pady=5, sticky=(tk.W, tk.E))

        ttk.Label(self.control_frame, text="平均次数:").grid(row=0, column=0, padx=2)
        self.avg_entry = ttk.Entry(self.control_frame, width=5)
        self.avg_entry.insert(0, "1")
        self.avg_entry.grid(row=0, column=1, padx=2)
        ttk.Button(self.control_frame, text="设置", command=self.set_average_time, width=5).grid(row=0, column=2, padx=2)

        ttk.Label(self.control_frame, text="增益:").grid(row=0, column=3, padx=2)
        self.gain_combo = ttk.Combobox(self.control_frame, values=["0 (不固定)", "1", "2", "4", "8", "16", "32", "64"], state="readonly", width=10)
        self.gain_combo.current(0)
        self.gain_combo.grid(row=0, column=4, padx=2)
        ttk.Button(self.control_frame, text="设置", command=self.set_gain, width=5).grid(row=0, column=5, padx=2)

        ttk.Button(self.control_frame, text="获取配置", command=self.get_config, width=10).grid(row=0, column=6, padx=2)
        ttk.Button(self.control_frame, text="写入配置", command=self.set_config, width=10).grid(row=0, column=7, padx=2)
        ttk.Button(self.control_frame, text="获取光谱", command=self.get_spectrum, width=10).grid(row=0, column=8, padx=2)
        ttk.Button(self.control_frame, text="绘制光谱", command=self.plot_spectrum, width=10).grid(row=0, column=9, padx=2)

        # 配置参数和日志区域（并列）
        self.left_frame = ttk.LabelFrame(self.main_frame, text="扫描配置参数", padding="5")
        self.left_frame.grid(row=2, column=0, pady=5, sticky=(tk.W, tk.N))

        ttk.Label(self.left_frame, text="选择配置:").grid(row=0, column=0, pady=2, sticky=tk.E)
        self.config_combo = ttk.Combobox(self.left_frame, state="readonly", width=15)
        self.config_combo.bind("<<ComboboxSelected>>", self.on_config_select)
        self.config_combo.grid(row=0, column=1, pady=2)

        ttk.Label(self.left_frame, text="扫描类型:").grid(row=1, column=0, pady=2, sticky=tk.E)
        self.scan_type_entry = ttk.Entry(self.left_frame, width=15)
        self.scan_type_entry.grid(row=1, column=1, pady=2)

        ttk.Label(self.left_frame, text="起始波长:").grid(row=2, column=0, pady=2, sticky=tk.E)
        self.wl_start_entry = ttk.Entry(self.left_frame, width=15)
        self.wl_start_entry.grid(row=2, column=1, pady=2)

        ttk.Label(self.left_frame, text="结束波长:").grid(row=3, column=0, pady=2, sticky=tk.E)
        self.wl_end_entry = ttk.Entry(self.left_frame, width=15)
        self.wl_end_entry.grid(row=3, column=1, pady=2)

        ttk.Label(self.left_frame, text="像素宽度:").grid(row=4, column=0, pady=2, sticky=tk.E)
        self.width_entry = ttk.Entry(self.left_frame, width=15)
        self.width_entry.grid(row=4, column=1, pady=2)

        ttk.Label(self.left_frame, text="模式数:").grid(row=5, column=0, pady=2, sticky=tk.E)
        self.patterns_entry = ttk.Entry(self.left_frame, width=15)
        self.patterns_entry.grid(row=5, column=1, pady=2)

        ttk.Label(self.left_frame, text="曝光时间:").grid(row=6, column=0, pady=2, sticky=tk.E)
        self.exp_time_entry = ttk.Entry(self.left_frame, width=15)
        self.exp_time_entry.grid(row=6, column=1, pady=2)

        self.right_frame = ttk.LabelFrame(self.main_frame, text="操作日志", padding="5")
        self.right_frame.grid(row=2, column=1, pady=5, sticky=(tk.E, tk.N))
        self.log_text = tk.Text(self.right_frame, height=8, width=40)
        self.log_text.grid(row=0, column=0, padx=5, pady=5)
        scrollbar = ttk.Scrollbar(self.right_frame, orient="vertical", command=self.log_text.yview)
        scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        self.log_text.config(yscrollcommand=scrollbar.set)

        # Matplotlib 绘图区域
        self.fig, self.ax = plt.subplots(figsize=(8, 3))
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.main_frame)
        self.canvas.get_tk_widget().grid(row=3, column=0, columnspan=2, pady=5)

        # 窗口关闭时清理
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def log(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_text.see(tk.END)

    def scan_devices(self):
        num_devices = c_int()
        result = lib.enumerateDevices(ctypes.byref(num_devices))
        if result < 0:
            self.log(f"扫描设备失败: {lib.getLastException().decode('utf-8')}")
            messagebox.showerror("错误", f"扫描设备失败")
            return
        self.device_label.config(text=f"设备: {num_devices.value}")
        self.log(f"找到 {num_devices.value} 个设备")
        if num_devices.value == 0:
            messagebox.showwarning("警告", "未找到设备")

    def open_device(self):
        if not self.device_open:
            result = lib.openSpectrometer(0)
            if result < 0:
                self.log(f"打开设备失败: {lib.getLastException().decode('utf-8')}")
                messagebox.showerror("错误", f"打开设备失败")
                return
            self.device_open = True
            self.status_label.config(text="状态: 已打开")
            self.log("设备打开成功")
            messagebox.showinfo("成功", "设备打开成功")
        else:
            self.log("设备已打开")
            messagebox.showwarning("警告", "设备已打开")

    def set_average_time(self):
        if not self.device_open:
            self.log("请先打开设备")
            messagebox.showwarning("警告", "请先打开设备")
            return
        try:
            avg_time = int(self.avg_entry.get())
            if avg_time <= 0:
                raise ValueError("平均次数必须大于0")
            result = lib.setSpectrumAverageTime(c_ushort(avg_time))
            if result < 0:
                self.log(f"设置平均次数失败: {lib.getLastException().decode('utf-8')}")
                messagebox.showerror("错误", f"设置平均次数失败")
            else:
                self.log(f"平均次数设置为: {avg_time}")
                messagebox.showinfo("成功", f"平均次数设置为: {avg_time}")
        except ValueError as e:
            self.log(f"无效输入: {e}")
            messagebox.showerror("错误", f"无效输入: {e}")

    def set_gain(self):
        if not self.device_open:
            self.log("请先打开设备")
            messagebox.showwarning("警告", "请先打开设备")
            return
        gain_str = self.gain_combo.get()
        is_fixed = 0 if gain_str == "0 (不固定)" else 1
        gain_val = int(gain_str.split()[0]) if is_fixed else 0
        result = lib.setPGAGain(c_int(is_fixed), c_ubyte(gain_val))
        if result < 0:
            self.log(f"设置增益系数失败: {lib.getLastException().decode('utf-8')}")
            messagebox.showerror("错误", f"设置增益系数失败")
        else:
            self.log(f"增益系数设置为: {gain_str}")
            messagebox.showinfo("成功", f"增益系数设置为: {gain_str}")

    def get_config(self):
        if not self.device_open:
            self.log("请先打开设备")
            messagebox.showwarning("警告", "请先打开设备")
            return

        self.scan_configs = []
        num_configs = lib.getScanSectionNumber()
        for i in range(num_configs):
            sec_name = ctypes.create_string_buffer(256)
            result = lib.getScanSectionName(i, sec_name, 256)
            if result == 0:
                self.scan_configs.append(sec_name.value.decode('utf-8'))
            else:
                self.log(f"获取配置 {i} 名称失败")
        self.config_combo["values"] = self.scan_configs
        self.log(f"找到 {len(self.scan_configs)} 个扫描配置")

        if self.scan_configs:
            self.config_combo.current(0)
            self.on_config_select(None)
        else:
            self.log("未找到扫描配置")
            messagebox.showwarning("警告", "未找到扫描配置")

    def load_config_params(self, scan_name):
        scan_type = ctypes.create_string_buffer(256)
        width_pixel = c_double()
        wl_start = c_ushort()
        wl_end = c_ushort()
        patterns_num = c_ushort()
        exp_time = c_double()
        result = lib.getScanSectionNameCfg(
            scan_name.encode('utf-8'), 0, scan_type, 256, ctypes.byref(width_pixel),
            ctypes.byref(wl_start), ctypes.byref(wl_end),
            ctypes.byref(patterns_num), ctypes.byref(exp_time)
        )
        if result < 0:
            self.log(f"获取配置 {scan_name} 参数失败: {lib.getLastException().decode('utf-8')}")
            messagebox.showerror("错误", f"获取配置参数失败")
            return

        self.scan_type_entry.delete(0, tk.END)
        self.scan_type_entry.insert(0, scan_type.value.decode('utf-8'))
        self.wl_start_entry.delete(0, tk.END)
        self.wl_start_entry.insert(0, str(wl_start.value))
        self.wl_end_entry.delete(0, tk.END)
        self.wl_end_entry.insert(0, str(wl_end.value))
        self.width_entry.delete(0, tk.END)
        self.width_entry.insert(0, str(width_pixel.value))
        self.patterns_entry.delete(0, tk.END)
        self.patterns_entry.insert(0, str(patterns_num.value))
        self.exp_time_entry.delete(0, tk.END)
        self.exp_time_entry.insert(0, str(exp_time.value))
        self.log(f"加载配置 {scan_name} 参数成功")

    def on_config_select(self, event):
        selected_config = self.config_combo.get()
        if not self.device_open:
            self.log("请先打开设备以激活配置")
            return
        index = self.scan_configs.index(selected_config)
        result = lib.setActiveScanIndex(c_ubyte(index))
        if result < 0:
            self.log(f"激活配置 {selected_config} 失败: {lib.getLastException().decode('utf-8')}")
            messagebox.showerror("错误", f"激活配置失败")
        else:
            self.log(f"激活配置 {selected_config} 成功")
            self.load_config_params(selected_config)

    def set_config(self):
        if not self.device_open or not self.config_combo.get():
            self.log("请先打开设备并选择配置")
            messagebox.showwarning("警告", "请先打开设备并选择配置")
            return

        try:
            scan_name = self.config_combo.get()
            scan_type = self.scan_type_entry.get().encode('utf-8')
            wl_start = c_ushort(int(self.wl_start_entry.get()))
            wl_end = c_ushort(int(self.wl_end_entry.get()))
            width_pixel = c_double(float(self.width_entry.get()))
            patterns_num = c_ushort(int(self.patterns_entry.get()))
            exp_time = c_double(float(self.exp_time_entry.get()))

            result = lib.setTgtCfg(
                scan_name.encode('utf-8'), 0, scan_type,
                wl_start, wl_end, width_pixel, patterns_num, exp_time
            )
            if result < 0:
                self.log(f"写入配置 {scan_name} 失败: {lib.getLastException().decode('utf-8')}")
                messagebox.showerror("错误", f"写入配置失败")
            else:
                self.log(f"配置 {scan_name} 写入成功")
                messagebox.showinfo("成功", "配置写入成功")
        except ValueError as e:
            self.log(f"无效输入: {e}")
            messagebox.showerror("错误", f"无效输入: {e}")

    def get_spectrum(self):
        if not self.device_open:
            self.log("请先打开设备")
            messagebox.showwarning("警告", "请先打开设备")
            return

        data_size = c_int()
        result = lib.getFormattedSpectrumLengths(ctypes.byref(data_size))
        if result < 0:
            self.log(f"获取数据长度失败: {lib.getLastException().decode('utf-8')}")
            messagebox.showerror("错误", f"获取数据长度失败")
            return

        wavelengths = (c_double * data_size.value)()
        intensities = (c_int * data_size.value)()
        data_size_ptr = c_int(data_size.value)
        result = lib.getFormattedSpectrum(wavelengths, intensities, ctypes.byref(data_size_ptr))
        if result < 0:
            self.log(f"获取光谱数据失败: {lib.getLastException().decode('utf-8')}")
            messagebox.showerror("错误", f"获取光谱数据失败")
            return

        self.wavelengths = [wavelengths[i] for i in range(data_size_ptr.value)]
        self.intensities = [intensities[i] for i in range(data_size_ptr.value)]
        self.log("光谱数据获取成功")
        self.log(f"光谱数据 ({data_size_ptr.value} 点):")
        for i in range(data_size_ptr.value):
            self.log(f"波长: {self.wavelengths[i]:.2f} nm, 强度: {self.intensities[i]}")
        messagebox.showinfo("成功", "光谱数据获取成功")

    def plot_spectrum(self):
        if not self.wavelengths or not self.intensities:
            self.log("请先获取光谱数据")
            messagebox.showwarning("警告", "请先获取光谱数据")
            return

        self.ax.clear()
        self.ax.plot(self.wavelengths, self.intensities, '-o', label="光谱数据")
        self.ax.set_xlabel("波长 (nm)")
        self.ax.set_ylabel("强度")
        self.ax.set_title("光谱仪数据")
        self.ax.legend()
        self.ax.grid(True)
        self.canvas.draw()
        self.log("光谱图绘制完成")

    def on_closing(self):
        if self.device_open:
            lib.closeSpectrometer()
            self.log("设备已关闭")
            self.device_open = False
        self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    root.geometry("900x700")
    app = SpectrometerGUI(root)
    root.mainloop()