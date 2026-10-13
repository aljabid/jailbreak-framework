#!/usr/bin/env python3
"""One-command driver for the journal study on the lab GPU machine.

After cloning the repository, putting the signing key in .env and starting Ollama, the
whole study is two commands:

  python research/remote_gpu/study.py prepare --accept-terms
  python research/remote_gpu/study.py run --budget-hours 75

`prepare` downloads the public benchmark files (only with --accept-terms, see
scripts/fetch_benchmarks.py), imports them, builds the base-prompt corpus and runs the
smoke test. `run` measures the real speed of every model, chooses how many prompts fit the
budget, then works in stages (N=300, 700, then the maximum): generate answers, score them
with Llama Guard, score a sample with the two local LLM judges, and write the zip files to
send back. It is resumable: after any stop, run the same command again.

  python research/remote_gpu/study.py status
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import NamedTuple

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run_all  # noqa: E402

ROOT = run_all.ROOT
DATA = ROOT / "research" / "data_journal"
STATE = ROOT / "outputs" / "study_state.json"
CORPUS = DATA / "journal_full_corpus.json"

IMPORTS = [  # (source, input file, extra args, output file)
    ("advbench", "advbench_harmful_behaviors.csv", [], "imported_advbench.json"),
    ("harmbench", "harmbench_behaviors_text_all.csv", ["--filter", "FunctionalCategory=standard"],
     "imported_harmbench_standard.json"),
    ("strongreject", "strongreject_dataset.csv", [], "imported_strongreject.json"),
    ("jailbreakbench", "jbb_harmful_behaviors.csv", [], "imported_jbb.json"),
    ("sorrybench", "question.jsonl", [], "imported_sorrybench.json"),
    ("xstest", "xstest_prompts.csv", ["--filter", "label=unsafe"], "imported_xstest_unsafe.json"),
    ("xstest", "xstest_prompts.csv", ["--filter", "label=safe"], "imported_xstest_safe.json"),
]


class Plan(NamedTuple):
    stages: list[int]
    n_max: int
    judge_k_max: int
    projected_generation_hours: float


def plan_stages(sec_per_attack_all_models: float, corpus: int, budget_hours: float, *,
                n_models: int, strategies: int = 6, variations: int = 1,
                gen_share: float = 0.60, judge_share: float = 0.24,
                judge_sec_per_pair: float = 5.0, first_stages: tuple[int, ...] = (300, 700)) -> Plan:
    """Choose the stage sizes and judge sample from the measured speed and the budget.

    sec_per_attack_all_models is the sum over models of the measured seconds per attack,
    because every prompt/strategy pair is run on every model.
    """
    per_prompt_h = sec_per_attack_all_models * strategies * variations / 3600
    gen_hours = budget_hours * gen_share
    n_max = min(corpus, int(gen_hours / per_prompt_h)) if per_prompt_h > 0 else corpus
    if n_max < 50:
        raise ValueError(f"budget too small: only {n_max} prompts would fit; raise --budget-hours")
    stages = sorted({min(s, n_max) for s in first_stages} | {n_max})
    judge_per_prompt_h = n_models * strategies * judge_sec_per_pair / 3600
    k_max = max(50, min(n_max, int(budget_hours * judge_share / judge_per_prompt_h)))
    return Plan(stages, n_max, k_max, n_max * per_prompt_h)


def sh(cmd: list[str], env: dict | None = None) -> int:
    print("  $", " ".join(cmd), flush=True)
    return subprocess.run(cmd, cwd=ROOT, env=env).returncode


def load_state() -> dict:
    if STATE.exists():
        return json.loads(STATE.read_text(encoding="utf-8"))
    return {}


def save_state(state: dict) -> None:
    STATE.parent.mkdir(exist_ok=True)
    STATE.write_text(json.dumps(state, indent=1), encoding="utf-8")


def make_args(args: argparse.Namespace, n: int = 0, arm: str = "main") -> argparse.Namespace:
    return argparse.Namespace(prompts=args.prompts, grant=args.grant, n=n, variations=1,
                              concurrency=args.concurrency, smoke=False, hours=0, arm=arm)


# ---------------------------------------------------------------- prepare
def prepare(args: argparse.Namespace) -> int:
    fetch = [sys.executable, "scripts/fetch_benchmarks.py"]
    if args.accept_terms:
        fetch.append("--accept-terms")
    if args.only:
        fetch += ["--only", *args.only]
    code = sh(fetch)
    if code == 2:
        print("\nRe-run with --accept-terms once you have read the terms above.")
        return 2
    if code != 0:
        return code
    for source, infile, extra, outfile in IMPORTS:
        src = DATA / infile
        if not src.exists():
            print(f"[skip] {infile} not present (optional dataset)")
            continue
        cmd = [sys.executable, "scripts/import_external_prompts.py", "--source", source,
               "--input", str(src), "--output", str(DATA / outfile), *extra]
        if sh(cmd) != 0:
            print(f"[fail] importing {infile}")
            return 1
    if sh([sys.executable, "research/build_full_corpus.py", "--seed", "42"]) != 0:
        return 1
    corpus = json.loads(CORPUS.read_text(encoding="utf-8"))["prompts"]
    digest = hashlib.sha256("\n".join(p["text"] for p in corpus).encode()).hexdigest()
    by_source: dict[str, int] = {}
    for p in corpus:
        by_source[p["source"]["name"]] = by_source.get(p["source"]["name"], 0) + 1
    (DATA / "corpus_manifest.json").write_text(json.dumps(
        {"prompts": len(corpus), "by_source": by_source, "texts_sha256": digest,
         "built_at": datetime.now(timezone.utc).isoformat()}, indent=1), encoding="utf-8")
    print(f"\ncorpus: {len(corpus)} unique prompts, sha256 {digest[:16]}...")
    if args.skip_smoke:
        return 0
    print("\nSmoke test:")
    code = sh([sys.executable, "research/remote_gpu/run_all.py", "--smoke", "--grant", args.grant,
               "--prompts", args.prompts])
    print("\nReady: run  python research/remote_gpu/study.py run --budget-hours <hours>"
          if code == 0 else "\nSmoke test failed; fix the problem above before running.")
    return code


# -------------------------------------------------------------------- run
def judge(models: list[str], k: int, args: argparse.Namespace, arm: str = "main") -> None:
    sh([sys.executable, "research/remote_gpu/judge_all.py", "--judge-n", str(k), "--arm", arm,
        "--models", *models, "--corpus", args.prompts])


def run(args: argparse.Namespace) -> int:
    state = load_state()
    ns = make_args(args)
    run_all.preflight(ns)
    models = args.models
    state.setdefault("started_at", datetime.now(timezone.utc).isoformat())
    state["budget_hours"] = args.budget_hours
    state.setdefault("stages_done", [])
    state.setdefault("seconds_used", 0.0)
    state.setdefault("failed_models", [])

    total = run_all.corpus_size(args.prompts)
    if "plan" not in state:
        print("\n=== measuring speed (a few minutes per model) ===")
        rows = run_all.estimate(models, make_args(args, n=min(total, 700)))
        if not rows:
            print("No model could be timed; fix the errors above.")
            return 1
        sec = sum(r[1] for r in rows)
        try:
            # ~52% of the budget for the main arm; ~8% is reserved for the reasoning arm
            plan = plan_stages(sec, total, args.budget_hours, n_models=len(rows), gen_share=0.52)
        except ValueError as exc:
            print(exc)
            return 1
        usable = [r[0] for r in rows]
        state["plan"] = {"stages": plan.stages, "n_max": plan.n_max, "judge_k_max": plan.judge_k_max,
                         "models": usable, "sec_per_attack": {r[0]: round(r[1], 3) for r in rows},
                         "projected_generation_hours": round(plan.projected_generation_hours, 1)}
        state["failed_models"] = [m for m in models if m not in usable]
        save_state(state)
    plan_d = state["plan"]
    usable = plan_d["models"]
    print(f"\nPlan: stages {plan_d['stages']} prompts, judge sample up to {plan_d['judge_k_max']} prompts, "
          f"projected generation {plan_d['projected_generation_hours']} h of a {args.budget_hours} h budget.")
    if state["failed_models"]:
        print(f"Models that could not be used: {state['failed_models']} (reported at the end)")

    budget_s = args.budget_hours * 3600
    for i, n in enumerate(plan_d["stages"]):
        if n in state["stages_done"]:
            continue
        if state["seconds_used"] > 0.97 * budget_s:
            print("\nBudget reached; stopping before the next stage.")
            break
        print(f"\n=== stage {i + 1}/{len(plan_d['stages'])}: first {n} prompts, {len(usable)} models ===")
        t0 = time.time()
        stage_args = make_args(args, n=n)
        failed = [m for m in usable if not run_all.attack(m, stage_args)]
        ok_models = [m for m in usable if m not in failed]
        if ok_models:
            run_all.guard_all(ok_models)
            k = min(plan_d["judge_k_max"], 250 if i == 0 else plan_d["judge_k_max"], n)
            if i == 0 or i == len(plan_d["stages"]) - 1:
                judge(ok_models, k, args)
        run_all.package(usable)
        state["seconds_used"] += time.time() - t0
        if failed:
            state["failed_models"] = sorted(set(state["failed_models"]) | set(failed))
            print(f"Stage {n} incomplete for {failed}; run the same command again to resume.")
        else:
            state["stages_done"].append(n)
        save_state(state)
        print(f"stage done in {(time.time() - t0) / 3600:.1f} h; total used {state['seconds_used'] / 3600:.1f} h")
        if failed:
            return 1

    if not args.no_reasoning_arm and "reasoning" not in state.get("arms_done", []):
        think_models = [m for m in run_all.REASONING_ARM_MODELS if m in usable]
        if think_models and state["seconds_used"] <= 0.85 * budget_s:
            print(f"\n=== reasoning arm: {think_models}, thinking ON, first "
                  f"{run_all.REASONING_ARM_PROMPTS} prompts ===")
            t0 = time.time()
            think_args = make_args(args, n=run_all.REASONING_ARM_PROMPTS, arm="think")
            tfailed = [m for m in think_models if not run_all.attack(m, think_args)]
            tok = [m for m in think_models if m not in tfailed]
            if tok:
                run_all.guard_all(tok, "adv_think")
                judge(tok, run_all.REASONING_ARM_PROMPTS, args, arm="think")
            run_all.package(usable)
            state["seconds_used"] += time.time() - t0
            if tfailed:
                state["failed_models"] = sorted(set(state["failed_models"]) | set(tfailed))
                print(f"Reasoning arm incomplete for {tfailed}; run the same command again to resume.")
            else:
                state.setdefault("arms_done", []).append("reasoning")
            save_state(state)
        elif think_models:
            print("\nSkipping the reasoning arm: not enough budget left.")

    if not args.no_control_arm and "control" not in state.get("arms_done", []):
        ctl_models = [m for m in run_all.CONTROL_MODELS if m in usable]
        if ctl_models and run_all.CONTROL_SOURCE.exists() and state["seconds_used"] <= 0.92 * budget_s:
            print(f"\n=== control arm: benign XSTest prompts, {ctl_models}, "
                  f"first {run_all.CONTROL_PROMPTS} prompts ===")
            t0 = time.time()
            ctl_corpus = str(run_all.build_control_corpus())
            ctl_args = make_args(args, n=run_all.CONTROL_PROMPTS, arm="control")
            ctl_args.prompts = ctl_corpus
            cfailed = [m for m in ctl_models if not run_all.attack(m, ctl_args)]
            cok = [m for m in ctl_models if m not in cfailed]
            if cok:
                run_all.guard_all(cok, "adv_control")
                judge(cok, run_all.CONTROL_PROMPTS, args, arm="control")
            run_all.package(usable)
            state["seconds_used"] += time.time() - t0
            if cfailed:
                state["failed_models"] = sorted(set(state["failed_models"]) | set(cfailed))
                print(f"Control arm incomplete for {cfailed}; run the same command again to resume.")
            else:
                state.setdefault("arms_done", []).append("control")
            save_state(state)
        elif ctl_models and not run_all.CONTROL_SOURCE.exists():
            print("\nSkipping the control arm: XSTest safe prompts not imported.")

    validate = sorted((ROOT / "validate_in").glob("*.json")) if (ROOT / "validate_in").exists() else []
    if validate and not state.get("validated"):
        print("\n=== validating the local judges on the supplied older answers ===")
        sh([sys.executable, "research/remote_gpu/judge_all.py", "--files", *map(str, validate)])
        state["validated"] = True
        save_state(state)

    print("\n" + "=" * 60)
    print("Finished. Send these files to the researcher PRIVATELY (not via GitHub):")
    for name in ("results_for_researcher.zip", "judges_for_researcher.zip",
                 "judges_think_for_researcher.zip", "judges_control_for_researcher.zip"):
        if (run_all.OUT_DIR / name).exists():
            print("  outputs/" + name)
    if state["failed_models"]:
        print(f"Models not completed: {state['failed_models']}")
    return 0


def show_status(args: argparse.Namespace) -> int:
    state = load_state()
    if not state:
        print("No study started yet.")
        return 0
    plan = state.get("plan", {})
    print(f"budget {state.get('budget_hours')} h, used {state.get('seconds_used', 0) / 3600:.1f} h")
    print(f"stages planned {plan.get('stages')}, done {state.get('stages_done')}")
    if state.get("failed_models"):
        print(f"models with problems: {state['failed_models']}")
    run_all.status(plan.get("models", args.models), make_args(args, n=(state.get("stages_done") or [0])[-1]))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["prepare", "run", "status"])
    ap.add_argument("--accept-terms", action="store_true",
                    help="prepare: confirm you read the datasets' terms (the human operator decides)")
    ap.add_argument("--budget-hours", type=float, default=75.0)
    ap.add_argument("--models", nargs="+", default=run_all.DEFAULT_MODELS)
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--prompts", default=str(CORPUS))
    ap.add_argument("--grant", default=str(ROOT / "research" / "grants" / "journal_grant_v4_signed.json"))
    ap.add_argument("--only", nargs="+", help="prepare: fetch only these dataset keys (see fetch_benchmarks.py --list)")
    ap.add_argument("--no-reasoning-arm", action="store_true",
                    help="run: skip the reasoning arm (thinking ON, a few models)")
    ap.add_argument("--no-control-arm", action="store_true",
                    help="run: skip the control arm (benign XSTest prompts)")
    ap.add_argument("--skip-smoke", action="store_true")
    args = ap.parse_args()
    return {"prepare": prepare, "run": run, "status": show_status}[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
