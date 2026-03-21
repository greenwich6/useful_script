import sys
import os.path

# 添加当前目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from strategies.base_strategy import BaseStrategy
from utils.config import STRATEGY_CONFIG
import pandas as pd

class EndOfDayStrategy(BaseStrategy):
    """尾盘选股策略"""
    
    def select_stocks(self, stock_list, data_fetcher):
        """选股方法
        
        Args:
            stock_list: 股票列表
            data_fetcher: 数据获取器
            
        Returns:
            选中的股票列表
        """
        selected_stocks = []
        
        # 遍历股票列表
        for index, row in stock_list.iterrows():
            try:
                # 获取股票代码
                if 'ts_code' in row:
                    code = row['ts_code']
                else:
                    code = row.name
                
                # 获取最近30天的股票数据
                end_date = pd.Timestamp.today().strftime('%Y%m%d')
                start_date = (pd.Timestamp.today() - pd.Timedelta(days=30)).strftime('%Y%m%d')
                df = data_fetcher.get_stock_data(code, start_date, end_date)
                
                if df is None or len(df) < 20:
                    continue
                
                # 计算技术指标
                df = self.calculate_indicators(df)
                
                # 获取最新数据
                latest = df.iloc[-1]
                
                # 应用选股条件
                if self._check_conditions(latest):
                    selected_stocks.append({
                        'code': code,
                        'name': row.get('name', code),
                        'price': latest['close'],
                        'change': latest['change'],
                        'volume': latest['volume']
                    })
                    
            except Exception as e:
                print(f"处理股票 {code} 时出错: {e}")
                continue
        
        # 按成交量排序
        selected_stocks.sort(key=lambda x: x['volume'], reverse=True)
        
        # 返回前20只股票
        return selected_stocks[:20]
    
    def _check_conditions(self, latest):
        """检查选股条件
        
        Args:
            latest: 最新的股票数据
            
        Returns:
            是否符合条件
        """
        # 价格范围
        if not (STRATEGY_CONFIG['min_price'] <= latest['close'] <= STRATEGY_CONFIG['max_price']):
            return False
        
        # 成交量
        if latest['volume'] < STRATEGY_CONFIG['min_volume']:
            return False
        
        # 涨跌幅
        if not (STRATEGY_CONFIG['min_change'] <= latest['change'] <= STRATEGY_CONFIG['max_change']):
            return False
        
        # 均线多头排列
        if not (latest['MA5'] > latest['MA10'] > latest['MA20']):
            return False
        
        # 成交量放大
        if not (latest['volume'] > latest['MA_VOL5'] * 1.2):
            return False
        
        return True

class VolumeSurgeStrategy(BaseStrategy):
    """成交量突增策略"""
    
    def select_stocks(self, stock_list, data_fetcher):
        """选股方法
        
        Args:
            stock_list: 股票列表
            data_fetcher: 数据获取器
            
        Returns:
            选中的股票列表
        """
        selected_stocks = []
        
        # 遍历股票列表
        for index, row in stock_list.iterrows():
            try:
                # 获取股票代码
                if 'ts_code' in row:
                    code = row['ts_code']
                else:
                    code = row.name
                
                # 获取最近10天的股票数据
                end_date = pd.Timestamp.today().strftime('%Y%m%d')
                start_date = (pd.Timestamp.today() - pd.Timedelta(days=10)).strftime('%Y%m%d')
                df = data_fetcher.get_stock_data(code, start_date, end_date)
                
                if df is None or len(df) < 5:
                    continue
                
                # 计算技术指标
                df = self.calculate_indicators(df)
                
                # 获取最新数据
                latest = df.iloc[-1]
                
                # 应用选股条件
                if self._check_conditions(df, latest):
                    selected_stocks.append({
                        'code': code,
                        'name': row.get('name', code),
                        'price': latest['close'],
                        'change': latest['change'],
                        'volume': latest['volume']
                    })
                    
            except Exception as e:
                print(f"处理股票 {code} 时出错: {e}")
                continue
        
        # 按成交量排序
        selected_stocks.sort(key=lambda x: x['volume'], reverse=True)
        
        # 返回前20只股票
        return selected_stocks[:20]
    
    def _check_conditions(self, df, latest):
        """检查选股条件
        
        Args:
            df: 股票数据
            latest: 最新的股票数据
            
        Returns:
            是否符合条件
        """
        # 价格范围
        if not (STRATEGY_CONFIG['min_price'] <= latest['close'] <= STRATEGY_CONFIG['max_price']):
            return False
        
        # 成交量突增（今日成交量是过去5天平均的3倍以上）
        if not (latest['volume'] > df['volume'].iloc[-6:-1].mean() * 3):
            return False
        
        # 价格上涨
        if latest['change'] <= 0:
            return False
        
        return True
