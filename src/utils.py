"""上海时间工具"""
from datetime import datetime, timezone, timedelta

SHA_TZ = timezone(timedelta(hours=8))

def sha_now() -> datetime:
    return datetime.now(SHA_TZ)

def sha_today() -> str:
    return sha_now().strftime("%Y-%m-%d")
