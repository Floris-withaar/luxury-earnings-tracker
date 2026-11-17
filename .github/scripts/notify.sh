#!/usr/bin/env bash
# Tell the repository owner that something needs attention, through a GitHub issue.
# Usage: notify.sh <report file> <label> <title> [--close-when-clean]
#   The report has text: open an issue with this label, or add a comment if one is already open.
#   GitHub emails the assignee either way.
#   The report is empty and --close-when-clean is given: close the open issue, because the problem is gone.
# Needs GH_TOKEN with issues: write, GH_REPO and OWNER.
set -euo pipefail

report="$1"; label="$2"; title="$3"; mode="${4:-}"

gh label create "$label" --color "B60205" --description "Raised automatically by a workflow" --force >/dev/null 2>&1 || true
open="$(gh issue list --label "$label" --state open --json number --jq '.[0].number // empty')"

if [ -s "$report" ]; then
  if [ -n "$open" ]; then
    gh issue comment "$open" --body-file "$report"
  else
    gh issue create --title "$title" --label "$label" --assignee "$OWNER" --body-file "$report"
  fi
elif [ -n "$open" ] && [ "$mode" = "--close-when-clean" ]; then
  gh issue close "$open" --comment "The watch is clean again. Closing."
else
  echo "Nothing to report."
fi
