# -*- coding: utf-8 -*-
"""DB connections: SQLite meta (WAL) + DuckDB biz read-only + writer-only write."""
from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from typing import Iterator

import duckdb

from app import config

_meta_lock = threading.RLock()
_writer_lock = threading.RLock()
_writer_paused = threading.Event()
_writer_paused.clear()


class _RWLock:
    """Readers-writer lock (writer-preferring) with per-thread reentrancy.

    Held for the lifetime of a DuckDB connection (biz_conn / writer_conn).
    duckdb 1.x refuses a second connection to the same file whose access mode
    differs from a currently-open connection (A0-4), so read-only and
    read-write connections must never overlap within the process.
    """

    def __init__(self) -> None:
        self._cv = threading.Condition()
        self._readers = 0
        self._reader_depth: dict[int, int] = {}
        self._writer_tid: int | None = None
        self._writer_depth = 0
        self._waiting_writers = 0

    def r_acquire(self) -> None:
        tid = threading.get_ident()
        with self._cv:
            if self._writer_tid == tid:
                # same thread already holds exclusive (nested read while writing)
                self._reader_depth[tid] = self._reader_depth.get(tid, 0) + 1
                self._readers += 1
                return
            if self._reader_depth.get(tid):
                self._reader_depth[tid] += 1
                return
            while self._writer_tid is not None or self._waiting_writers:
                self._cv.wait()
            self._reader_depth[tid] = 1
            self._readers += 1

    def r_release(self) -> None:
        tid = threading.get_ident()
        with self._cv:
            depth = self._reader_depth.get(tid, 0)
            if depth <= 1:
                self._reader_depth.pop(tid, None)
                self._readers -= 1
                if self._readers == 0:
                    self._cv.notify_all()
            else:
                self._reader_depth[tid] = depth - 1

    def w_acquire(self) -> None:
        tid = threading.get_ident()
        with self._cv:
            if self._writer_tid == tid:
                self._writer_depth += 1
                return
            self._waiting_writers += 1
            try:
                while self._writer_tid is not None or self._readers > 0:
                    self._cv.wait()
                self._writer_tid = tid
                self._writer_depth = 1
            finally:
                self._waiting_writers -= 1

    def w_release(self) -> None:
        with self._cv:
            self._writer_depth -= 1
            if self._writer_depth == 0:
                self._writer_tid = None
                self._cv.notify_all()


_rw_lock = _RWLock()
_bootstrap_lock = threading.Lock()
_bootstrapped_paths: set[str] = set()


class _LockedConn:
    """Delegating proxy that releases the readers-writer lock on close()."""

    __slots__ = ("_con", "_release")

    def __init__(self, con: duckdb.DuckDBPyConnection, release) -> None:
        object.__setattr__(self, "_con", con)
        object.__setattr__(self, "_release", release)

    def close(self) -> None:
        con = object.__getattribute__(self, "_con")
        if con is None:
            return
        object.__setattr__(self, "_con", None)
        try:
            con.close()
        finally:
            object.__getattribute__(self, "_release")()

    def __getattr__(self, name):
        con = object.__getattribute__(self, "_con")
        return getattr(con, name)

    def __enter__(self) -> "_LockedConn":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


def meta_conn() -> sqlite3.Connection:
    config.ensure_dirs()
    con = sqlite3.connect(str(config.META_DB), check_same_thread=False, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=NORMAL")
    con.execute("PRAGMA foreign_keys=ON")
    return con


@contextmanager
def meta_tx() -> Iterator[sqlite3.Connection]:
    with _meta_lock:
        con = meta_conn()
        try:
            yield con
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()


def biz_conn() -> "_LockedConn":
    """Read-only business DB (C1), readers-writer locked (A0-4).

    The returned connection must be closed by the caller (releases the shared
    lock). Read-only and read-write connections never overlap in-process.
    """
    _bootstrap_biz()
    _rw_lock.r_acquire()
    try:
        con = duckdb.connect(str(config.BIZ_DB), read_only=True)
    except BaseException:
        _rw_lock.r_release()
        raise
    return _LockedConn(con, _rw_lock.r_release)


def writer_conn() -> "_LockedConn":
    """ONLY call from writer module while holding writer lock (D2). Exclusive (A0-4).

    The returned connection must be closed by the caller (releases the
    exclusive lock), so no read-only connection can overlap this write window.
    """
    _bootstrap_biz()
    _rw_lock.w_acquire()
    try:
        con = duckdb.connect(str(config.BIZ_DB), read_only=False)
    except BaseException:
        _rw_lock.w_release()
        raise
    return _LockedConn(con, _rw_lock.w_release)


@contextmanager
def readonly_probe() -> Iterator[duckdb.DuckDBPyConnection]:
    """Health/ready probe: shared-locked read-only SELECT, no bootstrap side effects."""
    _rw_lock.r_acquire()
    try:
        con = duckdb.connect(str(config.BIZ_DB), read_only=True)
        try:
            yield con
        finally:
            con.close()
    finally:
        _rw_lock.r_release()


def _bootstrap_biz() -> None:
    config.ensure_dirs()
    path = str(config.BIZ_DB)
    if path in _bootstrapped_paths:
        return
    with _bootstrap_lock:
        if path in _bootstrapped_paths:
            return
        # bootstrap opens the file read-write to ensure schema; it must take the
        # exclusive lock so it never overlaps an in-flight read-only connection
        # (duckdb 1.x rejects same-file connections with differing access mode).
        _rw_lock.w_acquire()
        try:
            con = duckdb.connect(path)
            try:
                from app.repositories.schema import ensure_biz_schema

                ensure_biz_schema(con)
            finally:
                con.close()
            _bootstrapped_paths.add(path)
        finally:
            _rw_lock.w_release()


def pause_writer() -> None:
    _writer_paused.set()


def resume_writer() -> None:
    _writer_paused.clear()


def writer_is_paused() -> bool:
    return _writer_paused.is_set()


def acquire_writer() -> threading.RLock:
    """Block while backup pause is set; return acquired lock for exclusive write."""
    while True:
        while _writer_paused.is_set():
            _writer_paused.wait(timeout=0.2)
        _writer_lock.acquire()
        if _writer_paused.is_set():
            _writer_lock.release()
            continue
        return _writer_lock


def init_meta() -> None:
    with meta_tx() as con:
        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS file_batch (
                file_id TEXT PRIMARY KEY,
                filename TEXT NOT NULL,
                format TEXT,
                sha256 TEXT,
                stored_path TEXT,
                rows INTEGER DEFAULT 0,
                sheets INTEGER DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'uploaded',
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS intake_task (
                task_id TEXT PRIMARY KEY,
                file_id TEXT,
                filename TEXT,
                task_type TEXT NOT NULL,
                status TEXT NOT NULL,
                progress INTEGER DEFAULT 0,
                message TEXT,
                adapter TEXT,
                heartbeat_at TEXT,
                attempt INTEGER DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                finished_at TEXT,
                FOREIGN KEY (file_id) REFERENCES file_batch(file_id)
            );

            CREATE TABLE IF NOT EXISTS intake_report (
                report_id TEXT PRIMARY KEY,
                file_id TEXT NOT NULL,
                report_type TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (file_id) REFERENCES file_batch(file_id)
            );

            CREATE TABLE IF NOT EXISTS staging_record (
                staging_id TEXT PRIMARY KEY,
                file_id TEXT NOT NULL,
                config_version TEXT NOT NULL,
                target_domain TEXT NOT NULL,
                source_file_hash TEXT NOT NULL,
                status TEXT NOT NULL,
                fingerprint TEXT,
                dry_run_json TEXT,
                impact_json TEXT,
                clean_rows INTEGER DEFAULT 0,
                blocked_rows INTEGER DEFAULT 0,
                version INTEGER DEFAULT 1,
                release_id TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                UNIQUE (source_file_hash, config_version, target_domain),
                FOREIGN KEY (file_id) REFERENCES file_batch(file_id)
            );

            CREATE TABLE IF NOT EXISTS release_manifest (
                release_id TEXT PRIMARY KEY,
                file_id TEXT NOT NULL,
                config_version TEXT NOT NULL,
                staging_id TEXT,
                staging_report_id TEXT,
                clean_rows INTEGER DEFAULT 0,
                blocked_rows INTEGER DEFAULT 0,
                material_ops_json TEXT,
                fingerprint TEXT,
                released_by TEXT,
                released_at TEXT NOT NULL DEFAULT (datetime('now')),
                status TEXT NOT NULL DEFAULT 'released'
            );

            CREATE TABLE IF NOT EXISTS write_audit (
                audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
                action TEXT NOT NULL,
                release_id TEXT,
                actor TEXT,
                detail_json TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS govern_confirm (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT,
                detail TEXT,
                decision TEXT,
                note TEXT,
                actor TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS llm_call (
                call_id TEXT PRIMARY KEY,
                role TEXT,
                endpoint TEXT,
                model TEXT,
                task_type TEXT,
                model_state TEXT,
                ok INTEGER,
                latency_ms INTEGER,
                prompt_chars INTEGER,
                error TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS ask_log (
                log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                question TEXT NOT NULL,
                sql TEXT,
                source TEXT,
                metric_id TEXT,
                ok INTEGER NOT NULL,
                degraded INTEGER NOT NULL DEFAULT 0,
                model_state TEXT,
                error TEXT,
                latency_ms INTEGER,
                rows INTEGER,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS rule_dict (
                rule_id INTEGER PRIMARY KEY AUTOINCREMENT,
                header TEXT NOT NULL,
                std_field TEXT NOT NULL,
                business_domain TEXT DEFAULT 'default',
                hits INTEGER DEFAULT 1,
                source TEXT,
                confirmed_by TEXT,
                status TEXT NOT NULL DEFAULT 'active',
                changed_by TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                UNIQUE(header, business_domain, std_field)
            );

            CREATE TABLE IF NOT EXISTS map_pending (
                pending_id TEXT PRIMARY KEY,
                file_id TEXT,
                sheet TEXT,
                header TEXT NOT NULL,
                suggested_field TEXT,
                candidates_json TEXT,
                reason TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                version INTEGER NOT NULL DEFAULT 1,
                business_domain TEXT NOT NULL DEFAULT 'default',
                actor TEXT,
                note TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                UNIQUE(file_id, sheet, header, business_domain)
            );

            CREATE TABLE IF NOT EXISTS idempotency_record (
                idem_key TEXT PRIMARY KEY,
                scope TEXT NOT NULL,
                response_json TEXT NOT NULL,
                request_id TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS flow_pending (
                pending_id TEXT PRIMARY KEY,
                file_id TEXT,
                source_sheet TEXT,
                source_row INTEGER,
                source_segment INTEGER,
                flow_type TEXT,
                text_raw TEXT NOT NULL,
                text_norm TEXT,
                parse_level TEXT,
                suggested_json TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                version INTEGER NOT NULL DEFAULT 1,
                conflict INTEGER DEFAULT 0,
                llm_state TEXT NOT NULL DEFAULT 'none',
                llm_role TEXT,
                llm_error TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS material_align (
                align_id TEXT PRIMARY KEY,
                from_material_id TEXT NOT NULL,
                to_material_id TEXT NOT NULL,
                from_name TEXT,
                to_name TEXT,
                score REAL,
                match_kind TEXT,
                status TEXT NOT NULL DEFAULT 'proposed',
                version INTEGER NOT NULL DEFAULT 1,
                note TEXT,
                actor TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                UNIQUE(from_material_id, to_material_id)
            );

            CREATE TABLE IF NOT EXISTS master_pending (
                pending_id TEXT PRIMARY KEY,
                material_id TEXT,
                material_code TEXT,
                material_name TEXT,
                spec TEXT,
                unit TEXT,
                category TEXT,
                source_file TEXT,
                source_release_id TEXT,
                match_level TEXT NOT NULL DEFAULT 'L3',
                conflict_type TEXT,
                candidates_json TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                version INTEGER NOT NULL DEFAULT 1,
                decided_by TEXT,
                decided_at TEXT,
                note TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                UNIQUE(material_id)
            );

            CREATE TABLE IF NOT EXISTS flow_example (
                example_id TEXT PRIMARY KEY,
                text_norm TEXT NOT NULL UNIQUE,
                flow_json TEXT NOT NULL,
                level TEXT,
                hits INTEGER DEFAULT 1,
                confirmed_by TEXT,
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS flow_config (
                config_id TEXT PRIMARY KEY,
                source_sheet TEXT NOT NULL,
                config_json TEXT NOT NULL,
                version INTEGER DEFAULT 1,
                confirmed_by TEXT,
                updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                UNIQUE(source_sheet)
            );

            CREATE TABLE IF NOT EXISTS flow_reconcile_gap (
                gap_id INTEGER PRIMARY KEY AUTOINCREMENT,
                material_id TEXT,
                stock_qty DOUBLE,
                flow_net DOUBLE,
                gap DOUBLE,
                source_file TEXT,
                computed_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS metric_dict (
                metric_id TEXT PRIMARY KEY,
                metric_name TEXT NOT NULL,
                aliases TEXT,
                unit TEXT,
                definition TEXT,
                definition_sql TEXT NOT NULL,
                drilldown_template TEXT,
                source_tables TEXT,
                dimensions TEXT,
                allowed_dimensions TEXT,
                status TEXT NOT NULL DEFAULT 'draft',
                version INTEGER NOT NULL DEFAULT 1,
                engine TEXT NOT NULL DEFAULT 'biz',
                metric_group TEXT NOT NULL DEFAULT 'business',
                data_check_sql TEXT,
                confirmed_by TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS sql_fewshot (
                fewshot_id TEXT PRIMARY KEY,
                question_type TEXT,
                question TEXT NOT NULL,
                sql_gold TEXT NOT NULL,
                hits INTEGER DEFAULT 0,
                source TEXT,
                confirmed_by TEXT,
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS staging_blocked (
                block_id TEXT PRIMARY KEY,
                staging_id TEXT NOT NULL,
                file_id TEXT NOT NULL,
                target_domain TEXT NOT NULL,
                source_row INTEGER,
                header TEXT,
                reason_code TEXT NOT NULL,
                reason_detail TEXT,
                raw_value TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS value_rule (
                rule_id TEXT PRIMARY KEY,
                domain TEXT NOT NULL,
                std_field TEXT NOT NULL,
                check_type TEXT NOT NULL,
                params_json TEXT,
                severity TEXT NOT NULL DEFAULT 'block',
                status TEXT NOT NULL DEFAULT 'proposed',
                confirmed_by TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS report_definition (
                report_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                query_sql TEXT NOT NULL,
                params_json TEXT,
                cron_expr TEXT,
                active INTEGER DEFAULT 1,
                created_by TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS report_run (
                run_id TEXT PRIMARY KEY,
                report_id TEXT NOT NULL,
                status TEXT NOT NULL,
                started_at TEXT,
                finished_at TEXT,
                artifact_path TEXT,
                row_count INTEGER,
                error TEXT
            );

            CREATE TABLE IF NOT EXISTS metric_snapshot (
                snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
                metric_id TEXT NOT NULL,
                value DOUBLE,
                unit TEXT,
                status TEXT,
                evaluated_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS correction_request (
                correction_id TEXT PRIMARY KEY,
                release_id TEXT NOT NULL,
                row_key TEXT NOT NULL,
                field TEXT NOT NULL,
                value_new TEXT,
                reason TEXT,
                status TEXT NOT NULL DEFAULT 'proposed',
                actor TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE INDEX IF NOT EXISTS idx_intake_task_status ON intake_task(status);
            CREATE INDEX IF NOT EXISTS idx_staging_file ON staging_record(file_id);
            CREATE INDEX IF NOT EXISTS idx_staging_status ON staging_record(status);
            CREATE INDEX IF NOT EXISTS idx_flow_pending_status ON flow_pending(status);
            CREATE INDEX IF NOT EXISTS idx_flow_example_norm ON flow_example(text_norm);
            CREATE INDEX IF NOT EXISTS idx_metric_status ON metric_dict(status);
            CREATE INDEX IF NOT EXISTS idx_staging_blocked_sid ON staging_blocked(staging_id);
            CREATE INDEX IF NOT EXISTS idx_staging_blocked_code ON staging_blocked(reason_code);
            CREATE INDEX IF NOT EXISTS idx_metric_snapshot_mid ON metric_snapshot(metric_id, evaluated_at);
            CREATE INDEX IF NOT EXISTS idx_report_run_rid ON report_run(report_id);
            CREATE INDEX IF NOT EXISTS idx_ask_log_ts ON ask_log(created_at);
            """
        )
        # Soft migrations for existing meta DBs
        cols = {
            r[1]
            for r in con.execute("PRAGMA table_info(flow_pending)").fetchall()
        }
        if "llm_state" not in cols:
            con.execute(
                "ALTER TABLE flow_pending ADD COLUMN llm_state TEXT NOT NULL DEFAULT 'none'"
            )
        if "llm_role" not in cols:
            con.execute("ALTER TABLE flow_pending ADD COLUMN llm_role TEXT")
        if "llm_error" not in cols:
            con.execute("ALTER TABLE flow_pending ADD COLUMN llm_error TEXT")
        if "version" not in cols:
            con.execute(
                "ALTER TABLE flow_pending ADD COLUMN version INTEGER NOT NULL DEFAULT 1"
            )
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_flow_pending_llm ON flow_pending(status, llm_state)"
        )
        # release_manifest supersede cols (P1-4)
        rm_cols = {
            r[1]
            for r in con.execute("PRAGMA table_info(release_manifest)").fetchall()
        }
        if "supersedes" not in rm_cols:
            con.execute("ALTER TABLE release_manifest ADD COLUMN supersedes TEXT")
        if "superseded_by" not in rm_cols:
            con.execute("ALTER TABLE release_manifest ADD COLUMN superseded_by TEXT")
        # metric_dict cols (U-1/U-3/U-4): metric_group + data_check_sql
        md_cols = {
            r[1]
            for r in con.execute("PRAGMA table_info(metric_dict)").fetchall()
        }
        if "metric_group" not in md_cols:
            con.execute(
                "ALTER TABLE metric_dict ADD COLUMN metric_group TEXT NOT NULL DEFAULT 'business'"
            )
        if "data_check_sql" not in md_cols:
            con.execute("ALTER TABLE metric_dict ADD COLUMN data_check_sql TEXT")
        # pending board optimistic concurrency (optv1/08): version columns
        mp_cols = {
            r[1]
            for r in con.execute("PRAGMA table_info(map_pending)").fetchall()
        }
        if "version" not in mp_cols:
            con.execute(
                "ALTER TABLE map_pending ADD COLUMN version INTEGER NOT NULL DEFAULT 1"
            )
        ma_cols = {
            r[1]
            for r in con.execute("PRAGMA table_info(material_align)").fetchall()
        }
        if "version" not in ma_cols:
            con.execute(
                "ALTER TABLE material_align ADD COLUMN version INTEGER NOT NULL DEFAULT 1"
            )
        mdp_cols = {
            r[1]
            for r in con.execute("PRAGMA table_info(master_pending)").fetchall()
        }
        if "version" not in mdp_cols:
            con.execute(
                "ALTER TABLE master_pending ADD COLUMN version INTEGER NOT NULL DEFAULT 1"
            )
        # rule_dict status cols (optv1/04 规则资产: 启用/停用/预演)
        rd_cols = {
            r[1]
            for r in con.execute("PRAGMA table_info(rule_dict)").fetchall()
        }
        if "status" not in rd_cols:
            con.execute(
                "ALTER TABLE rule_dict ADD COLUMN status TEXT NOT NULL DEFAULT 'active'"
            )
        if "changed_by" not in rd_cols:
            con.execute("ALTER TABLE rule_dict ADD COLUMN changed_by TEXT")
        if "updated_at" not in rd_cols:
            # SQLite ADD COLUMN 不允许非常量默认值；先加可空列再回填
            con.execute("ALTER TABLE rule_dict ADD COLUMN updated_at TEXT")
            con.execute(
                "UPDATE rule_dict SET updated_at = datetime('now') WHERE updated_at IS NULL"
            )
        # Ensure new tables exist on older DBs (CREATE IF NOT EXISTS already in block;
        # re-run key DDLs defensively for DBs created before this revision)
        for ddl in (
            """CREATE TABLE IF NOT EXISTS staging_blocked (
                block_id TEXT PRIMARY KEY, staging_id TEXT NOT NULL, file_id TEXT NOT NULL,
                target_domain TEXT NOT NULL, source_row INTEGER, header TEXT,
                reason_code TEXT NOT NULL, reason_detail TEXT, raw_value TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')))""",
            """CREATE TABLE IF NOT EXISTS value_rule (
                rule_id TEXT PRIMARY KEY, domain TEXT NOT NULL, std_field TEXT NOT NULL,
                check_type TEXT NOT NULL, params_json TEXT,
                severity TEXT NOT NULL DEFAULT 'block',
                status TEXT NOT NULL DEFAULT 'proposed', confirmed_by TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')))""",
            """CREATE TABLE IF NOT EXISTS report_definition (
                report_id TEXT PRIMARY KEY, name TEXT NOT NULL, query_sql TEXT NOT NULL,
                params_json TEXT, cron_expr TEXT, active INTEGER DEFAULT 1,
                created_by TEXT, created_at TEXT NOT NULL DEFAULT (datetime('now')))""",
            """CREATE TABLE IF NOT EXISTS report_run (
                run_id TEXT PRIMARY KEY, report_id TEXT NOT NULL, status TEXT NOT NULL,
                started_at TEXT, finished_at TEXT, artifact_path TEXT,
                row_count INTEGER, error TEXT)""",
            """CREATE TABLE IF NOT EXISTS metric_snapshot (
                snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT, metric_id TEXT NOT NULL,
                value DOUBLE, unit TEXT, status TEXT,
                evaluated_at TEXT NOT NULL DEFAULT (datetime('now')))""",
            """CREATE TABLE IF NOT EXISTS correction_request (
                correction_id TEXT PRIMARY KEY, release_id TEXT NOT NULL,
                row_key TEXT NOT NULL, field TEXT NOT NULL, value_new TEXT, reason TEXT,
                status TEXT NOT NULL DEFAULT 'proposed', actor TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')))""",
        ):
            con.execute(ddl)
