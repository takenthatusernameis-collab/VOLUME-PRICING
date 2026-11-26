# Market-cap data-source audit

Last checked: 2026-11-26. The strategy needs circulating market capitalization in USD for each MEXC USDT perpetual's underlying base asset. Its numerator is MEXC's own rolling 24-hour USDT quote turnover, not an aggregator's global volume.

## Selected source: CoinPaprika Free API

- No API key, account, registration or payment card.
- Free tier: 20,000 calls/month per IP and a stated 2,000-asset data limit. The bulk ticker catalogue returns up to 2,000 assets.
- The public coin catalogue lists more than 11,000 active assets, and the API documents a single-coin ticker endpoint, GET /v1/tickers/{coin_id}. The workflow uses that endpoint for MEXC symbols outside the bulk list, but the free plan's 2,000-asset entitlement may restrict out-of-list access. The first individual lookup is therefore fail-fast: if the endpoint returns 402/403, the cycle stops immediately without consuming the remaining lookup budget. Actual out-of-list free-tier coverage remains to be verified by the first full-universe run.
- The workflow first matches the 2,000-asset ticker list, then uses the full coin catalogue to find unique IDs for MEXC assets outside that list and requests their individual tickers.
- Rate limit: 10 requests/second. Individual lookups are paced at no more than approximately 8 requests/second.
- Monthly quota guard: at most 640 individual ticker lookups plus two catalogue calls per daily decision. This is at most 642 calls/day, or 19,902 calls in a 31-day month. If more lookups are needed, the strategy fails closed rather than exceeding the free-tier budget. This quota guard does not override the separate 2,000-asset entitlement.
- Free licence is for personal use, side projects, learning and prototypes, not commercial products. Bulk redistribution of raw API data requires written permission, and a "Powered by CoinPaprika" attribution is required.
- This is a personal paper-research workflow. The raw coin catalogue and absolute provider market-cap values are kept in memory and in a private GitHub Actions cache only. They are not committed to the public repository. Public artifacts contain derived volume/market-cap ratios, MEXC turnover, provider attribution and source timestamps, not a bulk copy of CoinPaprika data.
- Provider lookups are deferred until all eligible MEXC histories and current tickers pass the bootstrap gate. They run for the daily decision, never on five-minute mark snapshots. The private cache and daily attempt latch prevent repeated calls on retry runs.

Official references:
- https://coinpaprika.com/api/pricing
- https://coinpaprika.com/terms-api
- https://coinpaprika.com/api/licensing
- https://docs.coinpaprika.com/

## Other providers investigated and rejected for this scheduled workflow

### CoinMarketCap Keyless Public API

- It is genuinely keyless: no signup, API key or auth header for its supported /public-api routes. Its listing endpoints provide circulating market cap and current market data.
- However, CoinMarketCap's current FAQ describes Keyless as a curated subset for prototyping, evaluating response shapes and quick one-off queries. It recommends the authenticated Basic tier for longer-running integrations and its Keyless guide says production usage should use an authenticated plan.
- The separate free Basic tier requires registration and an API key, which violates the no-authentication requirement.
- Therefore CoinMarketCap Keyless is not used by this scheduled Actions workflow.

Official references:
- https://coinmarketcap.com/api/keyless/
- https://coinmarketcap.com/api/faq/
- https://coinmarketcap.com/api/documentation/pro-api-reference/keyless-public-api/

### CoinGecko Keyless Public API

- It offers no-key access to market-cap data through `/coins/markets`, with up to 250 assets per page. Eight paginated requests cover the top 2,000 market-cap-ranked assets.
- Its unauthenticated shared rate pool is currently documented as 5–15 calls/minute, depending on global load. An eight-page daily snapshot is technically feasible when paced conservatively, but can still encounter shared-pool HTTP 429 responses and has no guaranteed per-project monthly quota.
- This makes it a viable no-auth alternative for a once-daily paper decision, not a dependable source for five-minute polling. This project currently prefers CoinPaprika's published 20,000-call monthly allowance and calls it only after the MEXC daily-history gate passes.
- CoinGecko is not currently configured as a fallback; if CoinPaprika coverage fails its 80% gate or the free-tier asset limit, the portfolio remains blocked rather than silently switching providers or mixing stale data.

Official references:
- https://docs.coingecko.com/reference/coins-markets
- https://docs.coingecko.com/docs/keyless-public-api
- https://support.coingecko.com/articles/5125303456-what-is-the-rate-limit-for-coingecko-api-public-plan

### CoinLore

- Its public API needs no key and advertises market-cap data for more than 14,000 assets.
- However, its current site Terms of Service prohibit automated bots, data mining/scraping, and copying/redistributing content without written consent. That conflicts with a scheduled GitHub Actions workflow.
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
2. Prefer exact symbol matches. For MEXC denomination-prefixed contracts such as 1000BONK or 1000000MOG, remove a known multiplier prefix only when the underlying CoinPaprika symbol is unique. If no symbol or multiplier match exists, allow an exact normalized CoinPaprika name match (for example FILECOIN to FIL) only when the provider name is unique. Record the alias rule in the ranking.
3. Do not fuzzy-match, infer a token from a similar name, or choose an arbitrary duplicate symbol.
4. If CoinPaprika returns multiple assets with the same symbol, mark the symbol ambiguous and exclude it.
5. Require positive finite circulating market cap and a source timestamp no older than six hours.
6. Require at least 80% fresh, unambiguous market-cap coverage across distinct eligible MEXC base-asset symbols; otherwise fail closed and do not update the portfolio.
7. Use MEXC turnover_24h_quote for the numerator and treat USDT as approximately USD 1:1.
8. Persist the daily ranking, derived ratio, MEXC turnover, provider attribution and source timestamp. Do not persist the raw provider catalogue or absolute market-cap values.
9. Never use today's market cap to manufacture historical observations. This is a forward paper simulation, not a historical backtest using current market caps.

The ratio is:

volume_to_market_cap = MEXC_24h_USDT_turnover / circulating_market_cap_USD

It measures the MEXC venue's 24-hour turnover relative to the asset's external circulating capitalization; it is not a claim that MEXC represents the asset's full global volume.
