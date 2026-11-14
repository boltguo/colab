"""Five Studio API smoke flows in mock mode; no model weights or GPU required."""
from contextlib import contextmanager
import io
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch
import wave

from fastapi.testclient import TestClient
from PIL import Image

from backend.core.app_factory import create_feature_app
from backend.core.config import AppSettings
from backend.core.models import GpuStats
from backend.features.registry import get_feature_plugin


class StudioApiSmokeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.api_key = "studio-smoke-test-key"
        self.headers = {"Authorization": f"Bearer {self.api_key}"}
        # Hardware telemetry is orthogonal to the API flow and must not initialize CUDA.
        gpu = patch("backend.core.app_factory.probe_gpu_stats", return_value=GpuStats())
        gpu.start()
        self.addCleanup(gpu.stop)
        # Fail immediately if a mock Studio accidentally calls an inference engine.
        for target in (
            "backend.core.comfy_client.ComfyClient.run_prompt",
            "backend.features.qwen3_8_27b.runner._open_vllm_connection",
            "backend.features.indextts_2_5.runner.ENGINE_MANAGER.get_engine",
        ):
            guard = patch(target, side_effect=AssertionError("Mock flow must not load an inference engine"))
            guard.start()
            self.addCleanup(guard.stop)

    @contextmanager
    def studio(self, feature):
        dist = self.root / "dist" / feature
        assets = dist / "assets"
        assets.mkdir(parents=True)
        (dist / "index.html").write_text(
            f'<!doctype html><title>{feature}</title><script type="module" src="/assets/app.js"></script>',
            encoding="utf-8",
        )
        (assets / "app.js").write_text("export const ready = true;", encoding="utf-8")
        settings = AppSettings(
            feature=feature, host="127.0.0.1", port=8188,
            data_dir=self.root / "data" / feature, dist_dir=dist,
            api_key=self.api_key, mock_inference=True,
            repo_root=Path(__file__).resolve().parents[1],
        )
        app = create_feature_app(get_feature_plugin(feature), settings)
        with TestClient(app) as client:
            health = client.get("/api/v1/health")
            self.assertEqual(health.status_code, 200)
            self.assertEqual(health.json()["feature"], feature)
            system = client.get("/api/v1/system")
            self.assertEqual(system.status_code, 200)
            self.assertTrue(system.json()["mock_mode"])
            self.assertTrue(system.json()["auth_required"])
            self.assertEqual(client.get("/api/v1/tasks").status_code, 401)
            self.assertEqual(client.get("/api/v1/tasks", headers={"X-API-Key": "wrong"}).status_code, 401)
            index = client.get("/")
            self.assertIn(feature, index.text)
            self.assertIn('data-cfasync="false"', index.text)
            self.assertIn("no-transform", index.headers["cache-control"])
            asset = client.get("/assets/app.js")
            self.assertEqual(asset.status_code, 200)
            self.assertIn("no-transform", asset.headers["cache-control"])
            self.assertEqual(client.get("/api/v1/does-not-exist").status_code, 404)
            yield client

    def upload(self, client, filename, data, content_type):
        response = client.post(
            "/api/v1/files", files={"file": (filename, data, content_type)}, headers=self.headers,
        )
        self.assertEqual(response.status_code, 200, response.text)
        upload = response.json()
        self.assertEqual(upload["size_bytes"], len(data))
        self.assertEqual(client.get(upload["url"]).status_code, 401)
        # Media elements authenticate through a query parameter, unlike API fetches.
        preview = client.get(upload["url"], params={"api_key": self.api_key})
        self.assertEqual(preview.content, data)
        return upload["file_id"]

    def generate(self, client, payload):
        self.assertEqual(client.post("/api/v1/generate", json=payload).status_code, 401)
        submitted = client.post("/api/v1/generate", json=payload, headers=self.headers)
        self.assertEqual(submitted.status_code, 200, submitted.text)
        self.assertEqual(submitted.json()["status"], "queued")
        task_id = submitted.json()["task_id"]
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            response = client.get(f"/api/v1/tasks/{task_id}", headers=self.headers)
            self.assertEqual(response.status_code, 200, response.text)
            task = response.json()
            if task["status"] in {"succeeded", "failed", "cancelled"}:
                break
            time.sleep(0.025)
        else:
            self.fail("Mock task did not finish within 15 seconds")
        self.assertEqual(task["status"], "succeeded", task.get("error"))
        self.assertEqual(task["progress"], 1)
        self.assertTrue(task["result"]["mock"])
        recent = client.get("/api/v1/tasks", params={"limit": 100}, headers=self.headers).json()["items"]
        self.assertEqual(recent[0]["task_id"], task_id)
        self.assertEqual(recent[0]["params"], task["params"])
        self.assertEqual(recent[0]["result"], task["result"])
        return task["result"]

    def download(self, client, result, key):
        self.assertEqual(client.get(result[key]).status_code, 401)
        response = client.get(result[key], params={"download": "true"}, headers=self.headers)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn("attachment", response.headers["content-disposition"])
        self.assertIn("no-transform", response.headers["cache-control"])
        self.assertEqual(len(response.content), result["size_bytes"])
        self.assertGreater(len(response.content), 32)
        return response.content

    @staticmethod
    def image_bytes():
        data = io.BytesIO()
        Image.new("RGB", (64, 48), (80, 120, 160)).save(data, format="PNG")
        return data.getvalue()

    def test_indextts_audio_upload_generate_and_download(self):
        audio = io.BytesIO()
        with wave.open(audio, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(16000)
            wav.writeframes(b"\0\0" * 4000)
        with self.studio("indextts-2.5") as client:
            ref = self.upload(client, "voice.wav", audio.getvalue(), "audio/wav")
            result = self.generate(client, {
                "text": "你好。", "speaker_audio": ref, "seed": 42,
                "output_format": "wav", "loudness_norm": False,
            })
            output = self.download(client, result, "audio_url")
            with wave.open(io.BytesIO(output), "rb") as wav:
                self.assertGreater(wav.getnframes(), 0)
            self.assertEqual(result["speaker_audio_ref"], ref)
            self.assertEqual(result["subtitle_timing"], "estimated")

    def test_qwen_image_reference_upload_generate_and_download(self):
        with self.studio("qwen-image-2.1") as client:
            ref = self.upload(client, "reference.png", self.image_bytes(), "image/png")
            result = self.generate(client, {
                "mode": "img2img", "prompt": "提高画面亮度", "reference_images": [ref],
                "aspect_ratio": "custom", "width": 256, "height": 256,
                "steps": 1, "seed": 42,
            })
            output = self.download(client, result, "image_url")
            with Image.open(io.BytesIO(output)) as image:
                self.assertEqual(image.size, (256, 256))
            self.assertEqual(len(result["images"]), 1)

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "ffmpeg/ffprobe not installed")
    def test_minimax_keyframe_upload_generate_and_download(self):
        with self.studio("minimax-h3") as client:
            ref = self.upload(client, "first-frame.png", self.image_bytes(), "image/png")
            result = self.generate(client, {
                "mode": "fl2v", "prompt": "镜头缓慢推进", "first_frame": ref,
                "resolution_tier": "custom", "aspect_ratio": "custom", "width": 256, "height": 256,
                "frame_count": 39, "steps": 1, "seed": 42, "soundtrack_enabled": False,
            })
            output = self.download(client, result, "video_url")
            self.assertIn(b"ftyp", output[:32])
            self.assertTrue(result["reference_summary"]["first_frame"])
            self.assertFalse(result["has_audio"])

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "ffmpeg/ffprobe not installed")
    def test_seedvr_video_upload_generate_and_download(self):
        source = self.root / "source.mp4"
        subprocess.run([
            "ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
            "color=c=blue:s=64x48:r=12:d=0.25", "-c:v", "libx264", "-pix_fmt", "yuv420p",
            str(source),
        ], check=True, timeout=15)
        with self.studio("seedvr2") as client:
            ref = self.upload(client, "source.mp4", source.read_bytes(), "video/mp4")
            result = self.generate(client, {"mode": "video", "input_file": ref, "scale_factor": 2, "seed": 42})
            output = self.download(client, result, "video_url")
            self.assertIn(b"ftyp", output[:32])
            self.assertEqual((result["width"], result["height"]), (128, 96))
            self.assertEqual(result["fps"], 12)
            self.assertFalse(result["has_audio"])

    def test_qwen_chat_attachment_async_history_and_stream(self):
        with self.studio("qwen3.8-27b") as client:
            ref = self.upload(client, "scene.png", self.image_bytes(), "image/png")
            payload = {
                "prompt": "描述这张图片", "attachments": [{"kind": "image", "file_id": ref}],
                "enable_thinking": False, "response_format": "json_object", "max_tokens": 64,
            }
            result = self.generate(client, payload)
            self.assertTrue(json.loads(result["content"])["mock"])
            self.assertTrue(result["usage"]["total_tokens"])
            stream = client.post("/api/v1/chat/stream", json=payload, headers=self.headers)
            self.assertEqual(stream.status_code, 200)
            self.assertIn("text/event-stream", stream.headers["content-type"])
            self.assertIn("no-transform", stream.headers["cache-control"])
            events = [json.loads(line[6:]) for line in stream.text.splitlines() if line.startswith("data: ")]
            self.assertTrue(any(event.get("type") == "delta" and event.get("content") for event in events))
            self.assertTrue(any(event.get("type") == "usage" and event.get("mock") for event in events))
            self.assertEqual(events[-1]["type"], "done")


if __name__ == "__main__":
    unittest.main()
