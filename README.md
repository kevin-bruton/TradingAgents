<p align="center">
  <img src="assets/TauricResearch.png" style="width: 60%; height: auto;">
</p>

<div align="center" style="line-height: 1;">
  <a href="https://arxiv.org/abs/2412.20138" target="_blank"><img alt="arXiv" src="https://img.shields.io/badge/arXiv-2412.20138-B31B1B?logo=arxiv"/></a>
  <a href="https://discord.com/invite/hk9PGKShPK" target="_blank"><img alt="Discord" src="https://img.shields.io/badge/Discord-TradingResearch-7289da?logo=discord&logoColor=white&color=7289da"/></a>
  <a href="./assets/wechat.png" target="_blank"><img alt="WeChat" src="https://img.shields.io/badge/WeChat-TauricResearch-brightgreen?logo=wechat&logoColor=white"/></a>
  <a href="https://x.com/TauricResearch" target="_blank"><img alt="X Follow" src="https://img.shields.io/badge/X-TauricResearch-white?logo=x&logoColor=white"/></a>
  <br>
  <a href="https://github.com/TauricResearch/" target="_blank"><img alt="Community" src="https://img.shields.io/badge/Join_GitHub_Community-TauricResearch-14C290?logo=discourse"/></a>
</div>

<div align="center">
  <!-- Keep these links. Translations will automatically update with the README. -->
  <a href="https://www.readme-i18n.com/TauricResearch/TradingAgents?lang=de">Deutsch</a> | 
  <a href="https://www.readme-i18n.com/TauricResearch/TradingAgents?lang=es">Español</a> | 
  <a href="https://www.readme-i18n.com/TauricResearch/TradingAgents?lang=fr">français</a> | 
  <a href="https://www.readme-i18n.com/TauricResearch/TradingAgents?lang=ja">日本語</a> | 
  <a href="https://www.readme-i18n.com/TauricResearch/TradingAgents?lang=ko">한국어</a> | 
  <a href="https://www.readme-i18n.com/TauricResearch/TradingAgents?lang=pt">Português</a> | 
  <a href="https://www.readme-i18n.com/TauricResearch/TradingAgents?lang=ru">Русский</a> | 
  <a href="https://www.readme-i18n.com/TauricResearch/TradingAgents?lang=zh">中文</a>
</div>

---

# TradingAgents: Multi-Agents LLM Financial Trading Framework 

> 🎉 **TradingAgents** officially released! We have received numerous inquiries about the work, and we would like to express our thanks for the enthusiasm in our community.
>
> So we decided to fully open-source the framework. Looking forward to building impactful projects with you!

<div align="center">
<a href="https://www.star-history.com/#TauricResearch/TradingAgents&Date">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=TauricResearch/TradingAgents&type=Date&theme=dark" />
   <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/svg?repos=TauricResearch/TradingAgents&type=Date" />
   <img alt="TradingAgents Star History" src="https://api.star-history.com/svg?repos=TauricResearch/TradingAgents&type=Date" style="width: 80%; height: auto;" />
 </picture>
</a>
</div>

<div align="center">

🚀 [TradingAgents](#tradingagents-framework) | ⚡ [Installation & CLI](#installation-and-cli) | 🎬 [Demo](https://www.youtube.com/watch?v=90gr5lwjIho) | 📦 [Package Usage](#tradingagents-package) | 🤝 [Contributing](#contributing) | 📄 [Citation](#citation)

</div>

## TradingAgents Framework

TradingAgents is a multi-agent trading framework that mirrors the dynamics of real-world trading firms. By deploying specialized LLM-powered agents: from fundamental analysts, sentiment experts, and trade planners, to trader, risk management team, the platform collaboratively evaluates market conditions and informs trading decisions. Moreover, these agents engage in dynamic discussions to pinpoint the optimal strategy.

<p align="center">
  <img src="assets/schema.png" style="width: 100%; height: auto;">
</p>

> TradingAgents framework is designed for research purposes. Trading performance may vary based on many factors, including the chosen backbone language models, model temperature, trading periods, the quality of data, and other non-deterministic factors. [It is not intended as financial, investment, or trading advice.](https://tauric.ai/disclaimer/)

Our framework decomposes complex trading tasks into specialized roles. This ensures the system achieves a robust, scalable approach to market analysis and decision-making.

### Analyst Team
- Fundamentals Analyst: Evaluates company financials and performance metrics, identifying intrinsic values and potential red flags.
- Sentiment Analyst: Analyzes social media and public sentiment using sentiment scoring algorithms to gauge short-term market mood.
- News Analyst: Monitors global news and macroeconomic indicators, interpreting the impact of events on market conditions.
- Trade Planner: Utilizes technical indicators (like MACD and RSI) to detect trading patterns and forecast price movements.

<p align="center">
  <img src="assets/analyst.png" width="100%" style="display: inline-block; margin: 0 2%;">
</p>

### Researcher Team
- Comprises both bullish and bearish researchers who critically assess the insights provided by the Analyst Team. Through structured debates, they balance potential gains against inherent risks.

<p align="center">
  <img src="assets/researcher.png" width="70%" style="display: inline-block; margin: 0 2%;">
</p>

### Trader Agent
- Composes reports from the analysts and researchers to make informed trading decisions. It determines the timing and magnitude of trades based on comprehensive market insights.

<p align="center">
  <img src="assets/trader.png" width="70%" style="display: inline-block; margin: 0 2%;">
</p>

### Risk Management and Portfolio Manager
- Continuously evaluates portfolio risk by assessing market volatility, liquidity, and other risk factors. The risk management team evaluates and adjusts trading strategies, providing assessment reports to the Portfolio Manager for final decision.
- The Portfolio Manager approves/rejects the transaction proposal. If approved, the order will be sent to the simulated exchange and executed.

<p align="center">
  <img src="assets/risk.png" width="70%" style="display: inline-block; margin: 0 2%;">
</p>

## Installation and CLI

### Installation

Clone TradingAgents:
```bash
git clone https://github.com/TauricResearch/TradingAgents.git
cd TradingAgents
```

Create a virtual environment in any of your favorite environment managers. Here are some indications if you've installed `uv`:
```bash
uv venv
```

Activate the virtual environment:
```bash
venv/Scripts/activate.bat
```

Install dependencies:
```bash
uv sync
```

### Required APIs

You will also need the FinnHub API for financial data. All of our code is implemented with the free tier.
```bash
export FINNHUB_API_KEY=$YOUR_FINNHUB_API_KEY
```

You will need the OpenAI API for all the agents.
```bash
export OPENAI_API_KEY=$YOUR_OPENAI_API_KEY
```

If you plan to use OpenRouter as your LLM provider, you'll also need:
```bash
export OPENROUTER_API_KEY=$YOUR_OPENROUTER_API_KEY
```

### CLI Usage

You can also try out the CLI directly by running:
```bash
python -m cli.main
```
You will see a screen where you can select your desired tickers, date, LLMs, research depth, etc.

<p align="center">
  <img src="assets/cli/cli_init.png" width="100%" style="display: inline-block; margin: 0 2%;">
</p>

An interface will appear showing results as they load, letting you track the agent's progress as it runs.

<p align="center">
  <img src="assets/cli/cli_news.png" width="100%" style="display: inline-block; margin: 0 2%;">
</p>

<p align="center">
  <img src="assets/cli/cli_transaction.png" width="100%" style="display: inline-block; margin: 0 2%;">
</p>

## Web Frontend (HTMX/FastAPI)

In addition to the CLI, a new web-based frontend is available to visualize the agent communication process in real-time. It allows you to set configuration parameters, start the trading analysis, and observe the step-by-step execution of agents and tools, including their outputs and any errors.

### New: User Position Awareness

You can now optionally specify your current position (None / Long / Short) along with existing stop-loss and take-profit levels. These inputs are incorporated by the Trade Planner and Risk / Portfolio Manager to:
 - Decide whether to maintain, adjust, or close the current position
 - Recommend flipping (e.g., long -> short) only when risk/reward justifies transaction costs
 - Adjust existing stop-loss / take-profit levels (tighten, widen, trail, move to breakeven)
 - Avoid unnecessary churn when changes would not exceed the trading cost threshold

If you leave these fields blank or select "No Open Position", the system will generate fresh trade planning levels as usual.

### Running the Web Frontend

1.  Ensure you have installed all dependencies using `uv sync`.
2.  Navigate to the project root directory in your terminal.
3.  Start the FastAPI server:
    ```bash
    uvicorn webapp.main:app --reload
    ```
4.  Open your web browser and go to `http://127.0.0.1:8000`.
5.  Enter a company symbol (e.g., `AAPL`) in the configuration form and click "Start Process" to begin the analysis.
6.  (Optional) If you have an open position, select Long/Short and enter existing stop-loss / take-profit so the final decision can include management guidance.

### Real-Time Updates (WebSockets)

The web frontend now uses a WebSocket channel (`/ws`) for real-time status and progress updates instead of relying solely on periodic HTTP polling.

Benefits:
- Lower latency updates as each agent completes
- Reduced network overhead vs. 2s polling
- Automatic retry with exponential backoff if the socket drops
- Graceful fallback to legacy polling if WebSockets are unavailable

Client behavior:
- On connection, the server sends an `init` payload with the current execution tree and progress.
- Subsequent incremental updates are sent as `status_update` messages.
- When you click an item, the existing HTMX request still works; alternatively, the client can request content over the socket using `{ "action": "get_content", "item_id": "..." }`.

If you need to disable WebSockets (e.g., for debugging a proxy), you can block the `/ws` path and the client will automatically revert to polling.

### Rendered Reports (Markdown Support)

Agent-generated reports (analysis summaries, debate histories, plans, and risk assessments) are produced in Markdown. The web frontend now renders these Markdown documents as styled HTML instead of showing raw markup. This includes support for:

- Headings, emphasis, lists, and blockquotes
- Tables (for structured metrics)
- Fenced code blocks and inline code

Security: Markdown is sanitized server‑side using `bleach` to strip unsafe tags/attributes while preserving semantic structure. If you need to extend allowed tags (e.g., to permit additional formatting), modify `ALLOWED_TAGS` / `ALLOWED_ATTRIBUTES` in `webapp/main.py`.

### LLM Invocation Reliability (Automatic Retry Layer)

Many agent nodes perform JSON-heavy LLM calls that can occasionally fail due to transient network issues (timeouts, dropped connections) or incomplete JSON payloads returned by the provider. To reduce user-facing errors and noisy red states in the execution tree, TradingAgents wraps model calls with a lightweight exponential backoff retry helper.

Core implementation: `safe_invoke_llm` in `tradingagents/agents/utils/safe_llm.py`.

Default behavior:
- Retries up to 4 attempts (configurable) on a targeted set of transient exceptions.
- Backoff: exponential (base 0.75s) with ±30% jitter, capped at 8s.
- Immediate propagation for non-transient errors (logical / prompt / auth failures aren’t retried).

Transient exception classes handled:
- `json.JSONDecodeError` (malformed or truncated JSON)
- `httpx.TimeoutException`
- `httpx.ConnectError`
- `httpx.NetworkError` (if available in the installed httpx version)
- Heuristic: any exception message containing both `Expecting value` and `json` (covers provider-specific wrappers)

Why this matters:
- Prevents single flaky decode from aborting an entire multi-agent debate or risk evaluation phase.
- Smooths over brief provider-side instabilities and network blips without user intervention.
- Reduces false-negative failure attribution in the UI.

Customization:
You can supply a custom `LLMRetryConfig` if a node needs different resilience parameters:
```python
from tradingagents.agents.utils.safe_llm import safe_invoke_llm, LLMRetryConfig

cfg = LLMRetryConfig(max_attempts=6, base_delay=0.5, max_delay=10.0, jitter=0.25)
response = safe_invoke_llm(llm, prompt, cfg)
```

Disabling or tightening:
- To effectively disable retries for debugging, set `max_attempts=1`.
- For latency-sensitive quick-think paths, you can lower `max_attempts` or `max_delay`.

Logging & observability (future enhancement):
- Currently, retries are silent except for aggregate timing impact. If you need visibility, wrap `safe_invoke_llm` and add structured logging around each attempt.

Edge cases not retried:
- Authentication / quota errors
- Deterministic validation failures in downstream parsing
- Prompt formatting errors (these should be fixed at the source)

If you encounter a failure pattern you believe should be considered transient, you can extend `TRANSIENT_EXCEPTION_TYPES` inside `safe_llm.py`.


## TradingAgents Package

### Implementation Details

We built TradingAgents with LangGraph to ensure flexibility and modularity. We utilize `o1-preview` and `gpt-4o` as our deep thinking and fast thinking LLMs for our experiments. However, for testing purposes, we recommend you use `o4-mini` and `gpt-4.1-mini` to save on costs as our framework makes **lots of** API calls.

### Python Usage

To use TradingAgents inside your code, you can import the `tradingagents` module and initialize a `TradingAgentsGraph()` object. The `.propagate()` function will return a decision. You can run `main.py`, here's also a quick example:

```python
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

ta = TradingAgentsGraph(debug=True, config=DEFAULT_CONFIG.copy())

# forward propagate
_, decision = ta.propagate("NVDA", "2024-05-10")
print(decision)
```

You can also adjust the default configuration to set your own choice of LLMs, debate rounds, etc.

```python
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

# Create a custom config
config = DEFAULT_CONFIG.copy()
config["deep_think_llm"] = "gpt-4.1-nano"  # Use a different model
config["quick_think_llm"] = "gpt-4.1-nano"  # Use a different model
config["max_debate_rounds"] = 1  # Increase debate rounds
config["online_tools"] = True # Use online tools or cached data

# Initialize with custom config
ta = TradingAgentsGraph(debug=True, config=config)

# forward propagate
_, decision = ta.propagate("NVDA", "2024-05-10")
print(decision)
```

> For `online_tools`, we recommend enabling them for experimentation, as they provide access to real-time data. The agents' offline tools rely on cached data from our **Tauric TradingDB**, a curated dataset we use for backtesting. We're currently in the process of refining this dataset, and we plan to release it soon alongside our upcoming projects. Stay tuned!

You can view the full list of configurations in `tradingagents/default_config.py`.

## Persistent Memory and Learning

To allow the agents to learn from the success or failure of previous decisions, TradingAgents includes a persistent memory mechanism.

Each agent's reflections and the "lessons learned" from past trading sessions are stored on disk. This allows the system to build a rich, searchable history of its actions and their consequences, enabling more informed decisions in the future.

- **Storage**: The memory is managed by the `FinancialSituationMemory` class in `tradingagents/agents/utils/memory.py` and is persisted to the `./memory_store/` directory using a local ChromaDB database.
- **Learning Loop**: After a trade, a `Reflector` agent analyzes the outcome (profit or loss) and generates a "lesson." This lesson is stored in the memory, linked to the market conditions at the time. Before the next trade, agents query this memory for similar past situations to retrieve relevant lessons, which are then used to inform their decision-making process.

### Inspecting the Memory

You can inspect the contents of the persistent memory to see what the agents have learned. To do this, run the memory utility script from the root of the project:

```bash
python -m tradingagents.agents.utils.memory
```

The first time you run this, it will populate the memory with example data. Subsequent runs will load and display the data from the `memory_store` directory, demonstrating that the memory persists across sessions.

## Contributing

We welcome contributions from the community! Whether it's fixing a bug, improving documentation, or suggesting a new feature, your input helps make this project better. If you are interested in this line of research, please consider joining our open-source financial AI research community [Tauric Research](https://tauric.ai/).

## Citation

Please reference our work if you find *TradingAgents* provides you with some help :)

```
@misc{xiao2025tradingagentsmultiagentsllmfinancial,
      title={TradingAgents: Multi-Agents LLM Financial Trading Framework}, 
      author={Yijia Xiao and Edward Sun and Di Luo and Wei Wang},
      year={2025},
      eprint={2412.20138},
      archivePrefix={arXiv},
      primaryClass={q-fin.TR},
      url={https://arxiv.org/abs/2412.20138}, 
}
```
