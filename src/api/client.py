import base64
import hashlib
import hmac
import time
import json
from datetime import datetime, timezone
from urllib.parse import urlencode

import httpx

from config.settings import settings


class OkxClient:
    def __init__(self):
        self.api_key = settings.okx_api_key
        self.secret_key = settings.okx_secret_key
        self.passphrase = settings.okx_passphrase
        self.base_url = settings.okx_base_url
        self.flag = settings.okx_flag
        self._rate_limit_window = 0.1
        self._last_request_time = 0

    def _get_timestamp(self) -> str:
        now = datetime.now(timezone.utc)
        return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"

    def _sign(self, timestamp: str, method: str, path: str, body: str = "") -> str:
        message = f"{timestamp}{method}{path}{body}"
        signature = hmac.new(
            self.secret_key.encode(),
            message.encode(),
            hashlib.sha256,
        ).digest()
        return base64.b64encode(signature).decode()

    def _get_headers(self, method: str, path: str, body: str = "") -> dict:
        timestamp = self._get_timestamp()
        sign = self._sign(timestamp, method, path, body)
        return {
            "OK-ACCESS-KEY": self.api_key,
            "OK-ACCESS-SIGN": sign,
            "OK-ACCESS-TIMESTAMP": timestamp,
            "OK-ACCESS-PASSPHRASE": self.passphrase,
            "Content-Type": "application/json",
            "x-simulated-trading": self.flag,
        }

    def _rate_limit(self):
        elapsed = time.time() - self._last_request_time
        if elapsed < self._rate_limit_window:
            time.sleep(self._rate_limit_window - elapsed)
        self._last_request_time = time.time()

    def _build_sign_path(self, path: str, method: str, params: dict = None) -> str:
        """构建签名用的完整路径，参数顺序需和 httpx 发送时一致"""
        if method == "GET" and params:
            return path + "?" + urlencode(list(params.items()))
        return path

    def _request(self, method: str, path: str, params: dict = None, body: dict = None) -> dict:
        body_str = ""
        if body:
            body_str = json.dumps(body, separators=(",", ":"))

        sign_path = self._build_sign_path(path, method, params)
        url = f"{self.base_url}{path}"
        headers = self._get_headers(method, sign_path, body_str)

        max_retries = 3
        for attempt in range(max_retries):
            try:
                self._rate_limit()
                if method == "GET":
                    resp = httpx.get(url, params=params, headers=headers)
                else:
                    resp = httpx.request(method, url, params=params, content=body_str, headers=headers)
                data = resp.json()
                if data.get("code") == "50011":
                    wait = 2 ** attempt
                    time.sleep(wait)
                    continue
                return data
            except httpx.RequestError:
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                raise

        return {"code": "-1", "msg": "Max retries exceeded"}

    def get(self, path: str, params: dict = None) -> dict:
        return self._request("GET", path, params=params)

    def post(self, path: str, body: dict) -> dict:
        return self._request("POST", path, body=body)


client = OkxClient()
