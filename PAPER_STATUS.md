# PAPER STATUS — VOLUME PRICING $100 USDT

**BOOTSTRAPPING · PAPER ONLY · NO LIVE ORDERS**

**Correct workflow:** [Open active workflow](https://github.com/takenthatusernameis-collab/VOLUME-PRICING/actions/workflows/volume-pricing-paper-cycle.yml)

- Account: `mexc-usdt-forward-volume-pricing-100usdt-v1`
- Strategy generation: `volume-to-market-cap-first-positive-negative-v1`
- Starting capital: **100.00000000 USDT**
- Account state: **READY — WAITING FOR FIRST FINANCIAL PAPER EVENT**
- Last report build: 2026-11-26 11:19:46 UTC
- Latest workflow run: [45808016426](https://github.com/takenthatusernameis-collab/VOLUME-PRICING/actions/runs/45808016426) · run #2, attempt 1 · failure · push
- Latest processed daily candle: —
- Latest account event: —
- Primary execution journal: [PAPER_TRADE_JOURNAL.md](PAPER_TRADE_JOURNAL.md)


## MEXC universe and data coverage

- Coverage state: **BOOTSTRAPPING**
- Active USDT-settled cross-margin perpetuals: —
- MEXC tickers received: —
- Missing tickers: —
- History bootstrap remaining: —
- API failures: —
- Latest completed daily candle (UTC ms): —
- Portfolio decision: `PUBLISH_READBACK_VERIFIED_AWAITING_FRESH_CHECKOUT`

### Volume-to-market-cap ranking

Numerator: MEXC rolling 24-hour USDT quote turnover. Denominator: circulating market capitalization in USD.

**Highest-ranked positive 24-hour change candidates (long side):**
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
| Lifetime / cross-session maximum drawdown | Unavailable — no account observations yet |
| Worst risk-session maximum drawdown | Unavailable — no account observations yet |
| Sharpe ratio | Unavailable — sample gate not met |
| Sortino ratio | Unavailable — sample gate not met |
| Annualized daily volatility | Unavailable — sample gate not met |

### Maximum drawdown by risk session

| Session start (UTC) | Starting NAV | Latest NAV | Max drawdown | Marks |
|---|---:|---:|---:|---:|
| No risk sessions observed | — | — | — | 0 |

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

The next eligible cycle can process the latest genuine completed UTC daily candle; the new account has no consumed-candle watermark.

The daily-candle watermark is not advanced by this report. Only the paper workflow can consume a completed candle after full-history and execution gates pass. A blocked or incomplete run remains visible.

## Historical separation

The v3 $50 USDT generation and its preliminary snapshots are archived and excluded from this account’s NAV, returns, equity curves and metrics. The immutable event ledger remains intact.

## Alternative-path reconstruction notes

- No reconstruction warnings.

This is the compact live status page. The former detailed v3 report is retained under `archive/2026-11-18/` for audit purposes only.
