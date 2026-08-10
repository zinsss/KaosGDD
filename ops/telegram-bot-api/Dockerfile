FROM ubuntu:24.04 AS build

ARG TELEGRAM_BOT_API_COMMIT=adfd7f6a8e990272851777eeb3ae0def4216f161

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        cmake \
        g++ \
        git \
        gperf \
        libssl-dev \
        make \
        zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

RUN git clone --recursive https://github.com/tdlib/telegram-bot-api.git /src \
    && git -C /src checkout "${TELEGRAM_BOT_API_COMMIT}" \
    && git -C /src submodule update --init --recursive

RUN cmake -S /src -B /build \
        -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_INSTALL_PREFIX=/install \
    && cmake --build /build --target install --parallel 2

FROM ubuntu:24.04

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates libssl3t64 zlib1g \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --system --uid 10001 --home /var/lib/telegram-bot-api --shell /usr/sbin/nologin telegram

COPY --from=build /install/bin/telegram-bot-api /usr/local/bin/telegram-bot-api

RUN mkdir -p /var/lib/telegram-bot-api/tmp \
    && chown -R telegram:telegram /var/lib/telegram-bot-api

USER telegram

EXPOSE 8081

ENTRYPOINT ["telegram-bot-api"]
CMD ["--local", "--http-ip-address=0.0.0.0", "--http-port=8081", "--dir=/var/lib/telegram-bot-api", "--temp-dir=/var/lib/telegram-bot-api/tmp"]
