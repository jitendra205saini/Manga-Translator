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
    $("status").innerHTML = `<div class="ok">Server running (${r.device})</div>` + lines.join("");
  } catch (e) {
    $("status").innerHTML = `<span class="bad">Server is not running. Start START_SERVER.bat.</span>`;
  }
})();
