#!/usr/bin/env python3
"""Build primary status/journal and the inverse-volatility shadow equity curve."""
from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENGINE_ROOT = ROOT.parent / "engine"
sys.path.insert(0, str(ENGINE_ROOT / "src"))

from high_vs_low.market_data_store import MarketDataStore
import high_vs_low.paper_status as status

status.ACCOUNT_ID = "mexc-usdt-forward-volume-pricing-coinpaprika-100usdt-v2"
status.STRATEGY_ID = "volume-to-market-cap-first-positive-negative-coinpaprika-v2"
status.INITIAL_CAPITAL = Decimal("100")

market_data = Path(os.environ.get("MARKET_DATA_DIR", "../market-data"))
state_dir = Path(os.environ.get("PAPER_STATE_DIR", "../state"))
generated_at_ms = int(datetime.now(UTC).timestamp() * 1000)
store = MarketDataStore(market_data, provider="mexc")
history = store.load_all_candles(
    start_timestamp_ms=max(0, generated_at_ms - 45 * 86_400_000)
)
metadata = {
    "repository": os.environ.get("GITHUB_REPOSITORY", ""),
    "server_url": os.environ.get("GITHUB_SERVER_URL", "https://github.com"),
    "run_id": os.environ.get("GITHUB_RUN_ID", ""),
    "run_number": os.environ.get("GITHUB_RUN_NUMBER", ""),
    "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT", ""),
    "run_url": (
        f"{os.environ.get('GITHUB_SERVER_URL', 'https://github.com')}/"
        f"{os.environ.get('GITHUB_REPOSITORY', '')}/actions/runs/"
        f"{os.environ.get('GITHUB_RUN_ID', '')}"
    ),
    "outcome": os.environ.get("PAPER_WORKFLOW_OUTCOME", "unknown"),
    "event_name": os.environ.get("GITHUB_EVENT_NAME", "scheduled"),
}
markdown = status.render_paper_status(
    state_dir,
    history,
    metadata,
    generated_at_ms=generated_at_ms,
    equal_svg_path=ROOT / "equal_exposure_equity_curve.svg",
    alternative_svg_path=ROOT / "alternative_path_equity_curve.svg",
)
markdown = (
    markdown.replace("HIGH-LOW", "VOLUME PRICING")
    .replace("High-Low", "Volume Pricing")
    .replace("high-low-paper-cycle.yml", "volume-pricing-paper-cycle.yml")
    .replace("ATH/ATL", "volume-to-market-cap")
    .replace("High-Low Equal-Notional Strategy", "Volume Pricing Equal-Notional Strategy")
)
if "READY — WAITING FOR FIRST FINANCIAL PAPER EVENT" in markdown:
    markdown = markdown.replace("# ACTIVE PAPER STATUS", "# PAPER STATUS")
    markdown = markdown.replace(
        "**🟢 ACTIVE · PAPER ONLY · NO LIVE ORDERS**",
        "**BOOTSTRAPPING · PAPER ONLY · NO LIVE ORDERS**",
    )

journal = status.render_primary_trade_journal(
    state_dir,
    generated_at_ms=generated_at_ms,
    workflow_metadata=metadata,
)
journal = (
    journal.replace("HIGH-LOW", "VOLUME PRICING")
    .replace("High-Low", "Volume Pricing")
    .replace("ATH/ATL", "volume-to-market-cap")
)
coverage_path = market_data / "data" / "reports" / "mexc" / "latest_cycle.json"
coverage_note = ""
if coverage_path.is_file():
    coverage = json.loads(coverage_path.read_text(encoding="utf-8"))
    coverage_state = "READY" if coverage.get("history_coverage_pass") else "BOOTSTRAPPING"
    coverage_note = "\n".join([
        "",
        "## MEXC universe and data coverage",
        "",
        f"- Coverage state: **{coverage_state}**",
        f"- Active USDT-settled cross-margin perpetuals: {coverage.get('active_cross_usdt_perpetual_count', '—')}",
        f"- Strategy-eligible crypto/unclassified contracts: {((coverage.get('strategy_universe_summary') or {}).get('eligible_crypto_and_unclassified', '—'))}",
        f"- Excluded non-crypto categories: {((coverage.get('strategy_universe_summary') or {}).get('excluded_by_category', {}))}",
        f"- MEXC tickers received: {coverage.get('ticker_coverage', '—')}",
        f"- Missing tickers: {coverage.get('missing_ticker_count', '—')}",
        f"- History bootstrap remaining: {coverage.get('bootstrap_remaining', '—')}",
        f"- API failures: {coverage.get('api_failure_count', '—')}",
        f"- Latest completed daily candle (UTC ms): {coverage.get('latest_completed_daily_bar_ms', '—')}",
        f"- Portfolio decision: `{coverage.get('paper_decision_status', 'UNKNOWN')}`",
        f"- Market-cap provider: {((coverage.get('market_cap_source_summary') or {}).get('provider', 'coinpaprika'))} — Powered by CoinPaprika",
        f"- Fresh market-cap matches: {((coverage.get('market_cap_source_summary') or {}).get('coverage', {}).get('resolved_symbols', '—'))}/{((coverage.get('market_cap_source_summary') or {}).get('coverage', {}).get('required_symbols', '—'))}",
        "",
        "### Volume-to-market-cap ranking",
        "",
        "Numerator: MEXC rolling 24-hour USDT quote turnover. Denominator: circulating market capitalization in USD.",
        "",
        "**Highest-ranked positive 24-hour change candidates (long side):**",
    ])
    if coverage.get("cycle_exception"):
        coverage_note += f"\n- Cycle error: `{coverage.get('cycle_exception')}`"
    long_preview = coverage.get("research_long_top", [])[:10]
    if long_preview:
        coverage_note += "\n" + "\n".join(
            f"- {row.get('symbol', '—')}: ratio={row.get('volume_to_market_cap_pct', '—')}%, "
            f"MEXC 24h change={row.get('mexc_change_24h', '—')}, "
            f"market-cap source={row.get('market_cap_provider', '—')} match={row.get('market_cap_symbol_match_type', 'exact')}"
            for row in long_preview
        )
    else:
        coverage_note += "\n- No eligible positive-change candidate."
    coverage_note += "\n\n**Highest-ranked negative 24-hour change candidates (short side):**"
    short_preview = coverage.get("research_short_top", [])[:10]
    if short_preview:
        coverage_note += "\n" + "\n".join(
            f"- {row.get('symbol', '—')}: ratio={row.get('volume_to_market_cap_pct', '—')}%, "
            f"MEXC 24h change={row.get('mexc_change_24h', '—')}, "
            f"market-cap source={row.get('market_cap_provider', '—')} match={row.get('market_cap_symbol_match_type', 'exact')}"
            for row in short_preview
        )
    else:
        coverage_note += "\n- No eligible negative-change candidate."
    coverage_note += "\n\nPortfolio transitions remain blocked until the complete eligible MEXC USDT universe passes the market-data gate."
    markdown = markdown.replace("## Current performance", coverage_note + "\n\n## Current performance")

(ROOT / "PAPER_STATUS.md").write_text(markdown, encoding="utf-8")
(ROOT / "PAPER_TRADE_JOURNAL.md").write_text(journal, encoding="utf-8")
print("Published Volume Pricing status, primary trade journal and both equity curves.")
