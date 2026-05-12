"""
FastAPI router that wraps the transcript_analyze/kb_qa system into REST endpoints.

Gracefully handles cases where the knowledge base hasn't been built yet.
"""
from __future__ import annotations

import json
import os
import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel

from website.auth import verify_password

# ── Import transcript_analyze (add parent to path) ──
_KB_QA_DIR = Path(__file__).resolve().parent.parent.parent / "transcript_analyze"
if str(_KB_QA_DIR) not in sys.path:
    sys.path.insert(0, str(_KB_QA_DIR))

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


# ── Request / Response Models ──────────────────────────────────────────────


class AskRequest(BaseModel):
    question: str
    vector_top_k: int = 1000
    bm25_top_k: int = 1000
    context_window: int = 3
    vector_score_threshold: float = 0.3
    bm25_score_threshold: float = 15.0
    analysis_batch_size: int = 20
    synthesis_context_window: int = 6
    synthesis_batch_trigger_count: int = 100
    synthesis_batch_size: int = 50


class AskResponse(BaseModel):
    success: bool
    question: str
    answer: str
    citations: List[Dict[str, Any]]
    video_results: List[Dict[str, Any]]
    stats: Dict[str, Any]
    archive_path: str = ""


# ── Password Verification (frontend helper) ────────────────────────────────


class PasswordVerifyRequest(BaseModel):
    password: str


@router.post("/verify-password")
def verify_site_password(req: PasswordVerifyRequest):
    """
    Frontend uses this to verify the site password.
    Returns success if password matches (or if no password is configured).
    """
    if not cfg.SITE_PASSWORD:
        return {"verified": True, "message": "未设置密码，无需验证"}

    if cfg.SITE_PASSWORD == req.password:
        return {"verified": True, "message": "密码正确"}

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="密码错误",
    )


# ── Status Endpoint ────────────────────────────────────────────────────────


@router.get("/status")
def get_status():
    """Check if the knowledge base is ready."""
    _get_qa_engine()
    return _qa_status


# ── Q&A Endpoint ───────────────────────────────────────────────────────────


@router.post("/ask", response_model=AskResponse)
def ask_question(req: AskRequest, _=Depends(verify_password)):
    """Ask a question against the video transcript knowledge base."""
    engine = _get_qa_engine()
    if engine is None:
        raise HTTPException(
            status_code=503,
            detail=_qa_status.get("message", "知识库不可用"),
        )

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

        return AskResponse(
            success=True,
            question=req.question,
            answer=result.get("answer", ""),
            citations=result.get("citations", []),
            video_results=result.get("video_results", []),
            stats=result.get("retrieval", {}),
            archive_path=result.get("archive_path", ""),
        )
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"问答处理失败: {e}")


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
