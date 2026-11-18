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
  const { lang, sites, fast, backup } = await chrome.storage.local.get({ lang: "Auto", sites: [], fast: false, backup: false });

  const paint = () => {
    $("toggle").textContent = on ? "ON (this tab)" : "OFF";
    $("toggle").classList.toggle("on", on);
  };
  paint();
  $("lang").value = lang;
  $("fast").checked = fast;
  $("fast").onchange = () => chrome.storage.local.set({ fast: $("fast").checked });
  $("backup").checked = backup;
  $("backup").onchange = () => chrome.storage.local.set({ backup: $("backup").checked });
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

  // is chapter ki progress: kitne page ho gaye
  async function progress() {
    try {
      const p = await chrome.tabs.sendMessage(tab.id, { type: "progress" });
      if (!p || !p.total) { $("prog").style.display = "none"; return; }
      $("prog").style.display = "block";
      $("progbar").style.width = Math.round(100 * p.done / p.total) + "%";
      $("progtxt").textContent = p.done >= p.total ? `Chapter done: ${p.done} pages` :
        `${p.done} / ${p.total} pages translated` + (p.limitMin ? ` — AI free limit over, resumes in ~${p.limitMin} min` : p.failed ? ` (${p.failed} will retry)` : "");
    } catch (e) { $("prog").style.display = "none"; }
  }
  progress();
  setInterval(progress, 1000);

  const extVer = chrome.runtime.getManifest().version;
  $("ver").textContent = "v" + extVer;
  // server status: jawab na aaye to "start ho raha hai" dikhao aur har 2s dobara dekho
  const opened = Date.now();
  async function serverStatus() {
  try {
    const r = await (await fetch("http://127.0.0.1:47391/health")).json();
    const lines = Object.entries(r.providers || {}).filter(([, s]) => s !== "not installed").map(([p, s]) =>
      `<div>${p}: <span class="${s === "ready" ? "ok" : "bad"}">${s}</span></div>`);
    const p = r.providers || {};
    const noKey = !(p.gemini === "ready" || p.groq === "ready" || String(p.gemini || "").startsWith("limit") || String(p.groq || "").startsWith("limit"));
    const u = r.usage || {};
    const gUsed = u.gemini || 0, gLim = u.gemini_limit || 500;
    const usage = `<div class="usage"><b>Today</b>: ${u.pages || 0} pages translated` +
      (u.cached ? `, ${u.cached} from cache` : "") +
      `<br>Gemini: ${gUsed} of ~${gLim} requests (${Math.max(0, gLim - gUsed)} left)` +
        (u.reset_in ? `<br>Resets at ${new Date(Date.now() + u.reset_in * 1000).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })} (in ${Math.floor(u.reset_in / 3600)}h ${Math.floor(u.reset_in % 3600 / 60)}m)` : "") +
      (u.groq ? `<br>Groq: ${u.groq} requests` : "") +
      (u.backup ? `<br>Backup translator: ${u.backup} pages` : "") +
      (!r.backup && $("backup").checked ? `<br><span class="bad">Backup translator: no key. Add it in Change API keys.</span>` : "") + `</div>`;
    $("status").innerHTML = `<div class="ok">Server running${r.version ? " (v" + r.version + ")" : ""}</div>` +
      (r.version && r.version !== extVer ? `<div class="bad">Version mismatch: extension v${extVer}, server v${r.version}. Update the older one.</div>` : "") + lines.join("") + usage +
      `<div><a href="#" id="keys">${noKey ? "<b>Add API key (required)</b>" : "Change API keys"}</a></div>`;
    $("keys").onclick = (e) => { e.preventDefault(); chrome.tabs.create({ url: "http://127.0.0.1:47391/setup" }); };
  } catch (e) {
    const waited = Math.round((Date.now() - opened) / 1000);
    $("status").innerHTML = waited < 45
      ? `<span class="starting"><i class="spin"></i>Server starting… please wait (${waited}s)</span>`
      : `<span class="bad">Server is not running. Open 'Manga Translator' from the Start menu or desktop.</span>` +
        `<div style="opacity:.7">Still checking every 2 seconds…</div>`;
    setTimeout(serverStatus, 2000);
  }
  }
  serverStatus();
})();
