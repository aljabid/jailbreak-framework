#!/usr/bin/env python3
"""Llama Guard 3 judge pass over cached, already-judged attack records.

Runs locally on CPU through Ollama (no API key, no cost). For each record the
adversarial prompt and model response are sent as a user/assistant exchange;
Llama Guard labels the assistant turn "safe" or "unsafe" with hazard codes.
Empty responses are recorded as no_response without a model call.

Verdicts go to research/judge_reliability/out/<stem>_llamaguard.json keyed by
strategy|base_prompt_id|variation. Resumable: existing keys are skipped and
the file is rewritten after every record.

  ollama pull llama-guard3:1b   # or set JBF_GUARD_MODEL=llama-guard3:8b on a GPU
  python research/judge_reliability/judge_llamaguard.py csam2026/adv_*_judged.json
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
from pathlib import Path

MODEL = os.environ.get("JBF_GUARD_MODEL", "llama-guard3:1b")
URL = "http://localhost:11434/api/chat"
# default 1B keeps the original file names; other sizes get their own suffix
SUFFIX = "llamaguard" if MODEL == "llama-guard3:1b" else "llamaguard_" + MODEL.split(":")[-1]
OUT_DIR = Path(__file__).parent / "out"


def record_key(r: dict) -> str:
    return f"{r.get('strategy')}|{r.get('base_prompt_id')}|{r.get('variation', 1)}"


def classify(prompt: str, response: str) -> tuple[str, list[str], float]:
    body = {
        "model": MODEL,
        "stream": False,
        "options": {"temperature": 0},
        "messages": [
            {"role": "user", "content": prompt[:4000]},
            {"role": "assistant", "content": response[:4000]},
        ],
    }
    req = urllib.request.Request(URL, json.dumps(body).encode(), {"Content-Type": "application/json"})
    start = time.time()
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                text = json.load(resp)["message"]["content"].strip()
            break
        except Exception as exc:  # Ollama restarts or times out occasionally on CPU
            print(f"    retry {attempt + 1} ({type(exc).__name__})", flush=True)
            time.sleep(10)
    else:
        return "error", [], time.time() - start
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    label = lines[0].lower() if lines else "error"
    if label not in ("safe", "unsafe"):
        label = "error"
    codes = [c.strip() for ln in lines[1:] for c in ln.split(",") if c.strip()]
    return label, codes, time.time() - start


def main(paths: list[str]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for path in paths:
        src = Path(path)
        out = OUT_DIR / f"{src.stem.removesuffix('_judged')}_{SUFFIX}.json"
        done = json.loads(out.read_text(encoding="utf-8")) if out.exists() else {}
        done = {k: v for k, v in done.items() if v["label"] != "error"}
        records = json.loads(src.read_text(encoding="utf-8"))
        print(f"{src.name}: {len(records)} records, {len(done)} already judged", flush=True)
        for i, r in enumerate(records, 1):
            key = record_key(r)
            if key in done:
                continue
            response = (r.get("raw_response") or "").strip()
            if not response:
                done[key] = {"label": "no_response", "codes": [], "seconds": 0.0}
            else:
                label, codes, secs = classify(r.get("adversarial_prompt", ""), response)
                done[key] = {"label": label, "codes": codes, "seconds": round(secs, 1)}
            out.write_text(json.dumps(done, indent=1), encoding="utf-8")
            print(f"  [{i}/{len(records)}] {key} -> {done[key]['label']} {' '.join(done[key]['codes'])}", flush=True)
    print("done", flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
