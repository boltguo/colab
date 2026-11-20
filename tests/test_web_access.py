"""Access gate regression tests without a model engine."""
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from backend.core.app_factory import FeaturePlugin, create_feature_app
from backend.core.config import AppSettings
from backend.core.models import GpuStats
from backend.core.security import AuthState, SESSION_COOKIE, create_session, valid_session
from backend.features.registry import get_feature_plugin


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
        self.settings = AppSettings("gate-test", "127.0.0.1", 8188, self.root / "data", dist, "", True, self.root, access_password=self.key)
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

    def test_web_password_does_not_enable_api_authentication(self):
        self.assertEqual(self.client.get("/api/v1/health").status_code, 200)
        for path in ["/", "/assets/app.js", "/docs", "/redoc", "/openapi.json", "/auth/logout"]:
            response = self.client.get(path)
            self.assertEqual(response.status_code, 303, path)
            self.assertEqual(response.headers["location"], "/auth/login")
        for path in ["/api/v1/system", "/api/v1/tasks", "/api/v1/outputs/private.png"]:
            self.assertEqual(self.client.get(path).status_code, 200, path)
        system = self.client.get("/api/v1/system").json()
        self.assertTrue(system["web_auth_required"])
        self.assertFalse(system["auth_required"])
        self.assertFalse(system["api_key_configured"])
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
                                      replace(self.settings, data_dir=self.root / "api-data", api_key="api-test-key"))
        with TestClient(self.app) as client:
            for headers in [{"Authorization": "Bearer api-test-key"}, {"X-API-Key": "api-test-key"}]:
                self.assertEqual(client.get("/api/v1/tasks", headers=headers).status_code, 200)
            self.assertEqual(client.get("/api/v1/tasks?api_key=api-test-key").status_code, 200)
            self.assertEqual(client.get("/", headers={"Authorization": "Bearer api-test-key"}, follow_redirects=False).status_code, 303)

    def test_web_login_and_api_key_have_independent_permissions(self):
        self.assertEqual(self.client.post("/auth/api-key", json={"api_key": "external-key"}).status_code, 401)
        self.login()
        cookie = self.client.cookies.get(SESSION_COOKIE)
        # The browser can use the application before any external API key exists.
        system = self.client.get("/api/v1/system").json()
        self.assertTrue(system["web_auth_required"])
        self.assertFalse(system["api_key_configured"])
        self.assertEqual(self.client.post("/api/v1/tasks", json={"params": {}}).status_code, 200)
        response = self.client.post("/auth/api-key", json={"api_key": "external-key"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.cookies.get(SESSION_COOKIE), cookie)
        self.assertTrue(self.client.get("/api/v1/system").json()["api_key_configured"])
        response = self.client.post("/auth/api-key", json={"api_key": "replacement-key"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get("/").status_code, 200)
        self.client.cookies.clear()
        self.assertEqual(self.client.get("/api/v1/tasks", params={"api_key": self.key}).status_code, 401)
        self.assertEqual(self.client.get("/api/v1/tasks", headers={"Authorization": "Bearer external-key"}).status_code, 401)
        api_headers = {"Authorization": "Bearer replacement-key"}
        self.assertEqual(self.client.get("/api/v1/tasks", headers=api_headers).status_code, 200)
        self.assertEqual(self.client.get("/", headers=api_headers).status_code, 303)
        self.assertEqual(self.client.post("/auth/api-key", headers=api_headers, json={"api_key": "attacker-key"}).status_code, 401)
        self.assertEqual(self.client.post("/auth/login", data={"password": "replacement-key"}).status_code, 401)
        self.login()

    def test_api_key_survives_restart_and_web_password_rotation_without_plaintext_storage(self):
        self.login()
        self.assertEqual(self.client.post("/auth/api-key", json={"api_key": "persistent-key"}).status_code, 200)
        path = self.settings.data_dir / "api_key.json"
        self.assertNotIn("persistent-key", path.read_text())
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        rotated = create_feature_app(FeaturePlugin("gate-test", "Test", "", "Mock", "test", lambda p: p, lambda *args: {}),
                                     replace(self.settings, access_password="new-web-password"))
        with TestClient(rotated, base_url="https://studio.test", follow_redirects=False) as client:
            client.cookies.update(self.client.cookies)
            self.assertEqual(client.get("/").status_code, 303)
            self.assertEqual(client.get("/api/v1/tasks", headers={"Authorization": "Bearer persistent-key"}).status_code, 200)
            self.assertEqual(client.post("/auth/login", data={"password": "new-web-password"}).status_code, 303)

    def test_api_key_settings_validate_inputs_and_reject_symlinks(self):
        self.login()
        for key in ["short", "with whitespace", "中文密钥abcdefgh"]:
            self.assertEqual(self.client.post("/auth/api-key", json={"api_key": key}).status_code, 422)
        self.assertEqual(self.client.post("/auth/api-key", json={"api_key": "external-key"}, headers={"Origin": "https://other.test"}).status_code, 403)
        target = self.root / "outside.json"
        target.write_text('{}')
        (self.settings.data_dir / "api_key.json").symlink_to(target)
        with self.assertRaises(RuntimeError):
            AuthState(self.key, self.settings.data_dir)
        self.assertEqual(target.read_text(), '{}')

    def test_cookie_auth_rejects_cross_site_writes_and_websockets(self):
        self.assertEqual(self.client.post("/auth/login", data={"password": self.key}, headers={"Origin": "https://other.test"}).status_code, 403)
        self.login()
        self.assertEqual(self.client.post("/auth/api-key", json={"api_key": "external-key"}).status_code, 200)
        self.assertEqual(self.client.post("/api/v1/tasks", json={"params": {}}, headers={"Origin": "https://other.test"}).status_code, 403)
        with self.client.websocket_connect("wss://studio.test/api/v1/tasks/missing/ws", headers={"Origin": "https://studio.test"}) as ws:
            self.assertIn("error", ws.receive_json())
        with self.assertRaises(WebSocketDisconnect) as error:
            with self.client.websocket_connect("wss://studio.test/api/v1/tasks/missing/ws", headers={"Origin": "https://other.test"}):
                pass
        self.assertEqual(error.exception.code, 4401)

    def test_clearing_api_key_persists_anonymous_api_access_without_unlocking_web(self):
        self.login()
        cookie = self.client.cookies.get(SESSION_COOKIE)
        self.assertEqual(self.client.post("/auth/api-key", json={"api_key": "external-key"}).status_code, 200)
        self.assertEqual(self.client.post("/auth/api-key", json={"api_key": ""}).json(), {"configured": False})
        self.assertEqual(self.client.cookies.get(SESSION_COOKIE), cookie)
        state = AuthState(self.key, self.settings.data_dir, "environment-key")
        self.assertFalse(state.api_required)
        self.client.cookies.clear()
        self.assertEqual(self.client.get("/api/v1/tasks").status_code, 200)
        self.assertEqual(self.client.get("/").status_code, 303)
        self.assertEqual(self.client.post("/auth/api-key", json={"api_key": "attacker-key"}).status_code, 401)

    def test_openai_endpoints_allow_no_key_until_a_key_is_explicitly_configured(self):
        settings = replace(self.settings, feature="qwen3.8-27b", data_dir=self.root / "qwen-data")
        app = create_feature_app(get_feature_plugin("qwen3.8-27b"), settings)
        payload = {"model": "Qwen/Qwen3.8-27B", "messages": [{"role": "user", "content": "测试"}], "stream": True, "max_tokens": 32}
        with TestClient(app, base_url="https://studio.test", follow_redirects=False) as client:
            self.assertEqual(client.get("/").status_code, 303)
            self.assertEqual(client.get("/v1/models").status_code, 200)
            response = client.post("/v1/chat/completions", json=payload)
            self.assertEqual(response.status_code, 200)
            self.assertIn("data: [DONE]", response.text)
            self.assertEqual(client.post("/auth/login", data={"password": self.key}).status_code, 303)
            self.assertEqual(client.post("/auth/api-key", json={"api_key": "external-key"}).status_code, 200)
            cookie = client.cookies.get(SESSION_COOKIE)
            client.cookies.clear()
            self.assertEqual(client.get("/v1/models").status_code, 401)
            response = client.post("/v1/chat/completions", json=payload)
            self.assertEqual(response.status_code, 401)
            self.assertIn("API Key", response.json()["detail"])
            self.assertNotIn("登录", response.json()["detail"])
            self.assertEqual(client.get("/v1/models", headers={"Authorization": "Bearer external-key"}).status_code, 200)
            client.cookies.set(SESSION_COOKIE, cookie, domain="studio.test", path="/")
            self.assertEqual(client.post("/auth/api-key", json={"api_key": ""}).status_code, 200)
            client.cookies.clear()
            self.assertEqual(client.get("/v1/models").status_code, 200)
            self.assertEqual(client.post("/v1/chat/completions", json=payload).status_code, 200)
            self.assertEqual(client.get("/").status_code, 303)

    def test_session_cannot_be_tampered_with_reused_after_rotation_or_expiry(self):
        token = create_session(self.key)
        self.assertTrue(valid_session(token, self.key))
        self.assertFalse(valid_session(token + "a", self.key))
        self.assertFalse(valid_session(token, "changed-key"))
        with patch("backend.core.security.time.time", return_value=10**12):
            self.assertFalse(valid_session(token, self.key))

    def test_login_page_defaults_to_english_and_honors_accept_language(self):
        default_page = self.client.get("/auth/login")
        self.assertEqual(default_page.status_code, 200)
        self.assertIn('<html lang="en">', default_page.text)
        self.assertIn("Access Password", default_page.text)

        zh_page = self.client.get("/auth/login", headers={"Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"})
        self.assertEqual(zh_page.status_code, 200)
        self.assertIn('<html lang="zh-CN">', zh_page.text)
        self.assertIn("访问密码", zh_page.text)

        en_pref = self.client.get("/auth/login", headers={"Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8"})
        self.assertEqual(en_pref.status_code, 200)
        self.assertIn('<html lang="en">', en_pref.text)

        bad_en = self.client.post("/auth/login", data={"password": "wrong"})
        self.assertEqual(bad_en.status_code, 401)
        self.assertIn("Incorrect password. Please try again.", bad_en.text)

        bad_zh = self.client.post(
            "/auth/login",
            data={"password": "wrong"},
            headers={"Accept-Language": "zh-CN,zh;q=0.9"},
        )
        self.assertEqual(bad_zh.status_code, 401)
        self.assertIn("密码不正确，请重试。", bad_zh.text)


if __name__ == "__main__":
    unittest.main()
