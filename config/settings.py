import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    okx_api_key: str = ""
    okx_secret_key: str = ""
    okx_passphrase: str = ""
    okx_base_url: str = "https://www.okx.com"
    okx_flag: str = "0"  # 0=实盘, 1=模拟盘
    database_url: str = "sqlite:///data/okx_grid.db"
    timezone: str = "Asia/Shanghai"
    take_profit_pct: float = 16.14
    feishu_webhook_url: str = ""

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
