const API = "http://127.0.0.1:38473";
let polling = false;

async function hostRequest(path, options = {}) {
  const response = await fetch(`${API}${path}`, {
    cache: "no-store",
    ...options,
    headers: { "Content-Type": "application/json" }
  });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}

async function broadcastEvent(event) {
  const tabs = await chrome.tabs.query({});
  await Promise.allSettled(
    tabs
      .filter((tab) => tab.id)
      .map((tab) => chrome.tabs.sendMessage(
        tab.id,
        { type: "host-event", event }
      ))
  );
}

async function pollHost() {
  if (polling) return;
  polling = true;
  const stored = await chrome.storage.session.get(["hostSequence", "hostInstance"]);
  let sequence = Number(stored.hostSequence || 0);
  let instance = String(stored.hostInstance || "");
  try {
    for (;;) {
      try {
        const data = await hostRequest(
          `/events?after=${sequence}&instance=${encodeURIComponent(instance)}`
        );
        if (data.instance_id && data.instance_id !== instance) {
          instance = data.instance_id;
          sequence = 0;
        }
        for (const event of data.events || []) {
          sequence = Math.max(sequence, Number(event.sequence || 0));
          await broadcastEvent(event);
        }
        await chrome.storage.session.set({
          hostSequence: sequence,
          hostInstance: instance
        });
      } catch {
        await new Promise((resolve) => setTimeout(resolve, 1500));
      }
    }
  } finally {
    polling = false;
  }
}

async function toggleInActiveTab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.id) {
    return;
  }
  try {
    await chrome.tabs.sendMessage(tab.id, { type: "toggle-dictation" });
  } catch {
    await chrome.action.setBadgeBackgroundColor({ color: "#B4233C" });
    await chrome.action.setBadgeText({ tabId: tab.id, text: "!" });
    setTimeout(() => chrome.action.setBadgeText({ tabId: tab.id, text: "" }), 1800);
  }
}

chrome.commands.onCommand.addListener((command) => {
  if (command === "toggle-dictation") {
    toggleInActiveTab();
  }
});

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  void sender;
  if (message?.type === "popup-toggle") {
    toggleInActiveTab()
      .then(() => sendResponse({ ok: true }))
      .catch((error) => sendResponse({ ok: false, error: String(error) }));
    return true;
  } else if (message?.type === "ensure-host-poll") {
    pollHost();
  } else if (message?.type === "host-request") {
    pollHost();
    hostRequest(message.path, {
      method: message.method || "GET",
      body: message.body ? JSON.stringify(message.body) : undefined
    })
      .then((data) => sendResponse({ ok: true, data }))
      .catch((error) => sendResponse({ ok: false, error: String(error) }));
    return true;
  }
});

chrome.runtime.onStartup.addListener(pollHost);
chrome.runtime.onInstalled.addListener(pollHost);
pollHost();
