#!/usr/bin/env python3
"""
Multi-server deployment helper for snh48_web.

Daily code deployment:
  python3 deploy/deploy.py deploy tencent
  python3 deploy/deploy.py deploy tencent aliyun

Docs/static-only deployment:
  python3 deploy/deploy.py deploy all --no-restart

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
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List
from urllib.parse import urlsplit


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

IMAGE_PROXY_CACHE_DIR = "/var/cache/nginx/snh48_image_proxy"
IMAGE_PROXY_CACHE_KEYS_ZONE_SIZE = "32m"
IMAGE_PROXY_CACHE_MAX_SIZE = "3g"
ENV_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

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
        "public_base_url": "https://cjy.plus",
        "public_urls": [
            "https://cjy.plus/",
            "https://cjy.plus/timeline",
            "https://cjy.plus/gift-replies",
            "https://cjy.plus/score-gifts",
            "https://cjy.plus/static/js/main.js",
            "https://cjy.plus/static/js/timeline.js",
            "https://cjy.plus/api/timeline/schedule",
            "https://cjy.plus/api/qa/status",
            "https://cjy.plus/image-proxy/health",
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
            {
                "type": "dir",
                "path": "/home/snh48-fan-hub/room_record/陈嘉仪_161808449/gift_replies",
                "delete": True,
            },
            {
                "type": "file",
                "path": "/home/snh48-fan-hub/room_record/陈嘉仪_161808449/messages.csv",
            },
            {
                "type": "file",
                "path": "/home/snh48-fan-hub/room_record/陈嘉仪_161808449/room_messages_ignored_batches.json",
                "optional": True,
            },
            {
                "type": "dir",
                "path": "/home/snh48-fan-hub/room_record/陈嘉仪_161808449/score_gifts",
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
        "public_base_url": "https://cjy.xn--6qq986b3xl",
        "public_urls": [
            "https://cjy.xn--6qq986b3xl/",
            "https://cjy.xn--6qq986b3xl/timeline",
            "https://cjy.xn--6qq986b3xl/gift-replies",
            "https://cjy.xn--6qq986b3xl/score-gifts",
            "https://cjy.xn--6qq986b3xl/static/js/main.js",
            "https://cjy.xn--6qq986b3xl/static/js/timeline.js",
            "https://cjy.xn--6qq986b3xl/api/timeline/schedule",
            "https://cjy.xn--6qq986b3xl/api/qa/status",
            "https://cjy.xn--6qq986b3xl/image-proxy/health",
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


def run_capture(args: List[str], dry_run: bool = False) -> subprocess.CompletedProcess:
    print("+ " + shell_join(args))
    if dry_run:
        return subprocess.CompletedProcess(args, 0, stdout="")
    return subprocess.run(args, check=True, text=True, stdout=subprocess.PIPE)


def run_with_retries(
    args: List[str],
    dry_run: bool = False,
    attempts: int = 1,
    delay: float = 1.0,
) -> subprocess.CompletedProcess:
    print("+ " + shell_join(args))
    if dry_run:
        return subprocess.CompletedProcess(args, 0)

    attempts = max(1, attempts)
    last_result = None
    for attempt in range(1, attempts + 1):
        result = subprocess.run(args)
        if result.returncode == 0:
            return result
        last_result = result
        if attempt < attempts:
            print(f"  retry {attempt}/{attempts - 1} after {delay:g}s")
            time.sleep(delay)
    raise subprocess.CalledProcessError(last_result.returncode, args)


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


def remote_capture(target: Dict[str, Any], command: str, dry_run: bool = False) -> str:
    result = run_capture(ssh_args(target) + [command], dry_run=dry_run)
    return str(result.stdout or "")


def remote_retry(
    target: Dict[str, Any],
    command: str,
    args: argparse.Namespace,
) -> None:
    run_with_retries(
        ssh_args(target) + [command],
        dry_run=args.dry_run,
        attempts=args.verify_attempts,
        delay=args.verify_delay,
    )


def curl_check(url: str, args: argparse.Namespace) -> None:
    run_with_retries(
        ["curl", "-fsS", "-D", "-", "-o", "/dev/null", url],
        dry_run=args.dry_run,
        attempts=args.verify_attempts,
        delay=args.verify_delay,
    )


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
    remote_path_value = nginx.get("remote_path")
    if not remote_path_value:
        raise SystemExit("Target nginx config is missing required field: remote_path")
    remote_path = quote(remote_path_value)
    prepare_cache = (
        f"mkdir -p {quote(IMAGE_PROXY_CACHE_DIR)} && "
        f"(if id nginx >/dev/null 2>&1; then chown -R nginx:nginx {quote(IMAGE_PROXY_CACHE_DIR)}; "
        f"elif id www-data >/dev/null 2>&1; then chown -R www-data:www-data {quote(IMAGE_PROXY_CACHE_DIR)}; fi) && "
    )
    if nginx.get("mode") == "generated" or not nginx.get("repo_config"):
        config = render_nginx_config(target)
        return (
            prepare_cache +
            f"cat > {remote_path} <<'EOF'\n"
            f"{config}"
            "EOF\n"
            "nginx -t && systemctl reload nginx"
        )
    repo_config_value = nginx.get("repo_config")
    if not repo_config_value:
        raise SystemExit("Target nginx config is missing required field: repo_config")
    repo_config = quote(repo_config_value)
    return (
        prepare_cache +
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
    image_proxy_cache_keys_zone_size = str(
        nginx.get("image_proxy_cache_keys_zone_size") or IMAGE_PROXY_CACHE_KEYS_ZONE_SIZE
    )
    image_proxy_cache_max_size = str(nginx.get("image_proxy_cache_max_size") or IMAGE_PROXY_CACHE_MAX_SIZE)
    access_log = str(nginx.get("access_log") or "/var/log/nginx/snh48_access.log")
    error_log = str(nginx.get("error_log") or "/var/log/nginx/snh48_error.log")

    headers = f"""        add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
        add_header X-Frame-Options "DENY" always;
        add_header X-Content-Type-Options "nosniff" always;
        add_header Referrer-Policy "strict-origin-when-cross-origin" always;
        add_header Content-Security-Policy "{SECURITY_CSP}" always;"""

    return f"""# Generated by deploy/deploy.py. Edit target config, not this file.
proxy_cache_path {IMAGE_PROXY_CACHE_DIR} levels=1:2 keys_zone=snh48_image_proxy:{image_proxy_cache_keys_zone_size} max_size={image_proxy_cache_max_size} inactive=30d use_temp_path=off;
limit_req_zone $binary_remote_addr zone=snh48_image_proxy_rate:20m rate=10r/s;

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
        proxy_cache snh48_image_proxy;
        proxy_cache_key "$scheme$host$request_uri";
        proxy_cache_methods GET HEAD;
        proxy_cache_valid 200 30d;
        proxy_cache_valid 301 302 1d;
        proxy_cache_valid 404 10m;
        proxy_cache_lock on;
        proxy_cache_lock_timeout 15s;
        proxy_cache_use_stale error timeout invalid_header updating http_500 http_502 http_503 http_504;
        proxy_cache_background_update on;
        proxy_cache_revalidate on;
        proxy_ignore_headers Cache-Control Expires Set-Cookie Vary;
        proxy_hide_header Cache-Control;
        proxy_hide_header Expires;
        proxy_hide_header Set-Cookie;
        proxy_buffering on;
        proxy_connect_timeout 5s;
        proxy_read_timeout 30s;
        proxy_send_timeout 10s;
        limit_req zone=snh48_image_proxy_rate burst=120 nodelay;
{headers}
        add_header Cache-Control "public, max-age=604800, immutable" always;
        add_header X-Cache-Status $upstream_cache_status always;
        add_header Access-Control-Allow-Origin * always;
    }}

    access_log {access_log};
    error_log  {error_log};
}}
"""


def verify_target(target: Dict[str, Any], args: argparse.Namespace) -> None:
    status_cmd = target.get("status")
    if status_cmd:
        remote_retry(target, str(status_cmd), args)
    local_url = target.get("local_url")
    if local_url:
        remote_retry(
            target,
            "curl -fsS -o /dev/null " + quote(local_url),
            args,
        )
    if not args.skip_public:
        for url in target.get("public_urls", []):
            curl_check(str(url), args)
    remote(target, remote_summary_command(target), dry_run=args.dry_run)


def public_base_url(target: Dict[str, Any]) -> str:
    configured = target.get("public_base_url")
    if configured:
        return str(configured).rstrip("/")
    for url in target.get("public_urls", []):
        parsed = urlsplit(str(url))
        if parsed.scheme and parsed.netloc:
            return f"{parsed.scheme}://{parsed.netloc}"
    raise SystemExit("Target has no public_base_url or public_urls")


def prewarm_image_cache_one(name: str, target: Dict[str, Any], args: argparse.Namespace) -> None:
    base_url = str(args.base_url or public_base_url(target)).rstrip("/")
    limit = max(1, int(args.limit))
    workers = max(1, int(args.workers))
    command = " && ".join(
        [
            f"cd {quote(site_dir(target))}",
            (
                "python3 script/prewarm_image_proxy.py "
                f"--base-url {quote(base_url)} "
                f"--limit {limit} "
                f"--workers {workers}"
            ),
        ]
    )
    print(f"\n== Prewarm image cache: {name} ==")
    remote(target, command, dry_run=args.dry_run)


def parse_env_example_keys(path: Path) -> List[str]:
    if not path.exists():
        raise SystemExit(f"Env example not found: {path}")
    keys: List[str] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key = line.split("=", 1)[0].strip()
        if ENV_KEY_RE.match(key):
            keys.append(key)
    return sorted(set(keys))


def remote_env_keys_command(target: Dict[str, Any]) -> str:
    return (
        f"cd {quote(site_dir(target))} && "
        "if [ -f .env ]; then "
        "sed -n 's/^\\([A-Za-z_][A-Za-z0-9_]*\\)=.*/\\1/p' .env | sort; "
        "else echo __MISSING_ENV_FILE__; fi"
    )


def check_env_one(name: str, target: Dict[str, Any], args: argparse.Namespace) -> None:
    print(f"\n== Check env keys: {name} ==")
    example_path = ROOT / str(args.env_example)
    expected = set(parse_env_example_keys(example_path))
    output = remote_capture(target, remote_env_keys_command(target), dry_run=args.dry_run)
    if args.dry_run:
        return

    remote_keys = {line.strip() for line in output.splitlines() if line.strip()}
    if "__MISSING_ENV_FILE__" in remote_keys:
        message = f"Remote .env is missing on {name}"
        if args.strict_env:
            raise SystemExit(message)
        print(f"WARNING: {message}")
        return

    missing = sorted(expected - remote_keys)
    extra = sorted(remote_keys - expected)
    if missing:
        print("Missing keys from remote .env:")
        for key in missing:
            print(f"  - {key}")
    else:
        print("Remote .env has all keys listed in .env.example.")
    if extra:
        print("Remote-only keys:")
        for key in extra:
            print(f"  - {key}")
    if missing and args.strict_env:
        raise SystemExit(f"Remote .env is missing {len(missing)} key(s) on {name}")


def deploy_one(name: str, target: Dict[str, Any], args: argparse.Namespace) -> None:
    print(f"\n== Deploy target: {name} ==")
    remote(target, remote_summary_command(target), dry_run=args.dry_run)
    remote(target, clean_tracked_changes_command(target), dry_run=args.dry_run)
    remote(target, git_update_command(target), dry_run=args.dry_run)
    if args.check_env:
        check_env_one(name, target, args)
    if args.nginx:
        remote(target, nginx_command(target), dry_run=args.dry_run)
    if args.no_restart:
        print("Skipping application restart (--no-restart).")
    else:
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
mkdir -p /home/snh48-fan-hub/room_record/陈嘉仪_161808449/gift_replies
mkdir -p /home/snh48-fan-hub/room_record/陈嘉仪_161808449/score_gifts
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

        opts = "-az --partial"
        if item.get("delete"):
            opts += " --delete"
        src = src_path.rstrip("/") + "/" if is_dir else src_path
        dst = f"{dest['ssh']}:{dest_path.rstrip('/') + '/' if is_dir else dest_path}"
        sync_command = f"rsync {opts} {quote(src)} {quote(dst)}"
        if item.get("optional"):
            sync_command = (
                f"if [ -e {quote(src_path)} ]; then "
                f"{sync_command}; "
                f"else echo optional data path missing: {quote(src_path)}; fi"
            )
        remote(source, sync_command, dry_run=args.dry_run)


def add_env_check_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--check-env", action="store_true", help="compare remote .env keys with .env.example")
    parser.add_argument("--strict-env", action="store_true", help="fail when remote .env is missing keys")
    parser.add_argument("--env-example", default=".env.example", help="path to local env example")


def add_prewarm_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--base-url", help="public base URL override")
    parser.add_argument("--limit", type=int, default=120, help="number of image URLs to prewarm")
    parser.add_argument("--workers", type=int, default=8, help="parallel prewarm workers")


def main() -> int:
    parser = argparse.ArgumentParser(description="Deploy snh48_web to one or more servers.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="optional targets.local.json")
    parser.add_argument("--dry-run", action="store_true", help="print commands without running them")

    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="list configured targets")

    deploy_parser = sub.add_parser("deploy", help="git pull, optionally restart, and verify target(s)")
    deploy_parser.add_argument("targets", nargs="+", help="target name(s), or all")
    deploy_parser.add_argument("--nginx", action="store_true", help="also copy nginx config and reload nginx")
    deploy_parser.add_argument("--no-restart", action="store_true", help="skip application restart after git pull")
    deploy_parser.add_argument("--no-verify", action="store_true", help="skip verification")
    deploy_parser.add_argument("--skip-public", action="store_true", help="skip local public URL checks")
    deploy_parser.add_argument("--verify-attempts", type=int, default=90, help="verification retry attempts")
    deploy_parser.add_argument("--verify-delay", type=float, default=2.0, help="seconds between verification attempts")
    add_env_check_args(deploy_parser)

    check_parser = sub.add_parser("check", help="run target verification only")
    check_parser.add_argument("targets", nargs="+", help="target name(s), or all")
    check_parser.add_argument("--skip-public", action="store_true", help="skip local public URL checks")
    check_parser.add_argument("--verify-attempts", type=int, default=90, help="verification retry attempts")
    check_parser.add_argument("--verify-delay", type=float, default=2.0, help="seconds between verification attempts")
    check_parser.set_defaults(no_verify=False)

    env_parser = sub.add_parser("check-env", help="compare remote .env keys with .env.example")
    env_parser.add_argument("targets", nargs="+", help="target name(s), or all")
    env_parser.add_argument("--strict-env", action="store_true", help="fail when remote .env is missing keys")
    env_parser.add_argument("--env-example", default=".env.example", help="path to local env example")

    boot_parser = sub.add_parser("bootstrap-ubuntu", help="prepare a new Ubuntu server")
    boot_parser.add_argument("target", help="target name")
    boot_parser.add_argument("--start", action="store_true", help="start service after bootstrap")

    sync_parser = sub.add_parser("sync-data", help="sync configured runtime data from one target to another")
    sync_parser.add_argument("source", help="source target")
    sync_parser.add_argument("dest", help="destination target")
    sync_parser.add_argument("--prewarm", action="store_true", help="prewarm destination image proxy cache after sync")
    add_prewarm_args(sync_parser)

    prewarm_parser = sub.add_parser("prewarm-image-cache", help="prewarm timeline image proxy cache")
    prewarm_parser.add_argument("targets", nargs="+", help="target name(s), or all")
    add_prewarm_args(prewarm_parser)

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

    if args.command == "check-env":
        for name in target_names(args.targets, targets):
            check_env_one(name, targets[name], args)
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
        if args.prewarm:
            prewarm_image_cache_one(args.dest, targets[args.dest], args)
        return 0

    if args.command == "prewarm-image-cache":
        for name in target_names(args.targets, targets):
            prewarm_image_cache_one(name, targets[name], args)
        return 0

    return 2


if __name__ == "__main__":
    sys.exit(main())
