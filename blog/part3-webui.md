# Building CLMA: A Self-Verifying Multi-Agent Framework from Scratch

## Part 3: The Web UI Deep Dive — Making Multi-Agent Execution Visible

*Posted on May 4, 2026 · #WebUI #UX #RealTime #DarkMode #SSE*

---

A multi-agent system is inherently invisible. The user types a query, agents talk to each other inside the framework, and minutes later an answer appears. But *what happened in between?* Which agent ran? What did it produce? Did the framework iterate? Why did it take so long?

Without this visibility, multi-agent systems are black boxes — and developers (rightly) distrust black boxes.

The CLMA Web UI was designed from day one to answer one question: **"What is the framework doing right now?"** Every agent action, every score change, every iteration is streamed to the browser in real-time.

<!-- INSERT IMAGE: webui-dark-mode.png -->
<!-- Caption: CLMA Web UI — Dark theme with live execution flow graph, score gauge, and session management sidebar. The interface updates in real-time as agents complete their work. -->

<!-- INSERT IMAGE: webui-light-mode.png -->
<!-- Caption: Day mode — one-click theme toggle inverts the interface for well-lit environments. The same data, different visual context. -->

### SSE-Driven Architecture

The Web UI uses Server-Sent Events (SSE) rather than WebSockets or polling. Why SSE?

- **Unidirectional is enough.** The browser only receives events; it never needs to send commands to the backend mid-stream. SSE is simpler than WebSockets for this use case.
- **Standard HTTP.** No special server support needed — Flask's streaming responses work out of the box.
- **Automatic reconnection.** Browsers natively reconnect dropped SSE connections, which matters when backend processing can take 40+ seconds.

The event stream carries typed payloads:

```
event: agent_start
data: {"agent": "solver", "agent_label": "Solver", "iteration": 1, "timestamp": ...}

event: agent_complete
data: {"agent": "solver", "content_preview": "...", "duration_ms": 2340, ...}

event: iteration
data: {"iteration": 2, "scores": {"reasonableness": 0.75, ...}, ...}

event: done
data: {"result": {"content": "...", "score": {...}}, ...}
```

Each event type triggers a different UI update — no polling, no manual refresh, no "waiting for response" spinner that tells you nothing.

### Score Gauge

<!-- INSERT IMAGE: overall-score-screenshot.png -->
<!-- Caption: The score gauge consolidates three evaluation dimensions into one visual readout. Green = passing (≥0.7), yellow = marginal, red = needs improvement. -->

The score gauge is the most-watched element in the UI. It shows:

- **Overall score** as a large circular gauge (green/yellow/red)
- **Three sub-scores** as animated bars (reasonableness, executability, satisfaction)
- **Iteration count** showing which round we're on

The gauge animates on each score update, giving a visceral sense of "getting better" as the framework iterates. This was a deliberate design choice — seeing the needle move from 0.66 to 0.70 across iterations builds trust in the process.

### Execution Timeline & Flow Graph

<!-- INSERT IMAGE: output-box-screenshot.png -->
<!-- Caption: After execution completes, the output panel shows the final code with syntax highlighting, execution results, and timing information. -->

The flow graph is rendered as an inline SVG that updates in real-time as agents complete. Each agent appears as a node with:

- **Agent name and icon** (Solver → 🛠, Verifier → 🔍, Evaluator → 📊)
- **Duration** — how long this agent took
- **Status** — running, completed, or failed
- **Token usage** — prompt/completion tokens for this call

When the mode is AAN (Adaptive Agent Network), the flow graph adapts its layout based on the Router's topology decision — showing a single node for Direct mode, a linear chain for Chain mode, parallel branches for Parallel mode, and a recursive tree for Tree mode.

### Session Management Sidebar

The sidebar lists all past sessions, grouped by date:

- Click any session to reload its full output and scores
- Sessions show query preview, score summary, and mode used
- Today's sessions have a separate summary (total queries, completions, tokens)

This turns CLMA into a persistent workspace rather than a one-shot chatbot. You can compare how different modes handled the same query, revisit past iterations, and track scoring trends over time.

### Configuration Panels

CLMA supports deep runtime configuration without restarting the server. Three settings panels are accessible from the UI:

<!-- INSERT IMAGE: api-settings-screenshot.png -->
<!-- Caption: API Configuration panel — switch between 5+ LLM providers, configure API keys, base URLs, and model selection. Zero-downtime switching. -->

**API Configuration** lets you:
- Switch between OpenAI, Anthropic, DeepSeek, Gemini, and local models at runtime
- Configure API keys, base URLs, and model names
- Test the connection before submitting queries

<!-- INSERT IMAGE: rules-settings-screenshot.png -->
<!-- Caption: Rules Configuration — YAML-based rule engine that customizes how the framework interprets different query types. -->

**Rules Configuration** exposes the C++ rule engine's patterns:
- Define custom validation methods per query type
- Configure automatic code execution triggers
- Set sandbox tiering rules by language

<!-- INSERT IMAGE: tools-settings-screenshot.png -->
<!-- Caption: Tools Configuration — enable/disable execution environments (Python, C++, Shell, Node.js) and set sandbox timeout limits. -->

**Tools Configuration** manages:
- Which execution environments are enabled (Python, C++, Shell, Node.js)
- Sandbox timeout limits
- Token budget and max iterations

### Theme System

The UI defaults to dark mode (designed for late-night coding sessions), with a one-click toggle to invert to light mode. The toggle uses a CSS filter approach — `invert(1) hue-rotate(180deg)` — which works across all elements without needing separate light/dark CSS variables.

<!-- INSERT IMAGE: webui-dark-mode.png AND webui-light-mode.png in a comparison layout -->
<!-- Caption: Dark mode (left) vs light mode (right). No refresh needed, instant toggle. -->

### Design Philosophy: Visibility Builds Trust

The most important design lesson from building the CLMA UI: **users trust systems they can watch.** A system that produces output in a black box is always suspect — no matter how good the output is. A system that shows every step, every agent, every score change, and every iteration builds confidence through transparency.

When a user sees:

1. Router analyzes the query → decides it's a Chain topology
2. Refiner restructures the task
3. Solver generates 1,200 lines of code in 4.2 seconds
4. Verifier identifies 3 potential issues
5. Score = 0.66 → below threshold → iterating
6. Second pass addresses all 3 issues
7. Score = 0.92 → passing → done

...they don't just trust the output more. They understand *why* the framework made the decisions it did. And when something goes wrong, they know where to look.

**Up next in Part 4 (final):** *Lessons Learned — what I'd do differently, the mistakes that taught me the most, and where CLMA goes from here.*

---

*CLMA is open source on [GitHub](https://github.com/kriely/CLMA). Part 1 covered the core architecture and self-verification problem. Part 2 covered the evolution of execution modes.*

*Part 4 (final) covers lessons learned and future plans. Stay tuned.*

> **A brief note on how this was built:** Every line of CLMA — from the C++17 DAG engine to the SVG gauges in the Web UI — was written with the help of Hermes (my AI agent companion) running on DeepSeek's API. I'm a developer with ideas, not a big team with a budget. Hermes and DeepSeek are the tools that let me ship those ideas.  
> *Because ideas shouldn't wait for the perfect stack — they should just be built.*
