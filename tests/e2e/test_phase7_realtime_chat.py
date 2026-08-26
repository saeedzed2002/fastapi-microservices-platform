import hashlib
import json
import os
import time
from uuid import UUID, uuid4

import httpx
import pytest

from platform_auth import encode_access_token

pytestmark = pytest.mark.e2e

LOCAL_SECRET = "local-development-jwt-secret-change-me-32-bytes"
ISSUER = "fastapi-platform.identity"
AUDIENCE = "fastapi-platform"
ONE_PIXEL_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010802000000907753de"
    "0000000c49444154789c636064620600000e0007d76fe4780000000049454e44ae426082"
)


def _token(*, subject: UUID) -> str:
    return encode_access_token(
        subject=subject,
        roles=("customer",),
        secret=os.environ.get("E2E_JWT_SECRET", LOCAL_SECRET),
        issuer=ISSUER,
        audience=AUDIENCE,
        ttl_seconds=900,
    )


def _receive_frame_type(socket: object, frame_type: str) -> dict[str, object]:
    for _ in range(4):
        payload = json.loads(socket.recv())  # type: ignore[union-attr]
        if payload["type"] == frame_type:
            return payload
    raise AssertionError(f"did not receive {frame_type}")


def _create_ready_chat_attachment(*, base_url: str, access_token: str) -> UUID:
    authorization = httpx.post(
        f"{base_url}:8004/api/v1/media/uploads",
        headers={"Authorization": f"Bearer {access_token}"},
        json={
            "purpose": "chat_attachment",
            "content_type": "image/png",
            "size_bytes": len(ONE_PIXEL_PNG),
            "checksum_sha256": hashlib.sha256(ONE_PIXEL_PNG).hexdigest(),
        },
        timeout=10.0,
    )
    authorization.raise_for_status()
    asset_id = UUID(authorization.json()["asset_id"])
    upload = httpx.put(
        authorization.json()["upload_url"],
        content=ONE_PIXEL_PNG,
        headers={"Content-Type": "image/png"},
        timeout=10.0,
    )
    upload.raise_for_status()
    completion = httpx.post(
        f"{base_url}:8004/api/v1/media/assets/{asset_id}/complete",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10.0,
    )
    completion.raise_for_status()
    for _ in range(30):
        asset = httpx.get(
            f"{base_url}:8004/api/v1/media/assets/{asset_id}",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10.0,
        )
        asset.raise_for_status()
        if asset.json()["status"] == "ready":
            return asset_id
        time.sleep(1)
    raise AssertionError("chat attachment did not reach ready state")


def test_realtime_chat_persists_before_ack_and_deduplicates_retries() -> None:
    if os.environ.get("RUN_E2E") != "1":
        pytest.skip("set RUN_E2E=1 after starting the local Docker Compose platform")

    from websockets.sync.client import connect

    base_url = os.environ.get("E2E_BASE_URL", "http://localhost")
    sender_id, recipient_id = uuid4(), uuid4()
    sender_token, recipient_token = _token(subject=sender_id), _token(subject=recipient_id)
    attachment_id = _create_ready_chat_attachment(base_url=base_url, access_token=sender_token)
    conversation = httpx.post(
        f"{base_url}:8010/api/v1/chat/conversations",
        headers={"Authorization": f"Bearer {sender_token}"},
        json={"participant_ids": [str(recipient_id)]},
        timeout=10.0,
    )
    conversation.raise_for_status()
    conversation_id = UUID(conversation.json()["id"])
    client_message_id = uuid4()
    request_id = uuid4()

    with connect(f"{base_url.replace('http', 'ws', 1)}:8010/api/v1/chat/ws") as recipient_socket:
        recipient_socket.send(
            json.dumps(
                {
                    "type": "chat.authenticate.v1",
                    "request_id": str(uuid4()),
                    "access_token": recipient_token,
                }
            )
        )
        assert (
            _receive_frame_type(recipient_socket, "chat.authenticated.v1")["type"]
            == "chat.authenticated.v1"
        )
        with connect(f"{base_url.replace('http', 'ws', 1)}:8010/api/v1/chat/ws") as sender_socket:
            sender_socket.send(
                json.dumps(
                    {
                        "type": "chat.authenticate.v1",
                        "request_id": str(uuid4()),
                        "access_token": sender_token,
                    }
                )
            )
            assert (
                _receive_frame_type(sender_socket, "chat.authenticated.v1")["type"]
                == "chat.authenticated.v1"
            )
            frame = {
                "type": "chat.send_message.v1",
                "request_id": str(request_id),
                "client_message_id": str(client_message_id),
                "conversation_id": str(conversation_id),
                "content": "persist before acknowledgement",
                "attachment_ids": [str(attachment_id)],
            }
            sender_socket.send(json.dumps(frame))
            acknowledgement = _receive_frame_type(sender_socket, "chat.message_ack.v1")
            assert acknowledgement["type"] == "chat.message_ack.v1"
            assert not acknowledgement["duplicate"]
            recipient_message = _receive_frame_type(recipient_socket, "chat.message.v1")
            assert recipient_message["type"] == "chat.message.v1"
            assert recipient_message["message_id"] == acknowledgement["message_id"]

            sender_socket.send(json.dumps(frame))
            duplicate_acknowledgement = _receive_frame_type(sender_socket, "chat.message_ack.v1")
            assert duplicate_acknowledgement["type"] == "chat.message_ack.v1"
            assert duplicate_acknowledgement["duplicate"]
            assert duplicate_acknowledgement["message_id"] == acknowledgement["message_id"]

    history = httpx.get(
        f"{base_url}:8010/api/v1/chat/conversations/{conversation_id}/messages",
        headers={"Authorization": f"Bearer {recipient_token}"},
        timeout=10.0,
    )
    history.raise_for_status()
    messages = history.json()["items"]
    assert len(messages) == 1
    assert messages[0]["id"] == acknowledgement["message_id"]
    assert messages[0]["attachments"] == [
        {
            "asset_id": str(attachment_id),
            "content_type": "image/png",
            "size_bytes": len(ONE_PIXEL_PNG),
        }
    ]

    attachment_url = httpx.get(
        f"{base_url}:8010/api/v1/chat/conversations/{conversation_id}/messages/"
        f"{acknowledgement['message_id']}/attachments/{attachment_id}/download-url",
        headers={"Authorization": f"Bearer {recipient_token}"},
        timeout=10.0,
    )
    attachment_url.raise_for_status()
    assert attachment_url.json()["asset_id"] == str(attachment_id)
    assert attachment_url.json()["content_type"] == "image/webp"
    download = httpx.get(attachment_url.json()["download_url"], timeout=10.0)
    download.raise_for_status()
    assert download.headers["content-type"].startswith("image/webp")
