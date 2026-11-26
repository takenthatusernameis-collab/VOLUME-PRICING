# Volume Pricing — Operating Model

## Account and safety

- Independent 100 USDT forward-paper account.
- MEXC public USDT perpetual market data only.
- No exchange API keys, private endpoints, wallet/account access, Testnet or live orders.
- The paper engine is checked out from `takenthatusernameis-collab/high-vs-low`; the strategy wrapper and account identity are isolated in this repository.
- Primary portfolio uses the established equal-notional 2× leverage convention: 50% NAV margin per leg, 1× NAV notional per leg.
- Existing engine costs and safeguards are retained: depth-weighted simulated fills, taker fees, slippage/shortfall, confirmed funding, 3× ATR trailing stops and 25% combined daily drawdown flattening.

## Universe

Discover active MEXC cross-margin perpetuals, then restrict the strategy universe to USDT-settled crypto and unclassified token contracts. Exclude MEXC equity, commodity and FX categories, plus tokenized-stock contracts whose base symbols end in STOCK, because their capitalization denominators are not comparable to circulating crypto market cap. No fixed symbol allowlist or arbitrary market-cap floor. Report every contract excluded by asset class, USDT eligibility, ticker, market-cap, history or execution checks.

## Signal and ranking

At the first eligible run after a newly completed UTC daily candle:

1. Get the complete eligible MEXC USDT perpetual universe and fresh MEXC tickers.
2. Resolve each base asset to an exact, unambiguous CoinPaprika record first, then an exact unique CoinGecko record; only strip a documented MEXC 1,000×/10,000×/1,000,000× denomination prefix when the underlying provider symbol is unique.
3. Calculate MEXC rolling 24-hour USDT quote turnover divided by circulating market cap in USD.
4. Sort all matched assets descending by this ratio. Tie-break deterministically by MEXC symbol and instrument ID.
5. Filter this single ranking by the sign of MEXC's rolling 24-hour price change. The first positive-change asset is the long; the first negative-change asset is the short.
6. Only those first two candidates are executable. If either cannot be executed under the paper engine's book/lot/shortfall checks, do not silently fall through to a lower-ranked symbol.
7. Require at least 80% fresh, unambiguous market-cap coverage across distinct eligible base-asset symbols; otherwise fail closed.
8. Persist the derived ranking ratios, MEXC turnover, exclusions, provider attribution and source timestamps. Keep absolute market caps and the provider cache in the private Actions cache, not the public repository.

The ranking order is not the long/short signal by itself: the price-change sign determines direction.

## Cadence

- GitHub Actions intended schedule: `*/5 * * * *`; this is best-effort scheduling, not a five-minute SLA.
- Portfolio decisions: once per newly completed UTC daily candle, after full eligible-universe market-data coverage passes.
- Intervening invocations: mark-to-market snapshots, funding settlement processing, stop/risk checks and recovery of a previously frozen pending entry. Do not recompute ordinary portfolio weights or make a second daily decision.
- The daily candle watermark prevents duplicate decisions.

## Data history and coverage

The reused engine bootstraps a 45-day rolling MEXC daily-candle window in bounded batches and persists it on `market-data`. This is sufficient for ATR14 and the 30-day inverse-volatility path; no all-time history is required. It requires the latest completed daily bar and current ticker coverage before a portfolio transition. CoinPaprika and CoinGecko lookups are deferred until full MEXC history/ticker coverage passes and run once per daily decision, not on five-minute snapshots. CoinPaprika is capped at 640 individual lookups plus two catalogue calls per day; CoinGecko uses eight paginated public calls paced at 12.5-second intervals. The inverse-volatility path uses 30 common completed daily returns; it does not claim that the market-cap data source provides historical market caps.

## Portfolio paths

### Primary: equal notional

One long and one short, each targeting 1× NAV notional at 2× leverage. Contract quantity is rounded down to MEXC lot rules. Costs and funding are applied to the primary account ledger.

### Alternative: inverse volatility

A visual-only shadow path replays the primary account's selected symbols, sides and entry/exit timestamps. It uses 30 common completed daily returns to weight the lower-volatility leg more heavily and applies the engine's volatility-matching overlay only when estimated pair volatility falls. Primary fees and confirmed funding are scaled by shadow notional. It is not a second account, does not submit fills and does not independently model nonlinear impact, depth or leverage constraints.

## Persistence and reporting

- `main`: source code, `PAPER_STATUS.md`, trade journal and SVG curves.
- `market-data`: MEXC daily history, ticker snapshots, a non-sensitive daily provider-attempt latch, derived ranking snapshots and cycle diagnostics. Absolute market caps and the provider cache are excluded from this public branch.
- `state-coinpaprika-v2`: isolated immutable, hash-chained events for the v2 paper account, now using CoinPaprika with CoinGecko supplemental market-cap coverage. The initial provider experiment remains isolated on the old `state` branch.
- One non-cancelling GitHub Actions concurrency group serializes all state writers.
- The publisher verifies remote read-back; the next invocation restores the fresh state branch before financial account initialization.
- Every report separates market-data coverage, market-cap matching, signal selection, execution, account initialization and performance evidence.

No live-trading capability is included.
