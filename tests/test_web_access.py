"""Access gate regression tests without a model engine."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from backend.core.app_factory import FeaturePlugin, create_feature_app
from backend.core.config import AppSettings
from backend.core.models import GpuStats
from backend.core.security import SESSION_COOKIE, create_session, valid_session


class WebAccessTests(unittest.TestCase):
    key = "测试访问密码-2026"

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        dist = self.root / "dist"
        (dist / "assets").mkdir(parents=True)
        (dist / "index.html").write_text('<!doctype html><title>private-studio</title><script src="/assets/app.js"></script>')
        (dist / "assets/app.js").write_text('const privateAsset = true;')
        self.settings = AppSettings("gate-test", "127.0.0.1", 8188, self.root / "data", dist, self.key, True, self.root)
        plugin = FeaturePlugin("gate-test", "Test", "", "Mock", "test", lambda p: p, lambda *args: {})
        self.app = create_feature_app(plugin, self.settings)
        (self.root / "data/outputs/private.png").write_bytes(b"private-output")
        probe = patch("backend.core.app_factory.probe_gpu_stats", return_value=GpuStats())
        probe.start()
        self.addCleanup(probe.stop)
        self.client = self.enterContext(TestClient(self.app, base_url="https://studio.test", follow_redirects=False))

    def login(self):
        response = self.client.post("/auth/login", data={"password": self.key}, headers={"Origin": "https://studio.test"})
        self.assertEqual(response.status_code, 303)
        return response

    def test_anonymous_visitors_cannot_view_studio_docs_telemetry_or_media(self):
        self.assertEqual(self.client.get("/api/v1/health").status_code, 200)
        for path in ["/", "/assets/app.js", "/docs", "/redoc", "/openapi.json", "/auth/logout"]:
            response = self.client.get(path)
            self.assertEqual(response.status_code, 303, path)
            self.assertEqual(response.headers["location"], "/auth/login")
        for path in ["/api/v1/system", "/api/v1/tasks", "/api/v1/outputs/private.png", "/v1/models"]:
            self.assertEqual(self.client.get(path).status_code, 401, path)
        response = self.client.post("/auth/login", data={"password": "wrong"})
        self.assertEqual(response.status_code, 401)
        self.assertNotIn(SESSION_COOKIE, self.client.cookies)
        self.assertNotIn(self.key, response.text)

    def test_login_cookie_unlocks_private_resources_and_logout_relocks(self):
        response = self.login()
        cookie = response.headers["set-cookie"]
        for flag in ["HttpOnly", "Secure", "SameSite=strict"]:
            self.assertIn(flag, cookie)
        self.assertNotIn(self.key, cookie)
        for path in ["/", "/assets/app.js", "/docs", "/openapi.json", "/api/v1/system"]:
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, path)
            self.assertIn("no-store", response.headers["cache-control"])
        self.assertTrue(self.client.get("/api/v1/system").json()["browser_authenticated"])
        self.assertEqual(self.client.get("/api/v1/outputs/private.png").content, b"private-output")
        self.assertEqual(self.client.post("/auth/logout").status_code, 303)
        self.assertEqual(self.client.get("/").status_code, 303)

    def test_api_tokens_still_work_without_a_browser_cookie(self):
        # HTTP header credentials are ASCII; the browser login also supports Unicode passwords.
        self.app = create_feature_app(FeaturePlugin("gate-test", "Test", "", "Mock", "test", lambda p: p, lambda *args: {}),
                                      AppSettings("gate-test", "127.0.0.1", 8188, self.root / "api-data", self.settings.dist_dir, "api-test-key", True, self.root))
        with TestClient(self.app) as client:
            for headers in [{"Authorization": "Bearer api-test-key"}, {"X-API-Key": "api-test-key"}]:
                self.assertEqual(client.get("/api/v1/tasks", headers=headers).status_code, 200)
            self.assertEqual(client.get("/api/v1/tasks?api_key=api-test-key").status_code, 200)

    def test_cookie_auth_rejects_cross_site_writes_and_websockets(self):
        self.assertEqual(self.client.post("/auth/login", data={"password": self.key}, headers={"Origin": "https://other.test"}).status_code, 403)
        self.login()
        self.assertEqual(self.client.post("/api/v1/tasks", json={"params": {}}, headers={"Origin": "https://other.test"}).status_code, 403)
        with self.client.websocket_connect("wss://studio.test/api/v1/tasks/missing/ws", headers={"Origin": "https://studio.test"}) as ws:
            self.assertIn("error", ws.receive_json())
        with self.assertRaises(WebSocketDisconnect) as error:
            with self.client.websocket_connect("wss://studio.test/api/v1/tasks/missing/ws", headers={"Origin": "https://other.test"}):
                pass
        self.assertEqual(error.exception.code, 4401)

    def test_session_cannot_be_tampered_with_reused_after_rotation_or_expiry(self):
        token = create_session(self.key)
        self.assertTrue(valid_session(token, self.key))
        self.assertFalse(valid_session(token + "a", self.key))
        self.assertFalse(valid_session(token, "changed-key"))
        with patch("backend.core.security.time.time", return_value=10**12):
            self.assertFalse(valid_session(token, self.key))


if __name__ == "__main__":
    unittest.main()
