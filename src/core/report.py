"""日报 / 周报生成模块"""

from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func

from src.db.models import (
    GridConfig, DailyStatistic, PairRecord, MarginAddition,
)
from src.utils import sha_today


def _fmt(v, decimals=2):
    if v is None:
        return None
    return round(v, decimals)


def _get_prev_stats(db: Session, algo_id: str, prev_date: str) -> dict:
    """获取前一天配对数据用于环比（从 pair_records）"""
    prev = db.query(PairRecord).filter(
        PairRecord.algo_id == algo_id,
        PairRecord.stat_date == prev_date,
    ).all()
    if not prev:
        return {}
    return {
        "pair_count": len(prev),
        "pair_profit": _fmt(sum(p.pair_amount or 0 for p in prev)),
    }


def generate_daily_report(db: Session, date: str) -> dict:
    """生成某一天的日报"""
    # 前一天
    prev_dt = datetime.strptime(date, "%Y-%m-%d") - timedelta(days=1)
    prev_date = prev_dt.strftime("%Y-%m-%d")

    grids = db.query(GridConfig).filter(
        GridConfig.status.in_(["active", "stopped"])
    ).all()

    today_pairs_total = 0
    today_profit_total = 0.0
    today_amount_total = 0.0
    total_input = 0.0

    # 前一天数据（从 pair_records 统一来源）
    prev_pairs = db.query(PairRecord).filter(PairRecord.stat_date == prev_date).all()
    yesterday_pairs_total = len(prev_pairs)
    yesterday_profit_total = sum(p.pair_amount or 0 for p in prev_pairs)

    grid_details = []
    for g in grids:
        # 当日配对数据（从 pair_records）
        pairs = db.query(PairRecord).filter(
            PairRecord.algo_id == g.algo_id,
            PairRecord.stat_date == date,
        ).all()
        pair_amount = sum(p.pair_amount or 0 for p in pairs)
        pair_cnt = len(pairs)
        pair_profit = sum(p.profit or 0 for p in pairs)

        # 回报率 = 配对收益 / 总投入
        snap_total_input = g.total_investment + (g.extra_margin or 0)
        snap_total_investment = g.total_investment

        ret_rate = round(pair_profit / snap_total_input * 100, 4) if snap_total_input > 0 else 0

        # 从 K线实时获取行情
        from src.core.statistics import _fetch_daily_ohlc
        o, h, l, c = _fetch_daily_ohlc(g.inst_id, date)
        amp = round((h - l) / o * 100, 4) if o and h and l and o > 0 else None
        chg = round((c - o) / o * 100, 4) if o and c and o > 0 else None

        # 前一天数据
        prev = _get_prev_stats(db, g.algo_id, prev_date)

        today_pairs_total += pair_cnt
        today_profit_total += pair_profit
        today_amount_total += pair_amount
        total_input += snap_total_input

        liq_dist = None
        if g.liq_px and g.liq_px > 0 and g.run_px and g.run_px > 0:
            liq_dist = round((g.run_px - g.liq_px) / g.run_px * 100, 1)

        grid_details.append({
            "algo_id": g.algo_id,
            "inst_id": g.inst_id,
            "status": g.status,
            "pair_count": pair_cnt,
            "pair_count_prev": prev.get("pair_count"),
            "pair_amount": _fmt(pair_amount),
            "profit": _fmt(pair_profit),
            "profit_prev": prev.get("pair_profit"),
            "return_rate": _fmt(ret_rate),
            "return_rate_prev": None,  # 环比只看配对次数和收益
            "amplitude": _fmt(amp),
            "change_pct": _fmt(chg),
            "total_input": _fmt(snap_total_input),
            "initial_investment": _fmt(snap_total_investment),
            "extra_margin": _fmt(g.extra_margin),
            "tp_ratio": _fmt((g.tp_ratio or 0) * 100) if g.tp_ratio else None,
            "liq_px": g.liq_px,
            "liq_distance": liq_dist,
            "lever": g.lever,
        })

    # 振幅走势（最近7天，实时获取K线）
    amplitude_chart = []
    for i in range(6, -1, -1):
        d = datetime.strptime(date, "%Y-%m-%d") - timedelta(days=i)
        ds = d.strftime("%Y-%m-%d")
        from src.core.statistics import _fetch_daily_ohlc
        o, h, l, c = _fetch_daily_ohlc(grids[0].inst_id if grids else "BTC-USDT-SWAP", ds)
        amp_val = round((h - l) / o * 100, 4) if o and h and l and o > 0 else None
        chg_val = round((c - o) / o * 100, 4) if o and c and o > 0 else None
        amplitude_chart.append({
            "date": ds,
            "amplitude": _fmt(amp_val),
            "change_pct": _fmt(chg_val),
        })

    # 风控摘要
    margin_events = db.query(MarginAddition).filter(
        MarginAddition.created_at >= date + " 00:00:00",
        MarginAddition.created_at <= date + " 23:59:59",
    ).all()
    risk_summary = {
        "margin_add_count": len(margin_events),
        "margin_add_total": _fmt(sum(m.added_amount for m in margin_events)),
        "grids_at_risk": [
            {"algo_id": g["algo_id"][:10], "inst_id": g["inst_id"], "liq_distance": g["liq_distance"]}
            for g in grid_details if g["liq_distance"] is not None and g["liq_distance"] <= 30
        ],
    }

    # 环比
    return_rate_today = round(today_profit_total / total_input * 100, 2) if total_input > 0 else 0
    return_rate_yesterday = round(yesterday_profit_total / total_input * 100, 2) if total_input > 0 else 0

    return {
        "date": date,
        "summary": {
            "total_profit": _fmt(today_profit_total),
            "total_profit_change": _fmt(today_profit_total - yesterday_profit_total),
            "total_pairs": today_pairs_total,
            "total_pairs_change": today_pairs_total - yesterday_pairs_total,
            "total_amount": _fmt(today_amount_total),
            "total_input": _fmt(total_input),
            "return_rate": return_rate_today,
            "return_rate_change": _fmt(return_rate_today - return_rate_yesterday),
        },
        "grid_details": grid_details,
        "amplitude_chart": amplitude_chart,
        "risk_summary": risk_summary,
    }


def generate_weekly_report(db: Session, end_date: str) -> dict:
    """生成周报（end_date 所在的那一周，周一~周日）"""
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")
    # 找到本周一
    monday = end_dt - timedelta(days=end_dt.weekday())
    sunday = monday + timedelta(days=6)
    # 上周
    prev_monday = monday - timedelta(days=7)
    prev_sunday = monday - timedelta(days=1)

    week_start = monday.strftime("%Y-%m-%d")
    week_end = sunday.strftime("%Y-%m-%d")
    prev_start = prev_monday.strftime("%Y-%m-%d")
    prev_end = prev_sunday.strftime("%Y-%m-%d")

    # 本周每日统计（统一从 pair_records 读取）
    daily_summary = []
    d = monday
    week_pairs = 0
    week_profit = 0.0
    week_amount = 0.0
    while d <= sunday:
        ds = d.strftime("%Y-%m-%d")
        day_rows = db.query(PairRecord).filter(PairRecord.stat_date == ds).all()
        day_pairs = len(day_rows)
        day_profit = sum(p.pair_amount or 0 for p in day_rows)
        day_amount = day_profit  # 配对金额 = 配对收益

        week_pairs += day_pairs
        week_profit += day_profit
        week_amount += day_amount

        daily_summary.append({
            "date": ds,
            "weekday": ["一","二","三","四","五","六","日"][d.weekday()],
            "pair_count": day_pairs,
            "profit": _fmt(day_profit),
            "amount": _fmt(day_amount),
        })
        d += timedelta(days=1)

    # 上周汇总（用于环比）
    prev_rows = db.query(PairRecord).filter(
        PairRecord.stat_date >= prev_start,
        PairRecord.stat_date <= prev_end,
    ).all()
    prev_pairs = len(prev_rows)
    prev_profit = sum(p.pair_amount or 0 for p in prev_rows)

    # 各网格周汇总
    grid_week_summary = []
    for g in db.query(GridConfig).filter(
        GridConfig.status.in_(["active", "stopped"])
    ).all():
        week_rows = db.query(PairRecord).filter(
            PairRecord.algo_id == g.algo_id,
            PairRecord.stat_date >= week_start,
            PairRecord.stat_date <= week_end,
        ).all()
        total_pairs = len(week_rows)
        total_profit = sum(p.pair_amount or 0 for p in week_rows)

        # 找最佳/最差日
        day_map = {}
        for p in week_rows:
            day_map[p.stat_date] = day_map.get(p.stat_date, 0) + (p.pair_amount or 0)
        best_day = max(day_map, key=day_map.get) if day_map else None
        worst_day = min(day_map, key=day_map.get) if day_map else None
        days_count = len(set(p.stat_date for p in week_rows)) or 1

        grid_week_summary.append({
            "algo_id": g.algo_id,
            "inst_id": g.inst_id,
            "total_input": _fmt(g.total_investment + (g.extra_margin or 0)),
            "initial_investment": _fmt(g.total_investment),
            "total_pairs": total_pairs,
            "total_profit": _fmt(total_profit),
            "avg_return_rate": _fmt(total_profit / (g.total_investment + (g.extra_margin or 0)) * 100 / max(days_count, 1), 2),
            "best_day": best_day,
            "best_profit": _fmt(day_map.get(best_day, 0)) if best_day else None,
            "worst_day": worst_day,
            "worst_profit": _fmt(day_map.get(worst_day, 0)) if worst_day else None,
        })

    # 风控事件
    margin_events = db.query(MarginAddition).filter(
        MarginAddition.created_at >= week_start + " 00:00:00",
        MarginAddition.created_at <= week_end + " 23:59:59",
    ).all()

    # 本周振幅走势（实时获取K线）
    amplitude_chart = []
    d2 = monday
    all_grids = db.query(GridConfig).filter(
        GridConfig.status.in_(["active", "stopped"])
    ).all()
    inst = all_grids[0].inst_id if all_grids else "BTC-USDT-SWAP"
    while d2 <= sunday:
        ds = d2.strftime("%Y-%m-%d")
        from src.core.statistics import _fetch_daily_ohlc
        o, h, l, c = _fetch_daily_ohlc(inst, ds)
        amp_val = round((h - l) / o * 100, 4) if o and h and l and o > 0 else None
        chg_val = round((c - o) / o * 100, 4) if o and c and o > 0 else None
        amplitude_chart.append({
            "date": ds,
            "amplitude": _fmt(amp_val),
            "change_pct": _fmt(chg_val),
        })
        d2 += timedelta(days=1)

    return {
        "week_start": week_start,
        "week_end": week_end,
        "summary": {
            "total_pairs": week_pairs,
            "pairs_change": week_pairs - prev_pairs,
            "total_profit": _fmt(week_profit),
            "profit_change": _fmt(week_profit - prev_profit),
            "total_amount": _fmt(week_amount),
        },
        "daily_summary": daily_summary,
        "grid_week_summary": grid_week_summary,
        "margin_events": {
            "count": len(margin_events),
            "total_amount": _fmt(sum(m.added_amount for m in margin_events)),
        },
        "amplitude_chart": amplitude_chart,
        "prev_week": {
            "week_start": prev_start,
            "week_end": prev_end,
            "total_pairs": prev_pairs,
            "total_profit": _fmt(prev_profit),
        },
    }
