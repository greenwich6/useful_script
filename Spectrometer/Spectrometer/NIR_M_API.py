import ctypes
from ctypes import c_int, c_char_p, c_double, c_ushort, POINTER, c_uint, c_ubyte

class NIR_M_API:
    """光谱仪 SDK 的 Python 封装类"""
    def __init__(self, dll_path):
        """初始化并加载 DLL 文件"""
        try:
            self.lib = ctypes.CDLL(dll_path)
            self._setup_function_signatures()
            self.device_open = False
        except OSError as e:
            raise RuntimeError(f"加载 DLL 失败: {e}")

    def _setup_function_signatures(self):
        """设置函数签名"""
        self.lib.enumerateDevices.argtypes = [POINTER(c_int)]
        self.lib.enumerateDevices.restype = c_int
        self.lib.openSpectrometer.argtypes = [c_int]
        self.lib.openSpectrometer.restype = c_int
        self.lib.closeSpectrometer.argtypes = []
        self.lib.closeSpectrometer.restype = None
        self.lib.getScanSectionNumber.argtypes = []
        self.lib.getScanSectionNumber.restype = c_int
        self.lib.getScanSectionName.argtypes = [c_int, c_char_p, c_uint]
        self.lib.getScanSectionName.restype = c_int
        self.lib.getScanSectionNameCfg.argtypes = [c_char_p, c_int, c_char_p, c_uint, POINTER(c_double),
                                                  POINTER(c_ushort), POINTER(c_ushort), POINTER(c_ushort), POINTER(c_double)]
        self.lib.getScanSectionNameCfg.restype = c_int
        self.lib.setTgtCfg.argtypes = [c_char_p, c_int, c_char_p, c_ushort, c_ushort, c_double, c_ushort, c_double]
        self.lib.setTgtCfg.restype = c_int
        self.lib.getFormattedSpectrumLengths.argtypes = [POINTER(c_int)]
        self.lib.getFormattedSpectrumLengths.restype = c_int
        self.lib.getFormattedSpectrum.argtypes = [POINTER(c_double), POINTER(c_int), POINTER(c_int)]
        self.lib.getFormattedSpectrum.restype = c_int
        self.lib.setSpectrumAverageTime.argtypes = [c_ushort]
        self.lib.setSpectrumAverageTime.restype = c_int
        self.lib.setPGAGain.argtypes = [c_int, c_ubyte]
        self.lib.setPGAGain.restype = c_int
        self.lib.setActiveScanIndex.argtypes = [c_ubyte]
        self.lib.setActiveScanIndex.restype = c_int
        self.lib.getLastException.argtypes = []
        self.lib.getLastException.restype = c_char_p

    def enumerate_devices(self):
        """枚举连接的设备，返回设备数量"""
        num_devices = c_int()
        result = self.lib.enumerateDevices(ctypes.byref(num_devices))
        if result < 0:
            raise RuntimeError(f"枚举设备失败: {self.get_last_exception()}")
        return num_devices.value

    def open_device(self, index=0):
        """打开指定索引的设备"""
        if not self.device_open:
            result = self.lib.openSpectrometer(index)
            if result < 0:
                raise RuntimeError(f"打开设备失败: {self.get_last_exception()}")
            self.device_open = True
        else:
            raise RuntimeError("设备已打开")

    def close_device(self):
        """关闭设备"""
        if self.device_open:
            self.lib.closeSpectrometer()
            self.device_open = False

    def get_scan_configs(self):
        """获取所有扫描配置名称"""
        num_configs = self.lib.getScanSectionNumber()
        configs = []
        for i in range(num_configs):
            sec_name = ctypes.create_string_buffer(256)
            result = self.lib.getScanSectionName(i, sec_name, 256)
            if result == 0:
                configs.append(sec_name.value.decode('utf-8'))
            else:
                raise RuntimeError(f"获取配置 {i} 名称失败: {self.get_last_exception()}")
        return configs

    def get_config_params(self, config_name, section=0):
        """获取指定配置的参数"""
        scan_type = ctypes.create_string_buffer(256)
        width_pixel = c_double()
        wl_start = c_ushort()
        wl_end = c_ushort()
        patterns_num = c_ushort()
        exp_time = c_double()
        result = self.lib.getScanSectionNameCfg(
            config_name.encode('utf-8'), section, scan_type, 256, ctypes.byref(width_pixel),
            ctypes.byref(wl_start), ctypes.byref(wl_end),
            ctypes.byref(patterns_num), ctypes.byref(exp_time)
        )
        if result < 0:
            raise RuntimeError(f"获取配置 {config_name} 参数失败: {self.get_last_exception()}")
        return {
            "scan_type": scan_type.value.decode('utf-8'),
            "width_pixel": width_pixel.value,
            "wavelength_start": wl_start.value,
            "wavelength_end": wl_end.value,
            "patterns_num": patterns_num.value,
            "exposure_time": exp_time.value
        }

    def set_config_params(self, config_name, section=0, scan_type=None, wavelength_start=None,
                          wavelength_end=None, width_pixel=None, patterns_num=None, exposure_time=None):
        """设置指定配置的参数"""
        params = self.get_config_params(config_name, section)
        scan_type = scan_type if scan_type is not None else params["scan_type"]
        wavelength_start = wavelength_start if wavelength_start is not None else params["wavelength_start"]
        wavelength_end = wavelength_end if wavelength_end is not None else params["wavelength_end"]
        width_pixel = width_pixel if width_pixel is not None else params["width_pixel"]
        patterns_num = patterns_num if patterns_num is not None else params["patterns_num"]
        exposure_time = exposure_time if exposure_time is not None else params["exposure_time"]

        result = self.lib.setTgtCfg(
            config_name.encode('utf-8'), section, scan_type.encode('utf-8'),
            c_ushort(wavelength_start), c_ushort(wavelength_end),
            c_double(width_pixel), c_ushort(patterns_num), c_double(exposure_time)
        )
        if result < 0:
            raise RuntimeError(f"写入配置 {config_name} 失败: {self.get_last_exception()}")

    def set_active_config(self, index):
        """激活指定索引的配置"""
        result = self.lib.setActiveScanIndex(c_ubyte(index))
        if result < 0:
            raise RuntimeError(f"激活配置索引 {index} 失败: {self.get_last_exception()}")

    def set_average_time(self, avg_time):
        """设置光谱平均次数"""
        if avg_time <= 0:
            raise ValueError("平均次数必须大于0")
        result = self.lib.setSpectrumAverageTime(c_ushort(avg_time))
        if result < 0:
            raise RuntimeError(f"设置平均次数失败: {self.get_last_exception()}")

    def set_gain(self, is_fixed, gain_val):
        """设置增益系数"""
        if is_fixed and gain_val not in [1, 2, 4, 8, 16, 32, 64]:
            raise ValueError("固定增益必须为 1, 2, 4, 8, 16, 32, 64 中的一个")
        result = self.lib.setPGAGain(c_int(is_fixed), c_ubyte(gain_val))
        if result < 0:
            raise RuntimeError(f"设置增益系数失败: {self.get_last_exception()}")

    def get_spectrum(self):
        """获取光谱数据，返回波长和强度列表"""
        data_size = c_int()
        result = self.lib.getFormattedSpectrumLengths(ctypes.byref(data_size))
        if result < 0:
            raise RuntimeError(f"获取数据长度失败: {self.get_last_exception()}")

        wavelengths = (c_double * data_size.value)()
        intensities = (c_int * data_size.value)()
        data_size_ptr = c_int(data_size.value)
        result = self.lib.getFormattedSpectrum(wavelengths, intensities, ctypes.byref(data_size_ptr))
        if result < 0:
            raise RuntimeError(f"获取光谱数据失败: {self.get_last_exception()}")

        return ([wavelengths[i] for i in range(data_size_ptr.value)],
                [intensities[i] for i in range(data_size_ptr.value)])

    def get_last_exception(self):
        """获取最后一次错误信息"""
        return self.lib.getLastException().decode('utf-8')

    def __del__(self):
        """析构时关闭设备"""
        if self.device_open:
            self.close_device()

# 示例使用
if __name__ == "__main__":
    try:
        # 初始化 API
        nir = NIR_M_API("NIR_M/easynirlib.dll")

        # 枚举设备
        num_devices = nir.enumerate_devices()
        print(f"找到 {num_devices} 个设备")

        # 打开设备
        nir.open_device(0)
        print("设备打开成功")

        # 获取配置
        configs = nir.get_scan_configs()
        print(f"扫描配置: {configs}")

        # 获取并打印第一个配置参数
        params = nir.get_config_params(configs[0])
        print(f"配置 {configs[0]} 参数: {params}")

        # 设置增益
        nir.set_gain(1, 4)  # 固定增益 4
        print("增益设置为固定 4 倍")

        # 设置平均次数
        nir.set_average_time(3)
        print("平均次数设置为 3")

        # 激活配置
        nir.set_active_config(0)
        print(f"激活配置 {configs[0]}")

        # 获取光谱数据
        wavelengths, intensities = nir.get_spectrum()
        print(f"光谱数据 ({len(wavelengths)} 点):")
        for wl, inten in zip(wavelengths, intensities):
            print(f"波长: {wl:.2f} nm, 强度: {inten}")

        # 关闭设备
        nir.close_device()
        print("设备已关闭")

    except RuntimeError as e:
        print(f"错误: {e}")
    except ValueError as e:
        print(f"参数错误: {e}")