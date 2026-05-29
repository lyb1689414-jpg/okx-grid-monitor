"""定时任务 —— 每日统计 + 止盈修改 + 网格同步"""

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from config.settings import settings
from src.db.database import SessionLocal
from src.db.repository import (
    is_job_done, start_job, complete_job, fail_job,
)
from src.core.pair_engine import scan_and_pair, sync_grids_from_exchange
from src.core.statistics import compute_all_active_grids
from src.core.profit import execute_all_tp_adjustments
from src.utils import sha_today

logger = logging.getLogger(__name__)

TZ = settings.timezone


def daily_stats_job():
    """每日23:59统计任务"""
    today = sha_today()
    job_name = "daily_stats"

    db = SessionLocal()
    try:
        if is_job_done(db, job_name, today):
            logger.info(f"[{job_name}] 今日统计已完成，跳过")
            return

        start_job(db, job_name, today)
        logger.info(f"[{job_name}] 开始每日统计: {today}")

        # 先扫描配对
        from src.db.models import GridConfig
        grids = db.query(GridConfig).filter(
            GridConfig.status.in_(["active", "stopped"])
        ).all()

        for g in grids:
            try:
                paired = scan_and_pair(db, g.algo_id)
                logger.info(f"[{job_name}] 网格 {g.algo_id}: 发现 {paired} 对新配对")
            except Exception as e:
                logger.error(f"[{job_name}] 网格 {g.algo_id} 扫描失败: {e}")

        # 计算所有活跃网格的统计
        results = compute_all_active_grids(db, today)
        logger.info(f"[{job_name}] 统计完成: {len(results)} 个网格")

        # 重新查询网格（避免内部 commit 导致的 stale 状态）
        grids = db.query(GridConfig).filter(
            GridConfig.status.in_(["active", "stopped"])
        ).all()
        for g in grids:
            g.base_arbitrage = g.arbitrage_num
            g.base_profit = g.grid_profit
        db.commit()
        logger.info(f"[{job_name}] 已保存基数: {len(grids)} 个网格")

        complete_job(db, job_name, today)
    except Exception as e:
        logger.error(f"[{job_name}] 执行失败: {e}")
        fail_job(db, job_name, today, str(e))
    finally:
        db.close()


def daily_take_profit_job():
    """每日00:00止盈修改任务"""
    today = sha_today()
    job_name = "daily_take_profit"

    db = SessionLocal()
    try:
        if is_job_done(db, job_name, today):
            logger.info(f"[{job_name}] 今日止盈已修改，跳过")
            return

        start_job(db, job_name, today)
        logger.info(f"[{job_name}] 开始止盈修改: {today}")

        results = execute_all_tp_adjustments(db)
        success_count = sum(1 for r in results if r.get("success"))
        logger.info(f"[{job_name}] 止盈修改完成: {success_count}/{len(results)} 成功")

        complete_job(db, job_name, today)
    except Exception as e:
        logger.error(f"[{job_name}] 执行失败: {e}")
        fail_job(db, job_name, today, str(e))
    finally:
        db.close()


def sync_grids_job():
    """每分钟同步网格状态 + 更新今日统计"""
    db = SessionLocal()
    try:
        results = sync_grids_from_exchange(db)
        synced = results.get("synced", [])
        errors = results.get("errors", [])
        if errors:
            logger.warning(f"网格同步有错误: {errors}")

        # 更新每日统计 + 扫描新配对
        today = sha_today()
        for g in synced:
            try:
                from src.core.pair_engine import scan_and_pair
                new_pairs = scan_and_pair(db, g["algo_id"])
                if new_pairs:
                    logger.info(f"网格 {g['algo_id'][:8]}: 发现 {new_pairs} 对新配对")
            except Exception as e:
                logger.error(f"配对扫描失败 {g['algo_id'][:8]}: {e}")

            try:
                from src.core.statistics import compute_daily_stats
                compute_daily_stats(db, g["algo_id"], today)
            except Exception as e:
                logger.error(f"统计更新失败 {g['algo_id'][:8]}: {e}")

            # 检查强平距离（仅合约网格）
            if g.get("algo_type") == "contract_grid":
                try:
                    from src.core.margin_guard import check_and_add_margin
                    result = check_and_add_margin(db, g["algo_id"])
                    if result:
                        logger.info(f"保证金守护: {result}")
                except Exception as e:
                    logger.error(f"保证金检查失败 {g['algo_id'][:8]}: {e}")

        if synced:
            logger.info(f"网格同步: {len(synced)} 个网格已更新")
    except Exception as e:
        logger.error(f"网格同步失败: {e}")
    finally:
        db.close()


def start_scheduler() -> BackgroundScheduler:
    """启动所有定时任务"""
    scheduler = BackgroundScheduler(timezone=TZ)

    # 每日统计 23:59
    scheduler.add_job(
        daily_stats_job,
        CronTrigger(hour=23, minute=59, timezone=TZ),
        id="daily_stats",
        name="每日配对统计",
        replace_existing=True,
    )

    # 每日止盈 00:00
    scheduler.add_job(
        daily_take_profit_job,
        CronTrigger(hour=0, minute=0, timezone=TZ),
        id="daily_take_profit",
        name="每日止盈修改",
        replace_existing=True,
    )

    # 网格同步 每5分钟
    scheduler.add_job(
        sync_grids_job,
        "interval",
        minutes=1,
        id="sync_grids",
        name="网格状态同步",
        replace_existing=True,
    )

    scheduler.start()
    logger.info("定时任务调度器已启动")
    return scheduler
