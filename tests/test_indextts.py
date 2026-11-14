"""IndexTTS adapter regressions that run without GPU weights."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
import random
from pathlib import Path
import shutil
import subprocess
import tempfile
import types
import unittest
from unittest.mock import patch

import numpy as np

from backend.core.config import AppSettings
from backend.core.storage import MediaStorage
from backend.features.indextts_2_5 import runner


class FakeEngine:
    def __init__(self, **options):
        self.options = options
        self.gpt = object()
        self.gr_progress = None
        self.calls = []
        self.random_samples = []
        random.random()  # Native model initialization can consume RNG state.

    def infer(self, **kwargs):
        self.calls.append(kwargs)
        self.random_samples.append(random.random())
        return 22050, np.zeros((2205, 1), dtype=np.int16)


class IndexTTSEngineTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.models = self.root / "models"
        self.models.mkdir()
        for name in runner.REQUIRED_MODEL_FILES:
            (self.models / name).touch()
        self.manager = runner.IndexTTS25EngineManager()
        fake_torch = types.ModuleType("torch")
        fake_torch.cuda = types.SimpleNamespace(is_available=lambda: False)
        fake_torch.manual_seed = lambda seed: None
        fake_package = types.ModuleType("indextts")
        fake_package.__path__ = []
        fake_inference = types.ModuleType("indextts.infer_v2_5")
        fake_inference.IndexTTS2 = FakeEngine
        self.stack.enter_context(patch.dict("sys.modules", {
            "torch": fake_torch,
            "indextts": fake_package,
            "indextts.infer_v2_5": fake_inference,
        }))
        self.stack.enter_context(patch.object(runner, "_resolve_model_dir", return_value=self.models))
        self.stack.enter_context(patch.object(runner, "_resolve_src_dir", return_value=None))
        self.stack.enter_context(patch.object(runner, "_install_transformers_compat_shim"))
        self.options = dict(
            use_bf16=True,
            use_qwen_emo=False,
            use_cuda_kernel=False,
            use_torch_compile=False,
            progress_cb=lambda *_: None,
        )

    def test_release_cannot_destroy_an_engine_in_use(self):
        with self.manager.use_engine(**self.options) as engine:
            with ThreadPoolExecutor(max_workers=1) as pool:
                result = pool.submit(self.manager.release).result(timeout=2)
            self.assertTrue(result["busy"])
            self.assertIsNotNone(engine.gpt)
        self.assertEqual(self.manager.release()["released_instances"], 1)
        self.assertIsNone(engine.gpt)

    def test_configuration_change_replaces_previous_model(self):
        with self.manager.use_engine(**self.options) as first:
            pass
        with self.manager.use_engine(**self.options) as cached:
            self.assertIs(first, cached)
        with self.manager.use_engine(**{**self.options, "use_qwen_emo": True}) as second:
            self.assertIsNot(first, second)
            self.assertIsNone(first.gpt)
            self.assertEqual(len(self.manager._cache), 1)

    def test_auto_release_runs_when_inference_fails(self):
        with self.assertRaisesRegex(RuntimeError, "inference failed"):
            with self.manager.use_engine(auto_free_memory=True, **self.options) as engine:
                raise RuntimeError("inference failed")
        self.assertEqual(self.manager._cache, {})
        self.assertIsNone(engine.gpt)

    def test_seed_and_sampling_survive_cold_and_warm_model_loads(self):
        storage = MediaStorage(self.root / "media")
        reference = self.root / "ref.wav"
        reference.touch()
        storage.register_preset("ref_audio", reference, "Reference")
        settings = AppSettings(
            feature="indextts-2.5", host="127.0.0.1", port=8188,
            data_dir=storage.base_dir, dist_dir=None, api_key="",
            mock_inference=False, repo_root=self.root,
        )
        params = {
            "text": "Hello world.", "language": "en", "seed": 42,
            "top_k": 0, "output_format": "wav", "duration_factor": 0.9,
            "interval_silence_ms": 350,
        }
        with patch.object(runner, "ENGINE_MANAGER", self.manager):
            result = runner.execute_indextts_task(params, storage, settings, lambda *_: None)
            engine = next(iter(self.manager._cache.values()))
            runner.execute_indextts_task(params, storage, settings, lambda *_: None)
        self.assertEqual(engine.random_samples[0], engine.random_samples[1])
        self.assertEqual(engine.calls[0]["top_k"], 0)
        self.assertEqual(engine.calls[0]["lang"], "en")
        self.assertEqual(engine.calls[0]["duration_factor"], 0.9)
        self.assertEqual(engine.calls[0]["interval_silence"], 350)
        self.assertEqual(result["seed"], 42)
        self.assertEqual(result["subtitle_timing"], "estimated")
        self.assertTrue((storage.outputs_dir / result["filename"]).is_file())


class IndexTTSOutputTests(unittest.TestCase):
    def test_subtitle_timestamp_carries_minutes_and_hours(self):
        self.assertEqual(runner._format_clock(59.9996, "srt"), "00:01:00,000")
        self.assertEqual(runner._format_clock(3599.9996, "vtt"), "01:00:00.000")

    def test_runtime_overrides_apply_and_restore_official_call_signature(self):
        calls = []

        def load_audio(path, max_seconds, verbose=False, sr=None):
            calls.append(("audio", max_seconds, sr))

        def cfm_inference(*args, **kwargs):
            calls.append(("cfm", args[5], kwargs["inference_cfg_rate"]))

        cfm = types.SimpleNamespace(inference=cfm_inference)
        engine = types.SimpleNamespace(
            _load_and_cut_audio=load_audio,
            s2mel=types.SimpleNamespace(models={"cfm": cfm}),
            cache_spk_cond=object(), cache_emo_cond=object(),
        )
        with self.assertRaisesRegex(RuntimeError, "stop"):
            with runner._override_indextts_runtime_knobs(engine, 9, 18, 0.85):
                engine._load_and_cut_audio("ref.wav", 15, sr=16000)
                cfm.inference(None, None, None, None, None, 25, inference_cfg_rate=0.7)
                raise RuntimeError("stop")
        self.assertEqual(calls, [("audio", 9.0, 16000), ("cfm", 18, 0.85)])
        self.assertIs(engine._load_and_cut_audio, load_audio)
        self.assertIs(cfm.inference, cfm_inference)
        self.assertIsNone(engine.cache_spk_cond)
        self.assertIsNone(engine.cache_emo_cond)

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg required")
    def test_loudness_normalized_flac_preserves_reported_sample_rate(self):
        with tempfile.TemporaryDirectory() as tmp:
            storage = MediaStorage(Path(tmp))
            sr = 22050
            samples = (np.sin(np.arange(sr) * 2 * np.pi * 440 / sr) * 6000).astype(np.int16)
            _, path, fmt, _ = runner._encode_audio_file(samples.tobytes(), sr, "flac", True, storage, "test")
            sample_rate = subprocess.check_output([
                "ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries",
                "stream=sample_rate", "-of", "default=noprint_wrappers=1:nokey=1", str(path),
            ], text=True).strip()
            self.assertEqual(fmt, "flac")
            self.assertEqual(sample_rate, str(sr))


if __name__ == "__main__":
    unittest.main()
