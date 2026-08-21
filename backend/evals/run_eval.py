"""
Run the golden set through the editorial judge and report what it decided.

Usage, from the repository root:

    python -m backend.evals.run_eval                    # run and print a report
    python -m backend.evals.run_eval --save before.json # keep a baseline
    python -m backend.evals.run_eval --compare before.json

The intended rhythm is: save a baseline, change a prompt, run with --compare. What
you want to see is the disagreements - a case that flipped is either the improvement
you were aiming for or a regression you would not otherwise have noticed until the
feed went quiet.

This makes real model calls, so it needs an API key and costs one judge call per
case. It is deliberately not part of the pytest suite: CI should stay free and
deterministic, and this is neither.
"""

import argparse
import json
import sys
from typing import Any, Dict, List

from backend.app.agent.nodes.editorial_judge import editorial_judge_node
from backend.app.agent.persona.presets import DISTILL_PRESET
from backend.evals.golden_set import GOLDEN_SET, summarise


def _run_case(case, persona) -> Dict[str, Any]:
    """One candidate through the judge, reduced to what a comparison needs."""
    state = {
        "persona": persona,
        "agent_id": "",                     # no memory: judgement must not depend on history
        "candidates": [case.candidate],
        "candidate_idx": 0,
        "current_candidate": case.candidate,
        "judge_verdict": None,
        "draft": None,
        "qa_verdict": None,
        "retry_count": 0,
        "node_error": None,
        "published_post": None,
        "rejected_count": 0,
        "rejected_this_cycle": [],
        "mode": "topic",
        "coverage_trend": None,
        "cycle_outcome": "in_progress",
        "evaluated_candidates": [],
        "forced_publish": False,
        "post_type": None,
    }

    try:
        result = editorial_judge_node(state)
    except Exception as err:
        return {
            "id": case.candidate.id,
            "title": case.candidate.title,
            "expected": case.expected_decision,
            "actual": "error",
            "disqualifier": None,
            "scores": {},
            "error": str(err)[:200],
            "because": case.because,
        }

    verdict = result.get("judge_verdict")
    if verdict is None:
        return {
            "id": case.candidate.id,
            "title": case.candidate.title,
            "expected": case.expected_decision,
            "actual": "no_verdict",
            "disqualifier": None,
            "scores": {},
            "error": result.get("node_error"),
            "because": case.because,
        }

    return {
        "id": case.candidate.id,
        "title": case.candidate.title,
        "expected": case.expected_decision,
        "actual": verdict.decision,
        "disqualifier": verdict.disqualifier,
        "expected_disqualifier": case.expected_disqualifier,
        "scores": verdict.scores.model_dump(),
        "credibility": verdict.credibility,
        "error": None,
        "because": case.because,
    }


def run(persona=DISTILL_PRESET) -> List[Dict[str, Any]]:
    print(f"Running golden set against '{persona.name}' - {summarise()}\n")
    results = []
    for i, case in enumerate(GOLDEN_SET, 1):
        print(f"  [{i}/{len(GOLDEN_SET)}] {case.candidate.title[:60]}...", flush=True)
        results.append(_run_case(case, persona))
    return results


def report(results: List[Dict[str, Any]]) -> int:
    """Print the outcome. Returns the number of cases that did not match."""
    agreed = [r for r in results if r["actual"] == r["expected"]]
    disagreed = [r for r in results if r["actual"] != r["expected"]]

    print(f"\n{'=' * 74}")
    print(f"AGREED: {len(agreed)}/{len(results)}")
    print(f"{'=' * 74}")

    if disagreed:
        print("\nDISAGREEMENTS\n")
        for r in disagreed:
            print(f"  {r['title'][:64]}")
            print(f"    expected {r['expected']}, got {r['actual']}")
            if r.get("error"):
                print(f"    error: {r['error']}")
            elif r["actual"] == "reject":
                print(f"    disqualifier: {r['disqualifier']}")
                print(f"    scores: {r['scores']}")
            print(f"    this case tests: {r['because']}")
            print()

    # A case can reach the right decision for the wrong reason, which is how a set
    # quietly stops testing what it was written to test.
    wrong_reason = [
        r for r in agreed
        if r.get("expected_disqualifier")
        and r.get("disqualifier")
        and r["disqualifier"] != r["expected_disqualifier"]
    ]
    if wrong_reason:
        print("RIGHT DECISION, DIFFERENT REASON\n")
        for r in wrong_reason:
            print(f"  {r['title'][:64]}")
            print(f"    expected {r['expected_disqualifier']}, got {r['disqualifier']}")
            print()

    return len(disagreed)


def compare(baseline_path: str, current: List[Dict[str, Any]]) -> None:
    """Show only what changed against a saved run - the point of the exercise."""
    with open(baseline_path, encoding="utf-8") as fh:
        baseline = {r["id"]: r for r in json.load(fh)}

    changed = []
    for r in current:
        before = baseline.get(r["id"])
        if before and before["actual"] != r["actual"]:
            changed.append((before, r))

    print(f"\n{'=' * 74}")
    if not changed:
        print(f"No decisions changed against {baseline_path}.")
        print(f"{'=' * 74}")
        return

    print(f"{len(changed)} DECISION(S) CHANGED against {baseline_path}")
    print(f"{'=' * 74}\n")
    for before, after in changed:
        direction = "improved" if after["actual"] == after["expected"] else "REGRESSED"
        print(f"  [{direction}] {after['title'][:60]}")
        print(f"    {before['actual']} -> {after['actual']} (expected {after['expected']})")
        print(f"    scores {before['scores']} -> {after['scores']}")
        print()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--save", metavar="PATH", help="Write results to PATH as a baseline")
    parser.add_argument("--compare", metavar="PATH", help="Show what changed against a saved baseline")
    args = parser.parse_args()

    results = run()
    failures = report(results)

    if args.save:
        with open(args.save, "w", encoding="utf-8") as fh:
            json.dump(results, fh, indent=2)
        print(f"Baseline written to {args.save}")

    if args.compare:
        compare(args.compare, results)

    # Non-zero on disagreement, so this can gate a deliberate prompt change.
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
