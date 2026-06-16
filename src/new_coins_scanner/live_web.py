from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import hmac
import html
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from .config import ScannerConfig, load_config
from .dashboard import render_dashboard_html
from .engine import run_announcement_scan, run_live_scan
from .env import load_dotenv
from .state_views import build_signal_rows, build_top_gainer_rows, selection_counts


SESSION_COOKIE_NAME = "new_coins_session"
SESSION_MAX_AGE_SECONDS = 60 * 60 * 24 * 14


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _config_path() -> Path:
    return _project_root() / "data" / "scanner_config.toml"


def _load_config() -> ScannerConfig:
    path = _config_path()
    return load_config(path if path.exists() else None)


def _live_api_base() -> str | None:
    load_dotenv()
    value = (
        os.environ.get("BINANCE_SPOT_API_BASE")
        or os.environ.get("BINANCE_API_BASE")
        or ""
    ).strip()
    return value or None


def _announcement_rows() -> list[dict[str, Any]]:
    try:
        return [asdict(item) for item in run_announcement_scan()[:20]]
    except Exception as exc:
        return [{"source": "system", "event_type": "error", "symbol_candidates": [], "title": f"announcements: {exc}"}]


def build_live_dashboard_state(*, flash: str | None = None, flash_tone: str = "neutral") -> dict[str, Any]:
    config = _load_config()
    candidates = run_live_scan(config, api_base=_live_api_base())
    universe_counts = selection_counts(candidates)
    updated_at = _now_iso()
    state = {
        "updated_at": updated_at,
        "cycle": {
            "started_at": updated_at,
            "finished_at": updated_at,
            "candidate_count": len(candidates),
            "tracked_universe_count": universe_counts["tracked_universe_count"],
            "top_volume_universe_count": universe_counts["top_volume_universe_count"],
            "top_gainer_universe_count": universe_counts["top_gainer_universe_count"],
        },
        "signals": build_signal_rows(candidates),
        "top_gainers": build_top_gainer_rows(candidates),
        "announcements": _announcement_rows(),
        "errors": [flash] if flash else [],
        "flash": flash or "",
        "flash_tone": flash_tone,
    }
    return state


def _render_dashboard_from_state(state: dict[str, Any]) -> str:
    with NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as handle:
        handle.write(json.dumps(state, indent=2))
        temp_path = handle.name
    try:
        base_html = render_dashboard_html(temp_path)
    finally:
        try:
            Path(temp_path).unlink(missing_ok=True)
        except OSError:
            pass
    return _augment_dashboard(base_html, state)


def _cookie_secret() -> str:
    load_dotenv()
    return (
        os.environ.get("DASHBOARD_SECRET", "").strip()
        or os.environ.get("WEBAPP_SECRET", "").strip()
        or os.environ.get("DASHBOARD_PASSWORD", "").strip()
    )


def _dashboard_password() -> str:
    load_dotenv()
    return os.environ.get("DASHBOARD_PASSWORD", "").strip()


def sign_session() -> str:
    secret = _cookie_secret()
    if not secret:
        raise ValueError("missing DASHBOARD_SECRET / WEBAPP_SECRET / DASHBOARD_PASSWORD")
    expires = str(int(datetime.now(timezone.utc).timestamp()) + SESSION_MAX_AGE_SECONDS)
    signature = hmac.new(secret.encode("utf-8"), expires.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{expires}.{signature}"


def verify_session(cookie_value: str | None) -> bool:
    if not cookie_value:
        return False
    secret = _cookie_secret()
    if not secret:
        return False
    try:
        expires, signature = cookie_value.split(".", 1)
    except ValueError:
        return False
    expected = hmac.new(secret.encode("utf-8"), expires.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        return False
    try:
        return int(expires) >= int(datetime.now(timezone.utc).timestamp())
    except ValueError:
        return False


def verify_password(password: str) -> bool:
    configured = _dashboard_password()
    return bool(configured) and hmac.compare_digest(password, configured)


def _login_page(message: str = "") -> str:
    detail = f"<p class='error'>{html.escape(message)}</p>" if message else ""
    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Small-Cap Radar Login</title>
    <style>
      body {{
        margin: 0;
        min-height: 100vh;
        display: grid;
        place-items: center;
        background: #f4f6f8;
        color: #111827;
        font-family: Inter, ui-sans-serif, -apple-system, BlinkMacSystemFont, sans-serif;
      }}
      .card {{
        width: min(92vw, 420px);
        border: 1px solid #e2e8f0;
        background: #ffffff;
        border-radius: 12px;
        padding: 24px;
        box-shadow: 0 18px 38px rgba(15, 23, 42, 0.10);
      }}
      h1 {{ margin: 0 0 8px; font-size: 22px; }}
      p {{ margin: 0 0 16px; color: #64748b; font-size: 14px; line-height: 1.5; }}
      input {{
        width: 100%;
        box-sizing: border-box;
        border: 1px solid #cbd5e1;
        background: #f8fafc;
        color: #111827;
        border-radius: 8px;
        padding: 12px 14px;
        font-size: 16px;
        margin-bottom: 12px;
      }}
      button {{
        width: 100%;
        border: 0;
        border-radius: 8px;
        padding: 12px 14px;
        background: #111827;
        color: #ffffff;
        font-size: 15px;
        font-weight: 700;
      }}
      .error {{ color: #dc2626; margin-bottom: 12px; }}
    </style>
  </head>
  <body>
    <form class="card" method="post" action="/login">
      <h1>Small-Cap Radar</h1>
      <p>Private read-only dashboard for small-cap market movement, liquidity, and volume context.</p>
      {detail}
      <input type="password" name="password" placeholder="Dashboard password" autocomplete="current-password" required>
      <button type="submit">Enter</button>
    </form>
  </body>
</html>
"""


def _flash_banner(state: dict[str, Any]) -> str:
    flash = str(state.get("flash", "") or "").strip()
    if not flash:
        return ""
    tone = str(state.get("flash_tone", "neutral") or "neutral")
    return f"<div class='flash flash-{html.escape(tone)}'>{html.escape(flash)}</div>"


def _view_only_toolbar() -> str:
    return """
      <section class='view-only-bar'>
        <div>
          <div class='view-only-kicker'>Read-only</div>
          <div class='view-only-text'>This page only shows market data, liquidity, volume, and event context. It does not execute trades.</div>
        </div>
        <form method="post" action="/logout" class="inline-form">
          <button class="action-btn action-btn-ghost" type="submit">Logout</button>
        </form>
      </section>
    """


def _augment_dashboard(base_html: str, state: dict[str, Any]) -> str:
    extra_css = """
      .flash {
        margin-bottom: 14px;
        padding: 12px 14px;
        border-radius: 8px;
        border: 1px solid #e2e8f0;
        color: #111827;
        background: #ffffff;
        font-size: 13px;
      }
      .inline-form { margin: 0; }
      .action-btn {
        border: 0;
        border-radius: 8px;
        padding: 10px 12px;
        font-size: 13px;
        font-weight: 700;
        cursor: pointer;
      }
      .action-btn-ghost {
        background: #f1f5f9;
        color: #475569;
      }
      .view-only-bar {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 14px;
        margin-bottom: 14px;
        padding: 14px 16px;
        border: 1px solid #e2e8f0;
        border-radius: 8px;
        background: #ffffff;
        box-shadow: 0 10px 26px rgba(15, 23, 42, 0.055);
      }
      .view-only-kicker {
        color: #2563eb;
        font-size: 11px;
        text-transform: uppercase;
        letter-spacing: 0.12em;
        margin-bottom: 4px;
      }
      .view-only-text {
        color: #64748b;
        font-size: 13px;
        line-height: 1.5;
      }
      @media (max-width: 880px) {
        .view-only-bar {
          flex-direction: column;
          align-items: flex-start;
        }
      }
    """
    injected = base_html.replace("</style>", f"{extra_css}\n        </style>", 1)
    banner = _flash_banner(state) + _view_only_toolbar()
    injected = injected.replace("<div class=\"ticker-tape\">", f"{banner}<div class=\"ticker-tape\">", 1)
    return injected


def render_live_dashboard_page(*, flash: str | None = None, flash_tone: str = "neutral") -> str:
    state = build_live_dashboard_state(flash=flash, flash_tone=flash_tone)
    return _render_dashboard_from_state(state)


def render_login_page(message: str = "") -> str:
    return _login_page(message)
