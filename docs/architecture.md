# 技术架构设计

## 整体架构

```
[浏览器]  <-->  [FastAPI 后端]  <-->  [欧易 OKX API]
                      |
                 [SQLite 数据库]
```

## 技术栈

| 组件 | 技术 | 版本 |
|------|------|------|
| Web 框架 | FastAPI | 0.110.0 |
| ASGI 服务器 | Uvicorn | 0.29.0 |
| 数据库 ORM | SQLAlchemy | 1.4.39 |
| 数据库 | SQLite（本地）→ PostgreSQL（云端） | - |
| HTTP 客户端 | httpx | 0.27.0 |
| 定时任务 | APScheduler | 3.11.2 |
| 配置管理 | pydantic-settings | 2.14.1 |
| YAML 解析 | PyYAML | 6.0 |
| 前端图表 | ECharts (CDN) | 5.5.0 |
| 前端样式 | Bootstrap (CDN) | 5.3.3 |
| Python 环境 | Anaconda Python 3.11.5 | - |

## 目录结构

```
合约网格自动监控/
├── config/                  # 配置层
│   ├── settings.py          # Pydantic 配置类，读取 .env
│   └── grid_config.yaml     # 网格列表和参数定义
├── src/
│   ├── api/                 # 外部接口层
│   │   ├── client.py        # OKX REST 客户端（签名/限频/重试）
│   │   ├── market.py        # 行情 API 封装
│   │   ├── grid.py          # 网格 API 封装
│   │   └── account.py       # 账户 API 封装
│   ├── core/                # 核心业务逻辑层
│   │   ├── pair_engine.py   # 配对识别引擎
│   │   ├── statistics.py    # 每日统计计算
│   │   └── profit.py        # 止盈修改逻辑
│   ├── db/                  # 数据持久层
│   │   ├── database.py      # 连接和会话管理
│   │   ├── models.py        # ORM 模型（6张表）
│   │   └── repository.py    # 数据访问封装
│   ├── scheduler/           # 调度层
│   │   └── jobs.py          # 定时任务定义
│   └── web/                 # Web 表示层
│       ├── app.py           # FastAPI 应用入口
│       ├── routes.py        # API 路由（10个端点）
│       └── templates/
│           └── index.html   # 单页面仪表盘
├── devlog/                  # 开发日志
├── docs/                    # 项目文档
├── data/                    # 数据库文件（.gitignore）
├── logs/                    # 日志文件（.gitignore）
├── .env                     # API密钥（.gitignore）
├── .env.example             # 密钥模板
├── requirements.txt         # Python 依赖
├── CLAUDE.md                # 项目指引
└── run.py                   # 启动入口
```

## 数据流

### 配对统计流程（23:59）
```
1. 遍历所有活跃/已停止网格
2. 调用 OKX API 获取子订单（sub-orders），分页全量拉取
3. 过滤已在 sub_orders_tracked 表中的订单
4. 按 groupId（网格档位）分组
5. 每组 FIFO 配对（买+卖 = 一次配对）
6. 配对日期 = 卖单成交日期（收益实现日）
7. 写入 pair_records + sub_orders_tracked
8. 汇总计算 daily_statistics
```

### 止盈修改流程（00:00）
```
1. 遍历所有活跃网格
2. 从 OKX API 获取网格当前收益
3. 计算新止盈 = 当前收益 + 投入 × 16.14%
4. 转换为止盈触发价
5. 调用 OKX amend API
6. 写入 take_profit_history
```

## 关键设计决策

1. **配对归属日期以卖单成交时间为准**: 因为只有在卖单成交时收益才真正实现
2. **SQLite 兼容**: 使用 SQLAlchemy 1.4 传统 Column 定义，适配 Anaconda 环境
3. **单线程调度器**: 23:59 和 0:00 两个任务不会冲突，共用 BackgroundScheduler
4. **去重机制**: 通过 sub_orders_tracked 表的 UNIQUE (ord_id) 约束防止重复配对
5. **幂等保证**: job_executions 表记录每次任务执行状态，防止重复执行
6. **轻量前端**: 无需 npm/webpack，CDN 引入 Bootstrap + ECharts，零构建
