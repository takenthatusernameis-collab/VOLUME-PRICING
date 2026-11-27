# Primary Volume Pricing Paper Trade Journal — MEXC $100 USDT

**Primary equal-exposure account only.** This journal is reconstructed from the verified, append-only Volume Pricing event chain. It contains no alternative-path trades or shadow executions.

- Account: `mexc-usdt-forward-volume-pricing-coinpaprika-100usdt-v2`
- Strategy generation: `volume-to-market-cap-first-positive-negative-coinpaprika-v2`
- Starting capital: **100.00000000 USDT**
- Generated: 2026-11-27 20:17:00 UTC
- Latest workflow: [46062182971](https://github.com/takenthatusernameis-collab/VOLUME-PRICING/actions/runs/46062182971)
- Recorded primary events: **4**

| Timestamp (UTC) | Symbol | Side | Action | Quantity | Price | Fee (USDT) | Realized net P&L (USDT) | Funding (USDT) | Event ID |
|---|---|---|---|---:|---:|---:|---:|---:|---|
| 2026-11-26 20:09:16 UTC | ANTHROPIC_USDT | long | OPENED | 1.186 | 84.32 | 0.00000 | — | — | `paper_entry_retry-snapshot-1795723748235` |
| 2026-11-26 20:09:16 UTC | BULLA_USDT | short | OPENED | 3050 | 0.03262 | 0.019898200 | — | — | `paper_entry_retry-snapshot-1795723748235` |
| 2026-11-27 02:52:44 UTC | ANTHROPIC_USDT | long | CLOSED | 1.186 | 84.32 | 0.00000 | — | — | `paper_risk_update-risk-1795747964772` |
| 2026-11-27 02:52:44 UTC | BULLA_USDT | short | CLOSED | 3050 | 0.03262 | 0.019898200 | — | — | `paper_risk_update-risk-1795747964772` |

This journal covers only the primary paper account. The inverse-volatility alternative path has no separate trade journal, positions or event stream.
