FROM python:3.12-slim-bookworm

ARG CLAWLITE_PIP_EXTRAS="telegram,media,observability"
ARG CLAWLITE_INSTALL_BROWSER=""

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      ca-certificates \
      curl \
      git \
      tini && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY clawlite ./clawlite

RUN python -m pip install --upgrade pip && \
    if [ -n "${CLAWLITE_PIP_EXTRAS}" ]; then \
      python -m pip install ".[${CLAWLITE_PIP_EXTRAS}]"; \
    else \
      python -m pip install .; \
    fi

RUN if [ -n "${CLAWLITE_INSTALL_BROWSER}" ]; then \
      python -m playwright install --with-deps chromium; \
    fi

RUN mkdir -p /root/.clawlite

VOLUME ["/root/.clawlite"]
EXPOSE 8787

ENTRYPOINT ["tini", "--", "clawlite"]
CMD ["status"]

