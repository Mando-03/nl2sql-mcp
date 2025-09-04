# AI for Text-to-SQL: Bridging Natural Language and Databases

## 1. Executive Summary

Text-to-SQL enables users to query databases using natural language (NL) instead of complex SQL, democratizing data access. Large Language Models (LLMs) have advanced this field, but challenges remain: generalization to out-of-distribution (OOD) data, handling complex queries and massive databases, semantic ambiguity, schema mismatch, and ensuring SQL accuracy and executability. Recent research focuses on multi-agent frameworks, advanced prompting, data-centric approaches, and error correction. The goal: robust, scalable, accurate Text-to-SQL systems with minimal reliance on costly fine-tuning and proprietary models.

---

## 2. Key Themes and Important Ideas

### 2.1 Generalization Challenges and Solutions

- **Domain Generalization:** Applying models to databases with non-overlapping domains.
- **Compositional Generalization:** Handling queries with new combinations of learned components.

**Solutions:**

| Technique | Description | Reference |
|-----------|-------------|-----------|
| Semantic Boundary Preservation | Token-level preprocessing and sequence-level special tokens to improve LM generalization. | [ACL 2023 Short Paper](https://aclanthology.org/2023.acl-short.15.pdf) |
| Knowledge-Enhanced Re-ranking | G3R framework uses domain knowledge, PLM, and contrastive learning for hybrid prompt tuning. | [ACL 2023 Findings](https://aclanthology.org/2023.findings-acl.23.pdf) |

---

### 2.2 Handling Complex SQL and Database Structures

- **Challenges:** Multi-table joins, nested queries, advanced clauses (GROUP BY, HAVING, INTERSECT, UNION, EXCEPT).

| Approach | Description | Reference |
|----------|-------------|-----------|
| AST Exploration | Joint modeling of AST and grammar rules via bipartite graph. | [ACL 2023 Findings](https://aclanthology.org/2023.findings-acl.23.pdf) |
| Structure-to-SQL | Links queries and databases structurally, decomposes with grammar trees. | [SGU-SQL](https://arxiv.org/abs/2402.13284) |
| Relational Deep Learning | Treats DBs as temporal, heterogeneous graphs for GNN learning. | [RDL](https://arxiv.org/abs/2312.04615) |

---

### 2.3 Schema Linking and Information Retrieval

- **Schema Linking:** Mapping NL questions to schema elements (tables, columns, values).

| Technique | Description | Reference |
|-----------|-------------|-----------|
| Schema Routing | DBCopilot uses Differentiable Search Index (DSI) for schema graph routing. | [DBCopilot](https://arxiv.org/abs/2312.03463) |
| Preliminary SQL (PreSQL) | PET-SQL generates preliminary SQL for easier schema linking. | [PET-SQL](https://arxiv.org/abs/2403.09732) |
| Bidirectional Schema Linking | RSL-SQL combines forward and backward linking, reducing input tokens. | [RSL-SQL](https://arxiv.org/abs/2411.00073) |
| IR Agent | CHESS retrieves relevant entities and schema context via hashing and vector DBs. | [CHESS](https://arxiv.org/abs/2405.16755) |

---

### 2.4 Error Detection and Correction

- **Framework:** Generation → Identification → Correction.

| Method | Description | Reference |
|--------|-------------|-----------|
| Multi-Grained Error Identification | Categorizes errors: system, skeleton, value. | [COLING 2025](https://arxiv.org/abs/2025.coling-main.289) |
| Self-Correction Modules | DIN-SQL and MAC-SQL use prompts and external tools for correction. | [DIN-SQL](https://arxiv.org/abs/2304.11015), [MAC-SQL](https://arxiv.org/abs/2312.11242) |
| Multi-Turn Self-Correction | RSL-SQL uses conversational correction for high-risk SQL. | [RSL-SQL](https://arxiv.org/abs/2411.00073) |

---

### 2.5 Prompting Strategies and LLM Capabilities

- **Prompting:** In-context learning, few-shot/zero-shot, Chain-of-Thought (CoT), multi-agent collaboration.

| Strategy | Description | Reference |
|----------|-------------|-----------|
| CoT Reasoning | Decomposes problems for step-by-step SQL generation. | [ACT-SQL](https://arxiv.org/abs/2310.17342) |
| Reference-Enhanced Prompt | PET-SQL uses custom instructions and schema info. | [PET-SQL](https://arxiv.org/abs/2403.09732) |
| Multi-Agent Collaboration | MAC-SQL and CHESS frameworks for modular reasoning. | [MAC-SQL](https://arxiv.org/abs/2312.11242), [CHESS](https://arxiv.org/abs/2405.16755) |
| Targeted Drilling | PTD-SQL partitions queries for focused learning. | [PTD-SQL](https://arxiv.org/abs/2409.14082) |
| Multi-task SFT | ROUTE adds schema linking, noise correction, continuation writing. | [ROUTE](https://arxiv.org/abs/2412.10138) |

---

### 2.6 Data Quality and Real-World Considerations

- **Issues:** Data duplication, missing values, inconsistent types, ambiguous NL queries.

| Solution | Description | Reference |
|----------|-------------|-----------|
| Data-Centric Framework | Offline preprocessing, relationship graph, business logic. | [Data-Centric Text-to-SQL](https://arxiv.org/abs/24_Data_Centric_Text_to_SQL_wi) |
| Database Description Generation | Automatic generation of table/column descriptions. | [DB Description](https://arxiv.org/abs/2502.20657) |
| Ambiguity Benchmarks | AMBROSIA tests model ability to handle ambiguous queries. | [AMBROSIA](https://arxiv.org/abs/2406.19073) |

---

### 2.7 Evaluation Metrics and Benchmarks

| Metric | Description |
|--------|-------------|
| Execution Accuracy (EX) | Compares execution output of predicted SQL vs ground truth. |
| Exact-Set-Match Accuracy (EM) | Clause-by-clause match, ignores values. |
| Valid Efficiency Score (VES) | Measures efficiency of valid SQLs. |

**Benchmarks:**
- [Spider](https://yale-lily.github.io/spider): Large-scale, cross-domain, difficulty-categorized.
- [BIRD](https://arxiv.org/abs/2405.16755): 12,751 question-SQL pairs, 95 databases, external knowledge.
- [AMBROSIA](https://arxiv.org/abs/2406.19073): Focused on ambiguity (scope, attachment, vagueness).

---

## 3. State-of-the-Art Approaches and Performance

| Model | Key Results | Reference |
|-------|-------------|-----------|
| CHASE-SQL | 73% EX on BIRD test/dev, divide-and-conquer, CoT, synthetic examples. | [CHASE-SQL](https://arxiv.org/abs/2410.01943) |
| DBCopilot | Up to 19.88% recall improvement, 4.43–11.22% EX gain. | [DBCopilot](https://arxiv.org/abs/2312.03463) |
| PET-SQL | 87.6% EX on Spider, reference-enhanced prompt, PreSQL linking. | [PET-SQL](https://arxiv.org/abs/2403.09732) |
| RSL-SQL | 67.2% EX on BIRD dev, 87.9% EX on Spider (GPT-4o), bidirectional linking. | [RSL-SQL](https://arxiv.org/abs/2411.00073) |
| Alpha-SQL | 69.7% EX on BIRD dev (32B open-source LLM, zero-shot). | [Alpha-SQL](https://arxiv.org/abs/2502.17248) |

---

## 4. Challenges and Future Directions

- **Cost & Resources:** Proprietary LLMs are expensive; open-source LLMs require significant compute.
- **Synthetic Data Quality:** Hallucination and bias in generated data; need for better synthesis.
- **Long Context Windows:** Newer LLMs handle long contexts, but with increased latency/cost.
- **Ambiguity Resolution:** LLMs often predict only one interpretation; need for clarification and multi-output.
- **Foundation Models for Relational DBs:** Opportunity for generic, inductive models for new databases.
- **Multi-Turn Conversations:** Context-dependent queries require better history handling.
- **Beyond Exact-Match Metrics:** Need for metrics evaluating semantic equivalence and user intent.

---

## References

- [ACL 2023 Short Paper](https://aclanthology.org/2023.acl-short.15.pdf)
- [ACL 2023 Findings](https://aclanthology.org/2023.findings-acl.23.pdf)
- [SGU-SQL](https://arxiv.org/abs/2402.13284)
- [RDL](https://arxiv.org/abs/2312.04615)
- [DBCopilot](https://arxiv.org/abs/2312.03463)
- [PET-SQL](https://arxiv.org/abs/2403.09732)
- [RSL-SQL](https://arxiv.org/abs/2411.00073)
- [CHESS](https://arxiv.org/abs/2405.16755)
- [COLING 2025](https://arxiv.org/abs/2025.coling-main.289)
- [DIN-SQL](https://arxiv.org/abs/2304.11015)
- [MAC-SQL](https://arxiv.org/abs/2312.11242)
- [ACT-SQL](https://arxiv.org/abs/2310.17342)
- [PTD-SQL](https://arxiv.org/abs/2409.14082)
- [ROUTE](https://arxiv.org/abs/2412.10138)
- [Data-Centric Text-to-SQL](https://arxiv.org/abs/24_Data_Centric_Text_to_SQL_wi)
- [DB Description](https://arxiv.org/abs/2502.20657)
- [AMBROSIA](https://arxiv.org/abs/2406.19073)
- [CHASE-SQL](https://arxiv.org/abs/2410.01943)
- [Alpha-SQL](https://arxiv.org/abs/2502.17248)
- [Spider Benchmark](https://yale-lily.github.io/spider)
- [BIRD Benchmark](https://arxiv.org/abs/2405.16755)
