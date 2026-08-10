# -*- coding: utf-8 -*-
"""Background intake + flow LLM worker thread."""
from __future__ import annotations

import logging
import threading
import time

from app import config
from app.services.intake import (
    claim_next_task,
    process_parse_evidence,
    recover_orphan_tasks,
)
from app.repositories import meta_conn

log = logging.getLogger("intake_worker")


class IntakeWorker:
    def __init__(self) -> None:
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_recover = 0.0
        self._last_snapshot = 0.0

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="intake-worker", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)

    def is_alive(self) -> bool:
        """True if the worker thread is currently running (A2-2 readiness probe)."""
        return self._thread is not None and self._thread.is_alive()

    def _maybe_recover(self) -> None:
        # Mid-run reclaim without process restart (docs/03 §3.1)
        now = time.time()
        if now - self._last_recover < 30:
            return
        self._last_recover = now
        try:
            n = recover_orphan_tasks()
            if n:
                log.warning("requeued %s stale processing task(s)", n)
        except Exception:
            log.exception("orphan recovery failed")

    def _maybe_snapshot(self) -> None:
        # UI-3：业务指标历史快照（间隔配置化，避免与首屏评价抢写）
        interval = max(5, int(getattr(config, "METRIC_SNAPSHOT_MINUTES", 30))) * 60
        now = time.time()
        if now - self._last_snapshot < interval:
            return
        self._last_snapshot = now
        try:
            from app.services.metrics import snapshot_business_metrics

            out = snapshot_business_metrics(actor="system:cron")
            if out.get("snapshotted") or out.get("failed"):
                log.info(
                    "metric snapshot: %s ok / %s skipped / %s failed",
                    out.get("snapshotted"),
                    out.get("skipped_no_data"),
                    out.get("failed"),
                )
        except Exception:
            log.exception("metric snapshot tick failed")

    def _dispatch(self, task_id: str) -> None:
        con = meta_conn()
        try:
            row = con.execute(
                "SELECT task_type FROM intake_task WHERE task_id=?", [task_id]
            ).fetchone()
        finally:
            con.close()
        ttype = (row["task_type"] if row else None) or "parse_evidence"
        if ttype == "analyze":
            from app.services.intake_analyze import process_analyze_task

            process_analyze_task(task_id)
        else:
            process_parse_evidence(task_id)

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self._maybe_recover()
                tid = claim_next_task()
                if tid:
                    self._dispatch(tid)
                    continue
                # Phase B: drain a small flow_pending LLM batch when idle
                if config.FLOW_LLM_ENABLED:
                    from app.services.flow_llm import process_pending_batch

                    batch = process_pending_batch(limit=config.FLOW_LLM_BATCH)
                    if batch.get("processed"):
                        continue
                # P2-3: at most one due cron report per idle tick
                try:
                    from app.services.report_runner import process_due_report_once

                    due = process_due_report_once()
                    if due and due.get("ok"):
                        continue
                except Exception:
                    log.exception("report cron tick failed")
                self._maybe_snapshot()
                self._stop.wait(config.WORKER_POLL_SEC)
            except Exception:
                log.exception("worker loop error")
                time.sleep(config.WORKER_POLL_SEC)


worker = IntakeWorker()
