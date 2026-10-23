"""AI addresses passed to the original Console and exported configuration."""
import json

import httpx
import pytest
import yaml

from backend.app.ai import console_ai_endpoint, preview_answer
from backend.app.configuration import PROVIDERS
from backend.app.console_process import ConsoleProcess, console_config
from backend.app.services import PlatformService
from backend.tests.test_platform import platform, add_account
from backend.tests.test_original_console import fake_console


@pytest.mark.parametrize("base", list(PROVIDERS.values()))
def test_provider_base_urls_resolve_to_complete_endpoints(base):
    expected = base.rstrip("/") + "/chat/completions"
    assert console_ai_endpoint(base) == expected
    assert console_ai_endpoint(base + "/") == expected
    assert console_ai_endpoint(expected) == expected
    assert console_ai_endpoint(expected + "/") == expected


@pytest.mark.parametrize("endpoint", [
    "https://ai.example/custom/answer", "https://ai.example/custom/answer/",
    "https://ai.example/v1/text/chatcompletion_v2", "https://ai.example/v1/responses",
])
def test_complete_custom_endpoints_keep_their_request_path(endpoint):
    assert console_ai_endpoint(endpoint) == endpoint


def test_unconfigured_endpoint_stays_empty():
    assert console_ai_endpoint("") == ""
    assert console_ai_endpoint("   ") == ""


def test_disabled_ai_keeps_incomplete_saved_address():
    assert console_ai_endpoint("https://[") == "https://["


@pytest.mark.parametrize("base", [
    "https://ai.example/v1", "https://ai.example/v1/", "https://ai.example/v1/chat/completions",
])
def test_saved_ai_settings_reach_console_and_preview_at_same_endpoint(platform, fake_console, monkeypatch, base):
    config, app, client = platform
    monkeypatch.setattr("backend.app.main.validate_endpoint", lambda _: None)
    monkeypatch.setattr("backend.app.ai.validate_endpoint", lambda _: None)
    account_id = add_account(client)
    response = client.put("/api/settings/ai", json={"enabled": True, "base_url": base,
        "model": "fixture-model", "api_key": "ai-fixture-secret", "api_style": "chat"})
    assert response.status_code == 200
    assert "ai-fixture-secret" not in response.text
    service = PlatformService(app.state.db, app.state.vault)
    account = service.account(account_id)
    value, proxy, secrets = console_config(service, account, service.study_settings(account_id))
    expected = "https://ai.example/v1/chat/completions"
    assert value["setting"]["aiSetting"]["aiUrl"] == expected

    # Read back the private YAML consumed by a real child process.
    ConsoleProcess(config, fake_console).run(account_id, value, proxy, secrets, lambda: None, lambda *_: None, "courses")
    observed = json.loads((config.data_dir / "console" / str(account_id) / "observed.json").read_text())
    settings = observed["config"]["setting"]["aiSetting"]
    assert settings == {"aiType": "OTHER", "aiUrl": expected, "model": "fixture-model", "API_KEY": "ai-fixture-secret"}
    assert not (config.data_dir / "console" / str(account_id) / "config.yaml").exists()

    exported = yaml.safe_load(client.get("/api/configuration/export").text)
    assert exported["setting"]["aiSetting"]["aiUrl"] == expected
    assert exported["setting"]["aiSetting"]["API_KEY"] == ""
    assert service.ai_settings(True)["base_url"] == base

    real_client = httpx.Client
    def handler(request):
        assert str(request.url) == expected
        assert request.method == "POST"
        payload = json.loads(request.content)
        assert payload["model"] == settings["model"]
        assert "messages" in payload
        return httpx.Response(200, json={"choices": [{"message": {"content": "Fixture answer"}}]})
    monkeypatch.setattr("backend.app.ai.httpx.Client", lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs))
    assert preview_answer(service.ai_settings(True), "Fixture question", []) == "Fixture answer"
