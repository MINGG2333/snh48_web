#!/usr/bin/env bash
set -u -o pipefail

# Read-only host verification. Override these values for each deployment role.
WEB_SERVICE="${WEB_SERVICE:-snh48-aliyun.service}"
WEB_EXPECTED_USER="${WEB_EXPECTED_USER:-snh48-web}"
WEB_EXPECT_NO_NEW_PRIVILEGES="${WEB_EXPECT_NO_NEW_PRIVILEGES:-yes}"
IMAGE_PROXY_SERVICE="${IMAGE_PROXY_SERVICE:-snh48-weibo-img-proxy.service}"
IMAGE_PROXY_EXPECT_DYNAMIC_USER="${IMAGE_PROXY_EXPECT_DYNAMIC_USER:-yes}"
IMAGE_PROXY_EXPECT_LOOPBACK="${IMAGE_PROXY_EXPECT_LOOPBACK:-yes}"
ENV_FILE="${ENV_FILE:-/home/snh48_web/.env}"
PRIVATE_RUNTIME_ROOT="${PRIVATE_RUNTIME_ROOT:-/home/snh48_web/website/data}"
WEB_PORT="${WEB_PORT:-8000}"
IMAGE_PROXY_PORT="${IMAGE_PROXY_PORT:-8899}"
ALLOWED_NETWORK_PORTS="${ALLOWED_NETWORK_PORTS:-22,80,443}"
PUBLIC_BASE_URL="${PUBLIC_BASE_URL:-}"

failures=0

pass() {
    printf 'PASS  %s\n' "$1"
}

fail() {
    printf 'FAIL  %s\n' "$1" >&2
    failures=$((failures + 1))
}

require_command() {
    if command -v "$1" >/dev/null 2>&1; then
        pass "command available: $1"
    else
        fail "missing command: $1"
    fi
}

check_sshd_setting() {
    local key="$1"
    local expected="$2"
    local actual
    actual="$(printf '%s\n' "$SSHD_EFFECTIVE" | awk -v key="$key" '$1 == key {print $2; exit}')"
    if [ "$actual" = "$expected" ]; then
        pass "sshd $key=$expected"
    else
        fail "sshd $key expected $expected, got ${actual:-missing}"
    fi
}

check_service() {
    local service="$1"
    if systemctl is-active --quiet "$service"; then
        pass "$service is active"
    else
        fail "$service is not active"
    fi
    if systemctl is-enabled --quiet "$service"; then
        pass "$service is enabled"
    else
        fail "$service is not enabled"
    fi
}

check_loopback_listener() {
    local port="$1"
    local label="$2"
    local listeners
    local unsafe
    listeners="$(ss -H -ltn | awk -v suffix=":$port" '$4 ~ suffix "$" {print $4}')"
    if [ -z "$listeners" ]; then
        fail "$label has no TCP listener on port $port"
        return
    fi
    unsafe="$(printf '%s\n' "$listeners" | awk '!/^127\.0\.0\.1:/ && !/^\[::1\]:/ && !/^::1:/')"
    if [ -z "$unsafe" ]; then
        pass "$label listens only on loopback port $port"
    else
        fail "$label has a non-loopback listener on port $port: $unsafe"
    fi
}

check_listener_present() {
    local port="$1"
    local label="$2"
    if ss -H -ltn | awk -v suffix=":$port" '$4 ~ suffix "$" {found=1} END {exit !found}'; then
        pass "$label has a TCP listener on port $port"
    else
        fail "$label has no TCP listener on port $port"
    fi
}

for command_name in sshd systemctl ss nginx stat find awk curl grep; do
    require_command "$command_name"
done

SSHD_EFFECTIVE="$(sshd -T 2>/dev/null)"
check_sshd_setting authenticationmethods publickey
check_sshd_setting passwordauthentication no
check_sshd_setting kbdinteractiveauthentication no
check_sshd_setting gssapiauthentication no
check_sshd_setting x11forwarding no
permit_root_login="$(printf '%s\n' "$SSHD_EFFECTIVE" | awk '$1 == "permitrootlogin" {print $2; exit}')"
if [ "$permit_root_login" = "without-password" ] || [ "$permit_root_login" = "prohibit-password" ]; then
    pass "sshd root login is public-key only"
else
    fail "sshd permitrootlogin is ${permit_root_login:-missing}"
fi

check_service "$WEB_SERVICE"
web_user="$(systemctl show "$WEB_SERVICE" --property=User --value)"
if [ "$web_user" = "$WEB_EXPECTED_USER" ]; then
    pass "$WEB_SERVICE runs as $WEB_EXPECTED_USER"
else
    fail "$WEB_SERVICE expected user $WEB_EXPECTED_USER, got ${web_user:-missing}"
fi
web_umask="$(systemctl show "$WEB_SERVICE" --property=UMask --value)"
if [ "$web_umask" = "0077" ]; then
    pass "$WEB_SERVICE uses UMask=0077"
else
    fail "$WEB_SERVICE expected UMask=0077, got ${web_umask:-missing}"
fi
if [ "$WEB_EXPECT_NO_NEW_PRIVILEGES" != "skip" ]; then
    web_nnp="$(systemctl show "$WEB_SERVICE" --property=NoNewPrivileges --value)"
    if [ "$web_nnp" = "$WEB_EXPECT_NO_NEW_PRIVILEGES" ]; then
        pass "$WEB_SERVICE NoNewPrivileges=$WEB_EXPECT_NO_NEW_PRIVILEGES"
    else
        fail "$WEB_SERVICE expected NoNewPrivileges=$WEB_EXPECT_NO_NEW_PRIVILEGES, got ${web_nnp:-missing}"
    fi
fi

check_service "$IMAGE_PROXY_SERVICE"
proxy_dynamic_user="$(systemctl show "$IMAGE_PROXY_SERVICE" --property=DynamicUser --value)"
if [ "$proxy_dynamic_user" = "$IMAGE_PROXY_EXPECT_DYNAMIC_USER" ]; then
    pass "$IMAGE_PROXY_SERVICE DynamicUser=$IMAGE_PROXY_EXPECT_DYNAMIC_USER"
else
    fail "$IMAGE_PROXY_SERVICE expected DynamicUser=$IMAGE_PROXY_EXPECT_DYNAMIC_USER, got ${proxy_dynamic_user:-missing}"
fi

check_loopback_listener "$WEB_PORT" "website backend"
if [ "$IMAGE_PROXY_EXPECT_LOOPBACK" = "yes" ]; then
    check_loopback_listener "$IMAGE_PROXY_PORT" "image proxy"
else
    check_listener_present "$IMAGE_PROXY_PORT" "image proxy"
fi

if unexpected_network_ports="$(
    ss -H -ltn | awk -v allowed="$ALLOWED_NETWORK_PORTS" '
        BEGIN {
            count = split(allowed, values, ",")
            for (i = 1; i <= count; i++) ok[values[i]] = 1
        }
        {
            address = $4
            if (address ~ /^127\./ || address ~ /^\[::1\]:/ || address ~ /^::1:/) next
            port = address
            sub(/^.*:/, "", port)
            if (!ok[port]) print address
        }
    '
)"; then
    if [ -z "$unexpected_network_ports" ]; then
        pass "network listeners are limited to ports $ALLOWED_NETWORK_PORTS"
    else
        fail "unexpected non-loopback listeners: $unexpected_network_ports"
    fi
else
    fail "unable to inspect non-loopback listeners"
fi

if nginx -t >/dev/null 2>&1; then
    pass "nginx configuration syntax"
else
    fail "nginx configuration syntax"
fi

if [ -f "$ENV_FILE" ]; then
    env_mode="$(stat -c '%a' "$ENV_FILE")"
    env_owner="$(stat -c '%U:%G' "$ENV_FILE")"
    if [ "$env_mode" = "600" ] && [ "$env_owner" = "root:root" ]; then
        pass "$ENV_FILE is root:root 0600"
    else
        fail "$ENV_FILE expected root:root 0600, got $env_owner $env_mode"
    fi
else
    fail "missing environment file: $ENV_FILE"
fi

if [ -d "$PRIVATE_RUNTIME_ROOT" ]; then
    exposed_runtime_path="$(find "$PRIVATE_RUNTIME_ROOT" -perm /077 -print -quit)"
    if [ -z "$exposed_runtime_path" ]; then
        pass "$PRIVATE_RUNTIME_ROOT has no group/other permission bits"
    else
        fail "$PRIVATE_RUNTIME_ROOT contains group/other-readable path: $exposed_runtime_path"
    fi
else
    fail "missing runtime directory: $PRIVATE_RUNTIME_ROOT"
fi

set +e
curl -sS --max-time 5 -o /dev/null -H 'Host: security-baseline.invalid' http://127.0.0.1/
unknown_host_rc=$?
set -e
if [ "$unknown_host_rc" -eq 52 ]; then
    pass "nginx rejects an unknown HTTP Host with an empty response"
else
    fail "unknown HTTP Host was not rejected as expected (curl rc=$unknown_host_rc)"
fi
set +e

if [ -n "$PUBLIC_BASE_URL" ]; then
    public_status="$(curl -sS --max-time 15 -o /dev/null -w '%{http_code}' "$PUBLIC_BASE_URL/")"
    openapi_status="$(curl -sS --max-time 15 -o /dev/null -w '%{http_code}' "$PUBLIC_BASE_URL/openapi.json")"
    public_headers="$(curl -sS --max-time 15 -D - -o /dev/null "$PUBLIC_BASE_URL/")"
    if [ "$public_status" = "200" ]; then
        pass "public homepage returns 200"
    else
        fail "public homepage returned $public_status"
    fi
    if [ "$openapi_status" = "404" ]; then
        pass "public OpenAPI document is disabled"
    else
        fail "public OpenAPI document returned $openapi_status"
    fi
    for header_name in strict-transport-security content-security-policy x-frame-options x-content-type-options; do
        if printf '%s\n' "$public_headers" | grep -qi "^$header_name:"; then
            pass "public response includes $header_name"
        else
            fail "public response is missing $header_name"
        fi
    done
    server_header="$(printf '%s\n' "$public_headers" | awk 'BEGIN {IGNORECASE=1} /^server:/ {sub(/^[^:]+:[[:space:]]*/, ""); sub(/\r$/, ""); print; exit}')"
    if [ "$server_header" = "nginx" ]; then
        pass "nginx version is hidden"
    else
        fail "unexpected Server header: ${server_header:-missing}"
    fi
else
    printf 'INFO  PUBLIC_BASE_URL is empty; public HTTPS checks were skipped.\n'
fi

printf 'INFO  Cloud security groups are outside this host check. Verify ports %s and %s are unreachable from an independent network.\n' "$WEB_PORT" "$IMAGE_PROXY_PORT"

if [ "$failures" -ne 0 ]; then
    printf 'RESULT failed (%s check(s))\n' "$failures" >&2
    exit 1
fi
printf 'RESULT passed\n'
