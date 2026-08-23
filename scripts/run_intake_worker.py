# -*- coding: utf-8 -*-
"""Standalone intake worker for offline Docker compose (doc 21)."""
from __future__ import annotations

import logging
import time

from app import config
from app.repositories import init_meta
from app.services.intake import claim_next_task, process_parse_evidence, recover_orphan_tasks

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("intake_worker_standalone")


def main() -> None:
    init_meta()
    log.info("standalone intake worker started poll=%ss", config.WORKER_POLL_SEC)
    last_recover = 0.0
    while True:
        now = time.monotonic()
        if now - last_recover > 60:
            n = recover_orphan_tasks()
            if n:
                log.info("recovered %s orphan tasks", n)
            last_recover = now
        task_id = claim_next_task()
        if task_id:
            log.info("processing task %s", task_id)
            process_parse_evidence(task_id)
        else:
            time.sleep(config.WORKER_POLL_SEC)


if __name__ == "__main__":
    main()
