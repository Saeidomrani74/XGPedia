"""تست‌های نسخه v0.50.0 (فاز ۷) — انتشار همزمان چندپلتفرمی (بله، ایتا، ایکس، اینستاگرام)."""
from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from src.xgpedia.publishers import omnichannel as om


def test_strip_html_and_fit_tweet_text() -> None:
    plain = om.strip_html_for_plain("<b>آرسنال × لیورپول</b><br>تحلیل <i>امید گل</i>")
    assert plain == "آرسنال × لیورپول\nتحلیل امید گل"

    long_txt = "آرسنال " * 80
    tw = om.fit_tweet_text(long_txt)
    assert len(tw) <= 276
    assert tw.endswith("…")


def test_omnichannel_status_and_unconfigured_skip() -> None:
    with patch.dict(os.environ, {}, clear=True):
        assert om.list_configured_adapters() == []
        rep = om.format_omnichannel_status_fa()
        assert "بله (Bale)" in rep
        assert "ایتا (Eitaa)" in rep
        assert "ایکس (X)" in rep
        assert "اینستاگرام" in rep
        assert "BALE_BOT_TOKEN" in rep


def test_bale_and_eitaa_broadcast_photo_with_mocked_httpx() -> None:
    class _FakeResp:
        def __init__(self, payload: dict):
            self._p = payload

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return self._p

    calls: list[str] = []

    def _fake_post(url, **kw):
        calls.append(url)
        if "bale.ai" in url:
            return _FakeResp({"ok": True, "result": {"message_id": 701}})
        if "eitaayar.ir" in url:
            return _FakeResp({"ok": True, "result": {"message_id": 802}})
        raise AssertionError(f"Unexpected URL: {url}")

    env = {
        "BALE_BOT_TOKEN": "bale_tok",
        "BALE_CHANNEL_ID": "@xgpedia_bale",
        "EITAA_TOKEN": "eitaa_tok",
        "EITAA_CHAT_ID": "12345",
    }
    with tempfile.TemporaryDirectory() as td:
        img = Path(td) / "card.png"
        img.write_bytes(b"PNGDATA")
        with patch.dict(os.environ, env, clear=True), patch("httpx.post", side_effect=_fake_post):
            outcomes = asyncio.run(om.broadcast_photo(img, "<b>تست انتشار همزمان</b>", title="تست"))
    assert len(outcomes) == 2
    assert all(o.ok for o in outcomes)
    assert any("bale.ai" in u for u in calls)
    assert any("eitaayar.ir" in u for u in calls)


def test_telegram_bot_and_publish_wired_for_omnichannel() -> None:
    tp_src = Path("src/xgpedia/publishers/telegram_publish.py").read_text(encoding="utf-8")
    assert "broadcast_photo" in tp_src
    assert '"omnichannel"' in tp_src

    tb_src = Path("src/xgpedia/publishers/telegram_bot.py").read_text(encoding="utf-8")
    assert 'callback_data="omni:status"' in tb_src
    assert 'Command("platforms")' in tb_src


def test_omnichannel_setup_guide_env_example_and_cli() -> None:
    assert Path("docs/OMNICHANNEL_SETUP_GUIDE_FA.md").exists()
    env_ex = Path(".env.example").read_text(encoding="utf-8")
    for k in ("BALE_BOT_TOKEN", "EITAA_TOKEN", "X_USER_ACCESS_TOKEN", "IG_ACCESS_TOKEN"):
        assert k in env_ex
    rp = Path("run.py").read_text(encoding="utf-8")
    assert "cmd_test_platforms" in rp
    assert '"test-platforms"' in rp
    with patch.dict(os.environ, {}, clear=True):
        res = om.verify_omnichannel_connections()
    assert len(res) == 4
    assert all(not r["configured"] for r in res)


def test_x_oauth_pkce_and_auto_refresh_rotation() -> None:
    from src.xgpedia.publishers import x_oauth as xo

    v, ch = xo.build_pkce_pair()
    assert len(v) >= 43 and len(ch) >= 40
    url = xo.build_authorize_url("cid123", "http://127.0.0.1:8080/callback", "st1", ch)
    assert "offline.access" in url and "tweet.write" in url

    class _FakeResp:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"access_token": "NEW_AT", "refresh_token": "NEW_RT", "expires_in": 7200}

    with tempfile.TemporaryDirectory() as td:
        store = Path(td) / "x_tokens.json"
        # ذخیرهٔ توکن منقضی‌شده
        xo.save_x_tokens({"access_token": "OLD_AT", "refresh_token": "OLD_RT", "expires_at": 100.0}, store)
        with patch.dict(os.environ, {"X_CLIENT_ID": "cid123", "X_CLIENT_SECRET": "csec456"}, clear=True), patch(
            "httpx.post", return_value=_FakeResp()
        ):
            tok = xo.get_valid_x_access_token(store_path=store)
        assert tok == "NEW_AT"
        saved = xo.load_x_tokens(store)
        assert saved["refresh_token"] == "NEW_RT"


def test_cli_registers_x_auth_and_ig_auth_and_ig_direct_mode() -> None:
    rp = Path("run.py").read_text(encoding="utf-8")
    assert 'sub.add_parser("x-auth"' in rp
    assert 'sub.add_parser("ig-auth"' in rp

    ig = om.InstagramAdapter()
    with patch.dict(os.environ, {"IG_SESSIONID": "12345%3Aabc%3A27"}, clear=True):
        assert ig.is_configured() is True
        assert ig._mode() == "direct"
    with patch.dict(os.environ, {"IG_USERNAME": "xgp", "IG_PASSWORD": "sec"}, clear=True):
        assert ig.is_configured() is True
        assert ig._mode() == "direct"
    with patch.dict(os.environ, {"IG_WEBHOOK_URL": "https://hook.make.com/abc"}, clear=True):
        assert ig.is_configured() is True
        assert ig._mode() == "webhook"
