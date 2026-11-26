from decimal import Decimal

import scripts.volume_pricing_paper_cycle as strategy


def instrument(iid: int, symbol: str, base: str) -> dict:
    return {
        "instrument_id": iid,
        "symbol": symbol,
        "base_asset": base,
        "quote_asset": "USDT",
        "settlement_asset": "USDT",
        "usdt_account_eligible": True,
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
