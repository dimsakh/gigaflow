const connection = document.querySelector("#connection");
const toggle = document.querySelector("#toggle");
const filter = document.querySelector("#filter");

async function api(path, options = {}) {
  const response = await chrome.runtime.sendMessage({
    type: "host-request",
    path,
    method: options.method || "GET",
    body: options.body ? JSON.parse(options.body) : undefined
  });
  if (!response?.ok) throw new Error(response?.error || "Помощник недоступен");
  return response.data;
}

async function refresh() {
  try {
    const state = await api("/health");
    connection.textContent = state.processing ? "Распознаёт…" : state.recording ? "Слушает…" : "Помощник запущен";
    connection.className = "online";
    filter.value = state.filler_filter || "soft";
    toggle.disabled = false;
    toggle.textContent = state.recording ? "Завершить диктовку" : "Начать диктовку";
  } catch {
    connection.textContent = "Помощник не запущен";
    connection.className = "offline";
    toggle.disabled = true;
  }
}

toggle.addEventListener("click", () => {
  chrome.runtime.sendMessage({ type: "popup-toggle" });
  window.close();
});

filter.addEventListener("change", async () => {
  try {
    await api("/settings", {
      method: "POST",
      body: JSON.stringify({ filler_filter: filter.value })
    });
  } catch {
    await refresh();
  }
});

refresh();
