# -*- coding: utf-8 -*-
"""Stable intake error mapping (doc 16 E1)."""
from __future__ import annotations

import json
from typing import Any, TypedDict


class IntakeErrorInfo(TypedDict):
    error_code: str
    phase: str
    user_message: str
    technical_message: str
    retryable: bool
    next_actions: list[str]


def map_exception_to_error(e: Exception, *, phase: str = "unknown") -> IntakeErrorInfo:
    """Map an exception to a stable intake error object."""
    msg = str(e)
    lower = msg.lower()

    if "conversion failed for column" in lower or "could not convert" in lower:
        return IntakeErrorInfo(
            error_code="TABULAR_PARQUET_TYPE_ERROR",
            phase="write_evidence",
            user_message="标准化表格列类型不一致，系统可在修复规则后重试解析",
            technical_message=msg,
            retryable=True,
            next_actions=[
                "修复 tabular 类型统一规则后点击重试",
                "如持续失败，请导出技术详情交给开发排查",
            ],
        )

    if "unsupported format" in lower:
        return IntakeErrorInfo(
            error_code="UNSUPPORTED_FORMAT",
            phase="load_evidence",
            user_message="文件格式暂不支持，请转换为 xlsx/csv/json 后再上传",
            technical_message=msg,
            retryable=False,
            next_actions=["将文件转换为 xlsx、csv 或 json 后重新上传"],
        )

    phase_write = phase if phase in ("write_evidence",) else phase
    if phase == "write_evidence":
        return IntakeErrorInfo(
            error_code="EVIDENCE_WRITE_FAILED",
            phase="write_evidence",
            user_message="证据文件写入失败，可重试",
            technical_message=msg,
            retryable=True,
            next_actions=["点击重试解析", "如持续失败，请导出技术详情交给开发排查"],
        )

    return IntakeErrorInfo(
        error_code="UNKNOWN_INTAKE_ERROR",
        phase=phase if phase != "unknown" else "unknown",
        user_message="接入任务失败，请查看技术详情",
        technical_message=msg,
        retryable=True,
        next_actions=["点击重试解析", "如持续失败，请导出技术详情交给开发排查"],
    )


def encode_error_message(info: IntakeErrorInfo) -> str:
    """Serialize error info for intake_task.message (ensure_ascii=False for Chinese)."""
    payload: dict[str, Any] = {
        "error_code": info["error_code"],
        "phase": info["phase"],
        "retryable": info["retryable"],
        "next_actions": info["next_actions"],
        "user_message": info["user_message"],
        "technical_message": info["technical_message"],
    }
    return json.dumps(payload, ensure_ascii=False)


def decode_error_message(message: str | None) -> dict[str, Any]:
    """Return flattened error fields; tolerate legacy plain strings."""
    if not message:
        return {
            "error_code": None,
            "phase": None,
            "user_message": None,
            "technical_message": None,
            "retryable": None,
            "next_actions": None,
        }
    try:
        data = json.loads(message)
        if isinstance(data, dict) and "error_code" in data:
            return {
                "error_code": data.get("error_code"),
                "phase": data.get("phase"),
                "user_message": data.get("user_message"),
                "technical_message": data.get("technical_message"),
                "retryable": data.get("retryable"),
                "next_actions": data.get("next_actions"),
            }
    except (json.JSONDecodeError, TypeError):
        pass
    return {
        "error_code": None,
        "phase": None,
        "user_message": message,
        "technical_message": message,
        "retryable": None,
        "next_actions": None,
    }


def cleanup_evidence_files(file_id: str) -> None:
    """Remove half-written evidence artifacts (doc 16 E4)."""
    from app import config

    (config.RAW / f"{file_id}.parquet").unlink(missing_ok=True)
    (config.RAW / f"{file_id}.tabular.parquet").unlink(missing_ok=True)
