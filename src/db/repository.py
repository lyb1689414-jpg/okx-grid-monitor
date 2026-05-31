from datetime import date
from sqlalchemy import func, and_
from sqlalchemy.orm import Session

from src.db.models import (
    GridConfig, PairRecord, DailyStatistic,
    TakeProfitHistory, SubOrderTracked, JobExecution,
)


# ==================== GridConfig ====================

def get_active_grids(db: Session) -> list[GridConfig]:
    return db.query(GridConfig).filter(GridConfig.status == "active").all()


def get_all_grids(db: Session) -> list[GridConfig]:
    return db.query(GridConfig).all()


def get_grid_by_algo_id(db: Session, algo_id: str) -> GridConfig | None:
    return db.query(GridConfig).filter(GridConfig.algo_id == algo_id).first()


def get_grid_by_inst_id(db: Session, inst_id: str) -> GridConfig | None:
    return db.query(GridConfig).filter(
        GridConfig.inst_id == inst_id, GridConfig.status == "active"
    ).first()


def upsert_grid_config(db: Session, algo_id: str, inst_id: str,
                       total_investment: float, algo_ord_type: str = "grid",
                       status: str = "active") -> GridConfig:
    cfg = get_grid_by_algo_id(db, algo_id)
    if cfg:
        cfg.status = status
        cfg.total_investment = total_investment
        cfg.algo_ord_type = algo_ord_type
    else:
        cfg = GridConfig(
            algo_id=algo_id, inst_id=inst_id,
            total_investment=total_investment, algo_ord_type=algo_ord_type,
            status=status,
        )
        db.add(cfg)
    db.commit()
    db.refresh(cfg)
    return cfg


def update_grid_status(db: Session, algo_id: str, status: str):
    cfg = get_grid_by_algo_id(db, algo_id)
    if cfg:
        cfg.status = status
        db.commit()


# ==================== PairRecord ====================

def is_order_tracked(db: Session, ord_id: str) -> bool:
    return db.query(SubOrderTracked).filter(
        SubOrderTracked.ord_id == ord_id
    ).first() is not None


def insert_pair(db: Session, pair_data: dict) -> PairRecord | None:
    existing = db.query(PairRecord).filter(
        (PairRecord.buy_ord_id == pair_data["buy_ord_id"])
        | (PairRecord.sell_ord_id == pair_data["sell_ord_id"])
    ).first()
    if existing:
        return None

    pair = PairRecord(**pair_data)
    db.add(pair)

    for side, ord_id in [("buy", pair_data["buy_ord_id"]), ("sell", pair_data["sell_ord_id"])]:
        tracked = SubOrderTracked(
            algo_id=pair_data["algo_id"],
            ord_id=ord_id,
            group_id=pair_data["group_id"],
            side=side,
            state="filled",
        )
        db.add(tracked)

    db.commit()
    db.refresh(pair)
    return pair


def get_pairs_by_date(db: Session, algo_id: str, stat_date: str) -> list[PairRecord]:
    return db.query(PairRecord).filter(
        PairRecord.algo_id == algo_id,
        PairRecord.stat_date == stat_date,
    ).all()


def get_today_pair_summary(db: Session, stat_date: str) -> dict:
    rows = db.query(
        PairRecord.algo_id,
        func.count(PairRecord.id).label("pair_count"),
        func.sum(PairRecord.pair_amount).label("total_amount"),
        func.sum(PairRecord.profit).label("total_profit"),
    ).filter(PairRecord.stat_date == stat_date).group_by(PairRecord.algo_id).all()

    result = {}
    for row in rows:
        result[row.algo_id] = {
            "pair_count": row.pair_count,
            "total_amount": row.total_amount or 0,
            "total_profit": row.total_profit or 0,
        }
    return result


# ==================== DailyStatistic ====================

def upsert_daily_stat(db: Session, stat_data: dict) -> DailyStatistic:
    existing = db.query(DailyStatistic).filter(
        DailyStatistic.algo_id == stat_data["algo_id"],
        DailyStatistic.stat_date == stat_data["stat_date"],
    ).first()

    if existing:
        for key, value in stat_data.items():
            setattr(existing, key, value)
        db.commit()
        db.refresh(existing)
        return existing
    else:
        stat = DailyStatistic(**stat_data)
        db.add(stat)
        db.commit()
        db.refresh(stat)
        return stat


def get_daily_stats(db: Session, stat_date: str = None, page: int = 1,
                    page_size: int = 20, algo_id: str = None) -> list[DailyStatistic]:
    query = db.query(DailyStatistic)
    if stat_date:
        query = query.filter(DailyStatistic.stat_date == stat_date)
    if algo_id:
        query = query.filter(DailyStatistic.algo_id == algo_id)
    query = query.order_by(DailyStatistic.stat_date.desc(), DailyStatistic.algo_id)
    return query.offset((page - 1) * page_size).limit(page_size).all()


def get_daily_stats_count(db: Session, stat_date: str = None, algo_id: str = None) -> int:
    query = db.query(DailyStatistic)
    if stat_date:
        query = query.filter(DailyStatistic.stat_date == stat_date)
    if algo_id:
        query = query.filter(DailyStatistic.algo_id == algo_id)
    return query.count()


def get_amplitude_data(db: Session, inst_id: str, begin_date: str,
                       end_date: str, algo_id: str = None) -> list[dict]:
    from src.db.models import PairRecord
    query = db.query(DailyStatistic).filter(
        DailyStatistic.inst_id == inst_id,
        DailyStatistic.stat_date >= begin_date,
        DailyStatistic.stat_date <= end_date,
    )
    if algo_id:
        query = query.filter(DailyStatistic.algo_id == algo_id)
    rows = query.order_by(DailyStatistic.stat_date.asc()).all()

    seen = set()
    result = []
    for r in rows:
        if r.stat_date not in seen:
            seen.add(r.stat_date)
            # 回报率从 pair_records 实时计算
            day_pairs = db.query(PairRecord).filter(
                PairRecord.algo_id == (algo_id or r.algo_id),
                PairRecord.stat_date == r.stat_date,
            ).all()
            pair_profit = sum(p.pair_amount or 0 for p in day_pairs)
            grid = db.query(GridConfig).filter(
                GridConfig.algo_id == (algo_id or r.algo_id)
            ).first()
            total_in = grid.total_investment + (grid.extra_margin or 0) if grid else 1
            ret_rate = round(pair_profit / total_in * 100, 4) if total_in > 0 else 0
            result.append({
                "date": r.stat_date,
                "amplitude": r.underlying_amplitude_pct,
                "change": r.underlying_change_pct,
                "return_rate": ret_rate,
            })
    return result


# ==================== TakeProfitHistory ====================

def insert_tp_history(db: Session, tp_data: dict) -> TakeProfitHistory:
    tp = TakeProfitHistory(**tp_data)
    db.add(tp)
    db.commit()
    db.refresh(tp)
    return tp


def get_tp_history(db: Session, algo_id: str = None, page: int = 1,
                   page_size: int = 20) -> list[TakeProfitHistory]:
    query = db.query(TakeProfitHistory)
    if algo_id:
        query = query.filter(TakeProfitHistory.algo_id == algo_id)
    query = query.order_by(TakeProfitHistory.modified_at.desc())
    return query.offset((page - 1) * page_size).limit(page_size).all()


# ==================== JobExecution ====================

def is_job_done(db: Session, job_name: str, exec_date: str) -> bool:
    return db.query(JobExecution).filter(
        JobExecution.job_name == job_name,
        JobExecution.execution_date == exec_date,
        JobExecution.status == "completed",
    ).first() is not None


def start_job(db: Session, job_name: str, exec_date: str) -> JobExecution:
    from datetime import datetime
    existing = db.query(JobExecution).filter(
        JobExecution.job_name == job_name,
        JobExecution.execution_date == exec_date,
    ).first()
    if existing:
        existing.status = "running"
        existing.started_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        existing.error_message = None
        db.commit()
        return existing
    job = JobExecution(
        job_name=job_name, execution_date=exec_date, status="running",
        started_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def complete_job(db: Session, job_name: str, exec_date: str):
    from datetime import datetime
    job = db.query(JobExecution).filter(
        JobExecution.job_name == job_name,
        JobExecution.execution_date == exec_date,
    ).first()
    if job:
        job.status = "completed"
        job.completed_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        db.commit()


def fail_job(db: Session, job_name: str, exec_date: str, error: str):
    from datetime import datetime
    job = db.query(JobExecution).filter(
        JobExecution.job_name == job_name,
        JobExecution.execution_date == exec_date,
    ).first()
    if job:
        job.status = "failed"
        job.error_message = error
        job.completed_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        db.commit()


# ==================== SubOrderTracked ====================

def get_last_tracked_time(db: Session, algo_id: str) -> str | None:
    last = db.query(SubOrderTracked).filter(
        SubOrderTracked.algo_id == algo_id
    ).order_by(SubOrderTracked.u_time.desc()).first()
    return last.u_time if last else None
