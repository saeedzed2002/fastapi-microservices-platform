import asyncio
import hashlib
import json
import os
import ssl
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


def _token(*, subject: UUID, roles: tuple[str, ...] = ("customer",)) -> str:
    return encode_access_token(
        subject=subject,
        roles=roles,
        secret=os.environ.get("E2E_JWT_SECRET", LOCAL_SECRET),
        issuer=ISSUER,
        audience=AUDIENCE,
        ttl_seconds=900,
    )


async def _receive_frame_type(socket: object, frame_type: str) -> dict[str, object]:
    for _ in range(4):
        payload = json.loads(await socket.recv())  # type: ignore[union-attr]
        if payload["type"] == frame_type:
            return payload
    raise AssertionError(f"did not receive {frame_type}")


def _create_ready_chat_attachment(*, base_url: str, access_token: str) -> UUID:
    with httpx.Client(verify=False, timeout=10.0) as client:
        authorization = client.post(
            f"{base_url}/api/v1/media/uploads",
            headers={"Authorization": f"Bearer {access_token}"},
            json={
                "purpose": "chat_attachment",
                "content_type": "image/png",
                "size_bytes": len(ONE_PIXEL_PNG),
                "checksum_sha256": hashlib.sha256(ONE_PIXEL_PNG).hexdigest(),
            },
        )
        authorization.raise_for_status()
        asset_id = UUID(authorization.json()["asset_id"])
        upload = client.put(
            authorization.json()["upload_url"],
            content=ONE_PIXEL_PNG,
            headers={"Content-Type": "image/png"},
        )
        upload.raise_for_status()
        completion = client.post(
            f"{base_url}/api/v1/media/assets/{asset_id}/complete",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        completion.raise_for_status()
        for _ in range(30):
            asset = client.get(
                f"{base_url}/api/v1/media/assets/{asset_id}",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            asset.raise_for_status()
            if asset.json()["status"] == "ready":
                return asset_id
            time.sleep(1)
    raise AssertionError("chat attachment did not reach ready state")


async def _send_and_receive_message(
    *,
    websocket_url: str,
    sender_token: str,
    recipient_token: str,
    conversation_id: UUID,
    attachment_id: UUID,
) -> dict[str, object]:
    from websockets.asyncio.client import connect

    websocket_ssl = ssl.create_default_context()
    websocket_ssl.check_hostname = False
    websocket_ssl.verify_mode = ssl.CERT_NONE
    request_id = uuid4()
    client_message_id = uuid4()

    async with connect(websocket_url, ssl=websocket_ssl) as recipient_socket:
        await recipient_socket.send(
            json.dumps(
                {
                    "type": "chat.authenticate.v1",
                    "request_id": str(uuid4()),
                    "access_token": recipient_token,
                }
            )
        )
        assert (await _receive_frame_type(recipient_socket, "chat.authenticated.v1"))[
            "type"
        ] == "chat.authenticated.v1"
        async with connect(websocket_url, ssl=websocket_ssl) as sender_socket:
            await sender_socket.send(
                json.dumps(
                    {
                        "type": "chat.authenticate.v1",
                        "request_id": str(uuid4()),
                        "access_token": sender_token,
                    }
                )
            )
            assert (await _receive_frame_type(sender_socket, "chat.authenticated.v1"))[
                "type"
            ] == "chat.authenticated.v1"
            frame = {
                "type": "chat.send_message.v1",
                "request_id": str(request_id),
                "client_message_id": str(client_message_id),
                "conversation_id": str(conversation_id),
                "content": "persist before acknowledgement",
                "attachment_ids": [str(attachment_id)],
            }
            await sender_socket.send(json.dumps(frame))
            acknowledgement = await _receive_frame_type(sender_socket, "chat.message_ack.v1")
            assert acknowledgement["type"] == "chat.message_ack.v1"
            assert not acknowledgement["duplicate"]
            recipient_message = await _receive_frame_type(recipient_socket, "chat.message.v1")
            assert recipient_message["type"] == "chat.message.v1"
            assert recipient_message["message_id"] == acknowledgement["message_id"]

            await sender_socket.send(json.dumps(frame))
            duplicate_acknowledgement = await _receive_frame_type(
                sender_socket, "chat.message_ack.v1"
            )
            assert duplicate_acknowledgement["type"] == "chat.message_ack.v1"
            assert duplicate_acknowledgement["duplicate"]
            assert duplicate_acknowledgement["message_id"] == acknowledgement["message_id"]
            return acknowledgement


async def _assert_closed_support_conversation_rejects_message(
    *, websocket_url: str, access_token: str, conversation_id: UUID
) -> None:
    from websockets.asyncio.client import connect

    websocket_ssl = ssl.create_default_context()
    websocket_ssl.check_hostname = False
    websocket_ssl.verify_mode = ssl.CERT_NONE
    async with connect(websocket_url, ssl=websocket_ssl) as socket:
        await socket.send(
            json.dumps(
                {
                    "type": "chat.authenticate.v1",
                    "request_id": str(uuid4()),
                    "access_token": access_token,
                }
            )
        )
        assert (await _receive_frame_type(socket, "chat.authenticated.v1"))["type"] == (
            "chat.authenticated.v1"
        )
        await socket.send(
            json.dumps(
                {
                    "type": "chat.send_message.v1",
                    "request_id": str(uuid4()),
                    "client_message_id": str(uuid4()),
                    "conversation_id": str(conversation_id),
                    "content": "this write must be rejected",
                    "attachment_ids": [],
                }
            )
        )
        rejected = await _receive_frame_type(socket, "chat.error.v1")
        assert rejected["code"] == "request_rejected"
        assert rejected["message"] == "support conversation is closed"


async def _claim_support_conversation_concurrently(
    *,
    base_url: str,
    conversation_id: UUID,
    first_headers: dict[str, str],
    second_headers: dict[str, str],
) -> list[httpx.Response]:
    async with httpx.AsyncClient(verify=False, timeout=10.0) as client:
        return list(
            await asyncio.gather(
                client.post(
                    f"{base_url}/api/v1/chat/support/conversations/{conversation_id}/claim",
                    headers=first_headers,
                ),
                client.post(
                    f"{base_url}/api/v1/chat/support/conversations/{conversation_id}/claim",
                    headers=second_headers,
                ),
            )
        )


def test_realtime_chat_persists_before_ack_and_deduplicates_retries() -> None:
    if os.environ.get("RUN_E2E") != "1":
        pytest.skip("set RUN_E2E=1 after starting the local Docker Compose platform")

    base_url = os.environ.get("E2E_BASE_URL", "https://localhost")
    sender_id, recipient_id = uuid4(), uuid4()
    sender_token, recipient_token = _token(subject=sender_id), _token(subject=recipient_id)
    attachment_id = _create_ready_chat_attachment(base_url=base_url, access_token=sender_token)

    with httpx.Client(verify=False, timeout=10.0) as client:
        conversation = client.post(
            f"{base_url}/api/v1/chat/conversations",
            headers={"Authorization": f"Bearer {sender_token}"},
            json={"participant_ids": [str(recipient_id)]},
        )
        conversation.raise_for_status()
        conversation_id = UUID(conversation.json()["id"])

        acknowledgement = asyncio.run(
            _send_and_receive_message(
                websocket_url=f"{base_url.replace('https', 'wss', 1)}/api/v1/chat/ws",
                sender_token=sender_token,
                recipient_token=recipient_token,
                conversation_id=conversation_id,
                attachment_id=attachment_id,
            )
        )

        history = client.get(
            f"{base_url}/api/v1/chat/conversations/{conversation_id}/messages",
            headers={"Authorization": f"Bearer {recipient_token}"},
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

        attachment_url = client.get(
            f"{base_url}/api/v1/chat/conversations/{conversation_id}/messages/"
            f"{acknowledgement['message_id']}/attachments/{attachment_id}/download-url",
            headers={"Authorization": f"Bearer {recipient_token}"},
        )
        attachment_url.raise_for_status()
        assert attachment_url.json()["asset_id"] == str(attachment_id)
        assert attachment_url.json()["content_type"] == "image/webp"
        download = client.get(attachment_url.json()["download_url"])
        download.raise_for_status()
        assert download.headers["content-type"].startswith("image/webp")


def test_support_queue_assigns_one_agent_and_preserves_membership_privacy() -> None:
    if os.environ.get("RUN_E2E") != "1":
        pytest.skip("set RUN_E2E=1 after starting the local Docker Compose platform")

    base_url = os.environ.get("E2E_BASE_URL", "https://localhost")
    customer_id, first_agent_id, second_agent_id = uuid4(), uuid4(), uuid4()
    customer_token = _token(subject=customer_id)
    first_agent_token = _token(subject=first_agent_id, roles=("admin",))
    second_agent_token = _token(subject=second_agent_id, roles=("admin",))
    customer_headers = {"Authorization": f"Bearer {customer_token}"}
    first_agent_headers = {"Authorization": f"Bearer {first_agent_token}"}
    second_agent_headers = {"Authorization": f"Bearer {second_agent_token}"}

    with httpx.Client(verify=False, timeout=10.0) as client:
        created = client.post(
            f"{base_url}/api/v1/chat/support/conversations", headers=customer_headers
        )
        assert created.status_code == 201
        conversation = created.json()
        conversation_id = UUID(conversation["id"])
        assert conversation["participant_ids"] == [str(customer_id)]
        assert conversation["support"]["status"] == "queued"

        repeated = client.post(
            f"{base_url}/api/v1/chat/support/conversations", headers=customer_headers
        )
        assert repeated.status_code == 200
        assert repeated.json()["id"] == str(conversation_id)

        customer_queue = client.get(
            f"{base_url}/api/v1/chat/support/queue", headers=customer_headers
        )
        assert customer_queue.status_code == 403

        first_agent_queue = client.get(
            f"{base_url}/api/v1/chat/support/queue", headers=first_agent_headers
        )
        first_agent_queue.raise_for_status()
        assert {item["conversation_id"] for item in first_agent_queue.json()["items"]} >= {
            str(conversation_id)
        }

        before_claim_history = client.get(
            f"{base_url}/api/v1/chat/conversations/{conversation_id}/messages",
            headers=first_agent_headers,
        )
        assert before_claim_history.status_code == 404

        first_claim, second_claim = asyncio.run(
            _claim_support_conversation_concurrently(
                base_url=base_url,
                conversation_id=conversation_id,
                first_headers=first_agent_headers,
                second_headers=second_agent_headers,
            )
        )
        assert sorted((first_claim.status_code, second_claim.status_code)) == [200, 409]
        winning_response, winning_agent_id, winning_token, winning_headers = next(
            (response, agent_id, token, headers)
            for response, agent_id, token, headers in (
                (first_claim, first_agent_id, first_agent_token, first_agent_headers),
                (second_claim, second_agent_id, second_agent_token, second_agent_headers),
            )
            if response.status_code == 200
        )
        _, losing_agent_id, losing_token, losing_headers = next(
            (response, agent_id, token, headers)
            for response, agent_id, token, headers in (
                (first_claim, first_agent_id, first_agent_token, first_agent_headers),
                (second_claim, second_agent_id, second_agent_token, second_agent_headers),
            )
            if response.status_code == 409
        )
        assert set(winning_response.json()["participant_ids"]) == {
            str(customer_id),
            str(winning_agent_id),
        }
        assert winning_response.json()["support"]["status"] == "claimed"
        assert winning_response.json()["support"]["assigned_admin_subject_id"] == str(
            winning_agent_id
        )

        losing_agent_history = client.get(
            f"{base_url}/api/v1/chat/conversations/{conversation_id}/messages",
            headers=losing_headers,
        )
        assert losing_agent_history.status_code == 404

        losing_agent_queue = client.get(
            f"{base_url}/api/v1/chat/support/queue", headers=losing_headers
        )
        losing_agent_queue.raise_for_status()
        assert str(conversation_id) not in {
            item["conversation_id"] for item in losing_agent_queue.json()["items"]
        }

        released = client.post(
            f"{base_url}/api/v1/chat/support/conversations/{conversation_id}/release",
            headers=winning_headers,
        )
        assert released.status_code == 204

        released_agent_history = client.get(
            f"{base_url}/api/v1/chat/conversations/{conversation_id}/messages",
            headers=winning_headers,
        )
        assert released_agent_history.status_code == 404

        reclaimed = client.post(
            f"{base_url}/api/v1/chat/support/conversations/{conversation_id}/claim",
            headers=losing_headers,
        )
        reclaimed.raise_for_status()
        assert reclaimed.json()["support"]["assigned_admin_subject_id"] == str(losing_agent_id)

        closed = client.post(
            f"{base_url}/api/v1/chat/support/conversations/{conversation_id}/close",
            headers=losing_headers,
        )
        closed.raise_for_status()
        assert closed.json()["support"]["status"] == "closed"

        asyncio.run(
            _assert_closed_support_conversation_rejects_message(
                websocket_url=f"{base_url.replace('https', 'wss', 1)}/api/v1/chat/ws",
                access_token=losing_token,
                conversation_id=conversation_id,
            )
        )

        new_request = client.post(
            f"{base_url}/api/v1/chat/support/conversations", headers=customer_headers
        )
        assert new_request.status_code == 201
        assert new_request.json()["id"] != str(conversation_id)
