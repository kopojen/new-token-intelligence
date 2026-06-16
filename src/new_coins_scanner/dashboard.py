from __future__ import annotations

from datetime import datetime
import html
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .runtime_state import load_runtime_state


def _fmt_datetime(value: object) -> str | None:
    if not isinstance(value, str) or "T" not in value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    localized = parsed.astimezone()
    return localized.strftime("%m-%d %H:%M")


def _fmt(value: object, digits: int = 4) -> str:
    if value is None:
        return "-"
    formatted_dt = _fmt_datetime(value)
    if formatted_dt is not None:
        return formatted_dt
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, (int, float)):
        return f"{value:.{digits}f}" if isinstance(value, float) else str(value)
    return str(value)


def _fmt_short_number(value: object) -> str:
    if not isinstance(value, (int, float)):
        return _fmt(value)
    absolute = abs(float(value))
    if absolute >= 1_000_000_000:
        return f"{value / 1_000_000_000:.2f}B"
    if absolute >= 1_000_000:
        return f"{value / 1_000_000:.2f}M"
    if absolute >= 1_000:
        return f"{value / 1_000:.2f}K"
    return _fmt(value, digits=2)


def _fmt_pct(value: object) -> str:
    if not isinstance(value, (int, float)):
        return _fmt(value)
    return f"{value:.2f}%"


def _fmt_price(value: object) -> str:
    if not isinstance(value, (int, float)):
        return _fmt(value)
    absolute = abs(float(value))
    if absolute == 0:
        return "0"
    if absolute < 0.0001:
        return f"{value:.8f}".rstrip("0").rstrip(".")
    if absolute < 1:
        return f"{value:.6f}".rstrip("0").rstrip(".")
    return f"{value:.4f}".rstrip("0").rstrip(".")


def _tone_from_return(value: object) -> str:
    if not isinstance(value, (int, float)):
        return "neutral"
    if float(value) > 0:
        return "good"
    if float(value) < 0:
        return "danger"
    return "neutral"


def _safe_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _chip(text: object, tone: str = "neutral") -> str:
    return f"<span class='chip chip-{tone}'>{html.escape(_fmt(text))}</span>"


def _render_card(label: str, value: object, hint: str = "", tone: str = "neutral") -> str:
    return (
        f"<div class='metric metric-{tone}'>"
        f"<div class='metric-label'>{html.escape(label)}</div>"
        f"<div class='metric-value'>{html.escape(_fmt(value))}</div>"
        f"<div class='metric-hint'>{html.escape(hint)}</div>"
        "</div>"
    )


def render_dashboard_html(state_path: str | Path) -> str:
    state = load_runtime_state(state_path)
    cycle = state.get("cycle", {}) if isinstance(state.get("cycle"), dict) else {}
    signals_raw = [item for item in state.get("signals", []) if isinstance(item, dict)]
    top_gainers_raw = [item for item in state.get("top_gainers", []) if isinstance(item, dict)]
    announcements_raw = [item for item in state.get("announcements", []) if isinstance(item, dict)]
    signals_by_symbol = {str(item.get("symbol")): item for item in signals_raw}
    movers = (
        [{**signals_by_symbol.get(str(item.get("symbol")), {}), **item} for item in top_gainers_raw]
        if top_gainers_raw
        else sorted(signals_raw, key=lambda item: _safe_float(item.get("ret_24h")), reverse=True)
    )
    leader = movers[0] if movers else None

    def base_symbol(symbol: object) -> str:
        value = _fmt(symbol)
        return value[:-4] if value.endswith("USDT") else value

    def market_notes(item: dict) -> list[str]:
        notes = [
            f"spread {_fmt(item.get('spread_pct'), 2)}%",
            f"depth {_fmt_short_number(item.get('depth_1pct_usd'))}",
        ]
        volume_multiple = _safe_float(item.get("volume_multiple_5m"))
        if volume_multiple >= 3:
            notes.append(f"volume {volume_multiple:.2f}x")
        return notes

    def market_tone(item: dict) -> str:
        if _safe_float(item.get("depth_1pct_usd")) < 100_000:
            return "danger"
        if _safe_float(item.get("spread_pct")) >= 0.25:
            return "warn"
        return "accent"

    def market_reason(item: dict) -> str:
        parts: list[str] = []
        if _safe_float(item.get("ret_24h")) >= 8:
            parts.append("large 24h move")
        if _safe_float(item.get("ret_1h")) >= 4:
            parts.append("strong 1h trend")
        if _safe_float(item.get("volume_multiple_5m")) >= 3:
            parts.append("volume expansion")
        if _safe_float(item.get("spread_pct")) >= 0.25:
            parts.append("spread widening")
        return ", ".join(parts) or "steady market activity"

    tracked_count = len(signals_raw)
    top_24h = max((_safe_float(item.get("ret_24h")) for item in signals_raw), default=0.0)
    avg_volume_spike = (
        sum(_safe_float(item.get("volume_multiple_5m")) for item in signals_raw) / tracked_count
        if tracked_count
        else 0.0
    )
    active_movers = sum(1 for item in signals_raw if _safe_float(item.get("ret_24h")) > 0)
    total_quote_volume = sum(_safe_float(item.get("quote_volume_24h")) for item in signals_raw)

    metric_cards = "".join(
        [
            _render_card("tracked pairs", tracked_count, "Binance spot universe"),
            _render_card("active movers", active_movers, "positive 24h change", "good" if active_movers else "neutral"),
            _render_card("top 24h move", _fmt_pct(top_24h), "largest observed move", "good"),
            _render_card("avg volume spike", f"{avg_volume_spike:.2f}x", "5m vs baseline", "accent"),
            _render_card("24h volume", _fmt_short_number(total_quote_volume), "combined quote volume"),
        ]
    )

    mover_cards = []
    max_volume_multiple = max((_safe_float(item.get("volume_multiple_5m")) for item in movers[:5]), default=1.0) or 1.0
    for item in movers[:5]:
        tone = _tone_from_return(item.get("ret_24h"))
        notes = market_notes(item)[:3]
        note_chips = "".join(_chip(note, market_tone(item)) for note in notes)
        volume_width = min(100, max(8, _safe_float(item.get("volume_multiple_5m")) / max_volume_multiple * 100))
        mover_cards.append(
            f"""
            <article class="mover-card">
              <div class="mover-top">
                <div>
                  <div class="symbol">{html.escape(base_symbol(item.get("symbol")))}</div>
                  <div class="pair">{html.escape(_fmt(item.get("symbol")))}</div>
                </div>
                <div class="price">${html.escape(_fmt_price(item.get("last_price")))}</div>
              </div>
              <div class="move move-{tone}">{html.escape(_fmt_pct(item.get("ret_24h")))}</div>
              <div class="volume-track"><span style="width: {volume_width:.0f}%"></span></div>
              <div class="mini-grid">
                <div><span>1h</span><strong>{html.escape(_fmt_pct(item.get("ret_1h")))}</strong></div>
                <div><span>15m</span><strong>{html.escape(_fmt_pct(item.get("ret_15m")))}</strong></div>
                <div><span>Vol Spike</span><strong>{html.escape(_fmt(item.get("volume_multiple_5m"), 2))}x</strong></div>
                <div><span>24h Vol</span><strong>{html.escape(_fmt_short_number(item.get("quote_volume_24h")))}</strong></div>
              </div>
              <div class="card-note">{html.escape(market_reason(item))}</div>
              <div class="chip-row">{note_chips}</div>
            </article>
            """
        )
    mover_cards_html = "".join(mover_cards) or "<div class='empty-card'>No market data available.</div>"

    table_rows = []
    for item in signals_raw[:12]:
        table_rows.append(
            f"""
            <tr>
              <td><strong>{html.escape(_fmt(item.get("symbol")))}</strong></td>
              <td>{html.escape(_fmt_price(item.get("last_price")))}</td>
              <td>{_chip(_fmt_pct(item.get("ret_24h")), _tone_from_return(item.get("ret_24h")))}</td>
              <td>{html.escape(_fmt_pct(item.get("ret_1h")))}</td>
              <td>{html.escape(_fmt_pct(item.get("ret_15m")))}</td>
              <td>{html.escape(_fmt(item.get("volume_multiple_5m"), 2))}x</td>
              <td>{html.escape(_fmt_short_number(item.get("quote_volume_24h")))}</td>
              <td>{html.escape(_fmt(item.get("spread_pct"), 2))}%</td>
              <td>{html.escape(_fmt_short_number(item.get("depth_1pct_usd")))}</td>
            </tr>
            """
        )
    market_table_html = "".join(table_rows) or "<tr><td colspan='9' class='empty'>No data</td></tr>"

    note_rows = []
    for item in signals_raw[:8]:
        tone = market_tone(item)
        note_rows.append(
            f"""
            <div class="note-row">
              <div>
                <strong>{html.escape(_fmt(item.get("symbol")))}</strong>
                <span>Spread {html.escape(_fmt(item.get("spread_pct"), 2))}% · Depth {html.escape(_fmt_short_number(item.get("depth_1pct_usd")))} · 24h Vol {html.escape(_fmt_short_number(item.get("quote_volume_24h")))}</span>
              </div>
              {_chip(f"{_fmt(item.get('volume_multiple_5m'), 2)}x vol", tone)}
            </div>
            """
        )
    note_rows_html = "".join(note_rows) or "<div class='empty-card'>No market notes.</div>"

    event_rows = []
    for item in announcements_raw[:4]:
        symbols = ", ".join(str(symbol) for symbol in item.get("symbol_candidates", [])[:2]) or "-"
        event_rows.append(
            f"""
            <div class="event-row">
              <div class="event-symbol">{html.escape(symbols)}</div>
              <div>
                <strong>{html.escape(_fmt(item.get("event_type")))}</strong>
                <p>{html.escape(_fmt(item.get("title")))}</p>
              </div>
            </div>
            """
        )
    event_rows_html = "".join(event_rows) or "<div class='empty-card'>No event notes in this cycle.</div>"

    hero_symbol = html.escape(_fmt(leader.get("symbol"))) if isinstance(leader, dict) else "No data"
    hero_move = html.escape(_fmt_pct(leader.get("ret_24h"))) if isinstance(leader, dict) else "-"
    hero_price = html.escape(_fmt_price(leader.get("last_price"))) if isinstance(leader, dict) else "-"
    hero_volume = html.escape(_fmt_short_number(leader.get("quote_volume_24h"))) if isinstance(leader, dict) else "-"
    leader_market_html = "".join(
        _chip(note, market_tone(leader) if isinstance(leader, dict) else "neutral")
        for note in (market_notes(leader)[:3] if isinstance(leader, dict) else ["no data"])
    )
    ticker_strip_html = "".join(
        f"""
        <div class="ticker-item">
          <span>{html.escape(base_symbol(item.get("symbol")))}</span>
          <strong>{html.escape(_fmt_pct(item.get("ret_24h")))}</strong>
        </div>
        """
        for item in movers[:6]
        if isinstance(item, dict)
    )
    watchlist_rows_html = "".join(
        f"""
        <div class="watch-row">
          <div>
            <strong>{html.escape(base_symbol(item.get("symbol")))}</strong>
            <span>{html.escape(_fmt(item.get("symbol")))}</span>
          </div>
          <div class="watch-metrics">
            <b class="move-{_tone_from_return(item.get("ret_24h"))}">{html.escape(_fmt_pct(item.get("ret_24h")))}</b>
            <span>{html.escape(_fmt(item.get("volume_multiple_5m"), 2))}x vol</span>
          </div>
        </div>
        """
        for item in movers[:6]
        if isinstance(item, dict)
    )
    insight_rows_html = "".join(
        f"""
        <div class="insight-row">
          <div>
            <strong>{html.escape(base_symbol(item.get("symbol")))}</strong>
            <span>{html.escape(_fmt_short_number(item.get("depth_1pct_usd")))} depth / {html.escape(_fmt(item.get("spread_pct"), 2))}% spread</span>
          </div>
          {_chip(f"24h vol {_fmt_short_number(item.get('quote_volume_24h'))}", "accent")}
        </div>
        """
        for item in movers[:4]
        if isinstance(item, dict)
    )
    body = f"""
    <!doctype html>
    <html lang="en">
      <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <meta http-equiv="refresh" content="60">
        <title>Small-Cap Radar</title>
        <style>
          :root {{
            --bg: #f4f6f8;
            --ink: #111827;
            --muted: #64748b;
            --panel: #ffffff;
            --line: #e2e8f0;
            --soft: #f8fafc;
            --accent: #10b981;
            --accent-dark: #047857;
            --blue: #2563eb;
            --warn: #b45309;
            --danger: #dc2626;
            --night: #111827;
            --shadow: 0 18px 38px rgba(15, 23, 42, 0.10);
          }}
          * {{ box-sizing: border-box; }}
          body {{
            margin: 0;
            color: var(--ink);
            font-family: Inter, "Avenir Next", "Segoe UI", sans-serif;
            background: linear-gradient(180deg, #f8fafc 0, #eef2f7 360px, #f4f6f8 100%);
          }}
          .shell {{
            max-width: 1360px;
            margin: 0 auto;
            padding: 18px 24px 44px;
          }}
          .nav {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 16px;
            color: var(--ink);
            margin-bottom: 12px;
            padding: 11px 12px;
            border: 1px solid var(--line);
            border-radius: 8px;
            background: rgba(255, 255, 255, 0.92);
            box-shadow: 0 10px 28px rgba(15, 23, 42, 0.07);
            backdrop-filter: blur(14px);
          }}
          .brand {{
            display: flex;
            align-items: center;
            gap: 12px;
            font-weight: 780;
            font-size: 18px;
          }}
          .mark {{
            width: 32px;
            height: 32px;
            border-radius: 8px;
            background:
              linear-gradient(135deg, transparent 0 52%, rgba(255, 255, 255, 0.18) 52%),
              #111827;
            border: 2px solid #10b981;
            box-shadow: 0 10px 24px rgba(15, 23, 42, 0.14);
          }}
          .ticker-tape {{
            display: grid;
            grid-template-columns: repeat(6, minmax(0, 1fr));
            gap: 8px;
            margin-bottom: 14px;
          }}
          .ticker-item {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 8px;
            min-height: 40px;
            padding: 9px 12px;
            border: 1px solid var(--line);
            border-radius: 8px;
            background: rgba(255, 255, 255, 0.94);
            box-shadow: 0 7px 18px rgba(15, 23, 42, 0.05);
            transition: transform 150ms ease, border-color 150ms ease, box-shadow 150ms ease;
          }}
          .ticker-item:hover {{
            transform: translateY(-2px);
            border-color: #cbd5e1;
            box-shadow: 0 12px 24px rgba(15, 23, 42, 0.08);
          }}
          .ticker-item span {{
            color: #334155;
            font-size: 12px;
            font-weight: 760;
          }}
          .ticker-item strong {{
            color: var(--accent-dark);
            font-size: 12px;
          }}
          .nav-meta {{
            display: flex;
            align-items: center;
            gap: 8px;
            flex-wrap: wrap;
          }}
          .dashboard-title {{
            display: flex;
            align-items: end;
            justify-content: space-between;
            gap: 18px;
            margin: 14px 0 12px;
          }}
          .dashboard-title h1 {{
            margin: 0;
            max-width: 720px;
            font-size: 28px;
            line-height: 1.08;
            letter-spacing: 0;
          }}
          .dashboard-title p {{
            margin: 6px 0 0;
            max-width: 720px;
            color: var(--muted);
            font-size: 13px;
            line-height: 1.45;
          }}
          .command-center {{
            display: grid;
            grid-template-columns: 310px minmax(0, 1fr) 360px;
            gap: 14px;
            margin-bottom: 18px;
          }}
          .panel {{
            border-radius: 8px;
            border: 1px solid var(--line);
            background: #ffffff;
            box-shadow: var(--shadow);
            transition: transform 160ms ease, box-shadow 160ms ease, border-color 160ms ease;
          }}
          .panel:hover, .mover-card:hover, .metric:hover {{
            transform: translateY(-2px);
            border-color: #cbd5e1;
            box-shadow: 0 20px 42px rgba(15, 23, 42, 0.11);
          }}
          .panel-head {{
            display: flex;
            align-items: flex-start;
            justify-content: space-between;
            gap: 12px;
            padding: 16px 16px 0;
          }}
          .panel-head h2 {{
            margin: 0;
            font-size: 16px;
          }}
          .panel-head p {{
            margin: 5px 0 0;
            color: var(--muted);
            font-size: 12px;
            line-height: 1.35;
          }}
          .eyebrow {{
            color: var(--blue);
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 0.12em;
            margin-bottom: 12px;
          }}
          .watchlist {{
            overflow: hidden;
          }}
          .watch-list {{
            padding: 10px 12px 12px;
          }}
          .watch-row {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 12px;
            padding: 11px 8px;
            border-bottom: 1px solid #eef2f7;
            border-radius: 7px;
            transition: background 140ms ease;
          }}
          .watch-row:hover, .insight-row:hover, .note-row:hover, .event-row:hover {{
            background: #f8fafc;
          }}
          .watch-row:last-child {{
            border-bottom: 0;
          }}
          .watch-row strong, .insight-row strong {{
            display: block;
            font-size: 15px;
          }}
          .watch-row span, .insight-row span {{
            display: block;
            margin-top: 3px;
            color: var(--muted);
            font-size: 11px;
          }}
          .watch-metrics {{
            text-align: right;
          }}
          .watch-metrics b {{
            display: block;
            font-size: 15px;
          }}
          .metric-label {{
            display: block;
            color: var(--muted);
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 0.08em;
          }}
          .leader-panel {{
            min-height: 316px;
            padding: 20px;
            border-radius: 8px;
            background: linear-gradient(135deg, #111827 0%, #172033 58%, #0f172a 100%);
            color: #f8fbf8;
            box-shadow: var(--shadow);
            position: relative;
            overflow: hidden;
          }}
          .leader-panel::before {{
            content: "";
            position: absolute;
            inset: 0 0 auto;
            height: 3px;
            background: linear-gradient(90deg, var(--accent), var(--blue));
          }}
          .leader-panel > * {{
            position: relative;
          }}
          .leader-topline {{
            display: flex;
            align-items: flex-start;
            justify-content: space-between;
            gap: 16px;
          }}
          .leader-topline h2 {{
            margin: 0;
            font-size: 16px;
          }}
          .leader-topline p {{
            margin: 6px 0 0;
            color: #94a3b8;
            font-size: 12px;
          }}
          .leader-symbol {{
            margin-top: 24px;
            display: flex;
            align-items: flex-end;
            justify-content: space-between;
            gap: 18px;
          }}
          .leader-symbol strong {{
            display: block;
            font-size: 48px;
            line-height: 0.9;
            letter-spacing: 0;
          }}
          .leader-symbol span {{
            display: block;
            margin-top: 8px;
            color: #cbd5e1;
            font-size: 13px;
          }}
          .leader-move {{
            color: #34d399;
            font-size: 50px;
            font-weight: 850;
            line-height: 0.95;
          }}
          .leader-grid {{
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 10px;
            margin-top: 24px;
          }}
          .leader-grid div {{
            padding: 12px;
            border-radius: 8px;
            background: rgba(255, 255, 255, 0.07);
            border: 1px solid rgba(226, 232, 240, 0.14);
          }}
          .leader-grid span {{
            display: block;
            color: #94a3b8;
            font-size: 10px;
            text-transform: uppercase;
            letter-spacing: 0.06em;
          }}
          .leader-grid strong {{
            display: block;
            margin-top: 6px;
            font-size: 17px;
            color: #f8fbf8;
          }}
          .leader-tags {{
            margin-top: 14px;
          }}
          .insights {{
            overflow: hidden;
          }}
          .insight-list {{
            padding: 8px 12px 12px;
          }}
          .insight-row {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 12px;
            padding: 11px 8px;
            border-bottom: 1px solid #eef2f7;
            border-radius: 7px;
          }}
          .insight-row:last-child {{
            border-bottom: 0;
          }}
          .snapshot-strip {{
            display: grid;
            grid-template-columns: repeat(5, minmax(0, 1fr));
            gap: 10px;
            margin-bottom: 18px;
          }}
          .metric {{
            padding: 13px 14px;
            border-radius: 8px;
            background: rgba(255, 255, 255, 0.94);
            border: 1px solid var(--line);
            box-shadow: 0 7px 18px rgba(15, 23, 42, 0.04);
            transition: transform 160ms ease, box-shadow 160ms ease, border-color 160ms ease;
          }}
          .metric-value {{
            display: block;
            margin-top: 8px;
            font-size: 22px;
            font-weight: 780;
          }}
          .metric-hint {{
            margin-top: 7px;
            color: var(--muted);
            font-size: 12px;
          }}
          .section {{
            padding: 18px;
            border: 1px solid var(--line);
            background: var(--panel);
            border-radius: 8px;
            box-shadow: 0 10px 26px rgba(15, 23, 42, 0.055);
            margin-bottom: 18px;
          }}
          .section-head {{
            display: flex;
            justify-content: space-between;
            gap: 16px;
            align-items: flex-start;
            margin-bottom: 16px;
          }}
          .section-head h2 {{
            margin: 0;
            font-size: 18px;
          }}
          .section-head p {{
            margin: 7px 0 0;
            color: var(--muted);
            line-height: 1.45;
            font-size: 13px;
          }}
          .mover-grid {{
            display: grid;
            grid-template-columns: repeat(5, minmax(0, 1fr));
            gap: 10px;
          }}
          .mover-card {{
            min-height: 188px;
            padding: 14px;
            border-radius: 8px;
            border: 1px solid var(--line);
            background: #ffffff;
            transition: transform 160ms ease, box-shadow 160ms ease, border-color 160ms ease;
          }}
          .mover-top {{
            display: flex;
            justify-content: space-between;
            gap: 10px;
            align-items: flex-start;
          }}
          .symbol {{
            font-size: 20px;
            font-weight: 820;
          }}
          .pair, .price {{
            color: var(--muted);
            font-size: 12px;
          }}
          .move {{
            margin: 14px 0 10px;
            font-size: 30px;
            font-weight: 850;
            line-height: 0.95;
          }}
          .move-good {{ color: var(--accent-dark); }}
          .move-danger {{ color: var(--danger); }}
          .move-neutral {{ color: var(--ink); }}
          .volume-track {{
            height: 6px;
            margin: 0 0 12px;
            border-radius: 999px;
            background: #eef2f7;
            overflow: hidden;
          }}
          .volume-track span {{
            display: block;
            height: 100%;
            border-radius: inherit;
            background: linear-gradient(90deg, var(--blue), var(--accent));
          }}
          .mini-grid {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 8px;
          }}
          .mini-grid div {{
            padding: 8px;
            border: 1px solid var(--line);
            border-radius: 8px;
            background: #f8fafc;
          }}
          .mini-grid span {{
            display: block;
            color: var(--muted);
            font-size: 10px;
            text-transform: uppercase;
            letter-spacing: 0.06em;
          }}
          .mini-grid strong {{
            display: block;
            margin-top: 5px;
            font-size: 14px;
          }}
          .card-note {{
            margin: 11px 0 9px;
            min-height: 30px;
            color: var(--muted);
            font-size: 12px;
            line-height: 1.4;
          }}
          .grid-2 {{
            display: grid;
            grid-template-columns: minmax(0, 1.45fr) minmax(340px, 0.8fr);
            gap: 18px;
          }}
          .side-stack {{
            display: grid;
            gap: 18px;
          }}
          .table-wrap {{
            overflow-x: auto;
          }}
          table {{
            width: 100%;
            min-width: 780px;
            border-collapse: collapse;
          }}
          th, td {{
            padding: 11px 12px;
            text-align: left;
            border-bottom: 1px solid #e2e8f0;
            font-size: 13px;
            white-space: nowrap;
          }}
          th {{
            color: var(--muted);
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 0.07em;
            background: #f8fafc;
          }}
          tbody tr {{
            transition: background 140ms ease;
          }}
          tbody tr:hover {{
            background: #f8fafc;
          }}
          .note-row, .event-row {{
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            gap: 12px;
            padding: 12px 0;
            border-bottom: 1px solid #e2e8f0;
            border-radius: 7px;
          }}
          .note-row:last-child, .event-row:last-child {{
            border-bottom: 0;
          }}
          .note-row span, .event-row p {{
            display: block;
            margin: 4px 0 0;
            color: var(--muted);
            font-size: 12px;
            line-height: 1.4;
          }}
          .event-symbol {{
            min-width: 64px;
            color: var(--accent-dark);
            font-weight: 780;
          }}
          .chip-row {{
            display: flex;
            flex-wrap: wrap;
            gap: 6px;
          }}
          .chip {{
            display: inline-flex;
            align-items: center;
            padding: 5px 9px;
            border-radius: 999px;
            border: 1px solid var(--line);
            background: #ffffff;
            font-size: 11px;
            font-weight: 700;
            white-space: nowrap;
          }}
          .chip-good {{ color: #047857; background: #ecfdf5; border-color: #bbf7d0; }}
          .chip-warn {{ color: #92400e; background: #fffbeb; border-color: #fde68a; }}
          .chip-danger {{ color: #b91c1c; background: #fef2f2; border-color: #fecaca; }}
          .chip-accent {{ color: #1d4ed8; background: #eff6ff; border-color: #bfdbfe; }}
          .chip-neutral {{ color: #475569; background: #f8fafc; }}
          .empty-card {{
            color: var(--muted);
            font-size: 13px;
            padding: 12px 0;
          }}
          .foot {{
            margin-top: 14px;
            color: #77807b;
            font-size: 12px;
            text-align: right;
          }}
          @media (max-width: 1160px) {{
            .command-center, .grid-2 {{
              grid-template-columns: 1fr;
            }}
            .snapshot-strip, .mover-grid, .ticker-tape {{
              grid-template-columns: repeat(2, minmax(0, 1fr));
            }}
            .leader-grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
          }}
          @media (max-width: 680px) {{
            .shell {{
              padding: 16px;
            }}
            .nav, .section-head, .dashboard-title {{
              flex-direction: column;
              align-items: flex-start;
            }}
            .dashboard-title h1 {{
              font-size: 24px;
            }}
            .leader-symbol {{
              align-items: flex-start;
              flex-direction: column;
            }}
            .leader-symbol strong, .leader-move {{
              font-size: 40px;
            }}
            .snapshot-strip, .mover-grid, .leader-grid, .ticker-tape {{
              grid-template-columns: 1fr;
            }}
          }}
        </style>
      </head>
      <body>
        <div class="shell">
          <nav class="nav">
            <div class="brand"><span class="mark"></span><span>Small-Cap Radar</span></div>
            <div class="nav-meta">
              {_chip("Binance spot pairs", "accent")}
              {_chip(f"Updated {_fmt(state.get('updated_at', '-'))}", "neutral")}
              {_chip("Data only", "warn")}
            </div>
          </nav>
          <div class="ticker-tape">{ticker_strip_html}</div>

          <div class="dashboard-title">
            <div>
              <div class="eyebrow">Small-cap market monitor</div>
              <h1>Compact dashboard for small-cap movers, liquidity, and volume context.</h1>
              <p>Built for traders who want to compare market data quickly. It shows movement, volume, spread, and depth without turning the dashboard into a buy/sell signal.</p>
            </div>
            {_chip("read-only demo", "neutral")}
          </div>

          <section class="command-center">
            <aside class="panel watchlist">
              <div class="panel-head">
                <div>
                  <h2>Watchlist</h2>
                  <p>Fast movers ranked by 24h change.</p>
                </div>
              </div>
              <div class="watch-list">{watchlist_rows_html}</div>
            </aside>

            <section class="leader-panel">
              <div class="leader-topline">
                <div>
                  <h2>Current Focus</h2>
                  <p>Highest small-cap movement in the current snapshot.</p>
                </div>
                {_chip("not financial advice", "warn")}
              </div>
              <div class="leader-symbol">
                <div>
                  <strong>{hero_symbol}</strong>
                  <span>Last ${hero_price} · 24h volume {hero_volume}</span>
                </div>
                <div class="leader-move">{hero_move}</div>
              </div>
              <div class="leader-grid">
                <div><span>Tracked pairs</span><strong>{tracked_count}</strong></div>
                <div><span>Avg vol spike</span><strong>{avg_volume_spike:.2f}x</strong></div>
                <div><span>Active movers</span><strong>{active_movers}</strong></div>
                <div><span>24h Volume</span><strong>{_fmt_short_number(total_quote_volume)}</strong></div>
              </div>
              <div class="leader-tags chip-row">{leader_market_html}</div>
            </section>

            <aside class="panel insights">
              <div class="panel-head">
                <div>
                  <h2>Liquidity Lens</h2>
                  <p>Depth and spread checks before interpreting a move.</p>
                </div>
              </div>
              <div class="insight-list">{insight_rows_html}</div>
            </aside>
          </section>

          <div class="snapshot-strip">{metric_cards}</div>

          <section class="section">
            <div class="section-head">
              <div>
                <h2>Momentum Board</h2>
                <p>Real Binance spot pairs sorted by current 24h movement in the demo snapshot.</p>
              </div>
              {_chip("refreshes every 60s", "neutral")}
            </div>
            <div class="mover-grid">{mover_cards_html}</div>
          </section>

          <div class="grid-2">
            <section class="section">
              <div class="section-head">
                <div>
                  <h2>Market Snapshot</h2>
                  <p>Raw indicators for comparison. No trade state and no execution recommendation.</p>
                </div>
              </div>
              <div class="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Pair</th>
                      <th>Last</th>
                      <th>24h</th>
                      <th>1h</th>
                      <th>15m</th>
                      <th>Vol spike</th>
                      <th>24h volume</th>
                      <th>Spread</th>
                      <th>Depth 1%</th>
                    </tr>
                  </thead>
                  <tbody>{market_table_html}</tbody>
                </table>
              </div>
            </section>

            <div class="side-stack">
              <section class="section">
                <div class="section-head">
                  <div>
                    <h2>Market Notes</h2>
                    <p>Spread, depth, and volume context for quick comparison across pairs.</p>
                  </div>
                </div>
                {note_rows_html}
              </section>

              <section class="section">
                <div class="section-head">
                  <div>
                    <h2>Event Notes</h2>
                    <p>Manual or official event rows can be attached to explain why a pair is worth watching.</p>
                  </div>
                </div>
                {event_rows_html}
              </section>
            </div>
          </div>

          <div class="foot">Educational market-intelligence demo only. Not financial advice.</div>
        </div>
      </body>
    </html>
    """
    return body


def serve_dashboard(state_path: str | Path, host: str, port: int) -> None:
    resolved_state_path = str(Path(state_path).resolve())

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            body = render_dashboard_html(resolved_state_path).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args) -> None:  # noqa: A003
            return

    server = ThreadingHTTPServer((host, port), Handler)
    try:
        server.serve_forever()
    finally:
        server.server_close()
