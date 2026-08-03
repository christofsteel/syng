FROM python:3.14-alpine AS build
RUN adduser -D -h /app syng
USER syng
WORKDIR /build
COPY --chown=syng:syng . /build
RUN pip install --no-cache-dir --user .[server] \
    && touch /app/keys \
    && cp -r /build/.git /app/.git

FROM python:3.14-alpine
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/app/.local/bin:$PATH
RUN apk add git && adduser -D -h /app syng
USER syng
WORKDIR /app
COPY --chown=syng:syng --from=build /app /app

EXPOSE 8080

ENTRYPOINT ["syng", "server", "-k", "/app/keys.txt"]
