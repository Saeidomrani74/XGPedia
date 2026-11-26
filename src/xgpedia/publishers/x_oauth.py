"""مدیریت کامل OAuth 2.0 PKCE + تمدید خودکار Access Token / Refresh Token برای ایکس (X / Twitter).

مزایا:
  - دریافت اولیهٔ `access_token` و `refresh_token` با یک دستور (`python run.py x-auth`) و سرور لوکال موقت `127.0.0.1:8080/callback`
  - ذخیرهٔ امن و پایدار توکن‌ها در `data/x_oauth_tokens.json`
  - تمدید خودکار (`grant_type=refresh_token`) پیش از انقضای ۲ساعته یا هنگام دریافت خطای `401` — بدون نیاز به دخالت دستی!
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import threading
import time
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

from src.xgpedia.config import ROOT

X_TOKEN_STORE = ROOT / "data" / "x_oauth_tokens.json"
X_TOKEN_URL = "https://api.x.com/2/oauth2/token"
X_AUTH_URL = "https://x.com/i/oauth2/authorize"
X_SCOPES = "tweet.read tweet.write users.read offline.access"

_LOCK = threading.RLock()


def _store_path(path: Path | None = None) -> Path:
    return path or X_TOKEN_STORE


def load_x_tokens(path: Path | None = None) -> dict[str, Any]:
    p = _store_path(path)
    with _LOCK:
        if p.exists():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return data
            except Exception:
                pass
    # پشتیبان از .env اگر فایل توکن هنوز ساخته نشده باشد
    at = (os.getenv("X_USER_ACCESS_TOKEN") or "").strip()
    rt = (os.getenv("X_REFRESH_TOKEN") or "").strip()
    if at or rt:
        return {"access_token": at, "refresh_token": rt, "expires_at": 0.0}
    return {}


def save_x_tokens(payload: dict[str, Any], path: Path | None = None) -> dict[str, Any]:
    p = _store_path(path)
    now = time.time()
    expires_in = float(payload.get("expires_in") or 7200)
    record = {
        "access_token": str(payload.get("access_token") or "").strip(),
        "refresh_token": str(payload.get("refresh_token") or "").strip(),
        "token_type": str(payload.get("token_type") or "bearer"),
        "scope": str(payload.get("scope") or X_SCOPES),
        "expires_at": round(float(payload.get("expires_at") or (now + expires_in)), 1),
        "updated_at": round(now, 1),
    }
    with _LOCK:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(p)
    return record


def _basic_auth_header(client_id: str, client_secret: str) -> dict[str, str]:
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    if client_id and client_secret:
        b64 = base64.b64encode(f"{client_id}:{client_secret}".encode("utf-8")).decode("ascii")
        headers["Authorization"] = f"Basic {b64}"
    return headers


def refresh_x_access_token(
    *,
    refresh_token: str | None = None,
    client_id: str | None = None,
    client_secret: str | None = None,
    store_path: Path | None = None,
    timeout: float = 20.0,
) -> dict[str, Any]:
    """تمدید خودکار Access Token با استفاده از Refresh Token و ذخیرهٔ توکن‌های چرخشی جدید."""
    import httpx

    cur = load_x_tokens(store_path)
    rt = (refresh_token or cur.get("refresh_token") or os.getenv("X_REFRESH_TOKEN") or "").strip()
    cid = (client_id or os.getenv("X_CLIENT_ID") or "").strip()
    csec = (client_secret or os.getenv("X_CLIENT_SECRET") or "").strip()
    if not rt:
        raise RuntimeError("X_REFRESH_TOKEN در حافظه یا .env یافت نشد؛ یک‌بار دستور `python run.py x-auth` را اجرا کنید.")
    if not cid:
        raise RuntimeError("X_CLIENT_ID در .env تنظیم نشده است.")

    data = {"grant_type": "refresh_token", "refresh_token": rt}
    if not csec:
        data["client_id"] = cid
    headers = _basic_auth_header(cid, csec)

    resp = httpx.post(X_TOKEN_URL, headers=headers, data=data, timeout=timeout)
    resp.raise_for_status()
    j = resp.json()
    if not j.get("access_token"):
        raise RuntimeError(f"پاسخ نامعتبر X هنگام رفرش توکن: {str(j)[:160]}")
    # اگر X رفرش توکن جدید نفرستاد، قبلی را حفظ کن
    if not j.get("refresh_token"):
        j["refresh_token"] = rt
    return save_x_tokens(j, store_path)


def get_valid_x_access_token(*, force_refresh: bool = False, store_path: Path | None = None) -> str:
    """برگرداندن Access Token معتبر X (با تمدید خودکار در صورت نزدیک بودن انقضا یا `force_refresh`)."""
    cur = load_x_tokens(store_path)
    at = str(cur.get("access_token") or "").strip()
    rt = str(cur.get("refresh_token") or "").strip()
    exp = float(cur.get("expires_at") or 0.0)
    now = time.time()

    need_refresh = force_refresh or (not at) or (exp > 0 and (exp - now) < 120.0)
    if need_refresh and rt and (os.getenv("X_CLIENT_ID") or "").strip():
        updated = refresh_x_access_token(refresh_token=rt, store_path=store_path)
        return str(updated.get("access_token") or "").strip()
    return at


def is_x_oauth_configured(store_path: Path | None = None) -> bool:
    cur = load_x_tokens(store_path)
    if cur.get("access_token"):
        return True
    if cur.get("refresh_token") and (os.getenv("X_CLIENT_ID") or "").strip():
        return True
    return False


def build_pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(48)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return verifier, challenge


def build_authorize_url(client_id: str, redirect_uri: str, state: str, code_challenge: str) -> str:
    params = urllib.parse.urlencode({
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": X_SCOPES,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    })
    return f"{X_AUTH_URL}?{params}"


def run_interactive_x_oauth_login(*, store_path: Path | None = None) -> dict[str, Any]:
    """اجرای یک‌بارهٔ احراز هویت OAuth 2.0 PKCE با مرورگر و ذخیرهٔ دائمی Access/Refresh Token."""
    import httpx

    cid = (os.getenv("X_CLIENT_ID") or "").strip()
    csec = (os.getenv("X_CLIENT_SECRET") or "").strip()
    redirect_uri = (os.getenv("X_REDIRECT_URI") or "http://127.0.0.1:8080/callback").strip()
    if not cid:
        raise RuntimeError("ابتدا X_CLIENT_ID (و در صورت انتخاب Web app مقدار X_CLIENT_SECRET) را در فایل .env تنظیم کنید.")

    parsed = urllib.parse.urlparse(redirect_uri)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 8080

    verifier, challenge = build_pkce_pair()
    state = secrets.token_urlsafe(16)
    auth_url = build_authorize_url(cid, redirect_uri, state, challenge)

    result_box: dict[str, str] = {}

    class _CallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if "code" in qs:
                result_box["code"] = qs["code"][0]
                result_box["state"] = (qs.get("state") or [""])[0]
                body = "<h2>XGPedia: Authorization successful! You can close this tab.</h2>".encode("utf-8")
                self.send_response(200)
            else:
                result_box["error"] = (qs.get("error") or ["unknown_error"])[0]
                body = f"<h2>XGPedia: Authorization failed ({result_box['error']})</h2>".encode("utf-8")
                self.send_response(400)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: Any) -> None:
            return

    server = HTTPServer((host, port), _CallbackHandler)
    server.timeout = 180.0
    print("\n=== X (Twitter) OAuth 2.0 Authorization ===")
    print(f"Listening on {redirect_uri} ...")
    print(f"Open this URL in your browser:\n{auth_url}\n")
    try:
        webbrowser.open(auth_url)
    except Exception:
        pass

    server.handle_request()
    server.server_close()

    if "code" not in result_box:
        raise RuntimeError(f"دریافت کد تأیید از X ناموفق بود: {result_box.get('error', 'timeout')}")
    if result_box.get("state") != state:
        raise RuntimeError("مقدار state مطابقت ندارد (CSRF check failed).")

    data = {
        "grant_type": "authorization_code",
        "code": result_box["code"],
        "redirect_uri": redirect_uri,
        "code_verifier": verifier,
    }
    if not csec:
        data["client_id"] = cid
    headers = _basic_auth_header(cid, csec)

    resp = httpx.post(X_TOKEN_URL, headers=headers, data=data, timeout=25.0)
    resp.raise_for_status()
    j = resp.json()
    saved = save_x_tokens(j, store_path)
    print("[OK] X Access Token & Refresh Token saved to data/x_oauth_tokens.json!")
    return saved
