"""飞书推送模块"""

import logging
import httpx

from config.settings import settings

logger = logging.getLogger(__name__)

WEBHOOK_URL = settings.feishu_webhook_url


def _fmt(v, decimals=2):
    if v is None:
        return "0"
    return str(round(v, decimals))


def send_weekly_report(report: dict) -> bool:
    """推送周报到飞书"""
    if not WEBHOOK_URL:
        return False

    from src.utils import sha_now
    ws = report.get("week_start", "")
    we = report.get("week_end", "")
    s = report.get("summary", {})

    lines = [f"📊 周报 {ws} ~ {we}", f"发送时间: {sha_now().strftime('%Y-%m-%d %H:%M:%S')}", ""]
    lines.append(f"总配对: {s.get('total_pairs', 0)} 次")
    lines.append(f"总收益: ${_fmt(s.get('total_profit', 0))}")
    lines.append(f"总配对金额: ${_fmt(s.get('total_amount', 0))}")

    lines.append("")
    lines.append("━━━━ 每日概况 ━━━━")
    for day in report.get("daily_summary", []):
        lines.append(f"  {day['date']} {day['weekday']} | 配对{day['pair_count']}次 | 收益${_fmt(day.get('profit',0))} | 金额${_fmt(day.get('amount',0))}")

    lines.append("")
    lines.append("━━━━ 各网格周汇总 ━━━━")
    for g in report.get("grid_week_summary", []):
        lines.append(f"▪ {g['inst_id']} | 配对{g['total_pairs']}次 | 收益${_fmt(g.get('total_profit',0))} | 日均回报率{g.get('avg_return_rate',0)}%")
        if g.get('best_day'):
            lines.append(f"  最佳: {g['best_day']} ${_fmt(g.get('best_profit',0))}")

    margin = report.get("margin_events", {})
    if margin.get("count", 0) > 0:
        lines.append(f"\n保证金追加: {margin['count']}次, ${_fmt(margin.get('total_amount', 0))}")

    body = {"msg_type": "text", "content": {"text": "\n".join(lines)}}
    try:
        resp = httpx.post(WEBHOOK_URL, json=body, timeout=10)
        logger.info(f"飞书响应: status={resp.status_code}, body={resp.text[:200]}")
        if resp.status_code == 200:
            logger.info(f"周报推送飞书成功: {ws}~{we}")
            return True
        else:
            logger.error(f"周报推送失败: status={resp.status_code}, body={resp.text}")
    except Exception as e:
        logger.error(f"周报推送异常: {e}")
    return False


def send_daily_report(report: dict) -> bool:
    """推送昨日日报到飞书"""
    if not WEBHOOK_URL:
        return False

    from src.utils import sha_now
    s = report.get("summary", {})
    date = report.get("date", "")

    lines = [f"📊 日报 {date}", f"发送时间: {sha_now().strftime('%Y-%m-%d %H:%M:%S')}", ""]
    lines.append(f"总配对收益: ${_fmt(s.get('total_profit'))}")
    lines.append(f"总配对次数: {s.get('total_pairs', 0)} 次")

    lines.append("")
    lines.append("━━━━ 各网格明细 ━━━━")

    for g in report.get("grid_details", []):
        algo = g.get("algo_id", "")[:10]
        total_in = _fmt(g.get("total_input", 0))
        init_in = _fmt(g.get("initial_investment", 0))
        pairs = g.get("pair_count", 0)
        profit = _fmt(g.get("profit", 0))
        rate = g.get("return_rate", 0)

        lines.append("")
        lines.append(f"▪ {algo}... {g['inst_id']}")
        lines.append(f"  总投入: ${total_in} (初始 ${init_in})")
        lines.append(f"  配对: {pairs} 次 | 收益: ${profit} | 回报率: {rate}%")

    body = {"msg_type": "text", "content": {"text": "\n".join(lines)}}
    try:
        resp = httpx.post(WEBHOOK_URL, json=body, timeout=10)
        logger.info(f"飞书响应: status={resp.status_code}, body={resp.text[:200]}")
        if resp.status_code == 200:
            logger.info(f"日报推送飞书成功: {date}")
            return True
        else:
            logger.error(f"飞书推送失败: status={resp.status_code}, body={resp.text}")
    except Exception as e:
        logger.error(f"飞书推送异常: {e}")
    return False
