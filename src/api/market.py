from src.api.client import client


def get_ticker(inst_id: str) -> dict:
    """获取单一产品行情"""
    return client.get("/api/v5/market/ticker", {"instId": inst_id})


def get_tickers(inst_type: str = "SWAP") -> dict:
    """批量获取行情"""
    return client.get("/api/v5/market/tickers", {"instType": inst_type})


def get_candles(inst_id: str, bar: str = "1D", limit: str = "100",
                before: str = "", after: str = "") -> dict:
    """获取K线数据"""
    params = {"instId": inst_id, "bar": bar, "limit": limit}
    if before:
        params["before"] = before
    if after:
        params["after"] = after
    return client.get("/api/v5/market/candles", params)


def get_history_candles(inst_id: str, bar: str = "1D",
                        before: str = "", after: str = "", limit: str = "100") -> dict:
    """获取历史K线"""
    params = {"instId": inst_id, "bar": bar, "limit": limit}
    if before:
        params["before"] = before
    if after:
        params["after"] = after
    return client.get("/api/v5/market/history-candles", params)


def get_order_book(inst_id: str, sz: str = "25") -> dict:
    """获取订单簿深度"""
    return client.get("/api/v5/market/books", {"instId": inst_id, "sz": sz})


def get_funding_rate(inst_id: str) -> dict:
    """获取资金费率"""
    return client.get("/api/v5/market/funding-rate", {"instId": inst_id})


def get_instruments(inst_type: str = "SWAP") -> dict:
    """获取可交易产品列表"""
    return client.get("/api/v5/public/instruments", {"instType": inst_type})
