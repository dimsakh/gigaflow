(() => {
  const clientId = crypto.randomUUID();
  let sessionTarget = null;
  let lastEditable = null;
  let overlay = null;
  let overlayStatus = null;
  let overlayText = null;
  let bars = [];
  let hideTimer = null;

  function isEditable(element) {
    if (!(element instanceof Element)) return false;
    if (element instanceof HTMLTextAreaElement) return !element.disabled && !element.readOnly;
    if (element instanceof HTMLInputElement) {
      return !element.disabled && !element.readOnly &&
        ["text", "search", "email", "url", "tel", "password", ""].includes(element.type);
    }
    return element.isContentEditable;
  }

  document.addEventListener("focusin", (event) => {
    if (isEditable(event.target)) lastEditable = event.target;
  }, true);

  function rememberTarget() {
    const active = document.activeElement;
    sessionTarget = isEditable(active) ? active : lastEditable;
  }

  function ensureOverlay() {
    if (overlay) return;
    const host = document.createElement("div");
    host.style.cssText = "all:initial;position:fixed;z-index:2147483647;left:50%;bottom:22px;transform:translateX(-50%);pointer-events:none";
    const shadow = host.attachShadow({ mode: "closed" });
    const style = document.createElement("style");
    style.textContent = `
      .box{box-sizing:border-box;width:310px;height:74px;padding:11px 18px;border:1px solid #3c486d;border-radius:17px;background:rgba(5,8,18,.96);box-shadow:0 12px 35px rgba(0,0,0,.38);font-family:"Segoe UI",sans-serif;color:#f2f4ff}
      .top{height:24px;display:flex;align-items:center;gap:9px}.dot{width:8px;height:8px;border-radius:50%;background:#ff5577}.status{font-size:12px;font-weight:650;min-width:78px}.bars{display:flex;align-items:center;height:23px;gap:3px;margin-left:auto}.bar{display:block;width:3px;height:4px;border-radius:2px;background:#736bff;transition:height 80ms linear}
      .text{margin-top:5px;color:#c8d0e5;font-size:11px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.processing .dot,.result .dot{background:#736bff}.error .dot{background:#ff5577}
    `;
    const box = document.createElement("div");
    box.className = "box";
    box.innerHTML = `<div class="top"><span class="dot"></span><span class="status">Слушаю…</span><span class="bars"></span></div><div class="text">Говорите • пауза завершит запись</div>`;
    shadow.append(style, box);
    document.documentElement.appendChild(host);
    overlay = { host, box };
    overlayStatus = box.querySelector(".status");
    overlayText = box.querySelector(".text");
    const barsRoot = box.querySelector(".bars");
    bars = Array.from({ length: 16 }, () => {
      const bar = document.createElement("span");
      bar.className = "bar";
      barsRoot.appendChild(bar);
      return bar;
    });
  }

  function showOverlay(status, text, kind = "", autoHide = false) {
    ensureOverlay();
    clearTimeout(hideTimer);
    overlay.box.className = `box ${kind}`;
    overlayStatus.textContent = status;
    overlayText.textContent = text;
    overlay.host.style.display = "block";
    if (autoHide) hideTimer = setTimeout(() => {
      if (overlay) overlay.host.style.display = "none";
    }, 2400);
  }

  function setLevel(level) {
    ensureOverlay();
    bars.forEach((bar, index) => {
      const wave = 0.25 + Math.abs(Math.sin(index * 0.8 + Date.now() / 170)) * 0.75;
      bar.style.height = `${4 + Math.round(level * wave * 19)}px`;
    });
  }

  function insertText(text) {
    let target = sessionTarget;
    if (!target?.isConnected || !isEditable(target)) {
      target = isEditable(document.activeElement) ? document.activeElement : lastEditable;
    }
    if (!target || !isEditable(target)) return false;
    target.focus();
    if (target.isContentEditable) {
      return document.execCommand("insertText", false, text);
    }
    const start = target.selectionStart ?? target.value.length;
    const end = target.selectionEnd ?? start;
    target.setRangeText(text, start, end, "end");
    target.dispatchEvent(new InputEvent("input", {
      bubbles: true,
      inputType: "insertText",
      data: text
    }));
    target.dispatchEvent(new Event("change", { bubbles: true }));
    return true;
  }

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

  async function toggle() {
    rememberTarget();
    try {
      await api("/toggle", {
        method: "POST",
        body: JSON.stringify({ client_id: clientId })
      });
    } catch {
      showOverlay("Нет помощника", "Сначала запустите Chrome GigaFlow", "error", true);
    }
  }

  function handleEvent(event) {
    if (event.client_id && event.client_id !== clientId) return;
    if (event.type === "recording") {
      rememberTarget();
      showOverlay("Слушаю…", "Говорите • пауза завершит запись");
    } else if (event.type === "level") {
      setLevel(event.level || 0);
    } else if (event.type === "partial") {
      showOverlay("Текст онлайн", event.text || "");
    } else if (event.type === "processing") {
      showOverlay("Распознаю…", "Формирую готовый текст", "processing");
    } else if (event.type === "result") {
      const inserted = insertText(event.text);
      showOverlay(
        inserted ? "Вставлено" : "Скопировано",
        inserted ? event.text : `Ctrl+V • ${event.text}`,
        "result",
        true
      );
      sessionTarget = null;
    } else if (event.type === "error") {
      showOverlay("Не получилось", event.message || "Ошибка", "error", true);
      sessionTarget = null;
    }
  }

  chrome.runtime.onMessage.addListener((message) => {
    if (message?.type === "toggle-dictation") {
      toggle();
    } else if (message?.type === "host-event") {
      handleEvent(message.event);
    }
  });

  chrome.runtime.sendMessage({ type: "ensure-host-poll" });
})();
