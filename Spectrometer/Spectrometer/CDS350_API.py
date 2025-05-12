import ctypes
from tkinter import messagebox
import matplotlib.pyplot as plt


class CDS350:
    """CDS350光谱仪控制类"""

    def __init__(self, dll_path="CDS350/cms_driver_x64_usb.dll"):
        """初始化类，加载DLL"""
        try:
            self.wrapper = ctypes.CDLL(dll_path)
            self._setup_function_prototypes()
            self.handle = ctypes.c_int(-1)  # 初始化句柄为无效值
            self.wavelengths = None
            self.spectrum = None
        except OSError as e:
            raise RuntimeError(f"加载DLL失败: {e}")

    def _setup_function_prototypes(self):
        """设置DLL函数原型"""
        self.wrapper.getUSBDeviceCount.restype = ctypes.c_int
        self.wrapper.getUSBDeviceName.argtypes = [ctypes.c_int]
        self.wrapper.getUSBDeviceName.restype = ctypes.c_char_p
        self.wrapper.openUSB.argtypes = [ctypes.c_char_p, ctypes.POINTER(ctypes.c_int)]
        self.wrapper.closeUSB.argtypes = [ctypes.c_int]
        self.wrapper.setIntegrationTime.argtypes = [ctypes.c_int, ctypes.c_int]
        self.wrapper.getIntegrationTime.argtypes = [ctypes.c_int, ctypes.POINTER(ctypes.c_int)]
        self.wrapper.setScansToAverage.argtypes = [ctypes.c_int, ctypes.c_ubyte]
        self.wrapper.getScansToAverage.argtypes = [ctypes.c_int, ctypes.POINTER(ctypes.c_ubyte)]
        self.wrapper.getWavelengths.argtypes = [ctypes.c_int, ctypes.POINTER(ctypes.c_float)]
        self.wrapper.getSpectrum.argtypes = [ctypes.c_int, ctypes.POINTER(ctypes.c_ushort)]

    def initialize_device(self):
        """初始化设备并打开第一个USB设备，返回积分时间和平均次数"""
        device_count = self.wrapper.getUSBDeviceCount()
        if device_count == 0:
            raise RuntimeError("未找到USB设备。")

        device_name_ptr = self.wrapper.getUSBDeviceName(0)
        if not device_name_ptr:
            raise RuntimeError("获取设备名称失败。")

        ret_open = self.wrapper.openUSB(device_name_ptr, ctypes.byref(self.handle))
        if ret_open != 0:
            raise RuntimeError("打开USB设备失败。")

        # 读取积分时间和平均次数
        integration_time = self.get_integration_time()
        scans_to_average = self.get_scans_to_average()
        return integration_time, scans_to_average

    def close_device(self):
        """关闭设备"""
        if self.handle.value != -1:
            self.wrapper.closeUSB(self.handle)
            self.handle = ctypes.c_int(-1)

    def set_integration_time(self, time):
        """设置积分时间（微秒），范围60～100,000,000"""
        if not isinstance(time, int) or time < 60:
            raise ValueError("积分时间必须为整数且至少为60微秒。")
        if self.handle.value == -1:
            raise RuntimeError("设备尚未初始化。")
        ret = self.wrapper.setIntegrationTime(self.handle, time)
        if ret != 0:
            raise RuntimeError(f"设置积分时间失败，返回码: {ret}")

    def get_integration_time(self):
        """获取当前积分时间（微秒）"""
        if self.handle.value == -1:
            raise RuntimeError("设备尚未初始化。")
        integration_time = ctypes.c_int()
        ret = self.wrapper.getIntegrationTime(self.handle, ctypes.byref(integration_time))
        if ret != 0:
            raise RuntimeError(f"获取积分时间失败，返回码: {ret}")
        return integration_time.value

    def set_scans_to_average(self, scans):
        """设置平均次数，范围1～255"""
        if not isinstance(scans, int) or scans < 1 or scans > 255:
            raise ValueError("平均次数必须为1到255之间的整数。")
        if self.handle.value == -1:
            raise RuntimeError("设备尚未初始化。")
        ret = self.wrapper.setScansToAverage(self.handle, ctypes.c_ubyte(scans))
        if ret != 0:
            raise RuntimeError(f"设置平均次数失败，返回码: {ret}")

    def get_scans_to_average(self):
        """获取当前平均次数"""
        if self.handle.value == -1:
            raise RuntimeError("设备尚未初始化。")
        scans_to_average = ctypes.c_ubyte()
        ret = self.wrapper.getScansToAverage(self.handle, ctypes.byref(scans_to_average))
        if ret != 0:
            raise RuntimeError(f"获取平均次数失败，返回码: {ret}")
        return scans_to_average.value

    def read_spectrum(self):
        """读取波长和光谱数据，返回波长和强度数组"""
        if self.handle.value == -1:
            raise RuntimeError("设备尚未初始化。")
        self.wavelengths = (ctypes.c_float * 2048)()
        self.spectrum = (ctypes.c_ushort * 2048)()
        ret_wl = self.wrapper.getWavelengths(self.handle, self.wavelengths)
        ret_sp = self.wrapper.getSpectrum(self.handle, self.spectrum)
        if ret_wl != 0 or ret_sp != 0:
            raise RuntimeError(f"读取光谱数据失败，波长返回码: {ret_wl}, 光谱返回码: {ret_sp}")
        return list(self.wavelengths), list(self.spectrum)

    def plot_spectrum(self):
        """绘制光谱图"""
        if self.wavelengths is None or self.spectrum is None:
            raise RuntimeError("请先读取光谱数据。")
        fig, ax = plt.subplots()
        ax.plot(self.wavelengths, self.spectrum, label="光谱")
        ax.set_xlabel("波长 (nm)")
        ax.set_ylabel("强度")
        ax.set_title("光谱数据")
        ax.legend()
        ax.grid(True)
        plt.show()

    def __del__(self):
        """析构函数，确保设备关闭"""
        self.close_device()


# 示例用法
if __name__ == "__main__":
    try:
        # 创建实例
        spectrometer = CDS350()

        # 初始化设备并获取参数
        integration_time, scans_to_average = spectrometer.initialize_device()
        print(f"当前积分时间: {integration_time} 微秒")
        print(f"当前平均次数: {scans_to_average}")

        # 设置参数
        spectrometer.set_integration_time(1000000)  # 设置为1000000微秒
        spectrometer.set_scans_to_average(1)  # 设置为10次平均

        # 读取并绘制光谱
        wavelengths, spectrum = spectrometer.read_spectrum()
        spectrometer.plot_spectrum()

    except Exception as e:
        print(f"发生错误: {e}")
    finally:
        spectrometer.close_device()