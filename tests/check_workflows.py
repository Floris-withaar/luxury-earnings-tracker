"""Checks the workflow files themselves. A workflow GitHub cannot read never runs, and says so nowhere obvious.

    python tests/check_workflows.py        (needs: pip install -r requirements-dev.txt)

It fails when a workflow file is not valid YAML, lacks a name, a trigger or jobs,
or uses an action that is not pinned to a full commit id.
"""
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
PINNED = re.compile(r"^[\w.-]+/[\w./-]+@[0-9a-f]{40}$")


def problems_in(path: Path) -> list[str]:
    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        return [f"not valid YAML: {str(exc).splitlines()[0]} (line {getattr(getattr(exc, 'problem_mark', None), 'line', -1) + 1})"]
    if not isinstance(doc, dict):
        return ["is not a mapping"]
    found = []
    if not doc.get("name"):
        found.append("has no name")
    if "on" not in doc and True not in doc:      # YAML reads the bare word `on` as true
        found.append("has no trigger")
    jobs = doc.get("jobs") or {}
    if not jobs:
        found.append("has no jobs")
    for job_id, job in jobs.items():
        steps = (job or {}).get("steps") or []
        if not steps:
            found.append(f"job {job_id} has no steps")
        for step in steps:
            uses = step.get("uses")
            if uses and not uses.startswith("./") and not PINNED.match(uses):
                found.append(f"job {job_id} uses {uses}, which is not pinned to a commit id")
            if "run" in step and not isinstance(step["run"], str):
                found.append(f"job {job_id} has a run step that is not text")
    return found


def main() -> int:
    files = sorted((ROOT / ".github" / "workflows").glob("*.y*ml"))
    failures = [f"{path.name}: {p}" for path in files for p in problems_in(path)]
    scripts = sorted((ROOT / ".github" / "scripts").glob("*.sh"))
    failures += [f"{s.name}: is not marked executable" for s in scripts if not s.stat().st_mode & 0o111]
    for f in failures:
        print("FAIL", f)
    print(f"Workflow check: {len(files)} workflow files and {len(scripts)} scripts, {len(failures)} problems.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
