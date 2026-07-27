# syntax = docker/dockerfile:latest

FROM python:3.14-alpine

ARG UID=101
ARG GID=101
RUN addgroup -g $GID -S app && adduser -u $UID -S app -G app

WORKDIR /app

# Dependencies first so this layer only rebuilds when requirements.txt
# actually changes, not on every code edit.
COPY --link requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --link --chown=$UID:$GID udmp.py .
COPY --link --chown=$UID:$GID docs/dashboard_server.py docs/dashboard-live.html docs/

# 0.0.0.0 inside a container is the correct default — "localhost only"
# would make the server unreachable through Docker's own port mapping.
# The Host-header allowlist in dashboard_server.py (DNS-rebinding
# protection) applies regardless of which address it's bound to.
ENV UDMP_DASHBOARD_HOST=0.0.0.0
EXPOSE 8765

# No curl in this image on purpose — one less package — so the healthcheck
# uses Python's own urllib instead.
HEALTHCHECK --interval=30s --timeout=10s --retries=3 --start-period=10s \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/')" || exit 1

STOPSIGNAL SIGTERM

USER $UID

CMD ["python3", "docs/dashboard_server.py"]
