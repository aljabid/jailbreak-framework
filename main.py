import json
import logging
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import click

from application.campaigns import CampaignRunner
from application.policies import BudgetPolicy
from application.rate_limits import TokenBucketRateLimiter
from core.attacker import AttackEngine
from core.evaluator import Evaluator
from core.generator import PromptGenerator
from core.scorer import Scorer
from domain.models import Campaign, CampaignStatus, ReviewDecision
from evaluation.benchmark import EvaluatorBenchmark
from evaluation.scoring_benchmark import ScoringBenchmark
from models.anthropic_model import AnthropicModel
from models.local_model import LocalModel
from models.openai_model import OpenAIModel
from observability.health import HealthChecker
from observability.metrics import GLOBAL_METRICS
from observability.server import create_observability_server
from persistence.sqlite import SQLiteCampaignRepository
from policy.access import AccessContext, Permission, Role
from policy.authorization import (
    AuthorizationGrant,
    AuthorizationVerifier,
    sign_authorization_payload,
)
from utils.cache import ResponseCache
from utils.config import Config
from utils.encryption import ArtifactCipher
from utils.files import atomic_write_text
from utils.logger import AttackRecordLogger, JBFLogger
from utils.redaction import redact_value
from utils.reporter import Reporter


@click.group(
    help=(
        "LLM Jailbreak Automation Framework for authorized model-security "
        "evaluation."
    )
)
@click.option("--config", default="config.yaml", help="Path to config.yaml")
@click.option("--verbose", "-v", is_flag=True, help="Enable debug logging")
@click.pass_context
def cli(ctx, config, verbose):

    ctx.ensure_object(dict)
    try:
        cfg = Config(config_file=config, strict=True)
    except (TypeError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc
    ctx.obj["config"] = cfg

    log_level = "DEBUG" if verbose else cfg.log_level
    JBFLogger(log_level=log_level, log_file=cfg.logs_file)
    ctx.obj["logger"] = logging.getLogger("jbf.main")


@cli.command()
@click.option(
    "--strategy", "-s", default=None, help="Run a single strategy (default: all from config)"
)
@click.option("--mock", is_flag=True, help="Use mock model (no API key required)")
@click.option(
    "--provider",
    type=click.Choice(["openai", "anthropic", "local", "mock"]),
    default=None,
    help="Model provider override",
)
@click.option("--model-name", default=None, help="Primary model name override")
@click.option(
    "--local-mode",
    type=click.Choice(["ollama", "huggingface"]),
    default=None,
    help="Local backend mode when provider is local",
)
@click.option("--ollama-base-url", default=None, help="Ollama base URL for local mode")
@click.option("--temperature", default=None, type=float, help="Sampling temperature override")
@click.option("--max-tokens", default=None, type=int, help="Max response tokens override")
@click.option("--timeout", default=None, type=int, help="Model timeout override")
@click.option(
    "--count", "-n", default=None, type=click.IntRange(min=1), help="Max prompts per strategy"
)
@click.option(
    "--variations", default=1, type=click.IntRange(min=1), show_default=True,
    help="Adversarial prompts generated per base prompt per strategy",
)
@click.option(
    "--eval-mode",
    default=None,
    type=click.Choice(["keyword", "ai_judge", "hybrid"]),
    help="Evaluation mode override",
)
@click.option(
    "--judge-model", default=None, help="AI judge model override for ai_judge/hybrid modes"
)
@click.option("--keywords-file", default=None, help="Custom evaluation keywords JSON file")
@click.option(
    "--critical-threshold", default=None, type=float, help="Critical risk threshold override"
)
@click.option("--high-threshold", default=None, type=float, help="High risk threshold override")
@click.option("--medium-threshold", default=None, type=float, help="Medium risk threshold override")
@click.option("--output", "-o", default=None, help="Output results file path")
@click.option("--report/--no-report", default=None, help="Generate report after run")
@click.option("--seed", default=None, type=int, help="Random seed for reproducibility")
@click.option("--target-id", default=None, help="Authorized target identifier")
@click.option(
    "--authorization-file",
    type=click.Path(exists=True, dir_okay=False),
    default=None,
    help="Signed authorization grant required for non-mock targets",
)
@click.option(
    "--cache/--no-cache",
    default=None,
    help="Reuse a cached response for an identical prompt+model+params instead of re-querying",
)
@click.option(
    "--category",
    "categories",
    multiple=True,
    help="Restrict base prompts to one or more categories (repeatable)",
)
@click.option(
    "--concurrency",
    default=1,
    type=click.IntRange(min=1),
    show_default=True,
    help="Concurrent requests in flight per strategy batch (thread pool)",
)
@click.pass_context
def run(
    ctx,
    strategy,
    mock,
    provider,
    model_name,
    local_mode,
    ollama_base_url,
    temperature,
    max_tokens,
    timeout,
    count,
    variations,
    eval_mode,
    judge_model,
    keywords_file,
    critical_threshold,
    high_threshold,
    medium_threshold,
    output,
    report,
    seed,
    target_id,
    authorization_file,
    cache,
    categories,
    concurrency,
):

    cfg: Config = ctx.obj["config"]
    log: logging.Logger = ctx.obj["logger"]
    should_report = True if report is None else report

    _print_banner()

    strategies = [strategy] if strategy else cfg.strategies
    log.info(f"Running strategies: {strategies}")

    generator = PromptGenerator(
        strategies=strategies,
        prompts_file=cfg.prompts_file,
        seed=seed,
        categories=list(categories) if categories else None,
    )
    planned_count = sum(len(generator.generate_batch(name, count=count, variations=variations)) for name in strategies)
    if not mock:
        resolved_provider = provider or cfg.model_provider
        resolved_model = model_name or cfg.model_name
        _verify_authorization(
            cfg,
            authorization_file=authorization_file,
            target_id=target_id,
            provider=resolved_provider,
            model=resolved_model,
            strategies=strategies,
            request_count=planned_count,
        )

    model = _build_model(
        cfg,
        mock=mock,
        provider=provider,
        model_name=model_name,
        local_mode=local_mode,
        ollama_base_url=ollama_base_url,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=timeout,
        seed=seed,
    )
    if not mock:
        log.info("Testing API connection...")
        if not model.test_connection():
            click.echo("ERROR: API connection failed. Use --mock for offline testing.", err=True)
            sys.exit(1)
        log.info("API connection OK")

    cache_enabled = cfg.cache_enabled if cache is None else cache
    response_cache = ResponseCache(cfg.cache_file) if cache_enabled else None
    if response_cache is not None:
        log.info(f"Response cache enabled: {cfg.cache_file}")

    attacker = AttackEngine(
        model=model,
        max_retries=cfg.max_retries,
        retry_delay=cfg.retry_delay,
        rate_limit_delay=cfg.rate_limit_delay,
        max_retry_delay=cfg.max_retry_delay,
        retry_jitter=cfg.retry_jitter,
        cache=response_cache,
        max_workers=concurrency,
    )
    resolved_eval_mode = eval_mode or cfg.eval_mode
    judge = None
    if resolved_eval_mode in ("ai_judge", "hybrid"):
        judge = _build_judge_model(
            cfg,
            mock=mock,
            judge_model=judge_model,
            provider=provider,
            local_mode=local_mode,
            ollama_base_url=ollama_base_url,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
            seed=seed,
        )
    evaluator = Evaluator(
        mode=resolved_eval_mode,
        keywords_file=keywords_file or cfg.keywords_file,
        ai_judge_model=judge,
        confidence_threshold=cfg.confidence_threshold,
    )
    scorer = Scorer(
        critical_threshold=critical_threshold
        if critical_threshold is not None
        else cfg.critical_threshold,
        high_threshold=high_threshold if high_threshold is not None else cfg.high_threshold,
        medium_threshold=medium_threshold if medium_threshold is not None else cfg.medium_threshold,
    )

    run_metadata = {
        **cfg.summarize(),
        "provider": "mock" if mock else (provider or cfg.model_provider),
        "model_name": model_name or cfg.model_name,
        "local_mode": local_mode or cfg.local_mode,
        "eval_mode": resolved_eval_mode,
        "keywords_file": keywords_file or cfg.keywords_file,
        "seed": seed,
        "report_enabled": should_report,
    }

    record_logger = AttackRecordLogger(output or cfg.results_file, run_metadata=run_metadata)
    reporter = Reporter(cfg.report_dir)

    log.info(
        f"Experiment start | strategies={strategies} | "
        f"prompts={generator.prompt_count} | model={model.model_name} | eval={resolved_eval_mode}"
    )

    all_results = []

    for strat_name in strategies:
        click.echo(f"\n{'=' * 60}")
        click.echo(f"  Strategy: {strat_name}")
        click.echo(f"{'=' * 60}")

        batch = generator.generate_batch(strat_name, count=count, variations=variations)
        click.echo(f"  Generated {len(batch)} adversarial prompts")

        click.echo(f"  Sending to model: {model.model_name}")
        attack_results = attacker.send_batch(batch)

        eval_results = evaluator.evaluate_batch(attack_results)

        scored = scorer.score_batch(eval_results)

        for r in scored:
            r["attack_type"] = r.get("strategy", "unknown")
            if cfg.save_all_responses or r.get("success"):
                record_logger.save(r)
            all_results.append(r)

            icon = "SUCCESS" if r.get("success") else "REFUSED"
            level = r.get("risk_level", "?")
            click.echo(f"  {icon} [{level:8s}] score={r.get('risk_score', 0):.3f} | {strat_name}")

    stats = scorer.aggregate_stats(all_results)

    if should_report and all_results:
        if cfg.pretty_print:
            reporter.print_summary(all_results, stats)
        reporter.save_json_summary(stats, session_id=JBFLogger.SESSION_ID)
        md_path = reporter.save_markdown_report(all_results, stats, session_id=JBFLogger.SESSION_ID)
        click.echo(f"\nMarkdown report: {md_path}")

        chart_paths = reporter.generate_charts(all_results, stats)
        if chart_paths:
            click.echo(f"Charts: {[str(p) for p in chart_paths]}")

        leaderboard = scorer.leaderboard(all_results)
        html_path = reporter.save_html_dashboard(
            all_results, stats, session_id=JBFLogger.SESSION_ID, leaderboard=leaderboard
        )
        click.echo(f"HTML dashboard: {html_path}")

    click.echo(f"\nResults saved to: {output or cfg.results_file}")
    click.echo(f"   Total records: {record_logger.record_count}")
    click.echo(f"   Session ID:    {JBFLogger.SESSION_ID}")


@cli.command()
@click.option(
    "--input", "-i", "input_file", default=None, help="Results JSON file (default: from config)"
)
@click.option(
    "--format",
    "-f",
    type=click.Choice(["terminal", "markdown", "html", "pptx", "pdf", "all"]),
    default="all",
)
@click.pass_context
def report(ctx, input_file, format):
    cfg: Config = ctx.obj["config"]
    results_path = Path(input_file or cfg.results_file)

    if not results_path.exists():
        click.echo(f"ERROR: Results file not found: {results_path}", err=True)
        sys.exit(1)

    with open(results_path) as f:
        results = json.load(f)

    scorer = Scorer()
    stats = scorer.aggregate_stats(results)
    reporter = Reporter(cfg.report_dir)

    if format in ("terminal", "all") and cfg.pretty_print:
        reporter.print_summary(results, stats)

    if format in ("markdown", "all"):
        path = reporter.save_markdown_report(results, stats)
        click.echo(f"Markdown: {path}")

    chart_paths: list = []
    if format == "all":
        chart_paths = reporter.generate_charts(results, stats)

    if format in ("html", "all"):
        leaderboard = scorer.leaderboard(results)
        html_path = reporter.save_html_dashboard(results, stats, leaderboard=leaderboard)
        click.echo(f"HTML dashboard: {html_path}")

    if format in ("pptx", "all"):
        pptx_path = reporter.save_pptx_summary(results, stats, chart_paths=chart_paths)
        if pptx_path:
            click.echo(f"PPTX summary: {pptx_path}")

    if format in ("pdf", "all"):
        pdf_path = reporter.save_pdf_summary(results, stats, chart_paths=chart_paths)
        if pdf_path:
            click.echo(f"PDF summary: {pdf_path}")


@cli.command("compare")
@click.option(
    "--models",
    required=True,
    help=(
        "Comma-separated provider:model specs to compare, e.g. "
        "'openai:gpt-4o-mini,anthropic:claude-3-5-haiku-latest,mock:mock'"
    ),
)
@click.option(
    "--strategy", "-s", default=None, help="Run a single strategy (default: all from config)"
)
@click.option(
    "--category",
    "categories",
    multiple=True,
    help="Restrict base prompts to one or more categories (repeatable)",
)
@click.option(
    "--count", "-n", default=None, type=click.IntRange(min=1), help="Max prompts per strategy"
)
@click.option(
    "--seed", default=None, type=int, help="Random seed shared across all compared models"
)
@click.option(
    "--eval-mode",
    default=None,
    type=click.Choice(["keyword", "ai_judge", "hybrid"]),
    help="Evaluation mode override",
)
@click.option("--judge-model", default=None, help="AI judge model override")
@click.option(
    "--target-id", default=None, help="Authorized target identifier (required for non-mock models)"
)
@click.option(
    "--authorization-file",
    type=click.Path(exists=True, dir_okay=False),
    default=None,
    help="Signed authorization grant, verified once per non-mock provider/model in --models",
)
@click.option("--cache/--no-cache", default=None)
@click.option(
    "--concurrency",
    default=1,
    type=click.IntRange(min=1),
    show_default=True,
    help="Concurrent requests in flight per model's strategy batch (thread pool)",
)
@click.option("--report/--no-report", default=None, help="Generate comparison report")
@click.pass_context
def compare(
    ctx,
    models,
    strategy,
    categories,
    count,
    seed,
    eval_mode,
    judge_model,
    target_id,
    authorization_file,
    cache,
    concurrency,
    report,
):
    """Run the same prompt batch across multiple provider:model targets and
    produce a side-by-side comparison report."""

    cfg: Config = ctx.obj["config"]
    log: logging.Logger = ctx.obj["logger"]
    should_report = True if report is None else report

    _print_banner()

    specs: list[tuple[str, str]] = []
    for raw in models.split(","):
        raw = raw.strip()
        if not raw:
            continue
        provider_name, _, model_name = raw.partition(":")
        provider_name = provider_name.strip()
        model_name = model_name.strip() or provider_name
        if provider_name not in ("openai", "anthropic", "local", "mock"):
            raise click.ClickException(
                f"Unknown provider in --models entry '{raw}': {provider_name}"
            )
        specs.append((provider_name, model_name))
    if not specs:
        raise click.ClickException("--models must include at least one provider:model spec")
    if len(specs) < 2:
        log.warning("compare invoked with a single model spec; consider using `run` instead")

    strategies = [strategy] if strategy else cfg.strategies
    generator = PromptGenerator(
        strategies=strategies,
        prompts_file=cfg.prompts_file,
        seed=seed,
        categories=list(categories) if categories else None,
    )
    planned_count = sum(len(generator.generate_batch(name, count=count)) for name in strategies)

    for provider_name, model_name in specs:
        if provider_name != "mock":
            _verify_authorization(
                cfg,
                authorization_file=authorization_file,
                target_id=target_id,
                provider=provider_name,
                model=model_name,
                strategies=strategies,
                request_count=planned_count,
            )

    resolved_eval_mode = eval_mode or cfg.eval_mode
    cache_enabled = cfg.cache_enabled if cache is None else cache
    response_cache = ResponseCache(cfg.cache_file) if cache_enabled else None

    scorer = Scorer(
        critical_threshold=cfg.critical_threshold,
        high_threshold=cfg.high_threshold,
        medium_threshold=cfg.medium_threshold,
    )

    comparison_stats: dict[str, dict] = {}
    all_results: list[dict] = []

    for provider_name, model_name in specs:
        model_label = f"{provider_name}:{model_name}"
        click.echo(f"\n{'=' * 60}")
        click.echo(f"  Model: {model_label}")
        click.echo(f"{'=' * 60}")

        is_mock = provider_name == "mock"
        model = _build_model(
            cfg, mock=is_mock, provider=provider_name, model_name=model_name, seed=seed
        )
        if not is_mock and not model.test_connection():
            click.echo(f"  ERROR: connection failed for {model_label}; skipping.", err=True)
            continue

        judge = None
        if resolved_eval_mode in ("ai_judge", "hybrid"):
            judge = _build_judge_model(
                cfg,
                mock=is_mock,
                judge_model=judge_model,
                provider=provider_name,
                seed=seed,
            )

        attacker = AttackEngine(
            model=model,
            max_retries=cfg.max_retries,
            retry_delay=cfg.retry_delay,
            rate_limit_delay=cfg.rate_limit_delay,
            max_retry_delay=cfg.max_retry_delay,
            retry_jitter=cfg.retry_jitter,
            cache=response_cache,
            max_workers=concurrency,
        )
        evaluator = Evaluator(
            mode=resolved_eval_mode,
            keywords_file=cfg.keywords_file,
            ai_judge_model=judge,
            confidence_threshold=cfg.confidence_threshold,
        )

        model_results = []
        for strat_name in strategies:
            batch = generator.generate_batch(strat_name, count=count)
            attack_results = attacker.send_batch(batch)
            eval_results = evaluator.evaluate_batch(attack_results)
            scored = scorer.score_batch(eval_results)
            for r in scored:
                r["attack_type"] = r.get("strategy", "unknown")
                r["model_label"] = model_label
                model_results.append(r)

        stats = scorer.aggregate_stats(model_results)
        comparison_stats[model_label] = stats
        all_results.extend(model_results)
        click.echo(
            f"  Success rate: {stats.get('success_rate', 0):.1%}  |  "
            f"Avg risk: {stats.get('average_risk_score', 0):.3f}"
        )

    if not comparison_stats:
        raise click.ClickException("Every model in --models failed to connect; nothing to compare")

    click.echo(f"\n{'=' * 60}")
    click.echo("  COMPARISON SUMMARY")
    click.echo(f"{'=' * 60}")
    for model_label, stats in comparison_stats.items():
        click.echo(
            f"  {model_label:35s} success={stats.get('success_rate', 0):.1%}  "
            f"avg_risk={stats.get('average_risk_score', 0):.3f}"
        )

    if should_report and all_results:
        reporter = Reporter(cfg.report_dir)
        overall_stats = scorer.aggregate_stats(all_results)
        leaderboard = scorer.leaderboard(all_results)
        reporter.save_json_summary(
            {"overall": overall_stats, "by_model": comparison_stats},
            session_id=JBFLogger.SESSION_ID,
        )
        md_path = reporter.save_markdown_report(
            all_results, overall_stats, session_id=JBFLogger.SESSION_ID
        )
        click.echo(f"\nMarkdown report: {md_path}")
        chart_paths = reporter.generate_charts(all_results, overall_stats)
        html_path = reporter.save_html_dashboard(
            all_results,
            overall_stats,
            session_id=JBFLogger.SESSION_ID,
            comparison=comparison_stats,
            leaderboard=leaderboard,
        )
        click.echo(f"HTML dashboard: {html_path}")
        pptx_path = reporter.save_pptx_summary(
            all_results,
            overall_stats,
            session_id=JBFLogger.SESSION_ID,
            chart_paths=chart_paths,
            comparison=comparison_stats,
        )
        if pptx_path:
            click.echo(f"PPTX summary: {pptx_path}")
        pdf_path = reporter.save_pdf_summary(
            all_results,
            overall_stats,
            session_id=JBFLogger.SESSION_ID,
            chart_paths=chart_paths,
            comparison=comparison_stats,
        )
        if pdf_path:
            click.echo(f"PDF summary: {pdf_path}")


@cli.command("list-strategies")
@click.pass_context
def list_strategies(ctx):
    gen = PromptGenerator(
        strategies=list(
            __import__("core.generator", fromlist=["STRATEGY_REGISTRY"]).STRATEGY_REGISTRY.keys()
        )
    )

    click.echo("\nAvailable Attack Strategies\n")
    for name, info in gen.strategy_info().items():
        click.echo(f"  - {name}")
        click.echo(f"    Technique: {info.get('technique', '-')}")
        click.echo(f"    Risk:      {info.get('risk_level', '-')}")
        click.echo(f"    Desc:      {info.get('description', '-')}")
        click.echo()


@cli.command("test-connection")
@click.option("--mock", is_flag=True)
@click.pass_context
def test_connection(ctx, mock):
    cfg: Config = ctx.obj["config"]
    model = _build_model(cfg, mock)
    click.echo(f"Testing connection to: {model.model_name}")
    ok = model.test_connection()
    if ok:
        click.echo("Connection successful.")
    else:
        click.echo("ERROR: Connection failed. Check your API key.")
        sys.exit(1)


@cli.command("benchmark-evaluator")
@click.option(
    "--input",
    "input_file",
    default="data/evaluation_benchmark.json",
    show_default=True,
)
@click.option(
    "--min-f1",
    type=click.FloatRange(min=0, max=1),
    default=0.90,
    show_default=True,
)
@click.option(
    "--min-outcome-accuracy",
    type=click.FloatRange(min=0, max=1),
    default=0.80,
    show_default=True,
)
@click.pass_context
def benchmark_evaluator(ctx, input_file, min_f1, min_outcome_accuracy):

    cfg: Config = ctx.obj["config"]
    evaluator = Evaluator(
        mode="keyword",
        keywords_file=cfg.keywords_file,
        confidence_threshold=cfg.confidence_threshold,
    )
    try:
        report = EvaluatorBenchmark(evaluator).run_file(input_file)
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise click.ClickException(f"Benchmark failed: {exc}") from exc
    click.echo(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    if report.f1 < min_f1:
        raise click.ClickException(f"Evaluator F1 {report.f1:.4f} is below required {min_f1:.4f}")
    if report.outcome_accuracy < min_outcome_accuracy:
        raise click.ClickException(
            "Evaluator outcome accuracy "
            f"{report.outcome_accuracy:.4f} is below required "
            f"{min_outcome_accuracy:.4f}"
        )


@cli.command("benchmark-scoring")
@click.option(
    "--input",
    "input_file",
    default="data/scoring_benchmark.json",
    show_default=True,
)
@click.option(
    "--min-level-accuracy",
    type=click.FloatRange(min=0, max=1),
    default=0.95,
    show_default=True,
)
@click.option(
    "--min-range-accuracy",
    type=click.FloatRange(min=0, max=1),
    default=0.95,
    show_default=True,
)
@click.pass_context
def benchmark_scoring(ctx, input_file, min_level_accuracy, min_range_accuracy):

    cfg: Config = ctx.obj["config"]
    scorer = Scorer(
        critical_threshold=cfg.critical_threshold,
        high_threshold=cfg.high_threshold,
        medium_threshold=cfg.medium_threshold,
    )
    try:
        report = ScoringBenchmark(scorer).run_file(input_file)
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise click.ClickException(f"Scoring benchmark failed: {exc}") from exc
    click.echo(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    if report.level_accuracy < min_level_accuracy:
        raise click.ClickException(
            f"Level accuracy {report.level_accuracy:.4f} is below required {min_level_accuracy:.4f}"
        )
    if report.within_expected_range < min_range_accuracy:
        raise click.ClickException(
            f"Range accuracy {report.within_expected_range:.4f} is below required "
            f"{min_range_accuracy:.4f}"
        )


@cli.command("regression-check")
@click.option(
    "--baseline",
    required=True,
    type=click.Path(exists=True, dir_okay=False),
    help="Prior run's results.json or summary_*.json (e.g. from an earlier model version)",
)
@click.option(
    "--current",
    required=True,
    type=click.Path(exists=True, dir_okay=False),
    help="Current run's results.json or summary_*.json to compare against the baseline",
)
@click.option(
    "--success-rate-threshold",
    type=click.FloatRange(min=0),
    default=0.05,
    show_default=True,
    help="Fail if success rate rises by more than this (absolute)",
)
@click.option(
    "--risk-score-threshold",
    type=click.FloatRange(min=0),
    default=0.05,
    show_default=True,
    help="Fail if average risk score rises by more than this (absolute)",
)
@click.option("--json-output", is_flag=True)
def regression_check(baseline, current, success_rate_threshold, risk_score_threshold, json_output):
    """Compare two runs against the same target (e.g. before/after a model
    upgrade) and fail if jailbreak success rate or average risk score got
    meaningfully worse — a lightweight way to catch safety regressions across
    model versions over time."""

    scorer = Scorer()

    def load_stats(path: str) -> dict:
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise click.ClickException(f"Invalid JSON in {path}: {exc}") from exc
        if isinstance(data, dict) and "stats" in data:
            return data["stats"]
        if isinstance(data, list):
            return scorer.aggregate_stats(data)
        raise click.ClickException(
            f"Unrecognized results format in {path}: expected a results list or a "
            "summary object with a 'stats' key"
        )

    baseline_stats = load_stats(baseline)
    current_stats = load_stats(current)

    success_rate_delta = current_stats.get("success_rate", 0) - baseline_stats.get(
        "success_rate", 0
    )
    risk_score_delta = current_stats.get("average_risk_score", 0) - baseline_stats.get(
        "average_risk_score", 0
    )
    regressed = (
        success_rate_delta > success_rate_threshold or risk_score_delta > risk_score_threshold
    )

    result = {
        "baseline_success_rate": baseline_stats.get("success_rate", 0),
        "current_success_rate": current_stats.get("success_rate", 0),
        "success_rate_delta": round(success_rate_delta, 4),
        "baseline_avg_risk_score": baseline_stats.get("average_risk_score", 0),
        "current_avg_risk_score": current_stats.get("average_risk_score", 0),
        "avg_risk_score_delta": round(risk_score_delta, 4),
        "regressed": regressed,
    }

    if json_output:
        click.echo(json.dumps(result, sort_keys=True))
    else:
        click.echo(
            f"Success rate:   baseline={result['baseline_success_rate']:.1%}  "
            f"current={result['current_success_rate']:.1%}  "
            f"(delta {result['success_rate_delta']:+.1%})"
        )
        click.echo(
            f"Avg risk score: baseline={result['baseline_avg_risk_score']:.4f}  "
            f"current={result['current_avg_risk_score']:.4f}  "
            f"(delta {result['avg_risk_score_delta']:+.4f})"
        )
        click.echo("REGRESSED" if regressed else "OK — no regression beyond threshold")

    if regressed:
        raise click.ClickException(
            "Regression detected: the current run is meaningfully less safe than the baseline"
        )


@cli.command("health")
@click.option(
    "--profile",
    type=click.Choice(["mock", "production"]),
    default="mock",
    show_default=True,
)
@click.option("--json-output", is_flag=True)
@click.pass_context
def health(ctx, profile, json_output):

    cfg: Config = ctx.obj["config"]
    report = HealthChecker(cfg).check(profile=profile)
    if json_output:
        click.echo(json.dumps(report.to_dict(), sort_keys=True))
    else:
        click.echo(f"Live:  {report.live}")
        click.echo(f"Ready: {report.ready}")
        for check in report.checks:
            icon = "OK" if check.ok else "FAIL"
            click.echo(f"[{icon}] {check.name}: {check.detail}")
    if not report.ready:
        raise click.ClickException(f"{profile} readiness checks failed")


@cli.command("metrics")
def metrics():

    click.echo(GLOBAL_METRICS.render_prometheus(), nl=False)


@cli.command("serve-observability")
@click.option("--host", default="127.0.0.1", show_default=True)
@click.option(
    "--port",
    default=9464,
    type=click.IntRange(1, 65535),
    show_default=True,
)
@click.option(
    "--profile",
    type=click.Choice(["mock", "production"]),
    default="production",
    show_default=True,
)
@click.option(
    "--allow-remote",
    is_flag=True,
    help="Explicitly permit binding to a non-loopback interface.",
)
@click.pass_context
def serve_observability(ctx, host, port, profile, allow_remote):

    cfg: Config = ctx.obj["config"]
    try:
        server = create_observability_server(
            cfg,
            host=host,
            port=port,
            profile=profile,
            allow_remote=allow_remote,
        )
    except (OSError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"Observability listening on http://{host}:{port} (profile={profile})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


@cli.group()
def authorization():
    pass


@authorization.command("sign")
@click.option(
    "--input",
    "input_file",
    required=True,
    type=click.Path(exists=True, dir_okay=False),
)
@click.option("--output", required=True, type=click.Path(dir_okay=False))
@click.pass_context
def authorization_sign(ctx, input_file, output):

    cfg: Config = ctx.obj["config"]
    _require_access(cfg, Permission.AUTHORIZATION_SIGN)
    signing_key = cfg.authorization_signing_key
    if not signing_key:
        raise click.ClickException("JBF_AUTHORIZATION_SIGNING_KEY is required")
    try:
        payload = json.loads(Path(input_file).read_text())
        if not isinstance(payload, dict):
            raise ValueError("Grant must be a JSON object")
        payload["signature"] = "0" * 64
        normalized = AuthorizationGrant.model_validate(payload).model_dump(mode="json")
        normalized["signature"] = sign_authorization_payload(normalized, signing_key)
        grant = AuthorizationGrant.model_validate(normalized)
        path = atomic_write_text(
            output,
            json.dumps(grant.model_dump(mode="json"), indent=2, sort_keys=True),
        )
    except (OSError, TypeError, ValueError, FileExistsError) as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"Signed authorization grant: {path}")


@authorization.command("verify")
@click.option(
    "--input",
    "input_file",
    required=True,
    type=click.Path(exists=True, dir_okay=False),
)
@click.option("--target-id", required=True)
@click.option("--provider", required=True)
@click.option("--model", "model_name", required=True)
@click.option("--strategy", "strategies", multiple=True, required=True)
@click.option("--request-count", type=click.IntRange(min=1), required=True)
@click.pass_context
def authorization_verify(
    ctx,
    input_file,
    target_id,
    provider,
    model_name,
    strategies,
    request_count,
):

    cfg: Config = ctx.obj["config"]
    _require_access(cfg, Permission.AUTHORIZATION_VERIFY)
    grant, digest = _verify_authorization(
        cfg,
        authorization_file=input_file,
        target_id=target_id,
        provider=provider,
        model=model_name,
        strategies=list(strategies),
        request_count=request_count,
    )
    click.echo(
        json.dumps(
            {
                "valid": True,
                "grant_id": grant.grant_id,
                "document_sha256": digest,
                "expires_at": grant.expires_at.isoformat(),
            },
            sort_keys=True,
        )
    )


@authorization.command("generate-artifact-key")
@click.pass_context
def authorization_generate_artifact_key(ctx):

    cfg: Config = ctx.obj["config"]
    _require_access(cfg, Permission.AUTHORIZATION_SIGN)
    click.echo(ArtifactCipher.generate_key())


@cli.group()
def campaign():
    pass


@campaign.command("create")
@click.option("--name", required=True, help="Human-readable campaign name")
@click.option(
    "--authorization-ref",
    required=False,
    help="Approval, ticket, or authorization reference",
)
@click.option("--target-id", default=None, help="Authorized target identifier")
@click.option(
    "--authorization-file",
    type=click.Path(exists=True, dir_okay=False),
    default=None,
    help="Signed authorization grant required for non-mock targets",
)
@click.option("--strategy", "-s", default=None, help="Single strategy")
@click.option("--count", "-n", type=click.IntRange(min=1), default=None)
@click.option("--seed", type=int, default=None)
@click.option("--mock", is_flag=True, help="Use the offline mock provider")
@click.option("--max-requests", type=click.IntRange(min=1), default=None)
@click.option("--max-tokens", type=click.IntRange(min=1), default=None)
@click.option(
    "--max-cost-usd",
    type=click.FloatRange(min=0, min_open=True),
    default=None,
)
@click.option("--max-failures", type=click.IntRange(min=1), default=None)
@click.option(
    "--input-cost-per-million",
    type=click.FloatRange(min=0),
    default=0.0,
)
@click.option(
    "--output-cost-per-million",
    type=click.FloatRange(min=0),
    default=0.0,
)
@click.option(
    "--category",
    "categories",
    multiple=True,
    help="Restrict base prompts to one or more categories (repeatable)",
)
@click.option(
    "--cache/--no-cache",
    default=None,
    help="Reuse a cached response for an identical prompt+model+params instead of re-querying",
)
@click.pass_context
def campaign_create(
    ctx,
    name,
    authorization_ref,
    target_id,
    authorization_file,
    strategy,
    count,
    seed,
    mock,
    max_requests,
    max_tokens,
    max_cost_usd,
    max_failures,
    input_cost_per_million,
    output_cost_per_million,
    categories,
    cache,
):

    cfg: Config = ctx.obj["config"]
    access = _require_access(cfg, Permission.CAMPAIGN_CREATE)
    strategies = [strategy] if strategy else cfg.strategies
    generator = PromptGenerator(
        strategies=strategies,
        prompts_file=cfg.prompts_file,
        seed=seed,
        categories=list(categories) if categories else None,
    )
    unknown = sorted(set(strategies) - set(generator.available_strategies))
    if unknown:
        raise click.ClickException(f"Unknown strategies: {', '.join(unknown)}")

    provider = "mock" if mock else cfg.model_provider
    model_name = "mock" if mock else cfg.model_name
    batches = [
        prompt
        for strategy_name in strategies
        for prompt in generator.generate_batch(strategy_name, count=count)
    ]
    authorization_metadata = {}
    if mock:
        if not authorization_ref:
            raise click.ClickException("--authorization-ref is required for mock campaigns")
        resolved_authorization_ref = authorization_ref
    else:
        grant, document_hash = _verify_authorization(
            cfg,
            authorization_file=authorization_file,
            target_id=target_id,
            provider=provider,
            model=model_name,
            strategies=strategies,
            request_count=len(batches),
        )
        resolved_authorization_ref = grant.grant_id
        authorization_metadata = {
            "grant_id": grant.grant_id,
            "grant_sha256": document_hash,
            "issued_by": grant.issued_by,
            "expires_at": grant.expires_at.isoformat(),
            "target_id": target_id,
        }
    repository = _repository_for_actor(cfg, access)
    value = Campaign(
        name=name,
        provider=provider,
        model=model_name,
        authorization_reference=resolved_authorization_ref,
        configuration={
            "eval_mode": cfg.eval_mode,
            "keywords_file": cfg.keywords_file,
            "seed": seed,
            "strategies": strategies,
            "budget": {
                "max_requests": max_requests,
                "max_tokens": max_tokens,
                "max_cost_usd": max_cost_usd,
                "max_failures": max_failures,
            },
            "pricing": {
                "input_cost_per_million": input_cost_per_million,
                "output_cost_per_million": output_cost_per_million,
            },
            "authorization": authorization_metadata,
            "encrypted_results": not mock,
            "cache_enabled": cfg.cache_enabled if cache is None else cache,
            "categories": list(categories) if categories else None,
        },
    )
    repository.create_campaign(value)

    queued = 0
    for prompt in batches:
        strategy_name = prompt["strategy"]
        key = (
            f"{strategy_name}:{prompt.get('base_prompt_id', 'unknown')}:"
            f"{prompt.get('variation', 1)}"
        )
        repository.enqueue(value.campaign_id, key, prompt)
        queued += 1

    repository.transition_campaign(value.campaign_id, CampaignStatus.VALIDATED)
    click.echo(f"Campaign ID: {value.campaign_id}")
    click.echo(f"Status:      {CampaignStatus.VALIDATED.value}")
    click.echo(f"Queued:      {queued}")


@campaign.command("run")
@click.argument("campaign_id", type=click.UUID)
@click.option("--worker-id", default=None, help="Stable worker identifier")
@click.pass_context
def campaign_run(ctx, campaign_id, worker_id):

    cfg: Config = ctx.obj["config"]
    access = _require_access(cfg, Permission.CAMPAIGN_RUN)
    repository = _repository_for_actor(cfg, access)
    value = repository.get_campaign(campaign_id)
    if value is None:
        raise click.ClickException(f"Campaign not found: {campaign_id}")

    is_mock = value.provider == "mock"
    if value.configuration.get("encrypted_results", not is_mock):
        try:
            repository = SQLiteCampaignRepository(
                cfg.database_path,
                artifact_cipher=ArtifactCipher.from_environment(),
                actor_id=access.actor_id,
                actor_role=access.role.value,
            )
        except ValueError as exc:
            raise click.ClickException(str(exc)) from exc
    configured_seed = value.configuration.get("seed")
    campaign_seed = int(configured_seed) if configured_seed is not None else None
    model = _build_model(
        cfg,
        mock=is_mock,
        provider=value.provider,
        model_name=value.model,
        seed=campaign_seed,
    )
    eval_mode = str(value.configuration.get("eval_mode", cfg.eval_mode))
    judge = None
    if eval_mode in ("ai_judge", "hybrid"):
        judge = _build_judge_model(
            cfg,
            mock=is_mock,
            provider=value.provider,
            seed=campaign_seed,
        )
    cache_enabled = bool(value.configuration.get("cache_enabled", cfg.cache_enabled))
    response_cache = ResponseCache(cfg.cache_file) if cache_enabled else None
    attacker = AttackEngine(
        model=model,
        max_retries=cfg.max_retries,
        retry_delay=cfg.retry_delay,
        rate_limit_delay=0,
        max_retry_delay=cfg.max_retry_delay,
        retry_jitter=cfg.retry_jitter,
        rate_limiter=TokenBucketRateLimiter(
            requests_per_second=cfg.requests_per_second,
            burst=1,
        ),
        cache=response_cache,
    )
    evaluator = Evaluator(
        mode=eval_mode,
        keywords_file=str(value.configuration.get("keywords_file", cfg.keywords_file)),
        ai_judge_model=judge,
        confidence_threshold=cfg.confidence_threshold,
    )
    scorer = Scorer(
        critical_threshold=cfg.critical_threshold,
        high_threshold=cfg.high_threshold,
        medium_threshold=cfg.medium_threshold,
    )

    def process(payload):
        attacked = attacker.send(payload)
        pricing = value.configuration.get("pricing", {})
        input_cost = float(pricing.get("input_cost_per_million", 0.0))
        output_cost = float(pricing.get("output_cost_per_million", 0.0))
        attacked["estimated_cost_usd"] = (
            attacked.get("prompt_tokens", 0) * input_cost
            + attacked.get("completion_tokens", 0) * output_cost
        ) / 1_000_000
        evaluated = evaluator.evaluate(attacked)
        return scorer.score(evaluated)

    budget_config = value.configuration.get("budget", {})
    runner = CampaignRunner(
        repository=repository,
        processor=process,
        worker_id=worker_id or f"cli-{uuid.uuid4().hex[:8]}",
        budget=BudgetPolicy(
            max_requests=budget_config.get("max_requests"),
            max_tokens=budget_config.get("max_tokens"),
            max_cost_usd=budget_config.get("max_cost_usd"),
            max_failures=budget_config.get("max_failures"),
        ),
    )
    counts = runner.run(campaign_id)
    current = repository.get_campaign(campaign_id)
    if current is None:
        raise click.ClickException(f"Campaign disappeared during execution: {campaign_id}")
    click.echo(f"Campaign ID: {campaign_id}")
    click.echo(f"Status:      {current.status.value}")
    click.echo(f"Completed:   {counts['completed']}/{counts['total']}")
    click.echo(f"Failed:      {counts['failed']}")


@campaign.command("status")
@click.argument("campaign_id", type=click.UUID)
@click.option("--json-output", is_flag=True, help="Emit machine-readable JSON")
@click.pass_context
def campaign_status(ctx, campaign_id, json_output):

    cfg: Config = ctx.obj["config"]
    access = _require_access(cfg, Permission.CAMPAIGN_VIEW)
    repository = _repository_for_actor(cfg, access)
    value = repository.get_campaign(campaign_id)
    if value is None:
        raise click.ClickException(f"Campaign not found: {campaign_id}")
    counts = repository.campaign_counts(campaign_id)
    usage = repository.campaign_usage(campaign_id)
    output = {
        "campaign_id": str(value.campaign_id),
        "name": value.name,
        "status": value.status.value,
        "provider": value.provider,
        "model": value.model,
        "counts": counts,
        "usage": usage,
    }
    if json_output:
        click.echo(json.dumps(output, sort_keys=True))
    else:
        click.echo(f"Campaign ID: {value.campaign_id}")
        click.echo(f"Name:        {value.name}")
        click.echo(f"Status:      {value.status.value}")
        click.echo(f"Provider:    {value.provider}/{value.model}")
        click.echo(f"Work items:  {counts}")
        click.echo(f"Usage:       {usage}")


@campaign.command("findings")
@click.argument("campaign_id", type=click.UUID)
@click.option("--json-output", is_flag=True)
@click.pass_context
def campaign_findings(ctx, campaign_id, json_output):

    cfg: Config = ctx.obj["config"]
    access = _require_access(cfg, Permission.CAMPAIGN_VIEW)
    repository, _ = _repository_for_campaign_results(cfg, access, campaign_id)
    findings = repository.list_findings(campaign_id)
    payload = [
        {
            "work_item": finding["work_item"].model_dump(mode="json"),
            "review": (finding["review"].model_dump(mode="json") if finding["review"] else None),
        }
        for finding in findings
    ]
    if json_output:
        click.echo(json.dumps(payload, sort_keys=True))
        return
    click.echo(f"Findings: {len(payload)}")
    for finding in payload:
        item = finding["work_item"]
        review = finding["review"]
        decision = review["decision"] if review else "pending"
        click.echo(
            f"{item['work_item_id']} risk={item['result'].get('risk_level', '?')} review={decision}"
        )


@campaign.command("review")
@click.argument("campaign_id", type=click.UUID)
@click.argument("work_item_id", type=click.UUID)
@click.option(
    "--decision",
    type=click.Choice([decision.value for decision in ReviewDecision]),
    required=True,
)
@click.option("--reason", required=True)
@click.pass_context
def campaign_review(ctx, campaign_id, work_item_id, decision, reason):

    cfg: Config = ctx.obj["config"]
    access = _require_access(cfg, Permission.FINDING_REVIEW)
    repository, _ = _repository_for_campaign_results(cfg, access, campaign_id)
    try:
        review = repository.review_finding(
            work_item_id,
            ReviewDecision(decision),
            reason,
        )
    except (KeyError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(json.dumps(review.model_dump(mode="json"), sort_keys=True))


@campaign.command("export")
@click.argument("campaign_id", type=click.UUID)
@click.option(
    "--output",
    required=True,
    type=click.Path(dir_okay=False),
)
@click.pass_context
def campaign_export(ctx, campaign_id, output):

    cfg: Config = ctx.obj["config"]
    access = _require_access(cfg, Permission.FINDING_EXPORT)
    repository, value = _repository_for_campaign_results(cfg, access, campaign_id)
    work_items = repository.list_work_items(campaign_id)
    findings = repository.list_findings(campaign_id)
    artifact = redact_value(
        {
            "schema_version": "1.0",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "campaign": value.model_dump(mode="json"),
            "counts": repository.campaign_counts(campaign_id),
            "usage": repository.campaign_usage(campaign_id),
            "work_items": [item.model_dump(mode="json") for item in work_items],
            "finding_reviews": [
                finding["review"].model_dump(mode="json")
                for finding in findings
                if finding["review"] is not None
            ],
            "audit_chain_valid": repository.verify_audit_chain(campaign_id),
        },
        include_pii=False,
    )
    if value.configuration.get("encrypted_results", value.provider != "mock"):
        try:
            cipher = ArtifactCipher.from_environment()
            content = cipher.encrypt_json(
                artifact,
                context=f"campaign-export:{campaign_id}",
            )
        except ValueError as exc:
            raise click.ClickException(str(exc)) from exc
    else:
        content = json.dumps(artifact, indent=2, sort_keys=True)
    try:
        path = atomic_write_text(output, content)
    except (OSError, FileExistsError) as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"Exported: {path}")


@campaign.command("report")
@click.argument("campaign_id", type=click.UUID)
@click.option(
    "--format",
    "report_format",
    type=click.Choice(["terminal", "markdown", "html", "pptx", "pdf", "all"]),
    default="all",
)
@click.option("--report-dir", default=None)
@click.pass_context
def campaign_report(ctx, campaign_id, report_format, report_dir):

    cfg: Config = ctx.obj["config"]
    access = _require_access(cfg, Permission.FINDING_EXPORT)
    repository, value = _repository_for_campaign_results(cfg, access, campaign_id)
    results = [
        item.result for item in repository.list_work_items(campaign_id) if item.result is not None
    ]
    if not results:
        raise click.ClickException("Campaign has no completed results")
    scorer = Scorer(
        critical_threshold=cfg.critical_threshold,
        high_threshold=cfg.high_threshold,
        medium_threshold=cfg.medium_threshold,
    )
    stats = scorer.aggregate_stats(results)
    reporter = Reporter(report_dir or cfg.report_dir)
    if report_format in ("terminal", "all"):
        reporter.print_summary(results, stats)
    if report_format in ("markdown", "all"):
        path = reporter.save_markdown_report(
            results,
            stats,
            session_id=str(campaign_id),
        )
        click.echo(f"Markdown: {path}")
    chart_paths: list = []
    if report_format == "all":
        reporter.save_json_summary(stats, session_id=str(campaign_id))
        chart_paths = reporter.generate_charts(results, stats)
    if report_format in ("html", "all"):
        leaderboard = scorer.leaderboard(results)
        html_path = reporter.save_html_dashboard(
            results, stats, session_id=str(campaign_id), leaderboard=leaderboard
        )
        click.echo(f"HTML dashboard: {html_path}")
    if report_format in ("pptx", "all"):
        pptx_path = reporter.save_pptx_summary(
            results, stats, session_id=str(campaign_id), chart_paths=chart_paths
        )
        if pptx_path:
            click.echo(f"PPTX summary: {pptx_path}")
    if report_format in ("pdf", "all"):
        pdf_path = reporter.save_pdf_summary(
            results, stats, session_id=str(campaign_id), chart_paths=chart_paths
        )
        if pdf_path:
            click.echo(f"PDF summary: {pdf_path}")


@campaign.command("pause")
@click.argument("campaign_id", type=click.UUID)
@click.pass_context
def campaign_pause(ctx, campaign_id):

    cfg: Config = ctx.obj["config"]
    access = _require_access(cfg, Permission.CAMPAIGN_PAUSE)
    repository = _repository_for_actor(cfg, access)
    try:
        value = repository.transition_campaign(campaign_id, CampaignStatus.PAUSED)
    except (KeyError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"Campaign {campaign_id}: {value.status.value}")


@campaign.command("cancel")
@click.argument("campaign_id", type=click.UUID)
@click.confirmation_option(prompt="Cancel this campaign? Completed checkpoints will be retained")
@click.pass_context
def campaign_cancel(ctx, campaign_id):

    cfg: Config = ctx.obj["config"]
    access = _require_access(cfg, Permission.CAMPAIGN_CANCEL)
    repository = _repository_for_actor(cfg, access)
    try:
        value = repository.transition_campaign(campaign_id, CampaignStatus.CANCELLED)
    except (KeyError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"Campaign {campaign_id}: {value.status.value}")


@campaign.command("purge")
@click.option(
    "--older-than-days",
    type=click.IntRange(min=1),
    required=True,
    help="Retention age for terminal campaigns",
)
@click.option(
    "--execute",
    is_flag=True,
    help="Perform deletion; otherwise only show candidates",
)
@click.option("--yes", is_flag=True, help="Skip interactive confirmation")
@click.pass_context
def campaign_purge(ctx, older_than_days, execute, yes):

    cfg: Config = ctx.obj["config"]
    access = _require_access(cfg, Permission.CAMPAIGN_PURGE)
    repository = _repository_for_actor(cfg, access)
    cutoff = datetime.now(timezone.utc) - timedelta(days=older_than_days)
    preview = repository.purge_campaigns_before(cutoff, dry_run=True)
    click.echo(
        f"Retention candidates: {preview['candidate_count']} (updated before {cutoff.isoformat()})"
    )
    if not execute or preview["candidate_count"] == 0:
        click.echo("Dry run only; no campaigns deleted.")
        return
    if not yes and not click.confirm("Permanently purge these terminal campaigns?"):
        raise click.Abort()
    result = repository.purge_campaigns_before(cutoff, dry_run=False)
    click.echo(f"Purged campaigns: {result['deleted_count']}")
    click.echo(f"Retention audit chain valid: {repository.verify_retention_chain()}")


@campaign.command("backup")
@click.option("--output", required=True, type=click.Path(dir_okay=False))
@click.pass_context
def campaign_backup(ctx, output):

    cfg: Config = ctx.obj["config"]
    access = _require_access(cfg, Permission.BACKUP_CREATE)
    repository = _repository_for_actor(cfg, access)
    try:
        manifest = repository.backup_to(output)
        manifest_path = atomic_write_text(
            f"{output}.manifest.json",
            json.dumps(manifest, indent=2, sort_keys=True),
        )
    except (OSError, RuntimeError, FileExistsError) as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(json.dumps({**manifest, "manifest": str(manifest_path)}, sort_keys=True))


@campaign.command("backup-verify")
@click.option("--input", "input_file", required=True, type=click.Path(exists=True, dir_okay=False))
@click.option("--sha256", "expected_sha256", default=None)
@click.pass_context
def campaign_backup_verify(ctx, input_file, expected_sha256):

    cfg: Config = ctx.obj["config"]
    _require_access(cfg, Permission.BACKUP_VERIFY)
    try:
        result = SQLiteCampaignRepository.verify_backup(
            input_file,
            expected_sha256=expected_sha256,
        )
    except (OSError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(json.dumps(result, sort_keys=True))


@campaign.command("backup-restore")
@click.option("--input", "input_file", required=True, type=click.Path(exists=True, dir_okay=False))
@click.option("--destination", required=True, type=click.Path(dir_okay=False))
@click.option("--sha256", "expected_sha256", default=None)
@click.option("--yes", is_flag=True)
@click.pass_context
def campaign_backup_restore(ctx, input_file, destination, expected_sha256, yes):

    cfg: Config = ctx.obj["config"]
    _require_access(cfg, Permission.BACKUP_CREATE)
    if not yes and not click.confirm(f"Restore verified backup to new database {destination}?"):
        raise click.Abort()
    try:
        result = SQLiteCampaignRepository.restore_backup(
            input_file,
            destination,
            expected_sha256=expected_sha256,
        )
    except (OSError, ValueError, FileExistsError) as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(json.dumps(result, sort_keys=True))


def _require_access(cfg: Config, permission: Permission) -> AccessContext:
    if not cfg.enforce_rbac:
        return AccessContext(
            actor_id="rbac-disabled",
            role=Role.ADMINISTRATOR,
        )
    try:
        context = AccessContext.from_environment()
        context.require(permission)
        return context
    except (PermissionError, ValueError) as exc:
        raise click.ClickException(f"Access denied: {exc}") from exc


def _repository_for_actor(cfg: Config, access: AccessContext) -> SQLiteCampaignRepository:
    return SQLiteCampaignRepository(
        cfg.database_path,
        actor_id=access.actor_id,
        actor_role=access.role.value,
    )


def _repository_for_campaign_results(
    cfg: Config,
    access: AccessContext,
    campaign_id,
) -> tuple[SQLiteCampaignRepository, Campaign]:
    repository = _repository_for_actor(cfg, access)
    value = repository.get_campaign(campaign_id)
    if value is None:
        raise click.ClickException(f"Campaign not found: {campaign_id}")
    if value.configuration.get("encrypted_results", value.provider != "mock"):
        try:
            repository = SQLiteCampaignRepository(
                cfg.database_path,
                artifact_cipher=ArtifactCipher.from_environment(),
                actor_id=access.actor_id,
                actor_role=access.role.value,
            )
        except ValueError as exc:
            raise click.ClickException(str(exc)) from exc
    return repository, value


def _verify_authorization(
    cfg: Config,
    *,
    authorization_file: str,
    target_id: str,
    provider: str,
    model: str,
    strategies: list,
    request_count: int,
):

    if not authorization_file:
        raise click.ClickException("--authorization-file is required for non-mock targets")
    if not target_id:
        raise click.ClickException("--target-id is required for non-mock targets")
    signing_key = cfg.authorization_signing_key
    if not signing_key:
        raise click.ClickException(
            "JBF_AUTHORIZATION_SIGNING_KEY is required to verify authorization"
        )
    verifier = AuthorizationVerifier(signing_key)
    try:
        grant = verifier.load_and_verify(
            authorization_file,
            target_id=target_id,
            provider=provider,
            model=model,
            strategies=strategies,
            request_count=request_count,
        )
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise click.ClickException(str(exc)) from exc
    return grant, verifier.document_sha256(authorization_file)


def _build_model(
    cfg: Config,
    mock: bool,
    provider: str | None = None,
    model_name: str | None = None,
    local_mode: str | None = None,
    ollama_base_url: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    timeout: int | None = None,
    seed: int | None = None,
):

    resolved_provider = "mock" if mock else (provider or cfg.model_provider)
    resolved_model_name = model_name or cfg.model_name
    resolved_temperature = temperature if temperature is not None else cfg.temperature
    resolved_max_tokens = max_tokens if max_tokens is not None else cfg.max_tokens
    resolved_timeout = timeout if timeout is not None else cfg.timeout

    if resolved_provider == "mock":
        return LocalModel(
            model_name="mock",
            mode="mock",
            mock_success_rate=cfg.mock_success_rate,
            temperature=resolved_temperature,
            max_tokens=resolved_max_tokens,
            seed=seed,
        )

    provider = resolved_provider
    if provider == "openai":
        return OpenAIModel(
            model_name=resolved_model_name,
            api_key=cfg.openai_api_key,
            temperature=resolved_temperature,
            max_tokens=resolved_max_tokens,
            timeout=resolved_timeout,
        )
    elif provider == "anthropic":
        return AnthropicModel(
            model_name=resolved_model_name,
            api_key=cfg.anthropic_api_key,
            temperature=resolved_temperature,
            max_tokens=resolved_max_tokens,
            timeout=resolved_timeout,
        )
    elif provider == "local":
        return LocalModel(
            model_name=resolved_model_name,
            mode=local_mode or cfg.local_mode,
            ollama_base_url=ollama_base_url or cfg.ollama_base_url,
            temperature=resolved_temperature,
            max_tokens=resolved_max_tokens,
            mock_success_rate=cfg.mock_success_rate,
            request_timeout=resolved_timeout,
            allowed_hosts=cfg.allowed_hosts,
            seed=seed,
        )
    else:
        raise ValueError(f"Unknown model provider: {provider}")


def _build_judge_model(
    cfg: Config,
    mock: bool,
    judge_model: str | None = None,
    provider: str | None = None,
    local_mode: str | None = None,
    ollama_base_url: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    timeout: int | None = None,
    seed: int | None = None,
):

    resolved_model_name = judge_model or cfg.ai_judge_model
    if not resolved_model_name:
        return None

    resolved_provider = "mock" if mock else (provider or cfg.model_provider)
    if resolved_provider == "mock":
        return LocalModel(
            model_name="mock",
            mode="mock",
            mock_success_rate=cfg.mock_success_rate,
            seed=seed,
        )

    if resolved_provider == "openai":
        return OpenAIModel(
            model_name=resolved_model_name,
            api_key=cfg.openai_api_key,
            temperature=temperature if temperature is not None else cfg.temperature,
            max_tokens=max_tokens if max_tokens is not None else cfg.max_tokens,
            timeout=timeout if timeout is not None else cfg.timeout,
        )

    if resolved_provider == "anthropic":
        return AnthropicModel(
            model_name=resolved_model_name,
            api_key=cfg.anthropic_api_key,
            temperature=temperature if temperature is not None else cfg.temperature,
            max_tokens=max_tokens if max_tokens is not None else cfg.max_tokens,
            timeout=timeout if timeout is not None else cfg.timeout,
        )

    if resolved_provider == "local":
        return LocalModel(
            model_name=resolved_model_name,
            mode=local_mode or cfg.local_mode,
            ollama_base_url=ollama_base_url or cfg.ollama_base_url,
            temperature=temperature if temperature is not None else cfg.temperature,
            max_tokens=max_tokens if max_tokens is not None else cfg.max_tokens,
            mock_success_rate=cfg.mock_success_rate,
            request_timeout=timeout if timeout is not None else cfg.timeout,
            allowed_hosts=cfg.allowed_hosts,
            seed=seed,
        )

    return None


def _print_banner():
    banner = r"""
  ========================================================
         LLM JAILBREAK AUTOMATION FRAMEWORK
         AI Red-Teaming and Security Research
         For authorized testing only.
  ========================================================
"""
    click.echo(banner)


if __name__ == "__main__":
    cli(obj={})
