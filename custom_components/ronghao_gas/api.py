"""Client for the Ronghao Gas web API."""

from __future__ import annotations

import asyncio
import base64
from dataclasses import dataclass
from datetime import timedelta
import json
from typing import Any

from aiohttp import ClientError, ClientSession
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from homeassistant.util import dt as dt_util


class RonghaoGasApiError(Exception):
    """Base API error."""


class RonghaoGasAuthError(RonghaoGasApiError):
    """Raised when the API reports an authentication failure."""


class RonghaoGasAesKeyError(RonghaoGasApiError):
    """Raised when the configured AES key is invalid."""


@dataclass(frozen=True)
class RonghaoGasConfig:
    """Connection settings for Ronghao Gas."""

    api_base_url: str
    bearer_token: str
    aes_key: str
    user_id: str
    userfiles_id: str
    userinfo_id: str
    timeout: int = 30


class RonghaoGasApi:
    """Small async API client based on the original Node-RED flow."""

    def __init__(self, session: ClientSession, config: RonghaoGasConfig) -> None:
        """Initialize the API client."""
        self._session = session
        self._config = config
        self._base_url = config.api_base_url.rstrip("/")

    async def async_validate(self) -> dict[str, Any]:
        """Fetch data once and ensure the configured account returns a meter."""
        data = await self.async_fetch_all()
        if not data.get("meter"):
            raise RonghaoGasApiError("No gas meter data returned")
        return data

    async def async_fetch_all(self) -> dict[str, Any]:
        """Fetch all data groups used by Home Assistant sensors."""
        meter_result, sell_list, hand_plan = await asyncio.gather(
            self.async_fetch_meter(),
            self.async_fetch_sell_list(),
            self.async_fetch_hand_plan(),
        )

        meter = _first(meter_result)
        user_info = await self.async_fetch_user_info(meter) if meter else {}

        return {
            "user_info": user_info if isinstance(user_info, dict) else {},
            "meter": meter if isinstance(meter, dict) else {},
            "sell_list": _as_list(sell_list),
            "hand_plan": _as_list(hand_plan),
            "updated_at": dt_util.now().isoformat(timespec="seconds"),
        }

    async def async_fetch_meter(self) -> Any:
        """Fetch gas meter data."""
        return await self._post_encrypted(
            "/rs/logic/searchUserMeter",
            {"condition": f"f_userinfo_id = {self._config.userinfo_id}"},
        )

    async def async_fetch_sell_list(self) -> Any:
        """Fetch purchase records."""
        return await self._post_encrypted(
            "/rs/sql/searchUserSellDetailToNew?pageNo=1&pageSize=50",
            {
                "data": {
                    "f_user_id": str(self._config.user_id),
                    "f_userfiles_id": str(self._config.userfiles_id),
                    "startDate": "2020-01-01 00:00:00",
                }
            },
        )

    async def async_fetch_hand_plan(self) -> Any:
        """Fetch meter reading / usage records."""
        now = dt_util.now()
        start = now - timedelta(days=365)
        return await self._post_encrypted(
            "/rs/sql/searchUserHandPlanDetailToNew?pageNo=1&pageSize=400",
            {
                "data": {
                    "f_user_id": str(self._config.user_id),
                    "startDate": start.strftime("%Y-%m-%d 00:00:00"),
                    "endDate": now.strftime("%Y-%m-%d 23:59:59"),
                }
            },
        )

    async def async_fetch_user_info(self, meter: dict[str, Any]) -> Any:
        """Fetch account/user information using the meter archive object."""
        return await self._post_encrypted("/rs/logic/queryUserInformation", meter)

    async def _post_encrypted(self, path: str, payload: dict[str, Any]) -> Any:
        """POST an AES-wrapped payload and decrypt the response."""
        body = self._encrypt_payload(payload)
        headers = {
            "Content-Type": "application/json;charset=UTF-8",
            "Authorization": f"Bearer {self._config.bearer_token}",
            "Origin": "http://www.rhwxsf.com",
            "Referer": "http://www.rhwxsf.com/ronghao/index.html",
        }
        url = f"{self._base_url}{path}"

        try:
            async with asyncio.timeout(self._config.timeout):
                async with self._session.post(url, data=body, headers=headers) as response:
                    text = await response.text()
                    if response.status in (401, 403):
                        raise RonghaoGasAuthError(f"HTTP {response.status}: {text[:160]}")
                    if response.status >= 400:
                        raise RonghaoGasApiError(f"HTTP {response.status}: {text[:160]}")
        except TimeoutError as err:
            raise RonghaoGasApiError("Timed out connecting to Ronghao Gas") from err
        except ClientError as err:
            raise RonghaoGasApiError(f"Connection error: {err}") from err

        return self._decrypt_response(text)

    def _encrypt_payload(self, payload: dict[str, Any]) -> str:
        """Return the encrypted request JSON expected by the API."""
        key = self._aes_key()
        plaintext = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
        padder = padding.PKCS7(algorithms.AES.block_size).padder()
        padded = padder.update(plaintext) + padder.finalize()
        cipher = Cipher(algorithms.AES(key), modes.ECB())
        encryptor = cipher.encryptor()
        encrypted = encryptor.update(padded) + encryptor.finalize()
        return json.dumps(
            {"aoteEncrypt": "AES", "data": base64.b64encode(encrypted).decode()},
            separators=(",", ":"),
        )

    def _decrypt_response(self, text: str) -> Any:
        """Decrypt an API response that is either raw base64 or JSON-wrapped."""
        stripped = text.strip()
        if not stripped:
            raise RonghaoGasApiError("Empty response from Ronghao Gas")
        if stripped.startswith(("RequestError", "Internal Server Error")):
            raise RonghaoGasApiError(stripped[:160])

        if stripped[0] in "[{":
            try:
                outer = json.loads(stripped)
            except json.JSONDecodeError as err:
                raise RonghaoGasApiError(f"Invalid JSON response: {err}") from err
            if not isinstance(outer, dict) or not isinstance(outer.get("data"), str):
                raise RonghaoGasApiError("Encrypted response JSON has no data field")
            b64_data = outer["data"]
        else:
            b64_data = stripped

        try:
            ciphertext = base64.b64decode(b64_data)
            cipher = Cipher(algorithms.AES(self._aes_key()), modes.ECB())
            decryptor = cipher.decryptor()
            padded = decryptor.update(ciphertext) + decryptor.finalize()
            unpadder = padding.PKCS7(algorithms.AES.block_size).unpadder()
            plaintext = unpadder.update(padded) + unpadder.finalize()
            return json.loads(plaintext.decode("utf-8"))
        except (ValueError, json.JSONDecodeError) as err:
            raise RonghaoGasApiError(f"Failed to decrypt Ronghao Gas response: {err}") from err

    def _aes_key(self) -> bytes:
        """Return the AES key as bytes, validating Node.js-compatible length."""
        key = self._config.aes_key.encode("utf-8")
        if len(key) != 16:
            raise RonghaoGasAesKeyError("AES-128 key must be exactly 16 bytes")
        return key


def _first(value: Any) -> Any:
    """Return the first item of a list, otherwise the value itself."""
    if isinstance(value, list):
        return value[0] if value else {}
    return value


def _as_list(value: Any) -> list[Any]:
    """Return value as a list."""
    return value if isinstance(value, list) else []
