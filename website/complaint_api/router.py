"""
FastAPI router for handling user complaints and reports.

Provides:
- POST /api/complaint/submit - Submit a new complaint/report

Complaints are stored as JSONL files in the data directory for the
administrator to review. This fulfills the requirement under
《生成式人工智能服务管理暂行办法》第十五条 to establish a complaint
and reporting mechanism.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, field_validator

router = APIRouter(prefix="/api/complaint", tags=["投诉举报"])

# ── Data directory ──────────────────────────────────────────────────────────
COMPLAINT_DIR = Path(__file__).resolve().parent.parent / "data" / "complaints"


def _ensure_dir() -> None:
    """Ensure the complaint data directory exists."""
    COMPLAINT_DIR.mkdir(parents=True, exist_ok=True)


# ── Request Models ──────────────────────────────────────────────────────────

COMPLAINT_TYPES = {
    "illegal_content": "违法信息",
    "ai_error": "AI 回答错误/不准确",
    "privacy_concern": "隐私问题",
    "copyright": "版权/知识产权问题",
    "abuse": "功能滥用",
    "technical": "技术问题/Bug 反馈",
    "other": "其他",
}


class ComplaintRequest(BaseModel):
    type: str
    content: str
    email: str | None = None

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        if v not in COMPLAINT_TYPES:
            raise ValueError(f"无效的投诉类型: {v}")
        return v

    @field_validator("content")
    @classmethod
    def validate_content(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("投诉内容不能为空")
        if len(v) < 10:
            raise ValueError("投诉内容不能少于10个字")
        if len(v) > 2000:
            raise ValueError("投诉内容不能超过2000字")
        return v

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str | None) -> str | None:
        if v:
            v = v.strip()
            if v and "@" not in v:
                raise ValueError("邮箱格式不正确")
        return v or None


# ── POST /api/complaint/submit ──────────────────────────────────────────────


@router.post("/submit")
def submit_complaint(req: ComplaintRequest):
    """
    Submit a complaint or report.

    Generates a unique ticket_id for tracking, stores the complaint
    data in a JSONL file, and returns the ticket_id to the user.
    """
    _ensure_dir()

    ticket_id = f"CP-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"
    now = datetime.now().isoformat(timespec="seconds")

    record = {
        "ticket_id": ticket_id,
        "type": req.type,
        "type_label": COMPLAINT_TYPES.get(req.type, req.type),
        "content": req.content,
        "email": req.email,
        "created_at": now,
        "status": "pending",  # pending | processing | resolved | rejected
    }

    # Write to daily complaint log
    log_file = COMPLAINT_DIR / f"complaints_{datetime.now().strftime('%Y%m')}.jsonl"
    try:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"投诉提交失败: {e}",
        )

    return {
        "success": True,
        "ticket_id": ticket_id,
        "message": "投诉已提交成功，我们将尽快处理。",
    }
