from scheduler import build_scheduler, run_daily_digest, run_daily_sync


def test_daily_sync_job_registered():
    scheduler = build_scheduler()
    job = scheduler.get_job("daily-sync")
    assert job is not None
    assert job.func is run_daily_sync
    trigger = str(job.trigger)
    assert "hour='7'" in trigger
    assert "minute='0'" in trigger
    assert str(job.trigger.timezone) == "America/New_York"
    assert not scheduler.running


def test_daily_digest_job_registered():
    scheduler = build_scheduler()
    job = scheduler.get_job("daily-digest")
    assert job is not None
    assert job.func is run_daily_digest
    trigger = str(job.trigger)
    assert "hour='7'" in trigger
    assert "minute='30'" in trigger
    assert str(job.trigger.timezone) == "America/New_York"
    assert not scheduler.running
