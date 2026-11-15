"""SeedVR2 input, sizing and timebase regressions; no GPU or model weights needed."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

from pydantic import ValidationError

from backend.features.seedvr2.runner import (
    SeedVR2Runner,
    _probe_image_dims_stdlib,
    _probe_video_meta,
    _render_mock_upscaled_video,
)
from backend.features.seedvr2.schemas import (
    SeedVR2GenerateRequest,
    align_chunk_frames,
    compute_target_dimensions,
)


class SeedVR2RequestTests(unittest.TestCase):
    def test_native_single_frame_chunk_option_is_available(self):
        req = SeedVR2GenerateRequest(
            input_file="video.mp4", split_latent=True, chunking_mode="manual", frames_per_chunk=1,
        )
        self.assertEqual(req.frames_per_chunk, 1)
        with self.assertRaises(ValidationError):
            SeedVR2GenerateRequest(input_file="video.mp4", frames_per_chunk=0)

    def test_default_keeps_original_audio_and_framerate(self):
        req = SeedVR2GenerateRequest(input_file="video.mp4")
        self.assertTrue(req.keep_audio)
        self.assertEqual(req.fps_override, 0)
        self.assertEqual(req.steps, 1)

    def test_speed_change_requires_muting_original_audio(self):
        with self.assertRaisesRegex(ValidationError, "关闭保留原声"):
            SeedVR2GenerateRequest(input_file="video.mp4", fps_override=48)
        req = SeedVR2GenerateRequest(input_file="video.mp4", fps_override=48, keep_audio=False)
        self.assertEqual(req.fps_override, 48)

    def test_sub_one_fps_is_rejected_before_comfy(self):
        with self.assertRaisesRegex(ValidationError, "1~120"):
            SeedVR2GenerateRequest(input_file="video.mp4", fps_override=0.5, keep_audio=False)

    def test_chunk_rounding_matches_browser_half_up(self):
        self.assertEqual(align_chunk_frames(11), 13)
        self.assertEqual(align_chunk_frames(10), 9)

    def test_sizing_modes_and_zero_dimension_keep_orientation(self):
        for mode, kwargs, expected in (
            ("multiplier", {"scale_factor": 1.5}, (2880, 1620)),
            ("shorter_edge", {"target_shorter_edge": 2160}, (3840, 2160)),
            ("longer_edge", {"target_longer_edge": 3840}, (3840, 2160)),
            ("dimensions", {"target_width": 0, "target_height": 1080}, (1920, 1080)),
        ):
            with self.subTest(mode=mode):
                self.assertEqual(compute_target_dimensions(1920, 1080, sizing_mode=mode, **kwargs), expected)
        self.assertEqual(
            compute_target_dimensions(1080, 1920, sizing_mode="shorter_edge", target_shorter_edge=2160),
            (2160, 3840),
        )


class SeedVR2MediaTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.source = Path(self.tmp.name) / "source.mp4"
        self.source.write_bytes(b"fixture")

    def probe(self, streams, duration="4.25"):
        completed = subprocess.CompletedProcess([], 0, stdout=json.dumps({
            "streams": streams, "format": {"duration": duration},
        }))
        with patch("backend.features.seedvr2.runner.shutil.which", return_value="ffprobe"), \
             patch("backend.features.seedvr2.runner.subprocess.run", return_value=completed):
            return _probe_video_meta(self.source)

    def test_probe_rejects_audio_only_file(self):
        with self.assertRaisesRegex(ValueError, "无法读取源视频"):
            self.probe([{"codec_type": "audio"}])

    def test_probe_uses_real_framerate_without_fabricating_audio(self):
        result = self.probe([{
            "codec_type": "video", "width": 1280, "height": 720,
            "avg_frame_rate": "0/0", "r_frame_rate": "30000/1001",
        }])
        self.assertEqual(result[:3], (1280, 720, 4.25))
        self.assertAlmostEqual(result[3], 30000 / 1001)
        self.assertFalse(result[4])

    def test_probe_rejects_unknown_duration(self):
        with self.assertRaisesRegex(ValueError, "无法读取源视频"):
            self.probe([{
                "codec_type": "video", "width": 1280, "height": 720,
                "avg_frame_rate": "24/1",
            }], duration="N/A")

    def test_probe_honors_legacy_portrait_rotation_tag(self):
        result = self.probe([{
            "codec_type": "video", "width": 320, "height": 180,
            "avg_frame_rate": "24/1", "tags": {"rotate": "270"},
        }])
        self.assertEqual(result[:2], (180, 320))

    def test_invalid_image_does_not_get_fallback_dimensions(self):
        with self.assertRaisesRegex(ValueError, "无法读取源图片"):
            _probe_image_dims_stdlib(self.source)

    def test_trim_past_end_is_rejected_before_model_submission(self):
        runner = object.__new__(SeedVR2Runner)
        runner.storage = Mock()
        runner.storage.resolve_input_ref.return_value = self.source
        runner.comfy = Mock()
        req = SeedVR2GenerateRequest(input_file="source.mp4", trim_video=True, start_time=4)
        with patch("backend.features.seedvr2.runner._probe_video_meta", return_value=(1920, 1080, 4, 24, True)):
            with self.assertRaisesRegex(ValueError, "截取起点"):
                runner._run_upscale(req, lambda *_: None)
        runner.comfy.stage_input_file.assert_not_called()

    def test_oversized_output_is_rejected_instead_of_silently_clamped(self):
        runner = object.__new__(SeedVR2Runner)
        runner.storage = Mock()
        runner.storage.resolve_input_ref.return_value = self.source
        runner.comfy = Mock()
        req = SeedVR2GenerateRequest(input_file="source.mp4", scale_factor=8)
        with patch("backend.features.seedvr2.runner._probe_video_meta", return_value=(3840, 2160, 4, 24, True)):
            with self.assertRaisesRegex(ValueError, "30720×17280"):
                runner._run_upscale(req, lambda *_: None)
        runner.comfy.stage_input_file.assert_not_called()

    def test_graph_uses_the_same_even_dimensions_as_preview(self):
        runner = object.__new__(SeedVR2Runner)
        req = SeedVR2GenerateRequest(input_file="source.mp4", scale_factor=1.5)
        dims = compute_target_dimensions(853, 479, sizing_mode="multiplier", scale_factor=1.5)
        graph, _, _ = runner._build_comfy_graph(
            req, actual_seed=42, staged_input_name="source.mp4", target_dimensions=dims,
        )
        resize = graph["resize"]["inputs"]
        self.assertEqual((resize["resize_type.width"], resize["resize_type.height"]), dims)
        self.assertEqual(resize["resize_type.crop"], "disabled")
        self.assertEqual(graph["create_vid"]["inputs"]["fps"], ["demux", 2])

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "ffmpeg/ffprobe not installed")
    def test_portrait_display_matrix_sets_portrait_upscale_dimensions(self):
        encoded = Path(self.tmp.name) / "landscape.mp4"
        subprocess.run([
            "ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
            "color=c=blue:s=320x180:r=24:d=0.25", "-c:v", "libx264", "-pix_fmt", "yuv420p",
            str(encoded),
        ], check=True, timeout=15)
        rotation = subprocess.run([
            "ffmpeg", "-v", "error", "-y", "-display_rotation:v:0", "90",
            "-i", str(encoded), "-c", "copy", str(self.source),
        ], capture_output=True, timeout=15)
        if rotation.returncode:  # FFmpeg versions before -display_rotation.
            subprocess.run([
                "ffmpeg", "-v", "error", "-y", "-i", str(encoded), "-c", "copy",
                "-metadata:s:v:0", "rotate=90", str(self.source),
            ], check=True, timeout=15)
        width, height, *_ = _probe_video_meta(self.source)
        self.assertEqual((width, height), (180, 320))
        dims = compute_target_dimensions(width, height, sizing_mode="multiplier", scale_factor=2)
        self.assertEqual(dims, (360, 640))
        runner = object.__new__(SeedVR2Runner)
        graph, _, _ = runner._build_comfy_graph(
            SeedVR2GenerateRequest(input_file="source.mp4"), actual_seed=42,
            staged_input_name="source.mp4", target_dimensions=dims,
        )
        resize = graph["resize"]["inputs"]
        self.assertEqual((resize["resize_type.width"], resize["resize_type.height"]), (360, 640))

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "ffmpeg/ffprobe not installed")
    def test_preview_speed_change_preserves_frame_sequence_and_updates_duration(self):
        subprocess.run([
            "ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
            "color=c=blue:s=64x48:r=24:d=2", "-c:v", "libx264", "-pix_fmt", "yuv420p",
            str(self.source),
        ], check=True, timeout=15)
        output = Path(self.tmp.name) / "output.mp4"
        _render_mock_upscaled_video(
            self.source, output, target_w=128, target_h=96, fmt="mp4", keep_audio=False,
            trim_video=True, start_time=0.5, duration=1.0, fps_override=48,
            source_fps=24, seed=42,
        )
        width, height, duration, fps, audio = _probe_video_meta(output)
        self.assertEqual((width, height), (128, 96))
        self.assertAlmostEqual(duration, 0.5, delta=0.05)
        self.assertEqual(fps, 48)
        self.assertFalse(audio)


if __name__ == "__main__":
    unittest.main()
