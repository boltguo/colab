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
    def test_base_model_does_not_advertise_an_unimplemented_hd_tier(self):
        self.assertEqual(MiniMaxH3GenerateRequest(prompt="镜头").resolution_tier, "768p")
        with self.assertRaises(ValidationError):
            MiniMaxH3GenerateRequest(prompt="镜头", resolution_tier="1080p")
        # The engine's explicit canvas controls remain available as experimental sizes.
        custom = MiniMaxH3GenerateRequest(
            prompt="镜头", resolution_tier="custom", aspect_ratio="custom", width=1920, height=1088,
        )
        self.assertEqual((custom.width, custom.height), (1920, 1088))

    def test_official_reference_limits_are_available_per_modality(self):
        for name, limit, make_item in (
            ("ref_images", 9, lambda i: f"image-{i}.png"),
            ("ref_videos", 3, lambda i: {"file_id": f"video-{i}.mp4"}),
            ("ref_audios", 3, lambda i: f"audio-{i}.wav"),
        ):
            refs = [make_item(i) for i in range(limit)]
            with self.subTest(name=name):
                request = MiniMaxH3GenerateRequest(mode="r2v", prompt="参考", **{name: refs})
                self.assertEqual(len(getattr(request, name)), limit)
                with self.assertRaises(ValidationError):
                    MiniMaxH3GenerateRequest(mode="r2v", prompt="参考", **{name: refs + [make_item(limit)]})

    def test_mixed_references_share_a_twelve_file_budget(self):
        videos = [{"file_id": f"video-{i}.mp4", "use_video_audio": True} for i in range(3)]
        request = MiniMaxH3GenerateRequest(
            mode="r2v", prompt="参考", ref_images=[f"image-{i}.png" for i in range(6)],
            ref_videos=videos, ref_audios=[f"audio-{i}.wav" for i in range(3)],
        )
        self.assertEqual(len(request.ref_images) + len(request.ref_videos) + len(request.ref_audios), 12)
        with self.assertRaisesRegex(ValidationError, "合计最多 12 个文件"):
            MiniMaxH3GenerateRequest(
                mode="r2v", prompt="参考", ref_images=[f"image-{i}.png" for i in range(7)],
                ref_videos=videos, ref_audios=[f"audio-{i}.wav" for i in range(3)],
            )
        # A video's embedded soundtrack is part of that file, not a thirteenth upload.
        full = MiniMaxH3GenerateRequest(
            mode="r2v", prompt="参考", ref_images=[f"image-{i}.png" for i in range(9)], ref_videos=videos,
        )
        self.assertEqual(len(full.ref_images), 9)

    def test_graph_forwards_highest_reference_slots_without_truncation(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            runner = MiniMaxH3Runner(MediaStorage(root), root, mock_mode=True)
            for image_count, audio_count in ((9, 0), (6, 3)):
                with self.subTest(images=image_count, audios=audio_count):
                    images = [f"image-{i}.png" for i in range(image_count)]
                    videos = [(f"video-{i}.mp4", True) for i in range(3)]
                    audios = [f"audio-{i}.wav" for i in range(audio_count)]
                    request = MiniMaxH3GenerateRequest(
                        mode="r2v", prompt="参考", ref_images=images,
                        ref_videos=[{"file_id": name, "use_video_audio": keep} for name, keep in videos],
                        ref_audios=audios,
                    )
                    graph, _, _ = runner._build_comfy_graph(
                        request, actual_seed=42, canvas_w=1344, canvas_h=768, aligned_frames=124,
                        turbo_lora_filename=None, resolved_loras=[], staged_first_frame=None,
                        staged_last_frame=None, staged_guide_image=None, staged_guide_audio=None,
                        staged_ref_images=images, staged_ref_videos=videos, staged_ref_audios=audios,
                    )
                    inputs = graph["cond_pos"]["inputs"]
                    for i, name in enumerate(images):
                        self.assertEqual(inputs[f"ref_images.ref_image_{i}"], [f"load_ref_img_{i}", 0])
                        self.assertEqual(graph[f"load_ref_img_{i}"]["inputs"]["image"], name)
                    self.assertEqual(inputs["ref_videos.ref_video_2"], ["split_ref_vid_2", 0])
                    self.assertEqual(inputs["ref_video_audios.ref_video_audio_2"], ["split_ref_vid_2", 1])
                    for i, name in enumerate(audios):
                        self.assertEqual(inputs[f"ref_audios.ref_audio_{i}"], [f"load_ref_aud_{i}", 0])
                        self.assertEqual(graph[f"load_ref_aud_{i}"]["inputs"]["audio"], name)

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
