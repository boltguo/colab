# @title 1. Environment Check {display-mode: "form"}
import os, shutil, subprocess, torch

MIN_VRAM_GIB = {{MIN_VRAM_GIB}}
REQUIREMENT = "{{REQUIREMENT}}"

if not torch.cuda.is_available():
    raise RuntimeError("No CUDA GPU detected. Select Runtime -> Change runtime type -> A100 / H100 / RTX 6000 GPU.")

print(subprocess.run(["nvidia-smi"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True).stdout)

gpu = torch.cuda.get_device_name(0)
vram_gib = torch.cuda.get_device_properties(0).total_memory / 1024**3
ram_gib = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 1024**3
disk_gib = shutil.disk_usage("/content").free / 1024**3
bf16 = torch.cuda.is_bf16_supported()
print(f"GPU: {gpu} | VRAM: {vram_gib:.1f} GiB | RAM: {ram_gib:.1f} GiB | Disk Free: {disk_gib:.1f} GiB | BF16: {bf16}")
print(f"PyTorch: {torch.__version__} | CUDA: {torch.version.cuda}")

if not any(k in gpu.upper() for k in ("A100", "H100", "6000")) or vram_gib < MIN_VRAM_GIB:
    raise RuntimeError(f"Detected {gpu} ({vram_gib:.1f} GiB), but this notebook requires {REQUIREMENT}. Please switch runtime.")
if not bf16:
    raise RuntimeError("Current GPU does not support BF16; please switch runtime.")
{{EXTRA}}print(f"[OK] GPU environment ready: {gpu} ({vram_gib:.1f} GiB)")
