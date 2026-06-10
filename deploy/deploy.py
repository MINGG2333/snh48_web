#!/usr/bin/env python3
"""
Multi-server deployment helper for snh48_web.

Daily code deployment:
  python3 deploy/deploy.py deploy tencent
  python3 deploy/deploy.py deploy tencent aliyun

New Ubuntu host bootstrap:
  cp deploy/targets.example.json deploy/targets.local.json
  # edit deploy/targets.local.json
  python3 deploy/deploy.py --config deploy/targets.local.json bootstrap-ubuntu huawei

The tool intentionally does not store or print production secrets. Keep real
values in the remote .env file.
"""
from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "deploy" / "targets.local.json"
SECURITY_CSP = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' cdnjs.cloudflare.com cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline' cdnjs.cloudflare.com fonts.googleapis.com; "
    "font-src 'self' cdnjs.cloudflare.com fonts.gstatic.com; "
    "img-src 'self' data: https:; "
    "connect-src 'self' https:; "
    "media-src 'self' https: blob:; "
    "worker-src 'self' blob:; "
    "object-src 'none'; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self';"
)

BUILTIN_TARGETS: Dict[str, Dict[str, Any]] = {
    "tencent": {
        "description": "Tencent Cloud mainland server, cjy.plus",
        "ssh": "root@124.222.72.203",
        "site_dir": "/home/snh48_web",
        "branch": "main",
        "repo_url": "git@github.com:MINGG2333/snh48_web.git",
        "transcript_repo_url": "git@github.com:MINGG2333/transcript_analyze.git",
        "restart": (
            "screen -S snh48 -X quit 2>/dev/null; "
            "screen -S snh48 -dm bash -c "
            "'cd /home/snh48_web && source venv/bin/activate && "
            "python -m website.main 2>&1 | tee /var/log/snh48/snh48_screen.log'"
        ),
        "status": "screen -ls | grep -q '\\.snh48'",
        "local_url": "http://127.0.0.1:8000/timeline",
        "public_urls": [
            "https://cjy.plus/timeline",
            "https://cjy.plus/static/js/timeline.js",
            "https://cjy.plus/api/timeline/schedule",
            "https://cjy.plus/api/qa/status",
        ],
        "nginx": {
            "repo_config": "deploy/nginx.conf",
            "remote_path": "/etc/nginx/conf.d/snh48.conf",
        },
        "data_paths": [
            {
                "type": "file",
                "path": "/home/snh48-fan-hub/schedule_record/schedule.csv",
            },
            {
                "type": "dir",
                "path": "/home/snh48-fan-hub/live_push_replays/陈嘉仪_161808449",
                "delete": True,
            },
            {
                "type": "dir",
                "path": "/home/snh48-fan-hub/room_record/陈嘉仪_161808449/live_covers",
                "delete": True,
            },
        ],
        "deploy_by_default": True,
    },
    "aliyun": {
        "description": "Aliyun Hong Kong server, cjy.xn--6qq986b3xl",
        "ssh": "root@8.210.188.184",
        "site_dir": "/home/snh48_web",
        "branch": "main",
        "repo_url": "git@github.com:MINGG2333/snh48_web.git",
        "transcript_repo_url": "git@github.com:MINGG2333/transcript_analyze.git",
        "restart": "systemctl restart snh48-aliyun",
        "status": "systemctl is-active --quiet snh48-aliyun",
        "local_url": "http://127.0.0.1:8000/timeline",
        "public_urls": [
            "https://cjy.xn--6qq986b3xl/timeline",
            "https://cjy.xn--6qq986b3xl/static/js/timeline.js",
            "https://cjy.xn--6qq986b3xl/api/timeline/schedule",
            "https://cjy.xn--6qq986b3xl/api/qa/status",
        ],
        "nginx": {
            "repo_config": "deploy/nginx-aliyun.conf",
            "remote_path": "/etc/nginx/conf.d/cjy.xn--6qq986b3xl.conf",
        },
        "deploy_by_default": True,
    },
}


def quote(value: Any) -> str:
    return shlex.quote(str(value))


def shell_join(args: Iterable[str]) -> str:
    return " ".join(quote(arg) for arg in args)


def run(args: List[str], dry_run: bool = False) -> subprocess.CompletedProcess:
    print("+ " + shell_join(args))
    if dry_run:
        return subprocess.CompletedProcess(args, 0)
    return subprocess.run(args, check=True)


def deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_targets(config_path: Path) -> Dict[str, Dict[str, Any]]:
    targets = {name: dict(cfg) for name, cfg in BUILTIN_TARGETS.items()}
    if config_path.exists():
        with config_path.open("r", encoding="utf-8") as f:
            payload = json.load(f)
        for name, cfg in payload.get("targets", {}).items():
            targets[name] = deep_merge(targets.get(name, {}), cfg)
    return targets


def target_names(names: List[str], targets: Dict[str, Dict[str, Any]]) -> List[str]:
    if names == ["all"]:
        return [name for name, cfg in targets.items() if cfg.get("deploy_by_default")]
    missing = [name for name in names if name not in targets]
    if missing:
        raise SystemExit(f"Unknown target(s): {', '.join(missing)}")
    return names


def ssh_args(target: Dict[str, Any]) -> List[str]:
    ssh = target.get("ssh")
    if not ssh:
        raise SystemExit("Target is missing required field: ssh")
    return ["ssh", "-F", "/dev/null", ssh]


def remote(target: Dict[str, Any], command: str, dry_run: bool = False) -> None:
    run(ssh_args(target) + [command], dry_run=dry_run)


def curl_check(url: str, dry_run: bool = False) -> None:
    run(["curl", "-fsS", "-D", "-", "-o", "/dev/null", url], dry_run=dry_run)


def site_dir(target: Dict[str, Any]) -> str:
    value = target.get("site_dir")
    if not value:
        raise SystemExit("Target is missing required field: site_dir")
    return str(value)


def branch(target: Dict[str, Any]) -> str:
    return str(target.get("branch") or "main")


def git_update_command(target: Dict[str, Any]) -> str:
    site = quote(site_dir(target))
    br = quote(branch(target))
    return " && ".join(
        [
            f"cd {site}",
            f"git fetch origin {br}",
            f"git checkout {br}",
            f"git pull --ff-only origin {br}",
            (
                "if [ -d transcript_analyze/.git ]; then "
                "cd transcript_analyze && git pull --ff-only; "
                "fi"
            ),
        ]
    )


def clean_tracked_changes_command(target: Dict[str, Any]) -> str:
    site = quote(site_dir(target))
    return " && ".join(
        [
            f"cd {site}",
            "git diff --quiet",
            "git diff --cached --quiet",
            (
                "if [ -d transcript_analyze/.git ]; then "
                "cd transcript_analyze && git diff --quiet && git diff --cached --quiet; "
                "fi"
            ),
        ]
    )


def remote_summary_command(target: Dict[str, Any]) -> str:
    site = quote(site_dir(target))
    return (
        f"cd {site} && "
        "echo HEAD=$(git rev-parse --short HEAD) && "
        "git status --short && "
        "if [ -d transcript_analyze/.git ]; then "
        "cd transcript_analyze && echo transcript_analyze=$(git rev-parse --short HEAD) && git status --short; "
        "fi"
    )


def nginx_command(target: Dict[str, Any]) -> str:
    nginx = target.get("nginx")
    if not nginx:
        raise SystemExit("Target has no nginx config")
    remote_path = quote(nginx.get("remote_path"))
    if nginx.get("mode") == "generated" or not nginx.get("repo_config"):
        config = render_nginx_config(target)
        return (
            f"cat > {remote_path} <<'EOF'\n"
            f"{config}"
            "EOF\n"
            "nginx -t && systemctl reload nginx"
        )
    repo_config = quote(nginx.get("repo_config"))
    return (
        f"cd {quote(site_dir(target))} && "
        f"cp {repo_config} {remote_path} && "
        "nginx -t && systemctl reload nginx"
    )


def render_nginx_config(target: Dict[str, Any]) -> str:
    nginx = target.get("nginx") or {}
    names = nginx.get("server_names") or []
    if not names:
        raise SystemExit("Generated nginx config requires nginx.server_names")
    cert = nginx.get("ssl_certificate")
    key = nginx.get("ssl_certificate_key")
    if not cert or not key:
        raise SystemExit("Generated nginx config requires ssl_certificate and ssl_certificate_key")

    site = site_dir(target).rstrip("/")
    server_names = " ".join(str(name) for name in names)
    image_proxy = str(nginx.get("image_proxy_upstream") or "http://127.0.0.1:8899/")
    access_log = str(nginx.get("access_log") or "/var/log/nginx/snh48_access.log")
    error_log = str(nginx.get("error_log") or "/var/log/nginx/snh48_error.log")

    headers = f"""        add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
        add_header X-Frame-Options "DENY" always;
        add_header X-Content-Type-Options "nosniff" always;
        add_header Referrer-Policy "strict-origin-when-cross-origin" always;
        add_header Content-Security-Policy "{SECURITY_CSP}" always;"""

    return f"""# Generated by deploy/deploy.py. Edit target config, not this file.
server {{
    listen 80;
    server_name {server_names};
    return 301 https://$host$request_uri;
}}

server {{
    listen 443 ssl;
    server_name {server_names};

    ssl_certificate     {cert};
    ssl_certificate_key {key};
    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_ciphers         HIGH:!aNULL:!MD5;

{headers}

    location /static/js/ {{
        alias {site}/website/static/js-dist/;
        expires 7d;
{headers}
        add_header Cache-Control "public, immutable" always;
    }}

    location /static/css/ {{
        alias {site}/website/static/css-dist/;
        expires 7d;
{headers}
        add_header Cache-Control "public, immutable" always;
    }}

    location /static/ {{
        alias {site}/website/static/;
        expires 7d;
{headers}
        add_header Cache-Control "public, immutable" always;
    }}

    location /api/ {{
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;
        proxy_send_timeout 60s;
    }}

    location / {{
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;
    }}

    location /image-proxy/ {{
        proxy_pass {image_proxy};
        proxy_set_header Host $proxy_host;
        proxy_set_header X-Real-IP $remote_addr;
{headers}
        add_header Cache-Control "public, max-age=86400" always;
        add_header Access-Control-Allow-Origin * always;
    }}

    access_log {access_log};
    error_log  {error_log};
}}
"""


def verify_target(target: Dict[str, Any], args: argparse.Namespace) -> None:
    status_cmd = target.get("status")
    if status_cmd:
        remote(target, str(status_cmd), dry_run=args.dry_run)
    local_url = target.get("local_url")
    if local_url:
        remote(
            target,
            "curl -fsS -o /dev/null " + quote(local_url),
            dry_run=args.dry_run,
        )
    if not args.skip_public:
        for url in target.get("public_urls", []):
            curl_check(str(url), dry_run=args.dry_run)
    remote(target, remote_summary_command(target), dry_run=args.dry_run)


def deploy_one(name: str, target: Dict[str, Any], args: argparse.Namespace) -> None:
    print(f"\n== Deploy target: {name} ==")
    remote(target, remote_summary_command(target), dry_run=args.dry_run)
    remote(target, clean_tracked_changes_command(target), dry_run=args.dry_run)
    remote(target, git_update_command(target), dry_run=args.dry_run)
    if args.nginx:
        remote(target, nginx_command(target), dry_run=args.dry_run)
    restart = target.get("restart")
    if not restart:
        raise SystemExit(f"Target {name} is missing restart command")
    remote(target, str(restart), dry_run=args.dry_run)
    if not args.no_verify:
        verify_target(target, args)


def list_targets(targets: Dict[str, Dict[str, Any]]) -> None:
    for name in sorted(targets):
        cfg = targets[name]
        marker = "*" if cfg.get("deploy_by_default") else " "
        print(f"{marker} {name:12} {cfg.get('ssh', '-'):24} {cfg.get('description', '')}")


def systemd_unit(target: Dict[str, Any]) -> str:
    service_name = str(target.get("service_name") or "snh48")
    site = site_dir(target)
    log_file = str(target.get("log_file") or f"/var/log/snh48/{service_name}.log")
    return f"""[Unit]
Description=SNH48 Website Service ({service_name})
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory={site}
EnvironmentFile={site}/.env
ExecStart={site}/venv/bin/python -m website.main
Restart=always
RestartSec=10
StandardOutput=append:{log_file}
StandardError=append:{log_file}

[Install]
WantedBy=multi-user.target
"""


def bootstrap_ubuntu(name: str, target: Dict[str, Any], args: argparse.Namespace) -> None:
    service_name = str(target.get("service_name") or f"snh48-{name}")
    site = site_dir(target)
    repo_url = str(target.get("repo_url") or "git@github.com:MINGG2333/snh48_web.git")
    transcript_repo_url = str(
        target.get("transcript_repo_url")
        or "git@github.com:MINGG2333/transcript_analyze.git"
    )
    unit = systemd_unit({**target, "service_name": service_name})
    start_cmd = f"systemctl restart {quote(service_name)}" if args.start else (
        f"echo 'systemd unit installed. Fill {site}/.env, then run: systemctl restart {service_name}'"
    )

    command = f"""set -e
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y python3 python3-venv python3-pip git nginx curl rsync build-essential certbot python3-certbot-nginx
mkdir -p {quote(site.rsplit("/", 1)[0] or "/")}
if [ ! -d {quote(site)}/.git ]; then
  git clone {quote(repo_url)} {quote(site)}
fi
cd {quote(site)}
git checkout {quote(branch(target))}
git pull --ff-only origin {quote(branch(target))}
if [ ! -d transcript_analyze/.git ]; then
  rm -rf transcript_analyze
  git clone {quote(transcript_repo_url)} transcript_analyze
else
  cd transcript_analyze && git pull --ff-only && cd ..
fi
python3 -m venv venv
venv/bin/python -m pip install --upgrade pip
venv/bin/pip install -r website/requirements.txt
if [ -f transcript_analyze/requirements_kb_qa.txt ]; then
  venv/bin/pip install -r transcript_analyze/requirements_kb_qa.txt
fi
mkdir -p /var/log/snh48
mkdir -p /home/snh48-fan-hub/schedule_record
mkdir -p /home/snh48-fan-hub/live_push_replays
mkdir -p /home/snh48-fan-hub/room_record/陈嘉仪_161808449/live_covers
if [ ! -f .env ] && [ -f .env.example ]; then
  cp .env.example .env
  chmod 600 .env
fi
cat > /etc/systemd/system/{quote(service_name)}.service <<'EOF'
{unit}EOF
systemctl daemon-reload
systemctl enable {quote(service_name)}
{start_cmd}
"""
    print(f"\n== Bootstrap Ubuntu target: {name} ==")
    remote(target, command, dry_run=args.dry_run)


def destination_path(item: Dict[str, Any]) -> str:
    return str(item.get("dest_path") or item.get("path"))


def parent_dir(path: str) -> str:
    return str(Path(path).parent)


def sync_data(source: Dict[str, Any], dest: Dict[str, Any], args: argparse.Namespace) -> None:
    data_paths = source.get("data_paths") or []
    if not data_paths:
        raise SystemExit("Source target has no data_paths configured")

    for item in data_paths:
        src_path = str(item["path"])
        dest_path = destination_path(item)
        is_dir = item.get("type") == "dir"
        dest_mkdir = dest_path.rstrip("/") if is_dir else parent_dir(dest_path)
        remote(dest, f"mkdir -p {quote(dest_mkdir)}", dry_run=args.dry_run)

        opts = "-az"
        if item.get("delete"):
            opts += " --delete"
        src = src_path.rstrip("/") + "/" if is_dir else src_path
        dst = f"{dest['ssh']}:{dest_path.rstrip('/') + '/' if is_dir else dest_path}"
        remote(source, f"rsync {opts} {quote(src)} {quote(dst)}", dry_run=args.dry_run)


def main() -> int:
    parser = argparse.ArgumentParser(description="Deploy snh48_web to one or more servers.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="optional targets.local.json")
    parser.add_argument("--dry-run", action="store_true", help="print commands without running them")

    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="list configured targets")

    deploy_parser = sub.add_parser("deploy", help="git pull, restart, and verify target(s)")
    deploy_parser.add_argument("targets", nargs="+", help="target name(s), or all")
    deploy_parser.add_argument("--nginx", action="store_true", help="also copy nginx config and reload nginx")
    deploy_parser.add_argument("--no-verify", action="store_true", help="skip verification")
    deploy_parser.add_argument("--skip-public", action="store_true", help="skip local public URL checks")

    check_parser = sub.add_parser("check", help="run target verification only")
    check_parser.add_argument("targets", nargs="+", help="target name(s), or all")
    check_parser.add_argument("--skip-public", action="store_true", help="skip local public URL checks")
    check_parser.set_defaults(no_verify=False)

    boot_parser = sub.add_parser("bootstrap-ubuntu", help="prepare a new Ubuntu server")
    boot_parser.add_argument("target", help="target name")
    boot_parser.add_argument("--start", action="store_true", help="start service after bootstrap")

    sync_parser = sub.add_parser("sync-data", help="sync configured runtime data from one target to another")
    sync_parser.add_argument("source", help="source target")
    sync_parser.add_argument("dest", help="destination target")

    args = parser.parse_args()
    targets = load_targets(args.config)

    if args.command == "list":
        list_targets(targets)
        return 0

    if args.command == "deploy":
        for name in target_names(args.targets, targets):
            deploy_one(name, targets[name], args)
        return 0

    if args.command == "check":
        for name in target_names(args.targets, targets):
            print(f"\n== Check target: {name} ==")
            verify_target(targets[name], args)
        return 0

    if args.command == "bootstrap-ubuntu":
        if args.target not in targets:
            raise SystemExit(f"Unknown target: {args.target}")
        bootstrap_ubuntu(args.target, targets[args.target], args)
        return 0

    if args.command == "sync-data":
        if args.source not in targets:
            raise SystemExit(f"Unknown source target: {args.source}")
        if args.dest not in targets:
            raise SystemExit(f"Unknown destination target: {args.dest}")
        sync_data(targets[args.source], targets[args.dest], args)
        return 0

    return 2


if __name__ == "__main__":
    sys.exit(main())
