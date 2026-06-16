from __future__ import annotations

from http import cookies
from http.server import BaseHTTPRequestHandler
import os
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in os.sys.path:
    os.sys.path.insert(0, str(SRC))

from new_coins_scanner.live_web import (  # noqa: E402
    SESSION_COOKIE_NAME,
    render_live_dashboard_page,
    render_login_page,
    sign_session,
    verify_password,
    verify_session,
)


def _parse_cookies(header_value: str | None) -> cookies.SimpleCookie[str]:
    jar: cookies.SimpleCookie[str] = cookies.SimpleCookie()
    if header_value:
        jar.load(header_value)
    return jar


def _read_form(handler: BaseHTTPRequestHandler) -> dict[str, str]:
    length = int(handler.headers.get("content-length", "0") or "0")
    raw = handler.rfile.read(length).decode("utf-8") if length > 0 else ""
    parsed = parse_qs(raw, keep_blank_values=True)
    return {key: values[-1] for key, values in parsed.items()}


class handler(BaseHTTPRequestHandler):
    def _is_authenticated(self) -> bool:
        jar = _parse_cookies(self.headers.get("Cookie"))
        morsel = jar.get(SESSION_COOKIE_NAME)
        return verify_session(morsel.value if morsel else None)

    def _send_html(self, payload: str, status: int = 200, set_cookie: str | None = None) -> None:
        body = payload.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        if set_cookie:
            self.send_header("Set-Cookie", set_cookie)
        self.end_headers()
        self.wfile.write(body)

    def _redirect(self, location: str, set_cookie: str | None = None) -> None:
        self.send_response(303)
        self.send_header("Location", location)
        self.send_header("Cache-Control", "no-store")
        if set_cookie:
            self.send_header("Set-Cookie", set_cookie)
        self.end_headers()

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/health":
            self._send_html("ok")
            return
        if not self._is_authenticated():
            self._send_html(render_login_page())
            return
        try:
            self._send_html(render_live_dashboard_page())
        except Exception as exc:
            self._send_html(render_login_page(f"runtime error: {exc}"), status=500)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path == "/login":
            form = _read_form(self)
            if not verify_password(form.get("password", "")):
                self._send_html(render_login_page("wrong password"), status=401)
                return
            cookie = (
                f"{SESSION_COOKIE_NAME}={sign_session()}; "
                "HttpOnly; Path=/; Max-Age=1209600; SameSite=Strict; Secure"
            )
            self._redirect("/", set_cookie=cookie)
            return
        if path == "/logout":
            expired = (
                f"{SESSION_COOKIE_NAME}=; "
                "HttpOnly; Path=/; Max-Age=0; SameSite=Strict; Secure"
            )
            self._redirect("/", set_cookie=expired)
            return
        if not self._is_authenticated():
            self._send_html(render_login_page("session expired"), status=401)
            return
        if path == "/action":
            self._send_html(
                render_live_dashboard_page(
                    flash="dashboard actions are disabled in this read-only demo",
                    flash_tone="neutral",
                ),
                status=403,
            )
            return
        self._send_html(render_login_page("unknown route"), status=404)
