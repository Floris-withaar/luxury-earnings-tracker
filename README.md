# Luxury Earnings Tracker

Quarterly sales growth of the large luxury groups in one sourced dataset, with a model on top and a website to read it.

Language models find and read the company releases. Fixed rules check their work and do the maths. A person approves every change before it goes live.

## Run it on your computer

You need Python 3.10 or newer. No API key is needed to view the site or run the model.

```bash
python -m pipeline.run serve
```

Then open http://localhost:8000.

To recompute the model and rebuild the site data after a change to `data/companies.json`:

```bash
python -m pipeline.run model
python -m unittest discover -s tests
```

## How it works

| Step | File | Who does it | What it does |
|---|---|---|---|
| 1. Research | `pipeline/research.py` | LLM with web search | Finds the newest quarterly release for each company in `config/watchlist.json`. Searches only once a release is due. |
| 2. Extract | `pipeline/extract.py` | LLM | Reads the release and returns each figure with the sentence or table row that states it. |
| 3. Verify | `pipeline/verify.py` | Rules | Checks that every quote and number is in the release. Flags implausible values and conflicts with stored figures. |
| 4. Model | `pipeline/model.py` | Arithmetic | Change against the prior quarter, peer medians, two-year growth, base effects, Asia gap and a rule-based signal. |
| 5. Interpret | `pipeline/interpret.py` | LLM | Writes a short note per company from the model output. A note containing a number that is not in the data is discarded and the rule-based note is kept. |

`pipeline/run.py` ties the steps together and writes `site/data.json`, the one file the website reads.

### The website

Five screens in `site/index.html`, with no build step and no framework:

- **Overview**: the finding for the quarter, four figures and three exhibits.
- **Compare**: pick companies, a measure and what to compare against (prior quarter, same quarter last year, the median of the others, or one company).
- **Company**: one page per group with its note, trend, segments, regions, base effect and sources.
- **Data and sources**: every figure, whether it comes from the company or from the press, and the evidence behind it.
- **Method**: definitions, signal rules, the pipeline and its recent runs.

### What is trusted and what is checked

- The LLM never computes a figure. It finds, quotes and describes.
- A figure is merged automatically only if its quote and its number are both found in the release text. Everything else lands in `data/review/` as a draft.
- The check catches copying errors. It does not prove that a release is genuine, so the research step is told to use company sites and regulatory wires.
- Scheduled updates arrive as a pull request. Nothing reaches the live site without a person merging it.

## Commands that use the LLM

These need an Anthropic API key. API usage is billed separately from a Claude subscription.

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...

python -m pipeline.run update                 # check companies whose release is due, write drafts to data/review
python -m pipeline.run update --apply         # also merge drafts in which every figure matched
python -m pipeline.run add "Burberry" --url https://...   # one company from a known release
python -m pipeline.run add "Burberry" --file release.pdf  # or from a file
python -m pipeline.run apply data/review/burberry-group-2026Q3.json   # merge a draft you have checked
python -m pipeline.run interpret              # rewrite the notes with the LLM
python -m pipeline.run eval                   # measure extraction accuracy against the verified figures
```

### What it costs to run

Hosting and automation on GitHub are free for a public repository. The only running cost is the API.

The pipeline is set up to keep that low:

- Research runs on the cheapest model (`claude-haiku-5-5`) with at most three searches per company.
- A company is searched only once its next release is due. `config/watchlist.json` holds, per company and quarter, how many days after quarter end it reported last time. Use `--force` to search anyway.
- Extraction and the written notes use `claude-sonnet-5-5` and only run when a new release is found.

At list prices this comes to roughly 5 to 8 US dollars a year for six companies, with nothing spent in weeks when no release is due. That figure is an estimate. Every run that calls the API writes its token counts, search count and estimated cost to `data/run_log.json`, and the Method screen shows it.

Each step's model can be changed with `TRACKER_MODEL_RESEARCH`, `TRACKER_MODEL_EXTRACT` and `TRACKER_MODEL_INTERPRET`.

## Put it online with GitHub Pages

1. Create a repository on GitHub and push this folder to the `main` branch.
2. In the repository, open Settings, then Pages, and set Source to "GitHub Actions".
3. The `Test and deploy site` workflow runs on every push to `main` and publishes the `site` folder.

## Automatic updates

The `Update data` workflow runs every Monday and can be started by hand from the Actions tab.

1. Add a repository secret named `ANTHROPIC_API_KEY` (Settings, Secrets and variables, Actions).
2. In Settings, Actions, General, allow GitHub Actions to create pull requests.
3. When a new release is found, the workflow opens a pull request with the new figures and the drafts that need review. Merging it redeploys the site.

## The data

`data/companies.json` holds one record per company:

- `series`: group growth by calendar quarter (`g`), with revenue (`rev`) and the company's own period label where given. `s` points at an entry in `sources`.
- `regions`: growth by quarter for five buckets (`asia`, `japan`, `europe`, `americas`, `me`), each with the company's own label and a note where the bucket is a loose fit.
- `segments`, `china`, `guidance`, `sources`.

Growth is on the underlying basis each company publishes: organic, constant exchange rates or comparable. Periods are filed under the calendar quarter in which they end. No figure is derived or estimated. See the Method section of the site for the scope differences between companies.

## Status

- The six companies and five quarters in the dataset were entered and checked by hand against the linked sources on 15 November 2026.
- Steps 3 and 4 and the website are covered by tests and run without a key.
- Steps 1, 2 and 5 are tested with a stand-in for the API. They have not yet been run against the live API or on GitHub Actions.

This is a study project built from public company releases. It gives no investment advice.
