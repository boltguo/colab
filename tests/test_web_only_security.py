"""Security regressions for web-only Studios behind Google Colab native proxy."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from backend.core.app_factory import create_feature_app
from backend.core.config import AppSettings
from backend.core.models import GpuStats
from backend.features.registry import get_feature_plugin

DISABLED_ROUTES = (
    "/docs",
    "/redoc",
    "/openapi.json",
    "/auth/login",
    "/auth/logout",
    "/auth/api-key",
    "/v1/models",
    "/v1/chat/completions",
    "/v1/messages",
)


class WebOnlySecurityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        gpu = patch("backend.core.app_factory.probe_gpu_stats", return_value=GpuStats())
        gpu.start()
        self.addCleanup(gpu.stop)

    def _build_client(self, feature="indextts-2.5", *, with_dist=True, proxy_origin="", write_proxy_info=False):
        data_dir = self.root / f"data_{feature}_{with_dist}_{bool(proxy_origin)}_{write_proxy_info}"
        data_dir.mkdir(parents=True, exist_ok=True)
        if write_proxy_info:
            (data_dir / "proxy_info.json").write_text(
                json.dumps({"public_url": "https://8188-file.prod.r.colab.dev", "access_mode": "colab"}),
                encoding="utf-8",
            )
        dist = None
        if with_dist:
            dist = self.root / f"dist_{feature}_{bool(proxy_origin)}_{write_proxy_info}"
            (dist / "assets").mkdir(parents=True, exist_ok=True)
            (dist / "index.html").write_text("<!doctype html><html><body>Studio</body></html>", encoding="utf-8")
        settings = AppSettings(
            feature=feature,
            host="127.0.0.1",
            port=8188,
            data_dir=data_dir,
            dist_dir=dist,
            mock_inference=True,
            repo_root=Path(__file__).resolve().parents[1],
            proxy_origin=proxy_origin,
        )
        app = create_feature_app(get_feature_plugin(feature), settings)
        return app, TestClient(app)

    def test_docs_auth_and_external_v1_gateway_are_disabled_and_return_404(self):
        for feature in ("indextts-2.5", "qwen3.8-27b", "h3-character-swap"):
            for with_dist in (True, False):
                with self.subTest(feature=feature, with_dist=with_dist):
                    app, client = self._build_client(feature, with_dist=with_dist)
                    self.assertIsNone(app.docs_url)
                    self.assertIsNone(app.redoc_url)
                    self.assertIsNone(app.openapi_url)
                    with client:
                        for path in DISABLED_ROUTES:
                            get_resp = client.get(path)
                            self.assertEqual(get_resp.status_code, 404, f"GET {path} should 404 on {feature}")
                            post_resp = client.post(path)
                            self.assertIn(post_resp.status_code, (404, 405), f"POST {path} should not succeed")
                        self.assertEqual(client.get("/api/v1/health").status_code, 200)
                        if not with_dist:
                            root = client.get("/")
                            self.assertEqual(root.status_code, 200)
                            self.assertNotIn("docs", root.json())

    def test_no_wildcard_cors_and_same_origin_write_and_websocket_protection(self):
        proxy_origin = "https://8188-test.prod.r.colab.dev"
        _, client = self._build_client("qwen3.8-27b", proxy_origin=proxy_origin)
        with client:
            health = client.get("/api/v1/health", headers={"Origin": "https://evil.example"})
            self.assertEqual(health.status_code, 200)
            self.assertNotIn("access-control-allow-origin", health.headers)

            # Cross-origin POST is rejected (403).
            cross_post = client.post(
                "/api/v1/generate",
                json={"prompt": "hi"},
                headers={"Origin": "https://evil.example"},
            )
            self.assertEqual(cross_post.status_code, 403)

            # Same-origin via configured COLAB_PROXY_ORIGIN succeeds.
            proxy_post = client.post(
                "/api/v1/generate",
                json={"prompt": "hi"},
                headers={"Origin": proxy_origin},
            )
            self.assertEqual(proxy_post.status_code, 200)

            # Same-origin via Host header (TLS terminated at Colab proxy, forwarded without X-Forwarded-Proto).
            _, bare_client = self._build_client("indextts-2.5", proxy_origin="")
            with bare_client:
                host_matched = bare_client.post(
                    "/api/v1/generate",
                    json={"text": "hello", "speaker_audio": "missing.wav"},
                    headers={"Host": "8188-hostonly.prod.r.colab.dev", "Origin": "https://8188-hostonly.prod.r.colab.dev"},
                )
                self.assertEqual(host_matched.status_code, 400)

            # Same-origin WebSocket succeeds; cross-origin WebSocket is rejected.
            with client.websocket_connect(
                "/api/v1/tasks/missing/ws",
                headers={"Origin": proxy_origin},
            ) as ws:
                self.assertIn("error", ws.receive_json())

            with self.assertRaises(WebSocketDisconnect):
                with client.websocket_connect(
                    "/api/v1/tasks/missing/ws",
                    headers={"Origin": "https://evil.example"},
                ):
                    pass

    def test_system_status_reports_colab_proxy_and_omits_auth_or_tunnel_fields(self):
        _, local_client = self._build_client("indextts-2.5")
        with local_client:
            local_sys = local_client.get("/api/v1/system").json()
            self.assertEqual(local_sys["access_mode"], "local")
            for removed_key in (
                "auth_required",
                "web_auth_required",
                "api_key_configured",
                "browser_authenticated",
                "tunnel_mode",
            ):
                self.assertNotIn(removed_key, local_sys)

        _, env_proxy_client = self._build_client(
            "indextts-2.5",
            proxy_origin="https://8188-env.prod.r.colab.dev",
        )
        with env_proxy_client:
            sys_env = env_proxy_client.get("/api/v1/system").json()
            self.assertEqual(sys_env["access_mode"], "colab")
            self.assertEqual(sys_env["public_url"], "https://8188-env.prod.r.colab.dev")

        _, file_proxy_client = self._build_client("indextts-2.5", write_proxy_info=True)
        with file_proxy_client:
            sys_file = file_proxy_client.get("/api/v1/system").json()
            self.assertEqual(sys_file["access_mode"], "colab")
            self.assertEqual(sys_file["public_url"], "https://8188-file.prod.r.colab.dev")

        with local_client:
            sys_hdr = local_client.get(
                "/api/v1/system",
                headers={"Host": "8188-proxy.colab.googleusercontent.com", "X-Forwarded-Proto": "https"},
            ).json()
            self.assertEqual(sys_hdr["access_mode"], "colab")
            self.assertEqual(sys_hdr["public_url"], "https://8188-proxy.colab.googleusercontent.com")


if __name__ == "__main__":
    unittest.main()
