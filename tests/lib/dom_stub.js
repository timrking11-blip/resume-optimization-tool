"use strict";
/* A DOM just wide enough for artifact/index.html to run under Node's vm.
   Every element accepts any property, its methods are no-ops, and queries return more stubs.
   Nothing renders: the parity oracle calls the page's own functions and reads their results. */
const METHODS = new Set(["addEventListener", "removeEventListener", "focus", "blur", "click", "select", "remove", "append", "appendChild",
  "prepend", "setAttribute", "removeAttribute", "toggleAttribute", "scrollIntoView", "dispatchEvent", "insertAdjacentHTML", "replaceChildren"]);

function element(tag) {
  const cls = new Set();
  const store = { tagName: String(tag || "div").toUpperCase(), value: "", textContent: "", innerHTML: "", hidden: false, disabled: false,
    checked: false, dataset: {}, style: {}, options: [], selectedIndex: -1, children: [], id: "",
    classList: { add: (...c) => c.forEach(x => cls.add(x)), remove: (...c) => c.forEach(x => cls.delete(x)), contains: c => cls.has(c),
      toggle: (c, f) => { if (f === undefined) f = !cls.has(c); if (f) cls.add(c); else cls.delete(c); return f; } } };
  return new Proxy(store, {
    get(t, p) {
      if (p in t) return t[p];
      if (p === "querySelector") return () => element();
      if (p === "querySelectorAll") return () => [];
      if (p === "closest") return () => null;
      if (p === "getAttribute") return () => null;
      if (p === "getBoundingClientRect") return () => ({ left: 0, top: 0, right: 0, bottom: 0, width: 0, height: 0 });
      if (METHODS.has(p)) return () => {};
      return undefined;
    },
    set(t, p, v) { t[p] = v; return true; },
  });
}

function makeWindow() {
  const win = {};
  const document = { querySelector: () => element(), querySelectorAll: () => [], getElementById: () => element(), createElement: tag => element(tag),
    createRange: () => ({ selectNodeContents() {} }), addEventListener() {}, removeEventListener() {}, body: element("body"),
    documentElement: element("html"), characterSet: "UTF-8", activeElement: null };
  const storage = () => { const m = new Map(); return { getItem: k => (m.has(k) ? m.get(k) : null), setItem: (k, v) => { m.set(k, String(v)); },
    removeItem: k => { m.delete(k); }, clear: () => m.clear(), get length() { return m.size; } }; };
  Object.assign(win, {
    window: win, self: win, document, localStorage: storage(), sessionStorage: storage(),
    navigator: { userAgent: "node-oracle", clipboard: { writeText: async () => {} } },
    location: { href: "http://localhost/", hostname: "localhost", hash: "", search: "" },
    addEventListener() {}, removeEventListener() {}, getSelection: () => ({ removeAllRanges() {}, addRange() {} }),
    setTimeout, clearTimeout, setInterval, clearInterval, queueMicrotask, console,
    AbortController, AbortSignal, TextEncoder, TextDecoder, URL, URLSearchParams, Blob, performance,
    requestAnimationFrame: cb => setTimeout(cb, 0), cancelAnimationFrame: clearTimeout,
    btoa: s => Buffer.from(String(s), "binary").toString("base64"), atob: s => Buffer.from(String(s), "base64").toString("binary"),
  });
  // no fetch and no window.claude on purpose: the page's start() returns early and every capability resolves to nothing
  return win;
}

module.exports = { element, makeWindow };
