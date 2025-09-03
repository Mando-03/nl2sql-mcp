AI for Text-to-SQL: Bridging Natural Language and Databases
1. Executive Summary
The field of Text-to-SQL aims to enable users to query databases using natural language (NL) instead of complex SQL. This is crucial for data democratization and is being significantly advanced by Large Language Models (LLMs). However, current LLM-based solutions face several challenges: generalization to out-of-distribution (OOD) data, handling complex SQL queries and massive databases, addressing semantic ambiguity and schema mismatch, and ensuring the accuracy and executability of generated SQL. Recent research focuses on multi-agent frameworks, advanced prompting strategies, data-centric approaches, and error correction mechanisms to overcome these hurdles. The ultimate goal is to create robust, scalable, and accurate Text-to-SQL systems that are less reliant on costly fine-tuning and proprietary models.

2. Key Themes and Important Ideas
2.1 Generalization Challenges and Solutions
LLMs, despite their promising performance, "still struggle to generalize on out-of-distribution (OOD) samples" (2023.acl-short.15.pdf). This includes:

Domain Generalization: Applying models to databases with non-overlapping domains.
Compositional Generalization: Handling queries with new combinations of learned components (e.g., "how many heads of the departments").
Solutions explored:

Semantic Boundary Preservation (2023.acl-short.15.pdf): Two simple yet effective techniques are proposed:
Token-level preprocessing: Rewrites inputs to handle naming conventions in database schemas and SQL queries, allowing the tokenizer to split them into semantically meaningful tokens (e.g., budget_in_billions becomes budget _ in _ billions). This "dramatically improves both types of LM generalization."
Sequence-level special tokens: Introduces special tokens (e.g., [sep0]) to mark semantic boundaries aligned between NL and SQL, helping the LM "build more precise input-output correspondences that are crucial for compositional generalization."
Knowledge-Enhanced Re-ranking (2023.findings-acl.23.pdf): The G3R framework introduces domain knowledge through a re-ranking mechanism using a pre-trained language model (PLM) and contrastive learning with hybrid prompt tuning. This aims to "mitigate performance degradation in unseen domains."
2.2 Handling Complex SQL and Database Structures
Generating complex SQL queries, especially those involving multiple tables, nested queries, and various clauses (GROUP BY, HAVING, INTERSECT, UNION, EXCEPT), remains a significant challenge.

Abstract Syntax Tree (AST) Exploration (2023.findings-acl.23.pdf): Current approaches often "cast SQL generation into sequence-to-sequence translation and ignore the structural information of AST and how it dynamically changes during the decoding process." G3R addresses this by constructing an AST-Grammar bipartite graph for joint modeling of the AST and corresponding grammar rules, capturing structural information.
Structural Information Exploitation (2402.13284v2.pdf): Existing models often "overlook the structural information inherent in user queries and databases," leading to inaccurate or unexecutable SQL. SGU-SQL proposes a "structure-to-SQL framework" that:
Links queries and databases in a "structure-enhanced manner."
Decomposes complicated linked structures with grammar trees to guide SQL generation step-by-step.
Relational Deep Learning (2312.04615v1.pdf): RDL views relational databases as a "temporal, heterogeneous graph, with a node for each row in each table, and edges specified by primary-foreign key links." Message Passing Graph Neural Networks (GNNs) can then learn representations across this graph, performing end-to-end learning without manual feature engineering.
2.3 Schema Linking and Information Retrieval
Effectively linking natural language questions to the correct database schema elements (tables, columns, values) is critical.

Schema Linking as a Challenge: "Schema linking is critical for accurate NL2SQL generation [9], as it maps ambiguous user questions to relevant schema elements" (2501.12372v4.pdf). Issues include semantic mismatch (domain-specific terminology), vocabulary mismatch, and the need to filter irrelevant information from large schemas.
Schema Routing for Massive Databases (2312.03463v3.pdf): DBCopilot addresses querying over "massive databases (e.g., data lakes, data warehouses, and open data portals) with large-scale schemata." It decouples NL2SQL into:
Schema Routing: Uses a lightweight Differentiable Search Index (DSI) to identify the target database and relevant tables. This involves constructing a schema graph and using DFS serialization with constrained decoding.
SQL Generation: Feeds the routed schema and question to LLMs.
Preliminary SQL (PreSQL) for Schema Linking (2403.09732v4.pdf): PET-SQL proposes generating a preliminary SQL statement first, then parsing its mentioned entities for schema linking. The rationale is that LLMs are "adequately pre-trained in relevant corpus" for code generation, making PreSQL generation "easier and more natural than directly performing schema linking as instructed." This can then simplify the prompt for generating the final SQL (FinSQL).
Bidirectional Schema Linking (2411.00073v2.pdf): RSL-SQL combines forward (retrieval-based) and backward (parsing preliminary SQL) schema linking. This significantly reduces input tokens while maintaining high recall for necessary schema elements, achieving a "strict recall of 94% while reducing the number of input columns by 83%."
Information Retriever (IR) Agent (2405.16755v3.pdf): CHESS includes an IR agent to retrieve relevant entities (values) and contextual schema descriptions. It uses locality-sensitive hashing for efficient value retrieval and vector databases for semantic similarity-based context extraction from database catalogs.
2.4 Error Detection and Correction
Ensuring the correctness and executability of generated SQL is paramount.

Generation-Identification-Correction Framework (2025.coling-main.289.pdf): This widely adopted framework involves:
Generating SQL: Initial query production.
Detecting Errors: Identifying issues in the generated SQL.
Correcting Errors: Refining the SQL based on detected errors.
Multi-Grained Error Identification (MGEI) (2025.coling-main.289.pdf): Categorizes SQL errors into three main types for precise identification:
System Errors: Invalid syntax (detected by SQL executor).
Skeleton Errors: Structural mismatches (detected by a skeleton matching model trained with contrastive learning).
Value Errors: Inconsistent values (detected by interacting with the database). This provides "detailed error information" to guide LLMs in correction.
Self-Correction Modules:DIN-SQL (2304.11015v3.pdf): Proposes a self-correction module where the model is instructed to fix minor mistakes in a zero-shot setting. It uses "generic" or "gentle" prompts based on the LLM.
MAC-SQL (2312.11242v5.pdf): Includes a "Refiner" agent that uses an external SQL execution tool to obtain feedback and refine erroneous SQL queries.
Multi-Turn Self-Correction (2411.00073v2.pdf): RSL-SQL employs a multi-turn conversational-based correction process for SQL queries with a high likelihood of errors, regenerating and adjusting high-risk SQL.
2.5 Prompting Strategies and LLM Capabilities
The way LLMs are prompted significantly impacts Text-to-SQL performance.

In-Context Learning (ICL) and Few-Shot/Zero-Shot Prompting: LLMs provide "strong baselines using only a few demonstrations and no fine-tuning" (2304.11015v3.pdf). However, they "fall behind on commonly used benchmarks (e.g., Spider) compared to well-designed and fine-tuned models" (2304.11015v3.pdf).
Chain-of-Thought (CoT) Reasoning: "Chain-of-Thought (CoT) prompting elicits reasoning in large language models" (2409.14082v1.pdf). Many approaches leverage CoT to decompose complex problems into sub-tasks and guide step-by-step SQL generation (e.g., DIN-SQL, SGU-SQL).
Automatic CoT Generation (ACT-SQL) (2310.17342v1.pdf): ACT-SQL automatically generates CoT for dataset training examples, showing that "the generated auto-CoT can indeed improve the LLMs’ performance."
Reference-Enhanced Prompt (REp) (2403.09732v4.pdf): PET-SQL's REp includes customized instructions, basic database information, sampled cell values, optimization rules, and foreign key declarations to enhance prompt quality and guide LLMs to generate more efficient SQL.
Multi-Agent Collaboration:MAC-SQL (2312.11242v5.pdf): A "multi-agent collaborative framework" with a Decomposer (for CoT reasoning and SQL generation), a Selector (for database simplification), and a Refiner (for error correction).
CHESS (2405.16755v3.pdf): A multi-agent framework including an Information Retriever, Schema Selector, Candidate Generation, and Unit Tester, designed for configurable deployment scenarios while maintaining high performance.
Targeted Drilling (PTD-SQL) (2409.14082v1.pdf): Proposes "employing query group partitioning" to allow LLMs to focus on learning "thought processes specific to a single problem type," enhancing reasoning across difficulty levels and problem categories. This is inspired by how humans learn.
Multi-task Supervised Fine-tuning (MSFT) (2412.10138v1.pdf): ROUTE introduces additional SFT tasks like schema linking, noise correction, and continuation writing to enhance the model's understanding of SQL syntax and improve high-quality SQL generation.
2.6 Data Quality and Real-World Considerations
Real-world databases introduce complexities beyond just schema structure.

Data Quality Issues (24_Data_Centric_Text_to_SQL_wi.pdf): Up to "11-37% of the ground truth answers in the BIRD benchmark are incorrect due to data quality issues (duplication, disguised missing values, data types and inconsistent values)."
Data-Centric Framework (24_Data_Centric_Text_to_SQL_wi.pdf): Proposes an offline data preprocessing and cleaning approach that builds a relationship graph and incorporates business logic. This helps LLM agents "efficiently retrieve relevant tables and details during query time, significantly improving accuracy."
Database Description Generation (2502.20657v1.pdf): Addresses the "cold-start problem" when table and column descriptions are missing by automatically generating effective database descriptions using a dual coarse-to-fine and fine-to-coarse LLM-based process.
Ambiguity in Natural Language (2406.19073v2.pdf, p74-floratou.pdf, 20_Data_Ambiguity_Strikes_Back.pdf): NL queries can be vague or ambiguous, leading to multiple plausible SQL interpretations. Benchmarks like AMBROSIA (2406.19073v2.pdf) are being developed to test models' ability to recognize and interpret ambiguous queries across different types (scope, attachment, vagueness). "The perception of whether an NL query is ambiguous differs among human annotators which probably denotes that we need a better definition of ambiguity" (p74-floratou.pdf).
2.7 Evaluation Metrics and Benchmarks
Execution Accuracy (EX): The primary metric, comparing the execution output of the predicted SQL with the ground truth. It "provides a more precise estimate of the model’s performance since there may be multiple valid SQL queries" (2304.11015v3.pdf).
Exact-Set-Match Accuracy (EM): Compares clause-by-clause, requiring all components to match the ground truth. Does not consider values (2304.11015v3.pdf).
Valid Efficiency Score (VES): Measures the efficiency of valid SQLs generated (2312.11242v5.pdf).
Benchmarks:Spider: "A large-scale human-labeled dataset for complex and cross-domain semantic parsing and text-to-SQL task" (2402.17144v1.pdf). Queries categorized by difficulty (easy, medium, hard, extra hard).
BIRD: A more recent and challenging dataset with "12,751 unique question-SQL pairs, covering 95 large databases with a combined size of 33.4 GB." It incorporates external knowledge and detailed database catalogs (2405.16755v3.pdf).
AMBROSIA: A new benchmark specifically designed to "inform and inspire the development of parsers capable of recognizing and interpreting ambiguous queries." It covers scope, attachment, and vagueness ambiguities (2406.19073v2.pdf).
3. State-of-the-Art Approaches and Performance
CHASE-SQL (2410.01943v1.pdf): Achieves "state-of-the-art execution accuracy of 73.0 % and 73.01% on the test set and development set of the notable BIRD Text-to-SQL dataset benchmark." It employs innovative strategies like divide-and-conquer, query execution plan-based CoT, and instance-aware synthetic example generation, with a fine-tuned binary-candidates selection LLM.
DBCopilot (2312.03463v3.pdf): Outperforms retrieval-based baselines in schema routing by up to 19.88% recall and shows an execution accuracy improvement of 4.43%~11.22% for schema-agnostic NL2SQL.
PET-SQL (2403.09732v4.pdf): Achieves "new SOTA results on the Spider benchmark, with an execution accuracy of 87.6%." It uses a "reference-enhanced representation" prompt, preliminary SQL for schema linking, and "cross-consistency" across different LLMs for post-refinement.
RSL-SQL (2411.00073v2.pdf): Achieves 67.2% EX on BIRD dev and 87.9% EX on Spider using GPT-4o, setting a new SOTA among open-source methods on BIRD dev. It leverages bidirectional schema linking, contextual information augmentation, binary selection, and multi-turn self-correction.
Alpha-SQL (2502.17248v1.pdf): Achieves 69.7% execution accuracy on the BIRD development set using a 32B open-source LLM without fine-tuning, outperforming the best previous zero-shot approach based on GPT-4o by 2.5%. It uses a Monte Carlo Tree Search framework with LLM-as-Action-Model to generate SQL construction actions.
4. Challenges and Future Directions
Cost and Resource Intensiveness: Proprietary LLMs (e.g., GPT-4) are expensive, and even open-source LLMs require significant computational resources for training and inference, especially with complex prompting and multi-agent systems.
Synthetic Data Quality: While synthetic data generation is crucial for expanding training datasets and covering diverse domains, hallucination and generation bias can lead to "similar but wrong questions" and impact robustness (2312.03463v3.pdf). More sophisticated data synthesis techniques are needed.
Long Context Window Management: While newer LLMs (e.g., Gemini 1.5 Pro) handle long contexts well without "lost-in-the-middle" issues (2501.12372v4.pdf), larger contexts increase latency and computational cost. Optimizing the balance between context size and performance is ongoing.
Ambiguity Resolution: LLMs often struggle to fully capture and resolve ambiguity in NL questions, frequently predicting only one interpretation (2406.19073v2.pdf). Developing models capable of asking clarification questions or generating multiple plausible SQL queries is a critical area.
Foundation Models for Relational Databases: The development of "powerful and generic pre-trained models" that are inductive and can be applied "to entirely new relational databases out-of-the-box" is an unexplored opportunity (2312.04615v1.pdf).
Multi-Turn Conversations: Handling context-dependent questions in multi-turn text-to-SQL tasks remains challenging, requiring effective strategies for question rewriting and leveraging conversational history (2310.17342v1.pdf, 2405.02712v1.pdf).
Beyond Exact-Match Metrics: The limitations of current accuracy measures (e.g., string matching, parse tree matching) highlight the need for more robust metrics that evaluate semantic equivalence and user intent (p1737-kim.pdf, p74-floratou.pdf).
This briefing doc provides a comprehensive overview of the current landscape of AI for Text-to-SQL, highlighting the significant progress and the remaining challenges in this rapidly evolving field.
