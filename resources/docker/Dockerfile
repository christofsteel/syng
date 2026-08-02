FROM python:3.14-slim

# ENV PYTHONDONTWRITEBYTECODE=1 \
#     PYTHONUNBUFFERED=1 \
ENV PATH=/app/.local/bin:$PATH

RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -m -d /app syng

WORKDIR /app

COPY --chown=syng:syng . /app

USER syng

RUN pip install --no-cache-dir --user . \
    && touch /app/keys.txt

EXPOSE 8080

ENTRYPOINT ["syng", "server", "-k", "/app/keys.txt"]
