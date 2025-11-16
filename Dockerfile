FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
    qbittorrent-nox \
    gosu \
    ca-certificates \
    python3 \
    curl \
    jq \
    wireguard \
    wireguard-tools \
    iproute2 \
    iptables \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Create default non-root shell user for debugging access (UID/GID can still be
# remapped at runtime by the entrypoint if desired).
RUN groupadd -r appuser && useradd -r -g appuser -d /home/appuser -m appuser

COPY docker-entrypoint.py /usr/local/bin/docker-entrypoint.py
RUN chmod +x /usr/local/bin/docker-entrypoint.py
COPY scripts/log-external-ip.sh /usr/local/bin/log-external-ip.sh
COPY scripts/wg-up.sh /usr/local/bin/wg-up.sh
COPY scripts/wg-down.sh /usr/local/bin/wg-down.sh
RUN chmod +x /usr/local/bin/log-external-ip.sh /usr/local/bin/wg-up.sh /usr/local/bin/wg-down.sh

EXPOSE 8080
VOLUME ["/config", "/downloads"]

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.py"]
CMD ["qbittorrent-nox", "--webui-port=8080", "--profile=/config"]
