"""Command line entry point.

    python -m pipeline.run model                 recompute the model and rebuild the site data (no API key needed)
    python -m pipeline.run serve                 open the site on http://localhost:8000
    python -m pipeline.run update [--apply]      research, extract and verify releases that are due (--force to search anyway)
    python -m pipeline.run add "Burberry" --url https://...    extract one release into a review file
    python -m pipeline.run apply data/review/x.json            merge a reviewed draft into the dataset
    python -m pipeline.run interpret             rewrite the commentary with the LLM
    python -m pipeline.run eval                  score the extraction stage against the verified dataset
"""
from __future__ import annotations

import argparse
import sys

from . import extract, fetch, interpret, llm, model, research, verify
from .common import (COMMENTARY, COMPANIES, DATA, DERIVED, REGION_KEYS, REVIEW, SITE, WATCHLIST, growth, load, now_iso,
                     region, save)

RUN_LOG = DATA / "run_log.json"


def rebuild(dataset: dict, *, use_llm: bool, client=None) -> None:
    """Steps 4 and 5, then write the single file the website reads."""
    derived = model.compute(dataset)
    save(DERIVED, derived)
    old = load(COMMENTARY, {})
    notes = {q: interpret.interpret(dataset, derived, q, client=client, use_llm=use_llm and q == dataset["latest"], previous=old.get(q))
             for q in derived}
    save(COMMENTARY, notes)
    save(SITE / "data.json", {
        "asOf": dataset["asOf"], "latest": dataset["latest"], "companies": dataset["companies"],
        "model": derived, "notes": notes,
        "meta": {"built_at": now_iso(), "runs": load(RUN_LOG, [])[-5:],
                 "thresholds": {"momentum_pts": model.MOMENTUM_PTS, "level_pts": model.LEVEL_PTS,
                                "asia_gap_pts": model.ASIA_GAP_PTS, "base_shift_pts": model.BASE_SHIFT_PTS}},
    })


def log_run(command: str, results: list[dict]) -> None:
    runs = load(RUN_LOG, [])
    entry = {"at": now_iso(), "command": command, "results": results}
    if llm.USAGE:
        entry["usage"] = llm.usage_summary()
    runs.append(entry)
    save(RUN_LOG, runs[-30:])


def process_release(dataset: dict, name: str, text: str, source: dict, *, client, company_id: str | None, apply: bool) -> dict:
    """Steps 2 and 3 for one release. Always leaves a review file behind."""
    draft = extract.extract(name, text, client=client, source=source)
    existing = next((c for c in dataset["companies"] if c["id"] == company_id), None)
    if existing:
        draft["company"].update(id=existing["id"], name=existing["name"], basis=existing["basis"], cur=existing.get("cur") or draft["company"]["cur"])
    if not draft["calendar_quarter"] and source.get("calendar_quarter"):
        draft["calendar_quarter"] = source["calendar_quarter"]
    verify.verify_draft(draft, text, existing)
    path = REVIEW / f"{draft['company']['id']}-{draft['calendar_quarter'] or 'unknown'}.json"
    save(path, draft)
    status = "needs review"
    if apply and draft["auto_merge"]:
        verify.merge_draft(dataset, draft)
        dataset["asOf"] = now_iso()[:10]
        status = "merged"
    return {"company": draft["company"]["name"], "quarter": draft["calendar_quarter"], "status": status,
            "checks": f"{draft['checks']['ok']}/{draft['checks']['total']}", "flags": draft["flags"], "file": str(path.relative_to(DATA.parent))}


def cmd_model(args) -> int:
    dataset = load(COMPANIES)
    rebuild(dataset, use_llm=False)
    block = model.compute(dataset)[dataset["latest"]]
    print(f"Model rebuilt for {len(dataset['companies'])} companies. Latest quarter {dataset['latest']}: median {block['peer']['median']}%.")
    for cid, m in sorted(block["companies"].items(), key=lambda kv: kv[1]["rank"]):
        print(f"  {m['rank']}. {cid:<10} growth {m['growth']:>5}%  change {m['delta']}  two-year {m['two_year_stack']}  {m['signal']['label']}  {m['signal']['flags']}")
    return 0


def cmd_update(args) -> int:
    client = llm.get_client()
    dataset = load(COMPANIES)
    results = []
    for entry in load(WATCHLIST)["companies"]:
        if args.company and entry["id"] != args.company:
            continue
        company = next((c for c in dataset["companies"] if c["id"] == entry["id"]), None)
        known = research.latest_known_quarter(company)
        if not args.force and not research.is_due(entry, known):
            results.append({"company": entry["name"], "status": "not due", "detail": f"next check from {research.due_date(entry, known)}"})
            continue
        try:
            found = research.find_release(entry, known, client=client)            # step 1
            if not research.is_newer(found, known):
                results.append({"company": entry["name"], "status": "no newer release", "detail": found.get("why", "")[:200]})
                continue
            text, used = None, None
            for url in [found["url"], *[u for u in (found.get("alternates") or []) if isinstance(u, str)]][:3]:
                try:
                    text, used = fetch.fetch_text(url), url
                    if len(text) > 500:
                        break
                except Exception:
                    continue
            if not text or len(text) < 500:
                results.append({"company": entry["name"], "status": "could not fetch", "detail": found["url"]})
                continue
            source = {"url": used, "title": found.get("title"), "publisher": found.get("publisher"),
                      "published": found.get("published"), "calendar_quarter": found.get("calendar_quarter")}
            results.append(process_release(dataset, entry["name"], text, source, client=client, company_id=entry["id"], apply=args.apply))
        except Exception as exc:
            results.append({"company": entry["name"], "status": "error", "detail": f"{type(exc).__name__}: {exc}"[:200]})
    changed = any(r["status"] == "merged" for r in results)
    if changed:
        save(COMPANIES, dataset)
    # The written notes are only redone when figures changed, so a quiet week costs nothing.
    rebuild(dataset, use_llm=changed, client=client)
    log_run("update", results)
    rebuild(dataset, use_llm=False)
    for r in results:
        print(r)
    print("Estimated API cost of this run: $%.4f" % llm.usage_summary()["estimated_usd"])
    return 0


def cmd_add(args) -> int:
    client = llm.get_client()
    dataset = load(COMPANIES)
    if args.file:
        text, source = fetch.read_file(args.file), {"url": args.url or "", "title": f"Results release, {args.name}"}
    elif args.url:
        text, source = fetch.fetch_text(args.url), {"url": args.url, "title": f"Results release, {args.name}"}
    else:
        found = research.find_release({"name": args.name}, None, client=client)
        if not found.get("found"):
            print("No release found:", found.get("why"))
            return 1
        text = fetch.fetch_text(found["url"])
        source = {"url": found["url"], "title": found.get("title"), "publisher": found.get("publisher"),
                  "published": found.get("published"), "calendar_quarter": found.get("calendar_quarter")}
    result = process_release(dataset, args.name, text, source, client=client, company_id=None, apply=args.apply)
    if result["status"] == "merged":
        save(COMPANIES, dataset)
    log_run(f"add {args.name}", [result])
    rebuild(dataset, use_llm=result["status"] == "merged", client=client)
    print(result)
    return 0


def cmd_apply(args) -> int:
    dataset, draft = load(COMPANIES), load(args.path if args.path.is_absolute() else DATA.parent / args.path)
    if draft is None:
        print("No such review file.")
        return 1
    if not draft.get("auto_merge") and not args.force:
        print(f"Not merged. {draft['checks']['ok']} of {draft['checks']['total']} figures matched the release.")
        for flag in draft.get("flags", []):
            print("  flag:", flag)
        for fig in draft["figures"]:
            if fig["check"] != "ok":
                print(f"  {fig['check']:<4} {fig['label']}: {fig.get('v')} | {fig.get('quote')!r}")
        print("Check these against the release, correct the review file if needed, then rerun with --force.")
        return 2
    verify.merge_draft(dataset, draft)
    dataset["asOf"] = now_iso()[:10]
    save(COMPANIES, dataset)
    log_run(f"apply {args.path.name}", [{"company": draft["company"]["name"], "quarter": draft["calendar_quarter"], "status": "merged by hand"}])
    rebuild(dataset, use_llm=False)
    print(f"Merged {draft['company']['name']} {draft['calendar_quarter']}.")
    return 0


def cmd_interpret(args) -> int:
    rebuild(load(COMPANIES), use_llm=True, client=llm.get_client())
    notes = load(COMMENTARY)[load(COMPANIES)["latest"]]["companies"]
    for cid, n in notes.items():
        print(f"{cid}: by {n['by']}" + (f" (rejected: {n['rejected']})" if n.get("rejected") else ""))
    return 0


def cmd_eval(args) -> int:
    """Run extraction on releases whose figures are already verified, and count the matches."""
    client = llm.get_client()
    dataset, hits, total = load(COMPANIES), 0, 0
    q = dataset["latest"]
    for company in dataset["companies"]:
        entry = (company.get("series") or {}).get(q)
        source = company["sources"][entry["s"]] if entry and company.get("sources") else None
        if not source or not source.get("url"):
            continue
        try:
            draft = extract.extract(company["name"], fetch.fetch_text(source["url"]), client=client)
        except Exception as exc:
            print(f"{company['name']}: skipped ({type(exc).__name__})")
            continue
        got = {"group": draft["figures"][0].get("v")}
        got.update({f["bucket"]: f["v"] for f in draft["figures"] if f["kind"] == "region"})
        want = {"group": growth(company, q), **{k: region(company, q, k) for k in REGION_KEYS if region(company, q, k) is not None}}
        for key, value in want.items():
            total += 1
            ok = got.get(key) is not None and abs(got[key] - value) < 0.05
            hits += ok
            if not ok:
                print(f"  {company['name']} {key}: expected {value}, extracted {got.get(key)}")
    print(f"Extraction accuracy on verified figures: {hits} of {total}.")
    return 0


def cmd_serve(args) -> int:
    import functools
    import http.server

    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(SITE))
    with http.server.ThreadingHTTPServer(("127.0.0.1", args.port), handler) as server:
        print(f"Serving the tracker on http://localhost:{args.port}  (Ctrl+C to stop)")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
    return 0


def main(argv=None) -> int:
    from pathlib import Path

    parser = argparse.ArgumentParser(prog="python -m pipeline.run", description="Luxury Earnings Tracker pipeline")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("model").set_defaults(func=cmd_model)
    p = sub.add_parser("serve"); p.add_argument("--port", type=int, default=8000); p.set_defaults(func=cmd_serve)
    p = sub.add_parser("update"); p.add_argument("--company"); p.add_argument("--apply", action="store_true"); p.add_argument("--force", action="store_true", help="search even when no release is due"); p.set_defaults(func=cmd_update)
    p = sub.add_parser("add"); p.add_argument("name"); p.add_argument("--url"); p.add_argument("--file"); p.add_argument("--apply", action="store_true"); p.set_defaults(func=cmd_add)
    p = sub.add_parser("apply"); p.add_argument("path", type=Path); p.add_argument("--force", action="store_true"); p.set_defaults(func=cmd_apply)
    sub.add_parser("interpret").set_defaults(func=cmd_interpret)
    sub.add_parser("eval").set_defaults(func=cmd_eval)
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except llm.LLMUnavailable as exc:
        print(f"This command needs the LLM: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
