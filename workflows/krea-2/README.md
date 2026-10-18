# Krea 2 工作流

- **笔记本**：[Krea_2.ipynb](../../notebooks/krea-2/Krea_2.ipynb)
- **支持显卡**：A100 (40GB / 80GB)、H100 (80GB)、RTX 6000 (96GB)
- **默认配置**：原生 BF16 全精度（`krea2_turbo_bf16` 24.5GB + `qwen3vl_4b_bf16` 8.3GB + `qwen_image_vae` 0.24GB，合计约 33 GB）、8 步极速生成、内置 `Qwen3-VL` 自动提示词扩写

| 工作流 | 功能 | 输入要求 | LoRA |
| --- | --- | --- | --- |
| [01 · 文生图](01_Krea_2_T2I.json) | 胶片/单反级写实摄影文生图 | 中/英文提示词 | 无需 |
| [02 · 风格 LoRA 文生图](02_Krea_2_T2I_LoRA.json) | 9 款官方艺术风格文生图 | 提示词 + 选择风格 LoRA 与触发词 | 9 款官方风格 LoRA |
| [03 · 参考图风格迁移](03_Krea_2_Style_Reference.json) | 提取参考图画风/光影生成新主体 | 上传 1 张风格参考图 + 提示词 | `krea2_style_reference.safetensors` |

## 官方风格 LoRA 触发词对照表

| LoRA 文件名 | 风格说明 | 对应触发词 (`LoRA 触发词`) | 推荐强度 |
| --- | --- | --- | --- |
| `krea2_retroanime.safetensors` | 复古紫调动漫风 | `purple retro anime style` | `1.0` |
| `krea2_darkbrush.safetensors` | 水墨暗黑笔触 | `monochrome ink wash style` | `1.0` |
| `krea2_rainywindow.safetensors` | 雨窗朦胧摄影 | `rainy window style` | `1.0` |
| `krea2_softwatercolor.safetensors` | 装饰艺术柔和水彩 | `art deco watercolor style` | `1.0` |
| `krea2_sunsetblur.safetensors` | 落日唯美动态模糊 | `ethereal motion blur style` | `1.0` |
| `krea2_vintagetarot.safetensors` | 复古塔罗牌插画 | `vintage tarot style` | `1.0` |
| `krea2_neondrip.safetensors` | 霓虹肌理抽象艺术 | `textured abstract style` | `1.0` |
| `krea2_dotmatrix.safetensors` | 黑白点阵版画 | `monochrome stippling style` | `1.0` |
| `krea2_kidsdrawing.safetensors` | 稚拙表现主义涂鸦 | `naive expressive sketch style` | `1.0` |

## 使用说明

1. 按笔记本 `1 → 2 → 3 → 4` 顺序运行，通过 Cloudflare Tunnel 自有域名打开 ComfyUI。
2. 第 3 步默认下载全套原生 BF16 权重及官方 10 款 LoRA（含 `krea2_style_reference` 与 9 款艺术风格 LoRA）。
3. 在 ComfyUI 左侧工作流列表打开 `01–03` 即可直接运行。

