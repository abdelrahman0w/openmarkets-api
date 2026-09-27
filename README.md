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
│   │   └── egx/
│   │       └── client.py           the sdk client lifecycle and error mapping
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
Endpoints without stored data, like news or the gold board, are fetched from the exchange
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
| `GET` | `/egx/news` | Disclosures and announcements, filtered by section, text, or date |
| `GET` | `/egx/news/financial-statements` | Financial statement filings, with their figures parsed out |
| `GET` | `/egx/news/{news_id}` | A single news item by its id |
| `GET` | `/egx/stocks` | Every listed stock, with its details and latest quote |
| `GET` | `/egx/stocks/{isin}` | A single stock, with its details and latest quote |
| `GET` | `/egx/stocks/{isin}/history` | A stock's price history, over a `period` |

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

> A daily close is stamped with the session's closing time.
> Periods are counted back from the latest stored point, so a weekend does not empty them

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
| `404` | `NOT_FOUND` | The requested item does not exist |
| `429` | `RATE_LIMITED` | Too many requests from the client's ip, see [rate limiting](#rate-limiting) |
| `502` | `EXCHANGE_ERROR` | The exchange responded with an error or with something unusable |
| `503` | `EXCHANGE_UNAVAILABLE` | The exchange could not be reached |
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
| `backfill_stock_prices` | fired by hand | Stores every stock's daily closes, 5 years back by default. Takes `--days`, `--isin`, and `--missing-only` |

In production, each job with a cron is a schedule in dokploy, running its command in the api's container.
Locally, nothing is scheduled, so your own ip does not poll EGX all day.

Every run logs `[Jobs] Job Started` and `[Jobs] Job Finished` with its `duration_ms`, or `[Jobs] Job Failed` with the error,
and every line of a run carries its `job`. A run that fails exits with an error, so the cron that started it knows.

With error tracking on, each job with a cron also checks in with a [sentry cron monitor](https://docs.sentry.io/product/crons/),
`jobs-sync-stock-prices` and `jobs-prune-stock-quotes`, so sentry alerts when a run fails,
and when the cron stops running it at all.

Run a job by hand when you need one:

```shell
docker compose run --rm --entrypoint /app/bin/jobs.sh openmarkets-api sync_stock_prices --force
```

The backfill is fired manually, once after the first setup:

```shell
docker compose run --rm --entrypoint /app/bin/jobs.sh openmarkets-api backfill_stock_prices
```

> EGX's firewall rejects bursts of requests, so the backfill goes a couple of stocks at a time
> and retries a rejected one. Rerun it with `--missing-only` to pick up any that still failed

### Configuration

Settings are read from the environment, or from a `.env` file:

| Variable | Default | Description |
| --- | --- | --- |
| `DATABASE_HOST`, `DATABASE_PORT`, `DATABASE_USER`, `DATABASE_PASSWORD`, `DATABASE_NAME` | port `5432`, the rest required | The postgres connection |
| `REDIS_HOST`, `REDIS_PORT`, `REDIS_DB`, `REDIS_PASSWORD` | `localhost`, `6379`, `0`, none | The redis connection |
| `REDIS_CACHE_TTL_SECONDS` | `300` | How long cached prices and histories live |
| `REDIS_LIVE_CACHE_SECONDS` | `30` | How long what is fetched from EGX on request, like news, is reused |
| `EGX_MARKET_TIMEZONE` | `Africa/Cairo` | The timezone the trading hours are in |
| `EGX_MARKET_OPEN_TIME`, `EGX_MARKET_CLOSE_TIME` | `10:00`, `14:30` | The trading hours |
| `EGX_MARKET_TRADING_DAYS` | `[6, 0, 1, 2, 3]` | The trading days, as python weekdays, monday is `0` |
| `EGX_MARKET_SYNC_GRACE_MINUTES` | `30` | How long the sync keeps going after the close |
| `EGX_MARKET_USE_LIVE_STATUS` | `true` | Also ask EGX whether it is open, once a trading day, so holidays count as closed |
| `EGX_MARKET_STATUS_RETRY_MINUTES`, `EGX_MARKET_STATUS_RETRY_SECONDS` | `15`, `60` | How long, and how often, EGX is asked again when it says closed at the open |
| `EGX_MARKET_LIVE_PRICES_CACHE_SECONDS` | `10` | How long a live fetch of prices is shared by requests during the session |
| `EGX_MARKET_QUOTE_RETENTION_DAYS` | `30` | How long the minute quotes are kept |
| `EGX_MARKET_REQUEST_TIMEOUT_SECONDS` | `10` | How long a request to EGX may take |
| `APP_ENVIRONMENT` | `dev` | `dev` or `prod` |
| `APP_HOST`, `APP_PORT` | `0.0.0.0`, `8080` | The address the API listens on |
| `APP_LOOP`, `APP_HTTP` | `uvloop`, `httptools` | The event loop and the http parser uvicorn runs with |
| `APP_WORKERS` | `1` | How many API processes run in the container, ignored with `--dev` |
| `APP_VERSION` | none | The release reported to error tracking |
| `APP_LOG_LEVEL` | `INFO` | The lowest level that is logged |
| `APP_LOG_JSON` | `true` | JSON logs, or readable ones with `false` |
| `FORWARDED_ALLOW_IPS` | `127.0.0.1` | The proxies uvicorn trusts with forwarded headers, read by uvicorn itself |
| `ERROR_TRACKING_DSN` | none | The sentry dsn, error tracking and the job monitors are off without it |
| `ERROR_TRACKING_TRACES_SAMPLE_RATE` | `0.1` | The share of requests traced, the health probes never are |
| `RATE_LIMIT_ENABLED` | `true` | Whether requests are limited per client ip |
| `RATE_LIMIT_REQUESTS`, `RATE_LIMIT_WINDOW_SECONDS` | `120`, `60` | How many requests a client makes per sliding window |
| `RATE_LIMIT_TIMEOUT_SECONDS` | `0.5` | How long to wait on redis before letting the request through |
| `RATE_LIMIT_CLIENT_IP_HEADER` | `CF-Connecting-IP` | The header the real client ip is read from |

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
