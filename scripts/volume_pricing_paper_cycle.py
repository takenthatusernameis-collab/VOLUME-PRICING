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

ACCOUNT_ID = "mexc-usdt-forward-volume-pricing-coinpaprika-100usdt-v2"
STRATEGY_ID = "volume-to-market-cap-first-positive-negative-coinpaprika-v2"
INITIAL_CAPITAL = Decimal("100")
MAX_SOURCE_AGE_MS = 6 * 60 * 60 * 1000
MAX_TICKER_SPREAD_MS = 5 * 60 * 1000
DAY_MS = 86_400_000
COINPAPRIKA_MAX_SINGLE_LOOKUPS = 640
COINPAPRIKA_REQUEST_INTERVAL_SECONDS = 0.13
_LAST_COINPAPRIKA_REQUEST = 0.0
_PENDING_DECISION_SNAPSHOT: dict[str, Any] | None = None
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


def _http_json(url: str, *, timeout: int = 30, retries: int = 4) -> Any:
    request = Request(
        url,
        headers={"Accept": "application/json", "User-Agent": USER_AGENT},
        method="GET",
    )
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            with urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            last_error = exc
            if (exc.code == 429 or 500 <= exc.code < 600) and attempt < retries:
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
            if attempt < retries:
                time.sleep(min(2 ** attempt, 16))
    raise MarketCapDataError(
        f"Request failed for {url.split('?')[0]}: {type(last_error).__name__}: {last_error}"
    )


def _coinpaprika_get(url: str, *, retries: int = 4) -> Any:
    global _LAST_COINPAPRIKA_REQUEST
    elapsed = time.monotonic() - _LAST_COINPAPRIKA_REQUEST
    if elapsed < COINPAPRIKA_REQUEST_INTERVAL_SECONDS:
        time.sleep(COINPAPRIKA_REQUEST_INTERVAL_SECONDS - elapsed)
    _LAST_COINPAPRIKA_REQUEST = time.monotonic()
    return _http_json(url, retries=retries)


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


def _fetch_coinpaprika_top_tickers() -> list[dict[str, Any]]:
    payload = _coinpaprika_get("https://api.coinpaprika.com/v1/tickers")
    if not isinstance(payload, list) or not payload:
        raise MarketCapDataError("CoinPaprika top-tickers response was empty or malformed")
    output: list[dict[str, Any]] = []
    for row in payload:
        if not isinstance(row, dict):
            continue
        quote = (row.get("quotes") or {}).get("USD") or {}
        item = _record(
            row.get("symbol"), row.get("name"), quote.get("market_cap"),
            row.get("id"), "coinpaprika", _iso_ms(row.get("last_updated")),
        )
        if item:
            output.append(item)
    if not output:
        raise MarketCapDataError("CoinPaprika returned no positive top-list market caps")
    return output


def _fetch_coinpaprika_coin_catalogue() -> list[dict[str, Any]]:
    payload = _coinpaprika_get("https://api.coinpaprika.com/v1/coins")
    if not isinstance(payload, list) or not payload:
        raise MarketCapDataError("CoinPaprika coin catalogue was empty or malformed")
    return [
        {
            "id": str(row.get("id", "")),
            "symbol": str(row.get("symbol", "")).strip().upper(),
            "name": str(row.get("name", "")),
        }
        for row in payload
        if isinstance(row, dict)
        and row.get("id")
        and str(row.get("symbol", "")).strip()
    ]


def _fetch_coinpaprika_single_ticker(coin_id: str) -> dict[str, Any] | None:
    payload = _coinpaprika_get(
        f"https://api.coinpaprika.com/v1/tickers/{coin_id}",
        retries=0,
    )
    if not isinstance(payload, dict):
        return None
    quote = (payload.get("quotes") or {}).get("USD") or {}
    return _record(
        payload.get("symbol"), payload.get("name"), quote.get("market_cap"),
        payload.get("id"), "coinpaprika", _iso_ms(payload.get("last_updated")),
    )


def _group_provider_rows(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        symbol = str(row.get("symbol", "")).upper()
        if symbol:
            grouped[symbol].append(row)
    return dict(grouped)


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _market_cap_paths() -> tuple[Path, Path]:
    root = Path(os.environ.get("MARKET_DATA_DIR", "../market-data"))
    directory = root / "data" / "market_cap"
    return directory / "provider_cache.json", directory / "daily_attempt.json"


def _record_is_fresh(record: dict[str, Any], now_ms: int) -> bool:
    stamp = int(record.get("source_updated_ms", 0))
    return (
        stamp > 0
        and stamp <= now_ms + 300_000
        and now_ms - stamp <= MAX_SOURCE_AGE_MS
    )


def _load_market_cap_records(
    required_symbols: set[str],
    now_ms: int,
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """Resolve the full MEXC symbol set with CoinPaprika's keyless single-coin endpoint."""
    cache_path, attempt_path = _market_cap_paths()
    today = datetime.fromtimestamp(now_ms / 1000, UTC).date().isoformat()
    required = sorted(required_symbols)

    if cache_path.is_file():
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            records = cached.get("records", {})
            if (
                cached.get("decision_date") == today
                and cached.get("required_symbols") == required
                and isinstance(records, dict)
                and now_ms - int(cached.get("fetched_at_ms", 0)) <= MAX_SOURCE_AGE_MS
                and all(_record_is_fresh(row, now_ms) for row in records.values())
            ):
                return records, cached["summary"]
        except (OSError, ValueError, TypeError, json.JSONDecodeError, KeyError):
            pass

    if attempt_path.is_file():
        try:
            attempt = json.loads(attempt_path.read_text(encoding="utf-8"))
            if attempt.get("decision_date") == today:
                raise MarketCapDataError(
                    "CoinPaprika lookup already attempted today; refusing repeated calls "
                    "without a complete private Actions cache. "
                    f"Previous status={attempt.get('status', 'UNKNOWN')}"
                )
        except MarketCapDataError:
            raise
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            pass

    attempt = {
        "decision_date": today,
        "status": "IN_PROGRESS",
        "started_at_ms": now_ms,
        "required_symbols": len(required),
        "provider": "coinpaprika",
    }
    _write_json_atomic(attempt_path, attempt)

    try:
        top_rows = _fetch_coinpaprika_top_tickers()
        catalogue = _fetch_coinpaprika_coin_catalogue()
        top_groups = _group_provider_rows(top_rows)
        catalogue_groups = _group_provider_rows(catalogue)

        resolved: dict[str, dict[str, Any]] = {}
        ambiguous: list[str] = []
        stale: list[str] = []
        missing: list[str] = []
        pending: dict[str, tuple[str, str, str]] = {}

        for base_symbol in required:
            top_matches = top_groups.get(base_symbol, [])
            if len(top_matches) > 1:
                ambiguous.append(base_symbol)
                continue
            if len(top_matches) == 1 and _record_is_fresh(top_matches[0], now_ms):
                record = dict(top_matches[0])
                record["source_symbol"] = base_symbol
                record["symbol_match_type"] = "exact_top_2000"
                resolved[base_symbol] = record
                continue

            coin_matches = catalogue_groups.get(base_symbol, [])
            match_type = "exact"
            source_symbol = base_symbol
            if len(coin_matches) > 1:
                ambiguous.append(base_symbol)
                continue
            if not coin_matches:
                # MEXC uses denomination-prefixed contracts for some assets.
                # Prefer exact symbols; only strip a known multiplier prefix
                # when the underlying CoinPaprika symbol is unique.
                alias_matches: list[dict[str, Any]] = []
                for prefix in ("1000000", "10000", "1000"):
                    if base_symbol.startswith(prefix):
                        candidate_symbol = base_symbol[len(prefix):]
                        candidate_matches = catalogue_groups.get(candidate_symbol, [])
                        if len(candidate_matches) == 1:
                            alias_matches = candidate_matches
                            source_symbol = candidate_symbol
                            match_type = f"mexc_{prefix}x_denomination_alias"
                            break
                        if len(candidate_matches) > 1:
                            break
                if len(alias_matches) > 1:
                    ambiguous.append(base_symbol)
                    continue
                if not alias_matches:
                    missing.append(base_symbol)
                    continue
                coin_matches = alias_matches

            coin_id = str(coin_matches[0].get("id", ""))
            if not coin_id:
                missing.append(base_symbol)
                continue
            pending[base_symbol] = (coin_id, source_symbol, match_type)

        if len(pending) > COINPAPRIKA_MAX_SINGLE_LOOKUPS:
            raise MarketCapDataError(
                "CoinPaprika free-tier monthly-call safety cap exceeded: "
                f"{len(pending)} individual ticker lookups requested; "
                f"maximum is {COINPAPRIKA_MAX_SINGLE_LOOKUPS} per daily decision"
            )

        individual_calls = 0
        request_errors: list[str] = []
        for base_symbol, (coin_id, source_symbol, match_type) in pending.items():
            individual_calls += 1
            try:
                record = _fetch_coinpaprika_single_ticker(coin_id)
            except MarketCapDataError as exc:
                if "HTTP 429" in str(exc):
                    raise
                request_errors.append(f"{base_symbol}:{str(exc)[:180]}")
                missing.append(base_symbol)
                continue
            if record is None or record.get("symbol") != source_symbol:
                missing.append(base_symbol)
                continue
            if not _record_is_fresh(record, now_ms):
                stale.append(base_symbol)
                continue
            record["source_symbol"] = source_symbol
            record["symbol_match_type"] = match_type
            resolved[base_symbol] = record

        coverage = {
            "required_symbols": len(required),
            "resolved_symbols": len(resolved),
            "missing_symbols": sorted(set(missing)),
            "ambiguous_symbols": sorted(set(ambiguous)),
            "stale_symbols": sorted(set(stale)),
        }
        calls_used = 2 + individual_calls
        summary = {
            "provider": "coinpaprika",
            "attribution": "Powered by CoinPaprika",
            "top_ticker_rows_received": len(top_rows),
            "coin_catalogue_rows_received": len(catalogue),
            "individual_ticker_lookups": individual_calls,
            "api_calls_used": calls_used,
            "api_calls_daily_safety_cap": 642,
            "request_errors": request_errors,
            "coverage": coverage,
        }
        cache_payload = {
            "decision_date": today,
            "fetched_at_ms": now_ms,
            "required_symbols": required,
            "records": resolved,
            "summary": summary,
        }
        _write_json_atomic(cache_path, cache_payload)
        _write_json_atomic(attempt_path, {
            **attempt,
            "status": "COMPLETED",
            "completed_at_ms": int(datetime.now(UTC).timestamp() * 1000),
            "api_calls_used": calls_used,
            "resolved_symbols": len(resolved),
            "required_symbols": len(required),
        })
        return resolved, summary
    except Exception as exc:
        _write_json_atomic(attempt_path, {
            **attempt,
            "status": "FAILED",
            "completed_at_ms": int(datetime.now(UTC).timestamp() * 1000),
            "error": f"{type(exc).__name__}: {str(exc)[:500]}",
        })
        raise


def _group_provider_rows(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        symbol = str(row.get("symbol", "")).upper()
        if symbol:
            grouped[symbol].append(row)
    return dict(grouped)


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _load_market_cap_records(
    required_symbols: set[str],
    now_ms: int,
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """Fetch one fresh keyless CoinPaprika snapshot; never persist its raw catalogue."""
    rows = _fetch_coinpaprika()
    grouped = _group_provider_rows(rows)
    resolved: dict[str, dict[str, Any]] = {}
    ambiguous: list[str] = []
    stale: list[str] = []
    missing: list[str] = []
    for symbol in sorted(required_symbols):
        matches = grouped.get(symbol, [])
        if len(matches) > 1:
            ambiguous.append(symbol)
            continue
        if not matches:
            missing.append(symbol)
            continue
        record = matches[0]
        stamp = int(record.get("source_updated_ms", 0))
        if (
            stamp <= 0
            or stamp > now_ms + 300_000
            or now_ms - stamp > MAX_SOURCE_AGE_MS
        ):
            stale.append(symbol)
            continue
        resolved[symbol] = record

    coverage = {
        "required_symbols": len(required_symbols),
        "resolved_symbols": len(resolved),
        "missing_symbols": missing,
        "ambiguous_symbols": ambiguous,
        "stale_symbols": stale,
    }
    if not resolved:
        raise MarketCapDataError(
            "CoinPaprika returned no fresh, unambiguous market-cap matches"
        )
    # Keep only summary metadata in the public report. The full provider
    # catalogue remains in memory and is never committed or redistributed.
    return resolved, {
        "provider": "coinpaprika",
        "provider_rows_received": len(rows),
        "attribution": "Powered by CoinPaprika",
        "coverage": coverage,
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
    market_caps, source_report = _load_market_cap_records(symbols, now_ms)
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
            "market_cap_provider": str(cap_row.get("provider", "")),
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
                "market_cap_provider": item[2]["market_cap_provider"],
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

    # Keep the CoinPaprika-only v2 paper account isolated from the initial
    # provider experiment and its immutable event chain.
    original_state_publisher = engine.GitHubStatePublisher

    def volume_pricing_state_publisher(repository_full_name, token, **kwargs):
        kwargs.pop("branch", None)
        return original_state_publisher(
            repository_full_name,
            token,
            branch="state-coinpaprika-v2",
            **kwargs,
        )

    engine.GitHubStatePublisher = volume_pricing_state_publisher
    market_data = Path(os.environ.get("MARKET_DATA_DIR", "../market-data"))
    report_path = market_data / "data" / "reports" / "mexc" / "latest_cycle.json"
    try:
        result = int(engine._run())
    except Exception as exc:
        failure_report = {
            "mode": "VOLUME_PRICING_CYCLE_EXCEPTION",
            "paper_decision_status": "FAILED",
            "generated_at_ms": int(datetime.now(UTC).timestamp() * 1000),
            "history_coverage_pass": False,
            "cycle_exception": f"{type(exc).__name__}: {str(exc)[:1000]}",
        }
        _write_json_atomic(report_path, failure_report)
        raise

    # Publish the full ranking only after the shared engine confirms that the
    # entire eligible universe has current daily data and fresh tickers. During
    # bootstrap, provisional rankings never become the frozen daily snapshot.
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
