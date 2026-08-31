from dataclasses import dataclass

import httpx


class ZibalNotConfigured(RuntimeError):
    pass


class ZibalUnavailable(RuntimeError):
    pass


class ZibalRejected(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class ZibalRequestResult:
    track_id: str
    redirect_url: str


@dataclass(frozen=True)
class ZibalVerificationResult:
    succeeded: bool
    code: str


class ZibalClient:
    """Narrow adapter for Zibal's documented request and verification API.

    The adapter deliberately uses the workspace-locked HTTPX runtime instead
    of introducing an unreviewed provider SDK. The provider's ``trackId`` is
    stored in Payment's existing opaque ``authority`` field; that field is a
    local browser-return token, not a Zarinpal-specific database contract.
    """

    _base_url = "https://gateway.zibal.ir/v1"

    def __init__(
        self,
        *,
        merchant_id: str,
        callback_url: str,
        timeout_seconds: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._merchant_id = merchant_id
        self._callback_url = callback_url
        self._timeout_seconds = timeout_seconds
        self._transport = transport

    def ensure_configured(self) -> None:
        if not self._merchant_id.strip():
            raise ZibalNotConfigured

    def redirect_url(self, track_id: str) -> str:
        return f"{self._base_url}/start/{track_id}"

    async def create_payment(self, *, amount: int, description: str) -> ZibalRequestResult:
        self.ensure_configured()
        payload = {
            "merchant": self._merchant_id,
            "callbackUrl": self._callback_url,
            "amount": amount,
            "description": description,
        }
        response = await self._post("request", payload)
        result = _result_code(response)
        track_id = response.get("trackId")
        if result != "100":
            raise ZibalRejected(result)
        if not isinstance(track_id, (int, str)) or not str(track_id):
            raise ZibalUnavailable("provider_invalid_response")
        normalized_track_id = str(track_id)
        return ZibalRequestResult(
            track_id=normalized_track_id,
            redirect_url=self.redirect_url(normalized_track_id),
        )

    async def verify_payment(self, *, amount: int, track_id: str) -> ZibalVerificationResult:
        del amount  # Zibal verifies its persisted transaction by track ID.
        self.ensure_configured()
        response = await self._post(
            "verify", {"merchant": self._merchant_id, "trackId": _track_id_value(track_id)}
        )
        result = _result_code(response)
        provider_status = response.get("status")
        succeeded = result in {"100", "201"} and (provider_status in (1, "1") or result == "201")
        return ZibalVerificationResult(succeeded=succeeded, code=result)

    async def _post(self, path: str, payload: dict[str, object]) -> dict[str, object]:
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout_seconds, transport=self._transport
            ) as client:
                response = await client.post(f"{self._base_url}/{path}", json=payload)
        except httpx.RequestError as exc:
            raise ZibalUnavailable("network_request_error") from exc
        if response.status_code >= 500:
            raise ZibalUnavailable("provider_http_5xx")
        try:
            decoded = response.json()
        except ValueError as exc:
            raise ZibalUnavailable("provider_invalid_json") from exc
        if not isinstance(decoded, dict):
            raise ZibalUnavailable("provider_invalid_response")
        if response.status_code >= 400:
            raise ZibalRejected(_result_code(decoded))
        return decoded


def _result_code(payload: dict[str, object]) -> str:
    value = payload.get("result")
    if isinstance(value, (int, str)):
        return str(value)
    raise ZibalUnavailable("provider_invalid_response")


def _track_id_value(track_id: str) -> int | str:
    try:
        return int(track_id)
    except ValueError:
        return track_id
