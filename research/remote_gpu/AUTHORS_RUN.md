# Running the study on the lab GPU machine

Thank you for helping. After setup the whole study is **two commands**. It runs for about
**3 days** inside a total budget of **70 to 80 GPU-hours**, needs about **130 GB** of disk, and
you only check on it now and then. `TASK.md` has the same plan in a form that can be handed
to a script runner; `STUDY_PLAN.md` explains what the whole project is for.

What this is: an authorised red-teaming measurement study (supervisor-approved). The scripts
download public safety benchmarks, send their prompts to open models running locally on this
machine, record the answers, and score them. The study measures how reliable automated
"jailbreak judges" are; it does not publish any harmful text.

## Author's instructions

*(Written by the researcher. Edit this section to add anything specific before sending.)*

* Do the setup and `prepare` first, then `run`. Report to me after `prepare` and when `run` finishes.
* Do not change any settings, prompts or models; the study depends on them being fixed.
* If something unexpected happens, stop and message me instead of working around it.
* Contact: `<name, phone, email>`

## The only thing that does not come from GitHub

The **signing key**, a 64-character string the researcher sends you privately (not in any
chat that is shared or stored publicly). Everything else, including the signed grant, comes
with the repository or is downloaded by the scripts.

## Models (downloaded automatically by `run`)

Target models (open-weight, pulled through Ollama; these exact tags are what the signed grant allows):

| Model tag | Family | Disk |
|---|---|---|
| `llama3.1:8b` | Llama | 5 GB |
| `qwen2.5:7b` | Qwen | 5 GB |
| `mistral:7b` | Mistral | 4 GB |
| `phi4` | Microsoft | 9 GB |
| `qwen2.5:14b` | Qwen | 9 GB |
| `gemma3:27b` | Google | 17 GB |
| `mistral-small:24b` | Mistral | 14 GB |
| `qwen2.5:32b` | Qwen | 20 GB |

Judge models (also pulled automatically): `llama-guard3:8b` (5 GB), `gpt-oss:20b` (13 GB),
`gemma2:27b` (16 GB). Everything together is about 130 GB. Only models up to about 32B are used,
because the machine has one 32 GB GPU. If a tag cannot be pulled, report it; do not substitute.

## One-time setup (Ubuntu)

1. Prerequisites, and make sure the GPU driver works (`nvidia-smi` must show the RTX 5090;
   a 570 or newer driver is needed):

   ```
   sudo apt update && sudo apt install -y git curl tmux
   curl -LsSf https://astral.sh/uv/install.sh | sh        # then open a new shell
   curl -fsSL https://ollama.com/install.sh | sh          # installs the Ollama service
   ```

2. Get the code:

   ```
   git clone https://github.com/aljabid/jailbreak-framework.git
   cd jailbreak-framework
   uv sync --locked
   ```

3. Create a file named `.env` in the project folder with exactly one line
   (use the real key from the researcher; never share or commit this file):

   ```
   JBF_AUTHORIZATION_SIGNING_KEY=PASTE_THE_KEY_HERE
   ```

4. Configure the Ollama service (on Ubuntu it runs under systemd, so settings go in the service,
   not in your shell). Pick a folder on a disk with 150 GB free for the models:

   ```
   sudo mkdir -p /data/ollama-models && sudo chown -R ollama:ollama /data/ollama-models
   sudo systemctl edit ollama
   ```

   In the editor that opens, add these lines, save, and exit:

   ```
   [Service]
   Environment="OLLAMA_NUM_PARALLEL=4"
   Environment="OLLAMA_MODELS=/data/ollama-models"
   ```

   then `sudo systemctl restart ollama`. Do not expose Ollama to the network (the default,
   127.0.0.1, is correct).

5. Keep the machine awake for the three days:
   `sudo systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target`

## Command 1: prepare (about 15 minutes plus downloads)

```
uv run python research/remote_gpu/study.py prepare --accept-terms
```

It downloads the public benchmark files, builds the prompt corpus and runs a 2-minute smoke
test. `--accept-terms` means **you** confirm you have read each dataset's terms (print them
with `uv run python scripts/fetch_benchmarks.py --list`) and will use the files only for
authorised safety evaluation. One dataset (SORRY-Bench) is gated on Hugging Face: if you have
an account that accepted its terms, set `HF_TOKEN` first; otherwise it is skipped and the study
still works. It ends with `Ready` when everything is in order.

## Command 2: run (about 3 days)

```
uv run python research/remote_gpu/study.py run --budget-hours 75
```

It downloads the models (the first time), measures the real speed of each, chooses how many
prompts fit the budget, and works in stages (first 300 prompts, then 700, then as many as the
budget allows). After each stage it scores the answers with Llama Guard and, on a sample, with
two local LLM judges, and rewrites the zip files below. Check progress any time with
`uv run python research/remote_gpu/study.py status`.

It is resumable: after any stop (crash, reboot, power cut) run the same command again. Run it inside
`tmux` so closing the terminal does not stop it (`tmux new -s study`, start the command, detach with
`Ctrl+b` then `d`, come back with `tmux attach -t study`). Avoid other heavy GPU jobs.

Optional validation: if the researcher sent files, put them in a folder `validate_in/` before
`run`; they are processed automatically at the end.

## When it finishes

Send these two files to the researcher **privately** (Drive link, email, or similar). The
answers inside contain harmful content produced by the models.

* `outputs/results_for_researcher.zip`
* `outputs/judges_for_researcher.zip`

## Please do not

* commit, push, or post anything from `outputs/`, `research/data_journal/`, `validate_in/`, or `.env`;
* change the prompts, models, seed, or settings;
* share the signing key with anyone else.

## Troubleshooting

| Problem | What to do |
|---|---|
| `prepare` says a dataset could not be fetched | put the file at the printed path by hand and run `prepare` again |
| `Authorization signature is invalid` | `.env` key is wrong or has spaces; paste it again with nothing around it |
| `model is outside scope` | the grant file is old; run `git pull` |
| `could not pull ...` | model name changed on ollama.com/library; tell the researcher which one |
| Out of memory | something else is using the GPU; check `nvidia-smi` |
| Very slow | the GPU is not being used; check `nvidia-smi` while it runs |

After the study, delete the model folder, `outputs/` and `validate_in/` from this machine.
