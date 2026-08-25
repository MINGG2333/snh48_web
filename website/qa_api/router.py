"""
FastAPI router that wraps the transcript_analyze/kb_qa system into REST endpoints.

Gracefully handles cases where the knowledge base hasn't been built yet.
"""
from __future__ import annotations

import json
import hmac
import os
import re
import secrets
import sys
import threading
import time
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
    check_email_submit_limit,
    get_client_ip,
    get_rate_limiter_stats,
    register_task,
    reset_password_rate_limit,
    unregister_task,
)
from website.action_inbox import InboxError, deterministic_request_id, record_request

# ── Import transcript_analyze (add parent to path) ──
_KB_QA_DIR = Path(__file__).resolve().parent.parent.parent / "transcript_analyze"
if str(_KB_QA_DIR) not in sys.path:
    sys.path.insert(0, str(_KB_QA_DIR))

from kb_qa.config import KB_QA_DEFAULTS
from website import config as cfg

router = APIRouter(prefix="/api/qa", tags=["知识库问答"])

# ── In-memory QA engine (lazy-loaded) ─────────────────────────────────────
_qa_engine: Optional[Any] = None
_qa_engine_loading = False
_qa_engine_lock = threading.Lock()
_qa_status: Dict[str, Any] = {"ready": False, "message": "未初始化", "stats": {}}
_qa_engine_load_thread: Optional[threading.Thread] = None
_qa_engine_load_timer: Optional[threading.Timer] = None
_qa_engine_load_generation = 0
_qa_engine_load_stage = "idle"


def _set_qa_engine_load_stage(stage: str) -> None:
    """Publish a short diagnostic stage without exposing internal exceptions."""
    global _qa_engine_load_stage
    with _qa_engine_lock:
        _qa_engine_load_stage = stage


def _build_qa_engine() -> Any:
    """Build the engine without holding the state lock.

    Loading the segment store, Chroma index and embedding model can take
    minutes on the small production host. Keeping this work outside the lock
    lets health requests continue to respond and lets the watchdog publish a
    useful timeout instead of leaving the API in an eternal loading state.
    """
    print("[QA] loading engine: validating knowledge-base paths", flush=True)
    records_path = Path(cfg.RECORDS_PATH)
    subtitle_root = Path(cfg.SUBTITLE_ROOT)
    kb_dir = Path(cfg.KB_DIR)

    if not records_path.exists():
        raise FileNotFoundError(f"记录文件不存在: {records_path}")
    if not kb_dir.exists() or not (kb_dir / "segment_store.json").exists():
        raise FileNotFoundError("知识库未构建，请先运行 `python run_kb_qa.py build`")

    _set_qa_engine_load_stage("importing_qa_engine")
    print("[QA] loading engine: importing kb_qa", flush=True)
    from kb_qa.qa import VideoKnowledgeQA
    from loguru import logger

    _set_qa_engine_load_stage("constructing_qa_engine")
    print("[QA] loading engine: constructing VideoKnowledgeQA", flush=True)
    return VideoKnowledgeQA(
        records_path=records_path,
        subtitle_root=subtitle_root,
        kb_dir=kb_dir,
        embedding_model=cfg.EMBEDDING_MODEL,
        llm_model=cfg.LLM_MODEL,
        api_base=cfg.LLM_API_BASE,
        api_key=cfg.LLM_API_KEY,
        logger=logger,
    )


def _set_load_error(message: str, *, retryable: bool = True) -> None:
    global _qa_status
    _qa_status = {
        "ready": False,
        "message": message,
        "stats": {},
        "retryable": retryable,
    }


def _finish_qa_engine_load(generation: int, engine: Any = None, error: Optional[Exception] = None) -> None:
    """Publish a load result only if it belongs to the current attempt."""
    global _qa_engine, _qa_engine_loading, _qa_engine_load_thread, _qa_engine_load_timer
    global _qa_engine_load_stage
    global _qa_status

    timer: Optional[threading.Timer] = None
    with _qa_engine_lock:
        if generation != _qa_engine_load_generation:
            return

        if engine is not None:
            _qa_engine = engine
            _qa_status = {
                "ready": True,
                "message": "知识库已加载",
                "stats": {
                    "segment_count": len(engine.store.segments),
                    "kb_dir": str(cfg.KB_DIR),
                },
                "retryable": False,
            }
        elif error is not None:
            print(f"[QA] knowledge-base load failed: {error!r}", flush=True)
            _set_load_error(f"加载失败: {error}")

        _qa_engine_loading = False
        _qa_engine_load_stage = "ready" if engine is not None else "error"
        if _qa_engine_load_thread is threading.current_thread():
            _qa_engine_load_thread = None
        timer = _qa_engine_load_timer
        _qa_engine_load_timer = None

    if timer is not None:
        timer.cancel()


def _mark_qa_engine_load_timeout(generation: int) -> None:
    """Make a stuck background load observable without killing its thread."""
    global _qa_engine_loading, _qa_engine_load_stage
    with _qa_engine_lock:
        if generation != _qa_engine_load_generation or not _qa_engine_loading:
            return
        _qa_engine_loading = False
        _qa_engine_load_stage = "timeout"
        _set_load_error(
            f"知识库加载超时（超过 {cfg.QA_ENGINE_LOAD_TIMEOUT_SECONDS} 秒），请稍后重试",
        )


def _start_qa_engine_load() -> bool:
    """Start one guarded background load attempt."""
    global _qa_engine_loading, _qa_engine_load_thread
    global _qa_engine_load_generation, _qa_engine_load_timer, _qa_status
    global _qa_engine_load_stage

    with _qa_engine_lock:
        if _qa_engine is not None or _qa_engine_loading:
            return False
        if _qa_engine_load_thread is not None and _qa_engine_load_thread.is_alive():
            return False

        _qa_engine_load_generation += 1
        generation = _qa_engine_load_generation
        _qa_engine_loading = True
        _qa_engine_load_stage = "starting"
        _qa_status = {
            "ready": False,
            "message": "知识库正在后台加载",
            "stats": {},
            "retryable": False,
            "started_at": time.time(),
        }

        def _worker() -> None:
            try:
                _set_qa_engine_load_stage("building")
                _finish_qa_engine_load(generation, engine=_build_qa_engine())
            except Exception as exc:
                _finish_qa_engine_load(generation, error=exc)

        thread = threading.Thread(target=_worker, name="qa-engine-warmup", daemon=True)
        _qa_engine_load_thread = thread
        timeout = max(1, int(cfg.QA_ENGINE_LOAD_TIMEOUT_SECONDS))
        timer = threading.Timer(timeout, _mark_qa_engine_load_timeout, args=(generation,))
        timer.daemon = True
        _qa_engine_load_timer = timer

    timer.start()
    thread.start()
    return True


def _get_qa_engine():
    """Return the ready engine, or start a non-blocking load attempt."""
    if _qa_engine is not None:
        return _qa_engine
    _start_qa_engine_load()
    return None


def warmup_qa_engine_async() -> bool:
    """Start QA engine warmup without blocking application requests."""
    return _start_qa_engine_load()


def warmup_qa_engine_sync() -> bool:
    """Load the engine during application startup before serving requests.

    The embedding runtime may initialize native thread pools. Running this one
    time on the startup thread avoids the deadlock observed when that runtime
    is first imported from a daemon worker inside the already-running server.
    """
    global _qa_engine, _qa_engine_loading, _qa_engine_load_generation
    global _qa_engine_load_stage, _qa_status

    with _qa_engine_lock:
        if _qa_engine is not None:
            return False
        if _qa_engine_loading:
            return False
        _qa_engine_load_generation += 1
        generation = _qa_engine_load_generation
        _qa_engine_loading = True
        _qa_engine_load_stage = "starting"
        _qa_status = {
            "ready": False,
            "message": "知识库正在启动加载",
            "stats": {},
            "retryable": False,
        }

    try:
        engine = _build_qa_engine()
    except Exception as exc:
        _finish_qa_engine_load(generation, error=exc)
        return False

    _finish_qa_engine_load(generation, engine=engine)
    return True


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
        # 密码正确 → 清除该 IP 的失败尝试记录，避免之前的错误尝试继续累积
        reset_password_rate_limit(ip)
        return {"verified": True, "message": "密码正确"}

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="密码错误",
    )


# ── Async Task Registry ────────────────────────────────────────────────────


class AsyncTask:
    """Represents an async QA task running in background thread."""
    def __init__(self, task_id: str, question: str, client_id: str, poll_token: str):
        self.task_id = task_id
        self.question = question
        self.client_id = client_id
        self.poll_token = poll_token
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
    global _qa_status
    if _qa_engine is None and not _qa_engine_loading:
        warmup_qa_engine_async()
    with _qa_engine_lock:
        status_payload = dict(_qa_status)
        status_payload["loading"] = _qa_engine_loading
        status_payload["load_stage"] = _qa_engine_load_stage
        status_payload.setdefault("retryable", False)
        status_payload.pop("started_at", None)
    return status_payload


# ── QA Frontend Config Endpoint ─────────────────────────────────────────────

@router.get("/config")
def get_qa_config():
    """
    Return frontend configuration so sensitive parameters
    are not hardcoded in the browser-visible JS.
    """
    return {
        "max_question_length": MAX_QUESTION_LENGTH,
        "timeout_seconds": cfg.QA_TIMEOUT_SECONDS,
        "poll_interval_ms": cfg.QA_POLL_INTERVAL_MS,
        "warn_seconds": cfg.QA_WARN_SECONDS,
        "engine_load_timeout_seconds": cfg.QA_ENGINE_LOAD_TIMEOUT_SECONDS,
    }


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
    poll_token = secrets.token_urlsafe(32)


    register_task(task_id, client_id)
    task = AsyncTask(task_id=task_id, question=req.question, client_id=client_id, poll_token=poll_token)
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

            # ── Copy archive file to session directory ──
            # This ensures the archive is accessible via relative links
            # from user event logs and notification center.
            archive_path = result.get("archive_path", "")
            session_archive_path = ""
            if archive_path:
                src = Path(archive_path)
                if src.exists():
                    # Copy to session dir with same filename
                    dst = session_dir / src.name
                    import shutil
                    shutil.copy2(str(src), str(dst))
                    session_archive_path = dst.name  # relative to session dir
                else:
                    session_archive_path = archive_path

            # Log completed interaction with full detail
            log_interaction(
                client_id=client_id,
                question=req.question,
                answer=result.get("answer", ""),
                citations=result.get("citations", []),
                video_results=result.get("video_results", []),
                stats=result.get("retrieval", {}),
                archive_path=session_archive_path,
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
        "poll_token": poll_token,
        "status": "processing",
        "message": "任务已提交，请通过 task_id 和 poll_token 轮询结果",
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
def get_ask_async_result(
    task_id: str,
    _=Depends(verify_password),
    x_client_id: Optional[str] = Header(None, alias="X-Client-Id"),
    x_poll_token: Optional[str] = Header(None, alias="X-Poll-Token"),
):
    """Poll the status/result of an async QA task."""
    task = _tasks.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在或已过期")
    if not x_client_id or x_client_id != task.client_id:
        raise HTTPException(status_code=403, detail="无权访问该任务结果")
    if not x_poll_token or not hmac.compare_digest(x_poll_token, task.poll_token):
        raise HTTPException(status_code=403, detail="无权访问该任务结果")

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
        "content_safety_flagged": result.get("content_safety_flagged", False),
        "created_at": task.created_at,
        "completed_at": task.completed_at,
    }



# ── Archive Email Endpoint ──────────────────────────────────────────────────


class ArchiveEmailRequest(BaseModel):
    task_id: str
    email: str
    question: Optional[str] = None
    client_id: Optional[str] = None


@router.post("/archive-email")
def archive_email(req: ArchiveEmailRequest, request: Request):
    """
    Store an email address associated with an async task.
    This allows notifying users when a long-running task completes.

    Writes to:
      1. email_requests.jsonl  — 机器可读的 JSONL 日志
      2. email_requests.md     — 人类可读的 Markdown 汇总文件（按时间倒序排列）
      3. notification_center.md — 统一通知中心（汇总所有待处理事件，含处理状态）
    """
    # Rate-limit email submissions to prevent spam
    ip = get_client_ip(request)
    check_email_submit_limit(ip)

    from website.logging_setup import get_session_dir
    session_dir = get_session_dir()
    email_log_path = session_dir / "email_requests.jsonl"
    email_md_path = session_dir / "email_requests.md"
    notification_path = session_dir / "notification_center.md"

    timestamp = datetime.now().isoformat()
    time_str = datetime.fromisoformat(timestamp).strftime("%Y-%m-%d %H:%M:%S")

    # ── 尝试查找对应的存档路径 ──
    # 如果是真实 task_id（非 comprehensiveness_request / content_safety_review 等特殊ID），
    # 尝试从 _tasks 中获取 archive_path
    # 优先使用 session 目录下的副本（由 _run() 复制），否则使用原始路径
    archive_path = ""
    if req.task_id not in ("comprehensiveness_request", "content_safety_review", "timeout"):
        task = _tasks.get(req.task_id)
        if task and task.status == "completed" and task.result:
            archive_path = task.result.get("archive_path", "")
            # Check if the archive was copied to session dir
            if archive_path:
                archive_name = Path(archive_path).name
                session_copy = session_dir / archive_name
                if session_copy.exists():
                    archive_path = archive_name  # relative to session dir

    record = {
        "task_id": req.task_id,
        "email": req.email,
        "timestamp": timestamp,
        "archive_path": archive_path,
    }
    if req.question:
        record["question"] = req.question

    inbox_event_id = deterministic_request_id("EMAIL", record)
    try:
        inbox_result = record_request(
            "email_request",
            record,
            event_id=inbox_event_id,
            created_at=timestamp,
        )
    except (InboxError, OSError) as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="邮箱请求保存失败",
        ) from exc

    # 1. 写入 JSONL（机器可读）
    try:
        with open(email_log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError:
        pass

    # 2. 写入 Markdown（人类可读）
    task_type_map = {
        "comprehensiveness_request": "📋 全面性请求",
        "content_safety_review": "🛡️ 内容安全审核",
    }
    task_type = task_type_map.get(req.task_id, "❓ 其他请求")

    # Generate a unique event_id for cross-referencing with user events
    # Uses client_id (from frontend) or email prefix as fallback
    id_prefix = req.client_id[:6] if req.client_id else (req.email[:6] if req.email else "unknown")
    event_id = f"EVT-{datetime.fromisoformat(timestamp).strftime('%Y%m%d-%H%M%S')}-{id_prefix}"

    # Escape pipe characters in user input to avoid breaking markdown table columns
    safe_question = req.question.replace("|", "\\|") if req.question else ""
    safe_email = req.email.replace("|", "\\|") if req.email else ""
    md_entry = (
        f"---\n"
        f"### 📧 邮箱请求 #{datetime.fromisoformat(timestamp).strftime('%H%M%S')}\n\n"
        f"| 字段 | 内容 |\n"
        f"|------|------|\n"
        f"| **时间** | {time_str} |\n"
        f"| **类型** | {task_type} |\n"
        f"| **邮箱** | `{safe_email}` |\n"
        f"| **事件ID** | `{event_id}` |\n"
        f"| **任务ID** | `{req.task_id}` |\n"
    )
    if safe_question:
        md_entry += f"| **问题** | {safe_question} |\n"
    if archive_path:
        md_entry += f"| **存档路径** | `{archive_path}` |\n"
    md_entry += "\n"

    existing = ""
    try:
        if email_md_path.exists():
            existing = email_md_path.read_text(encoding="utf-8")
        with open(email_md_path, "w", encoding="utf-8") as f:
            f.write("# 📬 用户邮箱请求记录\n\n")
            f.write("> 按时间倒序排列，最新的请求在最前面。\n\n")
            f.write(md_entry)
            f.write(existing)
    except OSError:
        pass

    # 3. 写入统一通知中心
    # 通知中心汇总所有需要管理员关注的事件，包含处理状态跟踪
    event_id = f"EVT-{datetime.fromisoformat(timestamp).strftime('%Y%m%d-%H%M%S')}"
    notification_entry = (
        f"---\n"
        f"### {event_id}\n\n"
        f"| 字段 | 内容 |\n"
        f"|------|------|\n"
        f"| **时间** | {time_str} |\n"
        f"| **类型** | {task_type} |\n"
        f"| **邮箱** | `{safe_email}` |\n"
        f"| **任务ID** | `{req.task_id}` |\n"
    )
    if safe_question:
        notification_entry += f"| **问题** | {safe_question} |\n"
    if archive_path:
        notification_entry += f"| **存档路径** | `{archive_path}` |\n"
    notification_entry += (
        f"| **处理状态** | ⏳ 待处理 |\n"
        f"| **处理备注** | |\n\n"
    )

    existing_notification = ""
    try:
        if notification_path.exists():
            existing_notification = notification_path.read_text(encoding="utf-8")
        with open(notification_path, "w", encoding="utf-8") as f:
            f.write("# 🔔 通知中心\n\n")
            f.write("> 所有需要管理员关注的事件汇总。按时间倒序排列，请及时处理。\n\n")
            f.write("## 待处理事件\n\n")
            f.write(notification_entry)
            f.write(existing_notification)
    except OSError:
        pass

    # Also log via standard interaction log
    try:
        log_interaction(
            client_id="email_collection",
            question=f"email_for_task_{req.task_id}",
            answer="",
            citations=[],
            video_results=[],
            stats={},
            archive_path=archive_path,
            extra={"type": "email_collection", "task_id": req.task_id, "email": req.email, "question": req.question or ""},
        )
    except OSError:
        pass

    return {
        "success": True,
        "message": "邮箱已记录",
        "inbox_event_id": inbox_event_id,
        "origin_node": inbox_result["event"]["origin_node"],
        "origin_label": inbox_result["event"]["origin_label"],
        "replication_pending": not inbox_result["replicated"],
    }


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

        # Reset engine so next ask uses the new data. Invalidate an older
        # background load so it cannot replace this freshly built engine.
        global _qa_engine, _qa_status, _qa_engine_loading
        global _qa_engine_load_generation, _qa_engine_load_thread, _qa_engine_load_timer
        global _qa_engine_load_stage
        timer: Optional[threading.Timer] = None
        with _qa_engine_lock:
            _qa_engine_load_generation += 1
            _qa_engine_loading = False
            _qa_engine_load_stage = "ready"
            _qa_engine_load_thread = None
            timer = _qa_engine_load_timer
            _qa_engine_load_timer = None
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
                "retryable": False,
            }
        if timer is not None:
            timer.cancel()

        return {"success": True, **stats}
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"构建失败: {e}")
