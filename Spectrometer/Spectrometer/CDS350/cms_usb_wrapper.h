#ifndef CMS_USB_WRAPPER_H
#define CMS_USB_WRAPPER_H

//在C#,Java等开发编程环境下,std::vector,std::string变得很难转换
// 现在将其舍弃,采用C接口

/**
 * @brief 获取USB设备数量
 * @return 设备数量
 * @note 此接口为所以接口的起始点
 */
int getUSBDeviceCount();

/**
 * @brief 获取USB设备名称
 * @param index 设备序号(从0开始)
 * @return 设备名称
 */
const char *getUSBDeviceName(const int index);

/**
 * @brief 打开USB
 * @param[in] name USB名称
 * @param[out] handle 打开的USB句柄
 * @return 0,正常;否则参考错误码.
 */
int openUSB(const char* name, int *handle);

/**
 * @brief 关闭USB
 * @param[in] handle 已打开的USB句柄
 */
void closeUSB(int handle);

/**
 * @brief 获取光谱仪序列号
 * @param[in] handle 设备句柄
 * @param[out] serial_number 光谱仪序列号（固定为8个字节,ASCII形式表示）
 * @return 0,正常;否则参考错误码.
 */
int getSerialNumber (const int handle, char* serial_number);

/**
 * @brief 获取光谱仪探测器型号
 * @param[in] handle 设备句柄
 * @param[out] model_number 光谱仪探测器型号（固定为16个字节,ASCII形式表示）
 * @return 0,正常;否则参考错误码.
 */
int getModelNumber (const int handle, char* model_number);


/**
 * @brief 获取USB设备波特率
 * @param handle 设备句柄
 * @param baudRate 波特率
 * @return 0,正常;否则参考错误码.
 */
int getUSBBaudRate(const int handle, int* baudRate);

/**
 * @brief 设置USB设备波特率
 * @param handle 设备句柄
 * @param baudRate 波特率
 * @return 0,正常;否则参考错误码.
 */
int setUSBBaudRate(const int handle, int baudRate);

/**
 * @brief 设置积分时间(微秒)
 * @param[in] handle 设备句柄
 * @param[in] integrationTime 积分时间(取值范围,60～100,000,000(us); 默认值:60)
 * @return 0,正常;否则参考错误码.
 */
int setIntegrationTime (const int handle, const int integrationTime);

/**
 * @brief 获取积分时间(微秒)
 * @param[in] handle 设备句柄
 * @param[out] integrationTime 积分时间(us)
 * @return 0,正常;否则参考错误码.
 */
int getIntegrationTime (const int handle, int* integrationTime);

/**
 * @brief 设置平均次数
 * @param[in] handle 设备句柄
 * @param[out] numberOfScansToAverageTogether 平均次数(0~255,默认20)
 * @return 0,正常;否则参考错误码.
 */
int setScansToAverage (const int handle, unsigned char numberOfScansToAverageTogether);

/**
 * @brief 获取平均次数
 * @param[in] handle 设备句柄
 * @param[out] numberOfScansToAverageTogether 平均次数(0~255,默认20)
 * @return 0,正常;否则参考错误码.
 */
int getScansToAverage (const int handle, unsigned char* numberOfScansToAverageTogether);

/**
 * @brief 设置像素范围[0-2047]
 * @param handle 设备句柄
 * @param start 起始位置
 * @param end 结束位置
 * @return 0,正常;否则参考错误码.
 */
int setPixelRange (const int handle, unsigned short start, unsigned short end);

/**
 * @brief 获取像素范围
 * @param handle 设备句柄
 * @param start 起始位置
 * @param end 结束位置
 * @return 0,正常;否则参考错误码.
 */
int getPixelRange (const int handle, unsigned short *start, unsigned short *end);

/**
 * @brief 获取波长数据
 * @param[in] handle 设备句柄
 * @param[out] value 光谱数据
 * @return 0,正常;否则参考错误码.
 */
int getWavelengths (const int handle, float* value);

/**
 * @brief 获取光谱数据
 * @param[in] handle 设备句柄
 * @param[out] value 光谱数据
 * @return 0,正常;否则参考错误码.
 */
int getSpectrum (const int handle, unsigned short* value);

/**
 * @brief 获取设备硬件版本
 * @param[in] handle 设备句柄
 * @param[out] version 设备硬件版本（固定为20个字节,ASCII形式表示）
 * @return 0,正常;否则参考错误码.
 */
int getHardwareVersion (const int handle, char* version);

/**
 * @brief 获取USB 连接状态
 * @param[in] handle 设备句柄
 * @param[out] state true:已连接，false:未连接
 * @return 0,正常;否则参考错误码.
 */
int getUSBState (const int handle, bool* state);

/**
 * @brief 获取光谱仪内腔温度
 * @param[in] handle 设备句柄
 * @param[out] temp 光谱仪内腔温度
 * @return 0,正常;否则参考错误码.
 */
int getTemperature (const int handle, double* temp);

/**
 * @brief 设置氙灯开关
 * @param[in] handle 设备句柄
 * @param[in] mode 氙灯模式,0:关闭, 1:单次脉冲, 2:连续脉冲
 * @return 0,正常;否则参考错误码.
 */
int setLampMode (const int handle, unsigned char mode);

/**
 * @brief 获取氙灯开关
 * @param[in] handle 设备句柄
 * @param[out] mode 氙灯模式,0:关闭, 1:单次脉冲, 2:连续脉冲
 * @return 0,正常;否则参考错误码.
 */
int getLampMode (const int handle, unsigned char* mode);

/**
 * @brief 获取脉冲最大次数
 * @param[in] handle 设备句柄
 * @param[out] number 脉冲最大次数
 * @return 0,正常;否则参考错误码.
 */
int getMaxNumberOfPulses (const int handle, int* number);

/**
 * @brief 获取脉冲次数
 * @param[in] handle 设备句柄
 * @param[out] number 脉冲次数
 * @return 0,正常;否则参考错误码.
 */
int getNumberOfPulses (const int handle, int *number);

/**
 * @brief 设置脉冲次数
 * @param[in] handle 设备句柄
 * @param[in] number 脉冲次数
 * @return 0,正常;否则参考错误码.
 */
int setNumberOfPulses (const int handle, int number);

/**
 * @brief 设置电平输出
 * @param[in] handle 设备句柄
 * @param[in] bit  GPIO 口序号
 * @param[in] state true:高电平(3.3V),false:低电平(0V)
 * @return 0,正常;否则参考错误码.
 */
int setDigitalLevel (const int handle, int bit, bool state);

/**
 * @brief 设置电压输出
 * @param[in] handle 设备句柄
 * @param[in] voltage 电压值（0~5V）
 * @return 0,正常;否则参考错误码.
 */
int setAnalogOut (const int handle, float voltage);

/**
 * @brief 获取波长校准系数
 * @param[in] handle 设备句柄
 * @param[out] coeffs校准系数,数量固定为4
 * @return 0,正常;否则参考错误码.
 */
int getWavelengthCalibrationCoefficients(const int handle, double* coeffs);

/**
 * @brief 注册获取外触发光谱数据的回调函数
 * @param[in] handle 设备句柄
 * @param[in] call_back 回调函数指针
 * @param[out] value 光谱数据组
 */
int registerTrigSpectrumsCallback (const int handle, int (*call_back)(unsigned short **), unsigned short **value);

/**
 * @brief 设置外触发配置
 * @param[in] handle 设备句柄
 * @param[in] enable 外触发使能 true:开启，false：关闭,默认为关闭
 * @param[in] type 外触发类型 0:上升沿;1:高电平触发（3.3V）,其他值无效,默认为0
 * @param[in] num 采集个数，进行多少次采集，取值范围1-63，,默认为0
 * @return 0,正常;否则参考错误码.
 * @note 采集过程中产生外触发误操作，则此误操作会被忽略.
 */
int setTrigEnable (const int handle, bool enable, int type, int num);

/**
 * @brief 获取外触发配置
 * @param[in] handle 设备句柄
 * @param[out] enable 外触发使能 true:开启，false：关闭,默认为关闭
 * @param[out] type 外触发类型 0:上升沿;1:高电平触发（3.3V）,其他值无效,默认为0
 * @param[out] num 采集个数，进行多少次采集，取值范围1-63,默认为0
 * @return 0,正常;否则参考错误码.
 */
int getTrigEnable (const int handle, bool *enable, int *type, int *num);

/**
 * @brief 获取外触发状态
 * @param[in] handle 设备句柄
 * @param[out] capture_status 采集状态 外触发有数据更新时为1，全部数据被取走后为0.
 * @param[out] spetctrum_status_h 参照@setTrigEnable中@num,，每个num对应一个比特（33-63,最高位除外）
 * @param[out] spetctrum_status_l 参照@setTrigEnable中@num,，每个num对应一个比特(1-32)
 * @return 0,正常;否则参考错误码.
 */
int getTrigStatus (const int handle, bool *capture_status, int *spetctrum_status_h, int *spetctrum_status_l);

/**
 * @brief 获取外触发光谱数据
 * @param[in] handle 设备句柄
 * @param[out] ack 0:空闲,1:采集中,2:已完成
 * @param[out] value 光谱数据组
 * @return 0,正常;否则参考错误码.
 * @note 数据组长度对于@getTrigEnable中的num值
 */
int getTrigSpectrums (const int handle, int *ack, unsigned short **value);

/**
 * @brief 全局复位（仅仅将固化寄存器的值复制到控制寄存器中）
 * @param[in] handle 设备句柄
 * @return 0,正常;否则参考错误码.
 */
int resetDevice(const int handle);

/**
 * @brief 自定义设备序列号
 * @param[in] handle 设备句柄
 * @param[in] serial_number 自定义序列号
 * @param[in] serial_number_length 自定义序列号长度,最多12个字节
 * @return 0,正常;否则参考错误码.
 */
int setSerialNumberStored (const int handle, const char* serial_number, const int serial_number_length);

/**
 * @brief 获取自定义设备序列号
 * @param[in] handle 设备句柄
 * @param[out] serial_number 自定义序列号,12个字节
 * @return 0,正常;否则参考错误码.
 */
int getSerialNumberStored (const int handle, char* serial_number);

/**
 * @brief 固化积分时间(微秒)
 * @param[in] handle 设备句柄
 * @param[in] integrationTime 积分时间(取值范围,60～100,000,000(us); 默认值:60)
 * @return 0,正常;否则参考错误码.
 */
int setIntegrationTimeStored (const int handle, const int integrationTime);


/**
 * @brief 固化平均次数
 * @param[in] handle 设备句柄
 * @param[out] numberOfScansToAverageTogether 平均次数(1~255,默认20)
 * @return 0,正常;否则参考错误码.
 */
int setScansToAverageStored (const int handle, unsigned char numberOfScansToAverageTogether);

/**
 * @brief 固化平滑宽度
 * @param[in] handle 设备句柄
 * @param[out] width 平均次数(0~100,默认0)
 * @return 0,正常;否则参考错误码.
 */
int setSmoothingWidthStored (const int handle, unsigned char width);

/**
 * @brief 读取固化波长范围
 * @param[in] handle 设备句柄
 * @param[out] start 起始波长
 * @param[out] end 结束波长
 * @return 0,正常;否则参考错误码.
 */
int getWavelengthsRangeStored (const int handle, double *start, double *end);

/**
 * @brief 设置固化波长范围
 * @param[in] handle 设备句柄
 * @param[in] start 起始波长
 * @param[in] end 结束波长
 * @return 0,正常;否则参考错误码.
 */
int setWavelengthsRangeStored (const int handle, double start, double end);

/**
 * @brief 读取固化波长数量
 * @param[in] handle 设备句柄
 * @param[out] count 波长数量
 * @return 0,正常;否则参考错误码.
 */
int getWavelengthsCountStored (const int handle, int *count);

/**
 * @brief 读取固化光谱波长范围对应像素范围
 * @param[in] handle 设备句柄
 * @param[out] start 起始波长像素
 * @param[out] end 结束波长像素
 * @return 0,正常;否则参考错误码.
 */
int getWavelengthsRangeToPixelStored (const int handle, int *start, int *end);

/**
 * @brief 读取固化原始波长范围
 * @param[in] handle 设备句柄
 * @param[out] start 起始波长
 * @param[out] end 结束波长
 * @return 0,正常;否则参考错误码.
 */
int getRawWavelengthsRangeStored (const int handle, double *start, double *end);

/**
 * @brief 获取错误信息
 * @param error_code 错误码
 * @return 错误信息
 */
const char* getErrorMessage(int error_code);

#endif // CMS_USB_WRAPPER_H
