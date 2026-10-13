# Task brief: run the model study on the lab GPU machine

Read this whole file before doing anything. It is written so that a person or a
script runner can carry out the task end to end. Where it says "ask the human",
stop and ask the person who gave you this task.

## 1. Context (why this exists)

This repository is an authorisation-gated framework for measuring how reliable
automated "jailbreak judges" are. The study sends prompts from public research
benchmarks (AdvBench, HarmBench, StrongREJECT, JailbreakBench, SORRY-Bench, XSTest)
to open-weight models and records the answers. Judges then score those answers and the
scores are compared with human labels. The master plan is `research/STUDY_PLAN.md`.

* The study is approved by the supervisor and runs on lab hardware with permission.
* Every request is checked against a signed authorisation grant that lists the allowed
  target, models and strategies. That check is part of the method; never bypass it.
* The prompts are intentionally adversarial, and some model answers will contain
  harmful text. This is expected, authorised measurement work. You do **not** need to read
  the answers.

## 2. Your task and budget

Run the scripts in this folder on this machine (NVIDIA RTX 5090, 32 GB). The total budget
is **70 to 80 GPU-hours**. Plan it as:

| Part | Script | Budget |
|---|---|---|
| A. Generate answers from 8 models | `run_all.py` | about 45 h |
| B. Llama Guard scoring of everything | `run_all.py` (automatic) | about 6 h |
| C. Local LLM judges on a sample | `judge_all.py` | about 18 h |
| D. Validate the local judges (optional but recommended) | `judge_all.py --files` | under 1 h |
| Buffer | | about 8 h |

The prompt corpus is ordered so that any prefix is a representative sample, so the work is
done in **stages** and is valid wherever the budget ends. Never skip ahead: finish a stage
(all models) before starting the next.

You are done when the human has the zip files named in section 7 and the final report.

## 3. Hard rules

* **Do not read, print, open, summarise, or paste the contents of any file in `outputs/`,
  `research/data_journal/`, `validate_in/` or `research/judge_reliability/out/*.json`.** To
  check progress use only `--status`, or count records without printing text, e.g.
  `uv run python -c "import json;print(len(json.load(open('outputs/FILE.json',encoding='utf-8'))))"`.
  Do not echo model answers into the conversation or logs.
* **Never print, log, or commit the signing key or the `.env` file.** Ask the human to create
  `.env` themselves (section 4, step 3) so the key never passes through you.
* **Never commit or push anything** from `outputs/`, `research/data_journal/` or `.env`. Do not
  run `git add -A`. You normally have no reason to commit anything at all.
* **Do not change** prompts, models, the model list, seed, temperature, token limit, variations
  count, strategies, judge prompts, or any file under `core/`, `strategies/`, `policy/`,
  `models/`, `main.py`. The study depends on these being fixed.
* **Do not work around the authorisation check.** If you see `Authorization signature is
  invalid`, `model is outside scope`, or `authorization is not active`, stop and ask the human.
  Never edit, re-sign, or regenerate a grant or key, and never disable the check.
* Do not expose Ollama to the network (keep it on `127.0.0.1`). Do not install anything beyond
  what section 4 lists. Do not run other models or other scripts.
* Ignore `RUNBOOK.md` and `setup_gpu_box.sh` in this folder. They describe a different
  plan (remote SSH operation) that is not being used.

## 4. Setup (once)

1. Check prerequisites: `git`, Python 3.10+, `uv` (https://docs.astral.sh/uv/), Ollama
   (https://ollama.com), and a working `nvidia-smi` (driver 570 or newer for the RTX 5090).
   Install only what is missing.
2. `git clone https://github.com/aljabid/jailbreak-framework.git`, `cd jailbreak-framework`,
   then `uv sync --locked`.
3. **Ask the human** to create a file named `.env` in the repository root containing exactly
   one line, `JBF_AUTHORIZATION_SIGNING_KEY=<key>`, using the key the researcher sent them
   privately. Wait until they confirm. Do not ask them to paste the key to you.
4. **Ask the human** to confirm these files are in place (they come from the researcher):
   `research/grants/journal_grant_v3_signed.json` and
   `research/data_journal/journal_full_corpus.json`. (The grant may already be in the
   repository after `git pull`; the corpus is never in the repository.) For part D also
   `validate_in/` with the response files the researcher sends.
5. Start Ollama with parallel requests enabled and storage on a big disk. Models need about
   130 GB (8 targets plus 3 judge models). Set `OLLAMA_NUM_PARALLEL=4` and, if the default
   drive is small, `OLLAMA_MODELS` to a folder with 150 GB free, then start Ollama.

## 5. Run

1. **Smoke test (2 minutes).** `uv run python research/remote_gpu/run_all.py --smoke`.
   It must finish with `Smoke test passed`. If not, go to section 6.
2. **Calibrate the budget (about 15 minutes).** Run
   `uv run python research/remote_gpu/run_all.py --estimate --n 1088 --hours 45`.
   It times a small real run per model and prints projected hours. Send the printed table to
   the human. If the projection for all prompts exceeds 45 h, the human will tell you which N
   to use; use that N below instead of the values written here.
3. **Stage 1.** Generate: `... run_all.py --n 300`. Then judge:
   `... judge_all.py --judge-n 250`. Both are resumable.
4. **Stage 2.** Only after stage 1 is complete and reported: `... run_all.py --n 700`
   (reuses stage 1 answers), then Llama Guard runs again automatically for the new ones.
5. **Stage 3.** Only if budget remains and the human agrees: `... run_all.py` (all prompts).
6. **Part D (optional).** `... judge_all.py --files validate_in/*.json`.
7. Run long jobs as **background processes** that survive your session (tmux/screen on Linux,
   `Start-Process` on Windows), logging to a file. Do not hold a foreground command open for hours.
   Every 30 to 60 minutes run `... run_all.py --status` (and `judge_all.py --status`) and read
   only the last few lines of the log. Keep the machine awake and avoid other heavy GPU jobs.
8. All scripts are resumable: if anything stops (crash, reboot, power cut), run the same
   command again; finished work is skipped or replayed from cache.

## 6. When something goes wrong

| Symptom | Action |
|---|---|
| `Cannot start:` followed by a list | fix exactly what it lists (missing file, Ollama not running, key not set) |
| `could not pull <model>` | model name may have changed on ollama.com/library; report the name to the human, do not substitute another model |
| `Authorization signature is invalid` | stop; ask the human to re-check the key in `.env` (no spaces, 64 characters) and that the grant file is the latest |
| `model is outside scope` or `not active` | stop; the grant file is wrong or old; ask the human to get the latest from the researcher |
| out of memory / very slow | check `nvidia-smi`; another process may be using the GPU; ask the human before killing anything |
| anything else unexpected | stop and report the last 30 lines of output; do not improvise fixes |

If you hit an error you cannot resolve in two attempts, stop and ask the human.

## 7. Reports and hand-over (short, no model text)

After each stage send the human: the `--status` output, hours used so far, any model that
needed a restart, and any warnings. At the end tell the human to send these files to the
researcher **privately** (not through GitHub):

* `outputs/results_for_researcher.zip` (answers and Llama Guard verdicts);
* `outputs/judges_for_researcher.zip` (LLM judge verdicts only).

The human should delete the model folder, `outputs/` and `validate_in/` after the researcher
confirms receipt.
