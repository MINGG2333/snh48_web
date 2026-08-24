from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SERVER_PATH = ROOT / "deploy/privileged/snh48_privileged_bridge_server.py"
CLIENT_PATH = ROOT / "deploy/privileged/snh48_privileged_bridge_client.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


bridge_server = load_module("snh48_privileged_bridge_server", SERVER_PATH)


class FakeProcess:
    pid = 12345

    def __init__(self, output: str) -> None:
        self.output = output
        self.stdin_payload = ""
        self.timeout = 0

    def communicate(self, payload: str, timeout: int):
        self.stdin_payload = payload
        self.timeout = timeout
        return self.output, None


class PrivilegedBridgeTests(unittest.TestCase):
    def make_fan_root(self, temporary: str) -> Path:
        fan_root = Path(temporary) / "fan-hub"
        (fan_root / "venv/bin").mkdir(parents=True)
        (fan_root / "scripts/web").mkdir(parents=True)
        (fan_root / "venv/bin/python3").symlink_to(sys.executable)
        script = fan_root / "scripts/web/social_credentials_admin.py"
        script.write_text(
            "import json, sys\n"
            "payload = json.load(sys.stdin)\n"
            "print(json.dumps({'ok': True, 'received': bool(payload)}))\n",
            encoding="utf-8",
        )
        return fan_root

    def test_sensitive_payload_stays_out_of_process_arguments(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fan_root = self.make_fan_root(temporary)
            broker = bridge_server.CommandBroker("social", fan_root)
            process = FakeProcess('{"ok":true,"platform":"weibo","slot":"primary"}')
            with (
                mock.patch.object(bridge_server, "_require_root_owned_readonly", side_effect=lambda path: path.resolve()),
                mock.patch.object(bridge_server.subprocess, "Popen", return_value=process) as popen,
            ):
                result = broker.run(
                    {
                        "command": "update",
                        "payload": {
                            "platform": "weibo",
                            "slot": "primary",
                            "cookie": "sensitive-cookie-value",
                        },
                    }
                )

        arguments = popen.call_args.args[0]
        self.assertNotIn("sensitive-cookie-value", " ".join(arguments))
        self.assertIn("sensitive-cookie-value", process.stdin_payload)
        self.assertNotIn("sensitive-cookie-value", result)
        self.assertEqual(process.timeout, 170)

    def test_command_allowlist_rejects_arbitrary_execution(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            broker = bridge_server.CommandBroker("flip", self.make_fan_root(temporary))
            with self.assertRaises(bridge_server.BridgeFailure):
                broker.run({"command": "shell", "payload": {"value": "id"}})

    def test_client_and_server_exchange_json_over_unix_socket(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fan_root = self.make_fan_root(temporary)
            runtime_dir = root / "snh48-privileged-bridge-social"
            runtime_dir.mkdir()
            socket_path = runtime_dir / "bridge.sock"
            broker = bridge_server.CommandBroker("social", fan_root)
            with mock.patch.object(
                bridge_server,
                "_require_root_owned_readonly",
                side_effect=lambda path: path.resolve(),
            ):
                server = bridge_server.BridgeSocketServer(
                    socket_path,
                    broker,
                    frozenset({os.getuid()}),
                )
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                try:
                    result = subprocess.run(
                        [sys.executable, str(CLIENT_PATH), "social", "status"],
                        input="{}",
                        text=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        check=False,
                        env={**os.environ, "SNH48_PRIVILEGED_BRIDGE_SOCKET_ROOT": str(root)},
                    )
                finally:
                    server.shutdown()
                    server.server_close()
                    thread.join(timeout=2)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {"ok": True, "received": False})

    def test_deployment_keeps_web_process_unprivileged(self) -> None:
        web_unit = (ROOT / "deploy/systemd/snh48-web.service").read_text(encoding="utf-8")
        hardening = (ROOT / "deploy/harden_runtime_permissions.sh").read_text(encoding="utf-8")
        flip_unit = (ROOT / "deploy/systemd/snh48-privileged-bridge-flip.service").read_text(encoding="utf-8")
        social_unit = (ROOT / "deploy/systemd/snh48-privileged-bridge-social.service").read_text(encoding="utf-8")

        self.assertNotIn("/usr/bin/sudo", web_unit)
        self.assertIn("NoNewPrivileges=yes", web_unit)
        self.assertIn("CapabilityBoundingSet=\n", web_unit)
        self.assertIn("snh48-privileged-bridge-client social", web_unit)
        self.assertIn("snh48-privileged-bridge-client flip", web_unit)
        for unit in (flip_unit, social_unit):
            self.assertIn("NoNewPrivileges=yes", unit)
            self.assertIn("CapabilityBoundingSet=\n", unit)
            self.assertIn("ProtectHome=read-only", unit)
        self.assertIn("/notifications/flip_web_admin", flip_unit)
        self.assertNotIn("ReadWritePaths=/home/snh48-fan-hub/notifications\n", flip_unit)
        self.assertIn("Environment=TRANSFORMERS_OFFLINE=1", flip_unit)
        self.assertIn("Environment=HF_HUB_OFFLINE=1", flip_unit)
        self.assertIn("Environment=TMPDIR=/home/snh48-fan-hub/notifications/flip_web_admin/tmp", flip_unit)
        self.assertIn('"$FAN_ROOT/notifications/flip_web_admin/tmp"', hardening)
        for lock_path in (
            "/tmp/snh48-fan-hub-flip-web-rate.lock",
            "/tmp/snh48-fan-hub-flip-update.lock",
            "/tmp/snh48-fan-hub-transcription.lock",
            "/tmp/snh48-fan-hub-flip-accounts-manifest.lock",
        ):
            self.assertIn(f"ReadWritePaths={lock_path}", flip_unit)
            self.assertIn(lock_path, hardening)
        self.assertNotIn("ReadWritePaths=/tmp\n", flip_unit)
        self.assertIn("chmod 0600 \"$lock_path\"", hardening)
        self.assertIn("rm -f /etc/sudoers.d/snh48-web", hardening)
        self.assertFalse((ROOT / "deploy/privileged/snh48-web.sudoers").exists())


if __name__ == "__main__":
    unittest.main()
