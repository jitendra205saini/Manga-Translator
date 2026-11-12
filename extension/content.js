(() => {
  if (window.__mangaTrLoaded) return;
  window.__mangaTrLoaded = true;

  const MIN_W = 400;
  const MIN_H = 300;
  let on = false;
  let seen = new WeakSet();   // har image sirf ek baar
  const originals = new Map(); // OFF par wapas lagane ke liye
  const queue = [];
  let io = null;
  let mo = null;

  const inView = (img) => {
    const r = img.getBoundingClientRect();
    return r.bottom > 0 && r.top < innerHeight && r.right > 0 && r.left < innerWidth;
  };

  function isCandidate(img) {
    // screen par chhoti dikhne wali (thumbnails, ads) skip
    if (img.getBoundingClientRect().width < 350) return false;
    return img.complete && img.naturalWidth >= MIN_W && img.naturalHeight >= MIN_H &&
      !img.dataset.mtDone && !seen.has(img);
  }

  function enqueue(img) {
    if (!on || !isCandidate(img)) return;
    seen.add(img);
    queue.push(img);
    pump();
  }

  // ek saath 3 pages (AI ka intezaar parallel mein)
  const WORKERS = 3;
  let active = 0;
  function pump() {
    while (on && active < WORKERS && queue.length) {
      // jo page screen ke sabse paas hai wo pehle
      queue.sort((a, b) => Math.abs(a.getBoundingClientRect().top) - Math.abs(b.getBoundingClientRect().top));
      const img = queue.shift();
      if (!img.isConnected) continue;
      active++;
      // 90s mein jawab na aaye to chhod do, worker atke nahi
      const timeout = new Promise((r) => setTimeout(() => r("timeout"), 90000));
      Promise.race([processImage(img), timeout]).then((r) => {
        if (r === "timeout") { console.warn("[manga-tr] timeout", img.src); seen.delete(img); }
      }).finally(() => { active--; pump(); });
    }
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
    const r = img.getBoundingClientRect();
    const full = r.top >= 0 && r.left >= 0 && r.bottom <= innerHeight && r.right <= innerWidth;
    return full ? { x: r.left, y: r.top, w: r.width, h: r.height, vw: innerWidth } : null;
  }

  async function processImage(img) {
    const src = img.currentSrc || img.src;
    const oldOutline = img.style.outline;
    img.style.outline = "3px dashed orange";
    try {
      const msg = { type: "translate", image: canvasBase64(img) };
      if (!msg.image) {
        if (/^https?:/.test(src)) msg.src = src;
        msg.rect = fullRect(img);
      }
      const res = await chrome.runtime.sendMessage(msg);
      if (!on) return;
      if (res && res.image) {
        originals.set(img, { src: img.src, srcset: img.getAttribute("srcset") });
        img.removeAttribute("srcset");
        const pic = img.closest("picture");
        if (pic) pic.querySelectorAll("source").forEach((s) => {
          s.dataset.mtSrcset = s.getAttribute("srcset") || "";
          s.removeAttribute("srcset");
        });
        img.dataset.mtDone = "1";
        img.src = "data:image/png;base64," + res.image;
      } else if (res && res.error) {
        console.warn("[manga-tr]", res.error);
        if (res.retry) setTimeout(() => seen.delete(img), 5000);
      }
    } catch (e) {
      console.warn("[manga-tr]", e);
      setTimeout(() => seen.delete(img), 5000);  // background so gaya / error: baad mein dobara
    } finally {
      img.style.outline = oldOutline;
    }
  }

  function restoreAll() {
    for (const [img, o] of originals) {
      if (o.srcset) img.setAttribute("srcset", o.srcset);
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

  // har 3s: screen ke paas wali bachi hui images dobara check (fail/miss hui ho to retry)
  let scanTimer = null;
  function scan() {
    document.querySelectorAll("img").forEach((img) => {
      const r = img.getBoundingClientRect();
      if (r.bottom > -1500 && r.top < innerHeight + 1500) enqueue(img);
    });
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
    }, { threshold: [0, 0.5, 1], rootMargin: "1500px 0px" });  // aage ke pages pehle se translate
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
    scanTimer = setInterval(scan, 3000);
  }

  function stop() {
    if (io) io.disconnect();
    if (mo) mo.disconnect();
    io = mo = null;
    clearInterval(scanTimer);
    queue.length = 0;
    restoreAll();
  }

  chrome.runtime.onMessage.addListener((msg) => {
    if (msg.type === "state") {
      on = msg.on;
      on ? start() : stop();
    }
  });

  chrome.runtime.sendMessage({ type: "getState" })
    .then((r) => { if (r && r.on) { on = true; start(); } })
    .catch(() => {});
})();
