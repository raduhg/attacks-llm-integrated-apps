"""Offline test of the Streamlit demo: the app renders, and an attack runs end to end in dry-run
mode (no API call). Uses Streamlit's own headless test runner."""

from __future__ import annotations

from streamlit.testing.v1 import AppTest

from testbed.config import PROJECT_ROOT

APP = str(PROJECT_ROOT / "ui" / "streamlit_app.py")


def test_demo_renders_and_runs_an_attack_in_dry_run() -> None:
    at = AppTest.from_file(APP, default_timeout=120).run()
    assert not at.exception
    assert [t.label for t in at.tabs] == ["Chat", "Attack"]

    at.toggle[0].set_value(True).run()  # dry run: nothing is sent to the API
    assert "planned API calls" in at.sidebar.caption[-1].value  # the tracker is in dry-run mode
    next(b for b in at.button if b.label == "Run attack").click().run()
    assert not at.exception
    assert any("Attack failed" in s.value for s in at.success)  # the dry-run model never calls a tool
    assert any(c.value.startswith("Model call 1:") for c in at.caption)  # the trace is shown
