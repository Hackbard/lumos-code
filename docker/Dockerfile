# Lumos Code Joern-Backend — eigenes Image auf Basis des offiziellen Joern-Release.
# Kein externer Codebadger-Server noetig; lmc bringt Joern selbst mit.
FROM eclipse-temurin:21-jdk

ARG JOERN_VERSION=4.0.548
ENV JOERN_HOME=/opt/joern-cli

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        unzip ca-certificates curl \
        php-cli python3 \
 # ponytail: Joerns PHP-Frontend braucht `php`; python3 fuer py2cpg. Weitere
 # Runtimes (node/go/ruby) bei Bedarf hier ergaenzen — die meisten Joern-
 # Frontends (java/c/cpp/js/ts/kotlin/...) sind Java-basiert und brauchen keine.
 && rm -rf /var/lib/apt/lists/* \
 && curl -fsSL -o /tmp/joern-cli.zip \
        "https://github.com/joernio/joern/releases/download/v${JOERN_VERSION}/joern-cli.zip" \
 && unzip -q /tmp/joern-cli.zip -d /opt \
 && rm /tmp/joern-cli.zip \
 && JOERN_DIR="$(find /opt -maxdepth 1 -type d -name 'joern*' | head -1)" \
 && [ -n "$JOERN_DIR" ] && ln -sf "$JOERN_DIR" /opt/joern-cli \
 && /opt/joern-cli/joern-parse --help >/dev/null 2>&1 || true

ENV PATH=/opt/joern-cli:/opt/joern-cli/bin:${PATH}

WORKDIR /workspace
EXPOSE 8085

# Persistenter Joern CPGQL-REST-Server. CPGs liegen im Volume /cpgs (<hash>.bin).
CMD ["joern", "--server", "--server-host", "0.0.0.0", "--server-port", "8085"]