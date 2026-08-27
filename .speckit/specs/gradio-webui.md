# Spec: OpenShorts Gradio WebUI Suite (SpecKit)

## 1. Overview & Objective
Provide an intuitive, standalone **Gradio WebUI** (`gradio_app.py`) optimized for Google Colab, local workstations, and cloud GPUs. It centralizes all OpenShorts features:
- **Instant Video Clipping (URL or Upload)**: Cut viral vertical shorts (9:16) with Gemini intelligence, Whisper, and MediaPipe.
- **Auto-Channel Watcher Tab**: Manage & poll YouTube channels with 1-click execution.
- **Smart Scheduler Tab**: View peak-time queue, schedule posts, and dispatch to social platforms.
- **Settings & API Keys Tab**: Live Gemini key configuration, device selection (`cuda` / `cpu`), and quality parameters.
- **Dual Mode**: Can run standalone in Colab with `share=True` (or via Cloudflare tunnel) and also mounts onto the FastAPI backend at `/gradio` or runs as `gradio_app.py`.

## 2. User Experience & Wireframe Flow

### Tab 1: 🎬 Gerador de Cortes (Shorts Maker)
- **Input**: YouTube URL ou Upload de arquivo `.mp4`.
- **Options**:
  - Layout Vertical: `Auto`, `Split (2 Speakers)`, `Screencast`, `Camera Inset`, `Padrão (Crop)`.
  - Estilo de Legendas: `Hormozi`, `Karaokê Dinâmico`, `Minimalista/Clean`, `Nenhuma`.
  - Duração dos Cortes: Slider (15s a 60s).
  - Número de Cortes: Slider (1 a 10).
- **Outputs**:
  - Galeria de vídeos gerados (`gr.Video` / `gr.Gallery`).
  - Títulos sugeridos para YouTube Shorts, legendas para TikTok e Instagram com CTA.

### Tab 2: 📺 Monitor de Canais (Auto-Channel Watcher)
- **Inputs**: Adicionar Canal (URL / @handle / UC...).
- **Actions**:
  - Botão "Verificar Novos Vídeos Agora".
  - Tabela com histórico de vídeos processados e canais monitorados.

### Tab 3: 📅 Agendador Inteligente (Smart Scheduler)
- **Features**:
  - Seleção de redes (TikTok, Instagram, YouTube, LinkedIn, Facebook).
  - Visualização dos horários de pico sugeridos.
  - Tabela de posts na fila de publicação.

### Tab 4: ⚙️ Configurações & GPU
- Status da GPU (CUDA / VRAM).
- Chave de API Gemini.
