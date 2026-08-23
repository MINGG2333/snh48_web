from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi import Request, Response

from website import visitor_observation
from website.ob_api import router as ob_api
from website.track_api import router as track_api


class VisitorObservationTests(unittest.TestCase):
    def test_coarse_device_description_does_not_store_versions(self) -> None:
        iphone = visitor_observation.describe_user_agent(
            "Mozilla/5.0 (iPhone; CPU iPhone OS 18_7 like Mac OS X) "
            "AppleWebKit/605.1.15 Version/18.7.5 Mobile Safari/604.1"
        )
        windows = visitor_observation.describe_user_agent(
            "Mozilla/5.0 (PC; Windows NT 10.0; Win64; x64) "
            "Chrome/132.0.0.0 Safari/537.36 htbrowser/2.0.21"
        )

        self.assertEqual(iphone["label"], "iPhone · Safari")
        self.assertEqual(windows["label"], "Windows 电脑 · 华为浏览器")
        self.assertNotIn("18.7", json.dumps(iphone, ensure_ascii=False))
        self.assertNotIn("132", json.dumps(windows, ensure_ascii=False))

    def test_page_view_log_contains_ip_and_device_but_no_location(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            session = Path(tmp) / "session_20260816_120000"
            record = visitor_observation.record_page_view(
                session,
                visitor_id="visitor_abcdefgh_12345678",
                client_id="user_abcdefgh_12345678",
                ip="203.0.113.8",
                user_agent="Mozilla/5.0 (iPhone) Version/18.0 Safari/604.1",
                page="/room",
            )

            self.assertIsNotNone(record)
            assert record is not None
            self.assertEqual(record["ip"], "203.0.113.8")
            self.assertEqual(record["device"]["label"], "iPhone · Safari")
            self.assertNotIn("city", record)
            self.assertNotIn("latitude", record)
            self.assertNotIn("longitude", record)
            self.assertNotIn("user_agent", record)

            loaded = visitor_observation.load_page_views(Path(tmp))
            self.assertEqual(len(loaded), 1)
            self.assertEqual(loaded[0]["page"], "/room")

    def test_invalid_identifiers_are_not_written(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            session = Path(tmp) / "session_invalid"
            record = visitor_observation.record_page_view(
                session,
                visitor_id="../../visitor",
                client_id="../../client",
                ip="203.0.113.8",
                user_agent="test",
                page="/",
            )
            self.assertIsNone(record)
            self.assertFalse((session / visitor_observation.PAGE_VIEWS_FILENAME).exists())

    def test_ob_groups_two_sessions_from_one_browser_across_ips(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            log_root = root / "interaction_logs"
            session = log_root / "session_20260816_120000"
            session.mkdir(parents=True)

            first_client = "user_aaaaaaaa_12345678"
            second_client = "user_bbbbbbbb_12345679"
            legacy_client = "user_cccccccc_12345680"
            visitor_id = "visitor_abcdefgh_12345678"

            ip_clients_path = root / "ip_clients.json"
            ip_clients_path.write_text(json.dumps({
                "203.0.113.8": [first_client, legacy_client],
                "198.51.100.4": [second_client],
            }), encoding="utf-8")

            for client_id, time_str, page in (
                (first_client, "2026-08-16 12:00:00", "/room"),
                (second_client, "2026-08-16 12:05:00", "/room/gift-senders"),
                (legacy_client, "2026-08-16 12:10:00", "/timeline"),
            ):
                (session / f"user_{client_id}_events.md").write_text(
                    "# 用户操作记录\n\n"
                    "| 时间 | 类型 | 用户 | 内容 | 操作记录 |\n"
                    "|------|------|------|------|----------|\n"
                    f"| {time_str} | 📄 页面浏览 | `{client_id}` | 页面：`{page}` | - |\n",
                    encoding="utf-8",
                )

            with mock.patch.object(visitor_observation, "datetime") as fake_datetime:
                fake_datetime.now.return_value = __import__("datetime").datetime.fromisoformat(
                    "2026-08-16T12:00:00+08:00"
                )
                visitor_observation.record_page_view(
                    session,
                    visitor_id=visitor_id,
                    client_id=first_client,
                    ip="203.0.113.8",
                    user_agent="Mozilla/5.0 (iPhone) Version/18.0 Safari/604.1",
                    page="/room",
                )
                fake_datetime.now.return_value = __import__("datetime").datetime.fromisoformat(
                    "2026-08-16T12:05:00+08:00"
                )
                visitor_observation.record_page_view(
                    session,
                    visitor_id=visitor_id,
                    client_id=second_client,
                    ip="198.51.100.4",
                    user_agent="Mozilla/5.0 (iPhone) Version/18.0 Safari/604.1",
                    page="/room/gift-senders",
                )

            with (
                mock.patch.object(ob_api, "IP_CLIENTS_FILE", ip_clients_path),
                mock.patch.object(ob_api, "READ_NOTIFS_FILE", root / "read_notifications.json"),
                mock.patch.object(ob_api, "LOG_ROOT", log_root),
                mock.patch.object(ob_api, "list_requests", return_value=[]),
            ):
                response = Response()
                payload = ob_api.get_ob_data(response, _=True)

            self.assertEqual(response.headers["Cache-Control"], "no-store")
            self.assertEqual(payload["stats"]["estimated_visitors"], 1)
            self.assertEqual(payload["stats"]["stable_profiles"], 1)
            self.assertEqual(payload["stats"]["legacy_sessions"], 1)

            stable = next(group for group in payload["groups"] if not group["is_legacy"])
            self.assertEqual(stable["visitor_id"], visitor_id)
            self.assertEqual(set(stable["users"]), {first_client, second_client})
            self.assertEqual(len(stable["visits"]), 2)
            self.assertEqual({item["value"] for item in stable["networks"]}, {
                "203.0.113.8",
                "198.51.100.4",
            })
            self.assertEqual(stable["devices"][0]["value"], "iPhone · Safari")

            legacy = next(group for group in payload["groups"] if group["is_legacy"])
            self.assertEqual(legacy["users"], [legacy_client])
            self.assertEqual(legacy["visits"], [])
            self.assertEqual(legacy["networks"][0]["value"], "203.0.113.8")

            associations = payload["association_groups"]
            self.assertEqual(len(associations), 1)
            association = associations[0]
            self.assertEqual(
                set(association["member_group_ids"]),
                {stable["id"], legacy["id"]},
            )
            self.assertEqual(association["shared_ips"][0]["value"], "203.0.113.8")
            self.assertFalse(association["shared_ips"][0]["historical_only"])

            graph = payload["ip_network_graph"]
            self.assertEqual(len(graph["nodes"]), 2)
            self.assertEqual(len(graph["links"]), 1)
            self.assertEqual(graph["links"][0]["shared_member_count"], 1)
            self.assertEqual(graph["links"][0]["shared_member_ids"], [stable["id"]])

    def test_ip_association_groups_use_transitive_links_without_changing_profiles(self) -> None:
        groups = [
            {
                "id": 0,
                "is_legacy": False,
                "networks": [{"value": "203.0.113.1", "historical_only": False}],
                "visits": [{"page": "/a"}],
                "notification_count": 0,
                "recent_time": "2026-08-16 12:00:00",
            },
            {
                "id": 1,
                "is_legacy": False,
                "networks": [
                    {"value": "203.0.113.1", "historical_only": False},
                    {"value": "198.51.100.2", "historical_only": True},
                ],
                "visits": [{"page": "/b"}],
                "notification_count": 0,
                "recent_time": "2026-08-16 12:01:00",
            },
            {
                "id": 2,
                "is_legacy": True,
                "networks": [{"value": "198.51.100.2", "historical_only": True}],
                "visits": [],
                "notification_count": 0,
                "recent_time": "2026-08-16 12:02:00",
            },
            {
                "id": 3,
                "is_legacy": True,
                "networks": [{"value": "192.0.2.3", "historical_only": True}],
                "visits": [],
                "notification_count": 0,
                "recent_time": "2026-08-16 12:03:00",
            },
        ]

        associations = ob_api._build_ip_association_groups(groups)
        self.assertEqual(len(associations), 2)
        linked = next(item for item in associations if item["member_count"] == 3)
        self.assertEqual(set(linked["member_group_ids"]), {0, 1, 2})
        self.assertEqual(
            {item["value"] for item in linked["shared_ips"]},
            {"203.0.113.1", "198.51.100.2"},
        )
        self.assertTrue(
            next(item for item in linked["shared_ips"] if item["value"] == "198.51.100.2")["historical_only"]
        )
        singleton = next(item for item in associations if item["member_count"] == 1)
        self.assertEqual(singleton["member_group_ids"], [3])

    def test_ip_network_graph_edges_count_shared_profiles_and_mark_history(self) -> None:
        groups = [
            {
                "id": 0,
                "is_legacy": False,
                "networks": [
                    {"value": "203.0.113.1", "historical_only": False},
                    {"value": "198.51.100.2", "historical_only": False},
                ],
                "visits": [{"page": "/a"}],
            },
            {
                "id": 1,
                "is_legacy": False,
                "networks": [
                    {"value": "203.0.113.1", "historical_only": False},
                    {"value": "198.51.100.2", "historical_only": True},
                ],
                "visits": [{"page": "/b"}],
            },
            {
                "id": 2,
                "is_legacy": True,
                "networks": [
                    {"value": "203.0.113.1", "historical_only": True},
                    {"value": "198.51.100.2", "historical_only": True},
                ],
                "visits": [],
            },
            {
                "id": 3,
                "is_legacy": True,
                "networks": [{"value": "192.0.2.3", "historical_only": True}],
                "visits": [],
            },
        ]

        graph = ob_api._build_ip_network_graph(groups)
        self.assertEqual(len(graph["nodes"]), 3)
        link = next(item for item in graph["links"] if item["shared_member_count"] == 3)
        self.assertEqual(link["stable_shared_count"], 2)
        self.assertEqual(link["legacy_shared_count"], 1)
        self.assertFalse(link["historical_only"])
        self.assertTrue(any(
            item["ip"] == "192.0.2.3" and item["member_count"] == 1
            for item in graph["nodes"]
        ))

    def test_tracker_keeps_qa_session_id_separate_from_browser_profile(self) -> None:
        tracker = (
            Path(__file__).resolve().parents[1] / "website" / "static" / "js" / "tracker.js"
        ).read_text(encoding="utf-8")
        self.assertIn("sessionStorage.getItem('client_id')", tracker)
        self.assertNotIn("localStorage", tracker)
        self.assertNotIn("payload.visitor_id", tracker)
        self.assertNotIn("canvas", tracker.lower())
        self.assertNotIn("geolocation", tracker.lower())

    def test_server_issued_device_cookie_is_signed_and_stable(self) -> None:
        visitor_id, should_set = visitor_observation.resolve_device_cookie(None)
        self.assertTrue(should_set)
        self.assertTrue(visitor_observation.is_valid_visitor_id(visitor_id))

        cookie = visitor_observation.make_device_cookie(visitor_id)
        resolved, replacement_needed = visitor_observation.resolve_device_cookie(cookie)
        self.assertEqual(resolved, visitor_id)
        self.assertFalse(replacement_needed)
        self.assertIsNone(visitor_observation.read_device_cookie(cookie + "tampered"))

    def test_page_view_route_issues_cookie_and_records_server_profile(self) -> None:
        request = Request(
            {
                "type": "http",
                "http_version": "1.1",
                "method": "POST",
                "scheme": "https",
                "path": "/api/track/event",
                "raw_path": b"/api/track/event",
                "query_string": b"",
                "headers": [(b"user-agent", b"Mozilla/5.0 (iPhone) Safari/604.1")],
                "client": ("203.0.113.9", 443),
                "server": ("testserver", 443),
            }
        )
        response = Response()
        req = track_api.TrackEventRequest(
            client_id="user_cookie_12345678",
            event_type="page_view",
            data={"page": "/room"},
        )

        with (
            mock.patch.object(track_api, "get_session_dir", return_value=Path("/tmp")),
            mock.patch.object(track_api, "_track_ip_to_client"),
            mock.patch.object(track_api, "check_track_event_limit"),
            mock.patch.object(track_api, "record_user_event"),
            mock.patch.object(track_api, "record_page_view") as record,
        ):
            result = track_api.track_event(req, request, response)

        self.assertEqual(result, {"success": True})
        self.assertIn("ob_device_profile=", response.headers["set-cookie"])
        self.assertIn("HttpOnly", response.headers["set-cookie"])
        record.assert_called_once()
        self.assertTrue(record.call_args.kwargs["visitor_id"].startswith("visitor_"))

    def test_ob_template_explains_identity_and_filters_profiles_by_page(self) -> None:
        template = (
            Path(__file__).resolve().parents[1] / "website" / "templates" / "ob.html"
        ).read_text(encoding="utf-8")

        self.assertIn('id="recordsTitle">用户记录</h2>', template)
        self.assertIn('id="pageFilterInput"', template)
        self.assertIn('id="pageFilterOptions"', template)
        self.assertIn("function normalizePagePath(value)", template)
        self.assertIn("function groupPagePaths(group)", template)
        self.assertIn("filter_ob_users_by_page", template)
        self.assertIn('id="inboxListToggle"', template)
        self.assertIn('id="inboxListWrap"', template)
        self.assertIn("setInboxListOpen(false)", template)
        self.assertIn("IP 关联组", template)
        self.assertIn("共享 IP 可能对应多个自然人", template)
        self.assertIn("不是硬件指纹", template)
        self.assertIn("association-group-header", template)
        self.assertIn("档案尾码", template)
        self.assertIn('id="networkVisualization"', template)
        self.assertIn('id="ipNetworkSvg"', template)
        self.assertIn('id="networkMemberGrid"', template)
        self.assertIn("function renderNetworkGraph()", template)
        self.assertIn("function showSessionTooltip", template)
        self.assertIn("select_ob_ip_node", template)
        self.assertIn('id="network3dCanvas"', template)
        self.assertIn('id="obLiveToggle"', template)
        self.assertIn('id="obRefreshNow"', template)
        self.assertIn("networkGraphSignature", template)
        self.assertIn("captureNetwork3dView", template)
        self.assertIn("copyNetwork3dNodePositions", template)
        self.assertIn("obDataRefreshBusy", template)
        self.assertIn("d3ReheatSimulation", template)
        self.assertIn("发现新数据，结束当前操作后更新", template)
        self.assertIn("ForceGraph3D", template)
        self.assertIn("createThreeIpNode", template)
        self.assertIn("shared_member_count", template)
        self.assertIn("ip_network_graph", template)
        self.assertIn("id=\"notifNav\"", template)
        self.assertIn("'visit-session'", template)
        self.assertNotIn("className = 'group-users'", template)
        self.assertNotIn("id=\"modalUsers\"", template)


if __name__ == "__main__":
    unittest.main()
