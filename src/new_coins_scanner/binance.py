from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from statistics import mean
from typing import Any
import json
import math
from urllib.parse import urlencode
from urllib.request import urlopen
from urllib.error import HTTPError, URLError

from .config import ScannerConfig
from .models import SymbolSnapshot


API_BASE = "https://api.binance.com"
STABLE_ASSETS = {
    "USDT",
    "USDC",
    "FDUSD",
    "TUSD",
    "USDP",
    "BUSD",
    "DAI",
    "USDE",
    "USD1",
    "RLUSD",
    "EUR",
}


@dataclass(slots=True)
class RollingTicker:
    symbol: str
    open_price: float
    high_price: float
    low_price: float
    last_price: float
    volume: float
    quote_volume: float
    count: int


class BinanceSpotPublicClient:
    def __init__(self, api_base: str = API_BASE, timeout: float = 15.0) -> None:
        self.api_base = api_base.rstrip("/")
        self.timeout = timeout

    def _get_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        url = f"{self.api_base}{path}"
        if params:
            url = f"{url}?{urlencode(params)}"
        try:
            with urlopen(url, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:  # pragma: no cover - network path
            raise RuntimeError(f"HTTP {exc.code} for {url}") from exc
        except URLError as exc:  # pragma: no cover - network path
            raise RuntimeError(f"network error for {url}: {exc}") from exc

    @staticmethod
    def _json_array_param(values: list[str]) -> str:
        # Binance expects a compact JSON array in query params.
        return json.dumps(values, separators=(",", ":"))

    def exchange_info(self) -> dict[str, Any]:
        return self._get_json("/api/v3/exchangeInfo", {"symbolStatus": "TRADING"})

    def ticker_24hr(self, symbols: list[str] | None = None) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"type": "MINI", "symbolStatus": "TRADING"}
        if symbols:
            params["symbols"] = self._json_array_param(symbols)
        data = self._get_json("/api/v3/ticker/24hr", params)
        if isinstance(data, dict):
            return [data]
        return data

    def rolling_ticker(self, symbols: list[str], window_size: str) -> list[RollingTicker]:
        params = {
            "symbols": self._json_array_param(symbols),
            "windowSize": window_size,
            "type": "MINI",
        }
        data = self._get_json("/api/v3/ticker", params)
        if isinstance(data, dict):
            data = [data]
        return [
            RollingTicker(
                symbol=item["symbol"],
                open_price=float(item["openPrice"]),
                high_price=float(item["highPrice"]),
                low_price=float(item["lowPrice"]),
                last_price=float(item["lastPrice"]),
                volume=float(item["volume"]),
                quote_volume=float(item["quoteVolume"]),
                count=int(item["count"]),
            )
            for item in data
        ]

    def book_ticker(self, symbols: list[str] | None = None) -> list[dict[str, Any]]:
        params: dict[str, Any] = {}
        if symbols:
            params["symbols"] = self._json_array_param(symbols)
        data = self._get_json("/api/v3/ticker/bookTicker", params)
        if isinstance(data, dict):
            return [data]
        return data

    def depth(self, symbol: str, limit: int = 100) -> dict[str, Any]:
        return self._get_json("/api/v3/depth", {"symbol": symbol, "limit": limit})

    def klines(self, symbol: str, interval: str = "5m", limit: int = 24) -> list[list[Any]]:
        data = self._get_json("/api/v3/klines", {"symbol": symbol, "interval": interval, "limit": limit})
        return data


def _parse_exchange_symbols(exchange_info: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {item["symbol"]: item for item in exchange_info.get("symbols", [])}


def _ret_pct(open_price: float, last_price: float) -> float:
    if open_price <= 0:
        return 0.0
    return (last_price / open_price - 1.0) * 100.0


def _ticker_ret_24h(item: dict[str, Any]) -> float:
    price_change_pct = item.get("priceChangePercent")
    if price_change_pct not in (None, ""):
        try:
            return float(price_change_pct)
        except (TypeError, ValueError):
            pass
    try:
        return _ret_pct(float(item.get("openPrice", 0.0) or 0.0), float(item.get("lastPrice", 0.0) or 0.0))
    except (TypeError, ValueError):
        return 0.0


def _depth_usd(depth_rows: list[list[str]], reference_price: float, pct_band: float) -> float:
    if reference_price <= 0:
        return 0.0
    total = 0.0
    lower = reference_price * (1.0 - pct_band)
    upper = reference_price * (1.0 + pct_band)
    for price_str, qty_str in depth_rows:
        price = float(price_str)
        qty = float(qty_str)
        if lower <= price <= upper:
            total += price * qty
    return total


def _rolling_averages(snapshot: SymbolSnapshot) -> tuple[float, float]:
    avg_quote_volume_5m = snapshot.quote_volume_24h / 288.0 if snapshot.quote_volume_24h > 0 else 0.0
    avg_trade_count_5m = snapshot.trade_count_24h / 288.0 if snapshot.trade_count_24h > 0 else 0.0
    return avg_quote_volume_5m, avg_trade_count_5m


def _apply_structure(snapshot: SymbolSnapshot, klines: list[list[Any]]) -> None:
    if len(klines) < 8:
        return
    highs = [float(row[2]) for row in klines]
    lows = [float(row[3]) for row in klines]
    closes = [float(row[4]) for row in klines]
    quote_volumes = [float(row[7]) for row in klines]

    recent_close = closes[-1]
    high_30m = max(highs[-7:-1])
    low_10m = min(lows[-3:-1])
    prev_low = min(lows[-5:-3])
    avg_quote_volume = mean(quote_volumes[:-1]) if len(quote_volumes) > 1 else 0.0

    snapshot.distance_from_30m_high_pct = 0.0 if high_30m <= 0 else ((high_30m - recent_close) / high_30m) * 100.0
    snapshot.breakout_active = recent_close >= high_30m
    snapshot.held_breakout_retest = snapshot.breakout_active and low_10m >= high_30m * 0.995
    snapshot.higher_low_confirmed = low_10m > prev_low

    vwap_proxy = mean(closes[-4:])
    snapshot.vwap_reclaim = recent_close >= vwap_proxy and closes[-2] < vwap_proxy
    snapshot.extended_move_flag = (
        snapshot.ret_1h > 18.0 and recent_close > high_30m * 1.03 and quote_volumes[-1] > avg_quote_volume * 2.5
    )


def build_live_snapshots(client: BinanceSpotPublicClient, config: ScannerConfig) -> list[SymbolSnapshot]:
    exchange_info = client.exchange_info()
    exchange_map = _parse_exchange_symbols(exchange_info)

    all_tickers = client.ticker_24hr()
    universe: list[tuple[str, float, float]] = []
    for item in all_tickers:
        symbol = item["symbol"]
        info = exchange_map.get(symbol)
        if info is None:
            continue
        if info.get("status") != "TRADING":
            continue
        if not symbol.isascii():
            continue
        if not info.get("isSpotTradingAllowed", True):
            continue
        if not any(symbol.endswith(suffix) for suffix in config.universe.quote_asset_suffixes):
            continue
        if info.get("baseAsset") in config.universe.excluded_base_assets:
            continue
        if info.get("baseAsset") in STABLE_ASSETS and info.get("quoteAsset") in STABLE_ASSETS:
            continue
        quote_volume = float(item["quoteVolume"])
        if config.universe.max_quote_volume_24h > 0 and quote_volume > config.universe.max_quote_volume_24h:
            continue
        universe.append((symbol, quote_volume, _ticker_ret_24h(item)))

    by_quote_volume = sorted(universe, key=lambda item: item[1], reverse=True)
    by_24h_return = sorted(universe, key=lambda item: item[2], reverse=True)
    volume_symbols = [symbol for symbol, _, _ in by_quote_volume[: config.runtime.live_top_n_by_quote_volume]]
    gainer_symbols = [symbol for symbol, _, _ in by_24h_return[: config.runtime.live_top_n_by_24h_gainers]]
    selected_symbols = list(dict.fromkeys(volume_symbols + gainer_symbols))
    ret_24h_by_symbol = {symbol: ret_24h for symbol, _, ret_24h in universe}
    selection_sources: dict[str, set[str]] = {symbol: set() for symbol in selected_symbols}
    for symbol in volume_symbols:
        selection_sources.setdefault(symbol, set()).add("top-volume")
    for symbol in gainer_symbols:
        selection_sources.setdefault(symbol, set()).add("top-gainer")
    if not selected_symbols:
        return []

    rolling_by_window: dict[str, dict[str, RollingTicker]] = {"5m": {}, "15m": {}, "1h": {}}
    batch_size = config.runtime.rolling_window_batch_size
    for window in rolling_by_window:
        for start in range(0, len(selected_symbols), batch_size):
            batch = selected_symbols[start : start + batch_size]
            for item in client.rolling_ticker(batch, window):
                rolling_by_window[window][item.symbol] = item

    book_rows = {item["symbol"]: item for item in client.book_ticker(selected_symbols)}

    snapshots: list[SymbolSnapshot] = []
    for item in all_tickers:
        symbol = item["symbol"]
        if symbol not in selected_symbols:
            continue
        five = rolling_by_window["5m"].get(symbol)
        fifteen = rolling_by_window["15m"].get(symbol)
        one_hour = rolling_by_window["1h"].get(symbol)
        book = book_rows.get(symbol)
        if not (five and fifteen and one_hour and book):
            continue

        bid_price = float(book["bidPrice"])
        ask_price = float(book["askPrice"])
        last_price = float(item["lastPrice"])
        midpoint = (bid_price + ask_price) / 2.0 if bid_price and ask_price else last_price
        spread_pct = 0.0 if midpoint <= 0 else ((ask_price - bid_price) / midpoint) * 100.0

        snapshot = SymbolSnapshot(
            symbol=symbol,
            status="TRADING",
            last_price=last_price,
            bid_price=bid_price,
            ask_price=ask_price,
            quote_volume_24h=float(item["quoteVolume"]),
            ret_24h=ret_24h_by_symbol.get(symbol, 0.0),
            trade_count_24h=int(item["count"]),
            ret_5m=_ret_pct(five.open_price, five.last_price),
            ret_15m=_ret_pct(fifteen.open_price, fifteen.last_price),
            ret_1h=_ret_pct(one_hour.open_price, one_hour.last_price),
            quote_volume_5m=five.quote_volume,
            quote_volume_15m=fifteen.quote_volume,
            quote_volume_1h=one_hour.quote_volume,
            trade_count_5m=five.count,
            trade_count_15m=fifteen.count,
            trade_count_1h=one_hour.count,
            spread_pct=spread_pct,
            distance_from_24h_high_pct=0.0 if float(item["highPrice"]) <= 0 else ((float(item["highPrice"]) - last_price) / float(item["highPrice"])) * 100.0,
            tags=sorted(selection_sources.get(symbol, set()) | {"small-cap-proxy", "emerging-token-candidate"}),
            raw={"ticker_24h": item, "book_ticker": book},
        )
        avg_quote_volume_5m, avg_trade_count_5m = _rolling_averages(snapshot)
        snapshot.volume_multiple_5m = snapshot.quote_volume_5m / avg_quote_volume_5m if avg_quote_volume_5m > 0 else 0.0
        avg_quote_volume_15m = snapshot.quote_volume_24h / 96.0 if snapshot.quote_volume_24h > 0 else 0.0
        snapshot.volume_multiple_15m = snapshot.quote_volume_15m / avg_quote_volume_15m if avg_quote_volume_15m > 0 else 0.0
        snapshot.trade_count_multiple_5m = snapshot.trade_count_5m / avg_trade_count_5m if avg_trade_count_5m > 0 else 0.0
        snapshots.append(snapshot)

    def enrich_snapshot(snapshot: SymbolSnapshot) -> SymbolSnapshot:
        depth = client.depth(snapshot.symbol, config.runtime.depth_limit)
        snapshot.depth_usd_1pct_bid = _depth_usd(depth.get("bids", []), snapshot.last_price, 0.01)
        snapshot.depth_usd_1pct_ask = _depth_usd(depth.get("asks", []), snapshot.last_price, 0.01)
        snapshot.depth_usd_2pct_bid = _depth_usd(depth.get("bids", []), snapshot.last_price, 0.02)
        snapshot.depth_usd_2pct_ask = _depth_usd(depth.get("asks", []), snapshot.last_price, 0.02)
        _apply_structure(snapshot, client.klines(snapshot.symbol, interval="5m", limit=24))
        return snapshot

    with ThreadPoolExecutor(max_workers=min(8, max(1, len(snapshots)))) as executor:
        snapshots = list(executor.map(enrich_snapshot, snapshots))

    snapshots.sort(key=lambda item: item.quote_volume_24h, reverse=True)
    return snapshots
