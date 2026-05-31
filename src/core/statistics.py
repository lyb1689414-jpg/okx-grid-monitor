"""每日统计模块 —— 汇总配对数据并计算回报率、涨跌幅、振幅"""

import logging
from datetime import datetime

from sqlalchemy.orm import Session

from src.api.market import get_candles
from src.db.models import GridConfig, DailyStatistic
from src.db.repository import upsert_daily_stat, get_active_grids

logger = logging.getLogger(__name__)


def compute_daily_stats(db: Session, algo_id: str, stat_date: str) -> dict | None:
    """
    计算某个网格在某一天的完整统计。
    首次调用时记录当日开盘基数(open_arbitrage)，
    后续调用用当日基数算增量：今日配对 = 当前套利 - 开盘基数。
    """
    cfg = db.query(GridConfig).filter(GridConfig.algo_id == algo_id).first()
    if not cfg:
        logger.warning(f"网格 {algo_id} 未在本地配置中")
        return None

    # 查已有记录，获取今日开盘基数
    existing = db.query(DailyStatistic).filter(
        DailyStatistic.algo_id == algo_id,
        DailyStatistic.stat_date == stat_date,
    ).first()

    today_arb = (cfg.arbitrage_num or 0)
    today_gp = (cfg.grid_profit or 0)
    total_investment = cfg.total_investment

    exist_arb = existing.open_arbitrage if existing else None
    if exist_arb is not None:
        base_arb = exist_arb
        base_gp = existing.open_profit or 0
    else:
        base_arb = today_arb
        base_gp = today_gp

    today_pairs = max(0, today_arb - base_arb)
    today_profit = max(0, today_gp - base_gp)

    daily_return_rate = (today_profit / total_investment * 100) if total_investment > 0 else 0.0

    # 获取日K线行情数据
    o, h, l, c = _fetch_daily_ohlc(cfg.inst_id, stat_date)

    change_pct = ((c - o) / o * 100) if o and o > 0 else None
    amplitude_pct = ((h - l) / o * 100) if o and h and l and o > 0 else None

    stat_data = {
        "algo_id": algo_id,
        "inst_id": cfg.inst_id,
        "stat_date": stat_date,
        "liq_px": cfg.liq_px,
        "run_px": cfg.run_px,
        "pair_count": today_pairs,
        "pair_amount": 0.0,
        "pair_profit": round(today_profit, 8),
        "total_investment": total_investment,
        "daily_return_rate": round(daily_return_rate, 4),
    }

    # 首次创建时写入 OHLCV 和开盘基数; 更新时不覆盖已有的 OHLCV
    is_new = exist_arb is None
    if is_new or existing.underlying_open is None:
        stat_data.update({
            "underlying_open": o,
            "underlying_high": h,
            "underlying_low": l,
            "underlying_close": c,
            "underlying_change_pct": round(change_pct, 4) if change_pct is not None else None,
            "underlying_amplitude_pct": round(amplitude_pct, 4) if amplitude_pct is not None else None,
        })
    if is_new:
        stat_data["open_arbitrage"] = base_arb
        stat_data["open_profit"] = base_gp

    upsert_daily_stat(db, stat_data)
    return stat_data


def _fetch_daily_ohlc(inst_id: str, target_date: str) -> tuple:
    """
    获取某标的在某一天的开盘、最高、最低、收盘价。
    欧易K线返回格式: [ts, open, high, low, close, vol, ...]
    如当日K线未收盘（今天），用最近一根K线近似。
    """
    try:
        resp = get_candles(inst_id, bar="1D", limit="30")
        data = resp.get("data", [])
        if not data:
            return (None, None, None, None)

        exact = None
        latest = None
        for candle in data:
            ts_ms = int(candle[0])
            # OKX日K时间戳为UTC 0:00，代表前一日K线; 减1秒获取正确日期
            candle_date = datetime.utcfromtimestamp((ts_ms - 1000) / 1000).strftime("%Y-%m-%d")
            vals = (
                float(candle[1]),
                float(candle[2]),
                float(candle[3]),
                float(candle[4]),
            )
            if latest is None:
                latest = vals
            if candle_date == target_date:
                exact = vals

        # 只返回精确匹配的K线，不用近似值（防止今天没收盘却用了昨天的数据）
        return exact if exact else (None, None, None, None)
    except Exception as e:
        logger.error(f"获取 {inst_id} 的 {target_date} 日K线失败: {e}")
        return (None, None, None, None)


def compute_all_active_grids(db: Session, stat_date: str) -> list[dict]:
    """对所有活跃网格执行每日统计"""
    grids = get_active_grids(db)
    results = []
    for g in grids:
        result = compute_daily_stats(db, g.algo_id, stat_date)
        if result:
            results.append(result)
    return results
