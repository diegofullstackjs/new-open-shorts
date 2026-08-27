# OpenShorts Automation SpecKit Constitution

## Core Principles
1. **Zero Degradation**: Do not break existing OpenShorts REST API, MCP or CLI workflows.
2. **GPU Optimization**: Google Colab environments must leverage CUDA for Faster-Whisper, PySceneDetect, and MediaPipe/YOLOv8.
3. **Spec-Driven Architecture**:
   - `01-colab-runner`: Google Colab GPU-ready notebook & tunnel runner.
   - `02-channel-watcher`: Async RSS / YouTube XML feed watcher & automatic processor.
   - `03-smart-scheduler`: Multi-platform queue & optimal timing scheduler for social distributions.
   - `04-chrome-extension`: Chrome Manifest V3 extension for 1-Click Shortify directly from YouTube.
4. **Reliability & Idempotency**: State tracking (e.g. SQLite / JSON store) to ensure no video is processed or scheduled twice.
