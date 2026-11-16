# Security

This is a public study project. It holds no personal data and no secrets in the repository. The one secret it uses is an Anthropic API key, kept as a GitHub repository secret.

## What could go wrong, and what stops it

| Risk | Protection |
|---|---|
| A wrong figure reaches the site | A figure is merged only when its quoted words and its number are both in the release. The data gate (`pipeline/validate.py`) then checks the whole dataset. Every change arrives as a pull request that a person merges. |
| A fake or edited release is used | Automatic merging is limited to links on the allowlist: the company domains in `config/watchlist.json` and the regulatory wires in `pipeline/fetch.py`. Releases from anywhere else wait in `data/review`. |
| Instructions hidden in a release steer the LLM | The release is passed as data and the prompt says so. The LLM cannot run tools in the extract and interpret steps. Whatever it returns still has to match the release text and pass the data gate. |
| The pipeline is pointed at an internal address | Downloads are refused for anything that is not http or https, for private, local and link-local addresses, and for redirects that lead to them. |
| The API key leaks or is overused | The key is a repository secret and is only passed to the steps that call the API. It is never printed or committed. Keep it in its own workspace with a monthly spend limit, and rotate it if in doubt. Pull requests from forks do not receive secrets. |
| A dependency or workflow action is tampered with | Every Python package, including indirect ones, is pinned with a hash and installed with `--require-hashes`, so a changed file is refused. Workflow actions are pinned to commit ids. Dependabot proposes updates monthly. Workflows start with read-only permissions and widen them only where needed. |
| The website runs something it should not | The site is static. A content security policy allows scripts, styles and fonts from the site itself only, and the site makes no request to any other host. All text from the dataset is written as text, never as HTML. The browser test fails on any policy violation or outside request. |

## Known limits

- Some investor sites refuse automated downloads. The pipeline identifies itself honestly and does not work around that. Those releases are added by hand with `add --file` and always wait for review.
- The address check and the download resolve a hostname separately. A hostile domain could answer differently the second time. Automatic downloads only go to allowlisted domains, which keeps this theoretical.
- The quote check proves a figure was copied correctly. It cannot prove the release is genuine. The allowlist and the review of each pull request cover that.

## Repository settings to keep

- Branch protection on `main`: require a pull request and the two checks (`Tests and data gate`, `Browser test of the site`) before merging.
- Dependabot alerts and security updates: on.
- Automatically delete head branches: on.
- Pages source: GitHub Actions.
- Actions: allow GitHub Actions to create pull requests. Keep the default token permission at read.
- Secret scanning and push protection: on.

## Reporting a problem

Open an issue on the repository. Never paste a key or other secret into an issue.
