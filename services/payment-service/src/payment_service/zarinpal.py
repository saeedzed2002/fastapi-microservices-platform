from dataclasses import dataclass
from typing import Any

import httpx


class ZarinpalNotConfigured(RuntimeError):
    pass


class ZarinpalUnavailable(RuntimeError):
    """A transport or malformed-response failure for which no authority is trusted."""


class ZarinpalRejected(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class ZarinpalRequestResult:
    authority: str
    redirect_url: str


@dataclass(frozen=True)
class ZarinpalVerificationResult:
    succeeded: bool
    reference_id: str | None
    code: str


@dataclass(frozen=True)
class ZarinpalReverseResult:
    code: str


class ZarinpalClient:
    def __init__(
        self,
        *,
        merchant_id: str,
        sandbox: bool,
        callback_url: str,
        timeout_seconds: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._merchant_id = merchant_id.strip()
        self._sandbox = sandbox
        self._callback_url = callback_url
        self._timeout_seconds = timeout_seconds
        self._transport = transport

    @property
    def _api_base_url(self) -> str:
        return "https://sandbox.zarinpal.com" if self._sandbox else "https://payment.zarinpal.com"

    @property
    def _start_pay_base_url(self) -> str:
        return "https://sandbox.zarinpal.com" if self._sandbox else "https://www.zarinpal.com"

    def ensure_configured(self) -> None:
        if not self._merchant_id:
            raise ZarinpalNotConfigured

    async def create_payment(self, *, amount: int, description: str) -> ZarinpalRequestResult:
        payload = await self._post(
            "/pg/v4/payment/request.json",
            {
                "merchant_id": self._merchant_id,
                "amount": amount,
                "callback_url": self._callback_url,
                "description": description,
            },
        )
        data = _data_or_rejection(payload)
        authority = data.get("authority")
        if data.get("code") != 100 or not isinstance(authority, str) or not authority:
            raise ZarinpalRejected(_provider_code(data))
        return ZarinpalRequestResult(
            authority=authority,
            redirect_url=self.redirect_url(authority),
        )

    def redirect_url(self, authority: str) -> str:
        return f"{self._start_pay_base_url}/pg/StartPay/{authority}"

    async def verify_payment(self, *, amount: int, authority: str) -> ZarinpalVerificationResult:
        payload = await self._post(
            "/pg/v4/payment/verify.json",
            {"merchant_id": self._merchant_id, "amount": amount, "authority": authority},
        )
        data = _data_or_rejection(payload)
        code = _provider_code(data)
        reference_id = data.get("ref_id")
        return ZarinpalVerificationResult(
            succeeded=code in {"100", "101"} and reference_id is not None,
            reference_id=str(reference_id) if reference_id is not None else None,
            code=code,
        )

    async def reverse_payment(self, *, authority: str) -> ZarinpalReverseResult:
        """Reverse a successful payment during Zarinpal's short reversal window."""
        payload = await self._post(
            "/pg/v4/payment/reverse.json",
            {"merchant_id": self._merchant_id, "authority": authority},
        )
        data = _data_or_rejection(payload)
        code = _provider_code(data)
        if code != "100":
            raise ZarinpalRejected(code)
        return ZarinpalReverseResult(code=code)

    async def _post(self, path: str, payload: dict[str, object]) -> dict[str, Any]:
        self.ensure_configured()
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout_seconds,
                transport=self._transport,
                headers={"User-Agent": "fastapi-microservices-platform-payment-service"},
            ) as client:
                response = await client.post(f"{self._api_base_url}{path}", json=payload)
        except httpx.RequestError as exc:
            raise ZarinpalUnavailable("network_request_error") from exc
        if response.status_code >= 500:
            raise ZarinpalUnavailable("provider_http_5xx")
        try:
            decoded = response.json()
        except ValueError as exc:
            raise ZarinpalUnavailable("provider_invalid_json") from exc
        if not isinstance(decoded, dict):
            raise ZarinpalUnavailable("provider_invalid_response")
        if response.status_code >= 400:
            raise ZarinpalRejected(_error_code(decoded))
        return decoded


def _data_or_rejection(payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("data")
    if not isinstance(data, dict):
        raise ZarinpalRejected(_error_code(payload))
    return data


def _provider_code(data: dict[str, Any]) -> str:
    code = data.get("code")
    return str(code) if code is not None else "unknown"


def _error_code(payload: dict[str, Any]) -> str:
    errors = payload.get("errors")
    if isinstance(errors, dict):
        return _provider_code(errors)
    return "unknown"
