import tushare as ts
import pandas as pd
import os
import sys
import os.path
import time
from datetime import datetime, timedelta

# 添加当前目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.config import TS_TOKEN, DATA_PATH, CACHE_CONFIG

class DataFetcher:
    def __init__(self):
        # 初始化tushare
        self.ts = ts
        if TS_TOKEN:
            # 直接使用token初始化pro API（按照tushare官方示例）
            self.pro = ts.pro_api(TS_TOKEN)
    
    def get_stock_list(self):
        """获取所有股票列表"""
        cache_file = f'{DATA_PATH}/stock_list_cache.csv'
        
        # 检查是否启用缓存
        if CACHE_CONFIG.get('enabled', True):
            # 检查缓存文件是否存在
            if os.path.exists(cache_file):
                # 检查缓存是否过期
                file_time = datetime.fromtimestamp(os.path.getmtime(cache_file))
                expire_days = CACHE_CONFIG.get('stock_list_expire_days', 7)
                
                if (datetime.now() - file_time).days < expire_days:
                    print(f"使用缓存的股票列表数据")
                    try:
                        stock_list = pd.read_csv(cache_file)
                        return stock_list
                    except Exception as e:
                        print(f"读取缓存文件失败: {e}")
        
        try:
            # 检查是否初始化了pro API
            if hasattr(self, 'pro'):
                # 使用pro API获取股票列表
                stock_list = self.pro.stock_basic(exchange='', list_status='L', fields='ts_code,symbol,name,area,industry,list_date')
            else:
                # 直接使用旧API
                stock_list = self.ts.get_stock_basics()
            
            # 保存到缓存
            if CACHE_CONFIG.get('enabled', True):
                try:
                    os.makedirs(DATA_PATH, exist_ok=True)
                    stock_list.to_csv(cache_file, index=False)
                    print(f"股票列表数据已缓存到: {cache_file}")
                except Exception as e:
                    print(f"保存缓存文件失败: {e}")
            
            return stock_list
        except Exception as e:
            error_msg = str(e)
            # 检查是否是权限错误
            if '权限' in error_msg or 'permission' in error_msg.lower() or '403' in error_msg or '401' in error_msg:
                print(f"Pro API权限不足，尝试使用旧API: {e}")
                try:
                    stock_list = self.ts.get_stock_basics()
                    
                    # 保存到缓存
                    if CACHE_CONFIG.get('enabled', True):
                        try:
                            os.makedirs(DATA_PATH, exist_ok=True)
                            stock_list.to_csv(cache_file, index=False)
                            print(f"股票列表数据已缓存到: {cache_file}")
                        except Exception as e2:
                            print(f"保存缓存文件失败: {e2}")
                    
                    return stock_list
                except Exception as e2:
                    print(f"使用旧API获取股票列表失败: {e2}")
                    return None
            else:
                print(f"获取股票列表失败: {e}")
                return None
    
    def get_stock_data(self, code, start_date, end_date):
        """获取单个股票的历史数据"""
        # 创建缓存文件名（包含股票代码和日期范围）
        cache_file = f'{DATA_PATH}/stock_data_{code}_{start_date}_{end_date}.csv'
        
        # 检查是否启用缓存
        if CACHE_CONFIG.get('enabled', True):
            # 检查缓存文件是否存在
            if os.path.exists(cache_file):
                # 检查缓存是否过期
                file_time = datetime.fromtimestamp(os.path.getmtime(cache_file))
                expire_days = CACHE_CONFIG.get('stock_data_expire_days', 1)
                
                if (datetime.now() - file_time).days < expire_days:
                    print(f"使用缓存的股票数据: {code}")
                    try:
                        df = pd.read_csv(cache_file)
                        return df
                    except Exception as e:
                        print(f"读取缓存文件失败: {e}")
        
        try:
            # 检查是否初始化了pro API
            if hasattr(self, 'pro'):
                # 使用pro API获取股票历史数据
                df = self.pro.daily(ts_code=code, start_date=start_date, end_date=end_date)
            else:
                # 直接使用旧API
                df = self.ts.get_k_data(code, start=start_date, end=end_date)
            
            # 保存到缓存
            if CACHE_CONFIG.get('enabled', True) and df is not None and not df.empty:
                try:
                    os.makedirs(DATA_PATH, exist_ok=True)
                    df.to_csv(cache_file, index=False)
                    print(f"股票数据已缓存到: {cache_file}")
                except Exception as e:
                    print(f"保存缓存文件失败: {e}")
            
            return df
        except Exception as e:
            error_msg = str(e)
            # 检查是否是权限错误
            if '权限' in error_msg or 'permission' in error_msg.lower() or '403' in error_msg or '401' in error_msg:
                print(f"Pro API权限不足，尝试使用旧API: {e}")
                try:
                    df = self.ts.get_k_data(code, start=start_date, end=end_date)
                    
                    # 保存到缓存
                    if CACHE_CONFIG.get('enabled', True) and df is not None and not df.empty:
                        try:
                            os.makedirs(DATA_PATH, exist_ok=True)
                            df.to_csv(cache_file, index=False)
                            print(f"股票数据已缓存到: {cache_file}")
                        except Exception as e2:
                            print(f"保存缓存文件失败: {e2}")
                    
                    return df
                except Exception as e2:
                    print(f"使用旧API获取股票数据失败: {e2}")
                    return None
            else:
                print(f"获取股票数据失败: {e}")
                return None
    
    def get_today_data(self, code):
        """获取股票当日数据"""
        try:
            # 检查是否初始化了pro API
            if hasattr(self, 'pro'):
                # 使用pro API获取当日数据
                df = self.pro.query('daily', ts_code=code, trade_date=pd.Timestamp.today().strftime('%Y%m%d'))
                return df
            else:
                # 直接使用旧API
                df = self.ts.get_today_data(code=code)
                return df
        except Exception as e:
            error_msg = str(e)
            # 检查是否是权限错误
            if '权限' in error_msg or 'permission' in error_msg.lower() or '403' in error_msg or '401' in error_msg:
                print(f"Pro API权限不足，尝试使用旧API: {e}")
                try:
                    df = self.ts.get_today_data(code=code)
                    return df
                except Exception as e2:
                    print(f"使用旧API获取当日数据失败: {e2}")
                    return None
            else:
                print(f"获取当日数据失败: {e}")
                return None
    
    def save_data(self, data, file_name):
        """保存数据到本地"""
        try:
            # 确保data目录存在
            os.makedirs(DATA_PATH, exist_ok=True)
            # 保存数据
            data.to_csv(f'{DATA_PATH}/{file_name}.csv', index=False)
            print(f"数据保存成功: {file_name}.csv")
        except Exception as e:
            print(f"保存数据失败: {e}")
    
    def load_data(self, file_name):
        """从本地加载数据"""
        try:
            # 加载数据
            df = pd.read_csv(f'{DATA_PATH}/{file_name}.csv')
            return df
        except Exception as e:
            print(f"加载数据失败: {e}")
            return None
