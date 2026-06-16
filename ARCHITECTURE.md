# System Architecture

## Product Goal

Small-Cap Radar converts public crypto market data into a paid market-intelligence product. The system helps active retail traders and small trading communities monitor small-cap tokens, new listings, short-term momentum, liquidity, spread, volume expansion, and event context without manually checking multiple sources.

The current product is framed as a data dashboard. It does not provide trade execution, buy/sell recommendations, or financial advice.

## End-to-End Flow

1. **Event ingestion**
   - Binance Alpha public token list
   - OKX official announcements
   - KuCoin new-listing announcements
   - local manual event feed for reproducible examples

2. **Small-cap universe filter**
   - excludes major blue-chip crypto base assets such as BTC, ETH, BNB, SOL, XRP, DOGE, ADA, AVAX, LINK, LTC, and similar large assets
   - keeps live candidates inside a configurable 24h quote-volume band
   - uses `max_quote_volume_24h` as a practical liquidity-based proxy because the prototype avoids adding a separate market-cap data dependency

3. **Market ingestion**
   - Binance Spot public REST endpoints
   - last price and 24h quote volume
   - 5m, 15m, 1h, and 24h returns
   - spread and order-book depth
   - recent trade-count and volume proxies

4. **Feature processing**
   - maps event symbols to market symbols
   - computes volume multiples against simple historical baselines
   - estimates liquidity through spread and depth
   - derives market notes such as spread, order-book depth, quote volume, and fast movement context
   - attaches event and narrative notes when available

5. **Delivery**
   - local dashboard for momentum board, market snapshot, market notes, and event notes
   - CLI output for reproducible local runs
   - Vercel-compatible web entrypoint for optional deployment
   - CSV evidence export for demand-validation data collection

## Data Product Boundary

The monetized product is the processed market-intelligence dashboard:

- consolidated announcement visibility
- small-cap and high-beta token filtering
- 24h movers and short-window momentum
- volume-spike and liquidity context
- spread and order-book depth context
- optional paid filters/export in the business model

The system does not guarantee investment outcomes and does not claim that a token should be bought or sold. It reduces monitoring effort and helps users decide what deserves deeper manual research.

## Main Modules

- `src/new_coins_scanner/binance.py` -> Binance public market-data ingestion
- `src/new_coins_scanner/event_providers.py` -> announcement and event-source ingestion
- `src/new_coins_scanner/event_engine.py` -> event processing and symbol merge
- `src/new_coins_scanner/scoring.py` -> internal feature scoring used for sorting market rows
- `src/new_coins_scanner/state_views.py` -> dashboard-ready market rows
- `src/new_coins_scanner/dashboard.py` -> local dashboard rendering
- `src/new_coins_scanner/live_web.py` -> Vercel-compatible live dashboard state builder
- `src/new_coins_scanner/cli.py` -> reproducible command-line entrypoints
- `scripts/build_demo_state.py` -> local dashboard demo-state builder
- `scripts/export_announcement_evidence.py` -> demand-evidence export helper

## Reproducible Commands

Build demo dashboard state:

```bash
PYTHONPATH=src python3 scripts/build_demo_state.py
```

Start local dashboard:

```bash
PYTHONPATH=src python3 -m new_coins_scanner.cli dashboard
```

Sample market-intelligence run:

```bash
PYTHONPATH=src python3 -m new_coins_scanner.cli sample --limit 6
```

Event-source run:

```bash
PYTHONPATH=src python3 -m new_coins_scanner.cli events --limit 5
```

Announcement-evidence export:

```bash
PYTHONPATH=src python3 scripts/export_announcement_evidence.py --out data/demand_evidence/announcement_evidence.csv
```

## Scalability Notes

The prototype uses local JSON fixtures and direct HTTP ingestion so the project remains easy to reproduce. A production version would separate ingestion, processing, and delivery:

- scheduled jobs for exchange-announcement ingestion
- object storage for raw announcement snapshots
- persistent database for symbol features and dashboard rows
- stream processing for live alert updates
- cached dashboard/API layer for paid customers

At 10x scale, the most likely bottleneck is source rate limiting and repeated market-data fetches. At 100x scale, the system would need deduplicated ingestion jobs, backoff policies, paid data licenses where required, and a persistent feature store.
