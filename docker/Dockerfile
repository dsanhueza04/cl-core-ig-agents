# Entorno reproducible: SUSHI + IG Publisher + Jekyll con versiones fijadas.
# NOTA: aún no probado en tu máquina; el primer `make build` confirma las versiones.
FROM node:22-bookworm-slim

ARG SUSHI_VERSION=3.20.1
# Versión del IG Publisher. La 2.0.17 funcionó, pero el 2026-10-01 el propio publisher la marcó desactualizada
# (vigente: 2.3.4) y tx.fhir.org rechazó su identificador de caché. Actualízala a propósito, no por accidente.
ARG PUBLISHER_VERSION=2.3.4
ARG JEKYLL_VERSION=4.3.4

RUN apt-get update && apt-get install -y --no-install-recommends \
      openjdk-17-jre-headless ruby-full build-essential zlib1g-dev \
      git curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN gem install jekyll -v ${JEKYLL_VERSION} --no-document \
    && npm install -g fsh-sushi@${SUSHI_VERSION}

RUN curl -fsSL -o /opt/publisher.jar \
      https://github.com/HL7/fhir-ig-publisher/releases/download/${PUBLISHER_VERSION}/publisher.jar

ENV JAVA_TOOL_OPTIONS="-Dfile.encoding=UTF-8"

COPY entrypoint.sh /usr/local/bin/entrypoint.sh
# Si el archivo se descargó en Windows puede traer saltos de línea CRLF: se quitan para que bash lo ejecute
RUN sed -i 's/\r$//' /usr/local/bin/entrypoint.sh && chmod +x /usr/local/bin/entrypoint.sh

WORKDIR /ig
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
