import tkinter as tk
from tkinter import ttk, messagebox
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import sys
import os.path

# 添加当前目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.data_fetcher import DataFetcher
from strategies.end_of_day_strategy import EndOfDayStrategy, VolumeSurgeStrategy
from backtest.backtest_engine import BacktestEngine

class StockSelectorUI:
    """尾盘选股工具界面"""
    
    def __init__(self, root):
        """初始化界面
        
        Args:
            root: 根窗口
        """
        self.root = root
        self.root.title("尾盘选股工具")
        self.root.geometry("1000x800")
        
        # 初始化数据获取器
        self.data_fetcher = DataFetcher()
        
        # 初始化策略
        self.strategies = {
            "尾盘选股策略": EndOfDayStrategy(),
            "成交量突增策略": VolumeSurgeStrategy()
        }
        
        # 创建主框架
        self.main_frame = ttk.Frame(self.root, padding="10")
        self.main_frame.pack(fill=tk.BOTH, expand=True)
        
        # 创建顶部控制面板
        self.control_frame = ttk.LabelFrame(self.main_frame, text="控制面板", padding="10")
        self.control_frame.pack(fill=tk.X, pady=5)
        
        # 策略选择
        ttk.Label(self.control_frame, text="选择策略:").grid(row=0, column=0, padx=5, pady=5, sticky=tk.W)
        self.strategy_var = tk.StringVar(value="尾盘选股策略")
        self.strategy_combobox = ttk.Combobox(self.control_frame, textvariable=self.strategy_var, values=list(self.strategies.keys()))
        self.strategy_combobox.grid(row=0, column=1, padx=5, pady=5, sticky=tk.W)
        
        # 选股按钮
        self.select_button = ttk.Button(self.control_frame, text="运行选股", command=self.run_selection)
        self.select_button.grid(row=0, column=2, padx=5, pady=5, sticky=tk.W)
        
        # 回测按钮
        self.backtest_button = ttk.Button(self.control_frame, text="运行回测", command=self.run_backtest)
        self.backtest_button.grid(row=0, column=3, padx=5, pady=5, sticky=tk.W)
        
        # 结果显示区域
        self.result_frame = ttk.LabelFrame(self.main_frame, text="选股结果", padding="10")
        self.result_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        # 创建结果表格
        self.result_tree = ttk.Treeview(self.result_frame)
        self.result_tree["columns"] = ("code", "name", "price", "change", "volume")
        
        # 设置列属性
        self.result_tree.column("#0", width=0, stretch=tk.NO)
        self.result_tree.column("code", width=100, anchor=tk.CENTER)
        self.result_tree.column("name", width=150, anchor=tk.CENTER)
        self.result_tree.column("price", width=100, anchor=tk.CENTER)
        self.result_tree.column("change", width=100, anchor=tk.CENTER)
        self.result_tree.column("volume", width=150, anchor=tk.CENTER)
        
        # 设置列标题
        self.result_tree.heading("code", text="股票代码")
        self.result_tree.heading("name", text="股票名称")
        self.result_tree.heading("price", text="价格")
        self.result_tree.heading("change", text="涨跌幅(%)")
        self.result_tree.heading("volume", text="成交量")
        
        # 添加滚动条
        self.scrollbar = ttk.Scrollbar(self.result_frame, orient=tk.VERTICAL, command=self.result_tree.yview)
        self.result_tree.configure(yscroll=self.scrollbar.set)
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.result_tree.pack(fill=tk.BOTH, expand=True)
        
        # 回测结果区域
        self.backtest_frame = ttk.LabelFrame(self.main_frame, text="回测结果", padding="10")
        self.backtest_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        # 回测指标显示
        self.metrics_frame = ttk.Frame(self.backtest_frame)
        self.metrics_frame.pack(fill=tk.X, pady=5)
        
        self.metrics_labels = {
            "total_return": ttk.Label(self.metrics_frame, text="总收益率: "),
            "annual_return": ttk.Label(self.metrics_frame, text="年化收益率: "),
            "max_drawdown": ttk.Label(self.metrics_frame, text="最大回撤: "),
            "sharpe_ratio": ttk.Label(self.metrics_frame, text="夏普比率: "),
            "final_value": ttk.Label(self.metrics_frame, text="最终资产: ")
        }
        
        for i, (key, label) in enumerate(self.metrics_labels.items()):
            label.grid(row=0, column=i*2, padx=10, pady=5, sticky=tk.W)
            self.metrics_labels[key] = label
        
        # 回测图表
        self.figure, self.ax = plt.subplots(figsize=(10, 4))
        self.canvas = FigureCanvasTkAgg(self.figure, master=self.backtest_frame)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
    
    def run_selection(self):
        """运行选股"""
        try:
            # 获取选择的策略
            strategy_name = self.strategy_var.get()
            strategy = self.strategies[strategy_name]
            
            # 获取股票列表
            stock_list = self.data_fetcher.get_stock_list()
            if stock_list is None:
                messagebox.showerror("错误", "获取股票列表失败")
                return
            
            # 运行选股
            selected_stocks = strategy.select_stocks(stock_list, self.data_fetcher)
            
            # 清空结果表格
            for item in self.result_tree.get_children():
                self.result_tree.delete(item)
            
            # 显示选股结果
            for stock in selected_stocks:
                self.result_tree.insert("", tk.END, values=(
                    stock['code'],
                    stock['name'],
                    stock['price'],
                    stock['change'],
                    stock['volume']
                ))
            
            messagebox.showinfo("成功", f"选股完成，共选中 {len(selected_stocks)} 只股票")
            
        except Exception as e:
            messagebox.showerror("错误", f"选股失败: {e}")
    
    def run_backtest(self):
        """运行回测"""
        try:
            # 获取选择的策略
            strategy_name = self.strategy_var.get()
            strategy = self.strategies[strategy_name]
            
            # 创建回测引擎
            backtest_engine = BacktestEngine(strategy, self.data_fetcher)
            
            # 运行回测
            backtest_results, metrics = backtest_engine.run_backtest()
            
            # 显示回测指标
            self.metrics_labels["total_return"].config(text=f"总收益率: {metrics['total_return']:.2f}%")
            self.metrics_labels["annual_return"].config(text=f"年化收益率: {metrics['annual_return']:.2f}%")
            self.metrics_labels["max_drawdown"].config(text=f"最大回撤: {metrics['max_drawdown']:.2f}%")
            self.metrics_labels["sharpe_ratio"].config(text=f"夏普比率: {metrics['sharpe_ratio']:.2f}")
            self.metrics_labels["final_value"].config(text=f"最终资产: {metrics['final_value']:.2f}")
            
            # 绘制回测曲线
            self.ax.clear()
            self.ax.plot(backtest_results['dates'], backtest_results['portfolio_value'])
            self.ax.set_title("回测结果")
            self.ax.set_xlabel("日期")
            self.ax.set_ylabel("资产价值")
            self.ax.grid(True)
            self.canvas.draw()
            
            messagebox.showinfo("成功", "回测完成")
            
        except Exception as e:
            messagebox.showerror("错误", f"回测失败: {e}")

def main():
    """主函数"""
    root = tk.Tk()
    app = StockSelectorUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()
