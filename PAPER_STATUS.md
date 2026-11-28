# BOOTSTRAPPING PAPER STATUS — VOLUME PRICING $100 USDT

**BOOTSTRAPPING · PAPER ONLY · NO LIVE ORDERS**

**Correct workflow:** [Open active workflow](https://github.com/takenthatusernameis-collab/VOLUME-PRICING/actions/workflows/volume-pricing-paper-cycle.yml)

- Account: `mexc-usdt-forward-volume-pricing-coinpaprika-100usdt-v2`
- Strategy generation: `volume-to-market-cap-first-positive-negative-coinpaprika-v2`
- Starting capital: **100.00000000 USDT**
- Account state: **INITIALIZED — FORWARD PAPER**
- Last report build: 2026-11-28 02:50:04 UTC
- Latest workflow run: [46099518872](https://github.com/takenthatusernameis-collab/VOLUME-PRICING/actions/runs/46099518872) · run #32, attempt 1 · failure · schedule
- Latest processed daily candle: 2026-11-25 00:00 UTC
- Latest account event: 2026-11-28 02:49:43 UTC
- Primary execution journal: [PAPER_TRADE_JOURNAL.md](PAPER_TRADE_JOURNAL.md)


## MEXC universe and data coverage

- Coverage state: **BOOTSTRAPPING**
- Active USDT-settled cross-margin perpetuals: 1090
- Strategy-eligible crypto/unclassified contracts: 611
- Excluded tokenized-stock suffix contracts (overlaps category counts): 448
- Excluded non-crypto categories: {'commodity': 13, 'equity': 142, 'fx': 6}
- MEXC tickers received: 2
- Missing tickers: 0
- History bootstrap remaining: 0
- API failures: 0
- Latest completed daily candle (UTC ms): 1795564800000
- Portfolio decision: `FAILED`
- Market-cap provider: coinpaprika+coingecko — Powered by CoinPaprika; Powered by CoinGecko
- Fresh market-cap matches: 514/611
- Market-cap API calls: CoinPaprika 13/642; CoinGecko 8/8

### Volume-to-market-cap ranking

Numerator: MEXC rolling 24-hour USDT quote turnover. Denominator: circulating market capitalization in USD.

**Highest-ranked positive 24-hour change candidates (long side):**
- Cycle error: `ValueError: nav must be positive`
- ANTHROPIC_USDT: ratio=786.9282990471105548999670127%, MEXC 24h change=0.0045, market-cap source=coinpaprika match=exact_coinpaprika_top_2000
- LAB_USDT: ratio=41.58089691685163016614432339%, MEXC 24h change=0.0105, market-cap source=coinpaprika match=exact_coinpaprika_top_2000
- INIT_USDT: ratio=41.17441566171532285569618224%, MEXC 24h change=0.0344, market-cap source=coinpaprika match=exact_coinpaprika_top_2000
- MANTRA_USDT: ratio=34.86486874065990902702984139%, MEXC 24h change=0.0099, market-cap source=coinpaprika match=exact_coinpaprika_top_2000
- GUA_USDT: ratio=26.62341278729432845337195529%, MEXC 24h change=0.0153, market-cap source=coinpaprika match=exact_coinpaprika_top_2000
- BIGTIME_USDT: ratio=23.35768918948540692749272902%, MEXC 24h change=0.0099, market-cap source=coinpaprika match=exact_coinpaprika_top_2000
- AKE_USDT: ratio=20.99075692062352451628968150%, MEXC 24h change=0.2365, market-cap source=coinpaprika match=exact_coinpaprika_top_2000
- MMT_USDT: ratio=15.57635294708743503599278533%, MEXC 24h change=0.0246, market-cap source=coingecko match=exact_coingecko_top_2000
- GUN_USDT: ratio=12.52236188136651931577935806%, MEXC 24h change=0.0007, market-cap source=coinpaprika match=exact_coinpaprika_top_2000
- ME_USDT: ratio=12.38982915175821657026476009%, MEXC 24h change=0.0433, market-cap source=coinpaprika match=exact_coinpaprika_top_2000

**Highest-ranked negative 24-hour change candidates (short side):**
- BULLA_USDT: ratio=128.4386327457821085596052024%, MEXC 24h change=-0.2511, market-cap source=coinpaprika match=exact_coinpaprika_top_2000
- EVAA_USDT: ratio=127.5156929939434583609500498%, MEXC 24h change=-0.1547, market-cap source=coinpaprika match=exact_coinpaprika_top_2000
- SPY_USDT: ratio=123.8565944085048324431746741%, MEXC 24h change=-0.0002, market-cap source=coingecko match=exact_coingecko_top_2000
- BLESS_USDT: ratio=61.40940470526122240766447873%, MEXC 24h change=-0.0833, market-cap source=coinpaprika match=exact_coinpaprika_top_2000
- MOVE_USDT: ratio=52.24942906552411516466737826%, MEXC 24h change=-0.0227, market-cap source=coinpaprika match=exact_coinpaprika_top_2000
- DCTY_USDT: ratio=33.02310523427023900297110404%, MEXC 24h change=-0.0326, market-cap source=coinpaprika match=exact_coinpaprika_top_2000
- SI_USDT: ratio=26.01741201242544143269171741%, MEXC 24h change=-0.0179, market-cap source=coingecko match=exact_coingecko_top_2000
- ACE_USDT: ratio=23.38694998544708479353788505%, MEXC 24h change=-0.005, market-cap source=coinpaprika match=exact_coinpaprika_top_2000
- SSV_USDT: ratio=14.88356978307003717811781508%, MEXC 24h change=-0.0043, market-cap source=coinpaprika match=exact_coinpaprika_top_2000
- LISTA_USDT: ratio=13.98481304357618542012252427%, MEXC 24h change=-0.0058, market-cap source=coinpaprika match=exact_coinpaprika_top_2000

Portfolio entry remains blocked until MEXC history and ticker coverage pass.

## Current performance

| Metric | Value |
|---|---:|
| Initial capital | 100.00000000 USDT |
| **NAV** | **-48.56441380 USDT** |
| Total return | -148.564% |
| Cash | -48.56441380 USDT |
| Unrealized P&L | +0.00000000 USDT |
| Fees paid | 0.06989380 USDT |
| Confirmed funding | +0.00000000 USDT |
| Gross exposure | 0.000× NAV |
| Net exposure | 0.000× NAV |
| Current drawdown from risk-window peak | +0.000% |
| Lifetime / cross-session maximum drawdown | -147.938% |
| Worst risk-session maximum drawdown | -147.938% |
| Sharpe ratio | Unavailable — sample gate not met |
| Sortino ratio | Unavailable — sample gate not met |
| Annualized daily volatility | Unavailable — sample gate not met |

### Maximum drawdown by risk session

| Session start (UTC) | Starting NAV | Latest NAV | Max drawdown | Marks |
|---|---:|---:|---:|---:|
| 2026-11-26 00:00:00 UTC | 100.00000000 | 100.00000000 | +0.000% | 15 |
| 2026-11-26 20:09:16 UTC | 99.72424180 | 101.30686180 | -0.207% | 2 |
| 2026-11-27 00:00:00 UTC | 101.30686180 | -48.56441380 | -147.938% | 3 |
| 2026-11-28 00:00:00 UTC | -48.56441380 | -48.56441380 | +0.000% | 1 |

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

- Latest long / short allocation: **86.3% / 13.7%** of alternative gross notional.
- Latest volatility-matching leverage multiplier: **2.875×**.
- Estimated base volatility reduction before leverage: **+65.21%**.
- Volatility observations used: **30**; status: `RISK_MATCHED_INVERSE_VOLATILITY`.

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
