# Complete Architecture Flow

```mermaid
flowchart TD
    User["User"] --> UI["React dashboard"]
    UI -->|"Initialize persona"| Init["POST /api/agent/init"]
    Init --> Idempotent{"Active agent with\nsame name + domain?"}
    Idempotent -->|"yes"| Resume["Return existing agent ID\nand ensure scheduler runs"]
    Idempotent -->|"no"| Persona["Load preset + optional bio override"]
    Persona --> SaveAgent[("SQLite: agents")]
    SaveAgent --> Schedule["Create per-agent scheduler task"]
    Resume --> Schedule

    Schedule --> Limits{"Within 48 hours\nand below post cap?"}
    Limits -->|"no"| Stop["Deactivate agent\nand stop task"]
    Limits -->|"yes"| Cycle["Execute cycle in worker thread"]

    Cycle --> Discover["Discover topic candidates"]
    Discover --> Sources["HN · arXiv · GitHub · Tavily/DDG"]
    Sources --> Prefilter["Deterministic prefilter\nstale · thin · credibility · cap 10"]
    Prefilter --> RejectHistory["Skip previously rejected URLs"]
    RejectHistory --> Duplicate["Hybrid duplicate check\nMiniLM cosine + IDF lexical overlap"]
    Duplicate --> Spacing["Defer topics near latest post"]
    Spacing --> Trend{"Coverage trend\ndetected?"}

    Trend -->|"yes"| ReflectionWriter["Reflection writer\nLLM structured output"]
    Trend -->|"no"| Candidate{"Candidate available?"}
    Candidate -->|"no"| NoCandidates["Outcome: no_novel_candidates"]
    Candidate -->|"yes"| Judge["Editorial judge\nLLM structured output"]

    Judge --> JudgeError{"Infrastructure error?"}
    JudgeError -->|"yes"| Abort["Abort cycle\nnever fabricate rejection"]
    JudgeError -->|"no"| EditorialPass{"Passes editorial\nthresholds?"}
    EditorialPass -->|"no"| LogReject["Persist rejection + reason"]
    EditorialPass -->|"yes"| Writer["Topic writer\nLLM structured output"]

    ReflectionWriter --> DraftReady["Draft ready"]
    Writer --> DraftReady
    DraftReady --> QA["QA judge\nLLM structured output"]
    QA --> QAError{"Infrastructure error?"}
    QAError -->|"yes"| Abort
    QAError -->|"no"| QAPass{"QA pass?"}
    QAPass -->|"yes"| Publish["Save post, rationale, and sources"]
    QAPass -->|"topic revise\n< 2 revisions"| Writer
    QAPass -->|"reflection revise\n< 2 revisions"| ReflectionWriter
    QAPass -->|"topic failed"| LogReject
    QAPass -->|"reflection failed"| Abort

    LogReject --> NextCandidate{"Another candidate?"}
    NextCandidate -->|"yes"| Judge
    NextCandidate -->|"no"| AllRejected["Outcome: all_rejected"]

    Publish --> SQLite[("SQLite: posts, cycle_runs")]
    Publish --> Embed["Embed published post\nall-MiniLM-L6-v2"]
    Embed --> Chroma[("ChromaDB: agent vectors")]

    NoCandidates --> Audit[("SQLite: cycle_runs")]
    AllRejected --> Audit
    Abort --> Audit
    SQLite --> Audit
    Audit --> NextRun["Calculate jittered next run\nand persist next_run_at"]
    NextRun --> Schedule

    UI -->|"Poll every 20 seconds"| ReadAPI["GET feed · status · rejected"]
    ReadAPI --> SQLite
```

## LLM touchpoints

| Node | Trigger | Maximum logical calls per cycle branch |
| --- | --- | --- |
| Editorial judge | Each candidate after deterministic triage | 1 per candidate |
| Topic writer | Editorial pass; QA requests revision | 3 per candidate |
| Reflection writer | Coverage trend; QA requests revision | 3 per reflection |
| QA judge | Each generated draft | 3 per topic/reflection branch |

Every structured call can retry up to three times for transient malformed provider responses. All other flowchart stages are local code, SQLite/ChromaDB operations, or external discovery requests.
