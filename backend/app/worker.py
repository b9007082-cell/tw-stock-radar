import logging
from datetime import date, datetime

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select

from app.config import get_settings
from app.database import SessionLocal, init_db
from app.models import JobRun
from app.services.market_data import OfficialSnapshotClient, upsert_market_rows
from app.services.scanner import run_scan

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def nightly_job() -> None:
    today = date.today()
    with SessionLocal() as session:
        existing = session.scalar(
            select(JobRun).where(
                JobRun.job_name == "nightly_scan",
                JobRun.run_date == today,
                JobRun.status == "SUCCESS",
            )
        )
        if existing:
            logger.info("Nightly scan already completed for %s", today)
            return
        job = JobRun(job_name="nightly_scan", run_date=today, status="RUNNING")
        session.add(job)
        session.commit()
        try:
            imported = upsert_market_rows(
                session, OfficialSnapshotClient().fetch_all()
            )
            generated = run_scan(session)
            job.status = "SUCCESS"
            job.records = generated
            job.message = f"Imported {imported}; generated {generated}"
        except Exception as exc:
            session.rollback()
            job = session.merge(job)
            job.status = "FAILED"
            job.message = str(exc)
            logger.exception("Nightly job failed")
        finally:
            job.finished_at = datetime.utcnow()
            session.commit()


def main() -> None:
    settings = get_settings()
    init_db()
    scheduler = BlockingScheduler(timezone=settings.timezone)
    scheduler.add_job(
        nightly_job,
        CronTrigger(day_of_week="mon-fri", hour=19, minute=0),
        id="nightly_scan",
        max_instances=1,
        coalesce=True,
    )
    logger.info("Worker scheduled for 19:00 %s on weekdays", settings.timezone)
    scheduler.start()


if __name__ == "__main__":
    main()

