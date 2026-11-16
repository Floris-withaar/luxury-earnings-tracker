#!/usr/bin/env bash
# Commit what a workflow changed to a new branch and open a pull request for a person to review.
# Usage: open-pr.sh <branch prefix> <title> <body> <path that must have changed>...
# Does nothing when none of the listed paths changed. Needs GH_TOKEN.
set -euo pipefail

prefix="$1"; title="$2"; body="$3"; shift 3

if [ -z "$(git status --porcelain -- "$@")" ]; then
  echo "Nothing changed. No pull request needed."
  exit 0
fi

stamp="$(date -u +%Y-%m-%d)"
branch="${prefix}-$(date -u +%Y%m%d-%H%M)"
git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
git checkout -b "$branch"
git add -A data site/data.json
git commit -m "${title} ${stamp}"
git push origin "$branch"
gh pr create --title "${title} ${stamp}" --body "$body" \
  || echo "::warning::The branch ${branch} was pushed. Open the pull request by hand, or allow Actions to create pull requests in the repository settings."
