# Small-Cap Radar

Final project prototype for **Big Data Systems: Designing a System That Monetizes Data**.

Small-Cap Radar turns fragmented crypto market data into a subscription-style market-intelligence dashboard for active retail crypto traders who monitor small-cap and high-beta tokens. The current product is a data dashboard, not a trading bot: it shows 24h movers, short-term momentum, volume expansion, liquidity depth, spread checks, and event notes in one place.

The product is for market monitoring and education only. It is not financial advice and does not provide buy/sell recommendations.

## Target Customer

The initial customer segment is active retail crypto traders and small trading communities that frequently check small-cap tokens, meme coins, new listings, exchange announcements, and short-term market movers.

Their current workflow is manual:

- check Binance, OKX, KuCoin, CoinGecko, TradingView, Telegram, and X
- scan top gainers and high-volume symbols
- inspect 24h movement, 1h movement, 15m movement, volume spikes, spread, and order-book depth
- decide which symbols deserve deeper manual research

Small-Cap Radar reduces this fragmented workflow into one clean market-data dashboard.

## Value Proposition

Small-cap token monitoring is time-sensitive and noisy. The system monetizes data by converting public but scattered market data into a paid intelligence layer:

- **Free tier:** delayed daily movers and liquidity summary
- **Basic tier:** USD 9-19/month for live dashboard access
- **Pro tier:** USD 49/month for custom filters, CSV/API export, and community watchlists

The customer pays for saved monitoring time, faster discovery, and clearer liquidity/volume context.

## Data Sources

The prototype uses public or local reproducible sources:

- Binance Spot public REST market data
- Binance Alpha public token list
- OKX official announcement pages
- KuCoin new-listing announcement pages
- local manual event feed at `data/local_event_feed.json`
- sample market snapshot at `data/sample_market_snapshot.json`

The Vercel demo runs a live Binance Spot public market scan and applies the small-cap filter at request time. The local fallback demo uses fixed real Binance spot pairs such as `MEMEUSDT`, `ORDIUSDT`, `WIFUSDT`, `BONKUSDT`, `PEPEUSDT`, and `FLOKIUSDT` only so the course demo remains reproducible when network access is unavailable.

The project avoids storing private user trading data in the public repository. Optional credentials must stay in `.env.local`, which is ignored by git.

## Technical Architecture

The system is split into:

1. **Event ingestion**: collect official exchange announcements and local event notes.
2. **Small-cap universe filtering**: exclude major blue-chip assets and keep symbols inside a configurable 24h quote-volume band.
3. **Market ingestion**: collect price, volume, spread, order-book depth, and trade-count features.
4. **Feature processing**: compute short-window returns, volume multiples, liquidity depth, spread, and market context.
5. **Dashboard delivery**: show market movers, market notes, event notes, and comparable raw indicators.

The current small-cap proxy is defined in `data/scanner_config.toml`: major base assets are excluded and the live scanner skips symbols with 24h quote volume above `max_quote_volume_24h`. This is not a perfect market-cap measure, but it is reproducible using public market data.

See `ARCHITECTURE.md` and `report/architecture_diagram.mmd` for the full architecture.

## Local Fallback Demo

Use Python 3.11 or newer.

Build the demo dashboard state:

```bash
PYTHONPATH=src python3 scripts/build_demo_state.py
```

Start the local dashboard:

```bash
PYTHONPATH=src python3 -m new_coins_scanner.cli dashboard
```

Then open the dashboard URL printed by the command.

CLI sample run:

```bash
PYTHONPATH=src python3 -m new_coins_scanner.cli sample --limit 6
```

Event-source demo:

```bash
PYTHONPATH=src python3 -m new_coins_scanner.cli events --limit 5
```

Announcement evidence export:

```bash
PYTHONPATH=src python3 scripts/export_announcement_evidence.py --out data/demand_evidence/announcement_evidence.csv
```

Live market scan, if network access is available:

```bash
PYTHONPATH=src python3 -m new_coins_scanner.cli live --limit 20
```

## Deployment

The repository includes a Vercel-compatible Python function:

- `api/index.py`
- `vercel.json`

The intended assignment deployment is a read-only or password-gated live dashboard. The Vercel function calls Binance Spot public market data at request time. Optional environment variables must be configured in the deployment provider and must never be committed.

Useful optional environment variables:

```bash
BINANCE_SPOT_API_BASE=https://data-api.binance.vision
DASHBOARD_PASSWORD=choose_a_private_password
DASHBOARD_SECRET=optional_cookie_secret
```

## Demand Evidence

Demand-validation materials are in `data/demand_evidence/`:

- `survey_results.csv`: planning/pilot rows that should be replaced with real responses before final submission if possible
- `competitor_pricing.csv`: pricing benchmarks for analogous crypto alert/intelligence products
- `announcement_evidence.csv`: generated by the export script when network access is available

These files support the final report sections on demand evidence and willingness to pay.

## Report Source

The report source is in `report/final_project_report.tex`.

Before submission, convert the report to a single PDF named:

```text
b11902138.pdf
```

## Ethics and Disclaimer

This project analyzes public market and announcement data for educational purposes. It does not promise profitable trades, does not provide individualized financial advice, and should not be used as the sole basis for investment decisions. Scraping or data collection should respect source terms of service, robots.txt, rate limits, and applicable privacy regulations.
