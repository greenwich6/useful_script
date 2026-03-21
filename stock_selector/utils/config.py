# 配置文件

# tushare API密钥（如果需要）
TS_TOKEN = "796dbc9f64d2925d635499c2335baee309c84553c9a584071dfd17b2"

# 数据存储路径
DATA_PATH = "data"

# 缓存配置
CACHE_CONFIG = {
    "enabled": True,  # 是否启用缓存
    "stock_list_expire_days": 7,  # 股票列表缓存过期天数
    "stock_data_expire_days": 1,  # 股票数据缓存过期天数
}

# 回测配置
BACKTEST_CONFIG = {
    "start_date": "2023-01-01",
    "end_date": "2023-12-31",
    "initial_cash": 100000,
    "transaction_fee": 0.0003
}

# 选股策略配置
STRATEGY_CONFIG = {
    "min_price": 5,
    "max_price": 50,
    "min_volume": 1000000,
    "max_volatility": 5,
    "min_change": -3,
    "max_change": 3
}
