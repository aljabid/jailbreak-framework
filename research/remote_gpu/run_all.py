#!/usr/bin/env python3
"""Run the journal-study attacks against every model on this machine's Ollama.

Works on Linux and Windows. For each model it pulls the model, runs the
framework (`main.py run`) over the first N base prompts of the corpus, and writes
outputs/adv_gpu_<model>.json. It is resumable: a finished model is skipped, and an
unfinished or smaller run continues from the response cache (--cache), so the
same command can simply be run again after any stop, or with a larger --n.

The corpus is ordered so that every prefix is a representative sample; the study
therefore proceeds in stages (for example --n 300, then 700, then all) and is
valid at whatever stage the GPU budget ends.

  python research/remote_gpu/run_all.py --smoke            # tiny check of the setup
  python research/remote_gpu/run_all.py --estimate --n 700 --hours 40
                                                           # measure speed, project hours
  python research/remote_gpu/run_all.py --n 300            # stage 1
  python research/remote_gpu/run_all.py --n 700            # stage 2 (reuses stage 1)
  python research/remote_gpu/run_all.py                    # everything
  python research/remote_gpu/run_all.py --status           # progress only

When all models are done it scores every output with Llama Guard 3 8B and zips
outputs + verdicts into outputs/results_for_researcher.zip.

Prerequisites: .env contains JBF_AUTHORIZATION_SIGNING_KEY; the corpus and the signed
grant are in place (see AUTHORS_RUN.md). Nothing here uploads data.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "outputs"
GUARD_OUT = ROOT / "research" / "judge_reliability" / "out"

DEFAULT_MODELS = [
    "llama3.1:8b", "qwen2.5:7b", "mistral:7b", "phi4",
    "qwen2.5:14b", "gemma3:27b", "mistral-small:24b", "qwen2.5:32b",
]
OLLAMA = os.environ.get("OLLAMA_HOST_URL", "http://127.0.0.1:11434")
TARGET_ID = "journal-study"
GUARD_MODEL = "llama-guard3:8b"
N_STRATEGIES = 6
ESTIMATE_PROMPTS = 5  # x 6 strategies = 30 attacks per model


def safe_name(model: str) -> str:
    return model.replace(":", "_").replace(".", "_").replace("/", "_")


def out_path(model: str, kind: str = "adv_gpu") -> Path:
    return OUT_DIR / f"{kind}_{safe_name(model)}.json"


def run(cmd: list[str], env: dict | None = None) -> int:
    print("  $", " ".join(cmd), flush=True)
    return subprocess.run(cmd, cwd=ROOT, env=env).returncode


def ollama_up() -> bool:
    try:
        with urllib.request.urlopen(OLLAMA + "/api/version", timeout=5) as r:
            return r.status == 200
    except Exception:
        return False


def installed_models() -> set[str]:
    try:
        with urllib.request.urlopen(OLLAMA + "/api/tags", timeout=10) as r:
            names = {m["name"] for m in json.load(r).get("models", [])}
    except Exception:
        return set()
    return names | {n.removesuffix(":latest") for n in names}


def warm_up(model: str) -> None:
    """Load the model into VRAM so timing and the first request are not skewed."""
    body = json.dumps({"model": model, "prompt": "hi", "stream": False,
                       "options": {"num_predict": 1}}).encode()
    req = urllib.request.Request(OLLAMA + "/api/generate", body, {"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=900).read()
    except Exception as exc:
        print(f"  (warm-up call failed: {type(exc).__name__}; continuing)")


def gpu_info() -> str:
    exe = shutil.which("nvidia-smi")
    if not exe:
        return "no nvidia-smi found (CPU only - this will be very slow)"
    out = subprocess.run([exe, "--query-gpu=name,memory.total", "--format=csv,noheader"],
                         capture_output=True, text=True)
    return out.stdout.strip() or "nvidia-smi returned nothing"


def corpus_size(path: str) -> int:
    try:
        d = json.loads(Path(path).read_text(encoding="utf-8"))
        return len(d if isinstance(d, list) else d.get("prompts", []))
    except Exception:
        return 0


def preflight(args: argparse.Namespace) -> None:
    problems = []
    if not (ROOT / "main.py").exists():
        problems.append(f"main.py not found under {ROOT}")
    if not Path(args.prompts).exists():
        problems.append(f"base-prompt file missing: {args.prompts}")
    if not Path(args.grant).exists():
        problems.append(f"signed grant missing: {args.grant}")
    key_set = bool(os.environ.get("JBF_AUTHORIZATION_SIGNING_KEY"))
    env_file = ROOT / ".env"
    if not key_set and not (env_file.exists() and "JBF_AUTHORIZATION_SIGNING_KEY=" in env_file.read_text(encoding="utf-8")):
        problems.append("JBF_AUTHORIZATION_SIGNING_KEY not set (put it in .env)")
    if not shutil.which("ollama"):
        problems.append("ollama is not installed or not on PATH")
    elif not ollama_up():
        problems.append(f"Ollama is not answering at {OLLAMA} (start it: `ollama serve`)")
    print(f"GPU: {gpu_info()}")
    if problems:
        print("\nCannot start:")
        for p in problems:
            print("  -", p)
        sys.exit(1)


def count_records(path: Path) -> int:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return len(data if isinstance(data, list) else data.get("results", []))
    except Exception:
        return 0


def expected_records(args: argparse.Namespace) -> int:
    total = corpus_size(args.prompts)
    n = min(args.n, total) if args.n else total
    return n * N_STRATEGIES * args.variations


def ensure_model(model: str) -> bool:
    if model in installed_models():
        print(f"  {model} is already installed; skipping pull")
        return True
    if run(["ollama", "pull", model]) != 0:
        print(f"[fail] could not pull {model}; check the name on ollama.com/library")
        return False
    return True


def main_cmd(model: str, args: argparse.Namespace, out: Path, n: int | None,
             strategy: str | None) -> tuple[list[str], dict]:
    env = dict(os.environ)
    env.update({
        "JBF_ATTACK_BASE_PROMPTS_FILE": str(Path(args.prompts).resolve()),
        "JBF_MODEL_TEMPERATURE": "0",
        "JBF_MODEL_MAX_TOKENS": "320",
        "JBF_MODEL_TIMEOUT": "600",
        "JBF_MODEL_RATE_LIMIT_DELAY": "0",
    })
    cmd = [sys.executable, "main.py", "run", "--provider", "local", "--local-mode", "ollama",
           "--ollama-base-url", OLLAMA, "--model-name", model, "--seed", "42",
           "--concurrency", str(args.concurrency), "--cache", "--no-report", "--eval-mode", "keyword",
           "--target-id", TARGET_ID, "--authorization-file", str(Path(args.grant).resolve()),
           "--variations", str(args.variations), "-o", str(out)]
    if n:
        cmd += ["-n", str(n)]
    if strategy:
        cmd += ["-s", strategy]
    return cmd, env


def attack(model: str, args: argparse.Namespace) -> bool:
    out = out_path(model, "smoke" if args.smoke else "adv_gpu")
    want = expected_records(args)
    have = count_records(out) if out.exists() else 0
    if not args.smoke and want and have >= int(want * 0.99):
        print(f"[skip] {model}: already complete for this stage ({have}/{want} records)")
        return True
    print(f"\n=== {model} ===", flush=True)
    if not ensure_model(model):
        return False
    # the framework APPENDS to an existing output file, so a smaller or interrupted earlier
    # file must go first; finished answers are replayed from the response cache (--cache)
    out.unlink(missing_ok=True)
    cmd, env = main_cmd(model, args, out, 3 if args.smoke else args.n or None,
                        "roleplay" if args.smoke else None)
    start = time.time()
    code = run(cmd, env)
    got = count_records(out)
    if code != 0 or got == 0:
        print(f"[fail] {model} exited with code {code}; run this script again to resume")
        return False
    print(f"[done] {model}: {got} records in {(time.time() - start) / 60:.1f} min")
    return True


def estimate(models: list[str], args: argparse.Namespace) -> None:
    """Time a small real run per model and project the hours for the requested N."""
    total_prompts = corpus_size(args.prompts)
    n = min(args.n, total_prompts) if args.n else total_prompts
    attacks = n * N_STRATEGIES * args.variations
    print(f"Projection for N={n} prompts x {N_STRATEGIES} strategies x {args.variations} variation(s)"
          f" = {attacks} attacks per model")
    rows = []
    for m in models:
        if not ensure_model(m):
            continue
        warm_up(m)
        out = out_path(m, "estimate")
        out.unlink(missing_ok=True)
        cmd, env = main_cmd(m, args, out, ESTIMATE_PROMPTS, None)
        start = time.time()
        code = run(cmd, env)
        secs = time.time() - start
        got = count_records(out)
        if code != 0 or got == 0:
            print(f"  [estimate failed for {m}]")
            continue
        per = secs / got
        rows.append((m, per, per * attacks / 3600))
        note = "  (answers were cached; speed is understated)" if per < 0.05 else ""
        print(f"  {m}: {per:.2f} s/attack -> {per * attacks / 3600:.1f} h{note}", flush=True)
    if not rows:
        return
    total = sum(r[2] for r in rows)
    print(f"\n{'model':<22}{'s/attack':>10}{'hours':>9}")
    for m, per, h in rows:
        print(f"{m:<22}{per:>10.2f}{h:>9.1f}")
    print(f"{'TOTAL':<22}{'':>10}{total:>9.1f}")
    if args.hours:
        fits = args.hours / total * n if total else 0
        verdict = "fits" if total <= args.hours else f"does NOT fit; about N={int(fits)} would"
        print(f"\nBudget {args.hours} h for generation: N={n} {verdict}.")


def guard_all(models: list[str]) -> None:
    files = [str(out_path(m)) for m in models if out_path(m).exists()]
    if not files:
        return
    print(f"\n=== Llama Guard 3 8B over {len(files)} output files ===", flush=True)
    if GUARD_MODEL not in installed_models() and run(["ollama", "pull", GUARD_MODEL]) != 0:
        print("[warn] could not pull the guard model; skipping Llama Guard")
        return
    env = dict(os.environ, JBF_GUARD_MODEL=GUARD_MODEL)
    run([sys.executable, "research/judge_reliability/judge_llamaguard.py", *files], env)


def package(models: list[str]) -> Path:
    zpath = OUT_DIR / "results_for_researcher.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for m in models:
            p = out_path(m)
            if p.exists():
                z.write(p, p.name)
            g = GUARD_OUT / f"{p.stem}_lg3_8b.json"
            if g.exists():
                z.write(g, "judge_out/" + g.name)
    return zpath


def status(models: list[str], args: argparse.Namespace) -> None:
    want = expected_records(args)
    print(f"stage target: {want} records per model "
          f"(N={args.n or 'all'}, variations={args.variations})")
    print(f"{'model':<22} status")
    for m in models:
        p = out_path(m)
        n = count_records(p) if p.exists() else 0
        state = "DONE" if n and want and n >= int(want * 0.99) else ("partial" if n else "not started")
        print(f"{m:<22} {state}  {n} records")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--models", nargs="+", default=DEFAULT_MODELS)
    ap.add_argument("--n", type=int, default=0, help="use the first N prompts of the corpus (default: all)")
    ap.add_argument("--variations", type=int, default=1)
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--prompts", default=str(ROOT / "research" / "data_journal" / "journal_full_corpus.json"))
    ap.add_argument("--grant", default=str(ROOT / "research" / "grants" / "journal_grant_v3_signed.json"))
    ap.add_argument("--smoke", action="store_true", help="tiny test run: 3 prompts, 1 strategy, first model only")
    ap.add_argument("--estimate", action="store_true", help="time a small run per model and project hours")
    ap.add_argument("--hours", type=float, default=0, help="with --estimate: the generation budget in hours")
    ap.add_argument("--status", action="store_true", help="show progress and exit")
    ap.add_argument("--no-guard", action="store_true", help="skip the Llama Guard pass")
    args = ap.parse_args()

    if args.status:
        status(args.models, args)
        return
    models = args.models[:1] if args.smoke else args.models
    if args.smoke:
        args.variations = 1
    OUT_DIR.mkdir(exist_ok=True)
    preflight(args)

    if args.estimate:
        estimate(models, args)
        return
    failed = [m for m in models if not attack(m, args)]
    if args.smoke:
        print("\nSmoke test", "FAILED" if failed else "passed", "- see AUTHORS_RUN.md if it failed.")
        sys.exit(1 if failed else 0)
    if not args.no_guard:
        guard_all(models)
    zpath = package(models)
    print("\n" + "=" * 60)
    status(models, args)
    if failed:
        print(f"\nNot finished: {failed}. Run the same command again to resume.")
    print(f"\nSend this file to the researcher (privately, NOT via GitHub):\n  {zpath}")


if __name__ == "__main__":
    main()
