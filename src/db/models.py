from datetime import datetime

from sqlalchemy import Column, String, Integer, Float, Text, UniqueConstraint
from sqlalchemy.orm import declarative_base

from src.db.database import Base


class GridConfig(Base):
    __tablename__ = "grid_configs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    algo_id = Column(String(50), unique=True, nullable=False, index=True)
    inst_id = Column(String(30), nullable=False)
    algo_ord_type = Column(String(20), default="grid")  # grid=现货网格, contract_grid=合约网格
    total_investment = Column(Float, nullable=False)
    min_px = Column(Float, nullable=True)
    max_px = Column(Float, nullable=True)
    grid_count = Column(Integer, nullable=True)
    run_px = Column(Float, nullable=True)           # 当前运行价格
    float_profit = Column(Float, nullable=True)      # 浮动盈亏
    total_pnl = Column(Float, nullable=True)         # 总盈亏
    pnl_ratio = Column(Float, nullable=True)          # 盈亏比率
    annualized_rate = Column(Float, nullable=True)    # 年化收益率
    sl_trigger_px = Column(Float, nullable=True)     # 止损触发价
    tp_trigger_px = Column(Float, nullable=True)     # 止盈触发价
    tp_ratio = Column(Float, nullable=True)            # 止盈收益率(小数)
    per_max_profit_rate = Column(Float, nullable=True)  # 每格最大利润率
    per_min_profit_rate = Column(Float, nullable=True)  # 每格最小利润率
    trade_num = Column(Integer, nullable=True)       # 成交笔数
    arbitrage_num = Column(Integer, nullable=True)   # 套利次数
    grid_profit = Column(Float, nullable=True)        # 网格收益
    lever = Column(Float, nullable=True)               # 杠杆倍数
    actual_lever = Column(Float, nullable=True)        # 实际杠杆
    liq_px = Column(Float, nullable=True)              # 预估强平价
    eq = Column(Float, nullable=True)                  # 账户权益
    ord_frozen = Column(Float, nullable=True)          # 冻结保证金
    avail_eq = Column(Float, nullable=True)            # 可用保证金
    extra_margin = Column(Float, nullable=True)        # 额外保证金（手动追加）
    base_arbitrage = Column(Integer, nullable=True)    # 昨日套利基数
    base_profit = Column(Float, nullable=True)         # 昨日网格收益基数
    take_profit_pct = Column(Float, default=16.14)
    status = Column(String(20), default="active")
    created_at = Column(String, default=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    updated_at = Column(String, default=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))


class PairRecord(Base):
    __tablename__ = "pair_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    algo_id = Column(String(50), nullable=False, index=True)
    group_id = Column(String(50), nullable=False)
    buy_ord_id = Column(String(50), unique=True, nullable=False)
    sell_ord_id = Column(String(50), unique=True, nullable=False)
    buy_price = Column(Float, nullable=True)
    sell_price = Column(Float, nullable=True)
    buy_amount = Column(Float, nullable=True)
    sell_amount = Column(Float, nullable=True)
    pair_amount = Column(Float, nullable=False)
    profit = Column(Float, nullable=True)
    pair_time = Column(String(30), nullable=False)
    stat_date = Column(String(10), nullable=False, index=True)
    created_at = Column(String, default=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))


class DailyStatistic(Base):
    __tablename__ = "daily_statistics"
    __table_args__ = (UniqueConstraint("algo_id", "stat_date", name="uq_algo_date"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    algo_id = Column(String(50), nullable=False, index=True)
    inst_id = Column(String(30), nullable=False)
    stat_date = Column(String(10), nullable=False)
    pair_count = Column(Integer, default=0)
    pair_amount = Column(Float, default=0.0)
    pair_profit = Column(Float, default=0.0)
    total_investment = Column(Float, default=0.0)
    daily_return_rate = Column(Float, default=0.0)
    open_arbitrage = Column(Integer, nullable=True)       # 当日开盘套利基数
    open_profit = Column(Float, nullable=True)             # 当日开盘收益基数
    underlying_open = Column(Float, nullable=True)
    underlying_high = Column(Float, nullable=True)
    underlying_low = Column(Float, nullable=True)
    underlying_close = Column(Float, nullable=True)
    underlying_change_pct = Column(Float, nullable=True)
    underlying_amplitude_pct = Column(Float, nullable=True)
    created_at = Column(String, default=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))


class TakeProfitHistory(Base):
    __tablename__ = "take_profit_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    algo_id = Column(String(50), nullable=False, index=True)
    inst_id = Column(String(30), nullable=False)
    old_tp_amount = Column(Float, nullable=True)
    new_tp_amount = Column(Float, nullable=False)
    current_profit = Column(Float, nullable=True)
    total_investment = Column(Float, nullable=False)
    modified_at = Column(String, default=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))


class SubOrderTracked(Base):
    __tablename__ = "sub_orders_tracked"

    id = Column(Integer, primary_key=True, autoincrement=True)
    algo_id = Column(String(50), nullable=False, index=True)
    ord_id = Column(String(50), unique=True, nullable=False)
    group_id = Column(String(50), nullable=False)
    side = Column(String(10), nullable=False)
    fill_sz = Column(Float, nullable=True)
    fill_px = Column(Float, nullable=True)
    state = Column(String(20), nullable=False)
    u_time = Column(String(20), nullable=True)
    created_at = Column(String, default=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))


class JobExecution(Base):
    __tablename__ = "job_executions"
    __table_args__ = (UniqueConstraint("job_name", "execution_date", name="uq_job_date"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_name = Column(String(50), nullable=False)
    execution_date = Column(String(10), nullable=False)
    status = Column(String(20), nullable=False, default="running")
    started_at = Column(String, nullable=True)
    completed_at = Column(String, nullable=True)
    error_message = Column(Text, nullable=True)


class MarginAddition(Base):
    __tablename__ = "margin_additions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    algo_id = Column(String(50), nullable=False, index=True)
    inst_id = Column(String(30), nullable=False)
    old_liq_px = Column(Float, nullable=True)
    new_liq_px = Column(Float, nullable=True)
    added_amount = Column(Float, nullable=False)
    available_before = Column(Float, nullable=True)
    mark_px = Column(Float, nullable=True)
    created_at = Column(String, default=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
