from decimal import Decimal
import json

import scripts.volume_pricing_paper_cycle as strategy


def instrument(iid: int, symbol: str, base: str) -> dict:
    return {
        "instrument_id": iid,
        "symbol": symbol,
        "base_asset": base,
        "quote_asset": "USDT",
        "settlement_asset": "USDT",
        "usdt_account_eligible": True,
        "category": "crypto",
    }


def ticker(turnover: str, change: str, stamp: int = 1_800_000_000_000) -> dict:
    return {
        "turnover_24h_quote": turnover,
        "change_24h": change,
        "timestamp_ms": stamp,
        "last_price": "1.25",
    }


def caps(**values: str) -> dict[str, dict]:
    return {
        symbol: {
            "symbol": symbol,
            "market_cap_usd": market_cap,
            "provider": "fixture",
            "source_id": symbol,
            "name": symbol,
            "source_updated_ms": 1_800_000_000_000,
        }
        for symbol, market_cap in values.items()
    }


def test_ranking_uses_turnover_to_market_cap_then_direction(monkeypatch):
    rows = [
        instrument(1, "AAA_USDT", "AAA"),
        instrument(2, "BBB_USDT", "BBB"),
        instrument(3, "CCC_USDT", "CCC"),
        instrument(4, "DDD_USDT", "DDD"),
    ]
    tickers = {
        1: ticker("10", "0.02"),
        2: ticker("20", "-0.01"),
        3: ticker("30", "0.03"),
        4: ticker("40", "0"),
    }
    market_caps = caps(AAA="100", BBB="100", CCC="100", DDD="100")
    stamp = 1_799_913_600_000
    histories = {iid: [{"timestamp_ms": stamp, "close": "1"}] for iid in (1, 2, 3, 4)}
    monkeypatch.setattr(strategy, "_universe_history_ready", lambda *args: True)
    monkeypatch.setattr(
        strategy,
        "_load_market_cap_records",
        lambda required, now: (market_caps, {"coverage": {"resolved_symbols": 4, "required_symbols": 4}}),
    )

    result = strategy.rank_volume_pricing_universe(
        rows, histories, tickers, Decimal("100"), as_of_timestamp_ms=stamp
    )

    assert [row.symbol for row in result.research_longs] == ["mexc:3", "mexc:1"]
    assert [row.symbol for row in result.research_shorts] == ["mexc:2"]
    assert [row.symbol for row in result.executable_longs] == ["mexc:3"]
    assert [row.symbol for row in result.executable_shorts] == ["mexc:2"]
    assert result.instruments_by_key["mexc:3"]["volume_to_market_cap_ratio"] == "0.3"


def test_unmatched_market_cap_is_excluded_without_symbol_guessing(monkeypatch):
    monkeypatch.setattr(strategy, "_universe_history_ready", lambda *args: True)
    rows = [
        instrument(1, "AAA_USDT", "AAA"),
        instrument(2, "BBB_USDT", "BBB"),
        instrument(3, "CCC_USDT", "CCC"),
        instrument(4, "DDD_USDT", "DDD"),
        instrument(5, "EEE_USDT", "EEE"),
    ]
    tickers = {1: ticker("10", "0.02"), 2: ticker("20", "-0.01"),
               3: ticker("30", "0.03"), 4: ticker("40", "-0.02"),
               5: ticker("50", "0.01")}
    market_caps = caps(AAA="100", CCC="100", DDD="100", EEE="100")
    stamp = 1_799_913_600_000
    histories = {iid: [{"timestamp_ms": stamp, "close": "1"}] for iid in (1, 2, 3, 4, 5)}
    monkeypatch.setattr(
        strategy,
        "_load_market_cap_records",
        lambda required, now: (market_caps, {"coverage": {"resolved_symbols": 4, "required_symbols": 5}}),
    )

    result = strategy.rank_volume_pricing_universe(
        rows, histories, tickers, Decimal("100"), as_of_timestamp_ms=stamp
    )

    assert [row.symbol for row in result.research_longs] == ["mexc:5", "mexc:3", "mexc:1"]
    assert [row.symbol for row in result.research_shorts] == ["mexc:4"]
    assert [row.symbol for row in result.executable_longs] == ["mexc:5"]
    assert [row.symbol for row in result.executable_shorts] == ["mexc:4"]
    assert any("BBB_USDT:MISSING_OR_AMBIGUOUS_MARKET_CAP:BBB" == item for item in result.excluded)


def test_non_usdt_contracts_never_enter_the_strategy_universe(monkeypatch):
    monkeypatch.setattr(strategy, "_universe_history_ready", lambda *args: True)
    rows = [instrument(1, "AAA_USDT", "AAA")]
    stamp = 1_799_913_600_000
    histories = {1: [{"timestamp_ms": stamp, "close": "1"}]}
    other = dict(instrument(2, "BBB_USDC", "BBB"))
    other["quote_asset"] = "USDC"
    other["settlement_asset"] = "USDC"
    other["usdt_account_eligible"] = False
    monkeypatch.setattr(
        strategy,
        "_load_market_cap_records",
        lambda required, now: (caps(AAA="100"), {"coverage": {"resolved_symbols": 1, "required_symbols": 1}}),
    )

    result = strategy.rank_volume_pricing_universe(
        rows + [other],
        histories,
        {1: ticker("10", "0.02"), 2: ticker("1000", "-0.5")},
        Decimal("100"),
        as_of_timestamp_ms=stamp,
    )

    assert [row.symbol for row in result.research_longs] == ["mexc:1"]
    assert result.research_shorts == []


def test_coinpaprika_duplicate_stale_and_multiplier_alias_resolution(monkeypatch, tmp_path):
    now = 1_800_000_000_000
    cache_path = tmp_path / "provider_cache_v2.json"
    attempt_path = tmp_path / "daily_attempt_v2.json"
    monkeypatch.setattr(
        strategy, "_market_cap_paths", lambda: (cache_path, attempt_path)
    )
    monkeypatch.setattr(
        strategy,
        "_fetch_coinpaprika_top_tickers",
        lambda: caps(AAA="100").values(),
    )
    monkeypatch.setattr(
        strategy,
        "_fetch_coinpaprika_coin_catalogue",
        lambda: [
            {"id": "bbb-1", "symbol": "BBB", "name": "BBB One"},
            {"id": "bbb-2", "symbol": "BBB", "name": "BBB Two"},
            {"id": "ccc-id", "symbol": "CCC", "name": "CCC"},
            {"id": "pepe-id", "symbol": "PEPE", "name": "Pepe"},
            {"id": "filecoin-id", "symbol": "FIL", "name": "Filecoin"},
        ],
    )

    def single_ticker(coin_id):
        stamp = now - 7 * 60 * 60 * 1000 if coin_id == "ccc-id" else now
        symbol = "CCC" if coin_id == "ccc-id" else ("FIL" if coin_id == "filecoin-id" else "PEPE")
        return {
            "symbol": symbol,
            "name": symbol,
            "market_cap_usd": "200",
            "source_id": coin_id,
            "provider": "coinpaprika",
            "source_updated_ms": stamp,
        }

    monkeypatch.setattr(strategy, "_fetch_coinpaprika_single_ticker", single_ticker)
    monkeypatch.setattr(strategy, "_fetch_coingecko_market_pages", lambda: [])

    resolved, report = strategy._load_market_cap_records(
        {"AAA", "BBB", "CCC", "1000PEPE", "FILECOIN"}, now
    )

    assert set(resolved) == {"AAA", "1000PEPE", "FILECOIN"}
    assert resolved["1000PEPE"]["source_symbol"] == "PEPE"
    assert resolved["1000PEPE"]["symbol_match_type"] == "mexc_1000x_coinpaprika_denomination_alias"
    assert resolved["FILECOIN"]["source_symbol"] == "FIL"
    assert resolved["FILECOIN"]["symbol_match_type"] == "exact_normalized_name_coinpaprika_alias"
    assert report["coverage"]["ambiguous_symbols"] == ["BBB"]
    assert report["coverage"]["stale_symbols"] == ["CCC"]
    assert cache_path.is_file()
    assert json.loads(attempt_path.read_text())["status"] == "COMPLETED"


def test_market_cap_api_is_deferred_until_full_mexc_history_coverage(monkeypatch):
    monkeypatch.setattr(strategy, "_universe_history_ready", lambda *args: False)

    def forbidden_lookup(*args, **kwargs):
        raise AssertionError("Market-cap provider must not be called during bootstrap")

    monkeypatch.setattr(strategy, "_load_market_cap_records", forbidden_lookup)
    result = strategy.rank_volume_pricing_universe(
        [instrument(1, "AAA_USDT", "AAA")],
        {},
        {1: ticker("10", "0.02")},
        Decimal("100"),
        as_of_timestamp_ms=1_799_913_600_000,
    )

    assert result.executable_longs == []
    assert result.executable_shorts == []
    assert result.excluded[0].startswith("BOOTSTRAP_INCOMPLETE")


def test_state_verification_retries_only_eventual_consistency(monkeypatch):
    calls = {"verify": 0, "sleep": []}

    def verify():
        calls["verify"] += 1
        if calls["verify"] < 3:
            raise RuntimeError(
                "Published event batch is not in the verified remote chain: pending"
            )
        return "verified"

    result = strategy._verify_remote_with_consistency_retries(
        verify, sleep=lambda delay: calls["sleep"].append(delay)
    )

    assert result == "verified"
    assert calls["verify"] == 3
    assert calls["sleep"] == [1, 2]


def test_state_verification_does_not_retry_integrity_errors():
    calls = {"verify": 0, "sleep": []}

    def verify():
        calls["verify"] += 1
        raise RuntimeError("State event chain forks after batch abc")

    try:
        strategy._verify_remote_with_consistency_retries(
            verify, sleep=lambda delay: calls["sleep"].append(delay)
        )
    except RuntimeError as exc:
        assert "forks" in str(exc)
    else:
        raise AssertionError("Permanent integrity errors must fail immediately")

    assert calls["verify"] == 1
    assert calls["sleep"] == []


def test_coingecko_keyless_market_pages_fill_coinpaprika_gaps(monkeypatch, tmp_path):
    now = 1_800_000_000_000
    cache_path = tmp_path / "provider_cache_v2.json"
    attempt_path = tmp_path / "daily_attempt_v2.json"
    monkeypatch.setattr(
        strategy, "_market_cap_paths", lambda: (cache_path, attempt_path)
    )
    monkeypatch.setattr(strategy, "COINGECKO_MARKET_PAGES", 1)
    monkeypatch.setattr(
        strategy,
        "_fetch_coinpaprika_top_tickers",
        lambda: [{
            "symbol": "AAA", "name": "AAA", "market_cap_usd": "100",
            "source_id": "aaa-paprika", "provider": "coinpaprika",
            "source_updated_ms": now,
        }],
    )
    monkeypatch.setattr(
        strategy,
        "_fetch_coinpaprika_coin_catalogue",
        lambda: [{"id": "bbb-paprika", "symbol": "BBB", "name": "BBB"}],
    )
    monkeypatch.setattr(
        strategy,
        "_fetch_coingecko_market_pages",
        lambda: [{
            "symbol": "BBB", "name": "BBB", "market_cap_usd": "200",
            "source_id": "bbb-gecko", "provider": "coingecko",
            "source_updated_ms": now,
        }],
    )

    def forbidden_single_lookup(_coin_id):
        raise AssertionError("CoinGecko should fill BBB without an extra CoinPaprika call")

    monkeypatch.setattr(
        strategy, "_fetch_coinpaprika_single_ticker", forbidden_single_lookup
    )

    resolved, report = strategy._load_market_cap_records({"AAA", "BBB"}, now)

    assert set(resolved) == {"AAA", "BBB"}
    assert resolved["AAA"]["provider"] == "coinpaprika"
    assert resolved["BBB"]["provider"] == "coingecko"
    assert resolved["BBB"]["symbol_match_type"] == "exact_coingecko_top_2000"
    assert report["provider"] == "coinpaprika+coingecko"
    assert report["attribution"] == "Powered by CoinPaprika; Powered by CoinGecko"
    assert report["coverage"]["resolved_symbols"] == 2
    assert report["coingecko_api_calls_used"] == 1
    assert json.loads(cache_path.read_text())["cache_version"] == 2
    assert json.loads(attempt_path.read_text())["status"] == "COMPLETED"


def test_coingecko_fallback_survives_coinpaprika_plan_limit_but_reports_missing(monkeypatch, tmp_path):
    now = 1_800_000_000_000
    cache_path = tmp_path / "provider_cache_v2.json"
    attempt_path = tmp_path / "daily_attempt_v2.json"
    monkeypatch.setattr(
        strategy, "_market_cap_paths", lambda: (cache_path, attempt_path)
    )
    monkeypatch.setattr(strategy, "COINGECKO_MARKET_PAGES", 1)
    monkeypatch.setattr(
        strategy,
        "_fetch_coinpaprika_top_tickers",
        lambda: [{
            "symbol": "AAA", "name": "AAA", "market_cap_usd": "100",
            "source_id": "aaa-paprika", "provider": "coinpaprika",
            "source_updated_ms": now,
        }],
    )
    monkeypatch.setattr(
        strategy,
        "_fetch_coinpaprika_coin_catalogue",
        lambda: [
            {"id": "bbb-paprika", "symbol": "BBB", "name": "BBB"},
            {"id": "ccc-paprika", "symbol": "CCC", "name": "CCC"},
        ],
    )
    monkeypatch.setattr(
        strategy,
        "_fetch_coingecko_market_pages",
        lambda: [{
            "symbol": "BBB", "name": "BBB", "market_cap_usd": "200",
            "source_id": "bbb-gecko", "provider": "coingecko",
            "source_updated_ms": now,
        }],
    )

    def plan_limited(_coin_id):
        raise strategy.MarketCapDataError("HTTP 402 from CoinPaprika ticker")

    monkeypatch.setattr(strategy, "_fetch_coinpaprika_single_ticker", plan_limited)

    resolved, report = strategy._load_market_cap_records({"AAA", "BBB", "CCC"}, now)

    assert set(resolved) == {"AAA", "BBB"}
    assert report["coinpaprika_single_lookup_plan_limited"] is True
    assert report["coverage"]["missing_symbols"] == ["CCC"]
    assert report["coverage"]["resolved_symbols"] == 2
