#!/usr/bin/env python3
"""Run the journal-study attacks against every model on this machine's Ollama.

Works on Linux and Windows. For each model it pulls the model, runs the
framework (`main.py run`) over the base-prompt corpus with --variations, and
writes outputs/adv_gpu_<model>.json. It is resumable: finished models are
skipped, and an interrupted model continues from its response cache
(--cache), so just run the same command again after any stop.

When all models are done it also scores every output with Llama Guard 3 8B
(needs a GPU) and zips outputs + verdicts into outputs/results_for_researcher.zip.

  python research/remote_gpu/run_all.py --smoke       # 1 tiny run, checks the setup
  python research/remote_gpu/run_all.py               # the full study
  python research/remote_gpu/run_all.py --models qwen2.5:7b mistral:7b
  python research/remote_gpu/run_all.py --status      # progress only

Prerequisites: .env contains JBF_AUTHORIZATION_SIGNING_KEY; the base-prompt file
and the signed grant are in place (see FRIEND_RUN.md). Nothing here uploads data.
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
    "qwen2.5:14b", "gemma2:27b", "mistral-small:24b", "qwen2.5:32b",
]
OLLAMA = os.environ.get("OLLAMA_HOST_URL", "http://127.0.0.1:11434")
TARGET_ID = "journal-study"
GUARD_MODEL = "llama-guard3:8b"


def safe_name(model: str) -> str:
    return model.replace(":", "_").replace(".", "_").replace("/", "_")


def out_path(model: str, smoke: bool) -> Path:
    return OUT_DIR / f"{'smoke' if smoke else 'adv_gpu'}_{safe_name(model)}.json"


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


def gpu_info() -> str:
    exe = shutil.which("nvidia-smi")
    if not exe:
        return "no nvidia-smi found (CPU only - this will be very slow)"
    out = subprocess.run([exe, "--query-gpu=name,memory.total", "--format=csv,noheader"],
                         capture_output=True, text=True)
    return out.stdout.strip() or "nvidia-smi returned nothing"


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


def attack(model: str, args: argparse.Namespace) -> bool:
    out = out_path(model, args.smoke)
    if out.exists() and not args.smoke and count_records(out) > 0:
        print(f"[skip] {model}: already done ({count_records(out)} records)")
        return True
    print(f"\n=== {model} ===", flush=True)
    if model in installed_models():
        print(f"  {model} is already installed; skipping pull")
    elif run(["ollama", "pull", model]) != 0:
        print(f"[fail] could not pull {model}; check the name on ollama.com/library")
        return False
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
    if args.smoke:
        cmd += ["-n", "3", "-s", "roleplay"]
    start = time.time()
    code = run(cmd, env)
    if code != 0 or count_records(out) == 0:
        print(f"[fail] {model} exited with code {code}; run this script again to resume")
        return False
    print(f"[done] {model}: {count_records(out)} records in {(time.time() - start) / 60:.1f} min")
    return True


def guard_all(models: list[str]) -> None:
    files = [str(out_path(m, False)) for m in models if out_path(m, False).exists()]
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
            p = out_path(m, False)
            if p.exists():
                z.write(p, p.name)
            g = GUARD_OUT / f"{p.stem}_lg3_8b.json"
            if g.exists():
                z.write(g, "judge_out/" + g.name)
    return zpath


def status(models: list[str]) -> None:
    print(f"{'model':<22} status")
    for m in models:
        p = out_path(m, False)
        n = count_records(p) if p.exists() else 0
        print(f"{m:<22} {'DONE  ' + str(n) + ' records' if n else 'not done'}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--models", nargs="+", default=DEFAULT_MODELS)
    ap.add_argument("--variations", type=int, default=3)
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--prompts", default=str(ROOT / "research" / "data_journal" / "journal_base_corpus.json"))
    ap.add_argument("--grant", default=str(ROOT / "research" / "grants" / "journal_grant_v2_signed.json"))
    ap.add_argument("--smoke", action="store_true", help="tiny test run: 3 prompts, 1 strategy, first model only")
    ap.add_argument("--status", action="store_true", help="show progress and exit")
    ap.add_argument("--no-guard", action="store_true", help="skip the Llama Guard pass")
    args = ap.parse_args()

    if args.status:
        status(args.models)
        return
    models = args.models[:1] if args.smoke else args.models
    if args.smoke:
        args.variations = 1
    OUT_DIR.mkdir(exist_ok=True)
    preflight(args)

    failed = [m for m in models if not attack(m, args)]
    if args.smoke:
        print("\nSmoke test", "FAILED" if failed else "passed", "- see FRIEND_RUN.md if it failed.")
        sys.exit(1 if failed else 0)
    if not args.no_guard:
        guard_all(models)
    zpath = package(models)
    print("\n" + "=" * 60)
    status(models)
    if failed:
        print(f"\nNot finished: {failed}. Run the same command again to resume.")
    print(f"\nSend this file to the researcher (privately, NOT via GitHub):\n  {zpath}")


if __name__ == "__main__":
    main()
