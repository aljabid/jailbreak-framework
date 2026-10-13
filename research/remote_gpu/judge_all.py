#!/usr/bin/env python3
"""Score the generated answers with LLM judges running locally on this machine's Ollama.

The free Groq quota cannot score tens of thousands of answers, so the two LLM judges are
run locally. They use the same rubrics as before (judge_llm_v2.py and judge_strongreject.py);
only the hosting changes, and every verdict records its judge model and host.

Because the corpus is ordered so that any prefix is representative, the judges score the
answers for the FIRST K base prompts (all models, all strategies), where K is chosen to fit
the time budget (--judge-n). Llama Guard has already scored everything (run_all.py).

  python research/remote_gpu/judge_all.py --judge-n 250
  python research/remote_gpu/judge_all.py --files validate_in/adv_local_qwen2_5_0_5b_judged.json
                                                       # validation mode: rejudge older answers
  python research/remote_gpu/judge_all.py --status

Resumable: run the same command again after any stop. Output: outputs/judges_for_researcher.zip
(verdict files only; send it privately like the generation results).
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "outputs"
VERDICTS = ROOT / "research" / "judge_reliability" / "out"
OLLAMA = os.environ.get("OLLAMA_HOST_URL", "http://127.0.0.1:11434")
DEFAULT_MODELS = [
    "llama3.1:8b", "qwen2.5:7b", "mistral:7b", "phi4",
    "qwen2.5:14b", "gemma3:27b", "mistral-small:24b", "qwen2.5:32b",
]
LLM_MODEL = "gpt-oss:20b"   # rubric judge v2 (not one of the targets, so no self-judging)
SR_MODEL = "gemma2:27b"     # StrongREJECT-style judge (also not a target)


def safe_name(model: str) -> str:
    return model.replace(":", "_").replace(".", "_").replace("/", "_")


def installed() -> set[str]:
    try:
        with urllib.request.urlopen(OLLAMA + "/api/tags", timeout=10) as r:
            names = {m["name"] for m in json.load(r).get("models", [])}
    except Exception:
        return set()
    return names | {n.removesuffix(":latest") for n in names}


def run(cmd: list[str], env: dict | None = None) -> int:
    print("  $", " ".join(cmd), flush=True)
    return subprocess.run(cmd, cwd=ROOT, env=env).returncode


def load_records(path: Path) -> list[dict]:
    d = json.loads(path.read_text(encoding="utf-8"))
    return d if isinstance(d, list) else d.get("results", [])


def first_prompt_ids(corpus: Path, k: int) -> set[str]:
    d = json.loads(corpus.read_text(encoding="utf-8"))
    prompts = d if isinstance(d, list) else d.get("prompts", [])
    return {p["id"] for p in prompts[:k]}


def build_subsets(models: list[str], corpus: Path, k: int) -> list[Path]:
    ids = first_prompt_ids(corpus, k)
    files = []
    for m in models:
        src = OUT_DIR / f"adv_gpu_{safe_name(m)}.json"
        if not src.exists():
            print(f"[skip] no generation output yet for {m}")
            continue
        recs = [r for r in load_records(src) if r.get("base_prompt_id") in ids]
        dst = OUT_DIR / f"judge_subset_adv_gpu_{safe_name(m)}.json"
        dst.write_text(json.dumps(recs), encoding="utf-8")
        print(f"  {m}: {len(recs)} answers in the first {k} prompts")
        files.append(dst)
    return files


def validation_copies(paths: list[str]) -> list[Path]:
    files = []
    for p in paths:
        src = Path(p)
        dst = OUT_DIR / f"validate_{src.stem.replace('_judged', '')}.json"
        shutil.copyfile(src, dst)
        files.append(dst)
    return files


def done_count(path: Path, suffix: str) -> int:
    v = VERDICTS / f"{path.stem}_{suffix}.json"
    if not v.exists():
        return 0
    try:
        data = json.loads(v.read_text(encoding="utf-8"))
        return sum(1 for x in data.values() if x.get("verdict", x.get("status")) not in (None, "UNCLEAR", "error"))
    except Exception:
        return 0


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--models", nargs="+", default=DEFAULT_MODELS)
    ap.add_argument("--judge-n", type=int, default=250, help="judge answers for the first K prompts")
    ap.add_argument("--corpus", default=str(ROOT / "research" / "data_journal" / "journal_full_corpus.json"))
    ap.add_argument("--files", nargs="+", help="validation mode: response files to rejudge instead")
    ap.add_argument("--llm-model", default=LLM_MODEL)
    ap.add_argument("--sr-model", default=SR_MODEL)
    ap.add_argument("--status", action="store_true")
    args = ap.parse_args()

    OUT_DIR.mkdir(exist_ok=True)
    files = validation_copies(args.files) if args.files else build_subsets(args.models, Path(args.corpus), args.judge_n)
    if args.status:
        for f in files:
            print(f"{f.name}: llmv2 {done_count(f, 'llmv2')}  strongreject {done_count(f, 'strongreject')}")
        return
    if not files:
        sys.exit("nothing to judge: run run_all.py first (or pass --files)")
    if not shutil.which("ollama"):
        sys.exit("ollama is not installed or not on PATH")
    have = installed()
    for model in (args.llm_model, args.sr_model):
        if model not in have and run(["ollama", "pull", model]) != 0:
            sys.exit(f"could not pull judge model {model}; check the name on ollama.com/library")

    env = dict(os.environ, JUDGE_BASE_URL=OLLAMA + "/v1", JUDGE_SLEEP="0",
               LLMV2_MODEL=args.llm_model, SR_MODEL=args.sr_model)
    paths = [str(f) for f in files]
    print(f"\n=== rubric judge v2 ({args.llm_model}) ===", flush=True)
    run([sys.executable, "research/judge_reliability/judge_llm_v2.py", *paths], env)
    print(f"\n=== StrongREJECT-style judge ({args.sr_model}) ===", flush=True)
    run([sys.executable, "research/judge_reliability/judge_strongreject.py", *paths], env)

    zpath = OUT_DIR / "judges_for_researcher.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for f in files:
            for suffix in ("llmv2", "strongreject"):
                v = VERDICTS / f"{f.stem}_{suffix}.json"
                if v.exists():
                    z.write(v, "judge_out/" + v.name)
    print("\n" + "=" * 60)
    for f in files:
        print(f"{f.name}: llmv2 {done_count(f, 'llmv2')}  strongreject {done_count(f, 'strongreject')}")
    print(f"\nSend this file to the researcher (privately, NOT via GitHub):\n  {zpath}")


if __name__ == "__main__":
    main()
