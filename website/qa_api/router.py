"""
FastAPI router that wraps the transcript_analyze/kb_qa system into REST endpoints.

Gracefully handles cases where the knowledge base hasn't been built yet.
"""
from __future__ import annotations

import json
import os
import re
import sys
import threading
import traceback
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel

from website.auth import verify_password
from website.logging_setup import log_interaction, log_llm_call, log_api_error, get_session_start_time
from website.rate_limiter import (
    check_all_qa_limits,
    check_password_rate_limit,
    get_client_ip,
    get_rate_limiter_stats,
    register_task,
    unregister_task,
)

# ── Import transcript_analyze (add parent to path) ──
_KB_QA_DIR = Path(__file__).resolve().parent.parent.parent / "transcript_analyze"
if str(_KB_QA_DIR) not in sys.path:
    sys.path.insert(0, str(_KB_QA_DIR))

from kb_qa.config import KB_QA_DEFAULTS
from website import config as cfg

router = APIRouter(prefix="/api/qa", tags=["知识库问答"])

# ── In-memory QA engine (lazy-loaded) ─────────────────────────────────────
_qa_engine: Optional[Any] = None
_qa_status: Dict[str, Any] = {"ready": False, "message": "未初始化", "stats": {}}


def _get_qa_engine():
    """Lazy-load the QA engine, returning None if unavailable."""
    global _qa_engine, _qa_status
    if _qa_engine is not None:
        return _qa_engine

    records_path = Path(cfg.RECORDS_PATH)
    subtitle_root = Path(cfg.SUBTITLE_ROOT)
    kb_dir = Path(cfg.KB_DIR)

    # Check if data exists
    if not records_path.exists():
        _qa_status = {"ready": False, "message": f"记录文件不存在: {records_path}"}
        return None
    if not kb_dir.exists() or not (kb_dir / "segment_store.json").exists():
        _qa_status = {
            "ready": False,
            "message": "知识库未构建，请先运行 `python run_kb_qa.py build`",
        }
        return None

    try:
        from kb_qa.qa import VideoKnowledgeQA
        from loguru import logger

        _qa_engine = VideoKnowledgeQA(
            records_path=records_path,
            subtitle_root=subtitle_root,
            kb_dir=kb_dir,
            embedding_model=cfg.EMBEDDING_MODEL,
            llm_model=cfg.LLM_MODEL,
            api_base=cfg.LLM_API_BASE,
            api_key=cfg.LLM_API_KEY,
            logger=logger,
        )
        _qa_status = {
            "ready": True,
            "message": "知识库已加载",
            "stats": {
                "segment_count": len(_qa_engine.store.segments),
                "kb_dir": str(kb_dir),
            },
        }
        return _qa_engine
    except Exception as e:
        _qa_status = {"ready": False, "message": f"加载失败: {e}"}
        return None


# ── Question validation ────────────────────────────────────────────────────
MAX_QUESTION_LENGTH = 20

# Allowed chars: Chinese chars, English letters, digits, common punctuation
_QUESTION_ALLOWED_RE = re.compile(
    r'^[\u4e00-\u9fff a-zA-Z0-9'
    r'，。！？、；：""''（）【】《》—…·'
    r',\.\?!;:()\[\]{}\-～~\s]+$'
)

def validate_question(question: str) -> Optional[str]:
    """
    Validate a question. Returns an error message if invalid, None if OK.
    """
    if not question or not question.strip():
        return "问题不能为空"
    if len(question) > MAX_QUESTION_LENGTH:
        return f"问题过长，请控制在 {MAX_QUESTION_LENGTH} 字以内（当前 {len(question)} 字）"
    if not _QUESTION_ALLOWED_RE.match(question):
        return "问题中包含不支持的特殊符号，请使用中文、英文字母、数字和常用标点符号"
    return None


# ── Request / Response Models ──────────────────────────────────────────────



class AskRequest(BaseModel):
    question: str

    vector_top_k: int = KB_QA_DEFAULTS.vector_top_k
    bm25_top_k: int = KB_QA_DEFAULTS.bm25_top_k
    context_window: int = KB_QA_DEFAULTS.context_window
    vector_score_threshold: float = KB_QA_DEFAULTS.vector_score_threshold
    bm25_score_threshold: float = KB_QA_DEFAULTS.bm25_score_threshold
    analysis_batch_size: int = KB_QA_DEFAULTS.analysis_batch_size
    synthesis_context_window: int = KB_QA_DEFAULTS.synthesis_context_window
    synthesis_batch_trigger_count: int = KB_QA_DEFAULTS.synthesis_batch_trigger_count
    synthesis_batch_size: int = KB_QA_DEFAULTS.synthesis_batch_size


class AskResponse(BaseModel):
    success: bool
    question: str
    answer: str
    citations: List[Dict[str, Any]]
    video_results: List[Dict[str, Any]]
    stats: Dict[str, Any]
    archive_path: str = ""
    comprehensiveness: Optional[Dict[str, Any]] = None


# ── Password Verification (frontend helper) ────────────────────────────────


class PasswordVerifyRequest(BaseModel):
    password: str


@router.post("/verify-password")
def verify_site_password(
    req: PasswordVerifyRequest,
    request: Request,
):
    """
    Frontend uses this to verify the site password.
    If SITE_PASSWORD is not set, the feature is disabled.

    Includes IP-based rate limiting to prevent brute-force attacks.
    """
    ip = get_client_ip(request)

    # ── 空密码 = 前端探测请求，不消耗限速次数 ────────────────────────
    if req.password:
        check_password_rate_limit(ip)

    if not cfg.SITE_PASSWORD:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="AI 问答功能未启用。请通知管理员设置以启用此功能。",
        )

    if cfg.SITE_PASSWORD == req.password:
        return {"verified": True, "message": "密码正确"}

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="密码错误",
    )


# ── Async Task Registry ────────────────────────────────────────────────────


class AsyncTask:
    """Represents an async QA task running in background thread."""
    def __init__(self, task_id: str, question: str):
        self.task_id = task_id
        self.question = question
        self.status = "processing"  # processing | completed | error
        self.result: Optional[Dict[str, Any]] = None
        self.error: Optional[str] = None
        self.created_at = datetime.now().isoformat()
        self.completed_at: Optional[str] = None


_tasks: Dict[str, AsyncTask] = {}


# ── Status Endpoint ────────────────────────────────────────────────────────


@router.get("/status")
def get_status():
    """Check if the knowledge base is ready."""
    _get_qa_engine()
    return _qa_status


# ── Async Q&A Endpoints ────────────────────────────────────────────────────


@router.post("/ask-async")
def ask_question_async(
    req: AskRequest,
    request: Request,
    _=Depends(verify_password),
    x_client_id: Optional[str] = Header(None, alias="X-Client-Id"),
):
    """
    Submit question for async processing. Returns immediately with a task_id.

    Enforces multiple rate-limit layers:
      - IP-based: max N questions per time window
      - User cooldown: minimum interval between questions
      - Daily quota: max questions per user per day
      - Concurrent task limit: max in-flight tasks per user
    """
    ip = get_client_ip(request)
    client_id = x_client_id or f"unknown_{uuid.uuid4().hex[:8]}"

    # ════════════════════════════════════════════════════════════════
    #  Rate limiting: check all layers before any resource is used
    # ════════════════════════════════════════════════════════════════
    engine = _get_qa_engine()
    if engine is None:
        log_api_error(client_id, "/ask-async", "知识库不可用")
        raise HTTPException(
            status_code=503,
            detail=_qa_status.get("message", "知识库不可用"),
        )

    # ── Question validation ─────────────────────────────────────────────
    err_msg = validate_question(req.question)
    if err_msg:
        log_api_error(client_id, "/ask-async", err_msg)
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=err_msg)

    check_all_qa_limits(ip, client_id)

    task_id = uuid.uuid4().hex[:12]


    register_task(task_id, client_id)
    task = AsyncTask(task_id=task_id, question=req.question)
    task.client_id = client_id
    _tasks[task_id] = task

    # Log the question submission
    from website.logging_setup import get_session_dir
    session_dir = get_session_dir()
    log_interaction(
        client_id=client_id,
        question=req.question,
        answer="",
        citations=[],
        video_results=[],
        stats={"status": "submitted", "session_dir": str(session_dir)},
        archive_path="",
        extra={"task_id": task_id, "endpoint": "ask-async"},
    )

    def _run():
        try:
            result = engine.ask(
                question=req.question,
                vector_top_k=req.vector_top_k,
                bm25_top_k=req.bm25_top_k,
                context_window=req.context_window,
                vector_score_threshold=req.vector_score_threshold,
                bm25_score_threshold=req.bm25_score_threshold,
                analysis_batch_size=req.analysis_batch_size,
                synthesis_context_window=req.synthesis_context_window,
                synthesis_batch_trigger_count=req.synthesis_batch_trigger_count,
                synthesis_batch_size=req.synthesis_batch_size,
            )
            task.status = "completed"
            task.result = result
            task.completed_at = datetime.now().isoformat()

            # Log completed interaction with full detail
            log_interaction(
                client_id=client_id,
                question=req.question,
                answer=result.get("answer", ""),
                citations=result.get("citations", []),
                video_results=result.get("video_results", []),
                stats=result.get("retrieval", {}),
                archive_path=result.get("archive_path", ""),
                extra={
                    "task_id": task_id,
                    "endpoint": "ask-async",
                    "answer_generated": bool(result.get("answer")),
                    "citation_count": len(result.get("citations", [])),
                    "useful_segment_count": result.get("useful_segment_count", 0),
                    "status": "completed",
                },
            )
        except Exception as e:
            task.status = "error"
            task.error = str(e)
            task.completed_at = datetime.now().isoformat()
            traceback.print_exc()

            # Log the error
            log_interaction(
                client_id=client_id,
                question=req.question,
                answer="",
                citations=[],
                video_results=[],
                stats={},
                archive_path="",
                error=str(e),
                extra={
                    "task_id": task_id,
                    "endpoint": "ask-async",
                    "status": "error",
                },
            )
        finally:
            # Release concurrent task slot regardless of outcome
            unregister_task(task_id, client_id)

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()

    return {
        "task_id": task_id,
        "status": "processing",
        "message": "任务已提交，请通过 task_id 轮询结果",
    }


@router.post("/ask")
def ask_question_sync(
    req: AskRequest,
    request: Request,
    _=Depends(verify_password),
    x_client_id: Optional[str] = Header(None, alias="X-Client-Id"),
):
    """Synchronous ask endpoint — kept for backward compatibility."""
    ip = get_client_ip(request)
    client_id = x_client_id or f"unknown_{uuid.uuid4().hex[:8]}"

    engine = _get_qa_engine()
    if engine is None:
        log_api_error(client_id, "/ask", "知识库不可用")
        raise HTTPException(
            status_code=503,
            detail=_qa_status.get("message", "知识库不可用"),
        )

    # ── Question validation ─────────────────────────────────────────────
    err_msg = validate_question(req.question)
    if err_msg:
        log_api_error(client_id, "/ask", err_msg)
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=err_msg)

    # Rate limiting for sync endpoint too

    check_all_qa_limits(ip, client_id)

    try:

        result = engine.ask(
            question=req.question,
            vector_top_k=req.vector_top_k,
            bm25_top_k=req.bm25_top_k,
            context_window=req.context_window,
            vector_score_threshold=req.vector_score_threshold,
            bm25_score_threshold=req.bm25_score_threshold,
            analysis_batch_size=req.analysis_batch_size,
            synthesis_context_window=req.synthesis_context_window,
            synthesis_batch_trigger_count=req.synthesis_batch_trigger_count,
            synthesis_batch_size=req.synthesis_batch_size,
        )

        # Log the interaction
        log_interaction(
            client_id=client_id,
            question=req.question,
            answer=result.get("answer", ""),
            citations=result.get("citations", []),
            video_results=result.get("video_results", []),
            stats=result.get("retrieval", {}),
            archive_path=result.get("archive_path", ""),
            extra={
                "endpoint": "ask-sync",
                "answer_generated": bool(result.get("answer")),
                "citation_count": len(result.get("citations", [])),
            },
        )

        retrieval = result.get("retrieval", {})
        comprehensiveness = retrieval.get("comprehensiveness") if isinstance(retrieval, dict) else None

        return AskResponse(
            success=True,
            question=req.question,
            answer=result.get("answer", ""),
            citations=result.get("citations", []),
            video_results=result.get("video_results", []),
            stats=retrieval,
            archive_path=result.get("archive_path", ""),
            comprehensiveness=comprehensiveness,
        )
    except Exception as e:
        traceback.print_exc()
        log_interaction(
            client_id=client_id,
            question=req.question,
            answer="",
            citations=[],
            video_results=[],
            stats={},
            archive_path="",
            error=str(e),
            extra={"endpoint": "ask-sync", "status": "error"},
        )
        raise HTTPException(status_code=500, detail=f"问答处理失败: {e}")


@router.get("/ask-async/{task_id}")
def get_ask_async_result(task_id: str):
    """Poll the status/result of an async QA task."""
    task = _tasks.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在或已过期")

    if task.status == "processing":
        return {
            "task_id": task.task_id,
            "status": "processing",
            "question": task.question,
            "created_at": task.created_at,
        }

    if task.status == "error":
        return {
            "task_id": task.task_id,
            "status": "error",
            "question": task.question,
            "error": task.error,
            "created_at": task.created_at,
            "completed_at": task.completed_at,
        }

    # completed
    result = task.result
    retrieval = result.get("retrieval", {})
    comprehensiveness = retrieval.get("comprehensiveness") if isinstance(retrieval, dict) else None
    return {
        "task_id": task.task_id,
        "status": "completed",
        "question": task.question,
        "answer": result.get("answer", ""),
        "citations": result.get("citations", []),
        "video_results": result.get("video_results", []),
        "stats": retrieval,
        "archive_path": result.get("archive_path", ""),
        "comprehensiveness": comprehensiveness,
        "created_at": task.created_at,
        "completed_at": task.completed_at,
    }


# ── Archive Email Endpoint ──────────────────────────────────────────────────


class ArchiveEmailRequest(BaseModel):
    task_id: str
    email: str
    question: Optional[str] = None


@router.post("/archive-email")
def archive_email(req: ArchiveEmailRequest):
    """
    Store an email address associated with an async task.
    This allows notifying users when a long-running task completes.
    """
    from website.logging_setup import get_session_dir
    session_dir = get_session_dir()
    email_log_path = session_dir / "email_requests.jsonl"

    record = {
        "task_id": req.task_id,
        "email": req.email,
        "timestamp": datetime.now().isoformat(),
    }
    if req.question:
        record["question"] = req.question

    with open(email_log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    # Also log via standard interaction log
    log_interaction(
        client_id="email_collection",
        question=f"email_for_task_{req.task_id}",
        answer="",
        citations=[],
        video_results=[],
        stats={},
        archive_path="",
        extra={"type": "email_collection", "task_id": req.task_id, "email": req.email, "question": req.question or ""},
    )

    return {"success": True, "message": "邮箱已记录"}


# ── Build KB Endpoint ──────────────────────────────────────────────────────


@router.post("/build")
def build_knowledge_base(background_tasks: BackgroundTasks, _=Depends(verify_password)):
    """Trigger knowledge base build / update."""
    records_path = Path(cfg.RECORDS_PATH)
    subtitle_root = Path(cfg.SUBTITLE_ROOT)
    kb_dir = Path(cfg.KB_DIR)

    if not records_path.exists():
        raise HTTPException(
            status_code=400,
            detail=f"记录文件不存在: {records_path}，请先上传 download_records.json",
        )
    if not subtitle_root.exists():
        raise HTTPException(
            status_code=400,
            detail=f"字幕目录不存在: {subtitle_root}，请先上传字幕文件",
        )

    try:
        from kb_qa.qa import VideoKnowledgeQA
        from loguru import logger

        engine = VideoKnowledgeQA(
            records_path=records_path,
            subtitle_root=subtitle_root,
            kb_dir=kb_dir,
            embedding_model=cfg.EMBEDDING_MODEL,
            llm_model=cfg.LLM_MODEL,
            api_base=cfg.LLM_API_BASE,
            api_key=cfg.LLM_API_KEY,
            logger=logger,
        )
        stats = engine.build_or_update()

        # Reset engine so next ask uses the new data
        global _qa_engine, _qa_status
        _qa_engine = engine
        _qa_status = {
            "ready": True,
            "message": "知识库构建完成",
            "stats": {
                "segment_count": len(engine.store.segments),
                "parsed_segments": stats["parsed_segments"],
                "updated_segments": stats["updated_segments"],
                "total_segments": stats["total_segments"],
            },
        }

        return {"success": True, **stats}
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"构建失败: {e}")
