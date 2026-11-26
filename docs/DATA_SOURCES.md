# Market-cap data-source audit

Last checked: 2026-11-26. The strategy needs circulating market capitalization in USD for the base asset of each MEXC USDT perpetual. Its numerator is MEXC's own rolling 24-hour USDT quote turnover, not an aggregator's global volume.

## Selected source: CoinPaprika Free API

- Base URL: https://api.coinpaprika.com/v1
- Endpoint: GET /tickers
- No API key, account, registration or payment card.
- Free tier: 20,000 calls/month per IP and up to 2,000 assets.
- Ticker response includes exact symbol, name, CoinPaprika ID, USD market cap, 24-hour volume/change and last_updated.
- Free data updates within approximately 10 minutes; API rate limit is 10 requests/second.
- Free licence is for personal use, side projects, learning and prototypes. It is not for commercial products. Bulk redistribution of raw API data requires written permission, and a "Powered by CoinPaprika" attribution is required.
- This is a personal paper-research workflow. It makes one ticker-catalogue request only when the daily ranking is recomputed (including bootstrap retries), not on each five-minute mark. The raw 2,000-asset catalogue and absolute provider market-cap values are kept in memory only; they are not written to GitHub. Public artifacts contain the strategy's derived volume/market-cap ratios, MEXC turnover, provider attribution and source timestamps, not a bulk copy of CoinPaprika data.

Official references:
- https://coinpaprika.com/api/pricing
- https://coinpaprika.com/terms-api
- https://coinpaprika.com/api/licensing
- https://docs.coinpaprika.com/

## Other providers investigated and rejected for this scheduled workflow

### CoinMarketCap Keyless Public API

- It is genuinely keyless: no signup, API key or auth header for its supported /public-api routes. Its listing endpoints provide circulating market cap and current market data.
- However, CoinMarketCap's current FAQ explicitly describes Keyless as a curated subset for prototyping, evaluating response shapes and quick one-off queries. It recommends the authenticated Basic tier for longer-running integrations and its Keyless guide says production usage should use an authenticated plan.
- The separate free Basic tier requires registration and an API key, which violates the user's no-authentication requirement.
- Therefore CoinMarketCap Keyless is not used by this scheduled Actions workflow.

Official references:
- https://coinmarketcap.com/api/keyless/
- https://coinmarketcap.com/api/faq/
- https://coinmarketcap.com/api/documentation/pro-api-reference/keyless-public-api/

### CoinGecko Keyless Public API

- It offers no-key access to market-cap data for evaluation and limited queries.
- Its unauthenticated shared rate pool is low (about 5 calls/minute, depending on load) and its documentation says the keyless route is not suitable for scheduled production or high-frequency workloads.
- It is not used for this five-minute Actions project.

Official references:
- https://docs.coingecko.com/docs/keyless-public-api
- https://support.coingecko.com/articles/5125303456-what-is-the-rate-limit-for-coingecko-api-public-plan

### CoinLore

- Its public API needs no key and advertises market-cap data for more than 14,000 assets.
- However, its current site Terms of Service prohibit automated bots, data mining/scraping, and copying/redistributing content without written consent. That conflicts with a scheduled GitHub Actions workflow that fetches and stores derived rankings.
- It is not used.

Official references:
- https://www.coinlore.com/cryptocurrency-data-api/terms
- https://www.coinlore.com/terms-of-use

### CoinCap

- The old v2 no-key API has been retired; the current v3 API requires a bearer key/account. Keyless x402 endpoints require per-call USDC payment.
- It is not used.

Official references:
- https://rest.coincap.io/api-docs/
- https://pro.coincap.io/api-docs/

### DexScreener and DeFiLlama

- DexScreener exposes token/pool market-cap or FDV fields when available, but does not provide a complete, canonical circulating-market-cap catalogue for all centralized-exchange perpetual assets. FDV is not interchangeable with circulating market cap.
- DeFiLlama's public price endpoints are useful for token pricing but do not supply a complete comparable circulating-market-cap catalogue for this strategy.
- Neither is used as the market-cap denominator.

## Matching and quality policy

1. Match MEXC base_asset to an exact uppercase CoinPaprika symbol.
2. Do not fuzzy-match, infer a token from a similar name, or choose an arbitrary duplicate symbol.
3. If CoinPaprika returns multiple assets with the same symbol, mark the symbol ambiguous and exclude it.
4. Require positive finite circulating market cap and a source timestamp no older than 24 hours.
5. Require at least 80% fresh, unambiguous market-cap coverage across distinct eligible MEXC base-asset symbols; otherwise fail closed and do not update the portfolio.
6. Use MEXC turnover_24h_quote for the numerator and treat USDT as approximately USD 1:1.
7. Persist the daily ranking, derived ratio, MEXC turnover, provider attribution and source timestamp. Do not persist the raw provider catalogue or absolute market-cap values.
8. Never use today's market cap to manufacture historical observations. This is a forward paper simulation, not a historical backtest using current market caps.

The ratio is:

volume_to_market_cap = MEXC_24h_USDT_turnover / circulating_market_cap_USD

It measures the MEXC venue's 24-hour turnover relative to the asset's external circulating capitalization; it is not a claim that MEXC represents the asset's full global volume.
