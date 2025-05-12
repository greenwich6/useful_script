/** \file easynirwrapper.h
 *  \brief \b 光谱仪对外接口.
 *  \author wangdh
 *  \version 1.0
 *  \date 2020-03-18 15:10:00
 *  \details \b 描述
 *  - 光谱仪操作对外接口
 *	- 光谱仪基本操作
 */

#ifndef EASY_NIR_WRAPPER_H
#define EASY_NIR_WRAPPER_H

#include <map>
#include <list>
#include <vector>

#ifdef __cplusplus
extern "C"
{
#endif
	/**
	 * \brief 枚举连接到系统的所有dlp设备.
	 * \param[out] num 设备数量
	 * \return >= 0:枚举成功, < 0:枚举失败.
	 */
	int enumerateDevices(int* num);

	/**
	 * \brief 打开连接到系统的设备.
	 * \param[in] index 需要打开的设备号,有效范围在0~(N-1)之间(N为枚举到设备数量).
	 * \return >= 0:打开成功, < 0:打开失败.
	 */
	int openSpectrometer(int index);

	/**
	 * \brief 关闭连接到系统的设备.
	 */
	void closeSpectrometer();

	/**
	 * \brief 获取设备扫描配置参数个数
	 * \return 扫描配置参数个数
	 */
	int getScanSectionNumber();

	/**
	 * \brief 获取设备扫描配置名称
	 * \param[in] index 设备扫描配置序号(参考getScanSectionNumber() index必须小于getScanSectionNumber()返回值)
	 * \param[out] secName 设备扫描配置名称
	 * \param[in] size 设备扫描配置名称内存大小
	 * \return 0:获取成功, <0:获取失败
	 */
	int getScanSectionName(int index, char* secName, unsigned int size);

	/**
	 * \brief 获取某一扫描配置含有的子扫描配置个数
	 * \param name 扫描配置名称
	 * \return 子扫描配置个数
	 */
	int getScanSectionNameNumber(char* name);

	/**
	 * \brief 获取子扫描配置
	 * \param name 子扫描配置名称
	 * \param index 子扫描配置里的序号
	 * \param scanType 扫描类型
	 * \param scanTypeLen 扫描类型内存长度
	 * \param widthPixel 像素宽度
	 * \param wavelengthStart 开始扫描的最小波长，单位为纳米
	 * \param wavelengthEnd 结束扫描的最小波长，单位为纳米
	 * \param patternsNum 频谱中所期望的点数
	 * \param exposureTime 曝光时间
	 * \return 0:获取成功, <0:获取失败
	 */
	int getScanSectionNameCfg(char* name, int index, char* scanType, unsigned int scanTypeLen, double* widthPixel,
		unsigned short* wavelengthStart, unsigned short* wavelengthEnd,
		unsigned short* patternsNum, double* exposureTime);

	/**
	 * \brief 获取设备扫描参数类型数量
	 * \return 类型数量
	 */
	int getScanTypesNumber();

	/**
	 * \brief 获取设备扫描参数类型名称
	 * \param index 参数类型序号(参考getScanTypesNumber() index必须小于getScanTypesNumber()返回值)
	 * \return 扫描参数类型名称
	 */
	char* getScanTypesName(int index);

	/**
	 * \brief 获取像素宽度类型个数
	 * \return 像素宽度类型个数
	 */
	int getWidthPixelsNumber();

	/**
	 * \brief 获取像素宽度类型
	 * \param index 素宽类型序号(参考getWidthPixelsNumber() index必须小于getWidthPixelsNumber()返回值)
	 * \return 素宽宽度
	 */
	double getWidthPixel(int index);

	/**
	 * \brief 获取曝光时间类型个数
	 * \return 曝光时间类型个数
	 */
	int getExposureTimesNumber();

	/**
	 * \brief 获取曝光时间类型
	 * \param index 素宽类型序号(参考getExposureTimesNumber() index必须小于getExposureTimesNumber()返回值)
	 * \return 曝光时间类型
	 */
	double getExposureTime(int index);

	/**
	 * \brief 获取剩余模式数
	 * \param cfgName[in] 配置文件名称
	 * \param section[in] 当前扫描截面序号
	 * \param num[out] 剩余模式数(去除当前界面)
	 * \return 0:获取成功, <0:获取失败
	 */
	int getRemainPatternNum(char* cfgName, unsigned char section, unsigned short* num);

	/**
	 * \brief 获取模式范围
	 * \param[out] start 开始
	 * \param[out] end 结束
	 * \return 0:获取成功, <0:获取失败
	 */
	int getPatternsRange(int* start, int* end);

	/**
	 * \brief 获取活动的参数配置序号
	 * \param[out] index 活动的配置序号
	 * \return 0:获取成功, <0:获取失败.
	 */
	int getActiveScanIndex(int* index);

	/**
	 * \brief 设置活动的参数配置序号
	 * \param[in] index 配置序号
	 * \return 0:设置成功, <0:设置失败.
	 */
	int setActiveScanIndex(char index);

	/**
	 * \brief 获取扫描的预期时间（毫秒）
	 * \return 预期时间（毫秒）
	 */
	int getEstimatedScanTime();

	/**
	 * \brief 设置目标板配置参数
	 * \param name 配置参数名称
	 * \param section 参数所属扫描截面
	 * \param scanType 扫描类型
	 * \param wavelengthStart 起始波长
	 * \param wavelengthEnd 结束波长
	 * \param widthPixel 像素宽度
	 * \param patternsNum 模式数
	 * \param exposureTime 曝光时间
	 * \return 0:设置成功, <0:设置失败
	 */
	int setTgtCfg(const char* name, int section, const char* scanType, unsigned short wavelengthStart,
		unsigned short wavelengthEnd, double widthPixel, unsigned short patternsNum,
		double exposureTime);

	/**
	  * \brief 设置目标板配置参数
	  * \param cfgName 配置参数名称
	  * \param averNum 扫描次数
	  * \return 0:设置成功, <0:设置失败
	  */
	int setTgtCfgs(const char* cfgName, unsigned short averNum);

	/**
	 * \brief 移除扫描配置
	 * \param name 扫描配置名称
	 * \return 0:移除成功, <0:移除失败
	 */
	int removeTgtCfg(const char* name);

	/**
	 * \brief 获取版本号
	 * \param[out] pTivaSwVersion Tiva版本
	 * \param[out] pDlpcswVersion DLP版本
	 * \param[out] pDlpcFlashBuildVersion flash版本
	 * \param[out] pSpecLibVer 光谱仪库版本
	 * \param[out] pCalDataVer 校准参数版本
	 * \param[out] pRefCalDataVer 参考参数版本
	 * \param[out] pCfgDataVer 配置参数版本
	 * \return 0:获取正确 <0:获取失败
	 */
	int getVersions(unsigned int *pTivaSwVersion, unsigned int *pDlpcswVersion, unsigned int *pDlpcFlashBuildVersion, unsigned int *pSpecLibVer, unsigned int *pCalDataVer, unsigned int *pRefCalDataVer, unsigned int *pCfgDataVer);

	/**
	 * \brief 设置光源开关状态
	 * \param[in] status 1:开 0:关
	 * \return 0:设置成功, <0:设置失败
	 */
	int setLampStatus(int status);
		
	/**
	 * \brief 设置增益系数
	 * \param[in] isFixed 1:固定 0:不固定
	 * \param[in] gainVal 1,2,4,8,16,32 或 64
	 * \return true:设置成功, false:设置失败
	 */
	int setPGAGain(int isFixed, unsigned char gainVal);

	/**
	 * \brief 获取最大模式数
	 * \param[in] cfg_name 配置名称
	 * \param[out] start_nm 开始波长
	 * \param[out] end_nm 结束波长
	 * \param[out] width_index 像素宽度
	 * \param[out] scan_type 扫描类型
	 * \param[out] scan_num 扫描次数
	 * \return 最大允许模式数
	 */
	int getMaxPattern(char* cfg_name, int start_nm, int end_nm, unsigned char width_index, int scan_type, unsigned char scan_num);

	/**
	 * \brief 获取光谱数据长度
	 * \param[out] fileSize 数据长度
	 * \return >= 0:获取正确 < 0:获取失败
	 */
	int getFormattedSpectrumLengths(int* fileSize);

	/**
	 * \brief 设置光谱仪采集的平均次数
	 * \param[in] time 平均次数
	 * \return 0:设置成功, <0:设置失败
	 */
	int setSpectrumAverageTime(unsigned short time);

	/**
	 * \brief 获取光谱数据.
	 * \param[out] pWavelength 波长数据
	 * \param[out] pData 光谱数据
	 * \param[out] dataSize 光谱数据长度
	 * \return >= 0:获取正确 < 0:获取失败
	 */
	int getFormattedSpectrum(double *pWavelength, int *pData, int *dataSize);

	/**
	 * \brief 获取最后一次的错误信息.
	 * \return 错误信息[最大长度为256字节]
	 */
	const char* getLastException();

	/**
	 * \brief 日志功能.
	 * \param[in] onOff 1:开启日志 0:关闭日志
	 */
	void setLogSwitch(int onOff);


#ifdef __cplusplus
}
#endif

#endif//EASY_NIR_WRAPPER_H
