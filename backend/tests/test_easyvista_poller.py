"""Background status poller (2026-07-01/02): due-date logic + one polling
pass. No live tenant or Postgres required — in-memory SQLite backs Finding
rows, and `easyvista.get_request_status` is monkeypatched (its own request/
response shape is covered by test_easyvista.py).
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.core.database import Base
from app.models.enums import FindingStatus
from app.models.models import EasyVistaSettings, Finding
from app.models.models import Test as Engagement
from app.services import easyvista, easyvista_poller

NOW = datetime(2026, 7, 2, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def poll_env():
    """Deterministic env-fallback poll config, enabled by default here (each
    test's DB row, if any, still overrides per field)."""
    s = get_settings()
    saved = {
        k: getattr(s, k)
        for k in (
            "easyvista_poll_enabled",
            "easyvista_poll_open_interval_seconds",
            "easyvista_poll_closed_interval_seconds",
            "easyvista_poll_closed_lookback_days",
        )
    }
    s.easyvista_poll_enabled = True
    s.easyvista_poll_open_interval_seconds = 3600  # 1h
    s.easyvista_poll_closed_interval_seconds = 86400  # 1d
    s.easyvista_poll_closed_lookback_days = 30
    yield s
    for k, v in saved.items():
        setattr(s, k, v)


def _finding(db, **kwargs):
    test = Engagement(name="Engagement")
    db.add(test)
    db.flush()
    f = Finding(test_id=test.id, status=FindingStatus.open, **kwargs)
    db.add(f)
    db.commit()
    return f


# ---- _is_due ----

def test_never_synced_is_always_due():
    f = Finding(itsm_synced_at=None, itsm_closed=None)
    assert easyvista_poller._is_due(
        f, now=NOW, open_interval=timedelta(hours=1),
        closed_interval=timedelta(days=1), lookback_cutoff=NOW - timedelta(days=30),
    )


def test_open_finding_not_due_within_interval():
    f = Finding(itsm_synced_at=NOW - timedelta(minutes=30), itsm_closed=False)
    assert not easyvista_poller._is_due(
        f, now=NOW, open_interval=timedelta(hours=1),
        closed_interval=timedelta(days=1), lookback_cutoff=NOW - timedelta(days=30),
    )


def test_open_finding_due_after_interval():
    f = Finding(itsm_synced_at=NOW - timedelta(hours=2), itsm_closed=False)
    assert easyvista_poller._is_due(
        f, now=NOW, open_interval=timedelta(hours=1),
        closed_interval=timedelta(days=1), lookback_cutoff=NOW - timedelta(days=30),
    )


def test_closed_finding_uses_closed_interval_not_open():
    # Past the (short) open interval but not the (long) closed interval.
    f = Finding(itsm_synced_at=NOW - timedelta(hours=2), itsm_closed=True)
    assert not easyvista_poller._is_due(
        f, now=NOW, open_interval=timedelta(hours=1),
        closed_interval=timedelta(days=1), lookback_cutoff=NOW - timedelta(days=30),
    )


def test_closed_finding_beyond_lookback_is_never_due_again():
    f = Finding(itsm_synced_at=NOW - timedelta(days=40), itsm_closed=True)
    assert not easyvista_poller._is_due(
        f, now=NOW, open_interval=timedelta(hours=1),
        closed_interval=timedelta(days=1), lookback_cutoff=NOW - timedelta(days=30),
    )


# ---- poll_once ----

def test_poll_once_noop_when_disabled(db):
    s = get_settings()
    saved = s.easyvista_poll_enabled
    s.easyvista_poll_enabled = False
    try:
        _finding(db, itsm_reference="RFC1")
        assert easyvista_poller.poll_once(db) == 0
    finally:
        s.easyvista_poll_enabled = saved


def test_poll_once_refreshes_due_findings(db, poll_env, monkeypatch):
    f1 = _finding(db, itsm_reference="RFC1")  # never synced -> due
    f2 = _finding(  # synced recently -> not due
        db, itsm_reference="RFC2", itsm_closed=False,
    )
    # Relative to real wall time, not the fixed NOW constant — poll_once()
    # computes its own now = datetime.now(timezone.utc) internally.
    f2.itsm_synced_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db.commit()

    calls = []

    def fake_get_request_status(rfc, db_arg, **kw):
        calls.append(rfc)
        return {"status_label": "Closed", "status_guid": "g", "closed": True}

    monkeypatch.setattr(easyvista, "get_request_status", fake_get_request_status)

    before = datetime.now(timezone.utc)
    refreshed = easyvista_poller.poll_once(db)
    after = datetime.now(timezone.utc)

    assert refreshed == 1
    assert calls == ["RFC1"]
    db.refresh(f1)
    assert f1.itsm_status_label == "Closed"
    assert f1.itsm_closed is True
    # SQLite doesn't round-trip tzinfo on DateTime(timezone=True) (unlike
    # Postgres) — normalize before comparing, same as production code does.
    synced_at = easyvista_poller._as_aware_utc(f1.itsm_synced_at)
    assert before <= synced_at <= after


def test_poll_once_skips_findings_without_itsm_reference(db, poll_env, monkeypatch):
    _finding(db, itsm_reference=None)
    monkeypatch.setattr(
        easyvista, "get_request_status",
        lambda *a, **kw: pytest.fail("should not be called"),
    )
    assert easyvista_poller.poll_once(db) == 0


def test_poll_once_continues_after_one_finding_errors(db, poll_env, monkeypatch):
    _finding(db, itsm_reference="RFC-BAD")
    _finding(db, itsm_reference="RFC-GOOD")

    def fake(rfc, db_arg, **kw):
        if rfc == "RFC-BAD":
            raise easyvista.EasyVistaError("boom")
        return {"status_label": "New", "status_guid": None, "closed": None}

    monkeypatch.setattr(easyvista, "get_request_status", fake)
    refreshed = easyvista_poller.poll_once(db)
    assert refreshed == 1  # the good one still got refreshed


def test_db_row_overrides_env_poll_settings(db, poll_env):
    db.add(EasyVistaSettings(id=1, poll_enabled=False))
    db.commit()
    from app.core.easyvista_config import get_easyvista_poll_config

    cfg = get_easyvista_poll_config(db)
    assert cfg.enabled is False  # DB row wins over env's True
    # Blank/unset numeric fields still fall back to env per-field.
    assert cfg.open_interval_seconds == 3600
