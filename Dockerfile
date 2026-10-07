# Trading AI Backend - obraz z zapietymi wersjami (tox.ini deps sa juz pinned).
# Zastepuje runtime git-clone + pip install tox robione w initContainerach przy
# kazdym restarcie poda (patrz kubernetes/apps/trading-ai-backend/README.md w cloud.config,
# punkt 4 listy bezpieczenstwa po incydencie 503 - unpinned uvicorn/websockets).
#
# Jeden obraz, trzy tryby uruchomienia wybierane przez SERVICE_MODE w runtime
# (sync-controller / rest-api-controller / rest-api-celery-worker) - wszystkie
# trzy tox environments maja identyczny zestaw `deps`, wiec nie ma sensu budowac
# trzech osobnych obrazow.

# 3.13-slim (nie 3.13.1-slim): tag przypiety do patcha nigdy nie dostaje poprawek Debiana -
# 3.13.1-slim mial 9 CRITICAL w Trivy. Niezmienny jest obraz wynikowy (tag = commit SHA),
# nie obraz bazowy. apt-get upgrade dociaga poprawki wydane po zbudowaniu obrazu bazowego.
#
# Multi-stage: build-essential (gcc, linux-libc-dev, ...) jest potrzebny tylko do skompilowania
# paczek bez wheeli. W obrazie wynikowym go nie ma - to bylo zrodlo CRITICAL bez poprawki
# (linux-libc-dev) i ~100 HIGH z pakietow systemowych w Trivy image. Oba etapy uzywaja tego
# samego obrazu bazowego, wiec skopiowane venvy (/app/.tox) wskazuja na ten sam interpreter.
FROM python:3.13-slim AS build

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir tox==4.30.3

WORKDIR /app
COPY . /app

# Buduje wszystkie trzy tox venvy PODCZAS builda obrazu (deps pinned w tox.ini
# `deps =`), nie przy starcie poda.
RUN tox --notest -e sync-controller,rest-api-controller,rest-api-celery-worker


FROM python:3.13-slim

RUN apt-get update \
    && apt-get upgrade -y \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir tox==4.30.3

COPY --from=build --chown=1000:1000 /app /app
WORKDIR /app

# Rozszerzenia skompilowane w etapie build moga linkowac biblioteki, ktorych slim nie ma -
# lepiej, zeby wywalil sie build niz pod na produkcji.
RUN missing=$(find /app/.tox -name '*.so*' -type f -exec ldd {} + 2>/dev/null | grep 'not found' | sort -u); \
    if [ -n "$missing" ]; then echo "brakujace biblioteki w runtime:"; echo "$missing"; exit 1; fi

COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh \
    && groupadd -g 1000 appgroup \
    && useradd -u 1000 -g 1000 -m appuser

USER 1000:1000

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
