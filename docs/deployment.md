# Deployment

The turn loop calls `commerce_common.llm.AsyncLLMClient`, an OpenAI-compatible
chat-completions client. Configure it with environment variables:

| Variable | Meaning | Default |
|---|---|---|
| `LLM_BASE_URL` | endpoint root, ending in `/v1` or equivalent | `https://api.groq.com/openai/v1` |
| `LLM_API_KEY` | bearer token | none |
| `LLM_MODEL` | model id used for the turn loop and memory extraction | `llama-3.3-70b-versatile` |

Examples of base URLs: OpenRouter `https://openrouter.ai/api/v1`, Google
`https://generativelanguage.googleapis.com/v1beta/openai`, local Ollama
`http://localhost:11434/v1`.

The model must support tool calling. Per-role overrides: pass `model=` and `memory_model=`
in the agent config.

To use another client, pass `client=` to `ShoppingAgent` or `MerchantAgent`; it needs
`messages.stream(**request)` (async context manager yielding content-block events, with
`get_final_message()`) and `messages.create(**request)`.

Dropped relative to the upstream project: server-side web search, hosted code execution
(use `MerchantBackend.execute_analysis_query`), prompt caching markers, and extended
thinking. The `enable_web_search` and `analysis_use_code_execution` switches have no effect.

Hosting: `uvicorn --app-dir examples retail.api.main:app` runs an example API; the example
hosts accept only loopback Host headers unless `DEMO_ALLOWED_HOSTS` lists the public host
name, and have no authentication, so put your own in front of any public deployment.
