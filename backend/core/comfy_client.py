"""Headless ComfyUI loopback client (HTTP + WebSocket progress bridge).

Connects strictly to the internal loopback ComfyUI worker (default 127.0.0.1:8189),
stages input media safely (rejecting symlinks), submits dynamic API prompt graphs,
streams live node/KSampler step progress into TaskManager's ProgressCallback,
and retrieves generated output artifacts.
"""
import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import struct
import time
from typing import Any, Callable, Dict, List, Optional, Tuple
import urllib.error
import urllib.parse
import urllib.request
import uuid

from .security import ensure_safe_dir, ensure_safe_path

ProgressFn = Callable[[float, str], None]


class ComfyExecutionError(RuntimeError):
    """Raised when ComfyUI rejects a prompt or fails during node execution."""


def _ws_handshake_and_iter(host: str, port: int, path: str, timeout: float = 5.0):
    """Minimal pure-stdlib RFC 6455 client for ws://127.0.0.1:<port> text/binary frames."""
    sock = socket.create_connection((host, port), timeout=timeout)
    try:
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        req = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host}:{port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        )
        sock.sendall(req.encode("ascii"))

        buf = b""
        while b"\r\n\r\n" not in buf:
            chunk = sock.recv(4096)
            if not chunk:
                raise ConnectionError("ComfyUI WebSocket 握手中断。")
            buf += chunk
        header_bytes, remainder = buf.split(b"\r\n\r\n", 1)
        status_line = header_bytes.split(b"\r\n", 1)[0].decode("latin1", errors="replace")
        if "101" not in status_line:
            raise ConnectionError(f"ComfyUI WebSocket 握手失败：{status_line}")
        expected_accept = base64.b64encode(
            hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode("ascii")).digest()
        ).decode("ascii")
        if expected_accept.lower() not in header_bytes.decode("latin1", errors="replace").lower():
            raise ConnectionError("ComfyUI WebSocket Sec-WebSocket-Accept 校验不匹配。")

        sock.settimeout(2.0)

        def _read_exact(n: int) -> bytes:
            nonlocal remainder
            while len(remainder) < n:
                chunk = sock.recv(max(4096, n - len(remainder)))
                if not chunk:
                    raise EOFError("WebSocket closed")
                remainder += chunk
            out, remainder = remainder[:n], remainder[n:]
            return out

        def _send_frame(opcode: int, payload: bytes = b"") -> None:
            mask_key = os.urandom(4)
            length = len(payload)
            header = bytearray([0x80 | (opcode & 0x0F)])
            if length < 126:
                header.append(0x80 | length)
            elif length < 65536:
                header.append(0x80 | 126)
                header.extend(struct.pack("!H", length))
            else:
                header.append(0x80 | 127)
                header.extend(struct.pack("!Q", length))
            header.extend(mask_key)
            masked = bytes(b ^ mask_key[i % 4] for i, b in enumerate(payload))
            sock.sendall(bytes(header) + masked)

        msg_opcode: Optional[int] = None
        msg_chunks: List[bytes] = []

        while True:
            try:
                first_two = _read_exact(2)
            except socket.timeout:
                yield None
                continue
            except EOFError:
                break

            b0, b1 = first_two[0], first_two[1]
            fin = bool(b0 & 0x80)
            opcode = b0 & 0x0F
            masked = bool(b1 & 0x80)
            length = b1 & 0x7F
            if length == 126:
                length = struct.unpack("!H", _read_exact(2))[0]
            elif length == 127:
                length = struct.unpack("!Q", _read_exact(8))[0]
            mask_bytes = _read_exact(4) if masked else b""
            payload = _read_exact(length) if length else b""
            if masked:
                payload = bytes(b ^ mask_bytes[i % 4] for i, b in enumerate(payload))

            if opcode == 0x8:  # Close
                break
            if opcode == 0x9:  # Ping -> Pong
                _send_frame(0xA, payload)
                continue
            if opcode == 0xA:  # Pong
                continue

            if opcode in (0x1, 0x2):
                msg_opcode = opcode
                msg_chunks = [payload]
            elif opcode == 0x0 and msg_opcode is not None:
                msg_chunks.append(payload)
            else:
                continue

            if fin:
                full = b"".join(msg_chunks)
                if msg_opcode == 0x1:
                    yield full.decode("utf-8", errors="replace")
                msg_opcode = None
                msg_chunks = []
    finally:
        try:
            sock.close()
        except Exception:
            pass


class ComfyClient:
    """Thread-safe HTTP + WebSocket client for headless ComfyUI on loopback."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        comfy_dir: Optional[Path] = None,
    ) -> None:
        raw_url = (base_url or os.environ.get("COMFY_BASE_URL") or "http://127.0.0.1:8189").rstrip("/")
        self.base_url = raw_url
        parsed = urllib.parse.urlparse(self.base_url)
        self.host = parsed.hostname or "127.0.0.1"
        self.port = parsed.port or (443 if parsed.scheme == "https" else 8189)
        self.comfy_dir = Path(comfy_dir or os.environ.get("COMFY_DIR") or "/content/ComfyUI")

    @property
    def input_dir(self) -> Path:
        return self.comfy_dir / "input"

    @property
    def output_dir(self) -> Path:
        return self.comfy_dir / "output"

    def get_json(self, route: str, timeout: float = 10.0) -> Any:
        req = urllib.request.Request(
            f"{self.base_url}{route}",
            headers={"Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def post_json(self, route: str, payload: Dict[str, Any], timeout: float = 30.0) -> Any:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}{route}",
            data=body,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw.strip() else {}
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            try:
                parsed = json.loads(detail)
                err_msg = parsed.get("error", {}).get("message") or detail
                node_errs = parsed.get("node_errors")
                if node_errs:
                    err_msg = f"{err_msg} | 节点错误: {json.dumps(node_errs, ensure_ascii=False)}"
            except Exception:
                err_msg = detail
            raise ComfyExecutionError(f"ComfyUI 拒绝推理图 ({exc.code})：{err_msg}") from exc

    def is_ready(self, timeout: float = 3.0) -> bool:
        try:
            stats = self.get_json("/system_stats", timeout=timeout)
            return isinstance(stats, dict) and "system" in stats
        except Exception:
            return False

    def free_memory(self, unload_models: bool = True, free_memory: bool = True) -> None:
        try:
            self.post_json(
                "/free",
                {"unload_models": unload_models, "free_memory": free_memory},
                timeout=15.0,
            )
        except Exception as exc:
            raise ComfyExecutionError(f"释放 ComfyUI 显存失败：{exc}") from exc

    def stage_input_file(self, src: Path, prefix: str = "ref") -> str:
        """Copy a validated media file into ComfyUI's input/ directory and return its filename."""
        ensure_safe_path(src)
        if not src.is_file():
            raise FileNotFoundError(f"参考输入文件不存在：{src}")
        in_dir = ensure_safe_dir(self.input_dir)
        ext = src.suffix.lower() or ".png"
        staged_name = f"studio_{prefix}_{uuid.uuid4().hex[:12]}{ext}"
        dest = ensure_safe_path(in_dir / staged_name, stop_at=in_dir)
        shutil.copy2(src, dest)
        return staged_name

    def resolve_output_file(self, item: Dict[str, Any]) -> Path:
        """Resolve an output entry ({filename, subfolder, type}) from ComfyUI history safely."""
        filename = Path(str(item.get("filename") or "")).name
        if not filename:
            raise ComfyExecutionError("ComfyUI 返回了空的输出文件名。")
        subfolder = str(item.get("subfolder") or "").strip().strip("/")
        base = ensure_safe_path(self.output_dir)
        candidate = base / subfolder / filename if subfolder else base / filename
        resolved = ensure_safe_path(candidate, stop_at=base)
        if not resolved.resolve().is_relative_to(base.resolve()):
            raise ComfyExecutionError(f"拒绝越界输出路径：{candidate}")
        if not resolved.is_file():
            raise ComfyExecutionError(f"未找到 ComfyUI 生成结果文件：{resolved}")
        return resolved

    def run_prompt(
        self,
        prompt: Dict[str, Dict[str, Any]],
        on_progress: ProgressFn,
        node_labels: Optional[Dict[str, str]] = None,
        progress_range: Tuple[float, float] = (0.10, 0.92),
        timeout_sec: float = 1800.0,
    ) -> Dict[str, Any]:
        """Submit a ComfyUI API prompt graph and stream step-level progress until completion."""
        if not self.is_ready(timeout=5.0):
            raise ComfyExecutionError(
                f"内部推理引擎 ComfyUI ({self.base_url}) 未就绪，请检查第 4 步启动日志。"
            )

        labels = node_labels or {}
        p_start, p_end = progress_range
        p_span = max(0.05, p_end - p_start)
        client_id = uuid.uuid4().hex

        submit_res = self.post_json("/prompt", {"prompt": prompt, "client_id": client_id})
        prompt_id = str(submit_res.get("prompt_id") or "")
        if not prompt_id:
            raise ComfyExecutionError(f"ComfyUI 未返回有效 prompt_id：{submit_res}")

        on_progress(p_start, "已提交推理图至 GPU 执行队列...")
        deadline = time.monotonic() + timeout_sec
        current_node_label = "模型推理中"

        def _check_history() -> Optional[Dict[str, Any]]:
            try:
                hist = self.get_json(f"/history/{prompt_id}", timeout=8.0)
            except Exception:
                return None
            if not isinstance(hist, dict) or prompt_id not in hist:
                return None
            entry = hist[prompt_id]
            status = entry.get("status") or {}
            if status.get("status_str") == "error":
                msgs = status.get("messages") or []
                detail = ""
                for m in msgs:
                    if isinstance(m, list) and len(m) >= 2 and m[0] == "execution_error":
                        err_info = m[1] if isinstance(m[1], dict) else {}
                        detail = (
                            f"{err_info.get('node_type', '')}: "
                            f"{err_info.get('exception_message', '')}"
                        ).strip(": ")
                        break
                raise ComfyExecutionError(f"GPU 算子执行报错：{detail or status}")
            if status.get("completed") or entry.get("outputs"):
                return entry
            return None

        # Prefer live WebSocket stream, seamlessly falling back to HTTP history polling
        try:
            ws_path = f"/ws?clientId={urllib.parse.quote(client_id)}"
            for raw_msg in _ws_handshake_and_iter(self.host, self.port, ws_path, timeout=5.0):
                if time.monotonic() > deadline:
                    raise TimeoutError(f"GPU 推理超时（超过 {int(timeout_sec)} 秒）。")

                if raw_msg is None:
                    done_entry = _check_history()
                    if done_entry is not None:
                        return done_entry
                    continue

                try:
                    evt = json.loads(raw_msg)
                except Exception:
                    continue

                etype = evt.get("type")
                edata = evt.get("data") or {}
                evt_prompt_id = edata.get("prompt_id")
                if evt_prompt_id and evt_prompt_id != prompt_id:
                    continue

                if etype == "executing":
                    node_id = edata.get("node")
                    if node_id is None:
                        # Execution finished!
                        break
                    nid_str = str(node_id)
                    current_node_label = labels.get(nid_str, f"执行节点 #{nid_str}")
                    on_progress(min(p_end, p_start + 0.04), f"{current_node_label}...")
                elif etype == "progress":
                    val = float(edata.get("value") or 0)
                    max_val = float(edata.get("max") or 1)
                    ratio = max(0.0, min(1.0, val / max(1.0, max_val)))
                    mapped = p_start + p_span * (0.08 + 0.90 * ratio)
                    on_progress(
                        mapped,
                        f"{current_node_label}（步数 {int(val)}/{int(max_val)}）...",
                    )
                elif etype == "execution_error":
                    exc_msg = edata.get("exception_message") or str(edata)
                    node_type = edata.get("node_type") or "UnknownNode"
                    raise ComfyExecutionError(f"GPU 算子 {node_type} 执行异常：{exc_msg}")
        except (ConnectionError, OSError):
            # Fallback to polling if WebSocket couldn't connect
            pass

        # Poll /history/{prompt_id} until completed or deadline
        while time.monotonic() <= deadline:
            done_entry = _check_history()
            if done_entry is not None:
                return done_entry
            time.sleep(1.0)

        raise TimeoutError(f"等待 ComfyUI 推理结果超时（prompt_id={prompt_id}）。")
