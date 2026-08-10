# -*- coding: utf-8 -*-
"""P1: upload quotas + LLM retries + backup includes evidence/staging."""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
TMP = Path(tempfile.mkdtemp(prefix="sms_p1_"))
shutil.rmtree(TMP, ignore_errors=True)
TMP.mkdir(parents=True)
os.environ["DATA_DIR"] = str(TMP)
os.environ["UPLOAD_MAX_FILES"] = "2"
os.environ["UPLOAD_MAX_BATCH_BYTES"] = "1000"
os.environ["UPLOAD_DIR_QUOTA_BYTES"] = "500"
os.environ["UPLOAD_MAX_BYTES"] = "400"
os.environ["LLM_MAX_RETRIES"] = "2"
os.environ["LLM_CIRCUIT_FAILS"] = "99"
os.environ["OPS_TOKEN"] = "test-ops"

sys.path.insert(0, str(ROOT))

from app import config  # noqa: E402
from app.repositories.db import init_meta  # noqa: E402
from app.services import upload_limits as ul  # noqa: E402
from app.services.backup import create_backup  # noqa: E402
from app.services.llm import model_client as mc  # noqa: E402


def test_upload_limits() -> None:
    init_meta()
    config.UPLOAD.mkdir(parents=True, exist_ok=True)
    config.UPLOAD_TMP.mkdir(parents=True, exist_ok=True)
    # empty dir ok
    ul.assert_dir_quota(incoming_bytes=0)
    ul.assert_batch_limits(file_count=2, batch_bytes=900)
    try:
        ul.assert_batch_limits(file_count=3, batch_bytes=10)
        raise AssertionError("expected MAX_FILES")
    except ValueError as e:
        assert "UPLOAD_MAX_FILES" in str(e)
    try:
        ul.assert_batch_limits(file_count=1, batch_bytes=2000)
        raise AssertionError("expected BATCH_BYTES")
    except ValueError as e:
        assert "UPLOAD_MAX_BATCH_BYTES" in str(e)

    # fill quota
    big = config.UPLOAD / "pad.bin"
    big.write_bytes(b"x" * 450)
    try:
        ul.assert_dir_quota(incoming_bytes=100)
        raise AssertionError("expected DIR_QUOTA")
    except ValueError as e:
        assert "UPLOAD_DIR_QUOTA" in str(e)
    big.unlink()


def test_llm_retries() -> None:
    init_meta()
    calls = {"n": 0}

    def fake_http(method, url, payload=None, timeout=30):
        calls["n"] += 1
        if calls["n"] < 3:
            raise TimeoutError("slow")
        return {"choices": [{"message": {"content": '{"a":1}'}}]}

    with mock.patch.object(mc, "_http_json", side_effect=fake_http):
        with mock.patch.object(mc, "circuit_allow", return_value=True):
            res = mc.chat(
                role="fast",
                messages=[{"role": "user", "content": "hi"}],
                task_type="test_retry",
                model="dummy",
                endpoint="http://127.0.0.1:9/v1",
            )
    assert res.ok, res.error
    assert calls["n"] == 3  # 1 + 2 retries


def test_backup_includes_trees() -> None:
    init_meta()
    config.RAW.mkdir(parents=True, exist_ok=True)
    config.STAGING.mkdir(parents=True, exist_ok=True)
    (config.RAW / "e.parquet").write_bytes(b"ev")
    (config.STAGING / "s.parquet").write_bytes(b"st")
    # touch empty dbs so copy path runs
    config.META_DB.parent.mkdir(parents=True, exist_ok=True)
    if not config.META_DB.exists():
        config.META_DB.write_bytes(b"")
    # biz may be created by init — ensure file exists
    from app.repositories.db import writer_conn

    con = writer_conn()
    con.close()
    out = create_backup(tag="p1")
    dest = Path(out["path"])
    assert (dest / "raw_evidence" / "e.parquet").exists()
    assert (dest / "staging" / "s.parquet").exists()
    man = json.loads((dest / "MANIFEST.json").read_text(encoding="utf-8"))
    assert man.get("includes_evidence") is True
    assert man.get("includes_staging") is True


def main() -> None:
    test_upload_limits()
    print("OK upload_limits")
    test_llm_retries()
    print("OK llm_retries")
    test_backup_includes_trees()
    print("OK backup_includes_trees")
    print("P1_LIMITS_OK")


if __name__ == "__main__":
    main()
