import json
import threading
from urllib.error import HTTPError
from urllib.request import urlopen

import pytest
from click.testing import CliRunner

from main import cli
from observability.health import HealthChecker
from observability.metrics import MetricsRegistry
from observability.server import create_observability_server
from utils.config import Config
from utils.encryption import ArtifactCipher


def test_metrics_registry_renders_prometheus_format():
    registry = MetricsRegistry()
    registry.increment(
        "jbf_requests",
        labels={"provider": "mock", "status": "success"},
    )
    registry.observe(
        "jbf_latency_seconds",
        0.25,
        labels={"provider": "mock"},
    )
    registry.set_gauge("jbf_queue_depth", 3)
    rendered = registry.render_prometheus()
    assert 'jbf_requests_total{provider="mock",status="success"} 1' in rendered
    assert "jbf_latency_seconds_count" in rendered
    assert "jbf_latency_seconds_sum" in rendered
    assert "jbf_queue_depth 3" in rendered


def test_counter_rejects_negative_increment():
    registry = MetricsRegistry()
    try:
        registry.increment("invalid", amount=-1)
    except ValueError:
        pass
    else:
        raise AssertionError("negative counter increment was accepted")


def test_mock_health_is_ready(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cfg = Config(config_file="missing.yaml")
    report = HealthChecker(cfg).check("mock")
    assert report.live is True
    assert report.ready is True


def test_production_health_requires_security_keys(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("JBF_AUTHORIZATION_SIGNING_KEY", raising=False)
    monkeypatch.delenv("JBF_ARTIFACT_ENCRYPTION_KEY", raising=False)
    report = HealthChecker(Config(config_file="missing.yaml")).check("production")
    assert report.live is True
    assert report.ready is False


def test_production_health_accepts_valid_keys(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("JBF_AUTHORIZATION_SIGNING_KEY", "x" * 32)
    monkeypatch.setenv(
        "JBF_ARTIFACT_ENCRYPTION_KEY",
        ArtifactCipher.generate_key(),
    )
    report = HealthChecker(Config(config_file="missing.yaml")).check("production")
    assert report.ready is True


def test_health_cli_json(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(cli, ["--config", "missing.yaml", "health", "--json-output"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["live"] is True


def test_observability_server_exposes_health_and_metrics(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    server = create_observability_server(
        Config(config_file="missing.yaml"),
        host="127.0.0.1",
        port=0,
        profile="mock",
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_address[1]
        with urlopen(f"http://127.0.0.1:{port}/health/live") as response:
            assert json.load(response)["live"] is True
            assert response.headers["Cache-Control"] == "no-store"
        with urlopen(f"http://127.0.0.1:{port}/health/ready") as response:
            assert json.load(response)["ready"] is True
        with urlopen(f"http://127.0.0.1:{port}/metrics") as response:
            metrics = response.read().decode()
            assert "jbf_health_live 1" in metrics
            assert "jbf_health_ready 1" in metrics
        with pytest.raises(HTTPError) as error:
            urlopen(f"http://127.0.0.1:{port}/missing")
        assert error.value.code == 404
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_observability_server_rejects_remote_bind_by_default(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValueError, match="explicit allow_remote"):
        create_observability_server(
            Config(config_file="missing.yaml"),
            host="0.0.0.0",
            port=0,
            profile="mock",
        )
