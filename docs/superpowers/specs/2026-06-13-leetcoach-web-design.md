# leetcoach · web app design

**Date:** 2026-06-13
**Status:** Vision locked. Implementation plan pending in the new `leetcoach-web` repo.

## Why

The Telegram bot proves the surface — logbook, spaced reviews, AI-assisted Q&A — but it's single-user and Notion-flavored. The product the bot wants to grow into is a multi-user web app that doesn't read like another LeetCode dashboard. It earns its keep by being a coach.

The bot stays where it is. The web app is a fresh repo, fresh database, multi-user from day one. The bot's application + infrastructure layers get *lifted* (copied) into the web repo as a starting foundation; nothing is shared at runtime.

## North Star

> The coach makes you do the rep, remembers you doing it, and checks whether it stuck.

Not another LeetCode dashboard. An award-winning, exciting smart coach for the personal grind.

## Audience

Solo developers grinding LeetCode for interviews. Multi-user public app. Personal isolation — no social feed, no leaderboards, no friends list. Outbound share intents to X / LinkedIn for milestone celebration only (web intent URLs, no OAuth).

## Brand (locked: Agent / Cyan-Steel)

- **Mascot:** hooded silhouette `@coach`. Pixel-grid construction. Sidebar avatar, chat avatar, favicon, loading state.
- **Palette:** bg `#04060d`, cyan `#22d3ee`, ice `#67e8f9`, steel `#64748b`, amber `#fbbf24` (urgency only). No purple.
- **Type:** JetBrains Mono primary, Inter for prose.
- **Voice:** terse, command-line-tinged. Examples:
  - `streak intact · 23d. dp still trails.`
  - `147 down. sample size means something now.`
  - `3 problems to target. skip easies.`
  - `recommend: dp quiz, 5 questions, ~7min.`

The full visual language lives in `.superpowers/brainstorm/74204-1781362065/content/agent-cyan-steel.html` until it migrates into the new repo as design tokens.

## Three Pillars

The product spine. Each is foundational. Every other feature derives from these, not the other way around.

### Pillar 1 — Memory

The coach knows your grind. Users ask natural-language questions about their own history and get grounded, defensible answers.

- **What it answers:** "where am I weakest?", "what dp problems did I struggle with?", "what pattern haven't I touched in two weeks?", "what should I try next that combines sliding window and hashmap?"
- **How it's bounded:** the chatbot is a product feature with a fixed tool catalog. Tools wrap structured queries over the user's data (problems, attempts, concepts, tags, review history). No raw model access. No arbitrary code execution. No cloud-code or generic LLM proxy.
- **Why it's a moat:** competitors with bolted-on ChatGPT can't promise behavior. We can. The chatbot can only do what we've wired tools for.
- **What lives in memory:** logged problems, attempt history, user-narrated concepts, time-to-solve, review outcomes, quiz performance, prior explanations.
- **Reasoning depth:** beyond direct tool calls, a multi-step agent loop composes answers across primitive tools (e.g., "weakness over last 30 days" = pattern × accuracy × recency × review-failure rate, composed turn-by-turn). Memory questions are first-class, not just thin wrappers over single tools. See **Agent Architecture** below.

### Pillar 2 — Low-Resistance Capture

Logging is the load-bearing user action. Every log-keeping app dies at the friction of manual entry. The coach removes the form.

- **Conversational log:** user narrates ("did two sum, took 8 minutes, used hashmap, kept missing the duplicates edge case") → coach extracts → fills concepts / time / notes / tags → user confirms or corrects.
- **Voice narration:** browser STT (or Whisper) feeds the same flow. Hands-free post-solve logging. (Phase 3.)
- **Time-to-solve from narration:** extracted from how the user describes the solve. No timer required.
- **Tool catalog stays tight:** `log_problem`, `log_attempt`, `confirm_extraction`, `correct_extraction`. The coach cannot wander.
- **Form-based fallback:** manual logging stays available for users who don't want to talk.

### Pillar 3 — Active Recall

The coach makes you teach the problem back. This is where learning actually happens.

- **Trigger:** opt-in per problem, or surfaced at review time. Never forced.
- **Format:** voice or text. Coach asks targeted follow-up questions: "what's the invariant here?", "why monotonic stack and not heap?", "where did you get stuck the first time?"
- **What's graded:** concept clarity, not code. Gaps in understanding, not syntax.
- **Compounds with the other two pillars:** uses voice (Pillar 2's surface) and quotes the user's past explanations back at them (Pillar 1's data).
- **What it earns:** the user actually retains what they grind through. The coach has evidence they did.

## Table Stakes

Standard but required. None of these are differentiators on their own — they're what an interview-prep app must do to be credible.

- Manual problem logging (form-based)
- Spaced reviews (existing 7d / 21d at launch; adaptive policy comes in Phase 3)
- Quizzes (multiple-choice over user's own concepts; existing pattern from the bot — paywalled in Phase 2)
- Reminders (push or email; user-controlled cadence; minimalism guardrail)
- Dashboards: streak, heatmap, stats, weak-spot ranking
- Cmd+K command palette
- Outbound share intents (X / LinkedIn) on milestones — no native social feed (Phase 3)

## Non-Goals (explicit)

- Generic AI tutor ("explain this algorithm to me") → that's ChatGPT
- Code execution / test runner → LeetCode does that
- Solution generation → undermines the grind
- Native social feed / leaderboards / friends
- Notion import → fresh app; users log directly
- Offline mode / service worker at launch
- Mobile-native apps (responsive + installable PWA only)
- Letting the chatbot do anything outside its tool catalog
- **Agent framework dependency** (LangChain, LangGraph, etc.) — direct provider SDKs only; custom agent loop lifted from the bot's `ask_service` pattern. Designed behind a swappable `AgentRunner` interface in case the topology ever genuinely warrants a framework.
- **External memory providers** (Pinecone, Mem0, Zep, Weaviate, etc.) — all memory lives in our SQLite. Bounded, debuggable, free.

## Product Principles

- **Minimalism is the constraint, not the aesthetic.** No notification bombardment. No vanity-stat walls. The coach speaks when it has something earned to say, not on a schedule. The user feels in control.
- **Bounded AI.** Every AI feature is scoped to a tool catalog. The chatbot is a product, not a proxy.
- **Coach over logbook.** Every feature ships with the question: does this make the coach more present, or just add another panel?
- **Capture > recall > insight.** Pillars are ordered by dependency. No insight without recall data. No recall data without capture.

## Auth & Pricing

- **Auth:** email + 6-digit OTP code, type back into the page. No social login at launch.
- **Phase 1 (Foundation):** fully free. No billing infrastructure. No paid tier.
- **Phase 2+ (Coach):** paywall opens.
  - **Free tier** = logging, dashboards, reviews, reminders, basic stats.
  - **Paid tier** = quizzes + chatbot (memory queries, conversational logging, active recall) + voice (Phase 3) + milestone share intents (Phase 3).
- **Billing:** Stripe, introduced in Phase 2.
- **Rationale:** logbook stays free so the dataset grows. Coach features and quizzes earn their keep. Phase 1 ships without billing surface to keep the launch lean.

## Architecture

The implementation plan owns concrete technical decisions; this section locks the load-bearing ones.

### Tech Stack

- **Backend:** FastAPI, Python 3.11+
- **Frontend:** Next.js
- **Database:** SQLite. WAL mode mandatory. `sqlite-vec` extension for embeddings. FTS5 for full-text search.
- **Backup:** Litestream → object storage (Backblaze B2 / S3) once deployed.
- **LLM provider:** abstraction layer; **Gemini default** (free API tier first, Gemini paid tier when usage scales). **Claude deferred** until revenue justifies the API spend.
- **Embeddings:** Gemini embedding API (free tier available); model swap via the same provider abstraction.
- **Mobile:** responsive + installable PWA. No service worker, no offline at launch.
- **Code lift:** the bot's `services/` (application) and `storage/` (infrastructure) get copied into the web repo's `core/` as foundation. The bot continues running from its own copy. No runtime sharing, no shared package.

**Migration trigger (documented, not planned):** revisit Postgres + pgvector if any single user accumulates 100k+ embeddings, *or* a feature requires cross-user vector search (currently a non-goal).

### Memory Architecture

Memory has five distinct kinds. They live together in SQLite; their access patterns differ.

| Kind | What | Storage |
| --- | --- | --- |
| **a. Grind data** | problems, attempts, concepts, notes, tags, reviews | SQLite relational tables |
| **b. Conversation history** | persistent chat threads, messages, tool-call traces | SQLite (`chat_threads`, `chat_messages`) |
| **c. LLM context window** | what the model sees per turn | Built per-call from a + b; never pre-stuffed; provider prompt caching for the stable prefix |
| **d. Semantic memory** | vector index over narrations / notes / past explanations | `sqlite-vec` table; rowid joins back to relational |
| **e. Rolling user summary** | "weak on DP, strong on hashmaps" | Derived on demand from (a); cached if expensive |

**Principles:**

- All memory in our SQLite. No external providers.
- Curated embedding: only narrations, notes, past explanations, optionally rolling thread summaries. Not numerical fields (SQL handles those), not code.
- Per-user scope on every query. Per-user vector counts stay in the low thousands; brute-force KNN in `sqlite-vec` is sub-millisecond at this scale.
- Hybrid retrieval: FTS5 keyword + `sqlite-vec` semantic, joined in SQL.
- Cosine similarity for vector search.

### Agent Architecture

A bounded chatbot. The agent loop is custom, lifted and extended from the bot's `ask_service` pattern. No framework dependency; designed for swappable `AgentRunner` if topology ever warrants it.

**Tool catalog — four layers:**

| Layer | Examples | Purpose |
| --- | --- | --- |
| **L1 Primitive** | `get_problems_by_tag`, `get_attempts`, `get_reviews`, `get_user_stats` | SQL-like access to structured data. Fast, deterministic. |
| **L2 Analytical** | `analyze_weakness`, `recommend_problems`, `assess_pattern_coverage` | Pre-composed for predictable questions. Server-side composition reduces multi-step burden. |
| **L3 Semantic / RAG** | `search_memory`, `find_similar_problems`, `recall_my_explanations` | Fuzzy retrieval over narrations and past explanations via `sqlite-vec`. |
| **L4 Terminals** | `final_answer`, `cannot_answer` | Honest exits. No bad guesses. |

The agent picks: L2 if a tool already answers the question; L1 to compose if not; L3 for fuzzy queries; L4 honestly when stuck.

**Loop pattern:**

- LLM API is stateless. Conversation state lives in our SQLite (`chat_messages`).
- Full conversation history (user messages + prior tool calls + tool results) is sent on every turn — required by providers' native tool-use APIs.
- **Prompt caching enabled** (Anthropic explicit cache blocks; Gemini implicit) so re-sending the stable prefix (system prompt + tool catalog + early thread) is cheap.
- `MAX_STEPS = 8` hard limit; force-terminate via `cannot_answer("exceeded reasoning budget")`.
- Loop detection: if the same tool is called with the same arguments twice consecutively, inject a system note: *"you just called this with these args and got X. Try something different."*
- Prompt discipline: explicit instructions to prefer L2 if it fits, compose with L1 otherwise, fall back to L3 for fuzzy queries, call L4 honestly when stuck.

**Failure modes addressed (from the bot's experience):**

- *No matching tool → confabulation:* fixed by L4 `cannot_answer` terminal + L3 RAG fallback for fuzzy queries.
- *Infinite loop on the same tool:* fixed by full-history context (model sees its prior calls), loop detection, and step cap.

### Hosting

**Phase 1 deployment is local-only.** Development on the user's machine; no cloud cost; no public exposure.

**Public deployment is deferred to when the app is ready to charge.** Cheapest defensible options at that point:

| Path | Approx fixed cost | Notes |
| --- | --- | --- |
| Oracle Cloud Free Tier ARM VPS | $0 | Free forever; Oracle account quirks |
| Hetzner ARM VPS | ~$5/mo | Predictable; manual updates |
| Render free web service | $0 | Cold starts after 15min idle |
| Fly.io free tier | $0 | $5 credit/mo; reliability rep is real |

**Common stack on any of these:** SQLite on the VM's disk; Litestream → object storage for backup; Cloudflare in front for free SSL + DNS; Gemini free-tier API for embeddings and chat at launch.

LLM API cost is the variable expense and is paid for by the subscription tier.

## Schema Notes

On top of the bot's existing schema:

- `user_problems`: add `solution_code`, `solution_language`
- New table `attempts`: per-problem attempt history (`started_at`, `ended_at`, `success`, `narration`, `derived_time_to_solve`)
- New tables `chat_threads`, `chat_messages`: persistent chat with tool-call trace visibility (collapsed by default in UI). `chat_messages.tool_calls` stored as JSON.
- New table `problem_narrations`: text + `source` (`logging`, `active_recall`, `chat`) + timestamps. 1:N with `user_problems`.
- New `sqlite-vec` virtual table `vec_problem_narrations`: `rowid` joins to `problem_narrations.id`; cosine distance; 768-dim embeddings (Gemini default).
- FTS5 virtual tables for keyword search across narrations, notes, problem titles.
- Phase 3: SM-2-lite adaptive review fields (`ease_factor`, `interval`, `due_at`).

## Phasing

Three phases. Each ships a product the user can use end-to-end. Phasing is an output of the locked vision, not an input.

### Phase 1 — Foundation

Multi-user web app at parity with the bot's logbook. Brand identity in place. **No billing. No AI features. No coach pillars yet.**

- Email OTP auth
- Manual problem logging (form-based)
- Spaced reviews (existing 7d / 21d schedule)
- Dashboards (streak, heatmap, stats, basic weak-spot ranking from existing tag data)
- Reminders
- Cmd+K palette
- Brand: Agent / Cyan-Steel applied across the full surface

**Ships when:** a new user can sign up, log a problem, run a review session, and see their dashboard. Local deployment only.

### Phase 2 — Coach

The pillars come online. The product becomes a coach. Paywall opens.

- Bounded chatbot with the four-layer tool catalog
- Memory queries (Pillar 1) with multi-step composition
- Low-resistance text-based logging via chat (Pillar 2; voice deferred to Phase 3)
- Active recall sessions, text-based (Pillar 3)
- Quizzes (now behind paywall)
- Stripe billing; paid features gated
- Persistent chat threads with collapsed tool-call traces

**Ships when:** a user can narrate "did two sum in 8 minutes, hashmap, struggled with duplicates" and have it logged correctly. A user can ask "where am I weakest?" and get a defensible answer. A user can opt into "explain this back to me" on a past problem.

### Phase 3 — Voice & Adaptive

The coach gets faster, sharper, and listens.

- Voice integration on capture and recall (browser STT or Whisper)
- SM-2-lite adaptive review schedule (replacing flat 7d / 21d)
- Milestone share intents (X / LinkedIn web intents)
- Broader L2 analytical tools (recommendations, readiness signals derived from memory)
- Quality-of-life: command palette extensions, keyboard navigation polish, animation refinements

**Ships when:** a user can solve a problem, speak "I just did valid parens, took 12 minutes, stack-based" into their phone, and the coach captures it cleanly. A user can ask the coach to grade their verbal explanation of monotonic stack.

## Success Criteria (the bar)

- Sign up via email OTP and log first problem in under 2 minutes
- Voice capture extracts time + concepts + tags correctly on >80% of solves (Phase 3)
- Coach answers "where am I weakest" with a ranked list backed by data the user can drill into
- Active recall session reads as coaching, not interrogation, in user testing
- Phase 2 paid conversion driven by AI feature exposure, not by gating table-stakes logging or reviews

## Open Questions Deferred to Implementation Plan

- Exact tool catalog schema (names, parameters, return types) for L1, L2, L3, L4
- Memory orchestration prompt structure and full L2 analytical tool list
- LLM cost ceiling per paid user / month and enforcement strategy
- Voice provider choice: browser STT vs Whisper API vs both
- Frontend architecture: server components vs client; state management
- Realtime chat transport: SSE vs WebSocket
- Session / cookie strategy under FastAPI
- SM-2-lite parameter tuning
- Embedding model selection (Gemini default vs Voyage / Cohere comparisons) and dimension choice
- Public deployment provider selection (defer until ready to charge)
