import pandas as pd
import numpy as np
import sys
import os.path

# 添加当前目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.config import BACKTEST_CONFIG

class BacktestEngine:
    """回测引擎"""
    
    def __init__(self, strategy, data_fetcher):
        """初始化回测引擎
        
        Args:
            strategy: 选股策略
            data_fetcher: 数据获取器
        """
        self.strategy = strategy
        self.data_fetcher = data_fetcher
        self.initial_cash = BACKTEST_CONFIG['initial_cash']
        self.transaction_fee = BACKTEST_CONFIG['transaction_fee']
        self.start_date = BACKTEST_CONFIG['start_date']
        self.end_date = BACKTEST_CONFIG['end_date']
        
    def run_backtest(self):
        """运行回测
        
        Returns:
            回测结果
        """
        # 初始化回测数据
        backtest_results = {
            'dates': [],
            'portfolio_value': [],
            'cash': [self.initial_cash],
            'holdings': {},
            'trades': []
        }
        
        # 生成回测日期列表
        dates = pd.date_range(start=self.start_date, end=self.end_date, freq='B')
        
        # 遍历每个交易日
        for i, date in enumerate(dates):
            date_str = date.strftime('%Y%m%d')
            print(f"回测日期: {date_str}")
            
            # 获取股票列表
            stock_list = self.data_fetcher.get_stock_list()
            if stock_list is None:
                continue
            
            # 使用策略选股
            selected_stocks = self.strategy.select_stocks(stock_list, self.data_fetcher)
            
            # 计算当前持仓价值
            current_value = self.calculate_portfolio_value(backtest_results['holdings'], date_str)
            
            # 更新回测结果
            backtest_results['dates'].append(date_str)
            backtest_results['portfolio_value'].append(current_value + backtest_results['cash'][-1])
            
            # 调仓
            if i > 0:
                self.rebalance_portfolio(backtest_results, selected_stocks, date_str)
        
        # 计算回测指标
        metrics = self.calculate_metrics(backtest_results)
        
        return backtest_results, metrics
    
    def calculate_portfolio_value(self, holdings, date_str):
        """计算投资组合价值
        
        Args:
            holdings: 持仓
            date_str: 日期
            
        Returns:
            投资组合价值
        """
        value = 0
        for code, shares in holdings.items():
            # 获取当日股票价格
            df = self.data_fetcher.get_stock_data(code, date_str, date_str)
            if df is not None and not df.empty:
                price = df.iloc[0]['close']
                value += price * shares
        return value
    
    def rebalance_portfolio(self, backtest_results, selected_stocks, date_str):
        """调仓
        
        Args:
            backtest_results: 回测结果
            selected_stocks: 选中的股票
            date_str: 日期
        """
        current_cash = backtest_results['cash'][-1]
        current_holdings = backtest_results['holdings'].copy()
        
        # 卖出不在选中列表中的股票
        for code in list(current_holdings.keys()):
            if not any(stock['code'] == code for stock in selected_stocks):
                # 获取当日股票价格
                df = self.data_fetcher.get_stock_data(code, date_str, date_str)
                if df is not None and not df.empty:
                    price = df.iloc[0]['close']
                    shares = current_holdings[code]
                    # 计算卖出金额
                    sell_amount = price * shares
                    # 扣除交易费用
                    sell_amount *= (1 - self.transaction_fee)
                    # 更新现金和持仓
                    current_cash += sell_amount
                    del current_holdings[code]
                    # 记录交易
                    backtest_results['trades'].append({
                        'date': date_str,
                        'code': code,
                        'type': 'sell',
                        'price': price,
                        'shares': shares,
                        'amount': sell_amount
                    })
        
        # 买入选中的股票
        if selected_stocks:
            # 计算每只股票的买入金额
            buy_amount_per_stock = current_cash / len(selected_stocks)
            
            for stock in selected_stocks:
                code = stock['code']
                # 获取当日股票价格
                df = self.data_fetcher.get_stock_data(code, date_str, date_str)
                if df is not None and not df.empty:
                    price = df.iloc[0]['close']
                    # 计算可购买的 shares
                    shares = int(buy_amount_per_stock / price)
                    # 计算实际买入金额
                    buy_amount = price * shares
                    # 扣除交易费用
                    buy_amount *= (1 + self.transaction_fee)
                    
                    if buy_amount <= current_cash:
                        # 更新现金和持仓
                        current_cash -= buy_amount
                        current_holdings[code] = shares
                        # 记录交易
                        backtest_results['trades'].append({
                            'date': date_str,
                            'code': code,
                            'type': 'buy',
                            'price': price,
                            'shares': shares,
                            'amount': buy_amount
                        })
        
        # 更新回测结果
        backtest_results['cash'].append(current_cash)
        backtest_results['holdings'] = current_holdings
    
    def calculate_metrics(self, backtest_results):
        """计算回测指标
        
        Args:
            backtest_results: 回测结果
            
        Returns:
            回测指标
        """
        portfolio_values = backtest_results['portfolio_value']
        
        # 计算收益率
        total_return = (portfolio_values[-1] - self.initial_cash) / self.initial_cash * 100
        
        # 计算年化收益率
        days = len(portfolio_values)
        annual_return = (pow(portfolio_values[-1] / self.initial_cash, 252 / days) - 1) * 100
        
        # 计算最大回撤
        max_drawdown = 0
        peak = portfolio_values[0]
        for value in portfolio_values:
            if value > peak:
                peak = value
            drawdown = (peak - value) / peak * 100
            if drawdown > max_drawdown:
                max_drawdown = drawdown
        
        # 计算夏普比率（假设无风险利率为3%）
        daily_returns = np.diff(portfolio_values) / portfolio_values[:-1]
        sharpe_ratio = (np.mean(daily_returns) - 0.03/252) / np.std(daily_returns) * np.sqrt(252)
        
        metrics = {
            'total_return': total_return,
            'annual_return': annual_return,
            'max_drawdown': max_drawdown,
            'sharpe_ratio': sharpe_ratio,
            'final_value': portfolio_values[-1]
        }
        
        return metrics
