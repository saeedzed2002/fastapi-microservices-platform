import base64
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from chat_service.media import MediaAttachmentGateway
from chat_service.models import Conversation, ConversationParticipant, Message, MessageAttachment
from chat_service.schemas import (
    AttachmentDownloadResponse,
    AttachmentResponse,
    ConversationCreate,
    ConversationPage,
    ConversationResponse,
    MarkReadResponse,
    MediaAttachment,
    MessagePage,
    MessageResponse,
    SendMessageFrame,
)


@dataclass(frozen=True)
class SentMessage:
    message: MessageResponse
    participant_ids: list[UUID]
    duplicate: bool


def encode_cursor(*, created_at: datetime, message_id: UUID) -> str:
    timestamp = created_at.astimezone(UTC).isoformat()
    return base64.urlsafe_b64encode(f"{timestamp}|{message_id}".encode()).decode().rstrip("=")


def decode_cursor(value: str) -> tuple[datetime, UUID]:
    try:
        padding = "=" * (-len(value) % 4)
        timestamp_text, message_id_text = (
            base64.urlsafe_b64decode(value + padding).decode().split("|", 1)
        )
        timestamp = datetime.fromisoformat(timestamp_text)
        if timestamp.tzinfo is None:
            raise ValueError("cursor timestamp has no timezone")
        return timestamp.astimezone(UTC), UUID(message_id_text)
    except (UnicodeDecodeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="invalid message cursor"
        ) from exc


async def _require_participant(
    db: AsyncSession,
    *,
    conversation_id: UUID,
    subject_id: UUID,
    lock: bool = False,
) -> ConversationParticipant:
    statement = select(ConversationParticipant).where(
        ConversationParticipant.conversation_id == conversation_id,
        ConversationParticipant.subject_id == subject_id,
    )
    if lock:
        statement = statement.with_for_update()
    participant = await db.scalar(statement)
    if participant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="conversation not found")
    return participant


async def _participant_ids(db: AsyncSession, *, conversation_id: UUID) -> list[UUID]:
    values = await db.scalars(
        select(ConversationParticipant.subject_id)
        .where(ConversationParticipant.conversation_id == conversation_id)
        .order_by(ConversationParticipant.subject_id)
    )
    return list(values)


async def _unread_count(db: AsyncSession, *, participant: ConversationParticipant) -> int:
    statement = (
        select(func.count())
        .select_from(Message)
        .where(
            Message.conversation_id == participant.conversation_id,
            Message.sender_subject_id != participant.subject_id,
        )
    )
    if participant.last_read_at is not None and participant.last_read_message_id is not None:
        statement = statement.where(
            or_(
                Message.created_at > participant.last_read_at,
                and_(
                    Message.created_at == participant.last_read_at,
                    Message.id > participant.last_read_message_id,
                ),
            )
        )
    return int((await db.scalar(statement)) or 0)


async def _conversation_response(
    db: AsyncSession, *, conversation: Conversation, subject_id: UUID
) -> ConversationResponse:
    participant = await _require_participant(
        db, conversation_id=conversation.id, subject_id=subject_id
    )
    return ConversationResponse(
        id=conversation.id,
        participant_ids=await _participant_ids(db, conversation_id=conversation.id),
        created_by_subject_id=conversation.created_by_subject_id,
        created_at=conversation.created_at,
        last_message_at=conversation.last_message_at,
        unread_count=await _unread_count(db, participant=participant),
    )


async def create_conversation(
    db: AsyncSession, *, subject_id: UUID, payload: ConversationCreate
) -> ConversationResponse:
    participant_ids = set(payload.participant_ids)
    participant_ids.add(subject_id)
    conversation = Conversation(created_by_subject_id=subject_id)
    db.add(conversation)
    await db.flush()
    db.add_all(
        ConversationParticipant(conversation_id=conversation.id, subject_id=participant_id)
        for participant_id in participant_ids
    )
    await db.commit()
    return await _conversation_response(db, conversation=conversation, subject_id=subject_id)


async def list_conversations(db: AsyncSession, *, subject_id: UUID, limit: int) -> ConversationPage:
    conversations = list(
        await db.scalars(
            select(Conversation)
            .join(
                ConversationParticipant,
                ConversationParticipant.conversation_id == Conversation.id,
            )
            .where(ConversationParticipant.subject_id == subject_id)
            .order_by(
                Conversation.last_message_at.desc().nullslast(), Conversation.created_at.desc()
            )
            .limit(limit)
        )
    )
    return ConversationPage(
        items=[
            await _conversation_response(db, conversation=conversation, subject_id=subject_id)
            for conversation in conversations
        ]
    )


async def get_conversation(
    db: AsyncSession, *, conversation_id: UUID, subject_id: UUID
) -> ConversationResponse:
    conversation = await db.get(Conversation, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="conversation not found")
    return await _conversation_response(db, conversation=conversation, subject_id=subject_id)


async def _attachments_by_message(
    db: AsyncSession, *, message_ids: list[UUID]
) -> dict[UUID, list[AttachmentResponse]]:
    if not message_ids:
        return {}
    attachments = await db.scalars(
        select(MessageAttachment)
        .where(MessageAttachment.message_id.in_(message_ids))
        .order_by(MessageAttachment.created_at, MessageAttachment.id)
    )
    result: dict[UUID, list[AttachmentResponse]] = {}
    for attachment in attachments:
        result.setdefault(attachment.message_id, []).append(
            AttachmentResponse(
                asset_id=attachment.media_asset_id,
                content_type=attachment.content_type,
                size_bytes=attachment.size_bytes,
            )
        )
    return result


async def _message_response(
    db: AsyncSession, *, message: Message, attachments: list[AttachmentResponse] | None = None
) -> MessageResponse:
    attachment_values = attachments
    if attachment_values is None:
        attachment_values = (await _attachments_by_message(db, message_ids=[message.id])).get(
            message.id, []
        )
    return MessageResponse(
        id=message.id,
        conversation_id=message.conversation_id,
        client_message_id=message.client_message_id,
        sender_id=message.sender_subject_id,
        content=message.content,
        message_type=message.message_type,
        created_at=message.created_at,
        attachments=attachment_values,
    )


async def list_messages(
    db: AsyncSession,
    *,
    conversation_id: UUID,
    subject_id: UUID,
    limit: int,
    before: str | None,
    after: str | None,
) -> MessagePage:
    if before is not None and after is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="before and after cannot be combined",
        )
    await _require_participant(db, conversation_id=conversation_id, subject_id=subject_id)
    statement = select(Message).where(Message.conversation_id == conversation_id)
    descending = before is not None
    if before is not None:
        created_at, message_id = decode_cursor(before)
        statement = statement.where(
            or_(
                Message.created_at < created_at,
                and_(Message.created_at == created_at, Message.id < message_id),
            )
        )
    if after is not None:
        created_at, message_id = decode_cursor(after)
        statement = statement.where(
            or_(
                Message.created_at > created_at,
                and_(Message.created_at == created_at, Message.id > message_id),
            )
        )
    if descending:
        statement = statement.order_by(Message.created_at.desc(), Message.id.desc())
    else:
        statement = statement.order_by(Message.created_at, Message.id)
    rows = list(await db.scalars(statement.limit(limit + 1)))
    has_more = len(rows) > limit
    rows = rows[:limit]
    if descending:
        rows.reverse()
    attachment_map = await _attachments_by_message(db, message_ids=[message.id for message in rows])
    items = [
        await _message_response(db, message=message, attachments=attachment_map.get(message.id, []))
        for message in rows
    ]
    next_before = None
    next_after = None
    if has_more and rows:
        cursor = encode_cursor(created_at=rows[0].created_at, message_id=rows[0].id)
        if descending:
            next_before = cursor
        else:
            next_after = encode_cursor(created_at=rows[-1].created_at, message_id=rows[-1].id)
    return MessagePage(items=items, next_before=next_before, next_after=next_after)


async def mark_read(
    db: AsyncSession, *, conversation_id: UUID, subject_id: UUID, message_id: UUID
) -> MarkReadResponse:
    participant = await _require_participant(
        db, conversation_id=conversation_id, subject_id=subject_id, lock=True
    )
    message = await db.scalar(
        select(Message).where(Message.id == message_id, Message.conversation_id == conversation_id)
    )
    if message is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="message not found")
    is_unread_cursor = (
        participant.last_read_at is None
        or participant.last_read_message_id is None
        or (message.created_at, message.id)
        > (participant.last_read_at, participant.last_read_message_id)
    )
    if is_unread_cursor:
        participant.last_read_at = message.created_at
        participant.last_read_message_id = message.id
    await db.commit()
    if participant.last_read_message_id is None or participant.last_read_at is None:
        raise RuntimeError("read cursor was not persisted")
    return MarkReadResponse(
        conversation_id=conversation_id,
        message_id=participant.last_read_message_id,
        read_at=participant.last_read_at,
    )


async def _existing_message(
    db: AsyncSession, *, sender_subject_id: UUID, client_message_id: UUID
) -> Message | None:
    return cast(
        Message | None,
        await db.scalar(
            select(Message).where(
                Message.sender_subject_id == sender_subject_id,
                Message.client_message_id == client_message_id,
            )
        ),
    )


async def send_message(
    db: AsyncSession,
    *,
    sender_subject_id: UUID,
    access_token: str,
    payload: SendMessageFrame,
    media_gateway: MediaAttachmentGateway,
) -> SentMessage:
    existing = await _existing_message(
        db, sender_subject_id=sender_subject_id, client_message_id=payload.client_message_id
    )
    if existing is not None:
        if existing.conversation_id != payload.conversation_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="client message id is already used"
            )
        return SentMessage(
            message=await _message_response(db, message=existing),
            participant_ids=await _participant_ids(db, conversation_id=existing.conversation_id),
            duplicate=True,
        )
    await _require_participant(
        db, conversation_id=payload.conversation_id, subject_id=sender_subject_id
    )
    await db.rollback()
    attachments = await media_gateway.validate_attachments(
        asset_ids=payload.attachment_ids, access_token=access_token
    )
    duplicate = False
    try:
        async with db.begin():
            await _require_participant(
                db,
                conversation_id=payload.conversation_id,
                subject_id=sender_subject_id,
                lock=True,
            )
            existing = await _existing_message(
                db, sender_subject_id=sender_subject_id, client_message_id=payload.client_message_id
            )
            if existing is not None:
                if existing.conversation_id != payload.conversation_id:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="client message id is already used",
                    )
                message = existing
                duplicate = True
            else:
                message = Message(
                    conversation_id=payload.conversation_id,
                    sender_subject_id=sender_subject_id,
                    client_message_id=payload.client_message_id,
                    content=payload.content,
                )
                db.add(message)
                await db.flush()
                db.add_all(
                    MessageAttachment(
                        message_id=message.id,
                        media_asset_id=attachment.asset_id,
                        content_type=attachment.content_type,
                        size_bytes=attachment.size_bytes,
                    )
                    for attachment in attachments
                )
                conversation = await db.get(
                    Conversation, payload.conversation_id, with_for_update=True
                )
                if conversation is None:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND, detail="conversation not found"
                    )
                conversation.last_message_at = message.created_at
    except IntegrityError as exc:
        await db.rollback()
        recovered_message = await _existing_message(
            db, sender_subject_id=sender_subject_id, client_message_id=payload.client_message_id
        )
        if (
            recovered_message is None
            or recovered_message.conversation_id != payload.conversation_id
        ):
            raise exc
        message = recovered_message
        duplicate = True
    return SentMessage(
        message=await _message_response(db, message=message),
        participant_ids=await _participant_ids(db, conversation_id=message.conversation_id),
        duplicate=duplicate,
    )


async def get_attachment_download_url(
    db: AsyncSession,
    *,
    conversation_id: UUID,
    message_id: UUID,
    asset_id: UUID,
    subject_id: UUID,
    media_gateway: MediaAttachmentGateway,
) -> AttachmentDownloadResponse:
    await _require_participant(db, conversation_id=conversation_id, subject_id=subject_id)
    attachment = await db.scalar(
        select(MessageAttachment)
        .join(Message, Message.id == MessageAttachment.message_id)
        .where(
            MessageAttachment.message_id == message_id,
            MessageAttachment.media_asset_id == asset_id,
            Message.conversation_id == conversation_id,
        )
    )
    if attachment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="attachment not found")
    media_attachment = MediaAttachment(
        asset_id=attachment.media_asset_id,
        content_type=attachment.content_type,
        size_bytes=attachment.size_bytes,
    )
    await db.rollback()
    return await media_gateway.create_download_url(
        subject_id=subject_id,
        conversation_id=conversation_id,
        message_id=message_id,
        attachment=media_attachment,
    )
