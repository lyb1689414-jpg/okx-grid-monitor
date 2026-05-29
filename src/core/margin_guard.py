"""保证金守护模块 —— 检测强平距离，自动追加保证金"""

import logging

from sqlalchemy.orm import Session

from src.api.grid import add_margin
from src.api.client import client
from src.db.models import MarginAddition

logger = logging.getLogger(__name__)

# 触发阈值：价格距强平价 ≤ 20%
TRIGGER_RATIO = 0.2
# 目标：强平价再降 10%
TARGET_LIQ_RATIO = 0.9


def _get_position_data(algo_id: str, algo_type: str = "contract_grid") -> dict | None:
    """获取网格持仓数据"""
    resp = client.get("/api/v5/tradingBot/grid/positions", {
        "algoId": algo_id,
        "algoOrdType": algo_type,
    })
    data = resp.get("data", [])
    if not data:
        return None
    return data[0]


def check_and_add_margin(db: Session, algo_id: str) -> dict | None:
    """
    检查强平距离，必要时自动追加保证金。
    返回操作结果字典，或 None 表示无需操作。
    """
    pos = _get_position_data(algo_id)
    if not pos:
        return None

    liq_px = float(pos.get("liqPx", 0) or 0)
    mark_px = float(pos.get("markPx", 0) or 0)
    notional = float(pos.get("notionalUsd", 0) or 0)
    inst_id = pos.get("instId", "")

    if liq_px <= 0 or mark_px <= 0 or notional <= 0:
        return None

    # 计算距强平百分比
    distance = (mark_px - liq_px) / mark_px
    if distance > TRIGGER_RATIO:
        return None  # 安全范围

    # 需要追加保证金
    target_liq = liq_px * TARGET_LIQ_RATIO
    delta_liq = liq_px - target_liq
    need_margin = delta_liq * notional / mark_px
    amt = round(max(need_margin, 0.01), 2)

    logger.warning(
        f"[保证金守护] 网格 {algo_id[:10]} 强平距离 {distance*100:.1f}% ≤ 触发线 {TRIGGER_RATIO*100}%"
    )
    logger.info(
        f"[保证金守护] 强平价 {liq_px} → 目标 {target_liq:.4f}，需追加 {amt} USDT"
    )

    # 获取追加前可用余额
    avail_before = 0.0
    try:
        bal = client.get("/api/v5/account/balance")
        for d in bal.get("data", [{}])[0].get("details", []):
            if d.get("ccy") == "USDT":
                avail_before = float(d.get("availBal", 0) or 0)
                break
    except Exception:
        pass

    if amt > avail_before:
        logger.error(f"[保证金守护] 可用余额 {avail_before} 不足，需 {amt}")
        return {
            "success": False,
            "error": f"可用余额不足: 需 {amt}, 可用 {avail_before}",
            "algo_id": algo_id,
        }

    # 调用 OKX API 追加保证金
    resp = add_margin(algo_id, str(amt))
    if resp.get("code") != "0":
        logger.error(f"[保证金守护] 追加失败: {resp}")
        return {
            "success": False,
            "error": resp.get("msg", "API失败"),
            "algo_id": algo_id,
        }

    # 记录
    record = MarginAddition(
        algo_id=algo_id,
        inst_id=inst_id,
        old_liq_px=round(liq_px, 6),
        new_liq_px=None,  # 下次同步更新
        added_amount=amt,
        available_before=round(avail_before, 2),
        mark_px=round(mark_px, 6),
    )
    db.add(record)
    db.commit()

    logger.info(f"[保证金守护] 成功追加 {amt} USDT")

    return {
        "success": True,
        "algo_id": algo_id,
        "inst_id": inst_id,
        "old_liq_px": liq_px,
        "target_liq": target_liq,
        "added_amount": amt,
        "distance_pct": round(distance * 100, 1),
    }
