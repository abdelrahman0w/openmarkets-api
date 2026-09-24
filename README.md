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
  - [Setup](#setup)
    - [Prerequisites](#prerequisites)
    - [Using Docker](#using-docker)
    - [Manually](#manually)
  - [Testing](#testing)
    - [Using Docker](#using-docker-1)
    - [Manually](#manually-1)

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

> This is the target layout, most of it is not there yet

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
│   ├── dependencies.py             db session, redis, egx service, pagination
│   ├── routes/                     path, params, status, response model
│   │   ├── health.py               liveness and readiness
│   │   └── egx/
│   ├── controllers/                use cases, called by routes only
│   │   └── egx/
│   ├── actions/                    reusable units, called by controllers, jobs, and events
│   │   └── egx/
│   ├── repositories/               queries only
│   │   ├── utils.py                ordering and pagination
│   │   └── egx/
│   ├── jobs/
│   │   └── main.py                 job name to action mapping
│   ├── services/                   external systems
│   │   └── egx/
│   │       └── client.py           the sdk client lifecycle and error mapping
│   ├── providers/                  stateful infra, opened in the lifespan
│   │   ├── db.py                   async engine and session maker
│   │   ├── redis.py
│   │   └── logger.py
│   ├── middlewares/
│   ├── utils/                      pure helpers
│   ├── structs/
│   │   ├── enums/
│   │   ├── models/                 pydantic models
│   │   │   ├── common.py           the shared base model and pagination envelope
│   │   │   ├── requests/           what comes in
│   │   │   └── responses/          what goes out
│   │   └── tables/                 sqlalchemy tables
│   │       ├── base.py             declarative base, metadata, timestamps
│   │       └── egx/
│   └── exceptions/
│       ├── custom_exceptions.py
│       └── exception_handlers.py   exceptions to http errors, registered once
└── tests/                          mirrors src
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
- **The SDK is only imported by `services`.** So a change in the SDK
    is a change in one place.
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
1. The controller checks redis first, and returns the cached data if it is there
1. Otherwise, it reads the data from postgres through a repository
1. Only if the data is not stored, it fetches it from the exchange through the egx service,
    stores it, and caches it
1. The controller returns a response model, which the route serializes

```
client → middlewares → route → controller → redis          (hit → return)
                                          → repository     (miss → postgres)
                                          → service        (not stored → exchange)
       ← response model ← route ← controller
```

Any exception raised along the way is caught by `exception_handlers.py`
and returned as an http error, so no layer below the routes has to know about http.

### Jobs

Jobs keep the stored data fresh, so most requests never have to wait on the exchange.

1. `bin/jobs.sh <job>` runs `jobs/main.py` with the job name
1. The job opens the providers it needs, since jobs do not run through the api lifespan
1. It calls its action, which fetches from the exchange through the egx service
1. The action upserts the data through a repository in a single transaction, then refreshes the cache

```
bin/jobs.sh sync_market_watch → jobs/main.py → action → service    (exchange)
                                                      → repository (postgres)
                                                      → redis      (cache)
```

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

### Using Docker

```shell
docker compose run --rm --entrypoint python openmarkets-api -m pytest
```

Afterwards, the tests would run and show the results in the current terminal window.

### Manually

1. Install the dependencies, if not installed

    ```shell
    uv sync --locked
    ```
1. Run the tests

    ```shell
    uv run pytest
    ```

To lint and format:

```shell
uv run ruff check . && uv run ruff format --check .
```
