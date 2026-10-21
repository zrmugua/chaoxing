"""Real native-process RPC tests; network protocol fixtures live in Go tests."""
import json
from pathlib import Path
import subprocess
import sys

import pytest

from backend.app.adapters.contracts import AdapterError
from backend.app.adapters.yatori import YatoriAdapter


ROOT = Path(__file__).resolve().parents[2]


def test_engine_identifies_the_pinned_yatori_source():
    pin = json.loads((ROOT / "engine/upstream.json").read_text(encoding="utf-8"))
    console = json.loads((ROOT / "engine/console-upstream.json").read_text(encoding="utf-8"))
    with YatoriAdapter({}) as adapter:
        assert adapter.engine_info == {"engine": "yatori", "upstream": pin["commit"],
                                       "execution": "yatori-go-console", "console_upstream": console["console"]["commit"]}


def test_two_account_processes_have_independent_yatori_caches():
    first = YatoriAdapter({}, [{"name": "_uid", "value": "fixture-account-one", "domain": ".chaoxing.com"}])
    second = YatoriAdapter({}, [{"name": "_uid", "value": "fixture-account-two", "domain": ".chaoxing.com"}])
    try:
        assert first._process.pid != second._process.pid
        assert first.export_cookies()[0]["value"] == "fixture-account-one"
        assert second.export_cookies()[0]["value"] == "fixture-account-two"
        assert first.export_cookies()[0]["value"] == "fixture-account-one"
    finally:
        first.close()
        second.close()


def test_foreign_cookie_domains_are_filtered_by_native_engine():
    with YatoriAdapter({}, [{"name": "x", "value": "fixture", "domain": ".external.invalid"}]) as adapter:
        assert adapter.export_cookies() == []


def test_fresh_process_has_no_previous_account_state():
    with YatoriAdapter({}, [{"name": "_uid", "value": "fixture", "domain": ".chaoxing.com"}]) as adapter:
        assert len(adapter.export_cookies()) == 1
    with YatoriAdapter({}) as adapter:
        assert adapter.export_cookies() == []


def test_cancellation_terminates_the_native_process():
    class Cancelled(Exception):
        pass
    adapter = YatoriAdapter({})
    process = adapter._process
    adapter._control = lambda: (_ for _ in ()).throw(Cancelled())
    with pytest.raises(Cancelled):
        adapter.export_cookies()
    assert process.poll() is not None


def test_cancellation_before_rpc_write_reports_unsent_and_kills_process():
    class Cancelled(Exception):
        pass
    adapter = YatoriAdapter({})
    process = adapter._process
    stream = process.stdin
    writes = []
    class TrackingInput:
        def write(self, value):
            writes.append(value)
            return stream.write(value)
        def flush(self):
            return stream.flush()
        def close(self):
            return stream.close()
    process.stdin = TrackingInput()
    adapter._control = lambda: (_ for _ in ()).throw(Cancelled())
    with pytest.raises(Cancelled) as error:
        adapter.export_cookies()
    assert error.value.rpc_request_sent is False
    assert writes == [] and process.poll() is not None


def test_missing_engine_has_a_sanitized_installation_error(monkeypatch):
    monkeypatch.setenv("YATORI_ENGINE", str(ROOT / "bin" / "not-installed"))
    with pytest.raises(AdapterError) as error:
        YatoriAdapter({"username": "fixture-private-user", "password": "fixture-private-password"})
    assert error.value.code == "core_unavailable"
    assert "fixture-private" not in str(error.value)


def test_vendor_manifest_verifies_all_source_files():
    subprocess.run([sys.executable, "scripts/vendor_yatori.py"], cwd=ROOT, check=True, capture_output=True)
