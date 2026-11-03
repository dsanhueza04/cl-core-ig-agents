#!/usr/bin/env bash
# Compila y valida el IG montado en /ig. Sale con código distinto de 0 si algún paso falla.
set -euo pipefail

PKG_DIR="/root/.fhir/packages/hl7.fhir.cl.clcore#1.9.3"

# Preinstala CL Core 1.9.3 desde el paquete local (evita depender de la red para este paquete).
if [[ -f /reference/clcore.tgz && ! -d "$PKG_DIR" ]]; then
  echo "== Instalando CL Core 1.9.3 en la caché de paquetes"
  mkdir -p "$PKG_DIR"
  tar -xzf /reference/clcore.tgz -C "$PKG_DIR"
fi

cd /ig

echo "== SUSHI $(sushi --version 2>/dev/null | head -n1)"
sushi build .

echo "== IG Publisher"
java -Xmx4g -jar /opt/publisher.jar -ig . ${PUBLISHER_ARGS:-}

echo "== Resumen QA"
if [[ -f output/qa.json ]]; then
  node -e "const d=require('./output/qa.json');console.log('errores:',d.errs,'| warnings:',d.warnings,'| hints:',d.hints)"
fi
