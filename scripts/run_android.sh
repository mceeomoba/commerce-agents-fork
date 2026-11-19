#!/bin/sh
# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0
#
# Single-process demo host: the retail API plus the prebuilt storefront on one port, using
# libraries installed into ./libs (or LIBS_DIR; falls back to ./libs2) via pip install --target libs -r requirements-android.txt.
# AI chat stays off unless LLM_API_KEY is set. Checkout is a demo; nothing is charged.
set -e
cd "$(dirname "$0")/.."
ROOT="$(pwd)"
LIBS_DIR="${LIBS_DIR:-$ROOT/libs}"
if [ ! -d "$LIBS_DIR" ] && [ -d "$ROOT/libs2" ]; then LIBS_DIR="$ROOT/libs2"; fi
export PYTHONPATH="$LIBS_DIR:$ROOT/commerce-common:$ROOT/shopping-agent/core:$ROOT/shopping-agent/runtime-messages-api:$ROOT/merchant-agent/core:$ROOT/merchant-agent/runtime-messages-api:$ROOT/examples"
if [ ! -f deploy/site/index.html ]; then
  mkdir -p deploy/site
  unzip -q -o deploy/storefront-export.zip -d deploy/site
fi
if [ -f deploy/merchant-export.zip ] && [ ! -f deploy/merchant-site/index.html ]; then
  mkdir -p deploy/merchant-site
  unzip -q -o deploy/merchant-export.zip -d deploy/merchant-site
fi
if [ -f deploy/merchant-site/index.html ]; then export MERCHANT_STATIC_DIR="$ROOT/deploy/merchant-site"; fi
export STOREFRONT_STATIC_DIR="$ROOT/deploy/site"
export STOREFRONT_DIRECT_ADD="${STOREFRONT_DIRECT_ADD:-1}"
export DEMO_ALLOWED_HOSTS="${DEMO_ALLOWED_HOSTS:-*.agt.novamail.store}"
exec python3 -m uvicorn retail.api.main:app --host 0.0.0.0 --port "${PORT:-8787}"
