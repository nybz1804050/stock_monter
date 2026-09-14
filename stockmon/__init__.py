# -*- coding: utf-8 -*-
"""stockmon —— A 股自选股实时行情监控工具包。

模块划分：
    quotes     行情数据结构与归一化
    datasource 行情数据源（东方财富 / 腾讯）与自动切换
    watchlist  自选股列表的读写与校验
    alerts     涨跌幅告警判定与落盘
    web        浏览器页面（Flask）
"""

__version__ = "0.2.0"
