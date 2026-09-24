# python version
ARG PYTHON_VERSION=3.14-slim

# build stage
FROM python:${PYTHON_VERSION} AS builder

# install uv
COPY --from=ghcr.io/astral-sh/uv:0.12.18 /uv /bin
COPY --from=ghcr.io/astral-sh/uv:0.12.18 /uvx /bin

# uv environment variables
ENV UV_COMPILE_BYTECODE=1 \
    UV_PROJECT_ENVIRONMENT="/usr/local/"

# set working directory
WORKDIR /app

# copy pyproject.toml and uv.lock* if not in the repo
COPY ./pyproject.toml .
COPY ./uv.lock* .

# allow installing dev dependencies
ARG INSTALL_DEV=false

# install dependencies
RUN if [ "$INSTALL_DEV" = "true" ]; \
    then uv sync --no-progress --locked --all-extras --all-groups; \
    else uv sync --no-progress --locked --all-extras --no-default-groups; \
    fi

# runtime stage
FROM python:${PYTHON_VERSION} AS runtime

# set environment variables
ENV NON_ROOT_USER=runtime \
    PYTHONUNBUFFERED=1

# create a non-root user
RUN groupadd -r ${NON_ROOT_USER} && \
    useradd --no-log-init -r -g ${NON_ROOT_USER} ${NON_ROOT_USER}

# copy needed binaries
COPY --from=builder \
    /usr/local/bin \
    /usr/local/bin

# copy installed dependencies
COPY --from=builder \
    /usr/local/lib/python${PYTHON_VERSION%.*}/site-packages \
    /usr/local/lib/python${PYTHON_VERSION%.*}/site-packages

# set working directory
WORKDIR /app

# copy app files
COPY bin ./bin
COPY src ./src
COPY migrations ./migrations
COPY alembic.ini .

# remove compiled python files and __pycache__ directories
RUN find . -name '*.pyc' -exec rm -f {} + && \
    find . -name '*.pyo' -exec rm -f {} + && \
    find . -name '__pycache__' -exec rm -rf {} +

# use the non-root user
USER ${NON_ROOT_USER}:${NON_ROOT_USER}

# start the app
ENTRYPOINT [ "/app/bin/entrypoint.sh" ]
