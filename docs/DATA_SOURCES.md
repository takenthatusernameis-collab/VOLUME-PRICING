# Market-cap data-source audit

Last checked: 2026-11-26. The strategy requires circulating market capitalization in USD for the base asset of every MEXC USDT perpetual. The numerator is MEXC's own rolling 24-hour USDT quote turnover, not an aggregator's global volume.

## Provider decision

### 1. CoinMarketCap Keyless Public API — primary

- Base URL: `https://pro-api.coinmarketcap.com/public-api`
- No key, signup, account or authentication header.
- Endpoint: `GET /v3/cryptocurrency/listings/latest?start=1&limit=5000&convert=USD`
- Returns active-asset listings with symbol, circulating supply, market cap, rolling 24-hour volume, 24-hour percentage change and quote update timestamps.
- Listings documentation says the endpoint refreshes every 15 seconds. The keyless API has a shared IP-based rate pool; exact numerical limits are not published on the page. HTTP 429 responses must be handled with bounded exponential backoff.
- The endpoint is paginated. The implementation requests up to 5,000 rows and records the returned count. A provider response that is empty, malformed, or carries a non-zero API error is not accepted.

Official documentation:
- https://coinmarketcap.com/api/documentation/pro-api-reference/keyless-public-api/
- https://coinmarketcap.com/api/documentation/pro-api-reference/cryptocurrency/

### 2. CoinPaprika — first fallback / coverage supplement

- Base URL: `https://api.coinpaprika.com/v1`
- No key, account or card for the keyless Free tier.
- Endpoint: `GET /tickers`
- Up to 2,000 assets, including USD market capitalization, 24-hour volume, 24-hour price change and `last_updated`.
- Free personal-use quota: 20,000 calls/month per IP; 10 requests/second; data refresh up to 10 minutes.
- The free plan is for personal use and requires a “Powered by CoinPaprika” attribution. It is not a commercial redistribution licence.

Official documentation:
- https://coinpaprika.com/api
- https://docs.coinpaprika.com/

### 3. CoinLore — second fallback / long-tail coverage

- Base URL: `https://api.coinlore.net/api`
- No key or registration.
- Endpoint: `GET /tickers/?start=0&limit=...`, paginated using `info.coins_num`.
- Provides coin ID, symbol, name, USD market cap, 24-hour volume, price changes and circulating supply for a catalogue exceeding 14,000 assets.
- The provider recommends approximately one request per second for stable/fair use. The fallback is fetched only when the first two sources leave MEXC base symbols unmatched, and pages are paced.

Official documentation:
- https://www.coinlore.com/cryptocurrency-data-api/v1/models

### 4. CoinGecko Keyless Public API — evaluated, not selected

- No API key or signup is required for its Keyless Public API.
- `/coins/markets` supplies price, market cap and volume; historical market charts are also available.
- Official documentation currently describes a shared IP pool of approximately 5 calls/minute, varying with server load, and explicitly says keyless endpoints are not suitable for production workloads, scheduled polling or high-frequency updates.
- It also requires attribution when displaying its data.

Documentation:
- https://docs.coingecko.com/docs/keyless-public-api
- https://support.coingecko.com/articles/5125303456-what-is-the-rate-limit-for-coingecko-api-public-plan

### 5. DexScreener — evaluated, not selected as a market-cap authority

- No authentication for its public API.
- Token-pair endpoints expose `marketCap` and `fdv` when available, plus liquidity and pool-level volume.
- Coverage is pool/token-centric, not a complete circulating-market-cap catalogue for centralized perpetual assets. Market cap may be absent, and FDV is not interchangeable with circulating market cap.
- Useful for supplementary token/pool research, not the denominator of this strategy.

Documentation:
- https://docs.dexscreener.com/api/reference

## Matching and quality policy

1. Match MEXC `base_asset` to an exact uppercase provider symbol.
2. Do not fuzzy-match, infer a token from a similar name, or choose an arbitrary duplicate symbol.
3. If a provider returns multiple assets with the same symbol, mark the symbol ambiguous and exclude it.
4. A missing symbol in CoinMarketCap may be resolved from CoinPaprika, then CoinLore. A symbol explicitly ambiguous in a provider is not silently resolved by guessing.
5. Require positive finite circulating market cap and a fresh source timestamp. Missing, zero, stale or malformed data is excluded.
6. Use MEXC `turnover_24h_quote` for the numerator and treat USDT as approximately USD 1:1. Record this assumption.
7. Record provider, source ID, name, market cap, source timestamp, MEXC turnover, MEXC 24-hour price change and the computed ratio.
8. Persist a decision-stamped snapshot. Never use today's market cap to manufacture historical observations.
9. A provider outage or rate-limit response is visible in the cycle report. No synthetic or stale market-cap fallback is permitted.

The ratio is:

`volume_to_market_cap = MEXC_24h_USDT_turnover / circulating_market_cap_USD`

It is a cross-sectional activity ratio, not a claim that the asset's full global volume is represented by MEXC.
