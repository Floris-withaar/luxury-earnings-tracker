# Roadmap

The aim: a sourced record of what the large luxury groups report each quarter, kept current by a pipeline whose every figure can be traced to the company's own words.

## Where it stands

| Phase | What | Status |
|---|---|---|
| 0 | Dataset of six groups and five quarters, model, five-screen site, pipeline code | Done |
| 1 | Prove it works: data gate, flow test, browser test on every change, live run, extraction score | Done. First live run on 16 November 2026 found three defects, all fixed. A second run confirms the fixes. |
| 2 | Secure it: source allowlist, download guards, hash-checked dependencies, content security policy, self-hosted fonts, protected `main` | Done |
| 3 | Deepen the data: company sources for the press figures, eight quarters of history, four more groups | In progress. Press figures down from 19 to 8, history extended to eight quarters. Four more groups are next. |
| 4 | Explain it: architecture diagram, this roadmap, notes on using it for another sector | Done in the README |

## Phase 3 in detail

1. Done for Hermès and Kering. LVMH's eight regional figures are in the company's slides, which automated tools may not read; they stay marked Press until a person confirms them against the slides. Still to do: link the guidance and China commentary to a source.
2. Done. Every company has eight quarters, from Q4 2024 to Q3 2026.
3. Add Burberry, Zegna, Brunello Cucinelli and Swatch Group. The limit is about ten groups: beyond that the peer median stops meaning "large luxury".
4. After two reporting seasons, publish how often the pipeline found the release, how many figures it extracted correctly and what it cost.

## Decided against

| Idea | Why not |
|---|---|
| Forecasts and share prices | The project reports what companies said. A forecast would need a track record this project does not have. |
| A chatbot or user accounts | They add an attack surface and running costs without making a figure more reliable. |
| A database or a server | The dataset is one small file. Git already gives history, review and rollback. |
| More than about ten companies | Depth and checked sources matter more than breadth. |
| More chart types | Five screens answer the questions. New charts are added only for a question the current ones cannot answer. |

## How a new figure gets in

1. The research step finds a release once it is due.
2. The link must be on the allowlist to be merged automatically.
3. The extract step returns each figure with the words that state it.
4. The verify step confirms the words and the number are in the release.
5. The data gate checks the whole dataset.
6. A person reviews the pull request and merges it.
