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
