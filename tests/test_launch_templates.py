"""Exercise notebook restart decisions, Colab native proxy helpers, and release guards."""
import ast
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import textwrap
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
STEP2_TEMPLATES = ("step2_comfy_app", "step2_indextts", "step2_vllm")
STEP4_TEMPLATES = ("step4_app", "step4_comfy_app", "step4_vllm")


def template_ast(name):
    source = (ROOT / "tools/templates" / f"{name}.py").read_text()
    values = {"REQUIRED_NODES": "set()", "BUNDLED_NODES_REL": ""}
    source = re.sub(r"\{\{([A-Z_]+)\}\}", lambda match: values.get(match[1], ""), source)
    return ast.parse(source)


def fingerprint(name, *, release="v0.1.1:abc", proxy_origin="https://8188-one.prod.r.colab.dev", environment=None):
    namespace = {
        "json": json,
        "APP_DIR": Path("/content/app"),
        "cmd": ["python", "backend/run_server.py"],
        "app_cmd": ["python", "backend/run_server.py"],
        "env_overrides": {
            "COLAB_FEATURE": "feature",
            "COLAB_PROXY_ORIGIN": proxy_origin,
            **(environment or {}),
        },
        "read_text": lambda _: release,
    }
    assignment = next(
        node for node in template_ast(name).body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id in ("app_fingerprint", "launch_fingerprint") for target in node.targets)
    )
    exec(compile(ast.Module(body=[assignment], type_ignores=[]), name, "exec"), namespace)
    return namespace[assignment.targets[0].id]


class NotebookRestartTests(unittest.TestCase):
    def test_step2_and_step4_templates_use_colab_native_proxy_without_tunnel_or_api_exposed(self):
        forbidden = (
            "cloudflared",
            "trycloudflare",
            "TUNNEL_MODE",
            "CF_TUNNEL_TOKEN",
            "ACCESS_PASSWORD",
            "COLAB_API_KEY",
            "COLAB_ACCESS_PASSWORD",
            "/docs",
        )
        for name in (*STEP2_TEMPLATES, *STEP4_TEMPLATES):
            raw = (ROOT / "tools/templates" / f"{name}.py").read_text(encoding="utf-8")
            with self.subTest(template=name):
                for marker in forbidden:
                    self.assertNotIn(marker, raw)
        for name in STEP4_TEMPLATES:
            source = (ROOT / "tools/templates" / f"{name}.py").read_text(encoding="utf-8")
            with self.subTest(template=name):
                self.assertIn("resolve_colab_proxy_url(PORT)", source)
                self.assertIn("open_colab_proxy(PORT, proxy_url, access_mode)", source)
                self.assertIn('"COLAB_PROXY_ORIGIN": proxy_origin', source)

    def test_updated_bundle_or_proxy_or_engine_changes_restart_fingerprint(self):
        for template in STEP4_TEMPLATES:
            with self.subTest(template=template):
                self.assertEqual(fingerprint(template), fingerprint(template))
                self.assertNotEqual(fingerprint(template), fingerprint(template, release="v0.1.2:def"))
                self.assertNotEqual(
                    fingerprint(template),
                    fingerprint(template, proxy_origin="https://8188-two.prod.r.colab.dev"),
                )
                self.assertNotEqual(
                    fingerprint(template, environment={"ENGINE_BASE": "http://127.0.0.1:8189"}),
                    fingerprint(template, environment={"ENGINE_BASE": "http://127.0.0.1:8190"}),
                )


class ColabProxyHelperTests(unittest.TestCase):
    def _load_helpers(self):
        tree = ast.parse((ROOT / "tools/templates/helpers.py").read_text(encoding="utf-8"))
        ns = {}
        exec(compile(tree, "helpers", "exec"), ns)
        return ns

    def test_local_fallback_when_google_colab_missing(self):
        ns = self._load_helpers()
        with patch.dict(sys.modules, {"google": None, "google.colab": None}):
            url, mode = ns["resolve_colab_proxy_url"](8188)
        self.assertEqual((url, mode), ("http://127.0.0.1:8188", "local"))

    def test_colab_proxy_resolution_and_window_open(self):
        ns = self._load_helpers()
        output_mod = SimpleNamespace(
            eval_js=Mock(return_value="https://8188-test.prod.r.colab.dev/"),
            serve_kernel_port_as_window=Mock(),
        )
        colab_pkg = SimpleNamespace(output=output_mod)
        google_pkg = SimpleNamespace(colab=colab_pkg)
        with patch.dict(sys.modules, {"google": google_pkg, "google.colab": colab_pkg}):
            url, mode = ns["resolve_colab_proxy_url"](8188)
            self.assertEqual((url, mode), ("https://8188-test.prod.r.colab.dev", "colab"))
            output_mod.eval_js.assert_called_once_with("google.colab.kernel.proxyPort(8188)")

            ns["open_colab_proxy"](8188, url, mode)
            output_mod.serve_kernel_port_as_window.assert_called_once_with(8188)

            output_mod.eval_js.return_value = "http://not-https.example"
            with self.assertRaisesRegex(RuntimeError, "valid HTTPS proxy URL"):
                ns["resolve_colab_proxy_url"](8188)


class VllmSingleGpuLaunchTests(unittest.TestCase):
    def launch_command(self, tree):
        assignment = next(node for node in tree.body if isinstance(node, ast.Assign)
                          and isinstance(node.targets[0], ast.Name) and node.targets[0].id == "vllm_cmd")
        namespace = {"model_dir": "/models/qwen", "VLLM_PORT": 8189, "UPLOADS_DIR": Path("/data/uploads")}
        exec(compile(ast.Module(body=[assignment], type_ignores=[]), "vllm-command", "exec"), namespace)
        return namespace["vllm_cmd"]

    def test_template_and_generated_notebook_fit_reported_mamba_cache_limit(self):
        notebook = json.loads((ROOT / "notebooks/qwen3.8-27b/Qwen3.8_27B.ipynb").read_text())
        code = next("".join(cell["source"]) for cell in notebook["cells"]
                    if cell["cell_type"] == "code" and "vllm_cmd =" in "".join(cell["source"]))
        commands = [self.launch_command(template_ast("step4_vllm")), self.launch_command(ast.parse(code))]
        self.assertEqual(commands[0], commands[1])
        for command in commands:
            concurrency = int(command[command.index("--max-num-seqs") + 1])
            self.assertTrue(1 <= concurrency <= 32)
            self.assertLessEqual(concurrency, 612)  # Cache capacity in the reported startup failure.
            self.assertEqual(command[command.index("--max-model-len") + 1], "262144")

    def test_repeated_step4_restarts_only_when_engine_arguments_change(self):
        tree = template_ast("step4_vllm")
        command = self.launch_command(tree)
        old_command = list(command)
        index = old_command.index("--max-num-seqs")
        del old_command[index:index + 2]
        nodes = [next(node for node in tree.body if isinstance(node, ast.Assign)
                      and isinstance(node.targets[0], ast.Name) and node.targets[0].id == name)
                 for name in ["vllm_cfg_str", "vllm_is_up"]]
        nodes.append(next(node for node in tree.body if isinstance(node, ast.If)
                          and ast.unparse(node.test).startswith("vllm_is_up and")))
        for prior, should_restart in [(old_command, True), (command, False)]:
            stop = Mock()
            namespace = {"vllm_cmd": command, "json": json, "vllm_ready": lambda: True,
                         "read_text": lambda _: json.dumps(prior), "VLLM_LAUNCH_CONFIG": Path("/config"),
                         "VLLM_PROCESS_PATTERN": "test-engine", "stop_processes": stop, "print": lambda *a: None}
            exec(compile(ast.Module(body=nodes, type_ignores=[]), "vllm-restart", "exec"), namespace)
            self.assertEqual(namespace["vllm_is_up"], not should_restart)
            if should_restart:
                stop.assert_called_once_with("test-engine", 120)
            else:
                stop.assert_not_called()


class MediaPrerequisiteTests(unittest.TestCase):
    def run_guard(self, template, feature, missing):
        guard = next(
            node for node in template_ast(template).body
            if isinstance(node, ast.If)
            and any(isinstance(child, ast.Name) and child.id == "missing_media_tools" for child in ast.walk(node))
        )
        namespace = {
            "FEATURE_NAME": feature,
            "shutil": SimpleNamespace(which=lambda name: None if name in missing else f"/usr/bin/{name}"),
        }
        exec(compile(ast.Module(body=[guard], type_ignores=[]), template, "exec"), namespace)

    def test_required_media_tools_fail_before_model_loading_with_recovery_hint(self):
        for template, feature in (
            ("step4_app", "indextts-2.5"),
            ("step4_comfy_app", "seedvr2"),
            ("step4_comfy_app", "minimax-h3"),
            ("step4_comfy_app", "h3-character-swap"),
        ):
            with self.subTest(feature=feature), self.assertRaisesRegex(RuntimeError, "ffprobe.*apt-get"):
                self.run_guard(template, feature, {"ffprobe"})

    def test_installed_tools_allow_launch(self):
        self.run_guard("step4_app", "indextts-2.5", set())
        self.run_guard("step4_comfy_app", "minimax-h3", set())

    def test_image_studio_does_not_require_video_tools(self):
        self.run_guard("step4_comfy_app", "qwen-image-2.1", {"ffmpeg", "ffprobe"})

    def test_generated_notebook_code_cells_are_pure_english_and_markdown_has_chinese_notes(self):
        cjk_re = re.compile(r"[\u4e00-\u9fff]")
        notebooks = sorted((ROOT / "notebooks").glob("*/*.ipynb"))
        self.assertGreaterEqual(len(notebooks), 6)
        for nb_path in notebooks:
            nb = json.loads(nb_path.read_text(encoding="utf-8"))
            has_chinese_markdown = False
            for idx, cell in enumerate(nb["cells"]):
                src = "".join(cell.get("source", []))
                if cell["cell_type"] == "code":
                    self.assertIsNone(
                        cjk_re.search(src),
                        f"{nb_path.name} code cell #{idx} must be pure English, found CJK text.",
                    )
                elif cell["cell_type"] == "markdown" and cjk_re.search(src):
                    has_chinese_markdown = True
            self.assertTrue(has_chinese_markdown, f"{nb_path.name} should keep Chinese explanations in Markdown cells.")


class ReleaseGuardTests(unittest.TestCase):
    def run_guard(self, *, tag="v0.1.1", existing_tag="", existing_release="", api_fail="0"):
        workflow = (ROOT / ".github/workflows/release.yml").read_text()
        step = workflow.split("- name: Validate new release tag", 1)[1].split("\n      - name:", 1)[0]
        script = textwrap.dedent(step.split("run: |\n", 1)[1])
        stubs = '''
git() {
  if [[ "$1" == "ls-remote" ]]; then printf '%s' "$EXISTING_GIT_TAG"; fi
}
gh() {
  if [[ "$API_FAIL" == "1" ]]; then return 1; fi
  printf '%s\\n' "$EXISTING_RELEASE_TAG"
}
'''
        return subprocess.run(
            ["bash", "-euo", "pipefail", "-c", stubs + script],
            env={**os.environ, "TAG_NAME": tag, "GITHUB_REPOSITORY": "example/project",
                 "EXISTING_GIT_TAG": existing_tag, "EXISTING_RELEASE_TAG": existing_release, "API_FAIL": api_fail},
            capture_output=True, text=True, timeout=10,
        )

    def test_new_version_is_allowed(self):
        for tag in ("v0.1.1", "v0.1.1-rc.1"):
            with self.subTest(tag=tag):
                self.assertEqual(self.run_guard(tag=tag).returncode, 0)

    def test_existing_tag_or_release_cannot_be_overwritten(self):
        self.assertNotEqual(self.run_guard(existing_tag="abc refs/tags/v0.1.1").returncode, 0)
        self.assertNotEqual(self.run_guard(existing_release="v0.1.1").returncode, 0)

    def test_tag_input_is_not_executed_as_shell_code(self):
        result = self.run_guard(tag="v0.1.1$(printf injected)")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("injected", result.stdout)

    def test_metadata_failure_stops_the_release(self):
        self.assertNotEqual(self.run_guard(api_fail="1").returncode, 0)


if __name__ == "__main__":
    unittest.main()
