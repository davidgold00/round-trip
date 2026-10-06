"""Rate limiter and SEC client guards."""
import time

import pytest

from src.sec_client import MissingUserAgentError, RateLimiter, resolve_user_agent


def test_spacing_is_at_least_one_over_rps():
    rl = RateLimiter(5)
    stamps = []
    fake_now = [0.0]

    def sleep(sec):
        fake_now[0] += sec

    def now():
        return fake_now[0]

    for _ in range(10):
        rl.acquire(_sleep=sleep, _now=now)
        stamps.append(fake_now[0])
    gaps = [b - a for a, b in zip(stamps, stamps[1:])]
    assert all(g >= 0.2 - 1e-9 for g in gaps), gaps


def test_never_more_than_rps_requests_in_any_one_second_window():
    rl = RateLimiter(5)
    t0 = time.monotonic()
    for _ in range(11):
        rl.acquire()
    elapsed = time.monotonic() - t0
    assert elapsed >= 2.0 - 0.05, f"11 calls at 5/s should take about 2s, took {elapsed:.2f}s"
    assert rl.calls == 11


def test_higher_rps_is_faster():
    fast, slow = RateLimiter(50), RateLimiter(5)
    t0 = time.monotonic()
    for _ in range(5):
        fast.acquire()
    fast_t = time.monotonic() - t0
    t0 = time.monotonic()
    for _ in range(5):
        slow.acquire()
    slow_t = time.monotonic() - t0
    assert fast_t < slow_t


def test_limiter_is_thread_safe():
    import threading
    rl = RateLimiter(100)
    errors = []

    def worker():
        try:
            for _ in range(20):
                rl.acquire()
        except Exception as exc:  # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(4)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert not errors
    assert rl.calls == 80


def test_missing_user_agent_is_a_hard_failure(monkeypatch):
    monkeypatch.setenv("SEC_USER_AGENT", "")
    with pytest.raises(MissingUserAgentError):
        resolve_user_agent()
    monkeypatch.setenv("SEC_USER_AGENT", "changeme")
    with pytest.raises(MissingUserAgentError):
        resolve_user_agent()
    monkeypatch.setenv("SEC_USER_AGENT", "no-at-sign-here")
    with pytest.raises(MissingUserAgentError):
        resolve_user_agent()
    monkeypatch.setenv("SEC_USER_AGENT", "Real Person real@example.com")
    assert resolve_user_agent() == "Real Person real@example.com"
