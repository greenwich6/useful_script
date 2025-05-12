import ctypes
import tkinter as tk
from tkinter import messagebox, ttk
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

# 加载DLL
try:
    wrapper = ctypes.CDLL("CDS350/cms_driver_x64_usb.dll")
except OSError as e:
    messagebox.showerror("错误", f"加载DLL失败: {e}")
    exit(1)

# 定义函数原型
wrapper.getUSBDeviceCount.restype = ctypes.c_int
wrapper.getUSBDeviceName.argtypes = [ctypes.c_int]
wrapper.getUSBDeviceName.restype = ctypes.c_char_p
wrapper.openUSB.argtypes = [ctypes.c_char_p, ctypes.POINTER(ctypes.c_int)]
wrapper.closeUSB.argtypes = [ctypes.c_int]
wrapper.setIntegrationTime.argtypes = [ctypes.c_int, ctypes.c_int]
wrapper.getIntegrationTime.argtypes = [ctypes.c_int, ctypes.POINTER(ctypes.c_int)]
wrapper.setScansToAverage.argtypes = [ctypes.c_int, ctypes.c_ubyte]
wrapper.getScansToAverage.argtypes = [ctypes.c_int, ctypes.POINTER(ctypes.c_ubyte)]
wrapper.getWavelengths.argtypes = [ctypes.c_int, ctypes.POINTER(ctypes.c_float)]
wrapper.getSpectrum.argtypes = [ctypes.c_int, ctypes.POINTER(ctypes.c_ushort)]

# 全局变量
handle = ctypes.c_int()
wavelengths = None
spectrum = None
canvas = None


# 初始化设备并读取参数
def init_device():
    global handle
    device_count = wrapper.getUSBDeviceCount()
    if device_count == 0:
        messagebox.showwarning("警告", "未找到USB设备。")
        return

    device_name_ptr = wrapper.getUSBDeviceName(0)
    if not device_name_ptr:
        messagebox.showerror("错误", "获取设备名称失败。")
        return

    ret_open = wrapper.openUSB(device_name_ptr, ctypes.byref(handle))
    if ret_open != 0:
        messagebox.showerror("错误", "打开USB设备失败。")
        return

    # 读取积分时间
    integration_time = ctypes.c_int()
    ret_time = wrapper.getIntegrationTime(handle, ctypes.byref(integration_time))
    if ret_time == 0:
        integration_time_entry.delete(0, tk.END)
        integration_time_entry.insert(0, str(integration_time.value))
    else:
        messagebox.showwarning("警告", "读取积分时间失败。")

    # 读取平均次数
    scans_to_average = ctypes.c_ubyte()
    ret_scans = wrapper.getScansToAverage(handle, ctypes.byref(scans_to_average))
    if ret_scans == 0:
        scans_to_average_entry.delete(0, tk.END)
        scans_to_average_entry.insert(0, str(scans_to_average.value))
    else:
        messagebox.showwarning("警告", "读取平均次数失败。")

    messagebox.showinfo("成功", "设备初始化并打开成功。")


# 设置积分时间
def set_integration_time():
    try:
        time = int(integration_time_entry.get())
        if time < 1:
            messagebox.showwarning("警告", "积分时间必须至少为1微秒。")
            return
        wrapper.setIntegrationTime(handle, time)
        messagebox.showinfo("成功", f"积分时间已设置为 {time} 微秒。")
    except ValueError:
        messagebox.showerror("错误", "无效的积分时间。")


# 设置平均次数
def set_scans_to_average():
    try:
        scans = int(scans_to_average_entry.get())
        if scans < 1:
            messagebox.showwarning("警告", "平均次数必须至少为1。")
            return
        wrapper.setScansToAverage(handle, ctypes.c_ubyte(scans))
        messagebox.showinfo("成功", f"平均次数已设置为 {scans}。")
    except ValueError:
        messagebox.showerror("错误", "无效的平均次数。")


# 初始化绘图区域
def init_plot():
    global canvas
    fig, ax = plt.subplots()
    ax.set_xlabel("波长 (nm)")
    ax.set_ylabel("强度")
    ax.set_title("光谱数据")
    ax.grid(True)

    canvas = FigureCanvasTkAgg(fig, master=plot_frame)
    canvas.draw()
    canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)


# 读取波长和强度并绘制曲线
def read_and_plot():
    global wavelengths, spectrum, canvas
    wavelengths = (ctypes.c_float * 2048)()
    spectrum = (ctypes.c_ushort * 2048)()

    wrapper.getWavelengths(handle, wavelengths)
    wrapper.getSpectrum(handle, spectrum)

    if canvas:
        canvas.get_tk_widget().destroy()

    fig, ax = plt.subplots()
    ax.plot(wavelengths, spectrum, label="光谱")
    ax.set_xlabel("波长 (nm)")
    ax.set_ylabel("强度")
    ax.set_title("光谱数据")
    ax.legend()
    ax.grid(True)

    canvas = FigureCanvasTkAgg(fig, master=plot_frame)
    canvas.draw()
    canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)


# 关闭设备
def close_device():
    wrapper.closeUSB(handle)
    messagebox.showinfo("提示", "设备已关闭。")


# 创建主窗口
root = tk.Tk()
root.title("光谱仪控制")

# 初始化设备按钮
init_button = tk.Button(root, text="初始化设备", command=init_device)
init_button.pack(pady=10)

# 设置积分时间
integration_time_frame = tk.Frame(root)
integration_time_frame.pack(pady=5)
tk.Label(integration_time_frame, text="积分时间 (微秒):").pack(side=tk.LEFT)
integration_time_entry = tk.Entry(integration_time_frame)
integration_time_entry.pack(side=tk.LEFT, padx=5)
set_integration_button = tk.Button(integration_time_frame, text="设置", command=set_integration_time)
set_integration_button.pack(side=tk.LEFT)

# 设置平均次数
scans_to_average_frame = tk.Frame(root)
scans_to_average_frame.pack(pady=5)
tk.Label(scans_to_average_frame, text="平均次数:").pack(side=tk.LEFT)
scans_to_average_entry = tk.Entry(scans_to_average_frame)
scans_to_average_entry.pack(side=tk.LEFT, padx=5)
set_scans_button = tk.Button(scans_to_average_frame, text="设置", command=set_scans_to_average)
set_scans_button.pack(side=tk.LEFT)

# 读取数据并绘制曲线
read_button = tk.Button(root, text="读取并绘制光谱", command=read_and_plot)
read_button.pack(pady=10)

# 绘图区域
plot_frame = tk.Frame(root)
plot_frame.pack(fill=tk.BOTH, expand=True)

# 初始化空的绘图区域
init_plot()

# 关闭设备按钮
close_button = tk.Button(root, text="关闭设备", command=close_device)
close_button.pack(pady=10)

# 运行主循环
root.mainloop()