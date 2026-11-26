#!/usr/bin/env python3
"""Run the volume-to-market-cap signal through the proven MEXC paper engine."""
from __future__ import annotations

import importlib.util
import json
import os
import re
import sys
import time
from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable
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
COINGECKO_REQUEST_INTERVAL_SECONDS = 12.5
COINGECKO_MARKET_PAGES = 8
MARKET_CAP_CACHE_VERSION = 2
_LAST_COINPAPRIKA_REQUEST = 0.0
_LAST_COINGECKO_REQUEST = 0.0
_PENDING_DECISION_SNAPSHOT: dict[str, Any] | None = None
_BOOTSTRAP_STATUS: dict[str, Any] | None = None
_STRATEGY_UNIVERSE_SUMMARY: dict[str, Any] | None = None
_MARKET_CAP_SOURCE_SUMMARY: dict[str, Any] | None = None
USER_AGENT = "volume-pricing-forward-paper/1.0"


class MarketCapDataError(RuntimeError):
    """Raised when no trustworthy unauthenticated market-cap source is available."""


def _verify_remote_with_consistency_retries(
    verify: Callable[[], Any],
    *,
    sleep: Callable[[float], None] = time.sleep,
) -> Any:
    """Retry only missing read-after-write event visibility; never bypass integrity checks."""
    delays = (1, 2, 4, 8, 12, 15)
    for attempt in range(len(delays) + 1):
        try:
            return verify()
        except Exception as exc:
            message = str(exc)
            eventually_consistent = (
                "Published event batch is not in the verified remote chain" in message
                or "Required event batch is missing from remote chain" in message
            )
            if not eventually_consistent or attempt == len(delays):
                raise
            sleep(delays[attempt])
    raise RuntimeError("Unreachable state verification retry exit")


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


def _coingecko_get(url: str) -> Any:
    """Use CoinGecko's no-key public pool at a conservative five calls/minute."""
    global _LAST_COINGECKO_REQUEST
    elapsed = time.monotonic() - _LAST_COINGECKO_REQUEST
    if elapsed < COINGECKO_REQUEST_INTERVAL_SECONDS:
        time.sleep(COINGECKO_REQUEST_INTERVAL_SECONDS - elapsed)
    _LAST_COINGECKO_REQUEST = time.monotonic()
    return _http_json(url, retries=4)


def _fetch_coingecko_market_pages() -> list[dict[str, Any]]:
    """Fetch the top 2,000 market-cap records in eight public 250-asset pages."""
    output: list[dict[str, Any]] = []
    for page in range(1, COINGECKO_MARKET_PAGES + 1):
        query = urlencode({
            "vs_currency": "usd",
            "order": "market_cap_desc",
            "per_page": 250,
            "page": page,
            "sparkline": "false",
        })
        payload = _coingecko_get(
            f"https://api.coingecko.com/api/v3/coins/markets?{query}"
        )
        if not isinstance(payload, list):
            raise MarketCapDataError(
                f"CoinGecko markets page {page} returned a malformed response"
            )
        if not payload:
            if page == 1:
                raise MarketCapDataError("CoinGecko markets endpoint returned no assets")
            break
        for row in payload:
            if not isinstance(row, dict):
                continue
            item = _record(
                row.get("symbol"),
                row.get("name"),
                row.get("market_cap"),
                row.get("id"),
                "coingecko",
                _iso_ms(row.get("last_updated")),
            )
            if item:
                output.append(item)
    if not output:
        raise MarketCapDataError("CoinGecko supplied no valid market-cap records")
    return output


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
        and row.get("is_active", True) is not False
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


def _normalize_provider_name(value: object) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())


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
    return directory / "provider_cache_v2.json", directory / "daily_attempt_v2.json"


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
    """Resolve market caps using keyless CoinPaprika plus paginated CoinGecko."""
    cache_path, attempt_path = _market_cap_paths()
    today = datetime.fromtimestamp(now_ms / 1000, UTC).date().isoformat()
    required = sorted(required_symbols)

    if cache_path.is_file():
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            records = cached.get("records", {})
            if (
                cached.get("cache_version") == MARKET_CAP_CACHE_VERSION
                and cached.get("decision_date") == today
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
                    "Market-cap providers already attempted today; refusing repeated "
                    "calls without a complete private Actions cache. "
                    f"Previous status={attempt.get('status', 'UNKNOWN')}"
                )
        except MarketCapDataError:
            raise
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            pass

    attempt = {
        "decision_date": today,
        "cache_version": MARKET_CAP_CACHE_VERSION,
        "status": "IN_PROGRESS",
        "started_at_ms": now_ms,
        "required_symbols": len(required),
        "providers": ["coinpaprika", "coingecko"],
    }
    _write_json_atomic(attempt_path, attempt)
    individual_calls = 0
    coingecko_calls = 0

    try:
        top_rows = _fetch_coinpaprika_top_tickers()
        catalogue = _fetch_coinpaprika_coin_catalogue()
        top_groups = _group_provider_rows(top_rows)
        catalogue_groups = _group_provider_rows(catalogue)
        catalogue_name_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for coin in catalogue:
            normalized_name = _normalize_provider_name(coin.get("name"))
            if normalized_name:
                catalogue_name_groups[normalized_name].append(coin)

        coingecko_error: str | None = None
        try:
            coingecko_rows = _fetch_coingecko_market_pages()
            coingecko_calls = COINGECKO_MARKET_PAGES
        except MarketCapDataError as exc:
            coingecko_rows = []
            coingecko_error = f"{type(exc).__name__}: {str(exc)[:350]}"
        coingecko_groups = _group_provider_rows(coingecko_rows)
        coingecko_name_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for coin in coingecko_rows:
            normalized_name = _normalize_provider_name(coin.get("name"))
            if normalized_name:
                coingecko_name_groups[normalized_name].append(coin)

        resolved: dict[str, dict[str, Any]] = {}
        ambiguous: list[str] = []
        stale: list[str] = []
        missing: list[str] = []
        pending: dict[str, tuple[str, str, str]] = {}

        def resolve_coingecko(
            base_symbol: str,
            matches: list[dict[str, Any]],
            match_type: str,
            source_symbol: str,
        ) -> bool:
            if len(matches) > 1:
                ambiguous.append(base_symbol)
                return True
            if len(matches) != 1:
                return False
            record = dict(matches[0])
            if not _record_is_fresh(record, now_ms):
                stale.append(base_symbol)
                return True
            record["source_symbol"] = source_symbol
            record["symbol_match_type"] = match_type
            resolved[base_symbol] = record
            return True

        for base_symbol in required:
            top_matches = top_groups.get(base_symbol, [])
            if len(top_matches) == 1 and _record_is_fresh(top_matches[0], now_ms):
                record = dict(top_matches[0])
                record["source_symbol"] = base_symbol
                record["symbol_match_type"] = "exact_coinpaprika_top_2000"
                resolved[base_symbol] = record
                continue

            # CoinGecko is a second, independent keyless market-cap catalogue.
            # Use it when CoinPaprika's bulk list omits the exact symbol.
            if resolve_coingecko(
                base_symbol,
                coingecko_groups.get(base_symbol, []),
                "exact_coingecko_top_2000",
                base_symbol,
            ):
                continue

            if len(top_matches) > 1:
                ambiguous.append(base_symbol)
                continue

            coin_matches = catalogue_groups.get(base_symbol, [])
            match_type = "exact_coinpaprika_single_ticker"
            source_symbol = base_symbol

            if len(coin_matches) > 1:
                ambiguous.append(base_symbol)
                continue

            if not coin_matches:
                alias_resolved = False
                for prefix in ("1000000", "10000", "1000"):
                    if not base_symbol.startswith(prefix):
                        continue
                    candidate_symbol = base_symbol[len(prefix):]
                    if resolve_coingecko(
                        base_symbol,
                        coingecko_groups.get(candidate_symbol, []),
                        f"mexc_{prefix}x_coingecko_denomination_alias",
                        candidate_symbol,
                    ):
                        alias_resolved = True
                        break
                    candidate_matches = catalogue_groups.get(candidate_symbol, [])
                    if len(candidate_matches) == 1:
                        coin_matches = candidate_matches
                        source_symbol = candidate_symbol
                        match_type = f"mexc_{prefix}x_coinpaprika_denomination_alias"
                        alias_resolved = True
                        break
                    if len(candidate_matches) > 1:
                        ambiguous.append(base_symbol)
                        alias_resolved = True
                        break
                if alias_resolved:
                    continue

                normalized_base = _normalize_provider_name(base_symbol)
                if resolve_coingecko(
                    base_symbol,
                    coingecko_name_groups.get(normalized_base, []),
                    "exact_normalized_name_coingecko_alias",
                    str((coingecko_name_groups.get(normalized_base) or [{}])[0].get("symbol", base_symbol)).upper(),
                ):
                    continue
                name_matches = catalogue_name_groups.get(normalized_base, [])
                if len(name_matches) > 1:
                    ambiguous.append(base_symbol)
                    continue
                if not name_matches:
                    missing.append(base_symbol)
                    continue
                coin_matches = name_matches
                source_symbol = str(coin_matches[0].get("symbol", "")).upper()
                match_type = "exact_normalized_name_coinpaprika_alias"

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

        request_errors: list[str] = []
        coinpaprika_single_lookup_plan_limited = False
        pending_items = list(pending.items())
        for index, (base_symbol, (coin_id, source_symbol, match_type)) in enumerate(pending_items):
            individual_calls += 1
            try:
                record = _fetch_coinpaprika_single_ticker(coin_id)
            except MarketCapDataError as exc:
                message = str(exc)
                if any(code in message for code in ("HTTP 402", "HTTP 403")):
                    coinpaprika_single_lookup_plan_limited = True
                    request_errors.append(f"{base_symbol}:{message[:180]}")
                    missing.extend(symbol for symbol, _ in pending_items[index:])
                    break
                if "HTTP 404" not in message:
                    raise
                request_errors.append(f"{base_symbol}:{message[:180]}")
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
        providers_used = sorted({
            str(record.get("provider", ""))
            for record in resolved.values()
            if record.get("provider")
        })
        provider_labels = {
            "coinpaprika": "CoinPaprika",
            "coingecko": "CoinGecko",
        }
        provider = "+".join(providers_used) if providers_used else "none"
        attribution = "; ".join(
            f"Powered by {provider_labels.get(name, name)}"
            for name in providers_used
        )
        coinpaprika_calls_used = 2 + individual_calls
        api_calls_used = coinpaprika_calls_used + coingecko_calls
        summary = {
            "provider": provider,
            "attribution": attribution,
            "top_ticker_rows_received": len(top_rows),
            "coin_catalogue_rows_received": len(catalogue),
            "coingecko_rows_received": len(coingecko_rows),
            "coingecko_pages_requested": coingecko_calls,
            "coingecko_request_error": coingecko_error,
            "coingecko_request_interval_seconds": COINGECKO_REQUEST_INTERVAL_SECONDS,
            "individual_ticker_lookups": individual_calls,
            "coinpaprika_single_lookup_plan_limited": coinpaprika_single_lookup_plan_limited,
            "coinpaprika_api_calls_used": coinpaprika_calls_used,
            "coinpaprika_api_calls_daily_safety_cap": 642,
            "coingecko_api_calls_used": coingecko_calls,
            "coingecko_api_calls_daily_safety_cap": COINGECKO_MARKET_PAGES,
            "api_calls_used": api_calls_used,
            "api_calls_daily_safety_cap": 650,
            "request_errors": request_errors,
            "coverage": coverage,
        }
        cache_payload = {
            "cache_version": MARKET_CAP_CACHE_VERSION,
            "decision_date": today,
            "fetched_at_ms": int(datetime.now(UTC).timestamp() * 1000),
            "required_symbols": required,
            "records": resolved,
            "summary": summary,
        }
        _write_json_atomic(cache_path, cache_payload)
        _write_json_atomic(attempt_path, {
            **attempt,
            "status": "COMPLETED",
            "completed_at_ms": int(datetime.now(UTC).timestamp() * 1000),
            "api_calls_used": api_calls_used,
            "coinpaprika_api_calls_used": coinpaprika_calls_used,
            "coingecko_api_calls_used": coingecko_calls,
            "resolved_symbols": len(resolved),
            "required_symbols": len(required),
        })
        return resolved, summary
    except Exception as exc:
        _write_json_atomic(attempt_path, {
            **attempt,
            "status": "FAILED",
            "completed_at_ms": int(datetime.now(UTC).timestamp() * 1000),
            "api_calls_used": 2 + individual_calls + coingecko_calls,
            "error": f"{type(exc).__name__}: {str(exc)[:500]}",
        })
        raise


def _universe_history_ready(
    eligible: list[dict[str, Any]],
    histories: dict[int, list[dict[str, Any]]],
    tickers: dict[int, dict[str, Any]],
    as_of_timestamp_ms: int,
) -> bool:
    """Avoid expensive provider lookups until the complete MEXC universe is ready."""
    market_data = Path(os.environ.get("MARKET_DATA_DIR", "../market-data"))
    manifest_path = market_data / "data" / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return False
    records = manifest.get("instruments", {})
    ticker_stamps = [
        int(row.get("timestamp_ms", 0))
        for row in tickers.values()
        if int(row.get("timestamp_ms", 0)) > 0
    ]
    newest_ticker_ms = max(ticker_stamps, default=0)
    if newest_ticker_ms <= 0:
        return False

    for instrument in eligible:
        iid = int(instrument["instrument_id"])
        record = records.get(str(iid), {})
        if not record or not record.get("bootstrap_complete"):
            return False
        if int(record.get("last_checked_daily_bar_ms", 0)) < as_of_timestamp_ms:
            return False
        if record.get("last_bootstrap_error"):
            return False
        ticker = tickers.get(iid)
        if ticker is None:
            return False
        ticker_stamp = int(ticker.get("timestamp_ms", 0))
        if ticker_stamp <= 0 or newest_ticker_ms - ticker_stamp > MAX_TICKER_SPREAD_MS:
            return False
        if record.get("history_status") == "AVAILABLE":
            daily_rows = histories.get(iid, [])
            if not any(
                int(row.get("timestamp_ms", 0)) == as_of_timestamp_ms
                for row in daily_rows
            ):
                return False
    return True


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
    global _PENDING_DECISION_SNAPSHOT, _STRATEGY_UNIVERSE_SUMMARY, _MARKET_CAP_SOURCE_SUMMARY
    if not nav.is_finite() or nav <= 0:
        raise ValueError("nav must be a finite positive Decimal")
    if as_of_timestamp_ms <= 0:
        raise ValueError("as_of_timestamp_ms must be positive")

    all_usdt = [
        row for row in instruments
        if bool(row.get("usdt_account_eligible"))
        and str(row.get("quote_asset", "")).upper() == "USDT"
        and str(row.get("settlement_asset", "")).upper() == "USDT"
    ]
    category_counts: dict[str, int] = defaultdict(int)
    for row in all_usdt:
        category_counts[str(row.get("category", "unknown")).lower()] += 1
    eligible = [
        row for row in all_usdt
        if str(row.get("category", "unknown")).lower() in {"crypto", "unclassified"}
        and not str(row.get("base_asset", "")).strip().upper().endswith("STOCK")
    ]
    _STRATEGY_UNIVERSE_SUMMARY = {
        "all_usdt_perpetuals": len(all_usdt),
        "eligible_crypto_and_unclassified": len(eligible),
        "excluded_stock_suffix_contracts": sum(
            str(row.get("base_asset", "")).strip().upper().endswith("STOCK")
            for row in all_usdt
        ),
        "excluded_by_category": {
            key: value for key, value in sorted(category_counts.items())
            if key not in {"crypto", "unclassified"}
        },
    }
    symbols = {
        str(row.get("base_asset", "")).strip().upper()
        for row in eligible if str(row.get("base_asset", "")).strip()
    }
    now_ms = int(datetime.now(UTC).timestamp() * 1000)
    if (
        (_BOOTSTRAP_STATUS is not None and (
            int(_BOOTSTRAP_STATUS.get("bootstrap_remaining", 1)) > 0
            or int(_BOOTSTRAP_STATUS.get("api_failure_count", 1)) > 0
            or not bool(_BOOTSTRAP_STATUS.get("daily_refresh_complete", False))
        ))
        or not _universe_history_ready(eligible, histories, tickers, as_of_timestamp_ms)
    ):
        _PENDING_DECISION_SNAPSHOT = None
        return MEXCRankings(
            research_longs=[],
            research_shorts=[],
            executable_longs=[],
            executable_shorts=[],
            instruments_by_key={},
            excluded=["BOOTSTRAP_INCOMPLETE: market-cap lookup deferred until full MEXC coverage"],
        )
    market_caps, source_report = _load_market_cap_records(symbols, now_ms)
    _MARKET_CAP_SOURCE_SUMMARY = source_report
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
            "market_cap_source_symbol": str(cap_row.get("source_symbol", base)),
            "market_cap_symbol_match_type": str(cap_row.get("symbol_match_type", "exact")),
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
                "market_cap_source_symbol": item[2]["market_cap_source_symbol"],
                "market_cap_symbol_match_type": item[2]["market_cap_symbol_match_type"],
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
            "market_cap_source_symbol": str(instrument["market_cap_source_symbol"]),
            "market_cap_symbol_match_type": str(instrument["market_cap_symbol_match_type"]),
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

    # This signal and the inverse-volatility shadow path need 30 daily returns
    # plus ATR14, not an all-time price history. Keep a 45-day rolling window.
    original_candles = engine.MEXCPublicClient.candles

    def recent_daily_candles(
        self,
        symbol,
        *,
        start_timestamp_ms,
        end_timestamp_ms,
        interval="Day1",
    ):
        if interval == "Day1":
            start_timestamp_ms = max(
                int(start_timestamp_ms),
                int(end_timestamp_ms) - 45 * DAY_MS,
            )
        return original_candles(
            self,
            symbol,
            start_timestamp_ms=start_timestamp_ms,
            end_timestamp_ms=end_timestamp_ms,
            interval=interval,
        )

    engine.MEXCPublicClient.candles = recent_daily_candles

    # Keep the CoinPaprika-only v2 paper account isolated from the initial
    # provider experiment and its immutable event chain.
    original_state_publisher = engine.GitHubStatePublisher
    from high_vs_low.github_state import GitHubStateError

    class VolumePricingStatePublisher(original_state_publisher):
        def __init__(self, repository_full_name, token, **kwargs):
            kwargs.pop("branch", None)
            super().__init__(
                repository_full_name,
                token,
                branch="state-coinpaprika-v2",
                **kwargs,
            )

        def _verify_remote_batch(
            self, repo_path, branch_path, encoded_path, content, batch_hash
        ):
            return _verify_remote_with_consistency_retries(
                lambda: super(VolumePricingStatePublisher, self)._verify_remote_batch(
                    repo_path, branch_path, encoded_path, content, batch_hash
                )
            )

    engine.GitHubStatePublisher = VolumePricingStatePublisher

    global _BOOTSTRAP_STATUS, _STRATEGY_UNIVERSE_SUMMARY, _MARKET_CAP_SOURCE_SUMMARY
    _BOOTSTRAP_STATUS = {}
    _STRATEGY_UNIVERSE_SUMMARY = None
    _MARKET_CAP_SOURCE_SUMMARY = None
    original_bootstrap = engine._bootstrap_or_increment
    original_daily_refresh_complete = engine._daily_refresh_complete

    def tracked_bootstrap(*args, **kwargs):
        result = original_bootstrap(*args, **kwargs)
        _BOOTSTRAP_STATUS["bootstrap_remaining"] = int(result[1])
        _BOOTSTRAP_STATUS["api_failure_count"] = len(result[2])
        return result

    def tracked_daily_refresh_complete(*args, **kwargs):
        result = original_daily_refresh_complete(*args, **kwargs)
        _BOOTSTRAP_STATUS["daily_refresh_complete"] = bool(result)
        return result

    engine._bootstrap_or_increment = tracked_bootstrap
    engine._daily_refresh_complete = tracked_daily_refresh_complete
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
        if _STRATEGY_UNIVERSE_SUMMARY is not None:
            failure_report["strategy_universe_summary"] = _STRATEGY_UNIVERSE_SUMMARY
        if _MARKET_CAP_SOURCE_SUMMARY is not None:
            failure_report["market_cap_source_summary"] = _MARKET_CAP_SOURCE_SUMMARY
        _write_json_atomic(report_path, failure_report)
        raise

    # Publish the full ranking only after the shared engine confirms that the
    # entire eligible universe has current daily data and fresh tickers. During
    # bootstrap, provisional rankings never become the frozen daily snapshot.
    if report_path.is_file():
        report = json.loads(report_path.read_text(encoding="utf-8"))
        if _PENDING_DECISION_SNAPSHOT is not None:
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
        if _STRATEGY_UNIVERSE_SUMMARY is not None:
            report["strategy_universe_summary"] = _STRATEGY_UNIVERSE_SUMMARY
        if _MARKET_CAP_SOURCE_SUMMARY is not None:
            report["market_cap_source_summary"] = _MARKET_CAP_SOURCE_SUMMARY
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
