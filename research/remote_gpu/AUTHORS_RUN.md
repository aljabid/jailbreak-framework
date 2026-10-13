# Running the study on the lab GPU machine

Thank you for helping. You run one script; it does the rest. Expect roughly
**1 to 2 days of GPU time** (about 17 to 22 GPU-hours) and about **100 GB of disk**
for the models. You only need to check on it now and then.

What this is: an authorised red-teaming measurement study (supervisor-approved).
The script sends prompts from public research benchmarks to open models running
locally on this machine, and records the answers. The study measures how
reliable automated "jailbreak judges" are; it does not publish any harmful text.

## Author's instructions

*(Written by the researcher. Edit this section to add anything specific before sending.)*

* Do the smoke test first. Only start the full run once it passes.
* Do not change any settings, prompts or models; the study depends on them being fixed.
* If something unexpected happens, stop and message me instead of working around it.
* Contact: `<name, phone, email>`

## What you need from the researcher (sent privately, not on GitHub)

1. `signing key`, a 64-character string. It goes into `.env` (step 3).
2. `journal_grant_v2_signed.json`, to place in `research/grants/`.
3. `journal_base_corpus.json`, to place in `research/data_journal/`.

## One-time setup

1. Install: Git, Python 3.10+, [uv](https://docs.astral.sh/uv/), [Ollama](https://ollama.com),
   and an NVIDIA driver that supports the RTX 5090 (570 or newer). Check with `nvidia-smi`.
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

4. Put the two files from the researcher in place:
   `research/grants/journal_grant_v2_signed.json` and
   `research/data_journal/journal_base_corpus.json`
   (create the `research/data_journal` folder if it does not exist).
5. Make sure Ollama is running (`ollama serve`, or it starts automatically as a service).
   Do not expose it to the network.
6. Put the model files on a big disk if the default drive is small:
   set the environment variable `OLLAMA_MODELS` to a folder with 100 GB free **before**
   starting Ollama.

## Smoke test (2 minutes): do this first

```
uv run python research/remote_gpu/run_all.py --smoke
```

It must end with `Smoke test passed`. If it fails, send the researcher the last 30 lines of output.

## Run the study

```
uv run python research/remote_gpu/run_all.py
```

* It handles all models in turn, then scores them with Llama Guard, then writes
  `outputs/results_for_researcher.zip`.
* **You can stop it any time** (Ctrl+C, reboot, power cut). Run the same command again and it
  continues where it stopped; finished models are skipped.
* On Linux, run it inside `tmux` or `screen` so closing your terminal does not kill it.
* Check progress without interrupting: `uv run python research/remote_gpu/run_all.py --status`
* Keep the machine from sleeping while it runs.
* Please avoid starting other heavy GPU jobs at the same time.

## When it finishes

Send `outputs/results_for_researcher.zip` to the researcher **privately** (Drive link,
email, or similar). The answers inside contain harmful content produced by the models.

## Please do not

* commit, push, or post anything from `outputs/`, `research/data_journal/`, or `.env`;
* change the prompts, models, seed, or settings (the study depends on them being fixed);
* share the signing key or the corpus file with anyone else.

## Troubleshooting

| Problem | What to do |
|---|---|
| `Authorization signature is invalid` | `.env` key is wrong or has spaces; paste it again with nothing around it |
| `model is outside scope` | the grant file is old or wrong; get the latest `journal_grant_v2_signed.json` |
| `could not pull ...` | model name changed on ollama.com/library; tell the researcher which one |
| Out of memory | something else is using the GPU; check `nvidia-smi` |
| Very slow | the GPU is not being used; check `nvidia-smi` while it runs |

After the study, delete the model folder and `outputs/` from this machine.
