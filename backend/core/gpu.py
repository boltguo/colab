"""Safe GPU, CPU, RAM, and Disk telemetry probes with zero-dependency OS fallbacks."""
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
from typing import Dict, Optional, Tuple

from .models import GpuStats, HostStats

_PROCESS_START_MONOTONIC = time.monotonic()
_LAST_PROC_CPU: Optional[Tuple[int, int]] = None
_SMI_CACHE: Tuple[float, Optional[Dict[str, object]]] = (0.0, None)

try:
    import psutil as _psutil  # type: ignore

    _psutil.cpu_percent(interval=None)
except Exception:
    _psutil = None


def _parse_float(val: str) -> Optional[float]:
    cleaned = val.strip()
    if not cleaned or cleaned.lower() in {"n/a", "[not supported]", "none"}:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _query_nvidia_smi(ttl_sec: float = 2.0) -> Optional[Dict[str, object]]:
    global _SMI_CACHE
    now = time.monotonic()
    if now - _SMI_CACHE[0] < ttl_sec:
        return _SMI_CACHE[1]

    smi_bin = shutil.which("nvidia-smi")
    if not smi_bin:
        _SMI_CACHE = (now, None)
        return None

    try:
        proc = subprocess.run(
            [
                smi_bin,
                "--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw,power.limit",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=1.5,
            check=False,
        )
        if proc.returncode != 0 or not proc.stdout.strip():
            _SMI_CACHE = (now, None)
            return None
        first_line = proc.stdout.strip().splitlines()[0]
        parts = [p.strip() for p in first_line.split(",")]
        if len(parts) < 4:
            _SMI_CACHE = (now, None)
            return None
        mem_used_mib = _parse_float(parts[2]) or 0.0
        mem_total_mib = _parse_float(parts[3]) or 0.0
        parsed: Dict[str, object] = {
            "name": parts[0],
            "utilization_pct": _parse_float(parts[1]),
            "vram_used_gib": mem_used_mib / 1024.0,
            "vram_total_gib": mem_total_mib / 1024.0,
            "temperature_c": _parse_float(parts[4]) if len(parts) > 4 else None,
            "power_draw_w": _parse_float(parts[5]) if len(parts) > 5 else None,
            "power_limit_w": _parse_float(parts[6]) if len(parts) > 6 else None,
        }
        _SMI_CACHE = (now, parsed)
        return parsed
    except Exception:
        _SMI_CACHE = (now, None)
        return None


def probe_gpu_stats() -> GpuStats:
    smi = _query_nvidia_smi()
    torch_mod = None
    try:
        import torch  # type: ignore

        torch_mod = torch
    except Exception:
        torch_mod = None

    torch_ver = getattr(torch_mod, "__version__", "") if torch_mod else ""
    cuda_ver = (getattr(getattr(torch_mod, "version", None), "cuda", None) or "") if torch_mod else ""
    torch_cuda_ok = bool(torch_mod and torch_mod.cuda.is_available())

    if not torch_cuda_ok and not smi:
        return GpuStats(
            available=False,
            name="CPU 模式 (未检测到 CUDA GPU)",
            torch_version=torch_ver,
            cuda_version=cuda_ver,
        )

    try:
        name = str(smi["name"]) if smi and smi.get("name") else ""
        total_gib = float(smi["vram_total_gib"]) if smi and smi.get("vram_total_gib") else 0.0
        used_gib = float(smi["vram_used_gib"]) if smi and smi.get("vram_used_gib") else 0.0
        torch_alloc_gib: Optional[float] = None
        torch_reserved_gib: Optional[float] = None
        bf16 = False

        if torch_cuda_ok and torch_mod is not None:
            if not name:
                name = torch_mod.cuda.get_device_name(0)
            props = torch_mod.cuda.get_device_properties(0)
            if total_gib <= 0:
                total_gib = props.total_memory / (1024 ** 3)
            torch_alloc_gib = round(torch_mod.cuda.memory_allocated(0) / (1024 ** 3), 2)
            torch_reserved_gib = round(torch_mod.cuda.memory_reserved(0) / (1024 ** 3), 2)
            if not smi:
                try:
                    free_bytes, total_bytes = torch_mod.cuda.mem_get_info(0)
                    used_gib = max(0.0, (total_bytes - free_bytes) / (1024 ** 3))
                except Exception:
                    used_gib = torch_alloc_gib
            bf16 = bool(torch_mod.cuda.is_bf16_supported())

        free_gib = max(0.0, total_gib - used_gib)
        vram_pct = round((used_gib / total_gib) * 100.0, 1) if total_gib > 0 else 0.0

        return GpuStats(
            available=True,
            name=name or "CUDA GPU",
            utilization_pct=smi.get("utilization_pct") if smi else None,  # type: ignore[arg-type]
            vram_total_gib=round(total_gib, 2),
            vram_used_gib=round(used_gib, 2),
            vram_free_gib=round(free_gib, 2),
            vram_percent=min(100.0, max(0.0, vram_pct)),
            torch_allocated_gib=torch_alloc_gib,
            torch_reserved_gib=torch_reserved_gib,
            temperature_c=smi.get("temperature_c") if smi else None,  # type: ignore[arg-type]
            power_draw_w=smi.get("power_draw_w") if smi else None,  # type: ignore[arg-type]
            power_limit_w=smi.get("power_limit_w") if smi else None,  # type: ignore[arg-type]
            bf16_supported=bf16,
            torch_version=torch_ver,
            cuda_version=cuda_ver,
        )
    except Exception as exc:
        return GpuStats(
            available=False,
            name=f"GPU 检测异常: {exc}",
            torch_version=torch_ver,
            cuda_version=cuda_ver,
        )


def _read_linux_proc_cpu() -> Optional[Tuple[int, int]]:
    stat_path = Path("/proc/stat")
    if not stat_path.is_file():
        return None
    try:
        first = stat_path.read_text(encoding="utf-8", errors="ignore").splitlines()[0]
        fields = [int(x) for x in first.split()[1:]]
        if len(fields) < 4:
            return None
        idle = fields[3] + (fields[4] if len(fields) > 4 else 0)
        total = sum(fields)
        return total, idle
    except Exception:
        return None


def _probe_cpu_percent(cpu_count: int, load_1m: Optional[float]) -> float:
    global _LAST_PROC_CPU
    if _psutil is not None:
        try:
            return round(float(_psutil.cpu_percent(interval=None)), 1)
        except Exception:
            pass

    snap = _read_linux_proc_cpu()
    if snap is not None:
        prev = _LAST_PROC_CPU
        _LAST_PROC_CPU = snap
        if prev is not None and snap[0] > prev[0]:
            delta_total = snap[0] - prev[0]
            delta_idle = snap[1] - prev[1]
            busy_pct = (1.0 - (delta_idle / delta_total)) * 100.0
            return round(min(100.0, max(0.0, busy_pct)), 1)

    if load_1m is not None and cpu_count > 0:
        return round(min(100.0, max(0.0, (load_1m / cpu_count) * 100.0)), 1)
    return 0.0


def _probe_ram_gib() -> Tuple[float, float, float, float]:
    if _psutil is not None:
        try:
            vm = _psutil.virtual_memory()
            total = vm.total / (1024 ** 3)
            avail = vm.available / (1024 ** 3)
            used = max(0.0, total - avail)
            pct = float(vm.percent)
            return round(total, 2), round(used, 2), round(avail, 2), round(pct, 1)
        except Exception:
            pass

    meminfo = Path("/proc/meminfo")
    if meminfo.is_file():
        try:
            raw = meminfo.read_text(encoding="utf-8", errors="ignore")
            kv: Dict[str, int] = {}
            for line in raw.splitlines():
                if ":" in line:
                    k, rest = line.split(":", 1)
                    nums = re.findall(r"\d+", rest)
                    if nums:
                        kv[k.strip()] = int(nums[0])
            total_kb = kv.get("MemTotal", 0)
            avail_kb = kv.get("MemAvailable", kv.get("MemFree", 0))
            if total_kb > 0:
                total = total_kb / (1024 ** 2)
                avail = avail_kb / (1024 ** 2)
                used = max(0.0, total - avail)
                pct = (used / total) * 100.0
                return round(total, 2), round(used, 2), round(avail, 2), round(pct, 1)
        except Exception:
            pass

    if sys.platform == "darwin":
        try:
            mem_bytes = int(
                subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True, timeout=1.0).strip()
            )
            vm_out = subprocess.check_output(["vm_stat"], text=True, timeout=1.0)
            page_match = re.search(r"page size of (\d+) bytes", vm_out)
            page_size = int(page_match.group(1)) if page_match else 4096

            def _pages(label: str) -> int:
                m = re.search(rf"{re.escape(label)}:\s+(\d+)", vm_out)
                return int(m.group(1)) if m else 0

            used_pages = (
                _pages("Pages active")
                + _pages("Pages wired down")
                + _pages("Pages occupied by compressor")
            )
            total = mem_bytes / (1024 ** 3)
            used = min(total, (used_pages * page_size) / (1024 ** 3))
            avail = max(0.0, total - used)
            pct = (used / total) * 100.0 if total > 0 else 0.0
            return round(total, 2), round(used, 2), round(avail, 2), round(pct, 1)
        except Exception:
            pass

    return 0.0, 0.0, 0.0, 0.0


def probe_host_stats(storage_dir: Optional[Path] = None) -> HostStats:
    cpu_count = os.cpu_count() or 1
    try:
        load_1m: Optional[float] = round(os.getloadavg()[0], 2)
    except Exception:
        load_1m = None

    cpu_pct = _probe_cpu_percent(cpu_count, load_1m)
    ram_total, ram_used, ram_free, ram_pct = _probe_ram_gib()

    content_dir = Path("/content")
    if content_dir.is_dir() and not content_dir.is_symlink():
        disk_target = content_dir
        disk_mount = "/content"
    elif storage_dir is not None:
        disk_target = storage_dir if storage_dir.exists() else Path.cwd()
        disk_mount = str(disk_target)
    else:
        disk_target = Path.cwd()
        disk_mount = str(disk_target)

    try:
        du = shutil.disk_usage(disk_target)
        disk_total = round(du.total / (1024 ** 3), 1)
        disk_used = round(du.used / (1024 ** 3), 1)
        disk_free = round(du.free / (1024 ** 3), 1)
        disk_pct = round((du.used / du.total) * 100.0, 1) if du.total > 0 else 0.0
    except Exception:
        disk_total, disk_used, disk_free, disk_pct = 0.0, 0.0, 0.0, 0.0

    uptime_sec = max(0, int(time.monotonic() - _PROCESS_START_MONOTONIC))
    return HostStats(
        cpu_count=cpu_count,
        cpu_percent=cpu_pct,
        load_avg_1m=load_1m,
        ram_total_gib=ram_total,
        ram_used_gib=ram_used,
        ram_free_gib=ram_free,
        ram_percent=ram_pct,
        disk_mount=disk_mount,
        disk_total_gib=disk_total,
        disk_used_gib=disk_used,
        disk_free_gib=disk_free,
        disk_percent=disk_pct,
        uptime_sec=uptime_sec,
    )


# Prime Linux /proc/stat baseline on import
_LAST_PROC_CPU = _read_linux_proc_cpu()
