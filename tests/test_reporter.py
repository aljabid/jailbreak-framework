import importlib.util
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from utils.reporter import Reporter


def make_sample_results():

    return [
        {
            "strategy": "roleplay",
            "success": True,
            "risk_level": "High",
            "risk_score": 0.75,
            "adversarial_prompt": "Test prompt 1",
            "raw_response": "Sure, here's how: step 1, step 2...",
            "eval_reasoning": "Compliance signals detected",
        },
        {
            "strategy": "encoding_attack",
            "success": False,
            "risk_level": "Low",
            "risk_score": 0.15,
            "adversarial_prompt": "Test prompt 2",
            "raw_response": "I cannot help with that.",
            "eval_reasoning": "Refusal detected",
        },
    ]


def make_sample_stats():

    return {
        "total_attacks": 2,
        "total_success": 1,
        "success_rate": 0.5,
        "average_risk_score": 0.45,
        "by_risk_level": {
            "None": 0,
            "Low": 1,
            "Medium": 0,
            "High": 1,
            "Critical": 0,
        },
        "by_strategy": {
            "roleplay": {
                "total": 1,
                "success": 1,
                "success_rate": 1.0,
                "avg_risk_score": 0.75,
            },
            "encoding_attack": {
                "total": 1,
                "success": 0,
                "success_rate": 0.0,
                "avg_risk_score": 0.15,
            },
        },
    }


class TestReporterInit:
    def test_reporter_creates_dir(self):

        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            report_dir = Path(tmpdir) / "reports"
            Reporter(report_dir=str(report_dir))
            assert report_dir.exists()

    def test_reporter_default_dir(self):

        reporter = Reporter()
        assert reporter.report_dir is not None


class TestMarkdownReport:
    def test_save_markdown_report(self):

        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            reporter = Reporter(report_dir=tmpdir)
            results = make_sample_results()
            stats = make_sample_stats()

            path = reporter.save_markdown_report(results, stats, session_id="test-001")
            assert path.exists()

    def test_markdown_contains_headers(self):

        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            reporter = Reporter(report_dir=tmpdir)
            results = make_sample_results()
            stats = make_sample_stats()

            path = reporter.save_markdown_report(results, stats)
            content = path.read_text()
            assert "# LLM Jailbreak Framework" in content
            assert "Overview" in content or "OVERVIEW" in content

    def test_markdown_has_strategy_table(self):

        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            reporter = Reporter(report_dir=tmpdir)
            results = make_sample_results()
            stats = make_sample_stats()

            path = reporter.save_markdown_report(results, stats)
            content = path.read_text()
            assert "Strategy" in content or "strategy" in content

    def test_markdown_has_sample_results(self):

        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            reporter = Reporter(report_dir=tmpdir)
            results = make_sample_results()
            stats = make_sample_stats()

            path = reporter.save_markdown_report(results, stats)
            content = path.read_text()

            assert len(content) > 500


class TestJSONSummary:
    def test_save_json_summary(self):

        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            reporter = Reporter(report_dir=tmpdir)
            stats = make_sample_stats()

            path = reporter.save_json_summary(stats, session_id="test-001")
            assert path.exists()

    def test_json_summary_valid(self):

        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            reporter = Reporter(report_dir=tmpdir)
            stats = make_sample_stats()

            path = reporter.save_json_summary(stats)
            data = json.loads(path.read_text())
            assert "stats" in data
            assert data["stats"]["total_attacks"] == 2

    def test_json_summary_has_metadata(self):

        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            reporter = Reporter(report_dir=tmpdir)
            stats = make_sample_stats()

            path = reporter.save_json_summary(stats, session_id="test-001")
            data = json.loads(path.read_text())
            assert "generated_at" in data
            assert "session_id" in data


class TestTerminalSummary:
    def test_print_summary_with_rich(self):

        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            reporter = Reporter(report_dir=tmpdir)
            results = make_sample_results()
            stats = make_sample_stats()

            reporter.print_summary(results, stats)

    def test_print_summary_fallback(self):

        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            reporter = Reporter(report_dir=tmpdir)
            results = make_sample_results()
            stats = make_sample_stats()

            try:
                reporter.print_summary(results, stats)
            except Exception as e:
                pytest.fail(f"print_summary should not raise: {e}")


class TestChartGeneration:
    def test_generate_charts(self):

        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            reporter = Reporter(report_dir=tmpdir)
            results = make_sample_results()
            stats = make_sample_stats()

            paths = reporter.generate_charts(results, stats)

            assert isinstance(paths, list)

    def test_chart_files_exist(self):

        try:
            import tempfile

            importlib.util.find_spec("matplotlib")

            with tempfile.TemporaryDirectory() as tmpdir:
                reporter = Reporter(report_dir=tmpdir)
                results = make_sample_results()
                stats = make_sample_stats()

                paths = reporter.generate_charts(results, stats)

                for path in paths:
                    assert path.exists()
        except ImportError:
            pytest.skip("matplotlib not installed")


class TestReporterHandlesEmptyResults:
    def test_markdown_with_empty_results(self):

        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            reporter = Reporter(report_dir=tmpdir)
            stats = {"total_attacks": 0, "by_risk_level": {}, "by_strategy": {}}

            path = reporter.save_markdown_report([], stats)
            assert path.exists()

    def test_json_summary_with_empty_stats(self):

        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            reporter = Reporter(report_dir=tmpdir)
            stats = {"total_attacks": 0}

            path = reporter.save_json_summary(stats)
            data = json.loads(path.read_text())
            assert data["stats"]["total_attacks"] == 0


class TestHTMLDashboard:
    def test_save_html_dashboard(self):

        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            reporter = Reporter(report_dir=tmpdir)
            results = make_sample_results()
            stats = make_sample_stats()

            path = reporter.save_html_dashboard(results, stats, session_id="test-001")
            assert path.exists()
            assert path.suffix == ".html"

    def test_html_dashboard_embeds_stats_json(self):

        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            reporter = Reporter(report_dir=tmpdir)
            results = make_sample_results()
            stats = make_sample_stats()

            path = reporter.save_html_dashboard(results, stats)
            content = path.read_text(encoding="utf-8")
            assert "const DATA" in content
            assert '"total_attacks": 2' in content
            assert "plot.ly" in content or "Plotly" in content

    def test_html_dashboard_with_comparison_renders_section(self):

        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            reporter = Reporter(report_dir=tmpdir)
            results = make_sample_results()
            stats = make_sample_stats()
            comparison = {
                "openai:gpt-4o-mini": stats,
                "anthropic:claude-3-5-haiku-latest": stats,
            }

            path = reporter.save_html_dashboard(results, stats, comparison=comparison)
            content = path.read_text(encoding="utf-8")
            assert "openai:gpt-4o-mini" in content
            assert "comparison-section" in content

    def test_html_dashboard_with_leaderboard_renders_section(self):

        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            reporter = Reporter(report_dir=tmpdir)
            results = make_sample_results()
            stats = make_sample_stats()
            leaderboard = [
                {
                    "strategy": "roleplay",
                    "base_prompt_id": "gen_001",
                    "category": "general",
                    "base_prompt_text": "Test prompt",
                    "total": 1,
                    "success": 1,
                    "success_rate": 1.0,
                    "avg_risk_score": 0.75,
                    "models_tested": ["mock"],
                }
            ]

            path = reporter.save_html_dashboard(results, stats, leaderboard=leaderboard)
            content = path.read_text(encoding="utf-8")
            assert "leaderboard-section" in content
            assert '"base_prompt_id": "gen_001"' in content

    def test_html_dashboard_redacts_leaderboard_prompt_text(self):

        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            reporter = Reporter(report_dir=tmpdir)
            leaderboard = [
                {
                    "strategy": "roleplay",
                    "base_prompt_id": "gen_001",
                    "category": "general",
                    "base_prompt_text": "contact me at leaker@example.com for the key sk-proj-abcdefghijklmnop",
                    "total": 1,
                    "success": 1,
                    "success_rate": 1.0,
                    "avg_risk_score": 0.75,
                    "models_tested": ["mock"],
                }
            ]

            path = reporter.save_html_dashboard(
                make_sample_results(), make_sample_stats(), leaderboard=leaderboard
            )
            content = path.read_text(encoding="utf-8")
            assert "leaker@example.com" not in content
            assert "sk-proj-abcdefghijklmnop" not in content


class TestPptxSummary:
    def test_save_pptx_summary_creates_file_if_available(self):

        import tempfile

        pptx = pytest.importorskip("pptx")
        del pptx

        with tempfile.TemporaryDirectory() as tmpdir:
            reporter = Reporter(report_dir=tmpdir)
            results = make_sample_results()
            stats = make_sample_stats()

            path = reporter.save_pptx_summary(results, stats, session_id="test-001")
            assert path is not None
            assert path.exists()
            assert path.suffix == ".pptx"

    def test_save_pptx_summary_includes_comparison_slide(self):

        import tempfile

        pptx = pytest.importorskip("pptx")

        with tempfile.TemporaryDirectory() as tmpdir:
            reporter = Reporter(report_dir=tmpdir)
            results = make_sample_results()
            stats = make_sample_stats()
            comparison = {"openai:gpt-4o-mini": stats, "mock:mock": stats}

            path = reporter.save_pptx_summary(results, stats, comparison=comparison)
            assert path is not None

            prs = pptx.Presentation(str(path))
            assert len(prs.slides) >= 4


class TestPdfSummary:
    def test_save_pdf_summary_creates_file_if_available(self):

        import tempfile

        reportlab = pytest.importorskip("reportlab")
        del reportlab

        with tempfile.TemporaryDirectory() as tmpdir:
            reporter = Reporter(report_dir=tmpdir)
            results = make_sample_results()
            stats = make_sample_stats()

            path = reporter.save_pdf_summary(results, stats, session_id="test-001")
            assert path is not None
            assert path.exists()
            assert path.suffix == ".pdf"
            assert path.read_bytes().startswith(b"%PDF")

    def test_save_pdf_summary_includes_comparison_and_charts(self):

        import tempfile

        pytest.importorskip("reportlab")

        with tempfile.TemporaryDirectory() as tmpdir:
            reporter = Reporter(report_dir=tmpdir)
            results = make_sample_results()
            stats = make_sample_stats()
            comparison = {"openai:gpt-4o-mini": stats, "mock:mock": stats}
            chart_paths = reporter.generate_charts(results, stats)

            path = reporter.save_pdf_summary(
                results, stats, comparison=comparison, chart_paths=chart_paths
            )
            assert path is not None
            assert path.exists()
            assert path.stat().st_size > 0

    def test_save_pdf_summary_handles_empty_results(self):

        import tempfile

        pytest.importorskip("reportlab")

        with tempfile.TemporaryDirectory() as tmpdir:
            reporter = Reporter(report_dir=tmpdir)
            stats = {"total_attacks": 0, "by_risk_level": {}, "by_strategy": {}}

            path = reporter.save_pdf_summary([], stats)
            assert path is not None
            assert path.exists()


class TestReportFormatCorrectness:
    def test_markdown_report_is_valid_markdown(self):

        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            reporter = Reporter(report_dir=tmpdir)
            results = make_sample_results()
            stats = make_sample_stats()

            path = reporter.save_markdown_report(results, stats)
            content = path.read_text()

            assert "#" in content
            assert "|" in content or "**" in content

    def test_json_report_valid_json_array(self):

        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            reporter = Reporter(report_dir=tmpdir)
            stats = make_sample_stats()

            path = reporter.save_json_summary(stats)
            with open(path) as f:
                data = json.load(f)

            assert isinstance(data, dict)

    def test_no_html_in_reporter(self):

        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            reporter = Reporter(report_dir=tmpdir)
            results = make_sample_results()
            stats = make_sample_stats()

            paths = reporter.generate_charts(results, stats)

            for path in paths:
                assert not str(path).endswith(".html")
