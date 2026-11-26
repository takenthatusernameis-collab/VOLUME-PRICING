#!/usr/bin/env python3
"""Run the volume-to-market-cap signal through the proven MEXC paper engine."""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import time
from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
ENGINE_ROOT = ROOT.parent / "engine"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ENGINE_ROOT / "src"))

from high_vs_low.mexc_paper import Candidate, MEXCRankings

ACCOUNT_ID = "mexc-usdt-forward-volume-pricing-100usdt-v1"
STRATEGY_ID = "volume-to-market-cap-first-positive-negative-v1"
INITIAL_CAPITAL = Decimal("100")
CACHE_TTL_MS = 6 * 60 * 60 * 1000
MAX_SOURCE_AGE_MS = 24 * 60 * 60 * 1000
MAX_TICKER_SPREAD_MS = 5 * 60 * 1000
_PENDING_DECISION_SNAPSHOT: dict[str, Any] | None = None
DAY_MS = 86_400_000
USER_AGENT = "volume-pricing-forward-paper/1.0"


class MarketCapDataError(RuntimeError):
    """Raised when no trustworthy unauthenticated market-cap source is available."""


def _dec(value: object, field: str, *, positive: bool = False) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"Invalid {field}") from exc
    if not parsed.is_finite() or (positive and parsed <= 0):
        raise ValueError(f"Invalid {field}")
    return parsed


def _iso_ms(value: object) -> int | None:
    if value in (None, ""):
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return int(parsed.timestamp() * 1000)
    except (TypeError, ValueError, OverflowError):
        return None


def _http_json(url: str, *, timeout: int = 30) -> Any:
    request = Request(
        url,
        headers={"Accept": "application/json", "User-Agent": USER_AGENT},
        method="GET",
    )
    last_error: Exception | None = None
    for attempt in range(5):
        try:
            with urlopen(request, timeout=timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
                return payload
        except HTTPError as exc:
            last_error = exc
            if exc.code == 429 or 500 <= exc.code < 600:
                retry_after = exc.headers.get("Retry-After")
                try:
                    delay = max(float(retry_after or 0), min(2 ** attempt, 16))
                except ValueError:
                    delay = min(2 ** attempt, 16)
                time.sleep(delay)
                continue
            raise MarketCapDataError(f"HTTP {exc.code} from {url.split('?')[0]}") from exc
        except (URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            last_error = exc
            time.sleep(min(2 ** attempt, 16))
    raise MarketCapDataError(
        f"Request failed for {url.split('?')[0]}: {type(last_error).__name__}: {last_error}"
    )


def _record(
    symbol: object,
    name: object,
    market_cap: object,
    source_id: object,
    provider: str,
    updated_ms: int | None,
) -> dict[str, Any] | None:
    normalized = str(symbol or "").strip().upper()
    if not normalized:
        return None
    try:
        cap = _dec(market_cap, "market cap", positive=True)
    except ValueError:
        return None
    if updated_ms is None or updated_ms <= 0:
        return None
    return {
        "symbol": normalized,
        "name": str(name or ""),
        "market_cap_usd": str(cap),
        "source_id": str(source_id or ""),
        "provider": provider,
        "source_updated_ms": int(updated_ms),
    }


def _fetch_coinmarketcap() -> list[dict[str, Any]]:
    base = "https://pro-api.coinmarketcap.com/public-api/v3/cryptocurrency/listings/latest"
    query = urlencode({
        "start": 1,
        "limit": 5000,
        "convert": "USD",
        "sort": "market_cap",
        "sort_dir": "desc",
    })
    payload = _http_json(f"{base}?{query}")
    if not isinstance(payload, dict):
        raise MarketCapDataError("CoinMarketCap returned a non-object response")
    status = payload.get("status") or {}
    if status.get("error_code") not in (None, 0):
        raise MarketCapDataError(
            f"CoinMarketCap error {status.get('error_code')}: {status.get('error_message')}"
        )
    global_stamp = _iso_ms(status.get("timestamp"))
    output: list[dict[str, Any]] = []
    rows = payload.get("data")
    if not isinstance(rows, list) or not rows:
        raise MarketCapDataError("CoinMarketCap listings response contained no assets")
    for row in rows:
        if not isinstance(row, dict):
            continue
        quote = (row.get("quote") or {}).get("USD") or {}
        stamp = _iso_ms(quote.get("last_updated")) or global_stamp
        item = _record(
            row.get("symbol"), row.get("name"), quote.get("market_cap"),
            row.get("id"), "coinmarketcap", stamp,
        )
        if item:
            output.append(item)
    if not output:
        raise MarketCapDataError("CoinMarketCap returned no positive market caps")
    return output


def _fetch_coinpaprika() -> list[dict[str, Any]]:
    payload = _http_json("https://api.coinpaprika.com/v1/tickers")
    if not isinstance(payload, list) or not payload:
        raise MarketCapDataError("CoinPaprika tickers response was empty or malformed")
    output: list[dict[str, Any]] = []
    for row in payload:
        if not isinstance(row, dict):
            continue
        quote = (row.get("quotes") or {}).get("USD") or {}
        stamp = _iso_ms(row.get("last_updated"))
        item = _record(
            row.get("symbol"), row.get("name"), quote.get("market_cap"),
            row.get("id"), "coinpaprika", stamp,
        )
        if item:
            output.append(item)
    if not output:
        raise MarketCapDataError("CoinPaprika returned no positive market caps")
    return output


def _fetch_coinlore() -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    start = 0
    limit = 1000
    total: int | None = None
    for page in range(200):
        query = urlencode({"start": start, "limit": limit})
        payload = _http_json(f"https://api.coinlore.net/api/tickers/?{query}")
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
            raise MarketCapDataError("CoinLore tickers response was malformed")
        info = payload.get("info") or {}
        try:
            total = int(info.get("coins_num")) if info.get("coins_num") is not None else total
            stamp = int(info.get("time", 0)) * 1000
        except (TypeError, ValueError):
            stamp = 0
        rows = payload["data"]
        for row in rows:
            if not isinstance(row, dict):
                continue
            item = _record(
                row.get("symbol"), row.get("name"), row.get("market_cap_usd"),
                row.get("id"), "coinlore", stamp or None,
            )
            if item:
                output.append(item)
        if not rows:
            break
        start += len(rows)
        if total is not None and start >= total:
            break
        if len(rows) < limit and total is None:
            break
        if page < 199:
            time.sleep(1.05)
    if not output:
        raise MarketCapDataError("CoinLore returned no positive market caps")
    return output


def _group_provider_rows(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        symbol = str(row.get("symbol", "")).upper()
        if symbol:
            grouped[symbol].append(row)
    return dict(grouped)


def _cache_path() -> Path:
    market_data = Path(os.environ.get("MARKET_DATA_DIR", "../market-data"))
    return market_data / "data" / "market_cap" / "provider_cache.json"


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _load_market_cap_cache(
    required_symbols: set[str],
    now_ms: int,
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    path = _cache_path()
    cache: dict[str, Any] = {}
    if path.is_file():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if (
                isinstance(loaded, dict)
                and now_ms - int(loaded.get("fetched_at_ms", 0)) <= CACHE_TTL_MS
                and now_ms >= int(loaded.get("fetched_at_ms", 0))
            ):
                cache = loaded
        except (OSError, ValueError, json.JSONDecodeError):
            cache = {}

    providers = cache.setdefault("providers", {})
    attempted = set(cache.setdefault("attempted", []))
    errors = cache.setdefault("errors", {})
    provider_order = ("coinmarketcap", "coinpaprika", "coinlore")

    def grouped() -> dict[str, dict[str, list[dict[str, Any]]]]:
        return {
            name: _group_provider_rows(rows)
            for name, rows in providers.items()
            if isinstance(rows, list)
        }

    def resolved_symbols() -> set[str]:
        groups = grouped()
        resolved: set[str] = set()
        for symbol in required_symbols:
            for name in provider_order:
                matches = groups.get(name, {}).get(symbol, [])
                if len(matches) == 1:
                    resolved.add(symbol)
                    break
                if len(matches) > 1:
                    # An ambiguous symbol is deliberately not guessed.
                    break
        return resolved

    fetchers = {
        "coinmarketcap": _fetch_coinmarketcap,
        "coinpaprika": _fetch_coinpaprika,
        "coinlore": _fetch_coinlore,
    }
    for provider in provider_order:
        missing = required_symbols - resolved_symbols()
        if not missing:
            break
        if provider in attempted:
            continue
        attempted.add(provider)
        try:
            providers[provider] = fetchers[provider]()
            errors.pop(provider, None)
        except Exception as exc:
            errors[provider] = f"{type(exc).__name__}: {str(exc)[:300]}"
        cache["attempted"] = sorted(attempted)
        cache["fetched_at_ms"] = now_ms
        cache["providers"] = providers
        cache["errors"] = errors
        _write_json_atomic(path, cache)

    groups = grouped()
    resolved: dict[str, dict[str, Any]] = {}
    ambiguous: list[str] = []
    for symbol in sorted(required_symbols):
        selected: dict[str, Any] | None = None
        for provider in provider_order:
            matches = groups.get(provider, {}).get(symbol, [])
            if len(matches) > 1:
                ambiguous.append(symbol)
                selected = None
                break
            if len(matches) == 1:
                selected = matches[0]
                break
        if selected is None:
            continue
        stamp = int(selected.get("source_updated_ms", 0))
        if stamp <= 0 or stamp > now_ms + 300_000 or now_ms - stamp > MAX_SOURCE_AGE_MS:
            continue
        resolved[symbol] = selected

    if not any(isinstance(rows, list) and rows for rows in providers.values()):
        details = "; ".join(f"{k}: {v}" for k, v in errors.items())
        raise MarketCapDataError(
            "All unauthenticated market-cap providers failed or returned no data. " + details
        )

    cache["attempted"] = sorted(attempted)
    cache["fetched_at_ms"] = int(cache.get("fetched_at_ms", now_ms))
    cache["providers"] = providers
    cache["errors"] = errors
    cache["coverage"] = {
        "required_symbols": len(required_symbols),
        "resolved_symbols": len(resolved),
        "unresolved_symbols": sorted(required_symbols - set(resolved)),
        "ambiguous_symbols": sorted(set(ambiguous)),
    }
    _write_json_atomic(path, cache)
    return resolved, {
        "provider_rows": {name: len(rows) for name, rows in providers.items()},
        "attempted": sorted(attempted),
        "errors": dict(errors),
        "coverage": cache["coverage"],
    }


def rank_volume_pricing_universe(
    instruments: list[dict[str, Any]],
    histories: dict[int, list[dict[str, Any]]],
    tickers: dict[int, dict[str, Any]],
    nav: Decimal,
    *,
    as_of_timestamp_ms: int,
    **_: Any,
) -> MEXCRankings:
    """Rank MEXC USDT perps by 24h turnover / circulating USD market cap."""
    if not nav.is_finite() or nav <= 0:
        raise ValueError("nav must be a finite positive Decimal")
    if as_of_timestamp_ms <= 0:
        raise ValueError("as_of_timestamp_ms must be positive")

    eligible = [
        row for row in instruments
        if bool(row.get("usdt_account_eligible"))
        and str(row.get("quote_asset", "")).upper() == "USDT"
        and str(row.get("settlement_asset", "")).upper() == "USDT"
    ]
    symbols = {
        str(row.get("base_asset", "")).strip().upper()
        for row in eligible if str(row.get("base_asset", "")).strip()
    }
    now_ms = int(datetime.now(UTC).timestamp() * 1000)
    market_caps, source_report = _load_market_cap_cache(symbols, now_ms)
    coverage = source_report["coverage"]
    coverage_fraction = (
        Decimal(coverage["resolved_symbols"]) / Decimal(coverage["required_symbols"])
        if coverage["required_symbols"] else Decimal("0")
    )
    if coverage_fraction < Decimal("0.80"):
        raise MarketCapDataError(
            "Fresh, unambiguous market-cap coverage is below the 80% safety gate: "
            f"{coverage['resolved_symbols']}/{coverage['required_symbols']} symbols"
        )

    ticker_stamps = [
        int(ticker.get("timestamp_ms", 0))
        for ticker in tickers.values()
        if int(ticker.get("timestamp_ms", 0)) > 0
    ]
    newest_ticker_ms = max(ticker_stamps, default=0)
    if newest_ticker_ms <= 0:
        raise MarketCapDataError("MEXC supplied no timestamped all-market tickers")

    ranked: list[tuple[Decimal, str, dict[str, Any], Decimal, Decimal]] = []
    excluded: list[str] = []
    for instrument in eligible:
        iid = int(instrument["instrument_id"])
        symbol = str(instrument.get("symbol", iid))
        base = str(instrument.get("base_asset", "")).strip().upper()
        daily_rows = histories.get(iid, [])
        if not any(int(row.get("timestamp_ms", 0)) == as_of_timestamp_ms for row in daily_rows):
            excluded.append(f"{symbol}:MISSING_COMPLETED_DAILY_CANDLE")
            continue
        ticker = tickers.get(iid)
        if ticker is None:
            excluded.append(f"{symbol}:MISSING_MEXC_TICKER")
            continue
        ticker_stamp = int(ticker.get("timestamp_ms", 0))
        if ticker_stamp <= 0 or newest_ticker_ms - ticker_stamp > MAX_TICKER_SPREAD_MS:
            excluded.append(f"{symbol}:STALE_MEXC_TICKER")
            continue
        cap_row = market_caps.get(base)
        if cap_row is None:
            excluded.append(f"{symbol}:MISSING_OR_AMBIGUOUS_MARKET_CAP:{base}")
            continue
        try:
            turnover = _dec(ticker.get("turnover_24h_quote"), "MEXC 24h USDT turnover", positive=True)
            change = _dec(ticker.get("change_24h"), "MEXC 24h price change")
            market_cap = _dec(cap_row.get("market_cap_usd"), "circulating market cap", positive=True)
            last_price = _dec(ticker.get("last_price"), "MEXC last price", positive=True)
        except ValueError as exc:
            excluded.append(f"{symbol}:INVALID_MARKET_INPUT:{str(exc)}")
            continue
        ratio = turnover / market_cap
        if not ratio.is_finite() or ratio <= 0:
            excluded.append(f"{symbol}:INVALID_VOLUME_TO_MARKET_CAP_RATIO")
            continue
        enriched = dict(instrument)
        enriched.update({
            "market_cap_usd": str(market_cap),
            "market_cap_provider": str(cap_row.get("provider", "")),
            "market_cap_source_id": str(cap_row.get("source_id", "")),
            "market_cap_source_name": str(cap_row.get("name", "")),
            "market_cap_source_updated_ms": int(cap_row.get("source_updated_ms", 0)),
            "mexc_turnover_24h_usdt": str(turnover),
            "mexc_change_24h": str(change),
            "volume_to_market_cap_ratio": str(ratio),
            "volume_to_market_cap_pct": str(ratio * Decimal("100")),
        })
        ranked.append((ratio, f"mexc:{iid}", enriched, change, last_price))

    ranked.sort(key=lambda item: (-item[0], str(item[2].get("symbol", "")), int(item[2]["instrument_id"])))
    instruments_by_key: dict[str, dict[str, Any]] = {}
    all_candidates: list[tuple[Candidate, Decimal]] = []
    for ratio, key, instrument, change, last_price in ranked:
        instruments_by_key[key] = instrument
        if change > 0:
            direction = "long"
        elif change < 0:
            direction = "short"
        else:
            continue
        all_candidates.append((
            Candidate(
                symbol=key,
                distance_pct=float(ratio),
                extreme_price=None,
                direction=direction,
                close_price=float(last_price),
                decision_timestamp_ms=as_of_timestamp_ms,
            ),
            change,
        ))

    longs = [candidate for candidate, change in all_candidates if change > 0]
    shorts = [candidate for candidate, change in all_candidates if change < 0]
    # Preserve the complete directional research rankings, but execute only the
    # first asset on each side. The engine must not silently substitute rank #2.
    executable_longs = longs[:1]
    executable_shorts = shorts[:1]

    decision_snapshot = {
        "strategy_id": STRATEGY_ID,
        "decision_daily_bar_timestamp_ms": int(as_of_timestamp_ms),
        "captured_at_ms": now_ms,
        "ranking_metric": "MEXC_24h_USDT_turnover / circulating_market_cap_USD",
        "price_change_source": "MEXC rolling 24h riseFallRate",
        "market_cap_sources": source_report,
        "ranked_assets": [
            {
                "rank": index + 1,
                "symbol": str(item[2]["symbol"]),
                "base_asset": str(item[2]["base_asset"]),
                "direction": "long" if item[3] > 0 else ("short" if item[3] < 0 else "flat"),
                "mexc_change_24h": str(item[3]),
                "mexc_turnover_24h_usdt": item[2]["mexc_turnover_24h_usdt"],
                "market_cap_usd": item[2]["market_cap_usd"],
                "market_cap_provider": item[2]["market_cap_provider"],
                "market_cap_source_id": item[2]["market_cap_source_id"],
                "market_cap_source_updated_ms": item[2]["market_cap_source_updated_ms"],
                "volume_to_market_cap_ratio": str(item[0]),
                "volume_to_market_cap_pct": item[2]["volume_to_market_cap_pct"],
            }
            for index, item in enumerate(ranked)
        ],
        "selected_long": (
            None if not executable_longs else executable_longs[0].symbol
        ),
        "selected_short": (
            None if not executable_shorts else executable_shorts[0].symbol
        ),
        "excluded": excluded,
    }
    global _PENDING_DECISION_SNAPSHOT
    _PENDING_DECISION_SNAPSHOT = decision_snapshot

    print(
        "[volume-pricing] "
        f"eligible={len(eligible)} ranked={len(ranked)} "
        f"long_candidates={len(longs)} short_candidates={len(shorts)} "
        f"market_cap_coverage={source_report['coverage']['resolved_symbols']}/"
        f"{source_report['coverage']['required_symbols']}",
        flush=True,
    )
    return MEXCRankings(
        research_longs=longs,
        research_shorts=shorts,
        executable_longs=executable_longs,
        executable_shorts=executable_shorts,
        instruments_by_key=instruments_by_key,
        excluded=excluded,
    )


def _ranking_report_rows(
    candidates: list[Candidate],
    instruments_by_key: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for candidate in candidates:
        instrument = instruments_by_key.get(candidate.symbol)
        if instrument is None:
            continue
        rows.append({
            "symbol": str(instrument["symbol"]),
            "instrument_id": int(instrument["instrument_id"]),
            "base_asset": str(instrument.get("base_asset", "")),
            "direction": candidate.direction,
            "volume_to_market_cap_ratio": str(instrument["volume_to_market_cap_ratio"]),
            "volume_to_market_cap_pct": str(instrument["volume_to_market_cap_pct"]),
            "mexc_turnover_24h_usdt": str(instrument["mexc_turnover_24h_usdt"]),
            "market_cap_usd": str(instrument["market_cap_usd"]),
            "market_cap_provider": str(instrument["market_cap_provider"]),
            "market_cap_source_updated_ms": int(instrument["market_cap_source_updated_ms"]),
            "mexc_change_24h": str(instrument["mexc_change_24h"]),
            "completed_daily_close": candidate.close_price,
            "decision_bar_timestamp_ms": candidate.decision_timestamp_ms,
        })
    return rows


def main() -> int:
    engine_script = ENGINE_ROOT / "scripts" / "high_low_paper_cycle.py"
    if not engine_script.is_file():
        raise RuntimeError("MEXC paper engine checkout is missing at ../engine")
    spec = importlib.util.spec_from_file_location("volume_pricing_mexc_engine_cycle", engine_script)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load the MEXC paper-cycle engine")
    engine = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = engine
    spec.loader.exec_module(engine)

    engine.ACCOUNT_ID = ACCOUNT_ID
    engine.STRATEGY_ID = STRATEGY_ID
    engine.INITIAL_CAPITAL = INITIAL_CAPITAL
    engine.rank_mexc_universe = rank_volume_pricing_universe
    engine._ranking_report_rows = _ranking_report_rows

    # The strategy is explicitly a USDT-settled perpetual cross-section. Keep
    # the shared engine's public discovery and execution checks, but avoid
    # collecting non-USDT histories that cannot enter this account.
    original_instruments = engine.MEXCPublicClient.instruments

    def usdt_instruments(self, *, usdt_only: bool = False):
        return original_instruments(self, usdt_only=True)

    engine.MEXCPublicClient.instruments = usdt_instruments
    result = int(engine._run())

    # Publish the full ranking only after the shared engine confirms that the
    # entire eligible universe has current daily data and fresh tickers. During
    # bootstrap, provisional rankings never become the frozen daily snapshot.
    market_data = Path(os.environ.get("MARKET_DATA_DIR", "../market-data"))
    report_path = market_data / "data" / "reports" / "mexc" / "latest_cycle.json"
    if _PENDING_DECISION_SNAPSHOT is not None and report_path.is_file():
        report = json.loads(report_path.read_text(encoding="utf-8"))
        report["market_cap_source_summary"] = _PENDING_DECISION_SNAPSHOT["market_cap_sources"]
        if (
            report.get("history_coverage_pass") is True
            and int(report.get("latest_completed_daily_bar_ms", 0))
            == int(_PENDING_DECISION_SNAPSHOT["decision_daily_bar_timestamp_ms"])
        ):
            decision_dir = market_data / "data" / "market_cap" / "decisions"
            decision_path = decision_dir / (
                f"daily_bar_{_PENDING_DECISION_SNAPSHOT['decision_daily_bar_timestamp_ms']}.json"
            )
            if not decision_path.exists():
                _write_json_atomic(decision_path, _PENDING_DECISION_SNAPSHOT)
            report["market_cap_decision_snapshot_path"] = str(
                decision_path.relative_to(market_data)
            )
        report_path.write_text(
            json.dumps(report, indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8",
        )

    # A clean bounded bootstrap batch is normal progress; portfolio changes
    # remain blocked until the full-universe coverage gate passes.
    if result != 0 and report_path.is_file():
        report = json.loads(report_path.read_text(encoding="utf-8"))
        expected_bootstrap = (
            report.get("paper_decision_status") == "BLOCKED_INCOMPLETE_MARKET_DATA"
            and int(report.get("bootstrap_remaining", 0)) > 0
            and int(report.get("api_failure_count", 0)) == 0
            and int(report.get("missing_ticker_count", 0)) == 0
            and int(report.get("missing_latest_bar_count", 0)) == 0
        )
        if expected_bootstrap:
            print("[volume-pricing-bootstrap] History is still being collected; portfolio changes remain blocked.")
            return 0
    return result


if __name__ == "__main__":
    raise SystemExit(main())
