# Open Markets API

[![python](https://img.shields.io/badge/Python-3776AB?logo=python&logoColor=white)](https://python.org/)
[![fastapi](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![postgresql](https://img.shields.io/badge/PostgreSQL-4169E1?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![redis](https://img.shields.io/badge/Redis-FF4438?logo=redis&logoColor=white)](https://redis.io/)
[![uv](https://img.shields.io/badge/uv-DE5FE9?logo=uv&logoColor=white)](https://docs.astral.sh/uv/)
[![ruff](https://img.shields.io/badge/Ruff-D7FF64?logo=ruff&logoColor=black)](https://docs.astral.sh/ruff/)
[![pre-commit](https://img.shields.io/badge/pre--commit-FAB040?logo=pre-commit&logoColor=black)](https://pre-commit.com/)

- [Open Markets API](#open-markets-api)
  - [Description](#description)
  - [Architecture](#architecture)
    - [Project Structure](#project-structure)
    - [Layers](#layers)
    - [Rules](#rules)
  - [Request Lifecycle](#request-lifecycle)
    - [API Requests](#api-requests)
    - [Jobs](#jobs)
  - [Usage](#usage)
    - [Available Endpoints](#available-endpoints)
    - [Stock Prices](#stock-prices)
    - [News](#news)
    - [Indices](#indices)
    - [Errors](#errors)
    - [Rate Limiting](#rate-limiting)
    - [Jobs](#jobs-1)
    - [Configuration](#configuration)
    - [Logging](#logging)
  - [Setup](#setup)
    - [Prerequisites](#prerequisites)
    - [Using Docker](#using-docker)
    - [Manually](#manually)
  - [Testing](#testing)
    - [Manually](#manually-1)
    - [Using Docker](#using-docker-1)

## Description

**openmarkets-api** is a [Python](https://www.python.org/) API
for public market data from regional exchanges.

It is built on top of [openmarkets-sdk](https://github.com/abdelrahman0w/openmarkets-sdk),
which handles talking to the exchanges and parsing their responses into typed models,
so this project only has to worry about storing, caching, and serving that data.

> The project is in its early stages, so there is not much to see here yet

## Architecture

The project is split into layers, each with a single responsibility,
and every layer is grouped by exchange (`egx/`),
so adding a new exchange is a new folder in each layer rather than changes all over the place.

### Project Structure

```
openmarkets-api/
├── bin/
│   ├── entrypoint.sh               the api entrypoint (--dev for reload)
│   └── jobs.sh                     runs a single job by name
├── migrations/                     alembic migrations
├── src/
│   ├── main.py                     app, lifespan, middlewares, exception handlers, routers
│   ├── settings.py                 settings read from the environment
│   ├── dependencies.py             db session, redis, egx service, the clock, the client ip
│   ├── routes/                     path, params, status
│   │   ├── responses.py            json served as it is, often straight from the cache
│   │   ├── health.py               liveness and readiness
│   │   └── egx/
│   ├── controllers/                use cases, called by routes only
│   │   └── egx/
│   ├── actions/                    reusable units, called by controllers, jobs, and events
│   │   └── egx/
│   ├── repositories/               queries only
│   │   └── egx/
│   ├── jobs/
│   │   ├── base.py                 what a job is, its run, help, flags, and monitor
│   │   ├── egx.py                  the egx jobs, next to their flags
│   │   └── main.py                 runs a job once, by name
│   ├── services/                   external systems
│   │   ├── egx/
│   │   │   └── client.py           the sdk client lifecycle and error mapping
│   │   └── gemini/
│   │       └── client.py           gemini, which summarizes the news, over its rest api
│   ├── providers/                  stateful infra, opened in the lifespan
│   │   ├── db.py                   async engine and session maker
│   │   ├── redis.py
│   │   ├── logger.py
│   │   └── error_tracking.py       sentry, and the job monitors
│   ├── middlewares/
│   │   ├── logs_contextualizer.py  the request's context on every log line, and its log
│   │   └── rate_limit.py           the sliding window, per client ip
│   ├── utils/                      pure helpers
│   ├── structs/
│   │   ├── enums/
│   │   ├── models/                 pydantic models
│   │   │   ├── common.py           the page envelope and the error shape
│   │   │   ├── requests/           what comes in
│   │   │   └── responses/          what goes out
│   │   └── tables/                 sqlalchemy tables
│   │       ├── base.py             declarative base, metadata, timestamps
│   │       └── egx/
│   └── exceptions/
│       ├── custom_exceptions.py
│       └── exception_handlers.py   exceptions to http errors, registered once
└── tests/                          laid out like src, by layer
```

### Layers

| Layer | Responsibility | Called By | May Use |
| --- | --- | --- | --- |
| `routes` | The http shape of an endpoint | FastAPI | `controllers`, `dependencies`, `structs/models` |
| `controllers` | One use case per file | `routes` | `actions`, `repositories`, `services`, `providers`, `utils` |
| `actions` | Reusable logic and side effects | `controllers`, `jobs`, events | `repositories`, `services`, `providers`, `utils` |
| `repositories` | Queries, nothing else | `controllers`, `actions` | `structs/tables` |
| `services` | Talking to external systems | `controllers`, `actions` | the SDK |
| `providers` | Connections and their lifecycle | the lifespan, `dependencies`, `jobs` | `settings` |
| `utils` | Pure helpers | any layer | nothing from `src` |

### Rules

- **Tables never leave the repositories.** `structs/tables` is only imported by `repositories`
    and `migrations`, everything above them works with `structs/models`.
- **The SDK stays behind `services` and `structs`.** `services` is the only layer that calls it,
    and `structs/models` re-exports its request and response models,
    so every other layer imports them from `structs`, and a change in the SDK
    is a change in those two places.
- **FastAPI stays at the edge.** Only `main.py`, `routes`, `dependencies.py`, `middlewares`,
    and `exception_handlers.py` import it. Everything else raises exceptions from `custom_exceptions.py`,
    and they are mapped to http errors once.
- **Repositories never commit.** The session is always passed in,
    and whoever opens it, a controller or an action, owns the transaction.
- **Jobs and events call actions, never controllers.**
- **Utils are pure.** No i/o, no state, and no imports from `src`.
    A helper that is only used by one layer stays in that layer.

## Request Lifecycle

### API Requests

1. The request goes through the middlewares
1. The route validates the path, query, and body into a request model
1. The route calls its controller, with the db session, redis, and the egx service injected through `dependencies.py`
1. The controller checks redis first, and returns the cached json as it is stored, untouched
1. Otherwise, it reads the data from postgres through a repository, and caches it
1. Only if nothing is stored yet, it falls back to the exchange
1. The route serves the json as it is, without parsing it into models and back

```
client → middlewares → route → controller → redis          (hit → return)
                                          → repository     (miss → postgres)
                                          → service        (nothing stored → exchange)
       ← json ← route ← controller
```

During the session, stock prices are the exception: they are fetched live from the exchange,
shared by every request for a few seconds, see [stock prices](#stock-prices).
Outside it, they are served from storage, which the [sync job](#jobs-1) fills every minute of the session.
News is served from storage too, which the [news sync](#jobs-1) fills, see [news](#news).
Endpoints without stored data, like the gold board, are fetched from the exchange
and cached for `REDIS_LIVE_CACHE_SECONDS`, so traffic does not reach it.

Any exception raised along the way is caught by `exception_handlers.py`
and returned as an http error, so no layer below the routes has to know about http.

### Jobs

Jobs keep the stored data fresh, so most requests never have to wait on the exchange.

1. A cron in dokploy runs `bin/jobs.sh <job>`, which runs that one job and exits
1. The job opens the connections it needs, since jobs do not run through the api lifespan
1. While the market is open, the sync fetches the board from the exchange, refreshes the cache,
    and stores it, every run, in a single transaction
1. Unchanged rows are not rewritten, so a quiet sync only adds the new quotes

```
bin/jobs.sh sync_stock_prices → jobs/main.py → action → service    (exchange, every run)
                                                      → redis      (cache, every run)
                                                      → repository (postgres, every run)
```

## Usage

> The API does not serve any interactive docs or OpenAPI schema

### Available Endpoints

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/health/live` | Whether the process is up, for a liveness probe |
| `GET` | `/health/ready` | Whether postgres and redis can be reached, `503` otherwise, for a readiness probe |
| `GET` | `/egx/market/status` | Whether the exchange is open or closed |
| `GET` | `/egx/market/stocks` | The paged stock quote board, sortable into gainers, losers, and more |
| `GET` | `/egx/market/gold` | Gold quotes per brand |
| `GET` | `/egx/market/silver` | Silver quotes per brand |
| `GET` | `/egx/market/derivatives` | The futures board |
| `GET` | `/egx/market/securities/{isin}/price-volume-points` | Daily closes and volumes for a single security |
| `GET` | `/egx/market/summaries` | Daily totals per market segment, plus market cap |
| `GET` | `/egx/market/indicators` | Market metrics with their history |
| `GET` | `/egx/instruments/treasury-bonds` | Listed treasury bonds with their yields and durations |
| `GET` | `/egx/instruments/mutual-funds` | Listed mutual funds |
| `GET` | `/egx/news` | Disclosures and announcements, filtered by section, text, date, company, or attachments |
| `GET` | `/egx/news/financial-statements` | Financial statement filings, with their figures parsed out |
| `GET` | `/egx/news/{news_id}` | A single news item by its id, with its AI summary once one is made |
| `GET` | `/egx/stocks` | Every listed stock, with its details and latest quote |
| `GET` | `/egx/stocks/performance` | Every stock's base close over a `period`, and what it traded since, to measure its change by |
| `GET` | `/egx/stocks/{isin}` | A single stock, with its details and latest quote |
| `GET` | `/egx/stocks/{isin}/history` | A stock's price history, over a `period` |
| `GET` | `/egx/stocks/{isin}/news` | A stock's own news, newest first, paged |
| `GET` | `/egx/indices` | Every index's latest level, change, and year to date, with its session's points |
| `GET` | `/egx/indices/performance` | Every index's base close over a `period`, to measure its change by |
| `GET` | `/egx/indices/{index}/history` | An index's history, over a `period` |
| `GET` | `/egx/indices/{index}/summary` | An index's value, volume, trades and market cap, and their share of the market |
| `GET` | `/egx/indices/{index}/weights` | The weights of EGX30's members, the only index EGX publishes them for |

> Every EGX endpoint is served under `/egx`. The readiness probe leaves EGX out,
> so an outage on its side does not take the API out of rotation

The API connects to postgres and redis on startup, and exits if either cannot be reached.

Paged endpoints return the rows under `items`, along with the pagination counters:

```json
{
    "items": [],
    "page": 1,
    "page_size": 25,
    "total_count": 221,
    "total_pages": 9
}
```

> Timestamps are returned in UTC

### Stock Prices

During the session, `/egx/stocks` and `/egx/stocks/{isin}` are fetched live from EGX.
A fetch is shared by every request for `EGX_MARKET_LIVE_PRICES_CACHE_SECONDS`, and concurrent requests share one fetch,
so EGX sees a request every few seconds at most, however much traffic there is, since every request reaching it would get the server blocked.
Outside the session, they are the last stored prices, from redis, or postgres when the cache is cold.

The market is open inside the trading hours in the [configuration](#configuration),
and, with `EGX_MARKET_USE_LIVE_STATUS` on, only when EGX says so too, which it is asked once a trading day,
at the first check of the session. Its answer holds until midnight, so holidays count as closed,
and outside the trading hours, EGX is never asked at all. `/egx/market/status` is answered the same way.

> EGX can lag the bell, so if it says closed at the open, it is asked again every `EGX_MARKET_STATUS_RETRY_SECONDS`
> for `EGX_MARKET_STATUS_RETRY_MINUTES`, then the day counts as a holiday. If it cannot be reached, the trading hours decide.
> A session suspended midday is not seen, the day stays open until the close

`/egx/stocks/{isin}/history` is always served from storage,
since EGX has no intraday history to fetch live, and takes a `period`:

| Period | Interval | Source |
| --- | --- | --- |
| `1d`, `3d`, `5d` | `1m` | The quotes of the last 1, 3, or 5 trading sessions |
| `1w` | `1m` | The quotes of the last week |
| `1m`, `2m`, `3m`, `6m` | `1d` | The daily closes of the last 1 to 6 months |
| `1y`, `2y`, `3y`, `5y` | `1d` | The daily closes of the last 1 to 5 years |

```json
{
    "isin": "EGS60121C018",
    "period": "1m",
    "interval": "1d",
    "points": [
        {"timestamp": "2026-09-23T11:30:00Z", "price": 128.1, "volume": 5462562}
    ]
}
```

A daily point also has the day's `open`, `high`, and `low`, for a candle, stored by the sync since they were added,
the days before, backfilled from EGX's history, have the close only, and those are `null`.
An intraday point is a single price, it has none of them.

> A daily close is stamped with the session's closing time.
> Periods are counted back from the latest stored point, so a weekend does not empty them

### News

`/egx/news`, `/egx/news/{news_id}`, and `/egx/stocks/{isin}/news` are served from storage,
which the [news sync](#jobs-1) keeps up to date, and the [backfill](#jobs-1) fills with the past 5 years.
Until anything is stored, and with `EGX_NEWS_SERVE_FROM_STORAGE` off, they are fetched from EGX instead.

A stored search filters by section, by date, as a day in Cairo, and by text,
in the heading, the content, and the company, in english and arabic.
It also takes an `isin`, a company's news, and `has_attachments`, the news linking a pdf,
which only the stored news has. Without storage, those two are refused with `UNSUPPORTED`,
rather than answered without them, as if they had applied.

> A text search reads a trigram index, over one column postgres keeps of every text of an item,
> and the attachments filter a column it keeps of whether it links a pdf, so neither reads every item.
> The index needs the `pg_trgm` extension, which the migrations create, it ships with postgres, and the database's owner may create it
A stock's news is filtered by its isin, which EGX has no filter for,
so from EGX it is a search for its reuters code over the last year, `COMI.CA`.

> From EGX, a search takes seconds, so it is served from the cache for up to `REDIS_NEWS_CACHE_SECONDS`,
> and once it is older than `REDIS_NEWS_FRESH_SECONDS`, it is refreshed in the background,
> so a request never waits on EGX while there is a copy. A single item is cached for `REDIS_NEWS_ITEM_CACHE_SECONDS`

> Financial statements are always fetched from EGX, the sync leaves their section out

### News Summaries

A news item with a pdf attached is summarized by [Gemini](https://aistudio.google.com), from the pdf,
in english and arabic, with its key points. `/egx/news/{news_id}` carries it as `summary`, `null` until there is one,
and a search does not, to keep the pages light:

```json
{
    "code": 295244,
    "heading": "Release from El Ahram Co. For Printing And Packing (EPPK.CA) Concerning a Lawsuit",
    "summary": {
        "summary": "The Alexandria Economic Court adjourned lawsuit no. 23 for 2026 to 20/10/2026.",
        "summary_ar": "أجلت محكمة الإسكندرية الاقتصادية الدعوى رقم 23 لسنة 2026 لجلسة 20/10/2026.",
        "key_points": ["Lawsuit no. 23 for 2026 was adjourned to 20/10/2026."],
        "key_points_ar": ["تأجيل الدعوى رقم 23 لسنة 2026 لجلسة 20/10/2026."],
        "model": "gemini-3.5-flash-lite",
        "read_attachments": true,
        "created_at": "2026-09-29T13:52:10Z"
    }
}
```

The [summaries job](#jobs-1) makes them, a request never asks Gemini, so a request never waits on it or spends its quota.
Gemini reads the pdf with its url context tool, and a summary is only kept when it did,
since one of the heading alone would be worse than none. EGX's bot check keeps some pdfs from it,
those fail, and are tried again on later runs, `EGX_NEWS_SUMMARIZE_MAX_ATTEMPTS` times at most,
after the ones never tried. A failure's reason is stored with it, in `egx_news_summaries.error`.

The job keeps to Gemini's quotas, which are per project, and a spent one is refused until it resets:

1. One request every `EGX_NEWS_SUMMARIZE_PAUSE_SECONDS`, 4 a minute, under the free tier's 5
1. At most `GEMINI_REQUESTS_PER_DAY` a day, counted in redis, a request counts whatever comes of it, as Gemini counts it
1. A single run at a time, a lock in redis, so a slow run and the next do not ask twice as fast
1. A rate limit or an outage stops the run, and pauses the job for as long as Gemini asks, `GEMINI_BUSY_PAUSE_SECONDS` at least,
    twice as long with each busy answer in a row, up to `GEMINI_LONGEST_PAUSE_SECONDS`. None of it spends an item's attempts
1. A spent daily quota pauses it until the quotas reset, at midnight in `GEMINI_QUOTA_TIMEZONE`

> Without `GEMINI_API_KEY`, the job skips, and every item's `summary` stays `null`.
> The key is a secret, keep it in `.env`, which git ignores, the compose file only passes it on

### Performance

`/egx/stocks/performance` and `/egx/indices/performance` take a `period`,
`1w`, `1m`, `3m`, `6m`, `ytd`, or `1y`, counted back from the latest stored session,
and return each one's base, the last close by the period's start, or its first since when it was listed after it.
A change over the period is the live price against the base, so a client keeps it live without asking again.

A stock also has what it traded since the start, up to the latest session stored, and that session's own,
for a live quote of a newer one. The value is estimated, each day's volume at its close,
since EGX's history has no value traded. The bases only move once a day, so both are cached for `REDIS_CACHE_TTL_SECONDS`.

### Indices

`/egx/indices` and `/egx/indices/{index}/history` are served from storage,
which the [index sync](#jobs-1) fills every few minutes of the session, and the [backfill](#jobs-1) since each index's inception.
An index is named by EGX's own code, so EGX30 is `CASE30`, and each one comes with a `title` to show.

`/egx/indices/{index}/history` takes the same `period` as a stock's history,
the stored points for up to a week, and the daily closes past that.

`/egx/indices/{index}/summary` and `/egx/indices/{index}/weights` are fetched from EGX on request,
and served from the cache while they are refreshed in the background, as a news search is.
EGX30 USD has EGX30's members, so it gets EGX30's summary, which EGX has none of for it.

> EGX publishes a point every few minutes of the session, so the sync asks for them every `EGX_INDICES_SYNC_EVERY_MINUTES`,
> one index every `EGX_INDICES_SYNC_PAUSE_SECONDS`. EGX30 USD has no points, only its daily level

### Errors

Errors share a single shape:

```json
{
    "error": {
        "type": "EXCHANGE_TIMEOUT",
        "message": "EGX took too long to respond"
    }
}
```

| Status | Type | When |
| --- | --- | --- |
| `400` | `UNSUPPORTED` | A filter only the stored data has, asked for while it is not served from storage |
| `404` | `NOT_FOUND` | The requested item does not exist |
| `429` | `RATE_LIMITED` | Too many requests from the client's ip, see [rate limiting](#rate-limiting) |
| `502` | `EXCHANGE_ERROR` | The exchange responded with an error or with something unusable |
| `503` | `EXCHANGE_UNAVAILABLE` | The exchange could not be reached |
| `503` | `EXCHANGE_BLOCKED` | The exchange's firewall is rejecting the server's requests |
| `504` | `EXCHANGE_TIMEOUT` | The exchange did not respond in time |

> Invalid parameters return FastAPI's default `422` validation response

### Rate Limiting

Every request is limited per client ip, 120 requests a minute by default,
over a sliding window, so there is no window boundary to burst across.

Each client's requests are timestamps in a redis sorted set, shared by every replica.
A request drops the timestamps older than the window, adds its own, and counts the rest,
all in a single transaction. Rejected requests count too, so a client that keeps hammering stays limited,
and the set is trimmed to just past the limit, so a flood does not grow it.

Every response carries the client's quota, and a limited one says when to retry:

```
RateLimit-Limit: 120
RateLimit-Remaining: 0
RateLimit-Reset: 42
Retry-After: 42
```

The client ip is read from cloudflare's `CF-Connecting-IP` header,
and from the peer address when a request comes without it, like a docker health probe.
IPv6 clients are counted by their `/64`, which is what a single user is usually handed.

> The header is trusted as is, which is only safe while the origin is reachable through cloudflare alone,
> like behind a zero trust tunnel with no open ports. Cloudflare overwrites the header on every request,
> but anyone reaching the origin directly could send their own, to dodge the limit or fake their ip in the logs

> The health probes are never limited, a path is exempted by adding it to `UNLIMITED_PREFIXES`,
> and requests go through when redis is down,
> or does not answer within `RATE_LIMIT_TIMEOUT_SECONDS`

### Jobs

Jobs are run once by name through `bin/jobs.sh`, each with its own flags, `bin/jobs.sh <job> --help` lists them:

| Job | Cron | Description |
| --- | --- | --- |
| `sync_stock_prices` | `* * * * *` | Stores a quote per stock, every run, and refreshes the cached stocks. It skips outside the trading hours, unless `--force` is passed |
| `prune_stock_quotes` | `0 0 * * *` | Drops the quotes older than `EGX_MARKET_QUOTE_RETENTION_DAYS`, the daily closes keep the long history |
| `backfill_stock_prices` | fired by hand | Stores every stock's daily closes, 5 years back by default. Takes `--days`, `--isin`, `--missing-only`, and `--concurrency` and `--pause` for its pace, one stock every 3 seconds by default |
| `sync_news` | `* * * * *` | Stores the latest news, when due, every `EGX_NEWS_SYNC_SESSION_MINUTES` in the session and `EGX_NEWS_SYNC_OFF_SESSION_MINUTES` outside, `EGX_NEWS_SYNC_DELAY_SECONDS` after the price sync. It pages back until it reaches stored news, or takes a single page while nothing is stored. Takes `--force` and `--delay` |
| `sync_indices` | `* * * * *` | Stores every index's level and its session's points, every `EGX_INDICES_SYNC_EVERY_MINUTES` while the market is open, `EGX_INDICES_SYNC_DELAY_SECONDS` into the minute, after the other syncs. Drops the points older than `EGX_INDICES_POINT_RETENTION_DAYS`. Takes `--force` and `--delay` |
| `backfill_indices` | fired by hand | Stores every index's daily history since its inception, a page of 250 every 3 seconds. Takes `--index`, `--missing-only`, and `--pause` |
| `backfill_news` | fired by hand | Stores the news of the last 5 years, a page of 250 every 3 seconds by default. Takes `--days`, `--pause`, and `--from-page` to resume |
| `summarize_news` | `*/5 * * * *` | Summarizes the stored news with a pdf that has no summary yet, the newest first, `EGX_NEWS_SUMMARIZE_BATCH_SIZE` a run, keeping to Gemini's [quotas](#news-summaries). It skips without `GEMINI_API_KEY`. Takes `--limit` and `--pause` |

In production, each job with a cron is a schedule in dokploy, running its command in the api's container.
Locally, nothing is scheduled, so your own ip does not poll EGX all day.

#### Scheduling in Dokploy

In the api's application, open **Schedules**, and create one per job, with the `sh` shell,
the api's container runs them, in `/app`, with the api's environment:

| Name | Cron | Command | Enabled |
| --- | --- | --- | --- |
| `sync_stock_prices` | `* * * * *` | `/app/bin/jobs.sh sync_stock_prices` | Yes |
| `sync_news` | `* * * * *` | `/app/bin/jobs.sh sync_news` | Yes |
| `sync_indices` | `* * * * *` | `/app/bin/jobs.sh sync_indices` | Yes |
| `summarize_news` | `*/5 * * * *` | `/app/bin/jobs.sh summarize_news` | Yes, once `GEMINI_API_KEY` is set, it only skips without it |
| `prune_stock_quotes` | `0 0 * * *` | `/app/bin/jobs.sh prune_stock_quotes` | Yes |
| `backfill_stock_prices` | `0 0 1 1 *` | `/app/bin/jobs.sh backfill_stock_prices` | No, run by hand |
| `backfill_news` | `0 0 1 1 *` | `/app/bin/jobs.sh backfill_news` | No, run by hand |
| `backfill_indices` | `0 0 1 1 *` | `/app/bin/jobs.sh backfill_indices` | No, run by hand |

Every minute is on purpose, the jobs decide for themselves whether they are due:

- `sync_stock_prices` skips outside the trading hours, and on the days EGX says it is closed
- `sync_news` runs every `EGX_NEWS_SYNC_SESSION_MINUTES` in the session and `EGX_NEWS_SYNC_OFF_SESSION_MINUTES` outside,
    `EGX_NEWS_SYNC_DELAY_SECONDS` into the minute, so it does not ask EGX along with the price sync
- `sync_indices` runs every `EGX_INDICES_SYNC_EVERY_MINUTES` while the market is open, `EGX_INDICES_SYNC_DELAY_SECONDS` into the minute
- `summarize_news` skips while Gemini is paused, while another run is going, and without `GEMINI_API_KEY`

So the schedules need no timezone, the trading hours are counted in `EGX_MARKET_TIMEZONE`, and Gemini's day in `GEMINI_QUOTA_TIMEZONE`,
only `prune_stock_quotes` follows the server's clock, and any hour does for it.

> Keep the cron of the syncs at every minute, a slower one skips the minutes they are due at.
> The flags are left at their defaults, the settings are where their pace is tuned

The backfills are schedules too, disabled, so each is a click on **Run** in dokploy rather than a command to remember,
their cron is never reached while they are off. Run them once, after the first deploy,
and again if one is stopped, from the container's **Terminal**, with `--missing-only`, or `--from-page` for the news.

> Run them one at a time, outside the session, EGX's firewall blocks bursts,
> and the syncs keep asking it every minute during the session

Every run logs `[Jobs] Job Started` and `[Jobs] Job Finished` with its `duration_ms`, or `[Jobs] Job Failed` with the error,
and every line of a run carries its `job`. A run that fails exits with an error, so the cron that started it knows.

With error tracking on, each job with a cron also checks in with a [sentry cron monitor](https://docs.sentry.io/product/crons/),
`jobs-sync-stock-prices`, `jobs-prune-stock-quotes`, `jobs-sync-news`, `jobs-sync-indices`, and `jobs-summarize-news`, so sentry alerts when a run fails,
and when the cron stops running it at all.

Run a job by hand when you need one:

```shell
docker compose run --rm --entrypoint /app/bin/jobs.sh openmarkets-api sync_stock_prices --force
```

The backfills are fired manually, once after the first setup:

```shell
docker compose run --rm --entrypoint /app/bin/jobs.sh openmarkets-api backfill_stock_prices
docker compose run --rm --entrypoint /app/bin/jobs.sh openmarkets-api backfill_news
docker compose run --rm --entrypoint /app/bin/jobs.sh openmarkets-api backfill_indices
```

> The news backfill logs `[News] Backfilled A Page` with the `page` it reached, so one that stopped,
> when EGX blocked it, is resumed with `--from-page`

> EGX's firewall rejects bursts of requests, so the backfill asks for one stock every few seconds
> and retries a failed one. Once the firewall rejects it, the backfill stops right away, since every further request
> keeps the block going, and it is logged as `[Stock Prices] Backfill Stopped`. Rerun it with `--missing-only`
> once the block lifts, after the session, when the sync is not asking EGX every minute too

To try a faster pace, raise it a little at a time, and fall back if it gets blocked:

```shell
docker compose run --rm --entrypoint /app/bin/jobs.sh openmarkets-api backfill_stock_prices --missing-only --concurrency 2 --pause 2
```

### Configuration

Settings are read from the environment, or from a `.env` file,
with every one of them listed in [`.env.example`](.env.example):

| Variable | Default | Description |
| --- | --- | --- |
| `DATABASE_HOST`, `DATABASE_PORT`, `DATABASE_USER`, `DATABASE_PASSWORD`, `DATABASE_NAME` | port `5432`, the rest required | The postgres connection |
| `REDIS_HOST`, `REDIS_PORT`, `REDIS_DB`, `REDIS_PASSWORD` | `localhost`, `6379`, `0`, none | The redis connection |
| `REDIS_CACHE_TTL_SECONDS` | `300` | How long cached prices and histories live |
| `REDIS_LIVE_CACHE_SECONDS` | `30` | How long what is fetched from EGX on request, like the gold board, is reused |
| `REDIS_NEWS_CACHE_SECONDS` | `300` | How long a news or financial statements search may be served from the cache |
| `REDIS_NEWS_FRESH_SECONDS` | `30` | How old a cached search gets before it is refreshed in the background |
| `REDIS_NEWS_ITEM_CACHE_SECONDS` | `3600` | How long a single news item is reused |
| `EGX_MARKET_TIMEZONE` | `Africa/Cairo` | The timezone the trading hours are in |
| `EGX_MARKET_OPEN_TIME`, `EGX_MARKET_CLOSE_TIME` | `10:00`, `14:30` | The trading hours |
| `EGX_MARKET_TRADING_DAYS` | `[6, 0, 1, 2, 3]` | The trading days, as python weekdays, monday is `0` |
| `EGX_MARKET_SYNC_GRACE_MINUTES` | `30` | How long the sync keeps going after the close |
| `EGX_MARKET_USE_LIVE_STATUS` | `true` | Also ask EGX whether it is open, once a trading day, so holidays count as closed |
| `EGX_MARKET_STATUS_RETRY_MINUTES`, `EGX_MARKET_STATUS_RETRY_SECONDS` | `15`, `60` | How long, and how often, EGX is asked again when it says closed at the open |
| `EGX_MARKET_LIVE_PRICES_CACHE_SECONDS` | `10` | How long a live fetch of prices is shared by requests during the session |
| `EGX_MARKET_QUOTE_RETENTION_DAYS` | `30` | How long the minute quotes are kept |
| `EGX_MARKET_REQUEST_TIMEOUT_SECONDS` | `10` | How long a request to EGX may take |
| `EGX_NEWS_SERVE_FROM_STORAGE` | `true` | Serve news from storage, once anything is stored, or always from EGX |
| `EGX_NEWS_SYNC_SESSION_MINUTES`, `EGX_NEWS_SYNC_OFF_SESSION_MINUTES` | `2`, `15` | How often the news sync runs, in the session and outside it |
| `EGX_NEWS_SYNC_DELAY_SECONDS` | `20` | How long the news sync waits, so it does not ask EGX in the same second as the price sync |
| `EGX_NEWS_SYNC_PAGE_SIZE`, `EGX_NEWS_SYNC_MAX_PAGES` | `50`, `10` | How much news the sync asks for at a time, and how far back it pages |
| `EGX_NEWS_SYNC_PAUSE_SECONDS` | `3` | How long the sync waits between pages |
| `EGX_NEWS_SUMMARIZE_BATCH_SIZE` | `10` | How many items the summaries job takes a run |
| `EGX_NEWS_SUMMARIZE_PAUSE_SECONDS` | `15` | How long it waits between items, a bit over 60 divided by the tier's requests a minute |
| `EGX_NEWS_SUMMARIZE_MAX_ATTEMPTS` | `3` | How many times an item that failed is tried |
| `EGX_INDICES_SYNC_EVERY_MINUTES` | `5` | How often the index sync runs while the market is open |
| `EGX_INDICES_SYNC_DELAY_SECONDS` | `40` | How long the index sync waits, so it does not ask EGX along with the other syncs |
| `EGX_INDICES_SYNC_PAUSE_SECONDS` | `3` | How long the index sync waits between indices |
| `EGX_INDICES_POINT_RETENTION_DAYS` | `30` | How long an index's points are kept, the daily closes keep the long history |
| `EGX_INDICES_LEVELS_CACHE_SECONDS` | `60` | How long the latest levels are cached |
| `EGX_INDICES_SUMMARY_CACHE_SECONDS`, `EGX_INDICES_SUMMARY_FRESH_SECONDS` | `900`, `120` | How long an index's summary may be served from the cache, and how old it gets before it is refreshed |
| `EGX_INDICES_WEIGHTS_CACHE_SECONDS`, `EGX_INDICES_WEIGHTS_FRESH_SECONDS` | `86400`, `3600` | The same, for the EGX30 weights |
| `GEMINI_API_KEY` | none | The Gemini key, from [Google AI Studio](https://aistudio.google.com), the summaries are off without it |
| `GEMINI_MODEL` | `gemini-3.5-flash-lite` | The model that summarizes |
| `GEMINI_BASE_URL`, `GEMINI_API_REVISION` | `https://generativelanguage.googleapis.com/v1beta`, `2026-05-20` | The Gemini api and the revision of it asked for |
| `GEMINI_TIMEOUT_SECONDS` | `90` | How long a summary may take |
| `GEMINI_REQUESTS_PER_DAY` | `100` | How many requests the job makes a day at most, keep it under the tier's, AI Studio shows them |
| `GEMINI_QUOTA_TIMEZONE` | `America/Los_Angeles` | Where the daily quotas reset at midnight |
| `GEMINI_BUSY_PAUSE_SECONDS`, `GEMINI_LONGEST_PAUSE_SECONDS` | `60`, `3600` | How long a rate limit pauses the job at least, and at most as it doubles |
| `APP_ENVIRONMENT` | `DEV` | `DEV` or `PROD` |
| `APP_HOST`, `APP_PORT` | `0.0.0.0`, `8080` | The address the API listens on |
| `APP_LOOP`, `APP_HTTP` | `uvloop`, `httptools` | The event loop and the http parser uvicorn runs with |
| `APP_WORKERS` | `1` | How many API processes run in the container, ignored with `--dev` |
| `APP_VERSION` | the commit the image is built from | The release reported to error tracking |
| `APP_LOG_LEVEL` | `INFO` | The lowest level that is logged |
| `APP_LOG_JSON` | `true` | JSON logs, or readable ones with `false` |
| `FORWARDED_ALLOW_IPS` | `127.0.0.1` | The proxies uvicorn trusts with forwarded headers, read by uvicorn itself |
| `ERROR_TRACKING_DSN` | none | The sentry dsn, error tracking and the job monitors are off without it |
| `ERROR_TRACKING_TRACES_SAMPLE_RATE` | `0.1` | The share of requests traced, the health probes never are |
| `ERROR_TRACKING_LOGS_ENABLED` | `true` | Also send the logs, `INFO` and up, to error tracking, with their fields as attributes |
| `RATE_LIMIT_ENABLED` | `true` | Whether requests are limited per client ip |
| `RATE_LIMIT_REQUESTS`, `RATE_LIMIT_WINDOW_SECONDS` | `120`, `60` | How many requests a client makes per sliding window |
| `RATE_LIMIT_TIMEOUT_SECONDS` | `0.5` | How long to wait on redis before letting the request through |
| `RATE_LIMIT_CLIENT_IP_HEADER` | `CF-Connecting-IP` | The header the real client ip is read from |
| `CORS_ORIGINS` | none | The web origins allowed to call the API from a browser, as a json list |
| `CORS_MAX_AGE_SECONDS` | `600` | How long a browser may reuse a preflight answer |

### Logging

Everything is logged through [loguru](https://github.com/Delgan/loguru),
including uvicorn's and the other libraries' logs.
The message is a plain string, `[Area] Title Case`, with ` - ` before a reason,
and anything else goes in as keyword arguments, one per line:

```python
from src.providers import logger

logger.info(
    "[Stock Prices] Synced",
    stocks=220,
    new_quotes=219,
)
```

Every request is logged once, as `[API Access Request] ...`, with its `method`, `path`, `status_code`, and `duration_ms`,
in place of uvicorn's access log, which is turned off.

Every line of a request carries its context:

| Field | Source |
| --- | --- |
| `correlation_id` | The `x-correlation-id` header, or generated, and sent back in the response |
| `client_ip` | The ip the API resolved, the one [rate limiting](#rate-limiting) counts |
| `cf_connecting_ip` | Cloudflare's `CF-Connecting-IP`, the client as its edge saw it |
| `real_ip` | Traefik's `X-Real-Ip`, the hop right before it |
| `forwarded_for` | The `X-Forwarded-For` chain of hops |

> Health probes are logged at debug, so they do not drown out everything else

## Setup

### Prerequisites

The SDK lives in a private repo, so you need read access to
[openmarkets-sdk](https://github.com/abdelrahman0w/openmarkets-sdk) to install the dependencies.

> Without it, `uv sync` fails to fetch the SDK

### Using Docker

1. Export a GitHub token with read access to the SDK repo

    ```shell
    export GH_TOKEN=$(gh auth token)
    ```

    > Or use a [fine-grained token](https://github.com/settings/personal-access-tokens) with read-only access to the repo contents
1. To summarize the news, put a [Gemini key](https://aistudio.google.com) in a `.env` file, which git ignores

    ```shell
    echo "GEMINI_API_KEY=your-key" >> .env
    ```

    > Without it, everything else runs, and the news has no summaries
1. Build and run the services

    ```shell
    docker compose up --build
    ```

This runs the API along with PostgreSQL and Redis.
After running the services, the API will be run locally on port `8080`.
Access it using the following URL: [http://127.0.0.1:8080](http://127.0.0.1:8080)

To build the image alone:

```shell
docker build --secret id=gh_token,env=GH_TOKEN -t openmarkets-api .
```

> Pass `--build-arg INSTALL_DEV=true` to include the development dependencies

### Manually

1. Install [uv](https://docs.astral.sh/uv/getting-started/installation/) if not installed
1. Make sure git can authenticate with GitHub

    ```shell
    gh auth setup-git
    ```

    > Or any other git credential helper, uv uses git under the hood to fetch the SDK
1. Clone [this repo](https://github.com/abdelrahman0w/openmarkets-api)

    ```shell
    git clone https://github.com/abdelrahman0w/openmarkets-api
    ```
1. Navigate to the repo directory

    ```shell
    cd openmarkets-api
    ```
1. Install the dependencies

    ```shell
    uv sync --locked
    ```
1. Copy the example env file, and adjust it if needed

    ```shell
    cp .env.example .env
    ```
1. Install the pre-commit hooks

    ```shell
    uvx pre-commit install
    ```

## Testing

Each layer is tested where its behaviour shows best:

| Layer | Tested Through |
| --- | --- |
| `routes`, `controllers` | `tests/test_routes`, http requests against the app, with EGX mocked |
| `actions` | `tests/test_actions`, caching, market hours, syncs and backfills |
| `repositories` | `tests/test_repositories`, the queries against a real postgres |
| `services`, `providers`, `utils`, `structs`, `jobs` | Their own folder, directly |

> Every database test runs inside a transaction that is rolled back, so nothing is left behind

### Manually

1. Install the dependencies, if not installed

    ```shell
    uv sync --locked
    ```
1. Start postgres and redis, for the tests that need a database

    ```shell
    docker compose up -d openmarkets-db openmarkets-redis
    ```

    > Without postgres, those tests are skipped and the rest still run
1. Run the tests

    ```shell
    uv run pytest
    ```

To lint and format:

```shell
uv run ruff check . && uv run ruff format --check .
```

### Using Docker

To run the tests in the same environment the API runs in:

```shell
docker compose run --rm --entrypoint python openmarkets-api -m pytest
```
