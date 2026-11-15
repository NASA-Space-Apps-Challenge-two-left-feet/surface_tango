"""Pure-logic tests for the judging-period on-demand VM (deploy/waker, deploy/vm).

The log lines below are hand-written uvicorn access-log lines, not data.
"""

from deploy.vm import idle_shutdown as idle
from deploy.waker import main as waker

PAGE = 'INFO:     1.2.3.4:5 - "GET / HTTP/1.1" 200 OK'
API = 'INFO:     1.2.3.4:5 - "GET /api/flood-series HTTP/1.1" 200 OK'
API_QUERY = 'INFO:     1.2.3.4:5 - "GET /api/flood-mask?date=2026-06-17 HTTP/1.1" 200 OK'
PROBE = 'INFO:     1.2.3.4:5 - "GET /assets/mission-control.css HTTP/1.1" 200 OK'
STARTUP = "INFO:     Application startup complete."
HOUR = 3600


def test_waker_redirects_only_when_running_and_ready():
    assert waker.decide("RUNNING", True) == "redirect"
    assert waker.decide("RUNNING", False) == "wait"


def test_waker_starts_stopped_and_resumes_suspended():
    assert waker.decide("TERMINATED", False) == "start"
    assert waker.decide("STOPPED", False) == "start"
    assert waker.decide("SUSPENDED", False) == "resume"


def test_waker_waits_through_transitions():
    for status in ("PROVISIONING", "STAGING", "STOPPING", "SUSPENDING", "REPAIRING"):
        assert waker.decide(status, False) == "wait"


def test_waker_target_keeps_path_and_query():
    assert waker.target_url("10.0.0.1") == "http://10.0.0.1:8000/"
    assert waker.target_url("10.0.0.1", "/api/x", "a=1") == "http://10.0.0.1:8000/api/x?a=1"
    assert waker.target_url("10.0.0.1", "static/y") == "http://10.0.0.1:8000/static/y"


def test_probe_path_is_not_counted_as_a_visit():
    assert idle.count_visits(PROBE) == 0
    assert idle.count_visits("\n".join([PAGE, API, API_QUERY, PROBE, STARTUP])) == 3


def test_idle_stops_only_after_grace_with_no_visits():
    assert idle.should_stop(HOUR, PROBE + "\n" + STARTUP, container_running=True)
    assert not idle.should_stop(HOUR, PAGE, container_running=True)
    assert not idle.should_stop(60, "", container_running=True)


def test_idle_leaves_a_broken_stack_up():
    assert not idle.should_stop(HOUR, "", container_running=False)
