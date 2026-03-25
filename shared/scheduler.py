from __future__ import annotations

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger


_scheduler: BackgroundScheduler | None = None


def get_scheduler() -> BackgroundScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = BackgroundScheduler(timezone="Asia/Shanghai")
    return _scheduler


def ensure_scheduler_started() -> BackgroundScheduler:
    scheduler = get_scheduler()
    if not scheduler.running:
        scheduler.start()
    return scheduler


def ensure_interval_job(job_id: str, func, hours: int = 3) -> BackgroundScheduler:
    scheduler = ensure_scheduler_started()
    if not scheduler.get_job(job_id):
        scheduler.add_job(
            func,
            trigger=IntervalTrigger(hours=hours),
            id=job_id,
            replace_existing=True,
        )
        scheduler.pause_job(job_id)
    return scheduler
