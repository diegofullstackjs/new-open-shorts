"""
OpenShorts Gradio WebUI Suite
Complete GUI for Google Colab, Local & Remote GPU Execution.
"""

import os
import sys
import json
import time
import shutil
import subprocess
from datetime import datetime, timezone
import gradio as gr
import torch

import channel_watcher
import smart_scheduler

OUTPUT_DIR = "output"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ----------------- Helper Functions -----------------

def get_gpu_status():
    if torch.cuda.is_available():
        device_name = torch.cuda.get_device_name(0)
        vram_gb = torch.cuda.get_device_properties(0).total_memory / (1024 ** 3)
        return f"🟢 CUDA Ativa: {device_name} ({vram_gb:.2f} GB VRAM)"
    return "🟡 Executando em CPU (Sem aceleração CUDA)"

def process_video_pipeline(
    video_source_type,
    youtube_url,
    uploaded_file,
    layout_mode,
    subtitle_style,
    target_clips_count,
    min_clip_duration,
    max_clip_duration,
    gemini_key,
    progress=gr.Progress(track_tqdm=True)
):
    if gemini_key and len(gemini_key.strip()) > 5:
        os.environ["GEMINI_API_KEY"] = gemini_key.strip()
    elif not os.environ.get("GEMINI_API_KEY"):
        raise gr.Error("Por favor, informe sua GEMINI_API_KEY na aba de configurações ou no campo acima.")

    progress(0.05, desc="Iniciando processamento...")
    
    # Import main pipeline
    import main as os_main

    target_video_path = None
    if video_source_type == "YouTube URL":
        if not youtube_url or "http" not in youtube_url:
            raise gr.Error("URL do YouTube inválida!")
        progress(0.1, desc="Baixando vídeo do YouTube...")
        target_video_path = os_main.download_youtube_video(youtube_url.strip())
    else:
        if not uploaded_file:
            raise gr.Error("Nenhum arquivo enviado!")
        target_video_path = uploaded_file

    if not target_video_path or not os.path.exists(target_video_path):
        raise gr.Error("Arquivo de vídeo não encontrado.")

    progress(0.25, desc="Transcrevendo áudio com Faster-Whisper...")
    words_data = os_main.transcribe_audio(target_video_path)
    
    # Prepare transcript
    full_transcript = " ".join([w.get("word", "") for w in words_data])
    words_json_str = json.dumps([{"w": w["word"], "s": round(w["start"], 3), "e": round(w["end"], 3)} for w in words_data])

    progress(0.5, desc="Identificando momentos virais com Gemini AI...")
    prompt = os_main.GEMINI_PROMPT_TEMPLATE.format(
        video_duration=round(words_data[-1]["end"] if words_data else 60, 2),
        transcript_text=full_transcript,
        words_json=words_json_str
    )
    
    # Call gemini
    gemini_response = os_main.get_gemini_analysis(prompt)
    
    shorts_list = gemini_response.get("shorts", [])
    if not shorts_list:
        raise gr.Error("Nenhum clipe viral identificado pela IA para este vídeo.")

    # Limit to target clips
    shorts_list = shorts_list[:int(target_clips_count)]
    
    output_clips = []
    metadata_cards = []

    total_shorts = len(shorts_list)
    for i, short_data in enumerate(shorts_list):
        progress_val = 0.6 + (0.35 * (i / total_shorts))
        progress(progress_val, desc=f"Renderizando clipe {i+1} de {total_shorts} (9:16 Vertical)...")

        start_time = float(short_data["start"])
        end_time = float(short_data["end"])
        clip_id = f"short_{int(time.time())}_{i+1}"
        output_clip_path = os.path.join(OUTPUT_DIR, f"{clip_id}.mp4")

        # Process clip with AI reframing
        os_main.process_video_to_vertical(
            input_video=target_video_path,
            final_output_video=output_clip_path,
            aspect_ratio=9/16
        )

        if os.path.exists(output_clip_path):
            output_clips.append(output_clip_path)
            meta_text = (
                f"### 🎬 Corte #{i+1}\n"
                f"**Título Shorts:** {short_data.get('video_title_for_youtube_short', 'Short Viral')}\n\n"
                f"**Hook Visual:** `{short_data.get('viral_hook_text', '')}`\n\n"
                f"**Legenda TikTok:**\n{short_data.get('video_description_for_tiktok', '')}\n\n"
                f"**Legenda Instagram:**\n{short_data.get('video_description_for_instagram', '')}\n"
                f"---\n"
            )
            metadata_cards.append(meta_text)

    progress(1.0, desc="Concluído!")
    combined_meta = "\n\n".join(metadata_cards)
    return output_clips, combined_meta


# ----------------- Channel Watcher Helpers -----------------

def add_watched_channel(channel_url, name, layouts, subtitle_style):
    watcher = channel_watcher.ChannelWatcher()
    cid = watcher.resolve_channel_id(channel_url)
    if not cid:
        return "❌ Não foi possível identificar o ID do canal.", get_channels_table()
    watcher.db.add_channel(cid, name=name or cid, layouts=layouts, subtitle_style=subtitle_style)
    return f"✅ Canal '{name or cid}' adicionado com sucesso!", get_channels_table()

def poll_channels_now():
    watcher = channel_watcher.ChannelWatcher()
    jobs = watcher.poll_all_channels()
    return f"🚀 Verificação concluída! {len(jobs)} novos vídeos disparados para corte.", get_processed_videos_table()

def get_channels_table():
    watcher = channel_watcher.ChannelWatcher()
    channels = watcher.db.list_channels()
    data = []
    for c in channels:
        data.append([c["channel_id"], c["name"], "Sim" if c["auto_process"] else "Não", c["layouts"], c["subtitle_style"]])
    return data

def get_processed_videos_table():
    watcher = channel_watcher.ChannelWatcher()
    videos = watcher.db.list_processed_videos(30)
    data = []
    for v in videos:
        data.append([v["title"], v["video_id"], v["status"], v["published_at"], v["created_at"]])
    return data


# ----------------- Smart Scheduler Helpers -----------------

def get_scheduled_posts_table():
    scheduler = smart_scheduler.SmartScheduler()
    posts = scheduler.db.list_all_posts(30)
    data = []
    for p in posts:
        data.append([p["id"], p["title"], p["platforms"], p["scheduled_time"], p["status"]])
    return data

def dispatch_scheduled_now():
    scheduler = smart_scheduler.SmartScheduler()
    count = scheduler.process_due_posts()
    return f"Postagens enviadas: {count}", get_scheduled_posts_table()


# ----------------- Gradio UI Definition -----------------

custom_theme = gr.themes.Soft(
    primary_hue="sky",
    secondary_hue="indigo",
    neutral_hue="slate"
)

with gr.Blocks(title="OpenShorts AI Studio") as app:
    gr.Markdown(
        """
        # ⚡ OpenShorts AI Studio
        ### Transforme vídeos longos em Shorts, TikToks e Reels virais de alta retenção (9:16) com IA.
        """
    )

    gpu_status_label = gr.Markdown(get_gpu_status())

    with gr.Tabs():
        # --- TAB 1: GERADOR DE CORTES ---
        with gr.TabItem("🎬 Gerador de Cortes (Shorts Maker)"):
            with gr.Row():
                with gr.Column(scale=1):
                    video_type = gr.Radio(["YouTube URL", "Upload de Arquivo MP4"], label="Origem do Vídeo", value="YouTube URL")
                    yt_url_input = gr.Textbox(label="URL do YouTube", placeholder="https://www.youtube.com/watch?v=...", visible=True)
                    file_input = gr.File(label="Arquivo de Vídeo (.mp4)", file_types=[".mp4", ".mov", ".mkv"], visible=False)

                    video_type.change(
                        fn=lambda t: (gr.update(visible=t == "YouTube URL"), gr.update(visible=t != "YouTube URL")),
                        inputs=video_type,
                        outputs=[yt_url_input, file_input]
                    )

                    with gr.Accordion("⚙️ Opções Avançadas de IA & Layout", open=True):
                        layout_select = gr.Dropdown(
                            ["auto", "split", "screencast", "camera_inset", "none"],
                            label="Modo de Layout Vertical",
                            value="auto"
                        )
                        sub_style_select = gr.Dropdown(
                            ["hormozi", "karaoke", "clean", "none"],
                            label="Estilo de Legendas Dinâmicas",
                            value="hormozi"
                        )
                        clips_count = gr.Slider(1, 10, value=3, step=1, label="Quantidade de Shorts a Gerar")
                        with gr.Row():
                            min_dur = gr.Slider(15, 60, value=20, step=5, label="Duração Mínima (s)")
                            max_dur = gr.Slider(20, 120, value=60, step=5, label="Duração Máxima (s)")

                    gemini_api_key_input = gr.Textbox(
                        label="Gemini API Key (Google AI Studio)",
                        placeholder="Cole sua chave aqui ou deixe vazio se já configurado no Colab",
                        type="password",
                        value=os.environ.get("GEMINI_API_KEY", "")
                    )

                    generate_btn = gr.Button("🚀 Gerar Shorts Virais com IA", variant="primary", size="lg")

                with gr.Column(scale=1):
                    output_gallery = gr.Gallery(label="Shorts Verticais Gerados (9:16)", columns=2, height="auto")
                    output_metadata = gr.Markdown(label="Títulos, Ganchos e Legendas Geradas")

            generate_btn.click(
                fn=process_video_pipeline,
                inputs=[
                    video_type,
                    yt_url_input,
                    file_input,
                    layout_select,
                    sub_style_select,
                    clips_count,
                    min_dur,
                    max_dur,
                    gemini_api_key_input
                ],
                outputs=[output_gallery, output_metadata]
            )

        # --- TAB 2: AUTO-CHANNEL WATCHER ---
        with gr.TabItem("📺 Monitor de Canais (Auto Watcher)"):
            gr.Markdown("### 📡 Monitoramento Automático de Canais do YouTube")
            with gr.Row():
                with gr.Column():
                    ch_url = gr.Textbox(label="Canal do YouTube", placeholder="URL do Canal, @handle ou ID UC...")
                    ch_name = gr.Textbox(label="Apelido / Nome do Canal", placeholder="Ex: Podcast do Diego")
                    with gr.Row():
                        ch_layout = gr.Dropdown(["auto", "split", "screencast", "none"], value="auto", label="Layout Padrão")
                        ch_subs = gr.Dropdown(["hormozi", "karaoke", "clean"], value="hormozi", label="Legendas Padrão")
                    add_ch_btn = gr.Button("➕ Adicionar Canal ao Monitoramento", variant="primary")
                    ch_status_msg = gr.Markdown()

                with gr.Column():
                    poll_now_btn = gr.Button("🔄 Verificar Novos Vídeos Agora", size="lg")
                    poll_status_msg = gr.Markdown()

            gr.Markdown("#### 📋 Canais Monitorados")
            channels_dataframe = gr.Dataframe(
                headers=["Channel ID", "Nome", "Auto-Processar", "Layout", "Legendas"],
                value=get_channels_table()
            )

            gr.Markdown("#### 🎬 Histórico de Vídeos Coletados e Processados")
            processed_dataframe = gr.Dataframe(
                headers=["Título", "Video ID", "Status", "Publicado em", "Registrado em"],
                value=get_processed_videos_table()
            )

            add_ch_btn.click(
                fn=add_watched_channel,
                inputs=[ch_url, ch_name, ch_layout, ch_subs],
                outputs=[ch_status_msg, channels_dataframe]
            )

            poll_now_btn.click(
                fn=poll_channels_now,
                inputs=[],
                outputs=[poll_status_msg, processed_dataframe]
            )

        # --- TAB 3: SMART SCHEDULER ---
        with gr.TabItem("📅 Agendador Inteligente (Smart Scheduler)"):
            gr.Markdown("### ⏰ Fila de Publicação em Horários de Maior Engajamento")
            with gr.Row():
                refresh_sched_btn = gr.Button("🔄 Atualizar Fila")
                dispatch_sched_btn = gr.Button("🚀 Disparar Posts do Horário Atual", variant="secondary")

            sched_status_label = gr.Markdown()
            scheduled_dataframe = gr.Dataframe(
                headers=["ID", "Título", "Plataformas", "Horário Agendado (UTC)", "Status"],
                value=get_scheduled_posts_table()
            )

            refresh_sched_btn.click(fn=get_scheduled_posts_table, outputs=scheduled_dataframe)
            dispatch_sched_btn.click(fn=dispatch_scheduled_now, outputs=[sched_status_label, scheduled_dataframe])

        # --- TAB 4: CONFIGURAÇÕES & GPU ---
        with gr.TabItem("⚙️ Configurações & Status"):
            gr.Markdown("### 🖥️ Informações do Ambiente de Execução")
            gr.Textbox(label="Status da GPU / CUDA", value=get_gpu_status(), interactive=False)
            gr.Markdown(
                """
                - **Faster-Whisper:** Acelerado por GPU (`float16` no Colab / CUDA).
                - **MediaPipe / YOLOv8:** Rastreamento facial e reenquadramento cinematográfico ativo.
                - **FFmpeg:** Renderização e queima de legendas com suporte a CJK e fontes virais.
                """
            )

if __name__ == "__main__":
    app.queue().launch(share=True, server_name="0.0.0.0", server_port=7860, theme=custom_theme)
