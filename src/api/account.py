from src.api.client import client


def get_balance() -> dict:
    """获取账户余额"""
    return client.get("/api/v5/account/balance")


def get_positions(inst_type: str = "SWAP") -> dict:
    """获取持仓信息"""
    return client.get("/api/v5/account/positions", {"instType": inst_type})


def get_account_config() -> dict:
    """获取账户配置"""
    return client.get("/api/v5/account/config")
