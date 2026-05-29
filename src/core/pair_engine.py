"""
配对计算引擎 —— 核心算法

逻辑：
1. 从欧易API获取网格的所有已成交子订单
2. 按 groupId（网格档位）分组
3. 每组内：买入和卖出按时间 FIFO 顺序配对
4. 每对买卖算一次配对，配对时间 = 卖单成交时间
5. 存入 pair_records，去重用 sub_orders_tracked
"""

from datetime import datetime, timezone, timedelta

from sqlalchemy.orm import Session

from src.api.grid import get_sub_orders, get_active_grids, get_grid_detail
from src.db.repository import (
    is_order_tracked, insert_pair, get_last_tracked_time,
)


def fetch_recent_sub_orders(algo_id: str, algo_ord_type: str = "grid",
                            after_time: str = "") -> list[dict]:
    """分页获取某个网格在指定时间之后的所有新成交子订单"""
    all_orders = []
    cursor = ""
    while True:
        resp = get_sub_orders(
            algo_id=algo_id,
            algo_ord_type=algo_ord_type,
            state="filled",
            after=cursor,
            limit="100",
        )
        data = resp.get("data", [])
        if not data:
            break
        # 如果设置了时间过滤，只保留该时间之后的
        if after_time:
            filtered = [o for o in data if o.get("uTime", "0") > after_time]
            if not filtered:
                break
            all_orders.extend(filtered)
            if len(filtered) < len(data):
                break
        else:
            all_orders.extend(data)

        if len(data) < 100:
            break
        cursor = data[-1]["ordId"]
    return all_orders


def scan_and_pair(db: Session, algo_id: str,
                  start_time: str = "", end_time: str = "") -> int:
    """
    扫描指定网格的最新成交子订单，识别配对并存入数据库。
    返回新发现的配对数量。

    start_time / end_time: OKX API 的毫秒时间戳格式字符串
    """
    # 查网格类型（现货/合约）
    from src.db.repository import get_grid_by_algo_id
    cfg = get_grid_by_algo_id(db, algo_id)
    algo_type = cfg.algo_ord_type if cfg else "grid"

    # 获取上次扫描的截止时间
    last_time = get_last_tracked_time(db, algo_id)
    filter_time = last_time or start_time

    # 获取新成交的子订单
    orders = fetch_recent_sub_orders(algo_id, algo_type, after_time=filter_time)

    if not orders:
        return 0

    # 按 groupId 分组
    grouped: dict[str, dict[str, list]] = {}
    for order in orders:
        ord_id = order["ordId"]
        if is_order_tracked(db, ord_id):
            continue
        group_id = order.get("groupId", order.get("gridId", ""))
        if group_id not in grouped:
            grouped[group_id] = {"buy": [], "sell": []}
        side = order.get("side", "")
        if side in grouped[group_id]:
            grouped[group_id][side].append(order)

    new_pairs = 0

    for group_id, sides in grouped.items():
        buys = sorted(sides["buy"], key=lambda o: o.get("uTime", o.get("cTime", "0")))
        sells = sorted(sides["sell"], key=lambda o: o.get("uTime", o.get("cTime", "0")))

        # FIFO 配对
        pair_count = min(len(buys), len(sells))
        for i in range(pair_count):
            buy = buys[i]
            sell = sells[i]

            buy_px = float(buy.get("avgPx", 0) or buy.get("px", 0))
            sell_px = float(sell.get("avgPx", 0) or sell.get("px", 0))
            buy_sz = float(buy.get("accFillSz", 0) or buy.get("sz", 0))
            sell_sz = float(sell.get("accFillSz", 0) or sell.get("sz", 0))

            # 配对收益 = (卖价-买价) × 数量 × 合约乘数 + 手续费（USDT保证金合约）
            ct_val = float(buy.get("ctVal", 0) or sell.get("ctVal", 0) or 1)
            buy_fee = float(buy.get("fee", 0) or 0)
            sell_fee = float(sell.get("fee", 0) or 0)
            profit = (sell_px - buy_px) * buy_sz * ct_val + buy_fee + sell_fee
            pair_amount = profit  # 配对金额 = 已配对收益（含手续费）

            # 配对时间 = 卖单成交时间（收益实现的那一刻）
            sell_time_ms = sell.get("uTime", sell.get("cTime", "0"))
            try:
                pair_dt = datetime.fromtimestamp(int(sell_time_ms) / 1000, tz=timezone(timedelta(hours=8)))
                pair_time = pair_dt.strftime("%Y-%m-%d %H:%M:%S")
                stat_date = pair_dt.strftime("%Y-%m-%d")
            except (ValueError, OSError):
                pair_time = sell_time_ms
                stat_date = datetime.now().strftime("%Y-%m-%d")

            pair_data = {
                "algo_id": algo_id,
                "group_id": group_id,
                "buy_ord_id": buy["ordId"],
                "sell_ord_id": sell["ordId"],
                "buy_price": buy_px,
                "sell_price": sell_px,
                "buy_amount": buy_sz,
                "sell_amount": sell_sz,
                "pair_amount": round(pair_amount, 8),
                "profit": round(profit, 8),
                "pair_time": pair_time,
                "stat_date": stat_date,
            }
            result = insert_pair(db, pair_data)
            if result:
                new_pairs += 1

    return new_pairs


def sync_grids_from_exchange(db: Session) -> dict:
    """
    从欧易获取活跃网格列表（同时查现货和合约网格），同步到本地数据库。
    返回 {synced: [...], errors: [...]}
    """
    from src.db.repository import upsert_grid_config

    synced = []
    errors = []

    # 同时查询现货网格(grid)和合约网格(contract_grid)
    for algo_type in ["grid", "contract_grid"]:
        resp = get_active_grids(algo_type)
        code = resp.get("code", "")
        msg = resp.get("msg", "")

        if code != "0":
            errors.append(f"{algo_type}: code={code}, msg={msg}")
            continue

        data = resp.get("data", [])
        if not data:
            continue

        for g in data:
            algo_id = g["algoId"]
            inst_id = g["instId"]

            # 从列表数据获取基础信息
            sz = float(g.get("sz", 0) or 0)

            detail = get_grid_detail(algo_id, algo_type)
            detail_data = detail.get("data", [{}])[0] if detail.get("data") else {}

            # 投入金额优先级: detail.investment > detail.quoteSz > detail.sz > pending.sz
            investment = (
                float(detail_data.get("investment", 0) or 0)
                or float(detail_data.get("quoteSz", 0) or 0)
                or float(detail_data.get("sz", 0) or 0)
                or sz
            )

            px_lower = float(detail_data.get("minPx", 0) or 0)
            px_upper = float(detail_data.get("maxPx", 0) or 0)
            grid_count = int(detail_data.get("gridNum", 0) or 0)
            ctime = detail_data.get("cTime", "")  # 网格创建时间毫秒戳
            run_px = float(detail_data.get("runPx", 0) or 0)
            float_profit = float(detail_data.get("floatProfit", 0) or 0)
            total_pnl = float(detail_data.get("totalPnl", 0) or 0)
            pnl_ratio = float(detail_data.get("pnlRatio", 0) or 0)
            annualized = float(detail_data.get("totalAnnualizedRate", 0) or 0)
            sl_px = float(detail_data.get("slTriggerPx", 0) or 0)
            trade_num = int(detail_data.get("tradeNum", 0) or 0)
            per_max = float(detail_data.get("perMaxProfitRate", 0) or 0)
            per_min = float(detail_data.get("perMinProfitRate", 0) or 0)
            arbitrage_num = int(detail_data.get("arbitrageNum", 0) or 0)
            grid_profit = float(detail_data.get("gridProfit", 0) or 0)
            lever = float(detail_data.get("lever", 0) or 0)
            actual_lever = float(detail_data.get("actualLever", 0) or 0)
            liq_px = float(detail_data.get("liqPx", 0) or 0)
            eq = float(detail_data.get("eq", 0) or 0)
            ord_frozen = float(detail_data.get("ordFrozen", 0) or 0)
            avail_eq = float(detail_data.get("availEq", 0) or 0)

            # 从 tpslTriggerParam 中提取止盈触发价
            tp_px = 0.0
            tp_ratio = float(detail_data.get("tpRatio", 0) or 0)
            tpsl = detail_data.get("tpslTriggerParam", {})
            if isinstance(tpsl, dict):
                triggers = tpsl.get("triggers", [])
                for t in triggers:
                    if t.get("type") == "tp":
                        try:
                            tp_px = float(t.get("value", 0) or 0)
                        except (ValueError, TypeError):
                            pass
                        break

            cfg = upsert_grid_config(db, algo_id, inst_id, investment, algo_type)

            # 更新网格参数
            cfg.min_px = px_lower
            cfg.max_px = px_upper
            cfg.grid_count = grid_count
            cfg.run_px = run_px
            cfg.float_profit = float_profit
            cfg.total_pnl = total_pnl
            cfg.pnl_ratio = pnl_ratio
            cfg.annualized_rate = annualized
            cfg.sl_trigger_px = sl_px
            cfg.tp_trigger_px = tp_px
            cfg.tp_ratio = tp_ratio
            cfg.per_max_profit_rate = per_max
            cfg.per_min_profit_rate = per_min
            cfg.trade_num = trade_num
            # 首次同步：初始化今日基数
            if cfg.base_arbitrage is None:
                cfg.base_arbitrage = arbitrage_num
            if cfg.base_profit is None:
                cfg.base_profit = grid_profit
            cfg.arbitrage_num = arbitrage_num
            cfg.grid_profit = grid_profit
            cfg.lever = lever
            cfg.actual_lever = actual_lever
            cfg.liq_px = liq_px
            cfg.eq = eq
            cfg.ord_frozen = ord_frozen
            cfg.avail_eq = avail_eq
            # 自动计算额外保证金: 权益 - 初始投入 - 累计盈亏（追加保证金时权益涨但盈亏不涨）
            extra = eq - investment - total_pnl
            if extra > 0 and (cfg.extra_margin is None or extra > cfg.extra_margin * 0.5):
                cfg.extra_margin = round(extra, 2)
            cfg.ctime = ctime
            db.commit()

            synced.append({
                "algo_id": algo_id,
                "inst_id": inst_id,
                "algo_type": algo_type,
                "status": cfg.status,
                "min_px": px_lower,
                "max_px": px_upper,
                "grid_count": grid_count,
                "investment": investment,
                "run_px": run_px,
                "float_profit": float_profit,
                "total_pnl": total_pnl,
                "pnl_ratio": pnl_ratio,
                "annualized_rate": annualized,
                "sl_trigger_px": sl_px,
                "tp_trigger_px": tp_px,
                "tp_ratio": tp_ratio,
                "per_max_profit_rate": per_max,
                "per_min_profit_rate": per_min,
                "trade_num": trade_num,
                "arbitrage_num": arbitrage_num,
                "grid_profit": grid_profit,
                "lever": lever,
                "actual_lever": actual_lever,
                "liq_px": liq_px,
                "eq": eq,
                "ord_frozen": ord_frozen,
                "avail_eq": avail_eq,
                "extra_margin": cfg.extra_margin,
            })

    return {"synced": synced, "errors": errors}
