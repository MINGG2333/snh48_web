#!/usr/bin/env python3
"""Check the production HTTPS certificate and write a monthly reminder report."""

from __future__ import annotations

import argparse
import socket
import ssl
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


DEFAULT_HOST = "cjy.xn--6qq986b3xl"
DEFAULT_CERT_FILE = "/etc/letsencrypt/live/cjy.xn--6qq986b3xl/fullchain.pem"


@dataclass
class CheckResult:
    source: str
    subject: str
    issuer: str
    not_after: datetime
    error: Optional[str] = None

    @property
    def days_remaining(self) -> float:
        delta = self.not_after - datetime.now(timezone.utc)
        return delta.total_seconds() / 86400


def parse_cert_time(value: str) -> datetime:
    parsed = datetime.strptime(value, "%b %d %H:%M:%S %Y %Z")
    return parsed.replace(tzinfo=timezone.utc)


def first_name_value(parts: Iterable[Tuple[Tuple[str, str], ...]], key: str) -> str:
    for group in parts:
        for name, value in group:
            if name == key:
                return value
    return "-"


def decode_name(parts: Iterable[Tuple[Tuple[str, str], ...]]) -> str:
    common_name = first_name_value(parts, "commonName")
    organization = first_name_value(parts, "organizationName")
    if common_name != "-":
        return common_name
    return organization


def result_from_cert_dict(source: str, cert: Dict[str, Any]) -> CheckResult:
    return CheckResult(
        source=source,
        subject=decode_name(cert.get("subject", [])),
        issuer=decode_name(cert.get("issuer", [])),
        not_after=parse_cert_time(str(cert["notAfter"])),
    )


def fetch_remote_cert(host: str, port: int, server_name: str, timeout: float) -> CheckResult:
    context = ssl.create_default_context()
    with socket.create_connection((host, port), timeout=timeout) as sock:
        with context.wrap_socket(sock, server_hostname=server_name) as tls:
            cert = tls.getpeercert()
    return result_from_cert_dict(f"remote TLS {server_name}:{port}", cert)


def decode_local_cert(path: Path) -> CheckResult:
    cert = ssl._ssl._test_decode_cert(str(path))  # type: ignore[attr-defined]
    return result_from_cert_dict(f"local file {path}", cert)


def state_for(days_remaining: float, warn_days: int, critical_days: int) -> str:
    if days_remaining < 0:
        return "EXPIRED"
    if days_remaining <= critical_days:
        return "CRITICAL"
    if days_remaining <= warn_days:
        return "WARN"
    return "OK"


def render_report(
    host: str,
    results: List[CheckResult],
    errors: List[str],
    warn_days: int,
    critical_days: int,
) -> str:
    now = datetime.now(timezone.utc)
    rows = []
    states = []
    for result in results:
        state = state_for(result.days_remaining, warn_days, critical_days)
        states.append(state)
        rows.append(
            "| {source} | {subject} | {issuer} | {expiry} | {days:.1f} | {state} |".format(
                source=result.source,
                subject=result.subject,
                issuer=result.issuer,
                expiry=result.not_after.isoformat(),
                days=result.days_remaining,
                state=state,
            )
        )

    if errors:
        overall = "ERROR"
        next_action = "Check Certbot, Nginx, DNS, and the certificate paths immediately."
    elif any(state in {"EXPIRED", "CRITICAL"} for state in states):
        overall = "CRITICAL"
        next_action = "Run certbot renewal diagnostics and reload Nginx after a successful renewal."
    elif any(state == "WARN" for state in states):
        overall = "WARN"
        next_action = "Confirm certbot.timer is active and run a dry-run renewal if the next renewal did not happen."
    else:
        overall = "OK"
        next_action = "No manual replacement needed. Keep Certbot auto-renewal enabled."

    lines = [
        "# HTTPS Certificate Monthly Reminder",
        "",
        f"- Updated UTC: `{now.isoformat()}`",
        f"- Host: `{host}`",
        f"- Overall state: `{overall}`",
        f"- Next action: {next_action}",
        "",
        "| Source | Subject | Issuer | Expires UTC | Days Remaining | State |",
        "|--------|---------|--------|-------------|----------------|-------|",
    ]
    lines.extend(rows or ["| - | - | - | - | - | ERROR |"])
    if errors:
        lines.extend(["", "## Errors", ""])
        lines.extend(f"- {error}" for error in errors)
    lines.extend(
        [
            "",
            "## Operational Notes",
            "",
            "- This is a reminder and health check, not the renewal mechanism.",
            "- The renewal mechanism is Certbot's systemd timer on the Aliyun server.",
            "- Runtime reminder output is intentionally not tracked by Git.",
        ]
    )
    return "\n".join(lines) + "\n"


def write_report(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=DEFAULT_HOST, help="TLS host to check")
    parser.add_argument("--server-name", help="SNI/server name; defaults to --host")
    parser.add_argument("--port", type=int, default=443)
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--cert-file", default=DEFAULT_CERT_FILE, help="Local certificate file to decode")
    parser.add_argument("--skip-local-cert", action="store_true", help="Only check the served TLS certificate")
    parser.add_argument("--output", help="Optional Markdown report path")
    parser.add_argument("--warn-days", type=int, default=35)
    parser.add_argument("--critical-days", type=int, default=14)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    server_name = args.server_name or args.host
    results: List[CheckResult] = []
    errors: List[str] = []

    try:
        results.append(fetch_remote_cert(args.host, args.port, server_name, args.timeout))
    except Exception as exc:  # noqa: BLE001 - cron output should include the concrete failure.
        errors.append(f"remote TLS check failed for {server_name}:{args.port}: {exc}")

    if not args.skip_local_cert and args.cert_file:
        cert_path = Path(args.cert_file)
        if cert_path.exists():
            try:
                results.append(decode_local_cert(cert_path))
            except Exception as exc:  # noqa: BLE001 - cron output should include the concrete failure.
                errors.append(f"local certificate check failed for {cert_path}: {exc}")
        else:
            errors.append(f"local certificate file not found: {cert_path}")

    report = render_report(args.host, results, errors, args.warn_days, args.critical_days)
    if args.output:
        write_report(Path(args.output), report)
    print(report, end="")

    states = [state_for(result.days_remaining, args.warn_days, args.critical_days) for result in results]
    if errors or any(state in {"EXPIRED", "CRITICAL"} for state in states):
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
