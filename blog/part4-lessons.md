# Building CLMA: A Self-Verifying Multi-Agent Framework from Scratch

## Part 4: Lessons Learned, Mistakes Made, and What's Next

*Posted on May 4, 2026 · #LessonsLearned #OpenSource #Future #AI*

---

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

> **Built with Hermes & DeepSeek.** Every line of CLMA — from the C++17 DAG engine to the SVG gauges in the Web UI — was written with the help of Hermes (my AI agent companion) running on DeepSeek's API. I'm a developer with ideas, not a big team with a budget. Hermes and DeepSeek are the tools that let me ship those ideas.  
> *Because ideas shouldn't wait for the perfect stack — they should just be built.*

---

*All four parts:*
- *Part 1: [The Problem — LLMs Can't Self-Verify](part1-problem.md)*
- *Part 2: [Architecture & Evolution — From Single Loop to Adaptive Network](part2-evolution.md)*
- *Part 3: [The Web UI Deep Dive — Making Multi-Agent Execution Visible](part3-webui.md)*
- *Part 4: [Lessons Learned, Mistakes Made, and What's Next](part4-lessons.md) (this one)*
