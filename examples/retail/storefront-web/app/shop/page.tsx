// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

"use client";

/**
 * A plain shopping page on the same API as the assistant: browse and search the catalog,
 * open a product, add to a cart, change quantities, review orders, and see a demo checkout.
 * It works with the AI assistant turned off. Nothing here takes payment or places an order.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { formatMoney, useSession } from "web-shared";
import { ProductTitle } from "@/components/ProductTile";
import { productTileClass } from "@/lib/format";
import { api } from "@/lib/api";
import type { CartPayload, Product, ProductDetails } from "@/lib/types";

interface OrderLine {
  title?: string;
  quantity?: number;
}
interface OrderRow {
  order_id: string;
  status: string;
  placed_at?: string;
  items?: OrderLine[];
  total?: number;
}

/** A product photo, or a plain tile with a drawn bag icon and the brand initials (no emoji). */
function ShopImage({ product, className = "" }: { product: Product; className?: string }) {
  if (product.image_url) {
    // eslint-disable-next-line @next/next/no-img-element
    return <img src={product.image_url} alt={product.title} className={`object-cover ${className}`} />;
  }
  const initials = (product.brand ?? product.title).replace(/^ACME\s+/i, "").slice(0, 2).toUpperCase();
  return (
    <div className={`flex flex-col items-center justify-center gap-1 ${productTileClass(product.product_id)} ${className}`} aria-hidden>
      <svg width="44" height="44" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="opacity-60">
        <path d="M6 8h12l-1 12H7L6 8z" />
        <path d="M9 8V6a3 3 0 016 0v2" />
      </svg>
      <span className="text-xs font-semibold tracking-widest opacity-60">{initials}</span>
    </div>
  );
}

const CATEGORY_LABEL = (id: string) =>
  id
    .split("-")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");

export default function ShopPage() {
  const session = useSession(api);
  const [products, setProducts] = useState<Product[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [category, setCategory] = useState<string>("all");
  const [query, setQuery] = useState("");
  const [cart, setCart] = useState<CartPayload | null>(null);
  const [open, setOpen] = useState<ProductDetails | null>(null);
  const [variant, setVariant] = useState<string | null>(null);
  const [tab, setTab] = useState<"shop" | "orders">("shop");
  const [orders, setOrders] = useState<OrderRow[] | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [checkout, setCheckout] = useState(false);
  const [cartOpen, setCartOpen] = useState(false);

  useEffect(() => {
    void api.get<{ products: Product[] }>("/products", { limit: "100" }).then((data) => {
      if (data) setProducts(data.products);
      else setFailed(true);
    });
  }, []);

  useEffect(() => {
    if (!session.sessionId) return;
    void api.fetchCart<CartPayload>().then((next) => next && setCart(next));
  }, [session.sessionId]);

  useEffect(() => {
    if (tab !== "orders" || !session.sessionId) return;
    void api.fetchOrders().then((rows) => setOrders(rows as unknown as OrderRow[] | null));
  }, [tab, session.sessionId]);

  const categories = useMemo(() => {
    const seen = new Set<string>();
    (products ?? []).forEach((p) => p.category && seen.add(p.category));
    return [...seen].sort();
  }, [products]);

  const shown = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (products ?? []).filter(
      (p) =>
        (category === "all" || p.category === category) &&
        (!q || `${p.title} ${p.brand ?? ""} ${p.short_description ?? ""}`.toLowerCase().includes(q)),
    );
  }, [products, category, query]);

  const flash = useCallback((text: string) => {
    setMessage(text);
    window.setTimeout(() => setMessage((current) => (current === text ? null : current)), 3500);
  }, []);

  const add = useCallback(
    async (productId: string) => {
      const response = await api.post<{ cart: CartPayload }>("/cart/add", { product_id: productId, quantity: 1 });
      if (response?.cart) {
        setCart(response.cart);
        setCheckout(false);
        flash("Added to your cart.");
      } else flash("That item could not be added. Choose its options first, or it may be out of stock.");
    },
    [flash],
  );

  const setQuantity = useCallback(async (productId: string, quantity: number) => {
    const response = await api.patch<{ cart: CartPayload }>(`/cart/item/${encodeURIComponent(productId)}`, { quantity });
    if (response?.cart) {
      setCart(response.cart);
      setCheckout(false);
    }
  }, []);

  const view = useCallback(async (productId: string) => {
    const details = await api.get<ProductDetails>(`/products/${encodeURIComponent(productId)}`);
    if (details) {
      setOpen(details);
      setVariant(details.variants?.[0]?.product_id ?? null);
    }
  }, []);

  const count = cart?.item_count ?? 0;

  const cartPanel = (
    <aside aria-label="Cart" className="flex h-full flex-col bg-white">
      <div className="flex items-center justify-between border-b border-(--line,#e5e7eb) px-4 py-3">
        <div className="font-semibold text-(--ink)">
          Cart <span key={count} className="bump ml-1 rounded-full bg-(--well) px-2 py-0.5 text-xs">{count === 1 ? "1 item" : `${count} items`}</span>
        </div>
        <button className="text-sm text-(--ink-soft) md:hidden" onClick={() => setCartOpen(false)}>
          Close
        </button>
      </div>
      <div className="flex-1 overflow-y-auto px-4 py-3">
        {cart && cart.items.length ? (
          cart.items.map((item) => (
            <div key={item.product_id} className="mb-3 flex gap-3 border-b border-(--well) pb-3">
              <div className="min-w-0 flex-1">
                <div className="text-[13px] font-medium text-(--ink)">{item.title}</div>
                <div className="text-xs text-(--ink-soft)">{formatMoney(item.price, cart.currency)} each</div>
                <div className="mt-1.5 flex items-center gap-2">
                  <button aria-label="Fewer" className="h-6 w-6 rounded border" onClick={() => setQuantity(item.product_id, item.quantity - 1)}>
                    -
                  </button>
                  <span className="w-5 text-center text-sm">{item.quantity}</span>
                  <button aria-label="More" className="h-6 w-6 rounded border" onClick={() => setQuantity(item.product_id, Math.min(24, item.quantity + 1))}>
                    +
                  </button>
                  <button className="ml-2 text-xs text-(--ink-soft) underline" onClick={() => setQuantity(item.product_id, 0)}>
                    Remove
                  </button>
                </div>
              </div>
              <div className="text-sm font-semibold">{formatMoney(item.line_total, cart.currency)}</div>
            </div>
          ))
        ) : (
          <p className="mt-10 text-center text-sm text-(--ink-soft)">Your cart is empty.</p>
        )}
      </div>
      <div className="border-t border-(--well) px-4 py-3">
        <div className="mb-2 flex justify-between text-sm">
          <span>Subtotal</span>
          <span className="font-bold">{formatMoney(cart?.subtotal ?? 0, cart?.currency)}</span>
        </div>
        {checkout ? (
          <div role="status" className="mb-2 rounded-lg bg-(--well) p-3 text-xs text-(--ink-2)">
            <b>Demo checkout.</b> This store is a demonstration with fictional products. No payment is taken and no order is placed.
          </div>
        ) : null}
        <button
          disabled={!count}
          onClick={() => setCheckout(true)}
          className="w-full rounded-lg bg-(--ink) px-3 py-2.5 text-sm font-semibold text-(--surface) disabled:opacity-40"
        >
          Check out (demo)
        </button>
      </div>
    </aside>
  );

  return (
    <div className="flex h-screen flex-col bg-(--surface-2,#f4f5f9) text-(--ink)">
      <header className="flex items-center gap-2 border-b sm:gap-4 border-(--well) bg-white px-4 py-2.5">
        <span className="grid h-[30px] w-[30px] shrink-0 place-items-center rounded-lg bg-(--ink) text-[15px] font-bold text-(--surface)">A</span>
        <span className="hidden text-[17px] font-bold tracking-tight sm:inline">ACME</span>
        <nav className="flex gap-0.5 text-[13px] sm:gap-1 sm:text-sm">
          {(["shop", "orders"] as const).map((id) => (
            <button key={id} onClick={() => setTab(id)} className={`rounded-md px-2 py-1.5 sm:px-3 ${tab === id ? "bg-(--well) font-semibold" : ""}`}>
              {id === "shop" ? "Shop" : "Orders"}
            </button>
          ))}
          <a href="/?assistant" className="rounded-md px-2 py-1.5 text-(--ink-soft) sm:px-3">
            Assistant
          </a>
        </nav>
        <div className="ml-auto flex shrink-0 items-center gap-3 text-sm">
          <span className="hidden text-(--ink-soft) sm:inline">Demo shopper</span>
          <button className="whitespace-nowrap rounded-lg border px-2.5 py-1.5 text-[13px] md:hidden" onClick={() => setCartOpen(true)}>
            Cart ({count})
          </button>
        </div>
      </header>
      <div role="note" className="bg-amber-50 px-4 py-1.5 text-center text-xs text-amber-900">
        Demo store: the products, ratings, orders and shopper are fictional sample data. No payments, no real orders.
      </div>
      <div className="flex min-h-0 flex-1">
        <main className="min-w-0 flex-1 overflow-y-auto px-4 py-5 md:px-8">
          {message ? (
            <div role="status" className="toast-in fixed left-1/2 top-16 z-30 -translate-x-1/2 rounded-lg bg-(--ink) px-4 py-2 text-sm text-(--surface) shadow">
              {message}
            </div>
          ) : null}
          {tab === "shop" ? (
            <>
              <section className="hero mb-5 overflow-hidden rounded-2xl p-6 text-white md:p-8" aria-label="Featured">
                <div className="hero-in text-xs font-semibold uppercase tracking-widest opacity-80">Demo marketplace</div>
                <h1 className="hero-in mt-1 text-2xl font-bold md:text-3xl" style={{ animationDelay: "80ms" }}>Find something you will actually use</h1>
                <p className="hero-in mt-2 max-w-xl text-sm opacity-90" style={{ animationDelay: "160ms" }}>
                  {products ? `${products.length} sample products` : "Loading"} across {categories.length} categories. Browse, compare options and fill a cart. Checkout is a demo, no payment is taken.
                </p>
                <div className="hero-in mt-4 flex flex-wrap gap-2" style={{ animationDelay: "240ms" }}>
                  {categories.slice(0, 8).map((id) => (
                    <button key={id} onClick={() => setCategory(id)} className={`pill ${category === id ? "pill-on" : ""}`}>{id.replace(/_/g, " ")}</button>
                  ))}
                  {category !== "all" ? <button onClick={() => setCategory("all")} className="pill">Clear</button> : null}
                </div>
              </section>
              <div className="mb-4 flex flex-wrap items-center gap-3">
                <input
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Search products"
                  aria-label="Search products"
                  className="w-full max-w-sm rounded-lg border bg-white px-3 py-2 text-sm"
                />
                <select value={category} onChange={(e) => setCategory(e.target.value)} aria-label="Category" className="rounded-lg border bg-white px-3 py-2 text-sm">
                  <option value="all">All categories</option>
                  {categories.map((id) => (
                    <option key={id} value={id}>
                      {CATEGORY_LABEL(id)}
                    </option>
                  ))}
                </select>
                <span className="text-xs text-(--ink-soft)">{products ? `${shown.length} products` : ""}</span>
              </div>
              {failed ? <p className="text-sm">Couldn&apos;t reach the store API.</p> : null}
              {!products && !failed ? <p className="text-sm text-(--ink-soft)">Loading the catalog…</p> : null}
              <div className="grid grid-cols-2 gap-4 lg:grid-cols-3 xl:grid-cols-4">
                {shown.map((p, idx) => (
                  <article key={p.product_id} style={{ animationDelay: `${Math.min(idx, 16) * 35}ms` }} className="tile-in lift flex flex-col overflow-hidden rounded-xl border bg-white">
                    <button onClick={() => view(p.product_id)} className="text-left" aria-label={`Details for ${p.title}`}>
                      <ShopImage product={p} className="h-36 w-full" />
                      <div className="p-3 pb-1">
                        <div className="text-[11px] uppercase tracking-wide text-(--ink-soft)">{p.brand}</div>
                        <ProductTitle title={p.title} className="line-clamp-2 text-[13.5px] font-medium" />
                      </div>
                    </button>
                    <div className="mt-auto flex items-center justify-between p-3 pt-1">
                      <div>
                        <div className="text-[15px] font-bold">{formatMoney(p.price, p.currency)}</div>
                        {p.rating ? <div className="text-[11px] text-(--ink-soft)">★ {p.rating} ({p.review_count}) sample</div> : null}
                      </div>
                      {p.options && Object.keys(p.options).length ? (
                        <button onClick={() => view(p.product_id)} className="rounded-lg border px-3 py-1.5 text-xs font-semibold">
                          Options
                        </button>
                      ) : p.in_stock === false ? (
                        <span className="text-xs text-(--ink-soft)">Out of stock</span>
                      ) : (
                        <button onClick={() => add(p.product_id)} className="rounded-lg bg-(--ink) px-3 py-1.5 text-xs font-semibold text-(--surface)">
                          Add
                        </button>
                      )}
                    </div>
                  </article>
                ))}
              </div>
            </>
          ) : (
            <section aria-label="Orders">
              <h1 className="mb-3 text-xl font-bold">Sample orders (demo data)</h1>
              {!orders ? <p className="text-sm text-(--ink-soft)">Loading…</p> : null}
              {orders?.map((order, oi) => (
                <div key={order.order_id} style={{ animationDelay: `${oi * 70}ms` }} className="tile-in mb-3 rounded-xl border bg-white p-4">
                  <div className="flex justify-between text-sm">
                    <b>{order.order_id}</b>
                    <span className="rounded-full bg-(--well) px-2 py-0.5 text-xs capitalize">{order.status}</span>
                  </div>
                  <div className="rail mt-3" aria-label={`Progress: ${order.status}`}>
                    <div className="rail-fill" style={{ width: `${({ processing: 25, shipped: 66, out_for_delivery: 85, delivered: 100 } as Record<string, number>)[order.status] ?? 40}%` }} />
                  </div>
                  <div className="mt-1 flex justify-between text-[10px] text-(--ink-soft)"><span>Ordered</span><span>Packed</span><span>Shipped</span><span>Delivered</span></div>
                  <ul className="mt-2 text-[13px] text-(--ink-2)">
                    {(order.items ?? []).map((line, i) => (
                      <li key={i}>
                        {line.quantity ?? 1} x {line.title}
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
              <p className="text-xs text-(--ink-soft)">These orders are fictional sample data, not real customer activity.</p>
            </section>
          )}
        </main>
        <div className="hidden w-[340px] shrink-0 border-l border-(--well) md:block">{cartPanel}</div>
      </div>
      {cartOpen ? (
        <div className="fade-in fixed inset-0 z-40 bg-black/40 md:hidden" onClick={() => setCartOpen(false)}>
          <div className="drawer-in absolute right-0 top-0 h-full w-[88%] max-w-sm" onClick={(e) => e.stopPropagation()}>
            {cartPanel}
          </div>
        </div>
      ) : null}
      {open ? (
        <div className="fade-in fixed inset-0 z-50 grid place-items-center bg-black/40 p-4" onClick={() => setOpen(null)}>
          <div role="dialog" aria-label={open.title} className="dialog-in max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-2xl bg-white" onClick={(e) => e.stopPropagation()}>
            <ShopImage product={open} className="h-52 w-full" />
            <div className="p-5">
              <div className="text-xs uppercase text-(--ink-soft)">{open.brand}</div>
              <h2 className="text-lg font-bold">{open.title}</h2>
              <div className="mt-1 text-xl font-bold">{formatMoney(open.price, open.currency)}</div>
              <p className="mt-3 text-sm text-(--ink-2)">{open.long_description ?? open.short_description}</p>
              {open.specs ? (
                <dl className="mt-3 grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
                  {Object.entries(open.specs).slice(0, 8).map(([k, v]) => (
                    <div key={k} className="contents">
                      <dt className="text-(--ink-soft)">{k}</dt>
                      <dd>{v}</dd>
                    </div>
                  ))}
                </dl>
              ) : null}
              {open.variants?.length ? (
                <label className="mt-4 block text-sm">
                  Choose an option
                  <select value={variant ?? ""} onChange={(e) => setVariant(e.target.value)} className="mt-1 block w-full rounded-lg border px-3 py-2">
                    {open.variants.map((v) => (
                      <option key={v.product_id} value={v.product_id}>
                        {Object.values(v.option_values ?? {}).join(" / ") || v.title} - {formatMoney(v.price, v.currency)}
                        {v.in_stock === false ? " (out of stock)" : ""}
                      </option>
                    ))}
                  </select>
                </label>
              ) : null}
              <div className="mt-5 flex gap-2">
                <button
                  onClick={() => {
                    void add(open.variants?.length ? (variant ?? open.product_id) : open.product_id);
                    setOpen(null);
                  }}
                  className="flex-1 rounded-lg bg-(--ink) px-3 py-2.5 text-sm font-semibold text-(--surface)"
                >
                  Add to cart
                </button>
                <button onClick={() => setOpen(null)} className="rounded-lg border px-4 py-2.5 text-sm">
                  Close
                </button>
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
