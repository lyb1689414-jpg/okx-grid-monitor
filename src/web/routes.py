"""API 路由"""

from datetime import timedelta

from fastapi import APIRouter, Query
from fastapi.requests import Request
from sqlalchemy.orm import Session

from src.db.database import SessionLocal
from src.db.repository import (
    get_all_grids, get_active_grids, get_daily_stats, get_daily_stats_count,
    get_amplitude_data, get_tp_history, get_pairs_by_date,
)
from src.core.pair_engine import scan_and_pair, sync_grids_from_exchange
from src.core.statistics import compute_daily_stats
from src.core.profit import execute_all_tp_adjustments
from src.web.app import templates
from src.utils import sha_today, sha_now

router = APIRouter()


def _get_db() -> Session:
    db = SessionLocal()
    try:
        return db
    except Exception:
        db.close()
        raise


# ==================== 页面 ====================

@router.get("/")
async def index(request: Request):
    """仪表盘主页"""
    return templates.TemplateResponse("index.html", {"request": request})


# ==================== 仪表盘汇总 ====================

@router.get("/api/dashboard/summary")
def dashboard_summary():
    """仪表盘顶部汇总卡片"""
    db = _get_db()
    try:
        today = sha_today()
        grids = get_active_grids(db)

        total_pairs = 0
        total_amount = 0.0
        total_profit = 0.0
        total_input = 0.0

        for g in grids:
            from src.db.models import DailyStatistic
            stat = db.query(DailyStatistic).filter(
                DailyStatistic.algo_id == g.algo_id,
                DailyStatistic.stat_date == today,
            ).first()
            if stat:
                total_pairs += (stat.pair_count or 0)
                total_amount += (stat.pair_amount or 0)
                total_profit += (stat.pair_profit or 0)
            total_input += g.total_investment + (g.extra_margin or 0)

        # 获取账户可用余额
        avail_balance = 0.0
        from src.api.account import get_balance
        try:
            bal = get_balance()
            for d in bal.get("data", [{}])[0].get("details", []):
                if d.get("ccy") == "USDT":
                    avail_balance = float(d.get("availBal", 0) or 0)
                    break
        except Exception:
            avail_balance = 0.0

        return {
            "active_grids": len(grids),
            "today_pairs": total_pairs,
            "today_amount": round(total_amount, 2),
            "today_profit": round(total_profit, 2),
            "total_input": round(total_input, 2),
            "today_return_rate": round(total_profit / total_input * 100, 2) if total_input > 0 else 0,
            "avail_balance": round(avail_balance, 2),
            "update_time": sha_now().strftime("%Y-%m-%d %H:%M:%S"),
        }
    finally:
        db.close()


# ==================== 网格列表 ====================

@router.get("/api/grids")
def list_grids():
    """获取所有网格及其今日统计"""
    db = _get_db()
    try:
        today = sha_today()
        grids = get_all_grids(db)
        result = []
        for g in grids:
            # 从每日统计表读取今日数据
            from src.db.models import DailyStatistic
            stat = db.query(DailyStatistic).filter(
                DailyStatistic.algo_id == g.algo_id,
                DailyStatistic.stat_date == today,
            ).first()
            # 从 pair_records 获取今日配对金额
            from src.db.models import PairRecord
            today_pair_amount = db.query(PairRecord).filter(
                PairRecord.algo_id == g.algo_id,
                PairRecord.stat_date == today,
            ).all()
            pair_amount = sum(p.pair_amount or 0 for p in today_pair_amount)

            if stat:
                pair_count = stat.pair_count
                pair_profit = stat.pair_profit
            else:
                pair_count = 0
                pair_profit = 0
            return_rate = round(pair_profit / g.total_investment * 100, 2) if g.total_investment > 0 else 0

                # 累计配对
            from src.db.models import PairRecord
            total_pairs = db.query(PairRecord).filter(
                PairRecord.algo_id == g.algo_id
            ).count()

            result.append({
                "algo_id": g.algo_id,
                "inst_id": g.inst_id,
                "algo_ord_type": g.algo_ord_type or "grid",
                "status": g.status,
                "total_investment": g.total_investment,
                "total_input": g.total_investment + (g.extra_margin or 0),
                "total_equity": (g.eq or g.total_investment or 0),
                "min_px": g.min_px,
                "max_px": g.max_px,
                "grid_count": g.grid_count,
                "run_px": g.run_px,
                "float_profit": g.float_profit,
                "total_pnl": g.total_pnl,
                "pnl_ratio": g.pnl_ratio,
                "annualized_rate": g.annualized_rate,
                "sl_trigger_px": g.sl_trigger_px,
                "tp_trigger_px": g.tp_trigger_px,
                "tp_ratio": g.tp_ratio,
                "per_max_profit_rate": g.per_max_profit_rate,
                "per_min_profit_rate": g.per_min_profit_rate,
                "trade_num": g.trade_num,
                "arbitrage_num": g.arbitrage_num,
                "grid_profit": g.grid_profit,
                "lever": g.lever,
                "actual_lever": g.actual_lever,
                "liq_px": g.liq_px,
                "eq": g.eq,
                "ord_frozen": g.ord_frozen,
                "avail_eq": g.avail_eq,
                "extra_margin": g.extra_margin,
                "total_pairs": total_pairs,
                "today_pairs": pair_count,
                "today_amount": round(pair_amount, 2),
                "today_profit": round(pair_profit, 2),
                "today_return_rate": return_rate,
            })
        return result
    finally:
        db.close()


# ==================== 振幅图表 ====================

@router.get("/api/amplitude-chart")
def amplitude_chart(inst_id: str = Query(...),
                    begin_date: str = Query(None),
                    end_date: str = Query(None)):
    """获取振幅走势数据"""
    db = _get_db()
    try:
        if not begin_date:
            begin_date = (sha_now() - timedelta(days=30)).strftime("%Y-%m-%d")
        if not end_date:
            end_date = sha_today()
        return get_amplitude_data(db, inst_id, begin_date, end_date)
    finally:
        db.close()


# ==================== 历史统计 ====================

@router.get("/api/statistics")
def statistics(date: str = Query(None), page: int = Query(1), page_size: int = Query(20)):
    """获取每日统计（支持分页和日期筛选）"""
    db = _get_db()
    try:
        rows = get_daily_stats(db, stat_date=date, page=page, page_size=page_size)
        total = get_daily_stats_count(db, stat_date=date)
        return {
            "data": [
                {
                    "algo_id": r.algo_id,
                    "inst_id": r.inst_id,
                    "stat_date": r.stat_date,
                    "pair_count": r.pair_count,
                    "pair_amount": r.pair_amount,
                    "pair_profit": r.pair_profit,
                    "total_investment": r.total_investment,
                    "daily_return_rate": r.daily_return_rate,
                    "underlying_change_pct": r.underlying_change_pct,
                    "underlying_amplitude_pct": r.underlying_amplitude_pct,
                }
                for r in rows
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    finally:
        db.close()


# ==================== 网格详情 ====================

@router.get("/api/grids/{algo_id}/detail")
def grid_detail(algo_id: str):
    """获取单个网格详情"""
    from src.api.grid import get_grid_detail
    from src.db.repository import get_grid_by_algo_id
    db = _get_db()
    try:
        cfg = get_grid_by_algo_id(db, algo_id)
        algo_type = cfg.algo_ord_type if cfg else "grid"
        api_detail = get_grid_detail(algo_id, algo_type)
        today = sha_today()
        pairs = get_pairs_by_date(db, algo_id, today)
        return {
            "config": {
                "algo_id": cfg.algo_id if cfg else algo_id,
                "inst_id": cfg.inst_id if cfg else "",
                "total_investment": cfg.total_investment if cfg else 0,
                "status": cfg.status if cfg else "unknown",
            },
            "api_detail": api_detail.get("data", [{}])[0] if api_detail.get("data") else {},
            "today_pairs": len(pairs),
            "today_profit": round(sum(p.profit or 0 for p in pairs), 2),
        }
    finally:
        db.close()


# ==================== 止盈历史 ====================

@router.get("/api/take-profit-history")
def take_profit_history(algo_id: str = Query(None), page: int = Query(1)):
    """获取止盈修改历史"""
    db = _get_db()
    try:
        rows = get_tp_history(db, algo_id=algo_id, page=page)
        return [
            {
                "algo_id": r.algo_id,
                "inst_id": r.inst_id,
                "old_tp_amount": r.old_tp_amount,
                "new_tp_amount": r.new_tp_amount,
                "current_profit": r.current_profit,
                "total_investment": r.total_investment,
                "modified_at": r.modified_at,
            }
            for r in rows
        ]
    finally:
        db.close()


# ==================== 配对记录 ====================

@router.get("/api/pairs")
def pair_records(algo_id: str = Query(None), date: str = Query(None),
                 page: int = Query(1), page_size: int = Query(50)):
    """获取配对记录"""
    from src.db.models import PairRecord
    db = _get_db()
    try:
        query = db.query(PairRecord)
        if algo_id:
            query = query.filter(PairRecord.algo_id == algo_id)
        if date:
            query = query.filter(PairRecord.stat_date == date)
        total = query.count()
        rows = query.order_by(PairRecord.pair_time.desc()).offset(
            (page - 1) * page_size
        ).limit(page_size).all()
        return {
            "data": [
                {
                    "algo_id": r.algo_id,
                    "group_id": r.group_id,
                    "buy_price": r.buy_price,
                    "sell_price": r.sell_price,
                    "pair_amount": r.pair_amount,
                    "profit": r.profit,
                    "pair_time": r.pair_time,
                    "stat_date": r.stat_date,
                }
                for r in rows
            ],
            "total": total,
            "page": page,
        }
    finally:
        db.close()


# ==================== 管理接口 ====================

@router.post("/api/admin/trigger-stats")
def trigger_stats():
    """手动触发每日统计"""
    db = _get_db()
    try:
        today = sha_today()
        from src.db.models import GridConfig
        grids = db.query(GridConfig).filter(
            GridConfig.status.in_(["active", "stopped"])
        ).all()
        for g in grids:
            scan_and_pair(db, g.algo_id)
            compute_daily_stats(db, g.algo_id, today)
        return {"success": True, "grids_processed": len(grids)}
    finally:
        db.close()


@router.post("/api/admin/check-margin")
def trigger_margin_check():
    """手动触发保证金检查"""
    db = _get_db()
    try:
        from src.db.models import GridConfig
        grids = db.query(GridConfig).filter(GridConfig.status == "active",
                                            GridConfig.algo_ord_type == "contract_grid").all()
        results = []
        for g in grids:
            from src.core.margin_guard import check_and_add_margin
            r = check_and_add_margin(db, g.algo_id)
            if r:
                results.append(r)
        return {"checked": len(grids), "actions": results}
    finally:
        db.close()


# ==================== 报表 ====================

@router.get("/api/report/daily")
def daily_report(date: str = Query(None)):
    """日报"""
    from src.core.report import generate_daily_report
    db = _get_db()
    try:
        if not date:
            from datetime import timedelta
            date = (datetime.strptime(sha_today(), "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
        return generate_daily_report(db, date)
    finally:
        db.close()


@router.get("/api/report/weekly")
def weekly_report(end_date: str = Query(None)):
    """周报"""
    from src.core.report import generate_weekly_report
    db = _get_db()
    try:
        if not end_date:
            end_date = sha_today()
        return generate_weekly_report(db, end_date)
    finally:
        db.close()


# ==================== 保证金记录 ====================

@router.get("/api/margin-additions")
def margin_additions(algo_id: str = Query(None), page: int = Query(1)):
    """获取保证金追加记录"""
    db = _get_db()
    try:
        from src.db.models import MarginAddition
        query = db.query(MarginAddition)
        if algo_id:
            query = query.filter(MarginAddition.algo_id == algo_id)
        total = query.count()
        rows = query.order_by(MarginAddition.created_at.desc()).offset(
            (page - 1) * 20
        ).limit(20).all()
        return {
            "data": [{
                "algo_id": r.algo_id,
                "inst_id": r.inst_id,
                "old_liq_px": r.old_liq_px,
                "added_amount": r.added_amount,
                "available_before": r.available_before,
                "mark_px": r.mark_px,
                "created_at": r.created_at,
            } for r in rows],
            "total": total,
            "page": page,
        }
    finally:
        db.close()


@router.post("/api/admin/trigger-tp")
def trigger_tp():
    """手动触发止盈修改"""
    db = _get_db()
    try:
        results = execute_all_tp_adjustments(db)
        return results
    finally:
        db.close()


@router.post("/api/admin/sync-grids")
def trigger_sync():
    """手动触发网格同步"""
    db = _get_db()
    try:
        results = sync_grids_from_exchange(db)
        return {
            "success": len(results["errors"]) == 0,
            "synced": len(results["synced"]),
            "grids": results["synced"],
            "errors": results["errors"],
        }
    finally:
        db.close()


@router.post("/api/admin/set-extra-margin")
def set_extra_margin(data: dict):
    """手动设置网格额外保证金 {algo_id, amount}"""
    from src.db.repository import get_grid_by_algo_id
    db = _get_db()
    try:
        algo_id = data.get("algo_id", "")
        amount = float(data.get("amount", 0))
        cfg = get_grid_by_algo_id(db, algo_id)
        if not cfg:
            return {"success": False, "error": "网格不存在"}
        cfg.extra_margin = amount
        db.commit()
        return {"success": True, "algo_id": algo_id, "extra_margin": amount}
    finally:
        db.close()
