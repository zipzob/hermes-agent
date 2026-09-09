from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from agent import account_usage


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _FakeClient:
    def __init__(self, calls, payload):
        self.calls = calls
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get(self, url, headers):
        self.calls.append({"url": url, "headers": headers})
        return _FakeResponse(self.payload)


@pytest.fixture
def codex_usage_payload():
    return {
        "plan_type": "plus",
        "rate_limit": {
            "primary_window": {
                "used_percent": 21,
                "reset_at": 1779846359,
            },
            "secondary_window": {
                "used_percent": 4,
                "reset_at": 1780230796,
            },
        },
        "credits": {"has_credits": False},
    }


def test_codex_usage_prefers_explicit_live_agent_credentials(monkeypatch, codex_usage_payload):
    calls = []
    monkeypatch.setattr(
        account_usage.httpx,
        "Client",
        lambda timeout: _FakeClient(calls, codex_usage_payload),
    )
    monkeypatch.setattr(
        account_usage,
        "resolve_codex_runtime_credentials",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("legacy auth should not be used")),
    )

    snapshot = account_usage.fetch_account_usage(
        "openai-codex",
        base_url="https://chatgpt.com/backend-api/codex",
        api_key="live-agent-token",
    )

    assert snapshot is not None
    assert snapshot.provider == "openai-codex"
    assert snapshot.plan == "Plus"
    assert [w.label for w in snapshot.windows] == ["Session", "Weekly"]
    assert snapshot.windows[0].used_percent == 21
    assert calls[0]["url"] == "https://chatgpt.com/backend-api/wham/usage"
    assert calls[0]["headers"]["Authorization"] == "Bearer live-agent-token"


def test_codex_usage_labels_duration_when_primary_is_weekly(monkeypatch, codex_usage_payload):
    calls = []
    codex_usage_payload["rate_limit"] = {
        "primary_window": {
            "used_percent": 20,
            "reset_at": 1785104392,
            "limit_window_seconds": 604800,
        },
        "secondary_window": None,
    }
    monkeypatch.setattr(
        account_usage.httpx,
        "Client",
        lambda timeout: _FakeClient(calls, codex_usage_payload),
    )
    snapshot = account_usage.fetch_account_usage(
        "openai-codex",
        base_url="https://chatgpt.com/backend-api/codex",
        api_key="live-agent-token",
    )
    assert snapshot is not None
    assert [window.label for window in snapshot.windows] == ["Weekly"]


def test_codex_usage_handles_independent_short_and_weekly_windows(monkeypatch, codex_usage_payload):
    calls = []
    codex_usage_payload["rate_limit"] = {
        "primary_window": {
            "used_percent": 80,
            "reset_at": 1785104392,
            "limit_window_seconds": 5 * 60 * 60,
        },
        "secondary_window": {
            "used_percent": 20,
            "reset_at": 1785500000,
            "limit_window_seconds": 7 * 24 * 60 * 60,
        },
    }
    codex_usage_payload["additional_rate_limits"] = [{
        "limit_name": "GPT-5.3-Codex-Spark",
        "metered_feature": "codex_bengalfox",
        "rate_limit": {
            "primary_window": {
                "used_percent": 40,
                "reset_at": 1785104904,
                "limit_window_seconds": 5 * 60 * 60,
            },
            "secondary_window": {
                "used_percent": 10,
                "reset_at": 1785500500,
                "limit_window_seconds": 7 * 24 * 60 * 60,
            },
        },
    }]
    monkeypatch.setattr(
        account_usage.httpx,
        "Client",
        lambda timeout: _FakeClient(calls, codex_usage_payload),
    )

    snapshot = account_usage.fetch_account_usage(
        "openai-codex",
        base_url="https://chatgpt.com/backend-api/codex",
        api_key="live-agent-token",
    )

    assert snapshot is not None
    assert [window.label for window in snapshot.windows] == [
        "5-hour",
        "Weekly",
        "GPT-5.3-Codex-Spark 5-hour",
        "GPT-5.3-Codex-Spark weekly",
    ]
    assert [window.scope for window in snapshot.windows] == [
        "general", "general", "model_specific", "model_specific",
    ]
    assert snapshot.windows[-1].limit_id == "codex_bengalfox"


def test_codex_window_period_supports_daily_and_nonstandard_plans():
    assert account_usage._codex_window_period(24 * 60 * 60, "fallback") == "Daily"
    assert account_usage._codex_window_period(2 * 24 * 60 * 60, "fallback") == "2-day"
    assert account_usage._codex_window_period(None, "Session") == "Session"


def test_weekly_window_renders_virtual_daily_pace(monkeypatch):
    monkeypatch.setattr(
        account_usage,
        "_utc_now",
        lambda: datetime(2026, 1, 2, tzinfo=timezone.utc),
    )
    snapshot = account_usage.AccountUsageSnapshot(
        provider="openai-codex",
        source="usage_api",
        fetched_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
        windows=(account_usage.AccountUsageWindow(
            label="Weekly",
            used_percent=20,
            reset_at=datetime(2026, 1, 8, tzinfo=timezone.utc),
            window_seconds=7 * 24 * 60 * 60,
        ),),
    )

    rendered = "\n".join(account_usage.render_account_usage_lines(snapshot))
    assert "virtual daily 14.3% budget vs 20.0% used/day" in rendered
    assert "140.0% of daily pace; 5.7pp over" in rendered


def test_usage_renderer_preserves_over_100_percent():
    snapshot = account_usage.AccountUsageSnapshot(
        provider="openai-codex",
        source="usage_api",
        fetched_at=datetime.now(timezone.utc),
        windows=(account_usage.AccountUsageWindow(label="Daily", used_percent=127),),
    )

    rendered = "\n".join(account_usage.render_account_usage_lines(snapshot))

    assert "Daily: 0% remaining (127% used; 27% over limit)" in rendered
    assert "LIMIT REACHED" in rendered


def test_codex_usage_includes_model_specific_additional_limits(monkeypatch, codex_usage_payload):
    calls = []
    codex_usage_payload["additional_rate_limits"] = [
        {
            "limit_name": "GPT-5.3-Codex-Spark",
            "metered_feature": "codex_bengalfox",
            "rate_limit": {
                "primary_window": {
                    "used_percent": 62,
                    "reset_at": 1785104904,
                    "limit_window_seconds": 604800,
                },
                "secondary_window": None,
            },
        }
    ]
    monkeypatch.setattr(
        account_usage.httpx,
        "Client",
        lambda timeout: _FakeClient(calls, codex_usage_payload),
    )
    snapshot = account_usage.fetch_account_usage(
        "openai-codex",
        base_url="https://chatgpt.com/backend-api/codex",
        api_key="live-agent-token",
    )
    assert snapshot is not None
    assert snapshot.windows[-1].label == "GPT-5.3-Codex-Spark weekly"
    assert snapshot.windows[-1].used_percent == 62
    assert snapshot.windows[-1].window_seconds == 604800


def test_codex_usage_falls_back_to_native_credential_pool(monkeypatch, codex_usage_payload):
    calls = []
    monkeypatch.setattr(
        account_usage.httpx,
        "Client",
        lambda timeout: _FakeClient(calls, codex_usage_payload),
    )
    # Pool fallback fires only on AuthError (the documented "no creds" mode of
    # the resolver), NOT on arbitrary exceptions — see the transient-error guard
    # test below.
    monkeypatch.setattr(
        account_usage,
        "resolve_codex_runtime_credentials",
        lambda **kwargs: (_ for _ in ()).throw(
            account_usage.AuthError("no singleton auth", provider="openai-codex", code="codex_auth_missing")
        ),
    )

    pool_entry = SimpleNamespace(
        runtime_api_key="pooled-token",
        runtime_base_url="https://chatgpt.com/backend-api/codex",
    )
    pool = SimpleNamespace(select=lambda: pool_entry)

    import agent.credential_pool as credential_pool

    monkeypatch.setattr(credential_pool, "load_pool", lambda provider: pool)

    snapshot = account_usage.fetch_account_usage("openai-codex")

    assert snapshot is not None
    assert snapshot.windows[0].label == "Session"
    assert snapshot.windows[1].label == "Weekly"
    assert calls[0]["url"] == "https://chatgpt.com/backend-api/wham/usage"
    assert calls[0]["headers"]["Authorization"] == "Bearer pooled-token"
    # Pool creds have no account_id concept — the ChatGPT-Account-Id header must
    # be omitted rather than sent stale/wrong.
    assert "ChatGPT-Account-Id" not in calls[0]["headers"]




def test_codex_usage_account_id_read_failure_keeps_singleton_token(monkeypatch, codex_usage_payload):
    """When the resolver succeeds but the separate account_id read raises, the
    working singleton token must still be used (best-effort account_id), NOT
    abandoned in favor of a header-less pool credential."""
    calls = []
    monkeypatch.setattr(
        account_usage.httpx,
        "Client",
        lambda timeout: _FakeClient(calls, codex_usage_payload),
    )
    monkeypatch.setattr(
        account_usage,
        "resolve_codex_runtime_credentials",
        lambda **kwargs: {
            "api_key": "singleton-token",
            "base_url": "https://chatgpt.com/backend-api/codex",
        },
    )
    monkeypatch.setattr(
        account_usage,
        "_read_codex_tokens",
        lambda *a, **k: (_ for _ in ()).throw(
            account_usage.AuthError("partial store", provider="openai-codex", code="codex_auth_invalid_shape")
        ),
    )

    import agent.credential_pool as credential_pool

    monkeypatch.setattr(
        credential_pool,
        "load_pool",
        lambda provider: (_ for _ in ()).throw(AssertionError("pool must not be consulted")),
    )

    snapshot = account_usage.fetch_account_usage("openai-codex")

    assert snapshot is not None
    assert calls[0]["headers"]["Authorization"] == "Bearer singleton-token"
    # account_id read failed → header omitted, but the singleton token is kept.
    assert "ChatGPT-Account-Id" not in calls[0]["headers"]




# ── Banked rate-limit reset credits (`/usage reset`) ─────────────────────────


class _FakeResetClient:
    """GET returns the usage payload; POST returns the consume payload."""

    def __init__(self, calls, usage_payload, consume_payload=None):
        self.calls = calls
        self.usage_payload = usage_payload
        self.consume_payload = consume_payload or {}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get(self, url, headers):
        self.calls.append({"method": "GET", "url": url, "headers": headers})
        return _FakeResponse(self.usage_payload)

    def post(self, url, headers=None, json=None):
        self.calls.append({"method": "POST", "url": url, "headers": headers, "json": json})
        return _FakeResponse(self.consume_payload)


def _usage_payload_with_resets(primary_used, secondary_used, banked):
    return {
        "plan_type": "plus",
        "rate_limit": {
            "primary_window": {"used_percent": primary_used, "reset_at": 1779846359},
            "secondary_window": {"used_percent": secondary_used, "reset_at": 1780230796},
        },
        "rate_limit_reset_credits": {"available_count": banked},
        "credits": {"has_credits": False},
    }








def test_redeem_detects_exhausted_model_specific_window(monkeypatch):
    calls = []
    payload = _usage_payload_with_resets(60, 30, 1)
    payload["additional_rate_limits"] = [{
        "limit_name": "GPT-5.3-Codex-Spark",
        "rate_limit": {
            "primary_window": {"used_percent": 100},
            "secondary_window": {"used_percent": 20},
        },
    }]
    monkeypatch.setattr(
        account_usage.httpx,
        "Client",
        lambda timeout: _FakeResetClient(
            calls,
            payload,
            consume_payload={"code": "reset", "windows_reset": 1},
        ),
    )

    result = account_usage.redeem_codex_reset_credit(
        base_url="https://chatgpt.com/backend-api/codex",
        api_key="live-agent-token",
    )

    assert result.redeemed
    assert [call["method"] for call in calls] == ["GET", "POST"]


def test_redeem_force_bypasses_exhaustion_guard(monkeypatch):
    calls = []
    monkeypatch.setattr(
        account_usage.httpx,
        "Client",
        lambda timeout: _FakeResetClient(
            calls,
            _usage_payload_with_resets(60, 30, 2),
            consume_payload={"code": "reset", "windows_reset": 2},
        ),
    )

    result = account_usage.redeem_codex_reset_credit(
        base_url="https://chatgpt.com/backend-api/codex",
        api_key="live-agent-token",
        force=True,
    )

    assert result.redeemed
    assert result.windows_reset == 2
    assert result.available_count == 1  # 2 banked - 1 spent
    assert "1 banked reset remaining" in result.message
    post = [c for c in calls if c["method"] == "POST"][0]
    assert post["url"] == "https://chatgpt.com/backend-api/wham/rate-limit-reset-credits/consume"
    assert post["json"]["redeem_request_id"]  # idempotency key present
    assert "credit_id" not in post["json"]








def test_redeem_missing_credentials_reports_unavailable(monkeypatch):
    monkeypatch.setattr(
        account_usage,
        "_resolve_codex_usage_credentials",
        lambda base_url, api_key: (_ for _ in ()).throw(RuntimeError("no creds")),
    )

    result = account_usage.redeem_codex_reset_credit()

    assert result.status == "unavailable"
    assert "hermes auth" in result.message
