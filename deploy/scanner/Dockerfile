FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends clamav clamav-daemon ca-certificates && rm -rf /var/lib/apt/lists/*
COPY clamd.conf /etc/clamav/clamd.conf
COPY start.sh /usr/local/bin/start-scanner
RUN chmod 755 /usr/local/bin/start-scanner && mkdir -p /run/clamav && chown clamav:clamav /run/clamav /var/lib/clamav /var/log/clamav
USER clamav
ENV TZ=UTC
ENTRYPOINT ["/usr/local/bin/start-scanner"]
