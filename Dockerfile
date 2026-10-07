# Trading AI Backend - obraz z zapietymi wersjami (tox.ini deps sa pinned).
#
# Jeden obraz, trzy tryby uruchomienia wybierane przez SERVICE_MODE w runtime
# (sync-controller / rest-api-controller / rest-api-celery-worker, docker-entrypoint.sh).
#
# Alpine (musl) zamiast Debian slim: obraz bazowy ma rzad wielkosci mniej pakietow systemowych,
# wiec znika wiekszosc HIGH w Trivy image, ktore w Debianie nie mialy poprawki.
# Multi-stage: kompilator i naglowki (build-base) tylko w etapie build - 7 zaleznosci nie ma
# wheeli musllinux (msgpack, PyYAML, websockets maja rozszerzenia C; pyaes, pymexc, ta, Telethon
# to czysty Python bez wheela) i buduja sie tutaj.
#
# Jeden venv zamiast trzech tox envs: deps rest-api-controller sa nadzbiorem pozostalych dwoch,
# a tox w runtime tylko uruchamial jedna komende. Lista paczek dalej pochodzi z tox.ini
# (jedno zrodlo prawdy), tox nie trafia do obrazu.
FROM python:3.13-alpine AS build

RUN apk add --no-cache build-base libffi-dev

COPY tox.ini /tmp/tox.ini
RUN python -c 'import configparser; c = configparser.ConfigParser(interpolation=None); c.read("/tmp/tox.ini"); print(c["testenv:rest-api-controller"]["deps"].strip())' \
    > /tmp/requirements.txt
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir -r /tmp/requirements.txt \
    && /opt/venv/bin/python -m pip uninstall -y pip setuptools wheel \
    && find /opt/venv -name '__pycache__' -type d -prune -exec rm -rf {} +


# Ten sam obraz bazowy co build, wiec /opt/venv wskazuje na ten sam interpreter.
FROM python:3.13-alpine

# apk upgrade dociaga poprawki wydane po zbudowaniu obrazu bazowego; libstdc++/libgcc to
# runtime skompilowanych rozszerzen C++ (numpy, pandas, matplotlib, tiktoken, ...).
# pip z obrazu bazowego nie jest potrzebny w runtime - mniej paczek do skanowania.
RUN apk upgrade --no-cache \
    && apk add --no-cache libstdc++ libgcc \
    && python -m pip uninstall -y pip \
    && addgroup -g 1000 -S appgroup \
    && adduser -u 1000 -S -G appgroup -h /app appuser

COPY --from=build /opt/venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Rozszerzenia skompilowane w etapie build moga linkowac biblioteki, ktorych runtime nie ma -
# lepiej, zeby wywalil sie build niz pod na produkcji (ldd z musl: "Error loading shared library").
RUN missing=$(find /opt/venv -name '*.so*' -type f -exec ldd {} + 2>&1 | grep -i 'error loading shared library' | sort -u); \
    if [ -n "$missing" ]; then echo "brakujace biblioteki w runtime:"; echo "$missing"; exit 1; fi

WORKDIR /app
# /app zapisywalne dla uid 1000: Telethon trzyma tu pliki *.session.
COPY --chown=1000:1000 . /app
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod 0755 /usr/local/bin/docker-entrypoint.sh

USER 1000:1000

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
