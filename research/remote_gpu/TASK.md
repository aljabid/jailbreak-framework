# Task brief: run the model study on the lab GPU machine

Read this whole file before doing anything. It is written so that a person or an
assistant tool can carry out the task end to end. Where it says "ask the human",
stop and ask the person who gave you this task.

## 1. Context (why this exists)

This repository is an authorisation-gated framework for measuring how reliable
automated "jailbreak judges" are. The study sends prompts from public research
benchmarks (HarmBench, JailbreakBench, StrongREJECT) to open-weight models and records
the answers. Other scripts, run elsewhere, then score those answers with several
judges and compare them with human labels.

* The study is approved by the supervisor and runs on lab hardware with permission.
* Every request is checked against a signed authorisation grant that lists the allowed
  target, models and strategies. That check is part of the method; never bypass it.
* The prompts are intentionally adversarial, and some model answers will contain
  harmful text. This is expected, authorised measurement work. You do **not** need to read
  the answers.

## 2. Your task

Run one script on this machine, which has an NVIDIA RTX 5090 (32 GB). The script
pulls 8 open models through Ollama, attacks each with the study prompts, scores the
answers with Llama Guard 3 8B, and packs everything into one zip file.

You are done when:

1. `uv run python research/remote_gpu/run_all.py --status` shows all 8 models as `DONE`
   with **2484 records each** (138 prompts x 6 strategies x 3 variations); and
2. `outputs/results_for_researcher.zip` exists and contains 8 `adv_gpu_*.json` files plus a
   `judge_out/` folder with 8 `*_lg3_8b.json` files; and
3. you have sent the human the short report in section 7.

## 3. Hard rules

* **Do not read, print, open, summarise, or paste the contents of any file in `outputs/`,
  `research/data_journal/` or `research/judge_reliability/out/*.json`.** To check progress use
  only `--status`, or count records without printing text, e.g.
  `uv run python -c "import json;print(len(json.load(open('outputs/FILE.json',encoding='utf-8'))))"`.
  Do not echo model answers into the conversation or logs.
* **Never print, log, or commit the signing key or the `.env` file.** Ask the human to create
  `.env` themselves (section 4, step 3) so the key never passes through you.
* **Never commit or push anything** from `outputs/`, `research/data_journal/` or `.env`. Do not
  run `git add -A`. You normally have no reason to commit anything at all.
* **Do not change** prompts, models, the model list, seed, temperature, token limit, variations
  count, strategies, or any file under `core/`, `strategies/`, `policy/`, `models/`, `main.py`.
  The study depends on these being fixed.
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
4. **Ask the human** to confirm these two files are in place (they come from the researcher):
   `research/grants/journal_grant_v2_signed.json` and
   `research/data_journal/journal_base_corpus.json`. (The grant may already be in the
   repository after `git pull`; the corpus is never in the repository.)
5. Make sure Ollama is running and storage is large enough: models need about 100 GB.
   If the default drive is small, ask the human where to put them and set `OLLAMA_MODELS` to
   that folder before starting Ollama.

## 5. Run

1. Smoke test (about 2 minutes). Run `uv run python research/remote_gpu/run_all.py --smoke`.
   It must finish with `Smoke test passed`. If not, go to section 6.
2. Full run. Start `uv run python research/remote_gpu/run_all.py` as a **background process**
   that survives your session (tmux/screen on Linux, `Start-Process` on Windows), logging to a
   file. Do not hold a foreground command open for hours.
3. Monitor. Every 30 to 60 minutes run `uv run python research/remote_gpu/run_all.py --status`
   and read only the last few lines of the log. Expect roughly 1 to 4 hours per model (larger
   models are slower); about 17 to 22 GPU-hours in total.
4. The script is resumable. If it stops for any reason (crash, reboot, power cut), just run the
   same command again; finished models are skipped and partial ones continue from cache.
5. Keep the machine awake while it runs. Avoid starting other heavy GPU jobs.

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

## 7. Final report to the human (short, no model text)

* output of `--status` (model names and record counts);
* path and size of `outputs/results_for_researcher.zip`;
* total wall-clock time and any models that needed a restart;
* any warnings seen.

Then tell the human to send the zip to the researcher **privately** (not through GitHub), and
to delete the model folder and `outputs/` after the researcher confirms receipt.
