# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""ACME retail example API: the mock retailer behind the shared storefront routes, the
merchant router under /api/merchant, and the retail-only routes below.

    uvicorn retail.api.main:app --app-dir examples --reload --port 8000

Memory here is file-backed (``data/.memory-store.json``, gitignored) and seeded once per
user, so what a shopper asks the store to remember, or to forget, survives a restart.
"""

from __future__ import annotations

import os

from fastapi import HTTPException
from fastapi.staticfiles import StaticFiles

from commerce_common.memory import InMemoryMemoryStore, JsonFileMemoryStore
from commerce_common.pyd import BaseModel, Field
from demo_common import (
    REPO_ROOT,
    CartAddRequest,
    MemorySeeder,
    build_storefront_host,
    load_demo_env,
)
from shopping_agent import ProductDetails
from shopping_agent_runtime import ShoppingAgent

from .agent_config import build_shopping_config
from .merchant import create_merchant_router
from .mock_retail import DATA_DIR, MockRetail

load_demo_env(DATA_DIR.parent)
PRODUCT_IMAGES = DATA_DIR.parent / "storefront-web" / "public" / "products"

backend = MockRetail()
agent = ShoppingAgent(
    backend=backend,
    skills_dir=REPO_ROOT / "shopping-agent" / "skills",
    config=build_shopping_config(),
    memory_store=JsonFileMemoryStore(DATA_DIR / ".memory-store.json"),
)


def product_detail(product: ProductDetails) -> dict:
    # Detail-panel enrichment only; the agent's tool results never carry it.
    return product.model_dump() | {
        "price_intelligence": backend.price_intelligence(product.product_id),
        "review_aspects": backend.review_aspects(product.product_id),
    }


host = build_storefront_host(
    title="ACME Retail demo API",
    example_root=DATA_DIR.parent,
    backend=backend,
    agent=agent,
    memory_seeder=MemorySeeder(
        DATA_DIR / "memory-seed.json", marker=DATA_DIR / ".memory-seeded.json"
    ),
    product_detail=product_detail,
)
app = host.app
app.include_router(create_merchant_router(backend, InMemoryMemoryStore()), prefix="/api/merchant")
# The merchant portal shows the storefront's listing photos, so the API serves them to both apps.
app.mount("/products", StaticFiles(directory=PRODUCT_IMAGES, check_dir=False), name="products")


@app.post("/api/cart/add")
async def cart_add(request: CartAddRequest, record: host.CurrentSession) -> dict:
    return await host.direct_add(
        record,
        request,
        note="Customer tapped the add-to-cart button on {title} ({product_id}), quantity {quantity}.",
    )


class CartQuantityRequest(BaseModel):
    quantity: int = Field(ge=0, le=24)


@app.patch("/api/cart/item/{product_id:path}")
async def cart_set_quantity(
    product_id: str, request: CartQuantityRequest, record: host.CurrentSession
) -> dict:
    """The shop page's stepper: set a line's quantity (0 removes it). Only a line already in
    the cart can change, so this cannot add a product the add-to-cart gates did not pass."""
    context = host.context(record)
    cart = await backend.get_cart(context)
    if not any(line.product_id == product_id for line in cart.items):
        raise HTTPException(status_code=404, detail="Not in the cart")
    if request.quantity == 0:
        await backend.remove_from_cart(context, product_id)
    else:
        await backend.update_cart_item(context, product_id, request.quantity)
    return {"ok": True, "cart": (await host.cart_payload(record))}


# Single-process hosting: with STOREFRONT_STATIC_DIR set to the storefront's static export
# (STATIC_EXPORT=1 npm run build), this API also serves the storefront pages on the same origin.
# Mounted last so every /api route and /products wins.
_merchant_static_dir = os.environ.get("MERCHANT_STATIC_DIR")
if _merchant_static_dir:
    app.mount("/merchant", StaticFiles(directory=_merchant_static_dir, html=True), name="merchant-portal")
_static_dir = os.environ.get("STOREFRONT_STATIC_DIR")
if _static_dir:
    app.mount("/", StaticFiles(directory=_static_dir, html=True), name="storefront")
