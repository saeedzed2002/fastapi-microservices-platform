# MinIO no longer publishes a container for its latest security release.
# Build the official upstream release from a tag and immutable source commit.
FROM golang:1.24.8-bookworm@sha256:4ed690d6649d63c312b99a6120025ec79ce3b542968a37da53d6236c7c61a848 AS build

ARG MINIO_RELEASE=RELEASE.2025-10-15T17-29-55Z
ARG MINIO_SOURCE_COMMIT=9e49d5e7a648f00e26f2246f4dc28e6b07f8c84a

RUN apt-get update \
    && apt-get install --no-install-recommends --yes git ca-certificates \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /src
RUN git clone --depth 1 --branch "${MINIO_RELEASE}" https://github.com/minio/minio.git . \
    && test "$(git rev-parse HEAD)" = "${MINIO_SOURCE_COMMIT}"
RUN CGO_ENABLED=0 go build -tags kqueue -trimpath \
    --ldflags "$(go run buildscripts/gen-ldflags.go)" \
    -o /out/minio

FROM debian:bookworm-slim@sha256:88200866dfff7ea7f5cbcb6ec7c8a701889efe6fe859fe64d6990e4b07ea4171

RUN apt-get update \
    && apt-get install --no-install-recommends --yes ca-certificates curl \
    && groupadd --gid 10001 minio \
    && useradd --no-create-home --uid 10001 --gid minio --home-dir /var/minio \
        --shell /usr/sbin/nologin minio \
    && install --directory --owner=minio --group=minio /data /var/minio \
    && rm -rf /var/lib/apt/lists/*
COPY --from=build /out/minio /usr/local/bin/minio

ENV HOME=/var/minio
VOLUME ["/data"]
USER minio:minio
ENTRYPOINT ["/usr/local/bin/minio"]
CMD ["server", "/data"]
