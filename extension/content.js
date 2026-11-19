(() => {
  if (window.__mangaTrLoaded) return;
  window.__mangaTrLoaded = true;

  const MIN_W = 400;
  const MIN_H = 300;
  const AHEAD = 4000;          // screen se itne px aage tak ke pages pehle se translate
  let on = false;
  let seen = new WeakSet();   // har image sirf ek baar
  const originals = new Map(); // OFF par wapas lagane ke liye
  let showOriginal = false;    // Alt+O: original / Hindi ke beech badlo

  function toggleOriginal() {
    showOriginal = !showOriginal;
    for (const [img, o] of originals) {
      if (o.hindi) img.src = showOriginal ? o.src : o.hindi;
    }
    return showOriginal;
  }
  const queue = [];
  let io = null;
  let mo = null;

  const inView = (img) => {
    const r = img.getBoundingClientRect();
    return r.bottom > 0 && r.top < innerHeight && r.right > 0 && r.left < innerWidth;
  };

  // lazy-load wali sites: asli URL data-src jaise attribute mein hota hai, image abhi load nahi hui
  const LAZY = ["data-src", "data-lazy-src", "data-original", "data-url"];
  function lazySrc(img) {
    for (const a of LAZY) {
      const v = (img.getAttribute(a) || "").trim();
      if (/^(https?:)?\/\//.test(v)) return new URL(v, location.href).href;
    }
    // browser ka apna lazy-load: tab chhod do to image kabhi load nahi hoti, URL seedha bhejo
    if (img.loading === "lazy" && /^https?:/.test(img.src)) return img.src;
    return null;
  }
  // ---------- webtoon: site ne lambi image tukdon mein kaati, bubble do tukdon mein bat jaata hai ----------
  // upar/neeche chipke hue (same chaudai) tukde dhoondho, unhe saath bhejo
  function adjacent(cur, dir) {
    const r = cur.getBoundingClientRect();
    if (r.height < 5) return null;
    let best = null, bg = 1e9;
    for (const i of document.images) {
      if (i === cur) continue;
      const q = i.getBoundingClientRect();
      if (q.height < 5 || Math.abs(q.width - r.width) > 0.15 * r.width) continue;
      if (Math.min(q.right, r.right) - Math.max(q.left, r.left) < 0.5 * r.width) continue;
      const gap = dir > 0 ? q.top - r.bottom : r.top - q.bottom;
      if (gap > -5 && gap < 40 && gap < bg) { bg = gap; best = i; }
    }
    return best;
  }
  function origSrc(nb) {
    const o = originals.get(nb);
    const s = o ? o.src : nb.currentSrc || nb.src;
    try { return new URL(s, location.href).href; } catch (e) { return null; }
  }
  function stack(img, dir) {
    const out = [];
    let cur = img, tot = 0;
    for (let k = 0; k < 4; k++) {
      const nb = adjacent(cur, dir);
      if (!nb || !nb.complete || !nb.naturalWidth) break;
      const src = origSrc(nb);
      if (!src || !/^https?:/.test(src)) break;
      out.push({ img: nb, src, w: nb.naturalWidth, h: nb.naturalHeight });
      tot += nb.naturalHeight * img.naturalWidth / nb.naturalWidth;
      if (tot >= 500) break;
      cur = nb;
    }
    return out;
  }
  const inStack = (img) => !!(adjacent(img, 1) || adjacent(img, -1));

  // padosi ka kata bubble is page par: target img -> Map(source img -> [{url, rects, y0, s}])
  const spills = new Map();
  function addSpills(res, own, prev, next) {
    if (!res.spill || !res.ctx) return;
    const W = own.naturalWidth;
    const touched = new Set();
    for (const sp of res.spill) {
      const isPrev = sp.dir === "prev";
      const url = "data:image/png;base64," + sp.patch;
      const list = (isPrev ? prev : next).slice(0, res.ctx[isPrev ? 0 : 1]);
      const hs = list.map((n) => Math.max(1, Math.round(n.h * W / n.w)));
      let acc = 0;
      list.forEach((n, k) => {
        if (!spills.has(n.img)) spills.set(n.img, new Map());
        const m = spills.get(n.img);
        // ek source ka ek hi (taaza) patch: redo par purana hata do
        const arr = (touched.has(n.img) ? m.get(own) : null) || [];
        // next: patch upar se, paas wala tukda sabse upar. prev: y0 compose mein patch ki oonchai se
        arr.push({ url, rects: sp.rects, s: n.w / W, y0: isPrev ? null : acc, stackHs: hs, idx: k });
        m.set(own, arr);
        touched.add(n.img);
        acc += hs[k];
      });
    }
    for (const t of touched) compose(t);
  }
  const loadImg = (u) => new Promise((ok, no) => { const i = new Image(); i.onload = () => ok(i); i.onerror = no; i.src = u; });
  async function compose(t) {
    const o = originals.get(t), m = spills.get(t);
    if (!o || !o.base || !m || !m.size) return;
    const tok = (o.tok = (o.tok || 0) + 1);
    try {
      const base = await loadImg(o.base);
      const c = document.createElement("canvas");
      c.width = base.naturalWidth;
      c.height = base.naturalHeight;
      const ctx = c.getContext("2d");
      ctx.drawImage(base, 0, 0);
      for (const arr of m.values()) for (const sp of arr) {
        const p = await loadImg(sp.url);
        let y0 = sp.y0;
        if (y0 == null) {
          // prev: patch ke neeche se ginti; paas wala tukda (idx 0) sabse neeche
          let acc = p.naturalHeight;
          for (let k = 0; k <= sp.idx; k++) acc -= sp.stackHs[k];
          y0 = acc;
        }
        const th = c.height / sp.s;  // target ki oonchai patch ke scale mein
        for (const [x0, ry0, x1, ry1] of sp.rects) {
          const a = Math.max(ry0, y0), b = Math.min(ry1, y0 + th);
          if (b <= a) continue;
          ctx.drawImage(p, x0, a, x1 - x0, b - a, x0 * sp.s, (a - y0) * sp.s, (x1 - x0) * sp.s, (b - a) * sp.s);
        }
      }
      if (tok !== o.tok || !originals.has(t)) return;
      o.hindi = c.toDataURL("image/png");
      for (const a in o.lazyAttrs || {}) t.setAttribute(a, o.hindi);
      if (!showOriginal) t.src = o.hindi;
    } catch (e) { console.warn("[manga-tr] spill compose fail", e); }
  }

  const loaded = (img) => img.complete && img.naturalWidth >= MIN_W &&
    (img.naturalHeight >= MIN_H || (img.naturalHeight >= 40 && inStack(img)));

  function isCandidate(img) {
    if (img.dataset.mtDone || seen.has(img)) return false;
    // screen par chhoti dikhne wali (thumbnails, ads) skip
    if (img.getBoundingClientRect().width < 350) return false;
    return loaded(img) || !!lazySrc(img);
  }

  function enqueue(img) {
    if (!on || !isCandidate(img)) return;
    seen.add(img);
    queue.push(img);
    badge(img, "wait");
    pump();
  }

  // ---------- loading parda: user ko dikhe ki page translate ho raha hai ----------
  const badges = new Map();
  let styled = false;
  let limitUntil = 0;
  function limitText() {
    const m = Math.max(1, Math.ceil((limitUntil - Date.now()) / 60000));
    return `AI ki free limit khatam — ~${m} min baad apne aap`;
  }
  setInterval(() => {
    if (limitUntil > Date.now()) for (const [img, el] of badges) if (el.classList.contains("limit")) el.querySelector("span").textContent = limitText();
  }, 20000);
  function badge(img, state) {
    let el = badges.get(img);
    if (!state) { if (el) { el.remove(); badges.delete(img); } return; }
    if (!styled) {
      styled = true;
      const st = document.createElement("style");
      st.textContent = `
        .mt-ov{position:absolute;z-index:2147483646;pointer-events:none;display:flex;justify-content:center;
          background:rgba(0,0,0,.18);transition:background .3s}
        .mt-ov.work{background:rgba(0,0,0,.55)}
        .mt-ov>div{position:sticky;top:45vh;align-self:flex-start;margin-top:40px;display:flex;align-items:center;gap:10px;
          background:rgba(20,20,20,.85);color:#fff;font:600 15px/1.2 system-ui,sans-serif;padding:10px 16px;border-radius:22px}
        .mt-ov i{width:18px;height:18px;border:3px solid #fff4;border-top-color:#ff9a3c;border-radius:50%;
          animation:mtspin .8s linear infinite;display:none}
        .mt-ov.work i{display:block}
        @keyframes mtspin{to{transform:rotate(360deg)}}`;
      document.documentElement.appendChild(st);
    }
    if (!el) {
      el = document.createElement("div");
      el.className = "mt-ov";
      el.innerHTML = "<div><i></i><span></span></div>";
      document.body.appendChild(el);
      badges.set(img, el);
    }
    el.classList.toggle("work", state === "work");
    el.classList.toggle("limit", state === "limit");
    el.querySelector("span").textContent = state === "work" ? "अनुवाद हो रहा है…" : state === "limit" ? limitText() : "कतार में…";
    place(img, el);
  }
  function place(img, el) {
    const r = img.getBoundingClientRect();
    if (!img.isConnected || !r.width) { el.style.display = "none"; return; }
    Object.assign(el.style, { display: "flex", left: r.left + scrollX + "px", top: r.top + scrollY + "px",
      width: r.width + "px", height: r.height + "px" });
  }
  let raf = 0;
  const placeAll = () => {
    if (!raf) raf = requestAnimationFrame(() => { raf = 0; badges.forEach((el, img) => place(img, el)); });
  };
  addEventListener("scroll", placeAll, { passive: true });
  addEventListener("resize", placeAll);
  setInterval(placeAll, 1000);  // lazy images load hone se layout khisakta hai

  // ek saath 5 pages (AI ka intezaar parallel mein)
  const WORKERS = 5;
  let active = 0;
  function pump() {
    if (limitUntil > Date.now()) {
      for (const q of queue) badge(q, "limit");
      clearTimeout(pump.t);
      pump.t = setTimeout(pump, limitUntil - Date.now() + 3000);
      return;
    }
    while (on && active < WORKERS && queue.length) {
      // chapter upar se neeche, kram se (mouse/scroll kahin bhi ho)
      queue.sort((a, b) => a.getBoundingClientRect().top - b.getBoundingClientRect().top);
      const img = queue.shift();
      if (!img.isConnected) continue;
      active++;
      // 3 min mein jawab na aaye to chhod do (server limit khulne ka intezaar karta hai), phir dobara
      const timeout = new Promise((r) => setTimeout(() => r("timeout"), 180000));
      Promise.race([processImage(img), timeout]).then((r) => {
        if (r === "timeout") { console.warn("[manga-tr] timeout", img.src); retryLater(img); }
      }).finally(() => {
        active--;
        pump();
        if (!active && !queue.length && !badges.size && originals.size >= 3) prefetchNext();
      });
    }
  }

  // fail hua page khud dobara bhejo (scroll ka intezaar nahi): 15s, 45s, 90s baad
  const tries = new WeakMap();
  const gaveUp = new Set();
  // tab par wapas aaye: jo pages chhoot gaye the (screenshot ki zaroorat thi) unhe phir se
  document.addEventListener("visibilitychange", () => {
    if (document.hidden || !on) return;
    for (const img of gaveUp) { tries.delete(img); seen.delete(img); enqueue(img); }
    gaveUp.clear();
  });
  function retryLater(img) {
    const n = (tries.get(img) || 0) + 1;
    tries.set(img, n);
    if (n > 3) { console.warn("[manga-tr] 3 baar fail, tab par wapas aane par dobara", img.src); gaveUp.add(img); badge(img, null); return; }
    badge(img, "wait");
    setTimeout(() => { seen.delete(img); if (on) enqueue(img); }, [15000, 45000, 90000][n - 1]);
  }

  // ---------- right-click "dobara translate": cache chhod ke naya ----------
  const fresh = new WeakSet();
  function redo(srcUrl) {
    const img = [...document.images].find((i) => i.src === srcUrl || i.currentSrc === srcUrl);
    if (!img) return false;
    const o = originals.get(img);
    if (o) {
      if (o.srcset) img.setAttribute("srcset", o.srcset);
      for (const a in o.lazyAttrs || {}) img.setAttribute(a, o.lazyAttrs[a]);
      originals.delete(img);
      img.src = o.src;
    }
    delete img.dataset.mtDone;
    seen.delete(img);
    tries.delete(img);
    gaveUp.delete(img);
    fresh.add(img);
    const go = () => enqueue(img);
    if (img.complete && img.naturalWidth) setTimeout(go, 50);
    else img.addEventListener("load", go, { once: true });
    return true;
  }

  // ---------- agla chapter: is chapter ke saare page ho gaye to agle ke pehle 4 pehle se ----------
  let prefetched = false;
  const NEXT_TXT = /^\s*(next|next chapter|next chap|ch\.? ?next|다음|다음 화|下一[章话話页]|अगला)\s*[>»→›]*\s*$/i;
  function nextChapterUrl() {
    const rel = document.querySelector('a[rel="next"][href], link[rel="next"][href]');
    if (rel) return rel.href;
    for (const a of document.querySelectorAll("a[href]")) {
      const t = (a.textContent || a.getAttribute("title") || a.getAttribute("aria-label") || "").trim();
      if (NEXT_TXT.test(t) || /next[-_ ]?chap/i.test(a.className + " " + a.id)) return a.href;
    }
    return null;
  }
  async function prefetchNext() {
    if (prefetched || !on) return;
    const href = nextChapterUrl();
    if (!href || href === location.href || new URL(href).origin !== location.origin) return;
    prefetched = true;
    try {
      const html = await (await fetch(href, { credentials: "include" })).text();
      const doc = new DOMParser().parseFromString(html, "text/html");
      const urls = [];
      for (const i of doc.querySelectorAll("img")) {
        let u = null;
        for (const a of [...LAZY, "src"]) {
          const v = (i.getAttribute(a) || "").trim();
          if (/^(https?:)?\/\//.test(v) || (a === "src" && v && !v.startsWith("data:"))) { u = new URL(v, href).href; break; }
        }
        if (!u || /logo|icon|avatar|banner|ads?[/_-]|sprite|\.gif(\?|$)|\.svg(\?|$)/i.test(u)) continue;
        const w = +i.getAttribute("width") || 0;
        if (w && w < 300) continue;
        if (!urls.includes(u)) urls.push(u);
        if (urls.length >= 4) break;
      }
      if (urls.length) {
        console.log("[manga-tr] agla chapter pehle se:", urls.length, "pages");
        chrome.runtime.sendMessage({ type: "prefetch", urls }).catch(() => {});
      }
    } catch (e) { console.warn("[manga-tr] prefetch fail", e); }
  }

  // Tarika 0: same-origin image ho to seedha canvas se
  function canvasBase64(img) {
    try {
      const c = document.createElement("canvas");
      c.width = img.naturalWidth;
      c.height = img.naturalHeight;
      c.getContext("2d").drawImage(img, 0, 0);
      return c.toDataURL("image/png").split(",")[1];
    } catch (e) {
      return null; // cross-origin -> canvas taint
    }
  }

  function fullRect(img) {
    // screenshot sirf dikh rahe tab ka hota hai: tab chhoda hua ho to galat page aa jaata
    if (document.hidden) return null;
    const r = img.getBoundingClientRect();
    const full = r.top >= 0 && r.left >= 0 && r.bottom <= innerHeight && r.right <= innerWidth;
    return full ? { x: r.left, y: r.top, w: r.width, h: r.height, vw: innerWidth } : null;
  }

  async function processImage(img) {
    const lazy = loaded(img) ? null : lazySrc(img);
    const src = lazy || img.currentSrc || img.src;
    badge(img, "work");
    let ok = false;
    try {
      const msg = { type: "translate", image: lazy ? null : canvasBase64(img), fresh: fresh.delete(img) };
      const prev = lazy ? [] : stack(img, -1), next = lazy ? [] : stack(img, 1);
      msg.prev = prev.map((n) => ({ src: n.src }));
      msg.next = next.map((n) => ({ src: n.src }));
      if (/^https?:/.test(src)) msg.url = src;  // agla chapter pehle se translate hua ho to seedha cache
      if (lazy) {
        msg.src = lazy;
        if ((tries.get(img) || 0) >= 1) { gaveUp.add(img); badge(img, "wait"); return; }  // 403: load hone ka intezaar
      } else if (!msg.image) {
        if (/^https?:/.test(src)) msg.src = src;
        msg.rect = fullRect(img);
      }
      const res = await chrome.runtime.sendMessage(msg);
      // OFF ho gaya, ya timeout ke baad dobara bheja hua page pehle hi lag gaya: purana jawab mat lagao
      if (!on || img.dataset.mtDone) return;
      if (res && res.image) {
        const lazyAttrs = {};
        for (const a of LAZY) if (img.hasAttribute(a)) lazyAttrs[a] = img.getAttribute(a);
        originals.set(img, { src: img.getAttribute("src") || src, srcset: img.getAttribute("srcset"), lazyAttrs });
        img.removeAttribute("srcset");
        const pic = img.closest("picture");
        if (pic) pic.querySelectorAll("source").forEach((s) => {
          s.dataset.mtSrcset = s.getAttribute("srcset") || "";
          s.removeAttribute("srcset");
        });
        img.dataset.mtDone = "1";
        const hindi = "data:image/png;base64," + res.image;
        originals.get(img).hindi = hindi;
        originals.get(img).base = hindi;
        // site ka lazy-loader baad mein original wapas na laga de
        for (const a in lazyAttrs) img.setAttribute(a, hindi);
        if (!showOriginal) img.src = hindi;
        ok = true;
        addSpills(res, img, prev, next);
        compose(img);
      } else if (res && res.retry_after) {
        // AI ki free limit khatam: page par saaf batao, limit khulte hi apne aap (tries nahi ginte)
        limitUntil = Math.max(limitUntil, Date.now() + res.retry_after * 1000);
        badge(img, "limit");
        setTimeout(() => { seen.delete(img); if (on && !img.dataset.mtDone) enqueue(img); }, res.retry_after * 1000 + 3000);
      } else if (res && res.error) {
        console.warn("[manga-tr]", res.error);
        retryLater(img);
      } else if (res) {
        // is page par translate karne ko kuch nahi (bina text ka page / patli patti): waisa hi rehne do
        img.dataset.mtDone = "1";
        ok = true;
      }
    } catch (e) {
      console.warn("[manga-tr]", e);
      retryLater(img);  // background so gaya / error: thodi der baad dobara
    } finally {
      if (ok || !on) badge(img, null);
    }
  }

  function restoreAll() {
    for (const [img, o] of originals) {
      if (o.srcset) img.setAttribute("srcset", o.srcset);
      for (const a in o.lazyAttrs || {}) img.setAttribute(a, o.lazyAttrs[a]);
      img.src = o.src;
      delete img.dataset.mtDone;
      const pic = img.closest("picture");
      if (pic) pic.querySelectorAll("source").forEach((s) => {
        if (s.dataset.mtSrcset) s.setAttribute("srcset", s.dataset.mtSrcset);
        delete s.dataset.mtSrcset;
      });
    }
    originals.clear();
  }

  // har 3s: poore chapter ki bachi hui images (kram queue khud sambhalti hai: upar se neeche)
  let scanTimer = null;
  function scan() {
    // lazy URL download se mana (403) hua tha, ab image page par load ho gayi: is baar seedha usi se
    for (const img of gaveUp) if (loaded(img)) { gaveUp.delete(img); tries.delete(img); seen.delete(img); }
    document.querySelectorAll("img").forEach(enqueue);
  }

  function watch(img) {
    io.observe(img);
  }

  function start() {
    if (io) return;
    seen = new WeakSet();
    io = new IntersectionObserver((entries) => {
      for (const e of entries) {
        if (!e.isIntersecting) continue;
        const img = e.target;
        if (img.complete && img.naturalWidth) enqueue(img);
        else img.addEventListener("load", () => enqueue(img), { once: true });
      }
    }, { threshold: [0, 0.5, 1], rootMargin: `${AHEAD}px 0px` });
    document.querySelectorAll("img").forEach(watch);

    // infinite scroll / naye pages
    mo = new MutationObserver((muts) => {
      for (const m of muts) for (const n of m.addedNodes) {
        if (n.nodeType !== 1) continue;
        if (n.tagName === "IMG") watch(n);
        else if (n.querySelectorAll) n.querySelectorAll("img").forEach(watch);
      }
    });
    mo.observe(document.documentElement, { childList: true, subtree: true });
    scan();
    scanTimer = setInterval(scan, 3000);
  }

  function stop() {
    if (io) io.disconnect();
    if (mo) mo.disconnect();
    io = mo = null;
    clearInterval(scanTimer);
    queue.length = 0;
    badges.forEach((el) => el.remove());
    badges.clear();
    restoreAll();
  }

  chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
    if (msg.type === "redo") {
      sendResponse({ ok: on && redo(msg.srcUrl) });
      return;
    }
    if (msg.type === "progress") {
      const done = [...originals.keys()].filter((i) => i.isConnected).length;
      sendResponse({ done, total: done + badges.size + gaveUp.size, failed: gaveUp.size, limitMin: limitUntil > Date.now() ? Math.ceil((limitUntil - Date.now()) / 60000) : 0 });
      return;
    }
    if (msg.type === "toggleOriginal") {
      sendResponse({ showOriginal: toggleOriginal() });
      return;
    }
    if (msg.type === "state") {
      on = msg.on;
      on ? start() : stop();
    }
  });

  chrome.runtime.sendMessage({ type: "getState" })
    .then((r) => { if (r && r.on) { on = true; start(); } })
    .catch(() => {});
})();
