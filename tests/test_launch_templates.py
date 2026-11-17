"""Exercise notebook restart decisions and release guards without starting services or publishing."""
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import textwrap
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import urllib.request
from urllib.error import HTTPError


ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ("step4_app", "step4_comfy_app", "step4_vllm")


def template_ast(name):
    source = (ROOT / "tools/templates" / f"{name}.py").read_text()
    values = {"REQUIRED_NODES": "set()", "SAMPLE_REQUEST_JSON": "{}"}
    source = re.sub(r"\{\{([A-Z_]+)\}\}", lambda match: values.get(match[1], ""), source)
    return ast.parse(source)


def fingerprint(name, *, release="v0.1.1:abc", key="key-one", environment=None):
    namespace = {
        "json": json, "hashlib": hashlib, "APP_DIR": Path("/content/app"),
        "cmd": ["python", "backend/run_server.py"],
        "app_cmd": ["python", "backend/run_server.py"],
        "access_password": key,
        "env_overrides": {"COLAB_ACCESS_PASSWORD": key, "COLAB_API_KEY": "", "COLAB_FEATURE": "feature", **(environment or {})},
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
    def test_web_password_is_required_without_an_api_toggle(self):
        for template in TEMPLATES:
            tree = template_ast(template)
            defaults = {node.targets[0].id: ast.literal_eval(node.value) for node in tree.body
                        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)
                        and node.targets[0].id in {"REQUIRE_API_KEY", "ACCESS_PASSWORD"}}
            self.assertNotIn("REQUIRE_API_KEY", defaults)
            self.assertEqual(defaults["ACCESS_PASSWORD"], "")
            resolver = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "resolve_access_password")
            namespace = {"ACCESS_PASSWORD": "test-access-password"}
            exec(compile(ast.Module(body=[resolver], type_ignores=[]), template, "exec"), namespace)
            self.assertEqual(namespace["resolve_access_password"](), "test-access-password")
            guard = next(node for node in tree.body if isinstance(node, ast.If) and ast.unparse(node.test) == "not access_password")
            with self.assertRaisesRegex(RuntimeError, "ACCESS_PASSWORD"):
                exec(compile(ast.Module(body=[guard], type_ignores=[]), template, "exec"), {"access_password": ""})
            # The web password is passed only as its own environment variable.
            assignment = next(node for node in tree.body if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name) and node.targets[0].id == "env_overrides")
            namespace.update(FEATURE_NAME="test", PORT=8188, DATA_DIR=Path("/data"), APP_DIR=Path("/app"),
                             access_password="test-access-password", COMFY_BASE="http://127.0.0.1:8189", COMFY_DIR=Path("/engine"), VLLM_BASE="http://127.0.0.1:8189")
            exec(compile(ast.Module(body=[assignment], type_ignores=[]), template, "exec"), namespace)
            self.assertEqual(namespace["env_overrides"]["COLAB_ACCESS_PASSWORD"], "test-access-password")
            self.assertEqual(namespace["env_overrides"]["COLAB_API_KEY"], "")

    def test_updated_bundle_changes_the_restart_fingerprint(self):
        for template in TEMPLATES:
            with self.subTest(template=template):
                self.assertNotEqual(fingerprint(template), fingerprint(template, release="v0.1.2:def"))

    def test_rotating_web_password_restarts_without_storing_the_password(self):
        for template in TEMPLATES:
            with self.subTest(template=template):
                first = fingerprint(template, key="private-key-one")
                second = fingerprint(template, key="private-key-two")
                self.assertNotEqual(first, second)
                self.assertNotIn("private-key", first)
                self.assertNotIn("private-key", second)
                self.assertNotIn("COLAB_API_KEY", first)
                self.assertNotIn("COLAB_ACCESS_PASSWORD", first)

    def test_engine_environment_changes_restart_the_gateway(self):
        for template in TEMPLATES:
            with self.subTest(template=template):
                self.assertNotEqual(
                    fingerprint(template, environment={"ENGINE_BASE": "http://127.0.0.1:8189"}),
                    fingerprint(template, environment={"ENGINE_BASE": "http://127.0.0.1:8190"}),
                )

    def test_unchanged_configuration_has_a_stable_fingerprint(self):
        for template in TEMPLATES:
            with self.subTest(template=template):
                self.assertEqual(fingerprint(template), fingerprint(template))


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
        for template, feature in (("step4_app", "indextts-2.5"), ("step4_comfy_app", "seedvr2"), ("step4_comfy_app", "minimax-h3")):
            with self.subTest(feature=feature), self.assertRaisesRegex(RuntimeError, "ffprobe.*apt-get"):
                self.run_guard(template, feature, {"ffprobe"})

    def test_installed_tools_allow_launch(self):
        self.run_guard("step4_app", "indextts-2.5", set())
        self.run_guard("step4_comfy_app", "minimax-h3", set())

    def test_image_studio_does_not_require_video_tools(self):
        self.run_guard("step4_comfy_app", "qwen-image-2.1", {"ffmpeg", "ffprobe"})


class PasswordLaunchVerificationTests(unittest.TestCase):
    def run_verification(self, opener, stop=None):
        tree = ast.parse((ROOT / "tools/templates/helpers.py").read_text())
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "verify_web_password")
        stop = stop or Mock()
        namespace = {"urllib": __import__("urllib"), "stop_processes": stop, "print": lambda *args: None}
        exec(compile(ast.Module(body=[function], type_ignores=[]), "helper", "exec"), namespace)
        with patch("urllib.request.build_opener", return_value=opener):
            namespace["verify_web_password"]("http://127.0.0.1:8188", "app-pattern")
        return stop

    def test_login_redirect_is_verified_before_exposing_the_tunnel(self):
        opener = Mock()
        opener.open.side_effect = HTTPError("http://127.0.0.1:8188/", 303, "Redirect", {"Location": "/auth/login"}, None)
        self.run_verification(opener).assert_not_called()
        for template in TEMPLATES:
            source = (ROOT / "tools/templates" / f"{template}.py").read_text()
            self.assertLess(source.index("verify_web_password(BASE,"), source.index("host_url = start_cf_tunnel"))

    def test_unprotected_service_is_stopped_even_when_health_would_succeed(self):
        opener = Mock()
        opener.open.return_value.__enter__ = Mock(return_value=Mock(status=200))
        opener.open.return_value.__exit__ = Mock(return_value=False)
        stop = Mock()
        with self.assertRaisesRegex(RuntimeError, "已停止 Web 服务"):
            self.run_verification(opener, stop)
        stop.assert_called_once_with("app-pattern", 30)


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
