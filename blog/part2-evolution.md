# Building CLMA: A Self-Verifying Multi-Agent Framework from Scratch

## Part 2: From Single Loop to Adaptive Network — The Evolution of Execution Modes

*Posted on May 4, 2026 · #Architecture #Evolution #SystemDesign #OpenSource*

---

### The Naive First Attempt

When I started CLMA, the architecture was embarrassingly simple: a linear pipeline. Take the user's query → pass it through five agents in sequence → output the result. No iteration, no scoring, no feedback.

It didn't work well.

The first real version was the **Single Closed Loop** — and it looked like this:

<!-- INSERT GIF: single执行流程.gif -->
<!-- Caption: Single Loop execution flow — the framework iterates through Refiner → Reasoner → Solver → Verifier → Evaluator until scores pass the threshold. -->

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

<!-- INSERT GIF: 打开DAG后的single执行.gif -->
<!-- Caption: DAG Mode — the C++ DAG processor decomposes tasks into parallel sub-tasks, executing them concurrently. -->

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

<!-- INSERT GIF: multi执行流程.gif -->
<!-- Caption: Nested Multi-Loop — outer strategy loop plans the architecture, inner execution loop implements each component. -->

- **Outer loop (strategy):** Planner → Commander → Producer → Verifier → Evaluator. This loop handles architectural decisions, component decomposition, and high-level design.
- **Inner loop (execution):** Refiner → Reasoner → Solver → Verifier → Evaluator. Runs *inside* each component, iterating on implementation quality.

The outer loop's output becomes the inner loop's input for each component. The inner loop's results feed back into the outer loop's Verifier. This hierarchical iteration catches both design-level and implementation-level issues in a single pass.

**The pain point:** Nested Multi-Loop is powerful but slow. A single query can take 40–60 seconds to complete, and the flow graph visualization becomes dense enough to require zoom and pan controls.

### Adaptive Agent Network: Self-Organizing Topology

The biggest insight came from watching how users actually interacted with the four modes. Most users defaulted to one mode — usually Single Loop — and never switched. The framework had all these execution modes, but no one was using them because *choosing the right mode* required understanding the framework's internals.

**What if the framework could choose for you?**

That's the Adaptive Agent Network (AAN):

<!-- INSERT GIF: aan执行流程.gif -->
<!-- Caption: AAN Mode — the Router Agent analyzes the query and selects the optimal execution topology automatically. -->

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

| Mode | Use Case | Avg Time | Best For |
|---|---|---|---|
| **Fast Path** | "hello world", trivial math | ~2s | Greetings, trivial queries |
| **Single Loop** | Function implementations, algorithms | ~5–8s | Well-defined coding tasks |
| **DAG** | Multi-component features | ~10–25s | APIs, services, parallel work |
| **Nested Multi-Loop** | System architecture | ~40s | Full-stack design + implementation |
| **AAN** | Whatever you throw at it | 2–30s | Mixed workloads, adaptive routing |

### What I Learned About Mode Design

1. **Don't make users choose.** AAN was the most recent addition for a reason — it took seeing users stick to one mode before realizing that choice itself is a UX failure. The framework should infer what the user needs.

2. **Iteration > Parallelism for quality.** DAG's parallel execution cuts wall-clock time, but it's the Single Loop's iterative feedback that actually improves output quality. The best combination is both — AAN Chain's closure-based iteration with DAG's parallel sub-task execution.

3. **Benchmark everything.** Without a scoring system, you can't tell whether a new mode is actually better. The three-dimensional score (reasonableness × executability × satisfaction) made it possible to compare modes quantitatively.

**Up next in Part 3:** *The Web UI Deep Dive — building a real-time interface that makes multi-agent execution visible, understandable, and even enjoyable to watch.*

---

*CLMA is open source on [GitHub](https://github.com/kriely/CLMA). Part 1 covered the core architecture and the self-verification problem. Part 3 covers the Web UI.*

*Star it, fork it, break it — and tell me what you find.*

> **A brief note on how this was built:** Every line of CLMA — from the C++17 DAG engine to the SVG gauges in the Web UI — was written with the help of Hermes (my AI agent companion) running on DeepSeek's API. I'm a developer with ideas, not a big team with a budget. Hermes and DeepSeek are the tools that let me ship those ideas.  
> *Because ideas shouldn't wait for the perfect stack — they should just be built.*
