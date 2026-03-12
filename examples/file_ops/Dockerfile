FROM debian:bookworm-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends jq coreutils && \
    rm -rf /var/lib/apt/lists/*

COPY run.sh /run.sh
RUN chmod +x /run.sh

ENTRYPOINT ["/run.sh"]
