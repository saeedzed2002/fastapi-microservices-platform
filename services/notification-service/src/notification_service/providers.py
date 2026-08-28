import json
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from notification_service.config import Settings


class SmsProviderError(Exception):
    pass


@dataclass(frozen=True)
class SmsDeliveryReceipt:
    provider_message_id: str


class SmsIrBulkProvider:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def send_otp(self, *, phone: str, code: str) -> SmsDeliveryReceipt:
        if (
            not self._settings.smsir_enabled
            or not self._settings.smsir_api_key
            or not self._settings.smsir_line_number
        ):
            raise SmsProviderError("SMS.ir OTP delivery is not configured")
        try:
            line_number = int(self._settings.smsir_line_number)
        except ValueError as exc:
            raise SmsProviderError("SMS.ir line number is invalid") from exc
        payload = {
            "lineNumber": line_number,
            "MessageText": self._settings.smsir_otp_message_template.format(code=code),
            "Mobiles": [phone],
            "SendDateTime": None,
        }
        request = Request(
            self._settings.smsir_bulk_endpoint,
            data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "X-API-KEY": self._settings.smsir_api_key,
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self._settings.smsir_timeout_seconds) as response:
                body: Any = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, ValueError, OSError) as exc:
            raise SmsProviderError("SMS.ir request failed") from exc
        if not isinstance(body, dict) or body.get("status") != 1:
            raise SmsProviderError("SMS.ir rejected the OTP request")
        data = body.get("data")
        message_ids = data.get("messageIds") if isinstance(data, dict) else None
        if not isinstance(message_ids, list) or not message_ids or not message_ids[0]:
            raise SmsProviderError("SMS.ir did not accept the OTP recipient")
        return SmsDeliveryReceipt(provider_message_id=str(message_ids[0]))
