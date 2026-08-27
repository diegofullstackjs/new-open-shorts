// Injects "⚡ Criar Shorts (OpenShorts)" button directly into YouTube's action bar

function createShortifyButton() {
  if (document.getElementById("openshorts-btn")) return;

  // Target YouTube action bar under the video player
  const targetContainer = document.querySelector("#top-row #actions #top-level-buttons-computed") ||
                          document.querySelector("#actions-inner #top-level-buttons-computed");

  if (!targetContainer) return;

  const btn = document.createElement("button");
  btn.id = "openshorts-btn";
  btn.className = "openshorts-yt-button";
  btn.innerHTML = `
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
      <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"></polygon>
    </svg>
    <span>Criar Shorts</span>
  `;

  btn.addEventListener("click", async () => {
    const videoUrl = window.location.href;
    if (!videoUrl.includes("watch?v=")) {
      alert("Por favor, abra um vídeo do YouTube.");
      return;
    }

    const stored = await chrome.storage.sync.get(["os_api_url", "os_layout", "os_subtitle_style"]);
    const apiUrl = stored.os_api_url || "http://localhost:8000";
    const layout = stored.os_layout || "auto";
    const subtitleStyle = stored.os_subtitle_style || "hormozi";

    btn.disabled = true;
    btn.classList.add("loading");
    btn.querySelector("span").textContent = "Enviando...";

    try {
      const formData = new FormData();
      formData.append("url", videoUrl);
      formData.append("acknowledged", "true");
      formData.append("force_low_quality", "true");
      formData.append("layouts", layout);
      formData.append("subtitle_style", subtitleStyle);

      const resp = await fetch(`${apiUrl}/api/process`, {
        method: "POST",
        body: formData
      });

      if (resp.ok) {
        const data = await resp.json();
        btn.querySelector("span").textContent = "🚀 Processando!";
        showNotification(`Job #${data.job_id} iniciado! O OpenShorts está gerando seus cortes virais com IA.`);
      } else {
        const errText = await resp.text();
        btn.querySelector("span").textContent = "Erro!";
        alert(`Falha ao iniciar processamento: ${resp.status} - ${errText}`);
      }
    } catch (err) {
      console.error(err);
      btn.querySelector("span").textContent = "Erro Conexão";
      alert(`Não foi possível conectar à API do OpenShorts em ${apiUrl}.\nVerifique se o Colab / backend está rodando.`);
    } finally {
      setTimeout(() => {
        btn.disabled = false;
        btn.classList.remove("loading");
        btn.querySelector("span").textContent = "Criar Shorts";
      }, 4000);
    }
  });

  targetContainer.prepend(btn);
}

function showNotification(msg) {
  let toast = document.getElementById("openshorts-toast");
  if (!toast) {
    toast = document.createElement("div");
    toast.id = "openshorts-toast";
    toast.className = "openshorts-toast";
    document.body.appendChild(toast);
  }
  toast.textContent = msg;
  toast.classList.add("show");
  setTimeout(() => {
    toast.classList.remove("show");
  }, 5000);
}

// Observe URL changes (YouTube SPA navigation)
let lastUrl = location.href;
new MutationObserver(() => {
  const currentUrl = location.href;
  if (currentUrl !== lastUrl) {
    lastUrl = currentUrl;
    setTimeout(createShortifyButton, 1500);
  }
  createShortifyButton();
}).observe(document, { subtree: true, childList: true });

// Initial mount check
setTimeout(createShortifyButton, 2000);
