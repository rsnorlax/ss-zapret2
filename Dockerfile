ARG ALPINE_VERSION=3.21
ARG ZAPRET_TAG
ARG CURL_VERSION=8.13.0
ARG BLOCKCHECKW_VERSION=v0.9.4
ARG SHADOWSOCKS_VERSION=1.21.2
ARG SHADOWSOCKS_AMD64_SHA256=53e6cc209ab9f925e5a59c9f43d75b8179551fc9e608846d7649b5e3aff22c16
ARG SHADOWSOCKS_ARM64_SHA256=19e11f39a1b1cd6f843d2d1b5e7759d557448bc82017ff87b9cfaeeff9814f8f

FROM alpine:${ALPINE_VERSION} AS build
ARG ZAPRET_TAG
ARG CURL_VERSION
ARG BLOCKCHECKW_VERSION
ARG TARGETPLATFORM
ARG ZAPRET_SRC=/opt/zapret2-src
ARG ZAPRET_BUILD=/opt/zapret2-build

WORKDIR /opt

RUN case "$TARGETPLATFORM" in \
      "linux/amd64") \
        echo "linux-x86_64" | tee /tmp/zapret_arch /tmp/blockcheckw_arch > /dev/null && \
        echo "x86_64" > /tmp/curl_arch ;; \
      "linux/arm64") \
        echo "linux-arm64" | tee /tmp/zapret_arch /tmp/blockcheckw_arch > /dev/null && \
        echo "aarch64" > /tmp/curl_arch ;; \
      *) echo "Unsupported platform: $TARGETPLATFORM" && exit 1 ;; \
    esac

RUN test -n "${ZAPRET_TAG}" && \
    wget -qO- "https://github.com/bol-van/zapret2/releases/download/${ZAPRET_TAG}/zapret2-${ZAPRET_TAG}.tar.gz" | tar xz && \
    mv zapret2-* ${ZAPRET_SRC}

WORKDIR ${ZAPRET_BUILD}

RUN ZAPRET_ARCH=$(cat /tmp/zapret_arch) && \
    mkdir -p binaries/${ZAPRET_ARCH} && \
    cp ${ZAPRET_SRC}/binaries/${ZAPRET_ARCH}/ip2net \
       ${ZAPRET_SRC}/binaries/${ZAPRET_ARCH}/mdig \
       ${ZAPRET_SRC}/binaries/${ZAPRET_ARCH}/nfqws2 \
       binaries/${ZAPRET_ARCH}/ && \
    chmod +x binaries/${ZAPRET_ARCH}/*

RUN cp -a ${ZAPRET_SRC}/init.d ${ZAPRET_SRC}/common ${ZAPRET_SRC}/ipset ${ZAPRET_SRC}/blockcheck2.d ${ZAPRET_SRC}/blockcheck2.sh . && \
    cp -a ${ZAPRET_SRC}/files files && \
    mv files/fake files/fake.dist && \
    cp -a ${ZAPRET_SRC}/lua lua.dist && \
    mv init.d/custom.d.examples.linux init.d/custom.d.examples.linux.dist && \
    find init.d -mindepth 1 -maxdepth 1 -type d \
      ! -name "sysv" \
      ! -name "files" \
      ! -name "custom.d.examples.*" \
      -exec rm -rf {} +

RUN ZAPRET_BASE=${ZAPRET_BUILD} ${ZAPRET_SRC}/install_bin.sh

RUN CURL_ARCH=$(cat /tmp/curl_arch) && \
    wget -qO- "https://github.com/stunnel/static-curl/releases/download/${CURL_VERSION}/curl-linux-${CURL_ARCH}-glibc-${CURL_VERSION}.tar.xz" | \
    tar -xJf - -C /opt && \
    chmod +x /opt/curl

RUN BLOCKCHECKW_ARCH=$(cat /tmp/blockcheckw_arch) && \
    wget -qO- "https://github.com/rcd27/blockcheckw/releases/download/${BLOCKCHECKW_VERSION}/blockcheckw-${BLOCKCHECKW_ARCH}.tar.gz" | \
    tar -xzf - -C /opt && \
    chmod +x /opt/blockcheckw

FROM alpine:${ALPINE_VERSION} AS shadowsocks
ARG SHADOWSOCKS_VERSION
ARG SHADOWSOCKS_AMD64_SHA256
ARG SHADOWSOCKS_ARM64_SHA256
ARG TARGETPLATFORM

WORKDIR /tmp/shadowsocks

RUN case "$TARGETPLATFORM" in \
      "linux/amd64") \
        SHADOWSOCKS_TARGET="x86_64-unknown-linux-musl" && \
        SHADOWSOCKS_SHA256="$SHADOWSOCKS_AMD64_SHA256" ;; \
      "linux/arm64") \
        SHADOWSOCKS_TARGET="aarch64-unknown-linux-musl" && \
        SHADOWSOCKS_SHA256="$SHADOWSOCKS_ARM64_SHA256" ;; \
      *) echo "Unsupported platform: $TARGETPLATFORM" >&2 && exit 1 ;; \
    esac && \
    ARCHIVE="shadowsocks-v${SHADOWSOCKS_VERSION}.${SHADOWSOCKS_TARGET}.tar.xz" && \
    wget -O "$ARCHIVE" \
      "https://github.com/shadowsocks/shadowsocks-rust/releases/download/v${SHADOWSOCKS_VERSION}/${ARCHIVE}" && \
    echo "$SHADOWSOCKS_SHA256  $ARCHIVE" | sha256sum -c - && \
    tar -xJf "$ARCHIVE" sslocal ssserver && \
    mkdir -p /usr/local/bin && \
    cp sslocal ssserver /usr/local/bin/ && \
    chmod 0755 /usr/local/bin/sslocal /usr/local/bin/ssserver

FROM alpine:${ALPINE_VERSION}

RUN apk add --no-cache \
      ca-certificates \
      ipset \
      iptables \
      ip6tables \
      nftables

WORKDIR /opt

COPY --from=build /opt/zapret2-build /opt/zapret2
COPY --from=build /opt/curl /usr/bin/curl
COPY --from=build /opt/blockcheckw /usr/bin/blockcheckw
COPY --from=shadowsocks /usr/local/bin/sslocal /usr/bin/sslocal
COPY --from=shadowsocks /usr/local/bin/ssserver /usr/bin/ssserver
COPY --chmod=755 entrypoint.sh /opt/entrypoint.sh
COPY --chmod=755 healthcheck.sh /opt/healthcheck.sh

ENTRYPOINT ["/opt/entrypoint.sh"]
