"""Public customer-service chat and password-protected reply APIs."""

from __future__ import annotations

import asyncio
import hashlib
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, field_validator

from website.action_inbox import InboxError, list_chat_events, record_request
from website.maintenance import ensure_writable
from website.ob_api.router import verify_ob_password
from website.rate_limiter import check_feedback_chat_history_limit, check_feedback_chat_limit, get_client_ip

router = APIRouter(prefix="/api/feedback-chat", tags=["客服聊天"])

_IDENTIFIER_MIN = 4
_IDENTIFIER_MAX = 64
_CONTENT_MAX = 2000
_CONVERSATION_ID_RE = re.compile(r"^[a-f0-9]{64}$")
_REVISION_RE = re.compile(r"^[a-f0-9]{64}$")
_WATCH_TIMEOUT_SECONDS = 25.0
_WATCH_POLL_SECONDS = 0.2


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _conversation_id(identifier: str) -> str:
    normalized = identifier.strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _validate_identifier(value: str) -> str:
    value = value.strip()
    if not (_IDENTIFIER_MIN <= len(value) <= _IDENTIFIER_MAX):
        raise ValueError(f"识别码长度需为 {_IDENTIFIER_MIN}-{_IDENTIFIER_MAX} 个字符")
    if any(char.isspace() or ord(char) < 32 for char in value):
        raise ValueError("识别码不能包含空格或控制字符")
    return value


class ChatIdentifierRequest(BaseModel):
    identifier: str

    @field_validator("identifier")
    @classmethod
    def validate_identifier(cls, value: str) -> str:
        return _validate_identifier(value)


class ChatMessageRequest(ChatIdentifierRequest):
    content: str

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("消息不能为空")
        if len(value) > _CONTENT_MAX:
            raise ValueError(f"消息不能超过 {_CONTENT_MAX} 个字")
        return value


class ChatWatchRequest(ChatIdentifierRequest):
    after_message_id: str = ""

    @field_validator("after_message_id")
    @classmethod
    def validate_after_message_id(cls, value: str) -> str:
        value = value.strip()
        if len(value) > 128 or any(ord(char) < 32 for char in value):
            raise ValueError("无效的消息游标")
        return value


class AdminConversationRequest(BaseModel):
    conversation_id: str

    @field_validator("conversation_id")
    @classmethod
    def validate_conversation_id(cls, value: str) -> str:
        value = value.strip().lower()
        if not _CONVERSATION_ID_RE.fullmatch(value):
            raise ValueError("无效的会话编号")
        return value


class AdminReplyRequest(AdminConversationRequest):
    content: str

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("回复内容不能为空")
        if len(value) > _CONTENT_MAX:
            raise ValueError(f"回复不能超过 {_CONTENT_MAX} 个字")
        return value


class AdminWatchRequest(BaseModel):
    revision: str = ""

    @field_validator("revision")
    @classmethod
    def validate_revision(cls, value: str) -> str:
        value = value.strip().lower()
        if value and not _REVISION_RE.fullmatch(value):
            raise ValueError("无效的会话版本")
        return value


def _message_from_event(event: dict[str, Any]) -> dict[str, Any]:
    payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
    sender = "support" if event.get("event_type") == "feedback_reply" else "visitor"
    return {
        "message_id": str(payload.get("message_id") or event.get("event_id") or ""),
        "sender": sender,
        "content": str(payload.get("content") or ""),
        "created_at": str(event.get("created_at") or payload.get("created_at") or ""),
        "origin_label": str(event.get("origin_label") or ""),
    }


def _history(conversation_id: str) -> list[dict[str, Any]]:
    return [_message_from_event(event) for event in list_chat_events(conversation_id)]


def _user_identifier_from_events(events: list[dict[str, Any]]) -> str:
    """Read the user-defined label only for password-protected admin views."""
    for event in events:
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        identifier = str(payload.get("user_identifier") or "").strip()
        if identifier:
            return identifier
    return ""


def _user_identifier(conversation_id: str) -> str:
    return _user_identifier_from_events(list_chat_events(conversation_id))


def _conversations() -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for event in list_chat_events():
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        conversation_id = str(payload.get("conversation_id") or "")
        if _CONVERSATION_ID_RE.fullmatch(conversation_id):
            grouped.setdefault(conversation_id, []).append(event)

    conversations = []
    for conversation_id, events in grouped.items():
        messages = [_message_from_event(event) for event in events]
        conversations.append({
            "conversation_id": conversation_id,
            "user_identifier": _user_identifier_from_events(events),
            "message_count": len(messages),
            "latest_at": messages[-1]["created_at"],
            "latest_sender": messages[-1]["sender"],
            "latest_message_id": messages[-1]["message_id"],
            "pending_reply": messages[-1]["sender"] == "visitor",
        })
    conversations.sort(key=lambda item: (item["latest_at"], item["conversation_id"]), reverse=True)
    return conversations


def _conversation_revision(conversations: list[dict[str, Any]]) -> str:
    state = "\n".join(
        f"{item['conversation_id']}:{item['message_count']}:{item['latest_message_id']}"
        for item in conversations
    )
    return hashlib.sha256(state.encode("utf-8")).hexdigest()


def _conversation_response(response: Response, conversations: list[dict[str, Any]]) -> dict[str, Any]:
    response.headers["Cache-Control"] = "no-store"
    return {
        "success": True,
        "revision": _conversation_revision(conversations),
        "conversations": conversations,
    }


def _chat_response(
    response: Response,
    conversation_id: str,
    messages: list[dict[str, Any]],
    *,
    user_identifier: str = "",
) -> dict[str, Any]:
    response.headers["Cache-Control"] = "no-store"
    body = {
        "success": True,
        "conversation_id": conversation_id,
        "messages": messages,
    }
    if user_identifier:
        body["user_identifier"] = user_identifier
    return body


@router.post("/history")
def get_history(req: ChatIdentifierRequest, request: Request, response: Response):
    check_feedback_chat_history_limit(get_client_ip(request))
    conversation_id = _conversation_id(req.identifier)
    return _chat_response(response, conversation_id, _history(conversation_id))


@router.post("/watch")
async def watch_history(req: ChatWatchRequest, request: Request, response: Response):
    """Wait until a conversation changes, avoiding fixed-interval browser polling."""
    check_feedback_chat_history_limit(get_client_ip(request))
    conversation_id = _conversation_id(req.identifier)
    loop = asyncio.get_running_loop()
    deadline = loop.time() + _WATCH_TIMEOUT_SECONDS
    while True:
        messages = _history(conversation_id)
        latest_message_id = messages[-1]["message_id"] if messages else ""
        if latest_message_id != req.after_message_id:
            body = _chat_response(response, conversation_id, messages)
            body["changed"] = True
            return body
        remaining = deadline - loop.time()
        if remaining <= 0:
            body = _chat_response(response, conversation_id, messages)
            body["changed"] = False
            return body
        await asyncio.sleep(min(_WATCH_POLL_SECONDS, remaining))


@router.post("/message")
def send_message(req: ChatMessageRequest, request: Request, response: Response):
    ensure_writable()
    check_feedback_chat_limit(get_client_ip(request))
    conversation_id = _conversation_id(req.identifier)
    created_at = _now()
    message_id = f"FC-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:12].upper()}"
    try:
        result = record_request(
            "feedback_message",
            {
                "conversation_id": conversation_id,
                "message_id": message_id,
                "content": req.content,
                "user_identifier": req.identifier,
                "created_at": created_at,
            },
            event_id=message_id,
            created_at=created_at,
        )
    except InboxError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="消息保存失败") from exc
    messages = _history(conversation_id)
    body = _chat_response(response, conversation_id, messages)
    body["message"] = messages[-1] if messages else {}
    body["replication_pending"] = not result["replicated"]
    return body


@router.get("/conversations")
def list_conversations(response: Response, _=Depends(verify_ob_password)):
    return _conversation_response(response, _conversations())


@router.post("/admin-watch")
async def watch_conversations(
    req: AdminWatchRequest,
    response: Response,
    _=Depends(verify_ob_password),
):
    """Wait until any support conversation changes."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + _WATCH_TIMEOUT_SECONDS
    while True:
        conversations = _conversations()
        revision = _conversation_revision(conversations)
        if revision != req.revision:
            body = _conversation_response(response, conversations)
            body["changed"] = True
            return body
        remaining = deadline - loop.time()
        if remaining <= 0:
            body = _conversation_response(response, conversations)
            body["changed"] = False
            return body
        await asyncio.sleep(min(_WATCH_POLL_SECONDS, remaining))


@router.post("/admin-history")
def get_admin_history(req: AdminConversationRequest, response: Response, _=Depends(verify_ob_password)):
    return _chat_response(
        response,
        req.conversation_id,
        _history(req.conversation_id),
        user_identifier=_user_identifier(req.conversation_id),
    )


@router.post("/reply")
def reply_message(req: AdminReplyRequest, response: Response, _=Depends(verify_ob_password)):
    ensure_writable()
    created_at = _now()
    message_id = f"FR-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:12].upper()}"
    user_identifier = _user_identifier(req.conversation_id)
    try:
        result = record_request(
            "feedback_reply",
            {
                "conversation_id": req.conversation_id,
                "message_id": message_id,
                "content": req.content,
                "user_identifier": user_identifier,
                "created_at": created_at,
            },
            event_id=message_id,
            created_at=created_at,
        )
    except InboxError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="回复保存失败") from exc
    messages = _history(req.conversation_id)
    body = _chat_response(
        response,
        req.conversation_id,
        messages,
        user_identifier=user_identifier,
    )
    body["message"] = messages[-1] if messages else {}
    body["replication_pending"] = not result["replicated"]
    return body
