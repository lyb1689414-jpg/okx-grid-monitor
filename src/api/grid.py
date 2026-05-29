from src.api.client import client


def get_active_grids(algo_ord_type: str = "contract_grid") -> dict:
    """获取活跃的网格策略列表"""
    return client.get(
        "/api/v5/tradingBot/grid/orders-algo-pending",
        {"algoOrdType": algo_ord_type},
    )


def get_grid_history(algo_ord_type: str = "contract_grid",
                     after: str = "", before: str = "", limit: str = "100") -> dict:
    """获取网格策略历史"""
    params = {"algoOrdType": algo_ord_type, "limit": limit}
    if after:
        params["after"] = after
    if before:
        params["before"] = before
    return client.get("/api/v5/tradingBot/grid/orders-algo-history", params)


def get_grid_detail(algo_id: str, algo_ord_type: str = "contract_grid") -> dict:
    """获取网格策略详情"""
    return client.get(
        "/api/v5/tradingBot/grid/orders-algo-details",
        {"algoId": algo_id, "algoOrdType": algo_ord_type},
    )


def get_sub_orders(algo_id: str, algo_ord_type: str = "contract_grid",
                   state: str = "filled", before: str = "", after: str = "",
                   limit: str = "100") -> dict:
    """获取网格子订单列表"""
    # type 参数传子订单状态（filled/live/...），和 state 保持一致
    params = {
        "algoId": algo_id,
        "algoOrdType": algo_ord_type,
        "type": state,
        "state": state,
        "limit": limit,
    }
    if before:
        params["before"] = before
    if after:
        params["after"] = after
    return client.get("/api/v5/tradingBot/grid/sub-orders", params)


def get_all_sub_orders(algo_id: str, algo_ord_type: str = "contract_grid",
                       state: str = "filled", after: str = "") -> list:
    """分页获取所有子订单"""
    all_orders = []
    cursor = after
    while True:
        resp = get_sub_orders(
            algo_id=algo_id,
            algo_ord_type=algo_ord_type,
            state=state,
            after=cursor,
            limit="100",
        )
        orders = resp.get("data", [])
        if not orders:
            break
        all_orders.extend(orders)
        if len(orders) < 100:
            break
        cursor = orders[-1]["ordId"]
    return all_orders


def amend_grid(algo_id: str, inst_id: str, tp_ratio: str = "",
               sl_trigger_px: str = "", algo_ord_type: str = "contract_grid") -> dict:
    """修改网格策略（止盈止损）"""
    body = {
        "algoId": algo_id,
        "instId": inst_id,
        "algoOrdType": algo_ord_type,
    }
    if tp_ratio:
        body["tpRatio"] = tp_ratio
    if sl_trigger_px:
        body["slTriggerPx"] = sl_trigger_px
    return client.post("/api/v5/tradingBot/grid/amend-order-algo", body)


def add_margin(algo_id: str, amt: str) -> dict:
    """追加网格保证金"""
    return client.post("/api/v5/tradingBot/grid/margin-balance", {
        "algoId": algo_id,
        "type": "add",
        "amt": amt,
    })


def stop_grid(algo_id: str, inst_id: str,
              algo_ord_type: str = "contract_grid") -> dict:
    """停止网格策略"""
    return client.post("/api/v5/tradingBot/grid/stop-order-algo", {
        "algoId": algo_id,
        "instId": inst_id,
        "algoOrdType": algo_ord_type,
        "stopType": "1",
    })


def get_grid_positions(algo_id: str,
                       algo_ord_type: str = "contract_grid") -> dict:
    """查询合约网格持仓"""
    return client.get(
        "/api/v5/tradingBot/grid/positions",
        {"algoId": algo_id, "algoOrdType": algo_ord_type},
    )
