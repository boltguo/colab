"""Validate the H3 native timeline and reference preprocessing without GPU inference."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from pydantic import ValidationError

from backend.core.storage import MediaStorage
from backend.features.minimax_h3.runner import MiniMaxH3Runner, _prepare_reference_video
from backend.features.minimax_h3.schemas import MiniMaxH3GenerateRequest


class MiniMaxRequestTests(unittest.TestCase):
    def test_generated_audio_requires_native_fps(self):
        with self.assertRaisesRegex(ValidationError, "24 fps"):
            MiniMaxH3GenerateRequest(prompt="对白", fps=30)
        self.assertEqual(MiniMaxH3GenerateRequest(prompt="对白").fps, 24)

    def test_silent_video_reports_playback_duration(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            runner = MiniMaxH3Runner(MediaStorage(root), root, mock_mode=True)
            request = MiniMaxH3GenerateRequest(prompt="镜头", fps=60, soundtrack_enabled=False)
            def write_video(path, **_):
                path.write_bytes(b"mock-video")
            with patch("backend.features.minimax_h3.runner._render_mock_video", side_effect=write_video), \
                    patch("backend.features.minimax_h3.runner.time.sleep"):
                result = runner._run_generation(request, lambda *_: None)
            self.assertEqual(result.duration_sec, round(result.frame_count / 60, 2))

    def test_guide_index_is_validated_against_aligned_frames(self):
        for index in (-125, 124):
            with self.subTest(index=index), self.assertRaisesRegex(ValidationError, "锚定帧"):
                MiniMaxH3GenerateRequest(prompt="镜头", guide_image="guide.png", guide_frame_idx=index)
        self.assertEqual(
            MiniMaxH3GenerateRequest(prompt="镜头", guide_image="guide.png", guide_frame_idx=-1).guide_frame_idx,
            -1,
        )

    def test_mode_change_does_not_keep_inactive_conditioning(self):
        text = MiniMaxH3GenerateRequest(prompt="镜头", first_frame="stale.png", ref_images=["stale.png"])
        self.assertIsNone(text.first_frame)
        self.assertEqual(text.ref_images, [])
        reference = MiniMaxH3GenerateRequest(
            mode="r2v", prompt="参考", ref_images=["ref.png"], guide_image="stale.png", guide_frame_idx=9999,
        )
        self.assertIsNone(reference.guide_image)

    def test_blank_prompt_is_rejected(self):
        with self.assertRaisesRegex(ValidationError, "请输入"):
            MiniMaxH3GenerateRequest(prompt=" \n ")


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg is required for media verification")
class MiniMaxReferenceVideoTests(unittest.TestCase):
    def test_reference_fps_conversion_keeps_audio_and_video_time_aligned(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "source.mp4"
            target = Path(temp) / "reference.mp4"
            subprocess.run([
                "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
                "-f", "lavfi", "-i", "color=c=blue:size=96x64:rate=30:duration=2",
                "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=32000:duration=2",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(source),
            ], check=True, capture_output=True, timeout=30)
            _prepare_reference_video(source, target, duration_sec=39 / 24, include_audio=True)
            metadata = json.loads(subprocess.check_output([
                "ffprobe", "-v", "error", "-show_streams", "-of", "json", str(target),
            ], text=True))
            video = next(stream for stream in metadata["streams"] if stream["codec_type"] == "video")
            audio = next(stream for stream in metadata["streams"] if stream["codec_type"] == "audio")
            self.assertEqual(video["avg_frame_rate"], "24/1")
            self.assertEqual(int(video["nb_frames"]), 39)
            self.assertAlmostEqual(float(video["duration"]), 39 / 24, places=3)
            self.assertLess(abs(float(video["duration"]) - float(audio["duration"])), 0.05)
            self.assertAlmostEqual(float(video["start_time"]), float(audio["start_time"]), places=3)

    def test_missing_requested_soundtrack_has_an_actionable_error(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "silent.mp4"
            target = Path(temp) / "reference.mp4"
            subprocess.run([
                "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
                "-f", "lavfi", "-i", "color=c=blue:size=96x64:rate=24:duration=1",
                "-c:v", "libx264", "-an", str(source),
            ], check=True, capture_output=True, timeout=30)
            with self.assertRaisesRegex(ValueError, "提取视频原声"):
                _prepare_reference_video(source, target, duration_sec=1, include_audio=True)


if __name__ == "__main__":
    unittest.main()
