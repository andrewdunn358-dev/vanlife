FROM debian:bookworm-slim

# Tippecanoe has no official image, so build it. Pinned to a tag rather
# than main so a rebuild in six months produces the same tiles.
ARG TIPPECANOE_VERSION=2.78.0

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        curl \
        git \
        libsqlite3-dev \
        python3 \
        python3-pip \
        zlib1g-dev \
    && git clone --depth 1 --branch ${TIPPECANOE_VERSION} \
        https://github.com/felt/tippecanoe.git /tmp/tippecanoe \
    && make -C /tmp/tippecanoe -j"$(nproc)" \
    && make -C /tmp/tippecanoe install \
    && rm -rf /tmp/tippecanoe \
    && apt-get purge -y build-essential git \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /work
ENTRYPOINT ["/bin/bash"]
