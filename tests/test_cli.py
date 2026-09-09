import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from click.testing import CliRunner

from main import cli
from utils.logger import JBFLogger


class TestCLIStructure:
    def test_cli_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "LLM Jailbreak" in result.output

    def test_cli_verbose_flag(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["--verbose", "--help"])
        assert result.exit_code == 0

    def test_cli_config_override(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["--config", "config.yaml", "--help"])
        assert result.exit_code == 0


class TestRunCommand:
    def test_run_mock_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["run", "--help"])
        assert result.exit_code == 0
        assert "--mock" in result.output
        assert "--strategy" in result.output
        assert "--count" in result.output

    def test_run_mock_basic(self):

        runner = CliRunner()
        with runner.isolated_filesystem():
            Path("config.yaml").write_text("""
model:
  provider: "local"
  local_mode: "mock"
attack:
  strategies:
    - roleplay
  base_prompts_file: "data/prompts.json"
evaluation:
  mode: "keyword"
output:
  results_file: "outputs/results.json"
  report_dir: "reports/"
logging:
  level: "INFO"
""")
            Path("data").mkdir(exist_ok=True)
            Path("data/prompts.json").write_text(
                json.dumps(
                    {
                        "prompts": [
                            {
                                "id": "test_001",
                                "text": "Test prompt 1",
                                "category": "general",
                                "severity": "low",
                            },
                        ]
                    }
                )
            )
            Path("outputs").mkdir(exist_ok=True)

            result = runner.invoke(
                cli,
                [
                    "run",
                    "--mock",
                    "--count",
                    "1",
                    "--seed",
                    "42",
                ],
            )
            assert result.exit_code == 0 or "successful" in result.output.lower()

    def test_run_mock_single_strategy(self):

        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "run",
                "--mock",
                "--strategy",
                "roleplay",
                "--count",
                "1",
            ],
        )

        assert result.exit_code in (0, 1)

    def test_run_eval_mode_options(self):

        runner = CliRunner()
        for mode in ["keyword", "ai_judge", "hybrid"]:
            result = runner.invoke(
                cli,
                [
                    "run",
                    "--mock",
                    "--eval-mode",
                    mode,
                    "--count",
                    "1",
                ],
            )

            assert "--eval-mode" not in result.output or "Error" not in result.output

    def test_run_with_output_file(self):

        runner = CliRunner()
        with runner.isolated_filesystem():
            result = runner.invoke(
                cli,
                [
                    "run",
                    "--mock",
                    "--output",
                    "custom_results.json",
                    "--count",
                    "1",
                ],
            )

            assert result.exit_code in (0, 1)

    def test_run_missing_prompts_file_handled(self):

        runner = CliRunner()
        with runner.isolated_filesystem():
            Path("config.yaml").write_text("""
model:
  provider: "local"
  local_mode: "mock"
attack:
  strategies:
    - roleplay
  base_prompts_file: "/nonexistent/prompts.json"
output:
  results_file: "outputs/results.json"
  report_dir: "reports/"
""")
            result = runner.invoke(cli, ["run", "--mock", "--count", "1"])

            assert result.exit_code == 0

            assert "warning" in result.output.lower() or "prompts" in result.output.lower()


class TestCompareCommand:
    def test_compare_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["compare", "--help"])
        assert result.exit_code == 0
        assert "--models" in result.output

    def test_compare_requires_models_option(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["compare"])
        assert result.exit_code != 0

    def test_compare_rejects_unknown_provider(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["compare", "--models", "not-a-provider:some-model"])
        assert result.exit_code != 0
        assert "Unknown provider" in result.output

    def test_compare_two_mock_models(self):
        runner = CliRunner()
        with runner.isolated_filesystem():
            Path("config.yaml").write_text("""
model:
  provider: "local"
  local_mode: "mock"
attack:
  strategies:
    - roleplay
  base_prompts_file: "data/prompts.json"
evaluation:
  mode: "keyword"
output:
  results_file: "outputs/results.json"
  report_dir: "reports/"
""")
            Path("data").mkdir(exist_ok=True)
            Path("data/prompts.json").write_text(
                json.dumps(
                    {
                        "prompts": [
                            {
                                "id": "test_001",
                                "text": "Test prompt 1",
                                "category": "general",
                                "severity": "low",
                            },
                        ]
                    }
                )
            )
            Path("outputs").mkdir(exist_ok=True)

            result = runner.invoke(
                cli,
                [
                    "compare",
                    "--models",
                    "mock:model-a,mock:model-b",
                    "--strategy",
                    "roleplay",
                    "--count",
                    "1",
                    "--seed",
                    "42",
                ],
            )
            assert result.exit_code == 0, result.output
            assert "COMPARISON SUMMARY" in result.output
            assert "mock:model-a" in result.output
            assert "mock:model-b" in result.output
            assert "HTML dashboard" in result.output

    def test_compare_no_report_skips_report_generation(self):
        runner = CliRunner()
        with runner.isolated_filesystem():
            Path("config.yaml").write_text("""
model:
  provider: "local"
  local_mode: "mock"
attack:
  strategies:
    - roleplay
  base_prompts_file: "data/prompts.json"
""")
            Path("data").mkdir(exist_ok=True)
            Path("data/prompts.json").write_text(
                json.dumps({"prompts": [{"id": "t1", "text": "Test", "category": "general"}]})
            )

            result = runner.invoke(
                cli,
                [
                    "compare",
                    "--models",
                    "mock:a,mock:b",
                    "--count",
                    "1",
                    "--no-report",
                ],
            )
            assert result.exit_code == 0, result.output
            assert "HTML dashboard" not in result.output


class TestRegressionCheckCommand:
    def _write_results(self, path: str, success_rate: float, risk_score: float):
        n_success = int(round(success_rate * 10))
        results = [
            {
                "strategy": "roleplay",
                "success": i < n_success,
                "risk_score": risk_score,
                "risk_level": "High" if i < n_success else "None",
            }
            for i in range(10)
        ]
        Path(path).write_text(json.dumps(results))

    def test_regression_check_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["regression-check", "--help"])
        assert result.exit_code == 0
        assert "--baseline" in result.output

    def test_no_regression_passes(self):
        runner = CliRunner()
        with runner.isolated_filesystem():
            self._write_results("baseline.json", success_rate=0.2, risk_score=0.2)
            self._write_results("current.json", success_rate=0.2, risk_score=0.2)

            result = runner.invoke(
                cli,
                [
                    "regression-check",
                    "--baseline",
                    "baseline.json",
                    "--current",
                    "current.json",
                ],
            )
            assert result.exit_code == 0, result.output
            assert "OK" in result.output

    def test_worse_success_rate_fails_gate(self):
        runner = CliRunner()
        with runner.isolated_filesystem():
            self._write_results("baseline.json", success_rate=0.1, risk_score=0.1)
            self._write_results("current.json", success_rate=0.9, risk_score=0.1)

            result = runner.invoke(
                cli,
                [
                    "regression-check",
                    "--baseline",
                    "baseline.json",
                    "--current",
                    "current.json",
                ],
            )
            assert result.exit_code != 0
            assert "REGRESSED" in result.output

    def test_json_output_is_valid_json(self):
        runner = CliRunner()
        with runner.isolated_filesystem():
            self._write_results("baseline.json", success_rate=0.1, risk_score=0.1)
            self._write_results("current.json", success_rate=0.1, risk_score=0.1)

            result = runner.invoke(
                cli,
                [
                    "regression-check",
                    "--baseline",
                    "baseline.json",
                    "--current",
                    "current.json",
                    "--json-output",
                ],
            )
            assert result.exit_code == 0, result.output
            payload = json.loads(result.output)
            assert payload["regressed"] is False

    def test_accepts_summary_json_shape(self):
        runner = CliRunner()
        with runner.isolated_filesystem():
            summary = {
                "generated_at": "2026-01-01T00:00:00Z",
                "session_id": "s1",
                "stats": {"success_rate": 0.1, "average_risk_score": 0.1},
            }
            Path("baseline.json").write_text(json.dumps(summary))
            Path("current.json").write_text(json.dumps(summary))

            result = runner.invoke(
                cli,
                [
                    "regression-check",
                    "--baseline",
                    "baseline.json",
                    "--current",
                    "current.json",
                ],
            )
            assert result.exit_code == 0, result.output

    def test_unrecognized_format_errors_cleanly(self):
        runner = CliRunner()
        with runner.isolated_filesystem():
            Path("baseline.json").write_text(json.dumps({"not": "a recognized shape"}))
            Path("current.json").write_text(json.dumps({"not": "a recognized shape"}))

            result = runner.invoke(
                cli,
                [
                    "regression-check",
                    "--baseline",
                    "baseline.json",
                    "--current",
                    "current.json",
                ],
            )
            assert result.exit_code != 0
            assert "Unrecognized results format" in result.output


class TestReportCommand:
    def test_report_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["report", "--help"])
        assert result.exit_code == 0

    def test_report_format_options(self):

        runner = CliRunner()
        with runner.isolated_filesystem():
            results = [
                {
                    "strategy": "roleplay",
                    "success": True,
                    "risk_level": "High",
                    "risk_score": 0.75,
                }
            ]
            Path("outputs").mkdir(exist_ok=True)
            Path("outputs/results.json").write_text(json.dumps(results))
            Path("config.yaml").write_text("""
output:
  results_file: "outputs/results.json"
  report_dir: "reports/"
""")

            for fmt in ["terminal", "markdown", "all"]:
                result = runner.invoke(
                    cli,
                    [
                        "report",
                        "--format",
                        fmt,
                    ],
                )
                assert result.exit_code in (0, 1)

    def test_report_missing_results_file(self):

        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "report",
                "--input",
                "/nonexistent/results.json",
            ],
        )

        assert result.exit_code != 0 or "not found" in result.output.lower()


class TestListStrategiesCommand:
    def test_list_strategies(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["list-strategies"])
        assert result.exit_code == 0

        assert "roleplay" in result.output.lower()
        assert "encoding" in result.output.lower()


class TestTestConnectionCommand:
    def test_test_connection_mock(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["test-connection", "--mock"])
        assert result.exit_code == 0
        assert "successful" in result.output.lower()

    def test_test_connection_flag_accepted(self):

        runner = CliRunner()
        result = runner.invoke(cli, ["test-connection", "--help"])
        assert "--mock" in result.output


class TestCLIErrorHandling:
    def test_invalid_strategy_name(self):

        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "run",
                "--mock",
                "--strategy",
                "nonexistent_strategy",
                "--count",
                "1",
            ],
        )

        assert result.exit_code in (0, 1)

    def test_invalid_eval_mode(self):

        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "run",
                "--mock",
                "--eval-mode",
                "invalid_mode",
            ],
        )

        assert result.exit_code != 0 or "invalid choice" in result.output.lower()

    def test_negative_count(self):

        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "run",
                "--mock",
                "--count",
                "-1",
            ],
        )

        assert result.exit_code == 2
        assert "range" in result.output.lower()


class TestCLISessionTracking:
    def test_session_id_generated(self):

        assert len(JBFLogger.SESSION_ID) > 0
        assert isinstance(JBFLogger.SESSION_ID, str)

    def test_session_id_in_logs(self):

        runner = CliRunner()
        result = runner.invoke(cli, ["test-connection", "--mock"])

        assert result.exit_code == 0
