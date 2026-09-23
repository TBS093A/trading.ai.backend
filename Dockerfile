# Trading AI Backend - obraz z zapietymi wersjami (tox.ini deps sa juz pinned).
# Zastepuje runtime git-clone + pip install tox robione w initContainerach przy
# kazdym restarcie poda (patrz kubernetes/apps/trading-ai-backend/README.md w cloud.config,
# punkt 4 listy bezpieczenstwa po incydencie 503 - unpinned uvicorn/websockets).
#
# Jeden obraz, trzy tryby uruchomienia wybierane przez SERVICE_MODE w runtime
# (sync-controller / rest-api-controller / rest-api-celery-worker) - wszystkie
# trzy tox environments maja identyczny zestaw `deps`, wiec nie ma sensu budowac
# trzech osobnych obrazow.

FROM python:3.13.1-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir tox==4.30.3

WORKDIR /app
COPY . /app

# Buduje wszystkie trzy tox venvy PODCZAS builda obrazu (deps pinned w tox.ini
# `deps =`), nie przy starcie poda. To jest sedno tej zmiany.
RUN tox --notest -e sync-controller,rest-api-controller,rest-api-celery-worker

COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh \
    && groupadd -g 1000 appgroup \
    && useradd -u 1000 -g 1000 -m appuser \
    && chown -R 1000:1000 /app

USER 1000:1000

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
