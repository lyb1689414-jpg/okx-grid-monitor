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
from src.core.feishu import send_daily_report, send_weekly_report
from src.utils import sha_today, sha_now

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


def feishu_report_job():
    """早上8点推送昨日日报到飞书"""
    today = sha_today()
    job_name = "feishu_report"
    db = SessionLocal()
    try:
        if is_job_done(db, job_name, today):
            logger.info(f"[{job_name}] 今日已推送，跳过")
            return

        start_job(db, job_name, today)

        from datetime import timedelta
        from src.core.report import generate_daily_report
        yesterday = (sha_now() - timedelta(days=1)).strftime("%Y-%m-%d")
        logger.info(f"[{job_name}] 开始生成 {yesterday} 日报...")
        report = generate_daily_report(db, yesterday)
        logger.info(f"[{job_name}] 日报生成完成，开始推送...")
        ok = send_daily_report(report)
        if ok:
            logger.info(f"[{job_name}] 推送成功: {yesterday}")
            complete_job(db, job_name, today)
        else:
            logger.error(f"[{job_name}] 推送失败: {yesterday}")
            fail_job(db, job_name, today, "webhook返回非200或URL为空")
    except Exception as e:
        logger.error(f"[{job_name}] 异常: {e}", exc_info=True)
        fail_job(db, job_name, today, str(e))
    finally:
        db.close()


def feishu_weekly_job():
    """每周一早上7点推送上周周报到飞书"""
    today = sha_today()
    job_name = "feishu_weekly"
    db = SessionLocal()
    try:
        if is_job_done(db, job_name, today):
            logger.info(f"[{job_name}] 今日已推送，跳过")
            return

        start_job(db, job_name, today)

        from datetime import timedelta
        from src.core.report import generate_weekly_report
        now = sha_now()
        last_sunday = now - timedelta(days=now.weekday() + 1)
        report = generate_weekly_report(db, last_sunday.strftime("%Y-%m-%d"))
        ok = send_weekly_report(report)
        if ok:
            logger.info(f"[{job_name}] 周报推送成功")
            complete_job(db, job_name, today)
        else:
            logger.error(f"[{job_name}] 周报推送失败")
            fail_job(db, job_name, today, "webhook返回非200或URL为空")
    except Exception as e:
        logger.error(f"[{job_name}] 周报异常: {e}", exc_info=True)
        fail_job(db, job_name, today, str(e))
    finally:
        db.close()


def db_backup_job():
    """每天备份数据库，保留最近7天"""
    import shutil, glob, os
    db_path = "/app/data/okx_grid.db"
    backup_dir = "/app/data/backups"
    os.makedirs(backup_dir, exist_ok=True)
    today = sha_today()
    backup_path = os.path.join(backup_dir, f"okx_grid_{today}.db")
    try:
        shutil.copy2(db_path, backup_path)
        logger.info(f"数据库备份完成: {backup_path}")
        # 删除7天前的备份
        from datetime import datetime, timedelta
        cutoff = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        for f in glob.glob(os.path.join(backup_dir, "okx_grid_*.db")):
            date_str = f.split("_")[-1].replace(".db", "")
            if date_str < cutoff:
                os.remove(f)
                logger.info(f"删除过期备份: {f}")
    except Exception as e:
        logger.error(f"数据库备份失败: {e}")


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

    # 飞书周报推送 每周一7:00
    scheduler.add_job(
        feishu_weekly_job,
        CronTrigger(day_of_week="mon", hour=7, minute=0, timezone=TZ),
        id="feishu_weekly",
        name="飞书周报推送",
        replace_existing=True,
    )

    # 飞书日报推送 每天8:00
    scheduler.add_job(
        feishu_report_job,
        CronTrigger(hour=8, minute=0, timezone=TZ),
        id="feishu_report",
        name="飞书日报推送",
        replace_existing=True,
    )

    # 数据库备份 每天 00:30
    scheduler.add_job(
        db_backup_job,
        CronTrigger(hour=0, minute=30, timezone=TZ),
        id="db_backup",
        name="数据库备份",
        replace_existing=True,
    )

    # 网格同步 每1分钟
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
