"""
止盈修改模块
逻辑：
1. 从欧易获取网格当前已实现收益
2. 新止盈金额 = 已配对收益 + 总投入金额 × 止盈比例
3. 调用欧易 API 修改网格止盈金额
"""

import logging

from sqlalchemy.orm import Session

from src.api.grid import amend_grid, get_grid_detail
from src.db.models import GridConfig
from src.db.repository import insert_tp_history, get_active_grids, get_grid_by_algo_id

logger = logging.getLogger(__name__)


def _get_grid_type(db: Session, algo_id: str) -> str:
    """从数据库获取网格类型，默认为 grid"""
    cfg = get_grid_by_algo_id(db, algo_id)
    return cfg.algo_ord_type if cfg else "grid"


def get_grid_exchange_profit(db: Session, algo_id: str) -> float:
    """从欧易API获取已配对网格收益(gridProfit)"""
    algo_type = _get_grid_type(db, algo_id)
    resp = get_grid_detail(algo_id, algo_type)
    data = resp.get("data", [])
    if not data:
        return 0.0
    detail = data[0]
    return float(detail.get("gridProfit", 0) or 0)


def calculate_new_tp(db: Session, algo_id: str) -> dict:
    """
    计算新止盈金额
    止盈条件: 网格收益 + 总投入 × 止盈比例
    总投入 = 初始投入 + 额外保证金
    返回: {algo_id, inst_id, grid_profit, total_input, take_profit_pct, new_tp_amount}
    """
    from config.settings import settings

    cfg = db.query(GridConfig).filter(GridConfig.algo_id == algo_id).first()
    if not cfg:
        return {"error": f"网格 {algo_id} 未找到"}

    grid_profit = get_grid_exchange_profit(db, algo_id)
    total_input = cfg.total_investment + (cfg.extra_margin or 0)
    tp_pct = settings.take_profit_pct

    # 止盈点 = 网格收益 + 总投入 × 16.14%
    new_tp_amount = grid_profit + total_input * (tp_pct / 100.0)

    return {
        "algo_id": algo_id,
        "inst_id": cfg.inst_id,
        "grid_profit": round(grid_profit, 8),
        "total_input": total_input,
        "take_profit_pct": tp_pct,
        "new_tp_amount": round(new_tp_amount, 2),
    }


def execute_tp_adjustment(db: Session, algo_id: str) -> dict:
    """
    执行止盈修改：计算 → 调API → 记录
    返回结果字典
    """
    calc = calculate_new_tp(db, algo_id)
    if "error" in calc:
        logger.error(calc["error"])
        return calc

    inst_id = calc["inst_id"]
    new_amount = calc["new_tp_amount"]
    total_input = calc["total_input"]

    # 收益率 = 止盈金额 ÷ 初始投入（OKX 按初始投入算收益率）
    # OKX 的 tpRatio 用小数格式，如 0.164 表示 16.4%
    cfg = db.query(GridConfig).filter(GridConfig.algo_id == algo_id).first()
    tp_ratio = (new_amount / cfg.total_investment) if cfg and cfg.total_investment > 0 else 0
    tp_ratio_str = str(round(tp_ratio, 4))

    resp = amend_grid(
        algo_id=algo_id,
        inst_id=inst_id,
        tp_ratio=tp_ratio_str,
    )

    if resp.get("code") == "0":
        # 记录历史
        insert_tp_history(db, {
            "algo_id": algo_id,
            "inst_id": inst_id,
            "old_tp_amount": None,
            "new_tp_amount": new_amount,
            "current_profit": calc["grid_profit"],
            "total_investment": total_input,
        })
        logger.info(f"网格 {algo_id} 止盈修改成功: 收益率 {tp_ratio_str}% (止盈额 {new_amount} USD)")
        return {"success": True, "algo_id": algo_id, "new_tp_amount": new_amount,
                "tp_ratio": tp_ratio_str}
    else:
        logger.error(f"网格 {algo_id} 止盈修改失败: {resp}")
        return {"success": False, "algo_id": algo_id, "error": resp.get("msg", "未知错误")}


def execute_all_tp_adjustments(db: Session) -> list[dict]:
    """对所有活跃网格执行止盈修改"""
    grids = get_active_grids(db)
    results = []
    for g in grids:
        result = execute_tp_adjustment(db, g.algo_id)
        results.append(result)
    return results
