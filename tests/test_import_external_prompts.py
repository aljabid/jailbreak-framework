import csv
import json
import subprocess
import sys
from pathlib import Path

SCRIPT = str(Path(__file__).resolve().parent.parent / "scripts" / "import_external_prompts.py")


def run_script(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, SCRIPT, *args],
        capture_output=True,
        text=True,
    )


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


class TestAdvBenchFormat:
    def test_converts_goal_column(self, tmp_path):
        src = tmp_path / "harmful_behaviors.csv"
        write_csv(
            src,
            ["goal", "target"],
            [
                {"goal": "Example synthetic goal one", "target": "Sure, here is"},
                {"goal": "Example synthetic goal two", "target": "Sure, here is"},
            ],
        )
        out = tmp_path / "imported.json"

        result = run_script("--source", "advbench", "--input", str(src), "--output", str(out))

        assert result.returncode == 0, result.stderr
        payload = json.loads(out.read_text())
        assert len(payload["prompts"]) == 2
        assert payload["prompts"][0]["text"] == "Example synthetic goal one"
        assert payload["prompts"][0]["source"]["name"] == "AdvBench"
        assert "id" in payload["prompts"][0]

    def test_skips_blank_goal_rows(self, tmp_path):
        src = tmp_path / "harmful_behaviors.csv"
        write_csv(
            src,
            ["goal", "target"],
            [{"goal": "", "target": "x"}, {"goal": "Valid one", "target": "x"}],
        )
        out = tmp_path / "imported.json"

        run_script("--source", "advbench", "--input", str(src), "--output", str(out))

        payload = json.loads(out.read_text())
        assert len(payload["prompts"]) == 1


class TestJailbreakBenchFormat:
    def test_converts_goal_and_category_columns(self, tmp_path):
        src = tmp_path / "jbb.csv"
        write_csv(
            src,
            ["Index", "Goal", "Category"],
            [
                {"Index": "1", "Goal": "Synthetic behavior A", "Category": "Malware/Hacking"},
                {"Index": "2", "Goal": "Synthetic behavior B", "Category": "Fraud/Deception"},
            ],
        )
        out = tmp_path / "imported.json"

        result = run_script("--source", "jailbreakbench", "--input", str(src), "--output", str(out))

        assert result.returncode == 0, result.stderr
        payload = json.loads(out.read_text())
        assert len(payload["prompts"]) == 2
        assert payload["prompts"][0]["category"] == "malware/hacking"
        assert payload["prompts"][0]["source"]["name"] == "JailbreakBench (JBB-Behaviors)"


class TestCustomFormat:
    def test_requires_text_column(self, tmp_path):
        src = tmp_path / "custom.csv"
        write_csv(src, ["prompt"], [{"prompt": "Something"}])
        out = tmp_path / "imported.json"

        result = run_script("--source", "custom", "--input", str(src), "--output", str(out))

        assert result.returncode != 0
        assert "--text-column" in result.stderr

    def test_custom_column_mapping(self, tmp_path):
        src = tmp_path / "custom.csv"
        write_csv(
            src,
            ["prompt", "cat"],
            [{"prompt": "Custom text one", "cat": "general"}],
        )
        out = tmp_path / "imported.json"

        result = run_script(
            "--source",
            "custom",
            "--input",
            str(src),
            "--output",
            str(out),
            "--text-column",
            "prompt",
            "--category-column",
            "cat",
        )

        assert result.returncode == 0, result.stderr
        payload = json.loads(out.read_text())
        assert payload["prompts"][0]["text"] == "Custom text one"
        assert payload["prompts"][0]["category"] == "general"


class TestMergeAndDryRun:
    def test_dry_run_writes_nothing(self, tmp_path):
        src = tmp_path / "harmful_behaviors.csv"
        write_csv(src, ["goal"], [{"goal": "A synthetic goal"}])
        out = tmp_path / "imported.json"

        result = run_script(
            "--source", "advbench", "--input", str(src), "--output", str(out), "--dry-run"
        )

        assert result.returncode == 0, result.stderr
        assert not out.exists()

    def test_merge_into_existing_corpus_appends_without_duplicating(self, tmp_path):
        existing = tmp_path / "prompts.json"
        existing.write_text(
            json.dumps(
                {
                    "version": "2.0",
                    "prompts": [
                        {"id": "gen_001", "category": "general", "text": "Existing", "severity": "low", "tags": []}
                    ],
                }
            )
        )
        src = tmp_path / "harmful_behaviors.csv"
        write_csv(src, ["goal"], [{"goal": "New synthetic goal"}])
        out = tmp_path / "unused.json"

        result = run_script(
            "--source",
            "advbench",
            "--input",
            str(src),
            "--output",
            str(out),
            "--merge-into",
            str(existing),
        )

        assert result.returncode == 0, result.stderr
        payload = json.loads(existing.read_text())
        assert len(payload["prompts"]) == 2
        assert payload["prompts"][0]["id"] == "gen_001"
        assert payload["prompts"][1]["text"] == "New synthetic goal"

    def test_missing_input_file_errors_cleanly(self, tmp_path):
        result = run_script(
            "--source",
            "advbench",
            "--input",
            str(tmp_path / "nonexistent.csv"),
            "--output",
            str(tmp_path / "out.json"),
        )
        assert result.returncode != 0
        assert "not found" in result.stderr
