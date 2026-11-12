const SERVER = "http://127.0.0.1:7860";
const key = (tabId) => `tab_${tabId}`;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function isOn(tabId) {
  const k = key(tabId);
  const r = await chrome.storage.session.get(k);
  return !!r[k];
}

async function setBadge(tabId, on) {
  try {
    await chrome.action.setBadgeText({ tabId, text: on ? "ON" : "" });
    await chrome.action.setBadgeBackgroundColor({ tabId, color: "#16a34a" });
  } catch (e) {}
}

const hostOf = (url) => { try { return new URL(url).hostname; } catch (e) { return ""; } };

async function getSettings() {
  const r = await chrome.storage.local.get({ lang: "Auto", sites: [] });
  return r;
}

async function setTabOn(tab, on) {
  await chrome.storage.session.set({ [key(tab.id)]: on });
  await setBadge(tab.id, on);
  try {
    await chrome.tabs.sendMessage(tab.id, { type: "state", on });
  } catch (e) {
    // purana tab jisme content script nahi hai -> inject karo
    if (on) {
      try {
        await chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ["content.js"] });
      } catch (err) { console.warn("inject fail", err); }
    }
  }
}

// Shortcut (Alt+T) -> is tab ka ON/OFF
chrome.commands.onCommand.addListener(async (cmd) => {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab) return;
  if (cmd === "toggle-translate") await setTabOn(tab, !(await isOn(tab.id)));
  if (cmd === "toggle-original") chrome.tabs.sendMessage(tab.id, { type: "toggleOriginal" }).catch(() => {});
});

// Navigation: "hamesha ON" wali site par apne aap ON, badge wapas lagao
chrome.tabs.onUpdated.addListener(async (tabId, info, tab) => {
  if (info.status !== "complete" && !info.status) return;
  if (info.status === "complete" && tab.url) {
    const { sites } = await getSettings();
    if (sites.includes(hostOf(tab.url)) && !(await isOn(tabId))) {
      await setTabOn(tab, true);
      return;
    }
  }
  setBadge(tabId, await isOn(tabId));
});
chrome.tabs.onRemoved.addListener((tabId) => chrome.storage.session.remove(key(tabId)));

function bufToB64(buf) {
  const bytes = new Uint8Array(buf);
  let s = "";
  for (let i = 0; i < bytes.length; i += 0x8000) {
    s += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
  }
  return btoa(s);
}

async function canvasToB64(canvas) {
  const blob = await canvas.convertToBlob({ type: "image/png" });
  return bufToB64(await blob.arrayBuffer());
}

// Extension ki request par wahi Referer lagao jo page khud bhejta hai (image hosts hotlink check karte hain)
let refererLock = Promise.resolve();
async function withPageReferer(url, pageUrl, fn) {
  const run = refererLock.then(async () => {
    let host = "";
    try { host = new URL(url).hostname; } catch (e) {}
    if (host && pageUrl && chrome.declarativeNetRequest) {
      await chrome.declarativeNetRequest.updateSessionRules({
        removeRuleIds: [1],
        addRules: [{
          id: 1, priority: 1,
          action: { type: "modifyHeaders", requestHeaders: [{ header: "referer", operation: "set", value: pageUrl }] },
          condition: { requestDomains: [host], tabIds: [-1], resourceTypes: ["xmlhttprequest"] },
        }],
      }).catch((e) => console.warn("[manga-tr] referer rule fail", e));
    }
    try { return await fn(); }
    finally { await chrome.declarativeNetRequest?.updateSessionRules({ removeRuleIds: [1] }).catch(() => {}); }
  });
  refererLock = run.catch(() => {});
  return run;
}

// Tarika 1: image URL seedha download (full quality, kisi bhi format ko PNG mein badlo)
async function fetchAsPngBase64(url, pageUrl) {
  const r = await withPageReferer(url, pageUrl, () => fetch(url, { credentials: "include" }));
  if (!r.ok) throw new Error("HTTP " + r.status);
  const bmp = await createImageBitmap(await r.blob());
  const c = new OffscreenCanvas(bmp.width, bmp.height);
  c.getContext("2d").drawImage(bmp, 0, 0);
  return canvasToB64(c);
}

// Tarika 2: screenshot + crop (rate limit ~2/sec, isliye queue)
let captureChain = Promise.resolve();
function captureCrop(tab, rect) {
  const job = captureChain.then(async () => {
    const t = await chrome.tabs.get(tab.id);
    if (!t.active) throw new Error("tab active nahi hai");
    const dataUrl = await chrome.tabs.captureVisibleTab(tab.windowId, { format: "png" });
    await sleep(550);
    const bmp = await createImageBitmap(await (await fetch(dataUrl)).blob());
    const s = bmp.width / rect.vw; // high-DPI scale
    const sw = Math.max(1, Math.round(rect.w * s));
    const sh = Math.max(1, Math.round(rect.h * s));
    const c = new OffscreenCanvas(sw, sh);
    c.getContext("2d").drawImage(bmp, Math.round(rect.x * s), Math.round(rect.y * s), sw, sh, 0, 0, sw, sh);
    return canvasToB64(c);
  });
  captureChain = job.catch(() => {});
  return job;
}

async function postServer(body) {
  let res;
  try {
    res = await fetch(SERVER + "/translate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch (e) {
    return { error: "Local server se connect nahi hua. START_SERVER.bat chalao.", retry: true };
  }
  return await res.json();
}

async function handleTranslate(msg, tab) {
  if (!tab || !(await isOn(tab.id))) return { error: "tab OFF hai" };
  const base = { lang: (await getSettings()).lang, page_url: tab.url || "" };

  // 1) content script ne canvas se image di
  if (msg.image) return postServer({ ...base, image: msg.image });

  // 2) browser se download (page ke Referer ke saath), PNG mein badlo
  let b64 = null;
  if (msg.src) b64 = await fetchAsPngBase64(msg.src, tab.url).catch((e) => { console.warn("[manga-tr] fetch fail", e); return null; });

  // 3) server khud download kare
  if (!b64 && msg.src) {
    const r = await postServer({ ...base, src: msg.src });
    if (!r.error || !/download fail/.test(r.error)) return r;
  }

  // 4) screenshot + crop (image poori screen par ho tab)
  if (!b64 && msg.rect) b64 = await captureCrop(tab, msg.rect).catch((e) => { console.warn("capture fail", e); return null; });
  if (!b64) return { error: "image nahi mil payi (poori image screen par laao)", retry: true };
  return postServer({ ...base, image: b64 });
}

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  const tab = sender.tab;
  if (msg.type === "setTab") {
    // popup se
    chrome.tabs.get(msg.tabId).then((t) => setTabOn(t, msg.on)).then(() => sendResponse({ ok: true }));
    return true;
  }
  if (msg.type === "getState") {
    isOn(tab?.id).then((on) => sendResponse({ on }));
    return true;
  }
  if (msg.type === "translate") {
    handleTranslate(msg, tab).then(sendResponse).catch((e) => sendResponse({ error: String(e) }));
    return true;
  }
});
