# -*- coding: utf-8 -*-
"""Doc 16 E1/E2: stable intake error mapping and API flattening."""
from __future__ import annotations

from app.services.intake.error_info import (
    decode_error_message,
    encode_error_message,
    map_exception_to_error,
)


def test_tabular_parquet_type_error_mapping():
    exc = Exception("Conversion failed for column asset_qty with type object")
    info = map_exception_to_error(exc, phase="write_evidence")
    assert info["error_code"] == "TABULAR_PARQUET_TYPE_ERROR"
    assert info["phase"] == "write_evidence"
    assert info["retryable"] is True


def test_json_message_flattened_fields():
    info = map_exception_to_error(Exception("Conversion failed for column qty"), phase="write_evidence")
    msg = encode_error_message(info)
    flat = decode_error_message(msg)
    assert flat["error_code"] == "TABULAR_PARQUET_TYPE_ERROR"
    assert flat["phase"] == "write_evidence"
    assert flat["user_message"]
    assert flat["technical_message"]
    assert flat["retryable"] is True
    assert isinstance(flat["next_actions"], list)


def test_encode_error_message_preserves_chinese():
    info = map_exception_to_error(Exception("test"), phase="unknown")
    msg = encode_error_message(info)
    assert "\\u" not in msg
    assert "接入任务失败" in msg


def test_decode_legacy_plain_string():
    flat = decode_error_message("raw python traceback here")
    assert flat["error_code"] is None
    assert flat["user_message"] == "raw python traceback here"
    assert flat["technical_message"] == "raw python traceback here"


def test_unsupported_format_not_retryable():
    info = map_exception_to_error(Exception("unsupported format: .doc"), phase="load_evidence")
    assert info["error_code"] == "UNSUPPORTED_FORMAT"
    assert info["retryable"] is False
