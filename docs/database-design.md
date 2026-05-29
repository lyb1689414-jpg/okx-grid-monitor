# 数据库设计

## 数据库类型
- 开发/测试: SQLite（文件: `data/okx_grid.db`）
- 生产环境: PostgreSQL（通过修改 `DATABASE_URL` 切换）

## 表结构

### 1. grid_configs — 网格配置表
| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | INTEGER | PK, AUTO | 自增ID |
| algo_id | TEXT(50) | UNIQUE, INDEX | OKX网格算法订单ID |
| inst_id | TEXT(30) | NOT NULL | 交易对，如 BTC-USDT-SWAP |
| total_investment | FLOAT | NOT NULL | 投入总金额(USDT) |
| take_profit_pct | FLOAT | DEFAULT 16.14 | 止盈比例(%) |
| status | TEXT(20) | DEFAULT 'active' | active/stopped/closed |
| created_at | TEXT | - | 创建时间 |
| updated_at | TEXT | - | 更新时间 |

### 2. daily_statistics — 每日统计表
| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | INTEGER | PK, AUTO | 自增ID |
| algo_id | TEXT(50) | NOT NULL, INDEX | 网格ID |
| inst_id | TEXT(30) | NOT NULL | 交易对 |
| stat_date | TEXT(10) | NOT NULL | 统计日期 |
| pair_count | INTEGER | DEFAULT 0 | 配对次数 |
| pair_amount | FLOAT | DEFAULT 0 | 配对金额 |
| pair_profit | FLOAT | DEFAULT 0 | 配对收益 |
| total_investment | FLOAT | DEFAULT 0 | 投入本金 |
| daily_return_rate | FLOAT | DEFAULT 0 | 回报率(%) |
| underlying_open | FLOAT | NULL | 标的开盘价 |
| underlying_high | FLOAT | NULL | 标的最高价 |
| underlying_low | FLOAT | NULL | 标的最低价 |
| underlying_close | FLOAT | NULL | 标的收盘价 |
| underlying_change_pct | FLOAT | NULL | 涨跌幅(%) |
| underlying_amplitude_pct | FLOAT | NULL | 振幅(%) |
| created_at | TEXT | - | 记录时间 |

**唯一约束**: (algo_id, stat_date)

### 3. pair_records — 配对记录表
| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | INTEGER | PK, AUTO | 自增ID |
| algo_id | TEXT(50) | NOT NULL, INDEX | 网格ID |
| group_id | TEXT(50) | NOT NULL | 网格档位ID |
| buy_ord_id | TEXT(50) | UNIQUE, NOT NULL | 买单ID |
| sell_ord_id | TEXT(50) | UNIQUE, NOT NULL | 卖单ID |
| buy_price | FLOAT | NULL | 买入成交价 |
| sell_price | FLOAT | NULL | 卖出成交价 |
| buy_amount | FLOAT | NULL | 买入数量 |
| sell_amount | FLOAT | NULL | 卖出数量 |
| pair_amount | FLOAT | NOT NULL | 配对金额 |
| profit | FLOAT | NULL | 配对收益 |
| pair_time | TEXT(30) | NOT NULL | 配对时间(卖单成交) |
| stat_date | TEXT(10) | NOT NULL, INDEX | 归属日期 |
| created_at | TEXT | - | 记录时间 |

### 4. take_profit_history — 止盈修改历史表
| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | INTEGER | PK, AUTO | 自增ID |
| algo_id | TEXT(50) | NOT NULL, INDEX | 网格ID |
| inst_id | TEXT(30) | NOT NULL | 交易对 |
| old_tp_amount | FLOAT | NULL | 旧止盈金额 |
| new_tp_amount | FLOAT | NOT NULL | 新止盈金额 |
| current_profit | FLOAT | NULL | 当时收益 |
| total_investment | FLOAT | NOT NULL | 投入本金 |
| modified_at | TEXT | - | 修改时间 |

### 5. sub_orders_tracked — 已处理子订单表（去重）
| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | INTEGER | PK, AUTO | 自增ID |
| algo_id | TEXT(50) | NOT NULL, INDEX | 网格ID |
| ord_id | TEXT(50) | UNIQUE, NOT NULL | OKX子订单ID |
| group_id | TEXT(50) | NOT NULL | 网格档位ID |
| side | TEXT(10) | NOT NULL | buy/sell |
| fill_sz | FLOAT | NULL | 成交数量 |
| fill_px | FLOAT | NULL | 成交价格 |
| state | TEXT(20) | NOT NULL | 订单状态 |
| u_time | TEXT(20) | NULL | 更新时间 |
| created_at | TEXT | - | 记录时间 |

**唯一约束**: (ord_id)

### 6. job_executions — 定时任务执行记录表
| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | INTEGER | PK, AUTO | 自增ID |
| job_name | TEXT(50) | NOT NULL | 任务名 |
| execution_date | TEXT(10) | NOT NULL | 执行日期 |
| status | TEXT(20) | NOT NULL | running/completed/failed |
| started_at | TEXT | NULL | 开始时间 |
| completed_at | TEXT | NULL | 完成时间 |
| error_message | TEXT | NULL | 错误信息 |

**唯一约束**: (job_name, execution_date)

## ER 关系

```
grid_configs (1) ──> (N) daily_statistics
grid_configs (1) ──> (N) pair_records
grid_configs (1) ──> (N) take_profit_history
grid_configs (1) ──> (N) sub_orders_tracked
```
