# Commerce Agents (provider-neutral fork)

Fork of [anthropics/commerce-agents](https://github.com/anthropics/commerce-agents) (Apache-2.0, Copyright 2026 Anthropic PBC; license and file notices kept). This fork removes the Anthropic SDK, Claude Agent SDK, Managed Agents and Claude Code plugin; the agents run on any OpenAI-compatible chat-completions endpoint (`commerce_common/llm.py`). Provider-only features (server web search, hosted code execution, prompt caching, extended thinking) are dropped.


Two commerce agents built on an OpenAI-compatible LLM endpoint: a **shopping agent** a business embeds in its app for
customers, and a **merchant agent** its staff use to run the back office. Each is defined
once (prompt, skills, tool contracts, gates) and runs on one turn loop; four runnable verticals show both over the same libraries.

> [!NOTE]
> Every company, brand, product, and person here is fictional; the only company is ACME.
> Nothing places an order, charges a card, or changes a live listing: `checkout` renders
> the cart for the host to complete, and every merchant write is staged until a person
> approves it. Business rules, authorization, and compliance are the deployment's.

## Quick start: run the demos

Python 3.11+ and Node 22. Clone, install, add a key, run a vertical:

```bash
# from the extracted fork tarball (or: git clone commerce-agents-full-history.bundle commerce-agents)
cd commerce-agents
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt       # the seven packages and their pinned dependencies
cp .env.example .env                  # set LLM_BASE_URL, LLM_API_KEY, LLM_MODEL
(cd examples && npm ci)               # the eight web apps share one workspace
python scripts/run_demo.py retail     # API :8000 + storefront :3000
```

`--merchant` starts the portal instead of the storefront and `--all` starts both. The
verticals are `retail` (:3000, portal :3100), `travel` (:3001, :3101), `telecom` (:3002,
:3102), and `entertainment` (:3003, :3103); each README lists prompts to try on both surfaces.

## The two agents

The **shopping agent** searches, compares, plans, fills the cart, answers order and policy
questions, and remembers what a customer tells it. Its five flows are the skills in
[`shopping-agent/skills/`](shopping-agent/skills/); a deployment implements
[`StorefrontBackend`](shopping-agent/core/shopping_agent/backend.py) over its catalog,
cart, order, and policy systems.

The **merchant agent** explains performance, maintains listings, acts on inventory and order
alerts, prices and promotes, and drafts campaigns; every write is a staged change the host's
approval surface applies. Its five flows are the skills in [`merchant-agent/skills/`](merchant-agent/skills/);
a deployment implements [`MerchantBackend`](merchant-agent/core/merchant_agent/backend.py) over
its analytics, catalog, inventory, pricing, and campaign systems.

## Layout

| Directory | Contents | pip package, `import` name |
|---|---|---|
| [`commerce-common/`](commerce-common/) | What both roles share: config, fencing, memory, skills, grounding, presentation, executor frame, events | `commerce-common`, `commerce_common` |
| [`shopping-agent/core/`](shopping-agent/core/) | Shopping types, `StorefrontBackend`, prompt, tool contracts, gates, executor | `shopping-agent-core`, `shopping_agent` |
| [`shopping-agent/runtime-messages-api/`](shopping-agent/runtime-messages-api/) | `ShoppingAgent`, the turn loop on the Messages API | `shopping-agent-runtime`, `shopping_agent_runtime` |
| [`merchant-agent/core/`](merchant-agent/core/) | Merchant types, `MerchantBackend`, prompt, tool contracts, change guardrails, gates, executor | `merchant-agent-core`, `merchant_agent` |
| [`merchant-agent/runtime-messages-api/`](merchant-agent/runtime-messages-api/) | `MerchantAgent` and the analysis delegate on the Messages API | `merchant-agent-runtime`, `merchant_agent_runtime` |
| [`examples/`](examples/) | Four verticals, shared host code (`demo_common/`), shared web code (`web-shared/`) | — |
| [`docs/`](docs/) | `safety.md` (enforced rules), `backends.md` (mapping your systems), `deployment.md` (other platforms) | — |
| [`tests/`](tests/) | Cross-package suites; each package also has its own `tests/` | — |
| [`scripts/`](scripts/) | `install.sh`, `run_demo.py`, `smoke_chat.py`, `screenshot_tour.py`,  | — |

## Three ways to run an agent

**Messages API.** The reference loop; the examples are host applications around it:

```python
from pathlib import Path

from shopping_agent import ShoppingAgentConfig
from shopping_agent_runtime import ShoppingAgent

agent = ShoppingAgent(backend=your_backend, skills_dir=Path("shopping-agent/skills"),
                      config=ShoppingAgentConfig(brand_name="Your Store"))
async for event in agent.stream_turn(messages, session, state):
    ...   # text_delta, tool_call, ui, cart_update (change_update on the merchant side), turn_complete
await agent.update_memory(messages, session)   # memory extraction; this path only
```

The example hosts take the session id in an `X-Session-Id` header.

## Safety

Fencing, provenance gates, caps, memory validation, and the merchant approval gate run
inside the tool call and hold; grounding, the analysis budgets, and memory
extraction are runtime features. [`docs/safety.md`](docs/safety.md) lists each rule with its
module and paths, and what a deployment adds first; the examples have no authentication and
the MCP servers bind to loopback.

## Verticals

| Example | Storefront | Portal |
|---|---|---|
| [`examples/retail/`](examples/retail/) ACME | Search, comparison, plans, cart, checkout, memory over the built-in components | Digest, staged restocks and listing fixes, analysis delegate over a SQL view |
| [`examples/travel/`](examples/travel/) ACME Travel | Date-bound inventory and a `present_itinerary` extension | Occupancy calendar and date-window rate moves |
| [`examples/telecom/`](examples/telecom/) ACME Mobile | Account context, plan matrix, server-authored fee disclosures | Plan mix, price moves that state the lines affected, protected regulated fees |
| [`examples/entertainment/`](examples/entertainment/) ACME Tickets | Timed holds, waitlists, transfers, venue map, all-in fee disclosures | Event pacing, hold releases that add real capacity, fee-preserving price moves |

Each example's README has a `Try` section: the turns `scripts/smoke_chat.py` runs, and single
prompts with what a good answer does.

## Verify

```bash
ruff check . && ruff format --check . && pytest && python scripts/check.py
python scripts/verify_all.py                        # the line above plus deploy dry runs and web builds
python scripts/smoke_chat.py --vertical travel      # one live conversation; needs a key
```

`requirements-dev.txt` adds pytest and ruff. CI installs from it on two Python versions,
builds the eight web apps, and checks that the package names stay unregistered on the
public index (the pin files install them from their directories, never from the index). To confirm caching, read
`cache_read_input_tokens` from `turn_complete`, or the line each model call logs on its
runtime's logger: zero on a second turn means the prefix changed.

## Status of this fork

- Tested: the fork's own suite (970 passed, 1 skipped) and a local end-to-end run against a mock OpenAI-compatible server. It has **not** been run against a real model, so tool-calling quality on any specific provider is unproven.
- AI chat needs `LLM_BASE_URL`, `LLM_API_KEY` and `LLM_MODEL` for an endpoint you are allowed to use. With none set, the catalog, product pages, cart and portal widgets still work and chat does not.
- Still demos: fictional ACME data, in-memory sessions, mock checkout, no payments. Do not put customer logins or payment details on a plain-HTTP host.
- Removed: everything that needs Anthropic's services (Messages API client, Agent SDK, Managed Agents, the Claude Code plugin, server web search, hosted code execution, prompt caching, extended thinking). The original is the first commit in this history.
- The MCP servers (`shopping-agent/managed-agents/storefront-mcp-server`, `merchant-agent/managed-agents/merchant-mcp-server`) use a small in-repo implementation (`commerce_common/mcp_lite.py`) of the open MCP wire format, with bearer-token auth (`MCP_AUTH_TOKEN`).

## Run as one process (no Node on the host)

Build the storefront once as plain files, then let the Python API serve them on the same origin:

```bash
(cd examples/retail/storefront-web && STATIC_EXPORT=1 npm run build)      # writes out/
STOREFRONT_STATIC_DIR=$PWD/examples/retail/storefront-web/out \
  uvicorn retail.api.main:app --app-dir examples --host 0.0.0.0 --port 8787
```

Run one worker: sessions and carts live in process memory. Needs Python 3.11+ with `fastapi`, `uvicorn`, `pydantic` v2 and the other packages in `requirements.txt`.

## Deploying

Set `LLM_BASE_URL`, `LLM_API_KEY` and `LLM_MODEL`, or pass any object with `messages.stream` / `messages.create` as `client=`. See [`docs/deployment.md`](docs/deployment.md).

## MCP connectors

None ship; both agents reach your systems through the backend interfaces. Where an official
connector is the source of record, it is the integration target: analytics warehouses (Snowflake,
BigQuery, Databricks, Amplitude), finance (Stripe, Square, PayPal, QuickBooks), delivery (Slack, Google Drive, Gmail).
A commerce platform's own MCP server for catalog, cart, or checkout is called from a backend
method server-side; the
provenance gates stay in front of every write.

## Making it yours

- **Backend methods.** Each one calls your service server-side with the
  credential your host holds for the session; the model reads only the result. A flow whose
  steps have a fixed order enforces that order in the backend.
- **Read the backend guide.** [`docs/backends.md`](docs/backends.md) walks through
  identity and credentials, ordered flows, checkout, products with options, and figures
  your platform cannot supply.
- **The same interface covers other business shapes.** On a marketplace, seller is a search
  dimension and the merchant agent acts for the operator the session names. With account or
  contract pricing, the price quoted is the session account's. With no checkout of your
  own, turn the cart off or hand it to a quote, a purchase order, or a hosted checkout URL.
- **Checkout hands off.** The checkout card links to your own checkout route, or to the
  platform's hosted checkout URL (one per seller on a marketplace). The backend returns the
  URL and the host renders it; the model never sees it.
- **Start small.** A shopping pilot implements search and product details and stubs the
  rest; a stubbed method returns an unavailable result and changes no prompt bytes. A
  merchant pilot implements the eight read methods and has the writes refuse; digests and
  metrics then run with no write path.
- **Switch off what you do not have.** A system the business lacks entirely (no cart on a
  referral surface, no order tracking) is an `enable_*` switch turned off, which removes its
  tools, prompt lines, and grounding rule on every path; park the flows that need it under
  `skills/_staged/`. The merchant config has the same switches for listing edits, inventory,
  pricing, and campaigns.
- **Add your own.** A flow is a directory with a `SKILL.md` under either `skills/`. Domain
  UI is a `PresentationExtension` (the verticals ship seven). `brand_name`,
  `assistant_name`, and `brand_voice` on either config set the identity.

## License

Copyright 2026 Anthropic PBC. Licensed under the [Apache License 2.0](./LICENSE).
This is a reference implementation; it is not maintained and does not accept contributions.
