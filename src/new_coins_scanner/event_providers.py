from __future__ import annotations

from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
import json
import re
from urllib.request import Request, urlopen

from .event_models import AnnouncementItem, EventSignal


BINANCE_ALPHA_LIST_URL = "https://www.binance.com/bapi/defi/v1/public/wallet-direct/buw/wallet/cex/alpha/all/token/list"
OKX_ANNOUNCEMENTS_URL = "https://www.okx.com/help/category/announcements"
KUCOIN_NEW_LISTINGS_URL = "https://www.kucoin.com/announcement/new-listings"
QUOTE_SUFFIXES = ("USDT", "USDC", "FDUSD", "USD")
GENERIC_TOKENS = {"OKX", "KUCOIN", "USD", "USDT", "USDC", "FDUSD", "UTC", "API", "P2P", "WEB3", "AI"}


def _fetch_text(url: str, timeout: float = 20.0) -> str:
    request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def _normalize_whitespace(value: str) -> str:
    return " ".join(value.split())


def _strip_quote_suffix(symbol: str) -> str:
    for suffix in QUOTE_SUFFIXES:
        if symbol.endswith(suffix) and len(symbol) > len(suffix):
            return symbol[: -len(suffix)]
    return symbol


def _extract_symbols(title: str) -> list[str]:
    matches: list[str] = []
    for token in re.findall(r"\(([A-Z0-9]{2,15})\)", title):
        matches.append(_strip_quote_suffix(token))
    for token in re.findall(r"\b([A-Z]{2,15}(?:USDT|USDC|FDUSD|USD))\b", title):
        matches.append(_strip_quote_suffix(token))
    for token in re.findall(r"\b([A-Z][A-Z0-9]{1,9})\b", title):
        if token in GENERIC_TOKENS:
            continue
        if token.isdigit():
            continue
        matches.append(_strip_quote_suffix(token))
    deduped: list[str] = []
    for token in matches:
        if token not in deduped:
            deduped.append(token)
    return deduped[:3]


def _classify_title(title: str) -> tuple[str, float, list[str]]:
    lowered = title.lower()
    tags: list[str] = ["official-announcement"]
    if "perpetual" in lowered or "futures" in lowered or "contract" in lowered:
        return "perp_listing", 11.0, tags + ["perp-listing"]
    if "listed on" in lowered or "to list" in lowered or "spot trading" in lowered or "new listing" in lowered:
        return "spot_listing", 12.0, tags + ["spot-listing"]
    if "delist" in lowered:
        return "delisting", 4.0, tags + ["delisting"]
    if "airdrop" in lowered:
        return "airdrop", 6.0, tags + ["airdrop"]
    return "other", 3.0, tags


def _published_recency_bonus(published_at: str) -> float:
    if not published_at:
        return 0.0
    for fmt in ("%b %d, %Y", "%m/%d/%Y, %H:%M:%S", "%Y-%m-%d"):
        try:
            parsed = datetime.strptime(published_at, fmt)
            parsed = parsed.replace(tzinfo=timezone.utc)
            break
        except ValueError:
            parsed = None
    if parsed is None:
        return 0.0
    age_hours = (datetime.now(timezone.utc) - parsed).total_seconds() / 3600.0
    if age_hours <= 24:
        return 5.0
    if age_hours <= 72:
        return 3.0
    if age_hours <= 168:
        return 1.0
    return 0.0


def _announcement_to_signals(item: AnnouncementItem) -> list[EventSignal]:
    signals: list[EventSignal] = []
    event_type, base_score, tags = _classify_title(item.title)
    recency = _published_recency_bonus(item.published_at)
    narrative_score = 2.0 if any(tag in item.title.lower() for tag in ("ai", "wallet", "world premiere")) else 0.0
    for symbol in item.symbol_candidates:
        signals.append(
            EventSignal(
                symbol=symbol,
                source=item.source,
                signal_type=event_type,
                event_score=base_score + recency,
                narrative_score=narrative_score,
                tradable_on_binance=False,
                tags=list(dict.fromkeys(tags + item.tags)),
                summary=item.summary or item.title,
                raw={
                    "title": item.title,
                    "url": item.url,
                    "published_at": item.published_at,
                    "event_type": event_type,
                    **item.raw,
                },
            )
        )
    return signals


class _AnchorParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._href = ""
        self._buf: list[str] = []
        self._in_a = False
        self.items: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        self._in_a = True
        self._href = dict(attrs).get("href", "") or ""
        self._buf = []

    def handle_data(self, data: str) -> None:
        if self._in_a:
            self._buf.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag != "a" or not self._in_a:
            return
        text = _normalize_whitespace("".join(self._buf))
        if self._href and text:
            self.items.append((self._href, text))
        self._in_a = False


class BinanceAlphaProvider:
    def __init__(self, url: str = BINANCE_ALPHA_LIST_URL, timeout: float = 20.0) -> None:
        self.url = url
        self.timeout = timeout

    def fetch(self) -> list[EventSignal]:
        with urlopen(self.url, timeout=self.timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        items = payload.get("data", [])
        return [self._to_signal(item) for item in items]

    def _to_signal(self, item: dict) -> EventSignal:
        symbol = str(item.get("symbol", "")).upper().strip()
        listing_cex = bool(item.get("listingCex"))
        hot_tag = bool(item.get("hotTag"))
        online_tge = bool(item.get("onlineTge"))
        online_airdrop = bool(item.get("onlineAirdrop"))
        price_change = float(item.get("percentChange24h") or 0.0)
        volume_24h = float(item.get("volume24h") or 0.0)
        liquidity = float(item.get("liquidity") or 0.0)
        market_cap = float(item.get("marketCap") or 0.0)
        fdv = float(item.get("fdv") or 0.0)
        listing_time = item.get("listingTime")

        event_score = 0.0
        narrative_score = 0.0
        liquidity_score = 0.0
        volume_score = 0.0
        tags: list[str] = ["binance-alpha"]

        if listing_cex:
            event_score += 12.0
            tags.append("listing-cex")
        if hot_tag:
            event_score += 5.0
            tags.append("hot")
        if online_tge:
            event_score += 6.0
            tags.append("tge")
        if online_airdrop:
            event_score += 4.0
            tags.append("airdrop")
        if listing_time:
            event_score += self._listing_recency_bonus(listing_time)
            tags.append("recent-listing")

        if volume_24h >= 50_000_000:
            volume_score += 8.0
        elif volume_24h >= 20_000_000:
            volume_score += 5.0
        elif volume_24h >= 5_000_000:
            volume_score += 2.0

        if liquidity >= 5_000_000:
            liquidity_score += 8.0
        elif liquidity >= 1_500_000:
            liquidity_score += 5.0
        elif liquidity >= 500_000:
            liquidity_score += 2.0

        if price_change >= 100.0:
            narrative_score += 4.0
        elif price_change >= 40.0:
            narrative_score += 2.0

        if fdv > 0 and market_cap > 0 and fdv / market_cap > 4.0:
            narrative_score -= 2.0
            tags.append("high-fdv")

        summary = f"Alpha token with 24h vol {volume_24h:,.0f} and liquidity {liquidity:,.0f}"
        return EventSignal(
            symbol=symbol,
            source="binance-alpha",
            signal_type="alpha-token",
            event_score=event_score,
            narrative_score=narrative_score,
            liquidity_score=liquidity_score,
            volume_score=volume_score,
            tradable_on_binance=listing_cex,
            tags=tags,
            summary=summary,
            raw=item,
        )

    @staticmethod
    def _listing_recency_bonus(listing_time: int | str) -> float:
        try:
            timestamp = int(listing_time)
        except (TypeError, ValueError):
            return 0.0
        listed_at = datetime.fromtimestamp(timestamp / 1000.0, tz=timezone.utc)
        age_hours = (datetime.now(timezone.utc) - listed_at).total_seconds() / 3600.0
        if age_hours <= 24:
            return 6.0
        if age_hours <= 72:
            return 4.0
        if age_hours <= 168:
            return 2.0
        return 0.0


class OKXAnnouncementsProvider:
    def __init__(self, url: str = OKX_ANNOUNCEMENTS_URL, timeout: float = 20.0) -> None:
        self.url = url
        self.timeout = timeout

    def fetch_announcements(self) -> list[AnnouncementItem]:
        html = _fetch_text(self.url, timeout=self.timeout)
        parser = _AnchorParser()
        parser.feed(html)
        items: list[AnnouncementItem] = []
        seen_urls: set[str] = set()
        for href, text in parser.items:
            if not href.startswith("/help/") or href.startswith("/help/section/") or href.startswith("/help/category/"):
                continue
            if "Published on " not in text:
                continue
            url = f"https://www.okx.com{href}"
            if url in seen_urls:
                continue
            seen_urls.add(url)
            title, published_at = self._split_text(text, marker="Published on ")
            symbols = _extract_symbols(title)
            items.append(
                AnnouncementItem(
                    source="okx-announcements",
                    title=title,
                    url=url,
                    published_at=published_at,
                    event_type=_classify_title(title)[0],
                    symbol_candidates=symbols,
                    tags=["okx", "official"],
                    summary=title,
                    raw={"href": href},
                )
            )
        return items[:25]

    def fetch(self) -> list[EventSignal]:
        signals: list[EventSignal] = []
        for item in self.fetch_announcements():
            signals.extend(_announcement_to_signals(item))
        return signals

    @staticmethod
    def _split_text(text: str, marker: str) -> tuple[str, str]:
        if marker not in text:
            return text, ""
        title, published = text.split(marker, 1)
        return _normalize_whitespace(title), _normalize_whitespace(published)


class KuCoinAnnouncementsProvider:
    def __init__(self, url: str = KUCOIN_NEW_LISTINGS_URL, timeout: float = 20.0) -> None:
        self.url = url
        self.timeout = timeout

    def fetch_announcements(self) -> list[AnnouncementItem]:
        html = _fetch_text(self.url, timeout=self.timeout)
        parser = _AnchorParser()
        parser.feed(html)
        items: list[AnnouncementItem] = []
        seen_urls: set[str] = set()
        for href, text in parser.items:
            if not href.startswith("/announcement/") or href.count("/") < 2:
                continue
            if href in {
                "/announcement",
                "/announcement/activities",
                "/announcement/new-listings",
                "/announcement/product-updates",
                "/announcement/vip",
                "/announcement/maintenance-updates",
                "/announcement/delistings",
                "/announcement/web3",
                "/announcement/others",
                "/announcement/history",
            }:
                continue
            url = f"https://www.kucoin.com{href}"
            if url in seen_urls:
                continue
            seen_urls.add(url)
            title, published_at = self._split_text(text)
            symbols = _extract_symbols(title)
            items.append(
                AnnouncementItem(
                    source="kucoin-announcements",
                    title=title,
                    url=url,
                    published_at=published_at,
                    event_type=_classify_title(title)[0],
                    symbol_candidates=symbols,
                    tags=["kucoin", "official"],
                    summary=title,
                    raw={"href": href},
                )
            )
        return items[:25]

    def fetch(self) -> list[EventSignal]:
        signals: list[EventSignal] = []
        for item in self.fetch_announcements():
            signals.extend(_announcement_to_signals(item))
        return signals

    @staticmethod
    def _split_text(text: str) -> tuple[str, str]:
        match = re.search(r"(\d{2}/\d{2}/\d{4}, \d{2}:\d{2}:\d{2})$", text)
        if not match:
            return _normalize_whitespace(text), ""
        published = match.group(1)
        title = text[: match.start()]
        title = re.sub(r"Trading:\s+\d{1,2}:\d{2}.*$", "", title).strip()
        return _normalize_whitespace(title), published


class LocalEventFeedProvider:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def fetch(self) -> list[EventSignal]:
        if not self.path.exists():
            return []
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        items = payload.get("events", [])
        signals: list[EventSignal] = []
        for item in items:
            signals.append(
                EventSignal(
                    symbol=str(item["symbol"]).upper(),
                    source=str(item.get("source", "local-feed")),
                    signal_type=str(item.get("signal_type", "manual-event")),
                    event_score=float(item.get("event_score", 0.0)),
                    narrative_score=float(item.get("narrative_score", 0.0)),
                    liquidity_score=float(item.get("liquidity_score", 0.0)),
                    volume_score=float(item.get("volume_score", 0.0)),
                    tradable_on_binance=bool(item.get("tradable_on_binance", False)),
                    tags=list(item.get("tags", [])),
                    summary=str(item.get("summary", "")),
                    raw=item,
                )
            )
        return signals
