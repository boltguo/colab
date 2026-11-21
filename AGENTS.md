# AGENTS.md — Architecture Memory, Product Design Standards & Engineering Rules

This document is the authoritative source of truth for the `boltguo/colab` repository, capturing core architectural decisions, Product Management (PM) workflow principles, UI/UX design specifications, maximal model controllability standards, and strict engineering/security invariants. All future feature apps, frontend/backend refactors, and generated Colab notebooks must adhere to these rules.

---

## 1. Project Vision & Architectural Evolution

- **Core Transformation**: Evolve from exposing raw ComfyUI node graphs + multiple static `.json` workflow files into a **Multi-Feature Web Studio + One-Click Colab Launch** platform accessed exclusively via Google Colab's native browser proxy (`google.colab.kernel.proxyPort`).
- **Eliminate User-Facing Workflow Files**:
  - Users must never need to understand, import, or switch between separate `.json` workflow files (e.g., text-to-image, single-image edit, dual-image fusion, style LoRA stacking, character swap, or multi-mode emotion TTS are unified into a single cohesive Studio page per model).
  - Conditional routing and pipeline orchestration live entirely in backend Python code; legacy `workflows/*.json` node graphs are progressively deprecated and removed.
- **One Colab Runtime = One Feature App**:
  - Each Colab notebook provisions a single isolated model application (`<feature>`), serving its own prebuilt static frontend bundle (`dist/<feature>`), dedicated same-origin Web Studio router, and underlying inference engine without cross-feature coupling.
- **User-Facing Language**:
  - Maintain `AGENTS.md` in English; keep Web Studio UI labels, tooltips, and Colab notebook instructions in clear, idiomatic Chinese unless requested otherwise.

---

## 2. Product Management (PM) & UI/UX Design Mandates

Every model application must be designed simultaneously from the perspective of a **Senior AI Product Manager** and a **Staff UI/UX Designer** — never ship a raw parameter dump or a stripped-down toy demo.

### 2.1 Visual Language: Default m3eui Theme
- **Clean Daylight Aesthetic**:
  - Use the **default m3eui theme** in light mode with Chinese localization. Do not override the palette or reproduce the previous Studio appearance. Import `normalize.css` in a lower-priority CSS layer, and keep application CSS below m3eui components so native focus states remain intact.
  - **Surface & Contrast Hierarchy**:
    - Use m3eui surface, text, outline, shape, and elevation tokens for app-owned surfaces. Let the library own component appearance and focus states; retain only necessary layout and sizing rules.
    - Follow the library Overview's composition: quiet `surface-container-low` workbench sections with 24px padding and clear gaps; avoid nested decorative panels. Reserve filled buttons for primary actions and use outlined/text buttons for secondary actions. Allocate numeric controls their full intrinsic width rather than clipping overflow.
    - Render API examples and chat code blocks with Shiki, wrapping long lines without changing copied source text. Keep the copy control as a compact icon in the code header.
    - Meet WCAG AA contrast across all text (≥ 4.5:1) and interactive control boundaries (≥ 3:1). Never convey status, warnings, or errors by color alone — always pair color with icons, numeric readouts, and explicit text badges.
  - **Zero-Jitter Numeric Typography**: Apply `font-variant-numeric: tabular-nums` to all slider readouts, durations, VRAM/CPU/RAM telemetry, sample rates, seeds, and timestamps so values never cause layout shift while dragging or polling.

### 2.2 Everyday Studio UI & Backend Parameter Control
- **Everyday Studio Policy (User-Directed Simplification)**:
  - All Studios prioritize common tasks. Keep primary creative inputs, media size/duration, and familiar generation controls (steps, CFG where useful, seed). Use server defaults for professional sampler/scheduler, cache, precision, tile, codec, and mastering knobs; do not present them as large panels.
  - Qwen Image and MiniMax may offer optional LoRA styling in a compact, initially collapsed section. Do not add separate quick/pro modes. Preserve the existing default m3eui theme and make selection states consistent.
  - Use one shared media generation dock containing only format, quantity when supported, and the generate action. Seed controls belong in generation settings, not in the dock.
  - Use only the model name for page/header titles. Render seeds with standalone rounded text fields, not a number stepper with its buttons hidden. Keep output selectors and the primary action capsule-shaped and vertically aligned.
  - Keep README concise: a one-click model/configuration table first, followed by Web UI, usage, and short feature/LoRA guidance. Add screenshots after the UI is finalized.
  - The IndexTTS Studio prioritizes everyday voice cloning: reference voice, text, language, speaking speed, simple emotion description/reference, audio format, playback/download, and session history.
  - Remove professional sampling, emotion-vector editors, text segmentation previews, estimated subtitle timelines, mastering and engine panels from the UI and client state. Use server defaults instead of submitting hidden advanced values.
  - Show speaking speed as a direct multiplier (larger means faster); convert it to the native inverse duration factor only when submitting. Keep labels short and numeric/reset controls in a stable aligned row.
- **Source-Level Parameter Audit**:
  - Before integrating any model, inspect its official inference source code and configuration files to catalog **every controllable dimension**: core conditioning inputs, fine-grained control vectors / reference guidance, text or image preprocessing toggles, chunking/segmentation thresholds, autoregressive/diffusion sampling hyperparameters (`temperature`, `top_p`, `top_k`, `num_beams`, `cfg`, `steps`, `seed`, penalties), vocoder/decoder knobs, mastering/post-processing (`loudness_norm`, silence trimming, tail fade-out, output codec/format), and hardware runtime flags (`bf16`, `torch.compile`, custom CUDA kernels, VRAM offload/release).
- **Validated Backend Schema + Flat-First UI**:
  - Expose complete validated schemas in backend Pydantic models with battle-tested defaults.
  - **The everyday Studio policy above takes precedence for UI scope.** Lay out primary creative & output controls **flat and scannable** on the workbench: mode toggle (`文生图` vs `图生图`, with optional multi-image slots), prompt, resolution/aspect ratio, editable dimensions, and basic generation settings. Let the server supply validated defaults for omitted controls.

### 2.3 Core PM Workflow & Interaction Principles
1. **Sticky Primary Action Dock**:
   - Keep the primary generate button (supporting `⌘/Ctrl + Enter` with IME composition safety), output format, and supported quantity selector anchored in a **Sticky Action Dock**; place seed lock/randomize controls in generation settings so scrolling or expanding engine flags never pushes the primary CTA off-screen.
2. **No Persistent User Preset Saving & Minimalist Input Hygiene**:
   - Because Colab VMs are ephemeral and discarded after shutdown, **do not include custom preset save/load modals or persistent preset dropdowns**.
   - **Modality-Appropriate Samples Only**: For audio/TTS studios where recording a clean voice sample requires hardware, provide a built-in reference voice clip and curated prosody recipes. For **image/video studios**, keep the workspace distraction-free: **do not ship synthetic built-in test images or noisy prompt-recipe banners** — let users upload, drag-drop, or paste their own reference images directly (`<image1>`, with optional `+ Add Reference Image` slots for `<image2>`..`<image4>`).
3. **Web-Only Access via Google Colab Native Proxy (No Tunnel, No Password Gate, No External API)**:
   - Do **not** install or launch external tunnels (`cloudflared`, `ngrok`), do **not** require `ACCESS_PASSWORD` or `/auth/login` password gates, and do **not** expose external APIs (`/docs`, `/redoc`, `/openapi.json`, API Key configuration/modals, API snippet modals, or external `/v1/*` OpenAI/Anthropic gateway routes).
   - Colab Step 4 binds the Web Studio strictly to `127.0.0.1:8188` and exposes it exclusively to the authenticated Colab browser session via Google Colab's native port proxy (`google.colab.kernel.proxyPort(8188)` + `google.colab.output.serve_kernel_port_as_window(8188)`), passing `COLAB_PROXY_ORIGIN` and persisting `proxy_info.json`.
   - Enforce same-origin checks (`same_origin`) on all non-GET HTTP writes and WebSocket upgrades, disable wildcard CORS (`CORSMiddleware`), and never expose a custom remote server URL input in the header. Display an ephemeral `Colab 内置代理（临时）` indicator in the Studio header when running under Colab's proxy.
4. **Live Machine Resource Telemetry**:
   - Display an always-glanceable telemetry pill in the top header (polling automatically while visible and pausing in background tabs) with a rich popover showing real-time **GPU utilization (`%`), VRAM used/total (`GiB`), GPU temperature (`°C`) & power (`W`), CPU load (`%` & core count), System RAM (`GiB`), Workspace Disk free/used (`/content`), Task Queue counts, and Uptime**.
5. **Authoring Micro-Tools**:
   - Eliminate syntax memorization. Provide interactive helpers tailored to each modality (e.g., polyphone/phoneme `<word|pron>` cursor insertion and live segment token preview for TTS; aspect-ratio presets, resolution alignment hints, prompt expansion diff, and subject bounding-box selection for vision/video models).
6. **A/B Reference Comparison & Session History**:
   - Keep the right-hand Audition / Preview stage sticky (`Sticky Aside`), featuring **one-click A/B comparison** against raw reference inputs (e.g., synthesized voice vs. original reference voice; upscaled vs. original media), interactive timestamped subtitles/metadata, one-click seed locking, and current-session generation history with full parameter restore.
7. **On-Demand Dynamic Model & LoRA Loader**:
   - For image/video models, Step 3 pre-downloads only mandatory base weights. Optional style/character/acceleration LoRAs can be dynamically fetched and hot-mounted at runtime from the Web UI or API via **built-in curated lists, Hugging Face repo/file inputs, Civitai/direct `.safetensors` URLs, or local file uploads** — supporting multi-LoRA stacking with independent strength sliders, `.safetensors`-only validation (rejecting unsafe pickle `.ckpt`/`.pt`), and pre-download disk-space checks without restarting the engine.

---

## 3. Tech Stack & Directory Layout

### 3.1 Frontend Monorepo (`pnpm workspace`, Per-Feature Static `dist`)
- **Stack**: `pnpm workspace` + `React 19` + `TypeScript` + `Vite` (pure static SPA) + `m3eui` (Material 3 Expressive, built on Base UI).
  - Isolate component-library imports inside `frontend/packages/shared/src/ui/primitives.tsx` and icon imports inside `ui/icons.tsx`. Use native m3eui shapes, states, motion, and accessible interactions; keep light mode, Chinese labels, and feature behavior.
  - Use the library's default CSS theme without generating custom theme files. `styles/index.css` declares the cascade layers for normalization, app layout, and m3eui. Colab consumes the prebuilt assets without Node.js.
- **Structure**:
  - `frontend/packages/shared`: Shared m3eui adapters and layout (`primitives.tsx`, `styles/`), `StudioShell` (header, live machine telemetry, Colab native proxy badge, language toggle), media upload/mic-record/preview components (`AudioSourceField`, `ImageSourceField`), WebSocket + polling task runner hook (`useTaskRunner`), and session history store (`useHistoryStore`).
  - `frontend/apps/<feature>`: Dedicated workbench per model feature, independently compiled into `frontend/dist/<feature>/`.

### 3.2 Backend Service Layer (`FastAPI` + Plugin Architecture)
- **Stack**: `Python FastAPI` + `Uvicorn`.
- **Structure**:
  - `backend/core`: Unified app factory (`app_factory.py`), SPA static hosting, same-origin write/WebSocket guard (`security.py`) with OpenAPI/docs disabled and no wildcard CORS, upload/output media storage (`storage.py`), async single-GPU task queue + WebSocket progress broadcaster (`task_manager.py`), and zero-dependency GPU/CPU/RAM/Disk telemetry probes (`gpu.py`).
  - `backend/features/<feature>`: Complete Pydantic request/response schemas (`schemas.py`), Web Studio feature routes (`plugin.py`), and inference engine adapter (`runner.py`).
- **Mandatory Async Execution**: Long-running inference (TTS, image/video generation, upscaling, character swap, model downloads) must **never** block synchronous HTTP responses (managed browser proxies drop idle long HTTP requests). Always submit asynchronously to return `task_id` immediately and stream progress over WebSocket (`/api/v1/tasks/{id}/ws`) with HTTP polling fallback (`/api/v1/tasks/{id}`). (Streaming SSE chat for LLMs is the sole exception.)

### 3.3 Inference Engine Selection Policy (No Forced ComfyUI Coupling)
Underlying engines remain completely transparent to the frontend and external API consumers:
1. **Official Native Engine First (Zero ComfyUI Dependency)**:
   - Prefer official Python inference libraries or dedicated serving engines whenever mature and VRAM-predictable.
   - Applies to: `indextts-2.5` (native `indextts` library), `qwen3.8-27b` (native `vLLM`), and future models cleanly supported by native PyTorch / `diffusers`.
2. **Headless ComfyUI Worker Where Ecosystem-Bound**:
   - Use background headless ComfyUI strictly as an internal operator graph engine when a model relies on `Comfy-Org` custom quantized weights (e.g., `int8_convrot`), multi-model single-GPU auto-offloading, or specialized node chains.
   - Applies to: `minimax-h3`, `qwen-image-2.1`, and `seedvr2`.
   - **Dynamic Python Graph Assembly**: Construct ComfyUI API prompt dictionaries dynamically in Python from validated request parameters rather than maintaining static UI workflow JSONs.

---

## 4. GitHub Releases Distribution & Colab Launch Pipeline

- **Preserve `README.md` One-Click Entry**:
  - Root `README.md` retains clear VRAM requirements and `Open in Colab` badges pointing to `notebooks/<feature>/*.ipynb`.
- **Zero Node.js Build in Colab via GitHub Releases**:
  - `tools/build_release.py` (and `.github/workflows/release.yml`) packages each feature into `release_artifacts/app-<feature>.tar.gz` (containing compiled `dist/<feature>` assets plus `backend/core` and `backend/features/<feature>`) along with `SHA256SUMS` and `tools/release_manifest.json`.
  - **Never install Node.js or `pnpm` inside Colab at runtime.** Step 2 fetches the pinned `app-<feature>.tar.gz` (or uses a pre-staged `/content/app-<feature>.tar.gz` during CLI deployment) and verifies its exact `SHA256` before extraction.
- **Port & Colab Native Proxy Topology**:
  - **Web Studio Port (`127.0.0.1:8188`)**: Bound on loopback only by FastAPI, serving `/` (Web Studio) and same-origin `/api/v1/*` Web UI routes/WebSockets without exposing `/docs`, `/redoc`, `/openapi.json`, or `/v1/*`.
  - **Internal Engine Port (`127.0.0.1:8189`)**: Reserved on loopback for internal headless ComfyUI or `vLLM` worker processes; never exposed externally.
  - **Colab Native Proxy**: Notebook Step 4 resolves `google.colab.kernel.proxyPort(8188)` and opens `output.serve_kernel_port_as_window(8188)` directly under the user's authenticated Google session, writing runtime metadata to `/content/app_data/<feature>/proxy_info.json` and passing `COLAB_PROXY_ORIGIN`.

---

## 5. Strict Security & Reproducibility Invariants

1. **Template-Driven Notebook Generation**:
   - Generate all `notebooks/` exclusively via `tools/build_notebooks.py` + `tools/templates/` (with `ast.parse` syntax verification), preserving the standardized 4-step structure: `1. Environment Check -> 2. Install Engine & Release App Bundle -> 3. Download & Verify Model Weights -> 4. Launch Web Studio`.
2. **End-to-End Pinning & Integrity Checks**:
   - Pin external Git repositories (official inference repos, ComfyUI, custom nodes) to exact 40-char commit SHAs and verify remote origin URLs and clean working trees.
   - Pin Hugging Face downloads to exact `revision` commit SHAs, verify exact file byte sizes (`st_size`), enable `hf_xet` high-throughput transfers, and check `/content` free disk space prior to downloading.
   - Pin `app-<feature>.tar.gz` (`SHA256`).
3. **Protect Preinstalled Colab CUDA Stack**:
   - Filter out `torch`, `torchvision`, `torchaudio`, and `xformers` when installing third-party requirement lists, and guard against stale transitive pins (such as `descript-audiotools` downgrading `protobuf`) so Colab's preinstalled CUDA-matched PyTorch stack remains intact.
4. **Symlink Rejection & Proxy Cache Safety**:
   - Check and reject symlinks (`is_symlink()`) across model directories, archive extraction targets, upload/output paths, and git checkouts.
   - Serve SPA HTML and static assets with `private` and `no-transform` cache headers so browser proxies never cache private responses publicly or rewrite ES module scripts.

---

## 6. Feature Matrix & Hardware Baselines

| Feature ID | Unified Capabilities (Web Studio Workbench) | VRAM Baseline | Target Engine |
| :--- | :--- | :--- | :--- |
| `indextts-2.5` | Zero-shot cross-lingual cloning (`zh/en/ja/es/ar`) / speaking speed multiplier / emotion description or reference audio / audio audition & download / session history | 40GB+ | Native `indextts` |
| `qwen3.8-27b` | Multimodal Web Playground (text, images, videos) + live `<think>` stream + sampling & tool controls | 40GB (FP8) / 80GB (BF16) | Native `vLLM` |
| `seedvr2` | Video upscaling (7B Sharp / 3B Fast) / interactive before-after comparison slider / temporal chunking & color-correction controls | 40GB+ | Headless ComfyUI |
| `qwen-image-2.1` | Text-to-image / single-image edit / dual-image fusion / multi-reference / custom LoRAs / aspect-ratio & sampling inspector | 80GB+ | Headless ComfyUI |
| `minimax-h3` | T2V / I2V / first-last frame control / multimodal reference-to-video with synced audio / Turbo & custom LoRAs | 80GB+ | Headless ComfyUI |
| `h3-character-swap` | Single & multi-person character replacement (`Ref2VA + FL2V Turbo 8-step + Character Swap V1.5 + SAM 3.1` automatic tracking & background lock) + anchor guide & A/B wipe video comparison | 80GB+ (40GB at 480p) | Headless ComfyUI |
