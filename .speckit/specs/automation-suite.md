# Spec: OpenShorts Automation Suite

## Overview
This specification covers the implementation of:
1. Google Colab Notebook Runner for GPU-accelerated video processing.
2. Auto-Channel Watcher (monitoring YouTube RSS feeds / channels and auto-submitting jobs).
3. Smart Scheduling Pipeline (calculating optimal social media times and queuing auto-posts).
4. Chrome Extension "1-Click Shortify" (browser-level submission).

## Architecture & Data Contracts

### 1. Colab Runner (`openshorts_colab.ipynb`)
- Installs system dependencies (`ffmpeg`, `fonts-noto-cjk`, etc.).
- Clones / pulls codebase and installs Python requirements with GPU-ready torch / faster-whisper.
- Exposes API via Ngrok / Cloudflare Tunnel / LocalTunnel or runs batch jobs locally with CUDA.

### 2. Auto-Channel Watcher (`channel_watcher.py` & API endpoint)
- Sources: YouTube Channel RSS (`https://www.youtube.com/feeds/videos.xml?channel_id=...` or `@handle` resolution).
- Storage: SQLite (`output/watcher.db`) storing `video_id`, `channel_id`, `published_at`, `status`, `job_id`, `created_at`.
- Polling: Periodic background task or standalone CLI runner (`python -m channel_watcher --poll-interval 300`).
- Integration: Calls `app.py` `/api/process` internally or over HTTP.

### 3. Smart Scheduling (`smart_scheduler.py` & API endpoint)
- Platforms supported: TikTok, Instagram, YouTube Shorts, LinkedIn, Facebook.
- Logic: Time window calculation (peak engagement slots: 12:00, 18:00, 21:00 UTC/local) with spacing interval (min 4 hours between posts).
- Queue Storage: SQLite (`output/scheduler.db`) storing `post_id`, `clip_path`, `platforms`, `scheduled_time`, `status`, `metadata`.
- Runner: Background daemon / endpoint `/api/scheduler/schedule`.

### 4. Chrome Extension "1-Click Shortify" (`extensions/chrome-shortify/`)
- Manifest V3 compliant.
- Injects a "⚡ Criar Shorts com OpenShorts" button beside YouTube actions on `youtube.com/watch*`.
- Popup settings: Target API URL (Colab / Localhost / Cloud API) + API Key (if required).
- Sends `POST /api/process` with YouTube URL, toast notifications on status.
