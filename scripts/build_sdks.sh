#!/bin/bash
# ==============================================================================
# ATENA SDK GENERATOR - DX Engine
# Genera automaticamente librerie client in TypeScript, Rust, Python e Go
# in base alle specifiche OpenAPI (generabili da FastAPI) o gRPC Protobuf.
# ==============================================================================

set -e

# Requisito: openapi-generator-cli
if ! command -v openapi-generator-cli &> /dev/null; then
    echo "Errore: openapi-generator-cli non trovato. Installare con npm install @openapitools/openapi-generator-cli -g"
    exit 1
fi

API_SCHEMA="server/api_schema.json"
OUTPUT_DIR="sdk"

echo "🛠 Generazione Atena SDK Dynamics..."

# 1. TypeScript / JS per Frontend e App Node.js
echo " Generando Atena SDK [TypeScript]..."
openapi-generator-cli generate \
    -i "$API_SCHEMA" \
    -g typescript-axios \
    -o "$OUTPUT_DIR/typescript" \
    --additional-properties=npmName=atena-sdk-js,supportsES6=true > /dev/null

# 2. Rust (Alte prestazioni, Sistemi Embed)
echo " Generando Atena SDK [Rust]..."
openapi-generator-cli generate \
    -i "$API_SCHEMA" \
    -g rust \
    -o "$OUTPUT_DIR/rust" \
    --additional-properties=packageName=atena-sdk-rs > /dev/null

# 3. Go (Microservizi)
echo " Generando Atena SDK [Go]..."
openapi-generator-cli generate \
    -i "$API_SCHEMA" \
    -g go \
    -o "$OUTPUT_DIR/go" \
    --additional-properties=packageName=atena > /dev/null

echo "✅ Tutte le SDK sono state generate in $OUTPUT_DIR/"
echo "Gli sviluppatori possono importare direttamente questi pacchetti per interagire con Atena con Type-Safety e crittografia nativa."
