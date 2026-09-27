from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from ipaddress import ip_address
from typing import Any

from observability.health import HealthChecker
from observability.metrics import GLOBAL_METRICS


def _health_metrics(report) -> str:
    lines = [
        "# HELP jbf_health_live Whether the process is live.",
        "# TYPE jbf_health_live gauge",
        f"jbf_health_live {1 if report.live else 0}",
        "# HELP jbf_health_ready Whether all readiness checks pass.",
        "# TYPE jbf_health_ready gauge",
        f"jbf_health_ready {1 if report.ready else 0}",
        "# HELP jbf_health_check Individual readiness check state.",
        "# TYPE jbf_health_check gauge",
    ]
    for check in report.checks:
        name = check.name.replace("\\", "\\\\").replace('"', '\\"')
        lines.append(f'jbf_health_check{{check="{name}"}} {1 if check.ok else 0}')
    return "\n".join(lines) + "\n"


def _handler(config: Any, profile: str):
    health_checker = HealthChecker(config)

    class Handler(BaseHTTPRequestHandler):
        server_version = "JBFObservability/1.0"
        sys_version = ""

        def do_GET(self) -> None:
            if self.path == "/health/live":
                self._json(HTTPStatus.OK, {"live": True})
                return
            if self.path == "/health/ready":
                report = health_checker.check(profile)
                self._json(
                    HTTPStatus.OK if report.ready else HTTPStatus.SERVICE_UNAVAILABLE,
                    report.to_dict(),
                )
                return
            if self.path == "/metrics":
                report = health_checker.check(profile)
                payload = _health_metrics(report) + GLOBAL_METRICS.render_prometheus()
                self._send(
                    HTTPStatus.OK,
                    payload.encode("utf-8"),
                    "text/plain; version=0.0.4; charset=utf-8",
                )
                return
            self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})

        def _json(self, status: HTTPStatus, value: dict[str, Any]) -> None:
            payload = (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode(
                "utf-8"
            )
            self._send(status, payload, "application/json; charset=utf-8")

        def _send(
            self,
            status: HTTPStatus,
            payload: bytes,
            content_type: str,
        ) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format: str, *args: Any) -> None:
            return

    return Handler


def create_observability_server(
    config: Any,
    *,
    host: str = "127.0.0.1",
    port: int = 9464,
    profile: str = "production",
    allow_remote: bool = False,
) -> ThreadingHTTPServer:
    if profile not in {"mock", "production"}:
        raise ValueError("Health profile must be mock or production")
    if not 0 <= port <= 65535:
        raise ValueError("Port must be between 0 and 65535")
    try:
        is_loopback = ip_address(host).is_loopback
    except ValueError:
        is_loopback = host.lower() == "localhost"
    if not is_loopback and not allow_remote:
        raise ValueError("Non-loopback observability binds require explicit allow_remote")
    return ThreadingHTTPServer((host, port), _handler(config, profile))
