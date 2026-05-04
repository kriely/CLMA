# Building CLMA: A Self-Verifying Multi-Agent Framework from Scratch

## Part 1: The Problem — LLMs Can't Self-Verify

*Posted on May 4, 2026 · #LLM #MultiAgent #CodeGeneration #OpenSource*

---

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

### What This Series Covers

Over the next few parts, I'll walk through:

1. **Part 1 (this one):** Why self-verification matters and the architecture that makes it possible
2. **Part 2:** How the framework evolved from a single closed loop into 5 execution modes — Fast Path, Single Loop, DAG, Nested Multi-Loop, and Adaptive Agent Network — and the painful lessons learned along the way
3. **Part 3:** Building a real-time Web UI with SSE-driven streaming, SVG flow graphs, and a dark theme that developers actually enjoy using
4. **Part 4:** Lessons learned, what I'd do differently, and where CLMA is headed next

All code is open source on GitHub: **[github.com/kriely/CLMA](https://github.com/kriely/CLMA)**

---

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

**Up next in Part 2:** *From Single Loop to Adaptive Network — how the execution modes evolved and why AAN was the hardest to get right.*

---

*CLMA is open source under the MIT License. Star it on [GitHub](https://github.com/kriely/CLMA), open an issue, or contribute a PR. Real feedback from real developers is the best way to make it better.*

> **A brief note on how this was built:** Every line of CLMA — from the C++17 DAG engine to the SVG gauges in the Web UI — was written with the help of Hermes (my AI agent companion) running on DeepSeek's API. I'm a developer with ideas, not a big team with a budget. Hermes and DeepSeek are the tools that let me ship those ideas.  
> *Because ideas shouldn't wait for the perfect stack — they should just be built.*
