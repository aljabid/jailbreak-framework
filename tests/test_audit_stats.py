"""Tests for the audit statistics (research/judge_reliability/audit_stats.py)."""
from __future__ import annotations

import importlib.util
import math
import random
import sys
from pathlib import Path

import numpy as np

SPEC = importlib.util.spec_from_file_location(
    "audit_stats", Path(__file__).resolve().parents[1] / "research" / "judge_reliability" / "audit_stats.py")
assert SPEC is not None and SPEC.loader is not None
st = importlib.util.module_from_spec(SPEC)
sys.modules["audit_stats"] = st
SPEC.loader.exec_module(st)


def population(rng: random.Random) -> tuple[list[dict], dict[str, bool]]:
    """Two models; a noisy judge; true labels known for everyone."""
    pop, truth = [], {}
    for model, rate in (("a", 0.10), ("b", 0.02)):
        for i in range(3000):
            y = rng.random() < rate
            # judge: sensitivity 0.7, false-positive rate 0.01
            vote = (rng.random() < 0.7) if y else (rng.random() < 0.01)
            uid = f"{model}{i}"
            pop.append({"uid": uid, "model": model, "vote": vote})
            truth[uid] = y
    return pop, truth


def audit_sample(pop: list[dict], truth: dict[str, bool], rng: random.Random, per_sub: int) -> dict[str, bool]:
    labels: dict[str, bool] = {}
    for model in ("a", "b"):
        for vote in (True, False):
            sub = [r for r in pop if r["model"] == model and r["vote"] is vote]
            for r in rng.sample(sub, min(per_sub, len(sub))):
                labels[r["uid"]] = truth[r["uid"]]
    return labels


def run(pop: list[dict], labels: dict[str, bool], nrng: np.random.Generator) -> dict[str, np.ndarray]:
    cells = st.build_cells(pop, labels, lambda r: r["vote"], lambda r: r["model"],
                           lambda r: f"{r['model']}|{r['vote']}")
    pos = st.draw_positives(cells, nrng, 4000)
    return st.group_metrics(cells, pos, "a")


def test_interval_covers_truth_most_of_the_time() -> None:
    rng = random.Random(1)
    nrng = np.random.default_rng(1)
    hits, reps = 0, 60
    for _ in range(reps):
        pop, truth = population(rng)
        labels = audit_sample(pop, truth, rng, 150)
        true_asr = sum(truth[r["uid"]] for r in pop if r["model"] == "a") / 3000
        _, lo, hi = st.summarize(run(pop, labels, nrng)["true_asr"])
        hits += lo <= true_asr <= hi
    assert hits / reps >= 0.88  # nominal 95%; few repetitions, so a loose floor


def test_zero_positive_cell_keeps_a_nonzero_upper_bound() -> None:
    pop = [{"uid": f"u{i}", "model": "a", "vote": False} for i in range(1000)]
    labels = {f"u{i}": False for i in range(100)}
    cells = st.build_cells(pop, labels, lambda r: r["vote"], lambda r: r["model"], lambda r: "s")
    pos = st.draw_positives(cells, np.random.default_rng(0), 4000)
    mean, lo, hi = st.summarize(st.group_metrics(cells, pos)["true_asr"])
    assert lo == 0 and hi > 0.002  # a normal interval would be [0, 0]


def test_group_metrics_identities() -> None:
    cells = [st.Cell("g", "s1", True, 100, 100, 80), st.Cell("g", "s2", False, 900, 900, 45)]
    pos = st.draw_positives(cells, np.random.default_rng(0), 10)
    m = st.group_metrics(cells, pos)
    assert np.allclose(m["true_asr"], 125 / 1000)
    assert np.allclose(m["sensitivity"], 80 / 125)
    assert np.allclose(m["precision"], 0.8)
    assert np.allclose(m["specificity"], 855 / 875)
    assert np.allclose(m["miss_rate_of_negatives"], 45 / 900)


def test_evidence_sample_size_matches_hand_values() -> None:
    assert st.evidence_sample_size(0.01, 1.0) == 299
    assert st.evidence_sample_size(0.01, 0.5) == 598
    assert st.evidence_sample_size(0.01, 0.25) == 1197


def test_zero_count_upper_bound() -> None:
    assert math.isclose(st.zero_count_upper(400), 1 - 0.05 ** (1 / 400))
    assert 0.0073 < st.zero_count_upper(400) < 0.0076


def test_kappas() -> None:
    a = ["x", "y", "x", "y", "x", "x"]
    assert st.cohen_kappa(a, a) == 1.0
    assert abs(st.cohen_kappa(["x", "y", "x", "y"], ["y", "x", "y", "x"]) + 1.0) < 1e-9
    rows = [["x", "x", "x"], ["y", "y", "y"], ["x", "y", "x"], ["y", "y", "x"]]
    assert 0 < st.fleiss_kappa(rows) < 1


def test_final_labels_majority_and_ties() -> None:
    resolved, unresolved = st.final_labels({
        "i1": {"A": "jailbreak", "B": "partial"},
        "i2": {"A": "refusal", "B": "safe"},
        "i3": {"A": "jailbreak", "B": "safe"},
        "i4": {"A": "jailbreak", "B": "safe", "C": "partial"},
    })
    assert resolved == {"i1": True, "i2": False, "i4": True}
    assert unresolved == ["i3"]
