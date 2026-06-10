# Ailey — Autonomous AI Companion Platform

> A full-stack, locally-hosted AI companion system: a Flask inference backend running
> fine-tuned LLMs on Apple Silicon, a PHP web portal, a Next.js + Tauri desktop app,
> and a complete LoRA/DoRA training pipeline.

**This is a public, read-only showcase repository.** It contains the source code and
architecture of the Ailey platform with all private user data, training datasets,
runtime state and credentials removed. It is intended to demonstrate engineering work,
not to be run as-is.

---

## What is Ailey?

Ailey is a persistent, personality-driven AI companion that runs entirely on local
hardware (Apple Silicon / MLX). Unlike a stateless chatbot, Ailey has long-term memory,
an autonomous "idle thinking" loop, a creative toolset (image / music / video / SVG
generation), an email agent, and a self-learning engine — all wired together behind a
single backend and exposed through both a web portal and a native desktop app.

The platform powers a live deployment where users can chat with Ailey, receive
AI-generated art and music, and follow an autonomous "thought stream".

---

## Architecture

```text
┌─────────────────────┐     poll/HTTPS     ┌──────────────────────┐
│  PHP Web Portal      │ ◄────────────────► │  Flask Inference     │
│  (MySQL, polling)    │                    │  Backend (ailey_api) │
└─────────────────────┘                    │                      │
                                            │  • MLX / GGUF LLMs   │
┌─────────────────────┐    local HTTP      │  • RAG (LanceDB)     │
│  Next.js + Tauri     │ ◄────────────────► │  • Memory & Profiles │
│  Desktop App         │                    │  • Idle Thinker      │
│  (React/TS + Rust)   │                    │  • Creative Tools    │
└─────────────────────┘                    │  • Email Agent       │
                                            └──────────────────────┘
```

The portal never connects directly to the user's machine — the local backend **polls**
the portal queue over HTTPS, so no inbound tunnel or port-forwarding is required.

---

## Repository Layout

| Path | Description |
|------|-------------|
| `ailey_api.py` | Main Flask backend — REST API, session orchestration, streaming chat, tool routing. |
| `ailey_system/` | Core Python package (see below). |
| `portal/` | PHP web portal (MySQL via PDO, polling architecture, i18n, admin panel). |
| `ailey-frontend/` | Next.js + React + TypeScript app, packaged as a native desktop app via **Tauri** (Rust). |
| `lora_training/` | DoRA / LoRA fine-tuning and model-merge pipeline (scripts only). |
| `requirements_*.txt` | Python dependencies. |

### `ailey_system/` highlights

- **Memory & identity** — `ailey_memory.py`, `character_memory.py`, `user_profile.py`,
  `rolling_summary.py`, `graph_rag.py`, `thought_graph.py`
- **Retrieval-Augmented Generation** — `ailey_rag.py`, `ailey_rag_lance.py`, `chunker.py`
- **LLM backends** — `llm_mlx.py`, `llm_gguf.py`, `llm_qwen_llamacpp.py`, `llm_coder.py`
- **Autonomy** — `idle_thinker.py`, `agent_loop.py`, `agency_queue.py`, `meta_reflection.py`,
  `proactive_store.py`
- **Creative tools** — `image_generator.py`, `music_generator.py`, `video_generator.py`,
  `creative_tools.py`, `image_stamp.py`
- **Learning engine** — `learning/` (curricula, exam prep, knowledge ingestion)
- **Integrations** — `email_monitor.py`, `portal_poller.py`, `portal_api.py`, `tools_*.py`
- **CMS** — `cms/` (schema, renderer, exporter, legal-page generator)

---

## Tech Stack

**Backend** Python 3 · Flask · MLX (Apple Silicon) · llama.cpp / GGUF · sentence-transformers ·
LanceDB · ChromaDB
**Frontend** Next.js · React · TypeScript · Tailwind · Radix UI · Monaco Editor · xterm.js
**Desktop** Tauri (Rust)
**Portal** PHP 8 · MySQL · PDO
**ML / Training** PyTorch · PEFT (DoRA/LoRA) · Hugging Face Hub

---

## Notes for Reviewers

- This repository is a **curated snapshot** — it is not the live, runnable system.
  Runtime data, model weights (multi-GB), user profiles and all secrets have been
  excluded by design.
- Configuration is provided via environment variables and `*.example` files
  (e.g. `portal/config.example.php`, `.env.example`). No real credentials are present.
- Some modules reference data paths and services that exist only in the private
  deployment; they are included to show structure and engineering approach.

---

## License

© Simon van de Loo. All rights reserved.
This code is published for portfolio / demonstration purposes only. You may read and
review it, but it may not be reused, redistributed, or deployed without permission.
