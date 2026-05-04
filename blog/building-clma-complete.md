# Building CLMA: A Self-Verifying Multi-Agent Framework from Scratch

*Posted on May 4, 2026 · #LLM #MultiAgent #CodeGeneration #OpenSource #SystemDesign #WebUI #SSE*

*All code is open source on GitHub: **[github.com/kriely/CLMA](https://github.com/kriely/CLMA)***

---

## Part 1: The Problem — LLMs Can't Self-Verify

### The One-Off Generation Trap

If you've spent any time using ChatGPT, Claude, or GitHub Copilot for coding, you've experienced this cycle: ask → get code → try to run → it fails → paste error → get fix → something else breaks → lather, rinse, repeat.

Each iteration costs you time, context switching, and cognitive energy. The LLM itself never knows whether its output actually *works* — it just predicts tokens. It produces code, but it cannot *verify* code.

This is the fundamental asymmetry of LLM-assisted coding today: **generation is cheap, but verification is manual**. And as tasks grow from "write a sort function" to "build a microservice architecture with authentication, rate limiting, and a PostgreSQL backend", the gap between "code that looks right" and "code that actually works" becomes a chasm.

Most existing solutions paper over this gap:
- **Direct prompting** — ask once, hope for the best
- **Chat-based refinement** — human-in-the-loop for every error
- **Agent frameworks** — chain multiple LLM calls, but still no automated quality gate
- **RAG + tools** — give the LLM more context, but still no feedback loop

None of them ask the hard question: *How do you know the output is good?*

### The Seed of an Idea

The idea for CLMA (Closed-Loop Multi-Agent) came from a simple observation: **if one LLM call is unreliable, and a human checking its output is slow, what if we let a *second* LLM call verify the first one's output — and then give that feedback back to the first one to improve?**

That's the core loop: Solver produces code → Verifier checks it → Refiner improves it → repeat until scores pass a threshold. No human in the middle.

But turning that simple idea into a working system took months of iteration, dozens of wrong turns, and a fundamental rethinking of what "multi-agent" actually means.

### The Core Architecture

CLMA is built in three layers:

```
┌─────────────────────────────────────┐
│  Web UI (Flask + SSE + SVG)         │
│  Real-time flow graphs & gauges     │
├─────────────────────────────────────┤
│  Python Interface (pybind11)        │
│  Agent orchestration & scoring      │
├─────────────────────────────────────┤
│  C++17 Core Engine                  │
│  Orchestrator · DAG · Rule Engine   │
│  Token Monitor · Plugin Manager     │
└─────────────────────────────────────┘
```

The C++ core handles performance-critical paths — DAG processing, rule matching, and token tracking — while the Python layer manages agent orchestration, LLM API calls, and scoring logic. The Web UI communicates via Server-Sent Events for real-time streaming of every agent action.

### The Five Agent Roles

Every query passes through some subset of these five agents:

| Agent | Role | Prompt Template |
|---|---|---|
| **Refiner** | Reformulates the user's query into a structured task. Extracts implicit requirements. | "Restate the task clearly. Identify edge cases." |
| **Reasoner** | Produces a solution strategy without writing code. Plans the approach. | "Outline the algorithm. Consider time/space complexity." |
| **Solver** | Generates the actual implementation code. | "Write production-quality code following the plan." |
| **Verifier** | Reviews the Solver's output. Checks correctness, completeness, and potential bugs. | "Review this code. List issues by severity." |
| **Evaluator** | Scores the final output on three dimensions. Decides if iteration is needed. | "Rate this solution on reasonableness, executability, and satisfaction." |

The Evaluator produces a three-dimensional score:

- **Reasonableness** (0–1): Does the approach make sense for the problem?
- **Executability** (0–1): Would the code actually run without errors?
- **Satisfaction** (0–1): Does the output fully address the user's query?

Overall = Reasonableness × 0.4 + Executability × 0.4 + Satisfaction × 0.2

If the overall score falls below a configurable threshold (default 0.7), the framework loops back: Refiner receives Verifier's feedback, Solver generates an improved version, Verifier checks again, and Evaluator re-scores. This continues up to `max_iterations` (default 3).

### Why Three Scores?

A single score is too coarse for meaningful iteration. Consider:

- High reasonableness + low executability → the approach is sound but the implementation has bugs → Verifier should focus on code issues
- Low reasonableness + high executability → the code runs but solves the wrong problem → Reasoner needs to rethink the approach
- Low satisfaction → the output is technically correct but misses the user's intent → Refiner should re-examine the query

By separating the three dimensions, each agent gets targeted feedback about *what* specifically needs improvement, rather than a vague "score too low, try again."

---

## Part 2: From Single Loop to Adaptive Network — The Evolution of Execution Modes

### The Naive First Attempt

When I started CLMA, the architecture was embarrassingly simple: a linear pipeline. Take the user's query → pass it through five agents in sequence → output the result. No iteration, no scoring, no feedback.

It didn't work well.

The first real version was the **Single Closed Loop** — and it looked like this:

![Single Loop execution flow — the framework iterates through Refiner → Reasoner → Solver → Verifier → Evaluator until scores pass the threshold.](https://raw.githubusercontent.com/kriely/CLMA/main/blog/images/single执行流程.gif)

```
┌─────────────────────────────────────────────────────────┐
│  Query                                                    │
│    ↓                                                      │
│  Refiner → Reasoner → Solver → Verifier → Evaluator      │
│    ↑                                          │           │
│    └────── score < threshold? ───────────────┘           │
└─────────────────────────────────────────────────────────┘
```

**The loop:** Solver generates code → Verifier reviews it → if Evaluator scores below threshold, Refiner gets the feedback and the loop restarts. Each iteration builds on the previous one's Verifier feedback.

This was the first time I saw the self-verification idea actually working. A query like "implement a thread-safe LRU cache" would start with a reasonable-but-flawed first attempt, then refine through 2–3 iterations into production-quality code — all without human intervention.

But the Single Loop had a glaring problem: **it treated every query the same way.** A "hello world" query and a "design a distributed rate limiter" query both went through the same 5-agent pipeline with the same iteration logic. The trivial query took 8 seconds when it should have taken 2. The complex query took 40 seconds when it needed more structured decomposition.

### DAG Mode: Parallel Decomposition

![DAG Mode — the C++ DAG processor decomposes tasks into parallel sub-tasks, executing them concurrently.](https://raw.githubusercontent.com/kriely/CLMA/main/blog/images/打开DAG后的single执行.gif)

The first major iteration was **DAG (Directed Acyclic Graph) mode.** Instead of running agents sequentially, the C++ DAG processor would:

1. Parse the user's query to identify independent sub-tasks
2. Build a dependency graph
3. Execute parallel sub-tasks concurrently
4. Aggregate and verify the combined output

For multi-component tasks like "build a REST API with auth, CRUD endpoints, and a PostgreSQL schema," DAG mode decomposes the three components, solves them in parallel, and merges the results. This cut total time from 40s (serial) to ~20s (parallel) for the same quality.

**The trade-off:** DAG mode works well for clearly separable tasks — components with clean interfaces and independent logic. But for tasks that need deep reasoning about a single complex problem, the bottleneck shifts from parallelism to iteration quality.

### Nested Multi-Loop: Strategy + Execution

Some problems are too complex for a single loop. Consider "design and implement a distributed task scheduler with leader election, worker pools, and fault tolerance." You need *strategic decisions* first (consensus protocol? Raft or Paxos? task distribution model?), *then* implementation.

The Nested Multi-Loop architecture addresses this with two concentric loops:

![Nested Multi-Loop — outer strategy loop plans the architecture, inner execution loop implements each component.](https://raw.githubusercontent.com/kriely/CLMA/main/blog/images/multi执行流程.gif)

- **Outer loop (strategy):** Planner → Commander → Producer → Verifier → Evaluator. This loop handles architectural decisions, component decomposition, and high-level design.
- **Inner loop (execution):** Refiner → Reasoner → Solver → Verifier → Evaluator. Runs *inside* each component, iterating on implementation quality.

The outer loop's output becomes the inner loop's input for each component. The inner loop's results feed back into the outer loop's Verifier. This hierarchical iteration catches both design-level and implementation-level issues in a single pass.

**The pain point:** Nested Multi-Loop is powerful but slow. A single query can take 40–60 seconds to complete, and the flow graph visualization becomes dense enough to require zoom and pan controls.

### Adaptive Agent Network: Self-Organizing Topology

The biggest insight came from watching how users actually interacted with the four modes. Most users defaulted to one mode — usually Single Loop — and never switched. The framework had all these execution modes, but no one was using them because *choosing the right mode* required understanding the framework's internals.

**What if the framework could choose for you?**

That's the Adaptive Agent Network (AAN):

![AAN Mode — the Router Agent analyzes the query and selects the optimal execution topology automatically.](https://raw.githubusercontent.com/kriely/CLMA/main/blog/images/aan执行流程.gif)

AAN introduces a **Router Agent** that runs before execution begins. The Router analyzes the query and picks from four topologies:

| Topology | When It's Chosen | What It Does |
|---|---|---|
| **Direct** | Trivial queries (effective length < 15 chars, no code intent) | Single Solver call → score → done. ~2s latency. |
| **Chain** | Most medium-complexity queries | Refiner → Reasoner → Solver → Verifier → Evaluator, with iterative score feedback (up to 3 rounds). |
| **Parallel** | Queries with explicit parallel keywords ("分别", "both", "multiple") | Solves modules concurrently, then merges via Integrator. |
| **Tree** | Complex architectural queries ("architecture", "system", "subsystem") | Recursive binary decomposition: splits the problem into sub-problems, solves each leaf independently, merges bottom-up. |

The Router uses a heuristic-based classifier rather than another LLM call (which would be expensive and defeat the purpose):

```python
effective_len = len(query) + cjk_count  # Chinese chars have higher info density
has_code_intent = any(kw in query for kw in ["写", "implement", "build", ...])
is_trivial = effective_len < 15 and not has_code_intent
```

### The AAN Chain Breakthrough

The most interesting evolution was the Chain topology itself. Initially, Chain was a single-pass pipeline — run all five agents once, score once, done. No iteration. The thinking was: "If the Router already selected Chain, the query should be straightforward enough for one pass."

That was wrong.

Even medium-complexity queries — "build a subset of Photoshop in HTML" — need iterative refinement. The first pass might cover basic features (pen tool, color picker, save) but miss important ones (layers, selection tools, undo/redo). Without iteration, the Verifier's feedback is wasted — the user sees the first attempt, and that's that.

So Chain evolved too. The current implementation runs the same closed-loop iteration as the original Single Loop:

```
Round 1: Refiner → Reasoner → Solver → Verifier → Evaluator → score = 0.66 ❌
Round 2: Refiner (with Verifier feedback) → Reasoner → Solver → Verifier → Evaluator → score = 0.70 ✅ → Output
```

Each round passes the previous Verifier's feedback to the Refiner, which uses it to guide the Solver toward specific improvements. The iteration stops when scores meet the threshold or max rounds are reached.

### The Current Mode Matrix

| Mode | Use Case | Typical Time (small task) | Best For |
|---|---|---|---|
| **Fast Path** | "hello world", trivial math | ~1–3s | Greetings, trivial queries |
| **Single Loop** | Function implementations, algorithms | ~8–20s | Well-defined coding tasks |
| **DAG** | Multi-component features | ~20–45s | APIs, services, parallel work |
| **Nested Multi-Loop** | System architecture | ~45–90s | Full-stack design + implementation |
| **AAN** | Whatever you throw at it | 2–90s | Mixed workloads, adaptive routing |

> **💡 Tip:** The times above reflect small-to-medium tasks. As project complexity grows — longer code output, deeper iteration loops, more parallel sub-tasks — actual processing time scales proportionally. A large system architecture query under Nested Multi-Loop can take 2–3 minutes, while a simple bug fix under Fast Path resolves in seconds. Choose your architecture mode based on the *scope of the task*, not the *clock on the wall*.

### What I Learned About Mode Design

1. **Don't make users choose.** AAN was the most recent addition for a reason — it took seeing users stick to one mode before realizing that choice itself is a UX failure. The framework should infer what the user needs.

2. **Iteration > Parallelism for quality.** DAG's parallel execution cuts wall-clock time, but it's the Single Loop's iterative feedback that actually improves output quality. The best combination is both — AAN Chain's closure-based iteration with DAG's parallel sub-task execution.

3. **Benchmark everything.** Without a scoring system, you can't tell whether a new mode is actually better. The three-dimensional score (reasonableness × executability × satisfaction) made it possible to compare modes quantitatively.

---

## Part 3: The Web UI Deep Dive — Making Multi-Agent Execution Visible

A multi-agent system is inherently invisible. The user types a query, agents talk to each other inside the framework, and minutes later an answer appears. But *what happened in between?* Which agent ran? What did it produce? Did the framework iterate? Why did it take so long?

Without this visibility, multi-agent systems are black boxes — and developers (rightly) distrust black boxes.

The CLMA Web UI was designed from day one to answer one question: **"What is the framework doing right now?"** Every agent action, every score change, every iteration is streamed to the browser in real-time.

![CLMA Web UI — Dark theme with live execution flow graph, score gauge, and session management sidebar.](https://raw.githubusercontent.com/kriely/CLMA/main/blog/images/webui-dark-mode.png)

![Day mode — one-click theme toggle inverts the interface for well-lit environments.](https://raw.githubusercontent.com/kriely/CLMA/main/blog/images/webui-light-mode.png)

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

![The score gauge consolidates three evaluation dimensions into one visual readout. Green = passing (≥0.7), yellow = marginal, red = needs improvement.](https://raw.githubusercontent.com/kriely/CLMA/main/blog/images/overall-score-screenshot.png)

The score gauge is the most-watched element in the UI. It shows:

- **Overall score** as a large circular gauge (green/yellow/red)
- **Three sub-scores** as animated bars (reasonableness, executability, satisfaction)
- **Iteration count** showing which round we're on

The gauge animates on each score update, giving a visceral sense of "getting better" as the framework iterates. This was a deliberate design choice — seeing the needle move from 0.66 to 0.70 across iterations builds trust in the process.

### Execution Timeline & Flow Graph

![After execution completes, the output panel shows the final code with syntax highlighting, execution results, and timing information.](https://raw.githubusercontent.com/kriely/CLMA/main/blog/images/output-box-screenshot.png)

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

![API Configuration panel — switch between 5+ LLM providers, configure API keys, base URLs, and model selection. Zero-downtime switching.](https://raw.githubusercontent.com/kriely/CLMA/main/blog/images/api-settings-screenshot.png)

**API Configuration** lets you:
- Switch between OpenAI, Anthropic, DeepSeek, Gemini, and local models at runtime
- Configure API keys, base URLs, and model names
- Test the connection before submitting queries

![Rules Configuration — YAML-based rule engine that customizes how the framework interprets different query types.](https://raw.githubusercontent.com/kriely/CLMA/main/blog/images/rules-settings-screenshot.png)

**Rules Configuration** exposes the C++ rule engine's patterns:
- Define custom validation methods per query type
- Configure automatic code execution triggers
- Set sandbox tiering rules by language

![Tools Configuration — enable/disable execution environments (Python, C++, Shell, Node.js) and set sandbox timeout limits.](https://raw.githubusercontent.com/kriely/CLMA/main/blog/images/tools-settings-screenshot.png)

**Tools Configuration** manages:
- Which execution environments are enabled (Python, C++, Shell, Node.js)
- Sandbox timeout limits
- Token budget and max iterations

### Theme System

The UI defaults to dark mode (designed for late-night coding sessions), with a one-click toggle to invert to light mode. The toggle uses a CSS filter approach — `invert(1) hue-rotate(180deg)` — which works across all elements without needing separate light/dark CSS variables.

![Dark mode vs light mode side-by-side comparison. No refresh needed, instant toggle.](https://raw.githubusercontent.com/kriely/CLMA/main/blog/images/webui-dark-mode.png)

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

---

## Part 4: Lessons Learned, Mistakes Made, and What's Next

### The Hardest Lessons

After months of building CLMA, here are the things I wish I'd known from day one.

#### 1. "Agent" is an abstraction leak, not a solution

The term "agent" sounds sophisticated, but it's dangerously vague. In CLMA, an agent is just a prompt template + a context builder + an LLM call. There's no persistent state, no tool use, no memory (in the agentic sense). The framework orchestrates these calls, not the agents themselves.

I spent weeks early on designing elaborate agent communication protocols (who talks to whom? how do they share context? what if an agent goes rogue?) before realizing that **the simplest architecture was the right one:** linear data flow with structured context injection. The complexity should live in the orchestration, not the agents.

**Lesson:** Don't over-model the agents. Model the data flow between them.

#### 2. Three scores > one score, but not by much

The three-dimensional scoring (reasonableness, executability, satisfaction) was a late addition — and it was the right call. A single score doesn't tell the Verifier *what* to fix. But in practice, two of the three dimensions are highly correlated for code generation tasks: if the code is executable, it's usually reasonable, and vice versa.

**What I'd do differently:** Make scoring adaptive. For code generation tasks, weigh executability higher. For design tasks, weigh reasonableness higher. The dimensions should adjust based on the Router's classification, not be fixed weights.

#### 3. AAN was the hardest feature to get right

The Adaptive Agent Network sounds elegant in theory — "the framework chooses its own topology!" — but the Router heuristic is fragile. A query like "分别用python和javascript实现排序算法" triggers Parallel mode (correctly), but "分别实现python排序和javascript排序" triggers..."

The AAN Router has gone through 6 major revisions. It started as a single `len(query)` threshold, evolved into keyword matching, then effective length (accounting for Chinese character density), then code-intent detection, and recently added closed-loop iteration to the Chain topology itself.

**The AAN Router will never be perfect,** and that's okay. The design goal isn't perfection — it's "better than always defaulting to Single Loop." Any heuristic that beats the baseline is a win.

#### 4. Performance is a UX problem, not just an engineering one

The biggest complaint about multi-agent systems is latency. "Why does it take 30 seconds?"

Early on, I tried to optimize the agents — shorter prompts, single-shot generation, parallel calls. It helped, but not enough. What *actually* improved user perception was:

- **Real-time SSE streaming.** Watching agents complete in sequence makes the wait feel productive, not wasted.
- **Placeholder events.** The moment the Router decides the topology, the UI shows all agent nodes in the flow graph — even before they start. Users see the full pipeline up front.
- **Token counters.** Showing token usage per call gives a concrete "here's what you're paying for" sense of progress.

**Lesson:** Users will wait 40 seconds if they can see progress. They won't wait 10 seconds in a black box.

#### 5. Testing multi-agent systems is qualitatively different

Unit-testing a single LLM call is straightforward — assert the output format, check for common failure modes, replay with fixed seeds. Testing a 5-agent pipeline with iterative feedback loops is a different beast.

Categories of bugs I encountered:

| Category | Example | How We Catch It |
|---|---|---|
| **State isolation** | Agent B reads Agent A's output from a *previous* query | C++ session_id isolation + Python memory reset per query |
| **Context leaks** | Similar experiences from unrelated queries pollute the Solver's prompt | Separate context builders per agent, with assert statements for placeholder keys |
| **Template drift** | One agent's prompt template adds a `{placeholder}` that doesn't exist in context | Automated script that extracts placeholders from all templates and validates them |
| **Cancellation race** | User cancels mid-stream, but the next agent starts anyway | Shared `_stream_cancelled` flag checked before every LLM call |
| **Score oscillation** | Round 2 scores better than Round 1, but Round 3 scores worse | Track `best_score` across iterations, not just the last score |

**The biggest practical win:** prompt-level validation. Every agent's context template is checked for `{placeholder}` keys before execution. Missing keys are filled with empty strings rather than crashing, but the mismatch is logged. This single check caught more bugs than all the integration tests combined.

### What I'd Do Differently

**1. Build the Router first.** AAN should have been the default from day one. The explicit mode selection UI (Fast Path / Single Loop / DAG / Multi-Loop) was useful for debugging but harmful for user experience. Users don't want to think about execution modes. They want to type a query and get a good result.

**2. Instrument everything from the beginning.** The token monitor, duration tracker, and scoring system were added in reactive response to user complaints ("why did it take so long?" "why is this score so low?"). If I'd built the measurement infrastructure first, I would have caught several design flaws months earlier.

**3. Use a single LLM provider for development.** Switching between OpenAI, Anthropic, DeepSeek, and local models during development introduced confounding variables. Behavioral differences between providers (prompt sensitivity, JSON output format, refusal patterns) made it hard to isolate bugs in the framework itself.

**4. Ship the CLI first, Web UI second.** The Flask Web UI is useful and visually compelling, but it adds a dependency layer that complicates setup. A CLI-first approach would have let early users try CLMA with zero configuration and provided faster feedback cycles.

### Where CLMA Goes Next

The framework is actively used for personal projects, but there's plenty of room to grow:

**Near-term (next few months):**
- **Multi-turn conversations** — currently, each query is stateless. The next version will support follow-up queries with access to the session history.
- **Improved AAN Router** — move from heuristic-based to a lightweight classifier (small LLM call or embedding-based) for more accurate topology selection.
- **Sandbox expansion** — Java, Go, Rust execution environments via Docker containers.

**Medium-term:**
- **Plugin system** — the C++ PluginManager exists but needs better documentation and a curated registry.
- **Distributed execution** — multi-machine agent orchestration for very large tasks (entire repository generation).
- **Automatic experience storage** — successful query-solution pairs are already saved; the next step is automatic retrieval and reuse in similar queries.

**Long-term vision:**
CLMA is a step toward **self-improving code generation** — a system that not only generates and verifies code, but learns from its successes and failures to generate better code over time. The experience store, scoring system, and iterative feedback loop are the foundational pieces. The next step is connecting them into a continuous learning cycle.

### Final Thoughts

Building CLMA taught me that **the bottleneck in code generation is not generation — it's verification.** Every LLM can produce plausible-looking code. The hard part is knowing whether it's *actually* correct, and what to do about it when it isn't.

The closed-loop approach works because it mirrors how good developers work:

1. Write a draft
2. Review it critically
3. Fix the problems
4. Repeat until it's good enough

The CLMA framework just automates this process — and makes it visible, measurable, and improvable.

If this series inspired you to think differently about LLM-generated code, or if you have ideas for making CLMA better, I'd love to hear from you. Open an issue, submit a PR, or just star the repo — it all helps.

**[github.com/kriely/CLMA](https://github.com/kriely/CLMA)**

---

> **Built with Hermes & DeepSeek.** Every line of CLMA — from the C++17 DAG engine to the SVG gauges in the Web UI — was written with the help of Hermes (my AI agent companion) running on DeepSeek's API. I'm a developer with ideas, not a big team with a budget. Hermes and DeepSeek are the tools that let me ship those ideas.
> *Because ideas shouldn't wait for the perfect stack — they should just be built.*

---

*Tags: #LLM #MultiAgent #CodeGeneration #OpenSource #SystemDesign #WebUI #SSE #DeepSeek*
