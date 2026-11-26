# Volume Pricing — MEXC USDT Perpetual Forward Paper Simulation

A paper-only, market-neutral cross-sectional strategy that ranks every eligible MEXC USDT-settled perpetual by MEXC rolling 24-hour quote turnover divided by the asset's external USD market capitalization.

## Strategy

At each newly completed UTC daily candle, after the full eligible universe has current data:

1. Discover active MEXC cross-margin USDT-settled perpetuals; retain all `crypto` and `unclassified` contracts, excluding tokenized-stock suffixes and contracts categorized as equity, commodity or FX because those lack a comparable crypto circulating-market-cap denominator.
2. Calculate `MEXC 24h USDT turnover / external circulating market cap (USD)`.
3. Sort all assets in descending order of that ratio.
4. Traverse the same ranking to select the first asset with positive MEXC 24-hour price change as the long and the first asset with negative 24-hour price change as the short.
5. If either side is unavailable or either selected contract fails paper execution checks, do not silently substitute a lower-ranked asset. Report the blocked decision.

The market-cap data uses two no-authentication public sources. CoinPaprika Free provides 20,000 calls/month and a top-2,000 ticker list; the workflow uses its public coin catalogue and bounded individual lookups for remaining unique IDs. CoinGecko supplements missing symbols through eight `/coins/markets` pages of 250 assets each, paced 12.5 seconds apart to respect its shared 5–15 calls/minute public pool. CoinPaprika's 640-lookup/day quota guard remains in place. The portfolio still requires at least 80% fresh, unambiguous market-cap coverage; neither provider can bypass that gate. The free licences are for personal use, so raw catalogues and absolute market-cap values remain in a private Actions cache; public artifacts contain derived ratios, MEXC turnover, provider attribution and source timestamps. CoinMarketCap Keyless is restricted to evaluation/prototyping; CoinLore's site terms prohibit automated bots/data mining; CoinCap v3 requires an API key.

## Two independent performance paths

- **Primary:** equal-notional long and short, each targeting 1× NAV notional (50% NAV margin at 2× leverage).
- **Alternative:** inverse-volatility shadow equity curve using the same selected pairs and daily decision timestamps, 30 common completed daily returns, and scaled observed fees/funding. It is a visual-only counterfactual, not a second paper account or execution ledger.

Both start at 100 USDT. The primary path uses the proven MEXC paper engine's book-depth fills, fees, slippage, confirmed funding, event ledger, 3× ATR trailing stop and 25% combined daily drawdown protection.

## Cadence and persistence

- GitHub Actions intended schedule: every five minutes (`*/5 * * * *`); scheduling is best-effort.
- Portfolio decisions: once per newly completed UTC daily candle.
- Intervening runs: mark-to-market snapshots, funding and risk checks only.
- Persistent MEXC market data: `market-data` branch.
- Immutable paper account events: `state-coinpaprika-v2` branch.
- Main branch: code, `PAPER_STATUS.md`, journal and equity curves.
- Public MEXC endpoints only. No API keys, exchange credentials, private endpoints, wallet access, testnet or live orders.

## Data-source limitations

A market-cap provider's global 24-hour volume is **not** the numerator. The numerator is MEXC's own 24-hour USDT contract turnover. The denominator is the provider's circulating market capitalization in USD. USDT is treated as approximately USD 1:1 for this ratio.

Symbols are joined conservatively. Ambiguous symbols, missing/zero market caps, stale market-cap observations, stale tickers and invalid turnover are excluded and reported. A portfolio decision requires at least 80% of the distinct eligible MEXC base-asset symbols to have fresh, unambiguous market-cap matches; otherwise the cycle fails closed. A symbol match is not proof of contract identity; the implementation does not guess among duplicate symbols.

At each decision, the public snapshot records the derived volume/market-cap ratio, MEXC turnover, provider attribution and source timestamp. Absolute provider market-cap values remain in the private daily Actions cache and are not published to the repository or workflow artifacts. This is a forward paper simulation, not a backtest using today's market capitalization for historical dates.

## Status

The first workflow run bootstraps public MEXC history and verifies the append-only state branch. No paper account is initialized until the recovery protocol succeeds and the full current data-coverage gate passes. See [DATA_SOURCES.md](docs/DATA_SOURCES.md) and [OPERATING_MODEL.md](docs/OPERATING_MODEL.md).

## Attribution

CoinPaprika attribution is included in the status and strategy documentation. The Free API is for personal use; the workflow stores derived strategy metrics rather than the raw 2,000-asset catalogue or absolute provider market-cap values.
