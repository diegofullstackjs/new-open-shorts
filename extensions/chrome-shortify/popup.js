document.addEventListener("DOMContentLoaded", async () => {
  const apiUrlInput = document.getElementById("apiUrl");
  const layoutInput = document.getElementById("layout");
  const subtitleStyleInput = document.getElementById("subtitleStyle");
  const saveBtn = document.getElementById("saveBtn");
  const statusDiv = document.getElementById("status");

  // Load saved settings
  const stored = await chrome.storage.sync.get(["os_api_url", "os_layout", "os_subtitle_style"]);
  if (stored.os_api_url) apiUrlInput.value = stored.os_api_url;
  if (stored.os_layout) layoutInput.value = stored.os_layout;
  if (stored.os_subtitle_style) subtitleStyleInput.value = stored.os_subtitle_style;

  saveBtn.addEventListener("click", async () => {
    const apiUrl = apiUrlInput.value.trim().replace(/\/+$/, "");
    const layout = layoutInput.value;
    const subtitleStyle = subtitleStyleInput.value;

    await chrome.storage.sync.set({
      os_api_url: apiUrl,
      os_layout: layout,
      os_subtitle_style: subtitleStyle
    });

    statusDiv.textContent = "Configurações salvas!";
    setTimeout(() => {
      statusDiv.textContent = "";
    }, 2500);
  });
});
