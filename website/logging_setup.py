"""
User interaction logging module.

Provides session-based log management:
 - One directory per server session (named by startup timestamp)
 - One combined log file for all users
 - One per-user log file for each distinct client_id
 - Detailed interaction records (question, answer, citations, video_results, etc.)
"""
from __future__ import annotations

import json
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


# ── Session & Directory Management ──────────────────────────────────────────

# Directory where session logs are stored
LOG_ROOT = Path(__file__).resolve().parent / "data" / "interaction_logs"

# Current session directory (set on import / module init)
_session_dir: Optional[Path] = None
_session_start_time: Optional[str] = None


def get_session_dir() -> Path:
    """Get the current session log directory, creating it if needed."""
    global _session_dir, _session_start_time
    if _session_dir is None:
        _session_start_time = datetime.now().strftime("%Y%m%d_%H%M%S")
        _session_dir = LOG_ROOT / f"session_{_session_start_time}"
        _session_dir.mkdir(parents=True, exist_ok=True)
        _log_system_event(f"Session started at {_session_start_time}")
    return _session_dir


def get_session_start_time() -> str:
    """Get the current session start time string."""
    get_session_dir()  # ensure initialized
    return _session_start_time  # type: ignore[return-value]


def get_combined_log_path() -> Path:
    """Get the combined (all-users) log file path for this session."""
    return get_session_dir() / "combined.jsonl"


def get_user_log_path(client_id: str) -> Path:
    """Get the per-user log file path for a given client_id."""
    return get_session_dir() / f"user_{client_id}.jsonl"


def _log_system_event(message: str) -> None:
    """Write a system-level event to a session event log."""
    event_path = get_session_dir() / "_events.jsonl"
    record = {
        "type": "system_event",
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "message": message,
    }
    _append_jsonl(event_path, record)


# ── Interaction Logging ────────────────────────────────────────────────────


def log_interaction(
    client_id: str,
    question: str,
    answer: str,
    citations: list[dict[str, Any]],
    video_results: list[dict[str, Any]],
    stats: dict[str, Any],
    archive_path: str,
    error: Optional[str] = None,
    extra: Optional[dict[str, Any]] = None,
) -> None:
    """
    Log a QA interaction for a specific user.

    Writes to both the per-user log and the combined log.
    """
    timestamp = datetime.now().isoformat(timespec="seconds")
    record = {
        "client_id": client_id,
        "timestamp": timestamp,
        "question": question,
        "answer": answer,
        "citations": citations,
        "video_results": video_results,
        "stats": stats,
        "archive_path": archive_path,
        "error": error,
    }
    if extra:
        record["extra"] = extra

    # Write combined log
    combined_path = get_combined_log_path()
    _append_jsonl(combined_path, record)

    # Write per-user log
    user_path = get_user_log_path(client_id)
    _append_jsonl(user_path, record)


def log_llm_call(
    client_id: str,
    description: str,
    prompt: str,
    response: str,
    model: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
    success: bool = True,
    error: Optional[str] = None,
) -> None:
    """
    Log an LLM API call for a specific user.
    This provides detailed traceability for debugging.
    """
    timestamp = datetime.now().isoformat(timespec="seconds")
    record = {
        "client_id": client_id,
        "timestamp": timestamp,
        "type": "llm_call",
        "description": description,
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "prompt": prompt,
        "response": response,
        "success": success,
        "error": error,
    }

    # Write to per-user LLM call log
    user_llm_path = get_session_dir() / f"user_{client_id}_llm.jsonl"
    _append_jsonl(user_llm_path, record)

    # Also write combined LLM call log
    combined_llm_path = get_session_dir() / "combined_llm.jsonl"
    _append_jsonl(combined_llm_path, record)


def log_api_error(
    client_id: str,
    endpoint: str,
    error_message: str,
    detail: Optional[dict[str, Any]] = None,
) -> None:
    """Log an API error for debugging."""
    timestamp = datetime.now().isoformat(timespec="seconds")
    record = {
        "client_id": client_id,
        "timestamp": timestamp,
        "type": "api_error",
        "endpoint": endpoint,
        "error": error_message,
        "detail": detail,
    }
    combined_path = get_combined_log_path()
    _append_jsonl(combined_path, record)
    user_path = get_user_log_path(client_id)
    _append_jsonl(user_path, record)


# ── Helpers ────────────────────────────────────────────────────────────────


def _append_jsonl(path: Path, record: dict[str, Any]) -> None:
    """Append a JSON record as a new line to a JSONL file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError as e:
        # Fail silently — logging should not crash the application
        print(f"[logging_setup] Failed to write log: {e}", file=__import__("sys").stderr)


# ── Backup Utilities for qa_archive ────────────────────────────────────────


def backup_and_recreate_qa_archive(kb_dir: Path) -> bool:
    """
    Rename the existing qa_archive directory to a timestamped backup,
    then create a fresh empty qa_archive directory.

    Returns True if backup was performed, False if no backup was needed.
    """
    qa_archive_dir = kb_dir / "qa_archive"
    if not qa_archive_dir.exists():
        # No archive to back up, just create the directory
        qa_archive_dir.mkdir(parents=True, exist_ok=True)
        return False

    # Check if it's already empty — no need to back up
    if not any(qa_archive_dir.iterdir()):
        return False

    # Create backup directory
    backup_name = f"qa_archive_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    backup_dir = kb_dir / backup_name

    try:
        shutil.move(str(qa_archive_dir), str(backup_dir))
        print(f"[logging_setup] Backed up qa_archive → {backup_name}")

        # Recreate empty qa_archive
        qa_archive_dir.mkdir(parents=True, exist_ok=True)
        return True
    except OSError as e:
        print(f"[logging_setup] Failed to backup qa_archive: {e}", file=__import__("sys").stderr)
        # Ensure a usable qa_archive exists
        qa_archive_dir.mkdir(parents=True, exist_ok=True)
        return False
