# @title 1. 环境检测 {display-mode: "form"}
import os, shutil, subprocess, torch

MIN_VRAM_GIB = {{MIN_VRAM_GIB}}
REQUIREMENT = "{{REQUIREMENT}}"

if not torch.cuda.is_available():
    raise RuntimeError("未检测到 GPU。请在 Colab 菜单选择：代码执行程序 -> 更改运行时类型 -> A100 / H100 / RTX 6000 GPU。")

print(subprocess.run(["nvidia-smi"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True).stdout)

gpu = torch.cuda.get_device_name(0)
vram_gib = torch.cuda.get_device_properties(0).total_memory / 1024**3
ram_gib = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 1024**3
disk_gib = shutil.disk_usage("/content").free / 1024**3
bf16 = torch.cuda.is_bf16_supported()
print(f"GPU: {gpu} | 显存: {vram_gib:.1f} GiB | 系统内存: {ram_gib:.1f} GiB | 磁盘可用: {disk_gib:.1f} GiB | BF16: {bf16}")
print(f"PyTorch: {torch.__version__} | CUDA: {torch.version.cuda}")

if not any(k in gpu.upper() for k in ("A100", "H100", "6000")) or vram_gib < MIN_VRAM_GIB:
    raise RuntimeError(f"当前显卡为 {gpu} ({vram_gib:.1f} GiB)，本笔记本需要 {REQUIREMENT}，请切换 runtime。")
if not bf16:
    raise RuntimeError("当前 GPU 不支持 BF16，请切换 runtime。")
{{EXTRA}}print(f"[OK] GPU 环境正常：{gpu} ({vram_gib:.1f} GiB)")
