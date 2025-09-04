# NL2SQL MCP – Refined Strategic Brief (Intelligence-Only, No Embedded LLM)

## 1. Purpose & Scope Clarification

This MCP server is an *intelligence surface*––it does **not** contain an internal language model. An external LLM (caller) performs:
- Natural language interpretation
- SQL authoring/refinement
- Multi-turn reasoning

The MCP’s mandate:
1. Provide *high-signal, low-token* structured schema intelligence.
2. Offer precise planning artifacts (retrieval results, join paths, constraints, skeletons).
3. Enforce safe execution (SELECT-only) with validation and diagnostics for the external LLM to iterate on.
4. Surface ambiguity, confidence, and clarification needs early—never hallucinate.
5. Remain engine-agnostic and schema-neutral (no hard-coded business logic).

All recommendations below are constrained to this intelligence-only scope (i.e., no internal candidate SQL generation loops, no embedded “agents”, no model fine-tuning pipeline inside the server).

---

## 2. Current Strengths (Already Well-Aligned with Scope)

1. Separation of expensive schema build vs. low-latency retrieval (precomputation-friendly).
2. Typed, deterministic tool contracts (excellent for external LLM prompt reliability).
3. Rich structural modeling: FK graph, subject areas, archetypes, column roles.
4. Multi-modal retrieval (lexical + optional embeddings + graph expansion).
5. Safety perimeter: strict SELECT-only + dialect normalization + validation.
6. Degradation strategy: fallback to lexical when embeddings fail; partial reflection tolerance.
7. Execution tool returns typed results + actionable notes (seed for external correction loops).
8. Utility scoring & table archetypes—gives the external LLM better feature cues for reasoning.
9. Clean extensibility: dependency injection + Pydantic; minimal implicit state.
10. Intent-first planning entry point (`plan_query_for_intent`) already aligned with “assistant not author” role.

---

## 3. Adjusted Gap Analysis (Within Server Responsibility Only)

| Need (External LLM Benefit) | Current Gap | Opportunity (Server-Side Artifact) |
|-----------------------------|-------------|------------------------------------|
| Ambiguity detection | No structured ambiguity metadata | Provide `ambiguity_flags`, `ambiguous_tokens`, `alternative_interpretations` (semantic roles / date scope guesses) |
| Confidence calibration | Qualitative only | Compute confidence from retrieval coverage, join path completeness, metric/date presence |
| Value-level assist | Distinct values captured but not exposed systematically per query intent | On-demand constrained enumerations / candidate filter value sets |
| Clarification loop enablement | Clarification text only; not typed | Return machine-usable `clarification_questions[]` with `reason` + `blocking` boolean |
| Join reasoning transparency | Join plan surfaced, but lacks scoring/explanation | Attach `join_edges[]` with features (fk_strength, cardinality_hint, utility_score) |
| Skeleton-first external SQL drafting | Direct `draft_sql` (optional) may bias LLM prematurely | Offer optional *abstract* `query_skeleton` (SELECT targets placeholders, table aliases, join edges, filter slots) without emitting full SQL unless explicitly requested |
| Error taxonomy for failed execution | Generic assist notes only | Map validation/runtime issues to structured categories: {parse_error, missing_table, missing_column, ambiguous_column, type_mismatch, unsafe_pattern, timeout, result_truncated} |
| Multiple plan perspectives (query complexity) | Single enrichment view | Provide alternative table sets (e.g., minimal path vs. enriched dimensional expansion) without generating SQL variants |
| Retrieval feature transparency | Scores implicitly applied | Return per-table feature vector (lexical_score, embedding_score, centrality, archetype_bonus, expansion_origin) |
| Cost / performance hints | Not provided | Static heuristic: estimated row-size risk flags (e.g., many-large-fact joins) |
| Coverage metrics | Not reported | Add retrieval coverage ratios (e.g., metrics_present, date_dimension_present, groupable_dimension_count) |
| Enum / categorical constraints | Stored, but not formatted for filter generation | Expose ranked categorical candidates (value + frequency_estimate + role) |
| Temporal inference | Not explicit | Provide inferred primary date column candidates + time grain suggestions |
| Observability / evaluation | No built-in structured logging spec | Define optional structured trace record for each planning call (feature-flag controlled) |
| Token efficiency | Potentially verbose payloads | Add `detail_level` parameter controlling verbosity of samples, value enumerations, and descriptive summaries |

---

## 4. Design Principles Going Forward (Scope-Safe)

1. Predictable over “smart”: prioritize explicit structured fields over inferred narrative text.
2. Reversible abstractions: every derived artifact (e.g., subject area) traceable to raw sources.
3. Zero hidden heuristics: expose feature contributions where scoring is used.
4. Minimize token footprint: enforce budgets with caller-directed `detail_level`.
5. Assist > Generate: prefer frames, enumerations, constraint sets—let caller LLM do language + synthesis.
6. Deterministic fallback paths: no branch that produces qualitatively different output shapes.

---

## 5. Prioritized Roadmap (P0 → P2)

### P0 (Immediate Enablement)
- Confidence & Ambiguity
  - Add `confidence_score` (0–1) derived from table score dispersion + presence of required semantic roles.
  - Add `ambiguity_flags[]` (e.g., MULTIPLE_DATE_CANDIDATES, METRIC_UNSPECIFIED).
- Clarification Model
  - Structured `clarification_questions[]`: {id, question, reason_code, blocking:boolean}.
- Retrieval Feature Transparency
  - Augment `relevant_tables[]` entries: include component scores & origin (seed, expanded, inferred).
- Error Taxonomy
  - Structured error object for `execute_query`: {category, code, message, hints[], recoverable:boolean}.
- Query Skeleton (Optional)
  - Provide `query_skeleton`: {tables[], joins[], select_slots[], filter_slots[], group_by_candidates[], metric_candidates[]}.
  - Deprecate default inclusion of raw `draft_sql` unless requested via flag (e.g., `include_sql_suggestion`).

### P1 (Core Intelligence Depth)
- Alternative Context Views
  - Add `context_variants[]` (e.g., MINIMAL_FACT_PATH vs ENRICHED_DIMENSIONAL) each with rationale and table set.
- Value & Categorical Enumerations
  - On-demand (`enumerate_values=...`) enumerated low-cardinality values per relevant table/column with frequency hints.
- Temporal Inference
  - Provide `time_dimensions[]` with inferred grain classification (date, datetime, month_bucket_candidate).
- Coverage Metrics
  - Return: `role_coverage` summary (have_metric:boolean, have_date:boolean, dimension_count:int).
- Cost / Complexity Heuristics
  - Add `complexity_assessment`: {estimated_join_count, potential_rowset_category (SMALL|MEDIUM|LARGE|RISK), notes[]}.
- Structured Planning Trace (Feature-Flag)
  - Emit machine-loggable JSON for offline evaluation (no PII, no raw data rows).

### P2 (Advanced Assist Enhancements)
- Bidirectional Linking Enhancements
  - Value-driven candidate narrowing (literal-like tokens → column value match probability).
- Semantic Constraint Packs
  - Provide grouped constraint artifacts: equality enums, typical ranges, date bounds.
- Adaptive Detail Policy
  - Auto-trim or expand context based on token budget hint from caller (`token_budget_hint` field).
- Safety Scoring
  - Pre-execution risk tags (e.g., CARTESIAN_RISK, BROAD_SELECT_NO_FILTER) when skeleton suggests risk patterns.
- Differential Change Summaries
  - If schema card updated: expose delta summary (tables added/removed, relationships changed).

---

## 6. Data & Model Extensions (No Internal LLM)

| Artifact | Extension | Purpose |
|----------|-----------|---------|
| TableProfile | +retrieval_features, +risk_tags | Transparent scoring + downstream guardrails |
| ColumnProfile | +enum_candidate (boolean), +categorical_cardinality_estimate | Filter suggestion precision |
| QuerySchemaResult | +query_skeleton, +confidence_score, +ambiguity_flags, +clarification_questions, +role_coverage, +complexity_assessment | Higher-fidelity planning context |
| ExecuteQueryResult | +error_taxonomy, +performance_warnings | External LLM self-repair |
| SchemaCard | +build_meta (version, feature_flags, hash lineage) | Reproducibility / caching |

---

## 7. Metrics & Observability (Server-Side Only)

Instrument (behind a feature flag):
- Retrieval:
  - Tables considered vs. returned
  - Score dispersion (Gini / variance) for confidence calibration
- Planning:
  - Role coverage percentages
  - Ambiguity incidence rate
- Execution:
  - Failure category distribution
  - Average row truncation occurrence
- Adoption:
  - Clarification question response success rate (if integrated via caller feedback loop)

Produce a lightweight evaluation harness (no embedded LLM):
- Feed recorded (NL query, chosen final executed SQL) pairs
- Compute:
  - Table recall (did returned `relevant_tables` cover actual tables?)
  - Join completeness (% of executed join edges present in skeleton)
  - Constraint accuracy (if enumerations requested, did final SQL use enumerated values?)

These metrics enable external LLM iteration improvement cycles without modifying server scope.

---

## 8. Out-of-Scope (Intentional Exclusions)

| Excluded | Reason |
|----------|--------|
| Internal SQL generative models or prompting | Delegated to caller LLM |
| Multi-agent orchestration within server | Complexity & model ownership external |
| Fine-tuning / synthetic data pipelines | Outside intelligence surface role |
| Multi-candidate natural language interpretations | Provide structured artifacts; caller generates linguistic variants |
| Learned re-rankers (initially) | Implement transparency first; add ML layer only if heuristics plateau |
| Conversational state persistence | Caller should manage dialogue context; server remains stateless per request |
| Complex AST mutation loops | Provide skeleton + diagnostics; external LLM performs transformation |

---

## 9. Summary

Refining to an intelligence-only paradigm clarifies our value: *be the precise, explainable, safety-anchored substrate that maximizes the external LLM’s SQL success rate while minimizing tokens and ambiguity*.  
The fastest improvements:
1. Structured confidence + ambiguity + clarifications
2. Transparent retrieval & join feature exposure
3. Query skeletons + role/coverage metrics
4. Rich error taxonomy + constraint enumerations

This preserves safety and neutrality while materially increasing downstream LLM effectiveness and debuggability.

---

## 10. Quick Action Checklist (Execution-Ready)

- [ ] Add flags & schema updates for new fields (backward compatible).
- [ ] Implement confidence & ambiguity heuristics (table score spread, missing metric/date).
- [ ] Introduce `query_skeleton` model + generation path.
- [ ] Extend execution error mapping → categorized taxonomy.
- [ ] Add retrieval feature vector fields to `relevant_tables[]`.
- [ ] Implement optional value enumeration endpoint param (with row/enum budget).
- [ ] Add planning trace emitter (env-controlled).
- [ ] Draft evaluation harness spec (table recall, join completeness).

Deliver these in P0/P1 to unlock immediate external LLM prompt quality improvements.

(End of Brief)