from abc import ABC, abstractmethod
import pandas as pd

class BaseStrategy(ABC):
    """策略基类"""
    
    @abstractmethod
    def select_stocks(self, stock_list, data_fetcher):
        """选股方法
        
        Args:
            stock_list: 股票列表
            data_fetcher: 数据获取器
            
        Returns:
            选中的股票列表
        """
        pass
    
    def calculate_indicators(self, df):
        """计算技术指标
        
        Args:
            df: 股票数据
            
        Returns:
            带有技术指标的DataFrame
        """
        # 计算简单移动平均线
        df['MA5'] = df['close'].rolling(window=5).mean()
        df['MA10'] = df['close'].rolling(window=10).mean()
        df['MA20'] = df['close'].rolling(window=20).mean()
        
        # 计算成交量移动平均线
        df['MA_VOL5'] = df['volume'].rolling(window=5).mean()
        df['MA_VOL10'] = df['volume'].rolling(window=10).mean()
        
        # 计算涨跌幅
        df['change'] = df['close'].pct_change() * 100
        
        return df
