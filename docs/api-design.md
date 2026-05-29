# API 接口设计规范

## 后端 API 端点

### 页面
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/` | 仪表盘主页（HTML） |

### 仪表盘数据
| 方法 | 路径 | 参数 | 返回 |
|------|------|------|------|
| GET | `/api/dashboard/summary` | 无 | 汇总数据: 活跃网格数、今日配对次数/金额/收益、回报率 |

### 网格管理
| 方法 | 路径 | 参数 | 返回 |
|------|------|------|------|
| GET | `/api/grids` | 无 | 所有网格列表及今日统计 |
| GET | `/api/grids/{algo_id}/detail` | algo_id | 单网格详情（配置+API数据+今日统计） |

### 数据分析
| 方法 | 路径 | 参数 | 返回 |
|------|------|------|------|
| GET | `/api/statistics` | `date?`, `page?`, `page_size?` | 分页历史统计 |
| GET | `/api/amplitude-chart` | `inst_id`, `begin_date?`, `end_date?` | 振幅/涨跌幅/回报率时序数据 |
| GET | `/api/pairs` | `algo_id?`, `date?`, `page?`, `page_size?` | 分页配对明细 |

### 止盈记录
| 方法 | 路径 | 参数 | 返回 |
|------|------|------|------|
| GET | `/api/take-profit-history` | `algo_id?`, `page?` | 止盈修改历史 |

### 管理接口
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/admin/trigger-stats` | 手动触发每日统计 |
| POST | `/api/admin/trigger-tp` | 手动触发止盈修改 |
| POST | `/api/admin/sync-grids` | 手动触发网格同步 |

## OKX API 调用清单

### 公共接口（无需认证）
| 方法 | 端点 | 用途 |
|------|------|------|
| GET | `/api/v5/market/ticker` | 单一产品行情 |
| GET | `/api/v5/market/tickers` | 批量行情 |
| GET | `/api/v5/market/candles` | K线数据 |
| GET | `/api/v5/market/books` | 订单簿深度 |
| GET | `/api/v5/market/funding-rate` | 资金费率 |
| GET | `/api/v5/public/instruments` | 产品列表 |

### 私有接口（需认证）
| 方法 | 端点 | 用途 |
|------|------|------|
| GET | `/api/v5/account/balance` | 账户余额 |
| GET | `/api/v5/account/positions` | 持仓信息 |
| GET | `/api/v5/account/config` | 账户配置 |
| POST | `/api/v5/trade/order` | 下单 |
| GET | `/api/v5/tradingBot/grid/orders-algo-pending` | 活跃网格列表 |
| GET | `/api/v5/tradingBot/grid/orders-algo-details` | 网格详情 |
| GET | `/api/v5/tradingBot/grid/sub-orders` | 网格子订单 |
| POST | `/api/v5/tradingBot/grid/amend-order-algo` | 修改网格止盈 |

## 认证方式
- **签名算法**: HMAC-SHA256（参考 `src/api/client.py`）
- **请求头**: OK-ACCESS-KEY, OK-ACCESS-SIGN, OK-ACCESS-TIMESTAMP, OK-ACCESS-PASSPHRASE
- **限频**: 客户端内置 100ms 请求间隔 + 429 自动退避重试
