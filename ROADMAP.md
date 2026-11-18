# Roadmap

The aim: a sourced record of what the large luxury groups report each quarter, kept current by a pipeline whose every figure can be traced to the company's own words.

## Where it stands

| Phase | What | Status |
|---|---|---|
| 0 | Dataset of six groups and five quarters, model, five-screen site, pipeline code | Done |
| 1 | Prove it works: data gate, flow test, browser test on every change, live run, extraction score | Done. First live run on 16 November 2026 found three defects, all fixed. A second run confirms the fixes. |
| 2 | Secure it: source allowlist, download guards, hash-checked dependencies, content security policy, self-hosted fonts, protected `main` | Done |
| 3 | Deepen the data: company sources for the press figures, eight quarters of history, more groups | Done. No press-sourced figures remain, history covers eight quarters, and sixteen companies sit in three peer groups. Open: link the guidance and China commentary to a source. |
| 4 | Explain it: architecture diagram, this roadmap, notes on using it for another sector | Done in the README |

## Phase 3 in detail

1. Done. Every figure now cites a company document. LVMH's regional figures were checked by hand against its slides, which automated tools may not read. Still to do: link the guidance and China commentary to a source.
2. Done. Nine companies have eight quarters, from Q4 2024 to Q3 2026. Brunello Cucinelli has five: it publishes no second-quarter figure, and its fourth quarter of 2024 came without a constant-rate basis.
3. Done. Burberry, Zegna, Brunello Cucinelli and Ferragamo are in, which makes ten. Swatch Group is left out because it publishes sales only twice a year, which a quarterly tracker cannot use. Pandora joined on 18 November 2026 as an eleventh personal luxury goods group, in jewellery and watches. The charts have eight checked colours plus two neutrals, so no hue is made up for the eleventh: its line is grey and dotted. Beyond about a dozen, the peer median stops meaning "large luxury", so further companies come in as separate peer groups, described below.
4. After two reporting seasons, publish how often the pipeline found the release, how many figures it extracted correctly and what it cost.

## The finish line: compare across groups, regions and industries

Once the data is deep enough, the tracker compares more than companies with each other:

1. **Peer groups.** Each company gets a group, such as fashion and leather, jewellery and watches, or luxury cars. Each group has its own median, and groups can be set side by side. Car makers and other industries enter here, never into the luxury goods median.
2. **Regions that line up.** Companies cut Asia differently: some report Japan alone, some fold it into the rest of Asia. A second set of region columns handles that, so regions compare like with like.
3. **Segments.** Leather goods against jewellery against watches, across companies.

Status on 18 November 2026, moved forward at Floris's request:

- **Peer groups: built.** `config/categories.json` puts each company in an industry (personal luxury goods or luxury autos) and a focus (fashion and leather goods, jewellery and watches, diversified, sports cars). Medians, ranks and "against peers" are taken inside one industry, and only when at least three companies stand behind them. The Categories screen sets the groups side by side.
- **Luxury autos: Ferrari and Aston Martin.** Porsche is left out for the same reason as Swatch: it publishes revenue for the year to date, not for the quarter. With two companies, the autos group shows both and has no median until a third quarterly reporter joins.
- **Accessible luxury: Ralph Lauren, Tapestry and Capri Holdings.** A third industry with its own median. All three have fiscal years that differ from the calendar, so each quarter is filed under the calendar quarter it ends in. Capri's history starts in Q2 2025, the first quarter it reported without Versace.
- **Segments: built.** Segment lines are grouped into product categories across companies. Q2 and Q3 2026 are in, so the Categories screen shows where each line stood a quarter earlier.
- **Regions that line up: not started.** Next after the January season.

## Decided against

| Idea | Why not |
|---|---|
| Forecasts and share prices | The project reports what companies said. A forecast would need a track record this project does not have. |
| A chatbot or user accounts | They add an attack surface and running costs without making a figure more reliable. |
| A database or a server | The dataset is one small file. Git already gives history, review and rollback. |
| More than about a dozen companies in one peer group | Depth and checked sources matter more than breadth. New industries come in as their own peer group. |
| Porsche | It publishes revenue for the year to date only. A quarter backed out of cumulative figures would be derived, which the dataset does not allow. |
| More chart types | Six screens answer the questions. New charts are added only for a question the current ones cannot answer. |

## How a new figure gets in

1. The research step finds a release once it is due.
2. The link must be on the allowlist to be merged automatically.
3. The extract step returns each figure with the words that state it.
4. The verify step confirms the words and the number are in the release.
5. The data gate checks the whole dataset.
6. A person reviews the pull request and merges it.
