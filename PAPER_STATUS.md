# BOOTSTRAPPING PAPER STATUS — VOLUME PRICING $100 USDT

**BOOTSTRAPPING · PAPER ONLY · NO LIVE ORDERS**

**Correct workflow:** [Open active workflow](https://github.com/takenthatusernameis-collab/VOLUME-PRICING/actions/workflows/volume-pricing-paper-cycle.yml)

- Account: `mexc-usdt-forward-volume-pricing-coinpaprika-100usdt-v2`
- Strategy generation: `volume-to-market-cap-first-positive-negative-coinpaprika-v2`
- Starting capital: **100.00000000 USDT**
- Account state: **INITIALIZED — FORWARD PAPER**
- Last report build: 2026-11-26 19:23:23 UTC
- Latest workflow run: [45883229583](https://github.com/takenthatusernameis-collab/VOLUME-PRICING/actions/runs/45883229583) · run #16, attempt 1 · skipped · push
- Latest processed daily candle: —
- Latest account event: 2026-11-26 19:12:20 UTC
- Primary execution journal: [PAPER_TRADE_JOURNAL.md](PAPER_TRADE_JOURNAL.md)


## MEXC universe and data coverage

- Coverage state: **BOOTSTRAPPING**
- Active USDT-settled cross-margin perpetuals: —
- Strategy-eligible crypto/unclassified contracts: 611
- Excluded tokenized-stock suffix contracts (overlaps category counts): 446
- Excluded non-crypto categories: {'commodity': 13, 'equity': 139, 'fx': 6}
- MEXC tickers received: —
- Missing tickers: —
- History bootstrap remaining: —
- API failures: —
- Latest completed daily candle (UTC ms): —
- Portfolio decision: `FAILED`
- Market-cap provider: coinpaprika — Powered by CoinPaprika
- Fresh market-cap matches: 460/611
- Market-cap API calls: CoinPaprika —/642; CoinGecko —/8

### Volume-to-market-cap ranking

Numerator: MEXC rolling 24-hour USDT quote turnover. Denominator: circulating market capitalization in USD.

**Highest-ranked positive 24-hour change candidates (long side):**
- Cycle error: `MarketCapDataError: Fresh, unambiguous market-cap coverage is below the 80% safety gate: 460/611 symbols`
- No eligible positive-change candidate.

**Highest-ranked negative 24-hour change candidates (short side):**
- No eligible negative-change candidate.

Portfolio transitions remain blocked until the complete eligible MEXC USDT universe passes the market-data gate.

## Current performance

| Metric | Value |
|---|---:|
| Initial capital | 100.00000000 USDT |
| **NAV** | **100.00000000 USDT** |
| Total return | +0.000% |
| Cash | 100.00000000 USDT |
| Unrealized P&L | +0.00000000 USDT |
| Fees paid | 0.00000000 USDT |
| Confirmed funding | +0.00000000 USDT |
| Gross exposure | 0.000× NAV |
| Net exposure | 0.000× NAV |
| Current drawdown from risk-window peak | +0.000% |
| Lifetime / cross-session maximum drawdown | +0.000% |
| Worst risk-session maximum drawdown | +0.000% |
| Sharpe ratio | Unavailable — sample gate not met |
| Sortino ratio | Unavailable — sample gate not met |
| Annualized daily volatility | Unavailable — sample gate not met |

### Maximum drawdown by risk session

| Session start (UTC) | Starting NAV | Latest NAV | Max drawdown | Marks |
|---|---:|---:|---:|---:|
| 2026-11-26 00:00:00 UTC | 100.00000000 | 100.00000000 | +0.000% | 9 |

## Open positions

| Symbol | Side | Quantity | Entry price | Mark | Notional (USDT) |
|---|---|---:|---:|---:|---:|
| No open positions yet | — | — | — | — | — |

## Primary path — equal exposure

The live forward-paper strategy sizes the long and short legs independently toward equal USDT notional (approximately 1× NAV per leg before lot rounding).

![Equal-exposure strategy equity curve](equal_exposure_equity_curve.svg)

## Alternative path — volatility-weighted sizing

This chart is a **visual-only counterfactual**, not an executed account. It reuses the primary strategy’s exact selected symbols, sides and rebalance timestamps; only the notional split changes. No alternative trade journal is created.

At each rebalance, the quieter leg receives the larger share using inverse 30-completed-day realized volatility. The leverage overlay is the ratio of equal-exposure pair volatility to the inverse-volatility pair’s base estimated volatility. It increases modeled gross exposure only when the alternative has lower estimated volatility. Estimates use only data available at that rebalance.

- Latest long / short allocation: **50.0% / 50.0%** of alternative gross notional.
- Latest volatility-matching leverage multiplier: **1.000×**.
- Estimated base volatility reduction before leverage: **+0.00%**.
- Volatility observations used: **0**; status: `AWAITING_FIRST_PAIR`.

![Inverse-volatility alternative equity curve](alternative_path_equity_curve.svg)

**Model limitations:** the counterfactual scales observed primary entry/exit fees and funding by shadow notional. It does not model additional nonlinear market impact, depth constraints, liquidation limits or exchange leverage caps for larger hypothetical exposure. It is not an executable leverage recommendation.

## Next workflow action

The next daily decision requires a newer completed UTC candle and a passing data-coverage gate.

The daily-candle watermark is not advanced by this report. Only the paper workflow can consume a completed candle after full-history and execution gates pass. A blocked or incomplete run remains visible.

## Historical separation

The initial provider-validation attempt is isolated from this CoinPaprika-only v2 account. The current immutable paper ledger is on the state-coinpaprika-v2 branch.

## Alternative-path reconstruction notes

- No reconstruction warnings.

This is the current live status page for the CoinPaprika-only v2 paper simulation.
