const $ = (id) => document.getElementById(id);

(async () => {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  let host = "";
  try { host = new URL(tab.url).hostname; } catch (e) {}

  // Firefox: site access install ke time nahi milta, user ko dena padta hai
  const ORIGINS = { origins: ["<all_urls>"] };
  if (!(await chrome.permissions.contains(ORIGINS))) {
    $("perm").style.display = "block";
    $("perm").onclick = async () => {
      if (await chrome.permissions.request(ORIGINS)) {
        $("perm").style.display = "none";
        await chrome.tabs.reload(tab.id);
      }
    };
  }

  const k = `tab_${tab.id}`;
  let on = !!(await chrome.storage.session.get(k))[k];
  const { lang, sites } = await chrome.storage.local.get({ lang: "Auto", sites: [] });

  const paint = () => {
    $("toggle").textContent = on ? "ON (this tab)" : "OFF";
    $("toggle").classList.toggle("on", on);
  };
  paint();
  $("lang").value = lang;
  $("always").checked = sites.includes(host);
  $("always").disabled = !host;

  $("toggle").onclick = async () => {
    on = !on;
    paint();
    await chrome.runtime.sendMessage({ type: "setTab", tabId: tab.id, on });
  };

  $("orig").onclick = async () => {
    try {
      const r = await chrome.tabs.sendMessage(tab.id, { type: "toggleOriginal" });
      $("orig").textContent = r && r.showOriginal ? "Show Hindi (Alt+O)" : "Show original (Alt+O)";
    } catch (e) {}
  };

  $("lang").onchange = () => chrome.storage.local.set({ lang: $("lang").value });

  $("always").onchange = async () => {
    const cur = (await chrome.storage.local.get({ sites: [] })).sites.filter((s) => s !== host);
    if ($("always").checked) {
      cur.push(host);
      if (!on) { on = true; paint(); await chrome.runtime.sendMessage({ type: "setTab", tabId: tab.id, on }); }
    }
    await chrome.storage.local.set({ sites: cur });
  };

  // server status
  try {
    const r = await (await fetch("http://127.0.0.1:7860/health")).json();
    const lines = Object.entries(r.providers || {}).map(([p, s]) =>
      `<div>${p}: <span class="${s === "ready" ? "ok" : "bad"}">${s}</span></div>`);
    const p = r.providers || {};
    const noKey = !(p.gemini === "ready" || p.groq === "ready" || String(p.gemini || "").startsWith("limit") || String(p.groq || "").startsWith("limit"));
    $("status").innerHTML = `<div class="ok">Server running (${r.device})</div>` + lines.join("") +
      `<div><a href="#" id="keys">${noKey ? "<b>Add API key (required)</b>" : "Change API keys"}</a></div>`;
    $("keys").onclick = (e) => { e.preventDefault(); chrome.tabs.create({ url: "http://127.0.0.1:7860/setup" }); };
  } catch (e) {
    $("status").innerHTML = `<span class="bad">Server is not running. Open 'Manga Translator' from the Start menu or desktop.</span>`;
  }
})();
