/* ==========================================================================
 *  user's Homepage — peak-1990s (GeoCities) custom.js
 *  Loaded by Homepage from /app/config/custom.js (served at /api/config/custom.js,
 *  injected with next/script after hydration). Safe to load more than once.
 *
 *  Injects:  #y2k-marquee   live status ticker (top of page, refreshed every 60 s)
 *            .y2k-construction  "UNDER CONSTRUCTION" banner after the tab bar
 *                               (+ small per-group ones next to chosen group titles)
 *            .y2k-new       blinking NEW! badges next to chosen group titles
 *            #y2k-footer    webring + "best viewed in" + guestbook + last updated
 *            #y2k-counter   fake-but-persistent odometer hit counter (in the footer)
 *  All styling here is zero-specificity (:where) fallback — parts/theme overrides it.
 * ========================================================================== */
(function () {
  "use strict";

  /* ------------------------------ CONFIG -------------------------------- */
  // Tweak freely. Group names must match services.yaml group names exactly.
  // Each list can also be overridden at runtime with a data attribute on <html>
  // (comma-separated), e.g. <html data-y2k-new-groups="Media,Ops">:
  //   data-y2k-new-groups, data-y2k-construction-groups, data-y2k-refresh-ms,
  //   data-y2k-site-banner ("off" hides the big construction banner)
  var CONFIG = {
    newGroups: ["Smart Home", "Coming Soon 2 a TV Near U", "Drive Bay"],          // get a blinking NEW! badge
    constructionGroups: ["Jobs in Progress"],             // get a small 🚧 badge
    siteBanner: true,                              // big 🚧 banner after the tab bar
    siteBannerText: "🚧 UNDER CONSTRUCTION 🚧",
    refreshMs: 60000,                              // ticker refresh
    fetchTimeoutMs: 15000,
    tickerPxPerSec: 45,                            // scroll speed
    counterKey: "y2k-hit-counter",
    counterSeed: 13370,                            // first value if none stored
    counterDigits: 6,
    links: {
      prev: { label: "« Prev", href: "https://github.com/example-owner/homelab-media-server" },
      ring: { label: "Homelab Webring", href: "http://192.0.2.242:3001/status/box" },
      next: { label: "Next »", href: "http://192.0.2.150/origami-home" },
      guestbook: { label: "✍ Sign my guestbook! (the build log)", href: "https://www.notion.so/<private-board> + "be045181b49647ed" + "8b59b866c9d91a79" },
    },
    // Fallback service names (the script resolves real ones from /api/services
    // by widget type + name pattern; these are used only if that call fails).
    services: {
      migration: { group: "Jobs in Progress", service: "NTFS → ext4 migration", index: 0, match: /migrat/i, type: "customapi" },
      selftest: { group: "Jobs in Progress", service: "New drives self-test", index: 0, match: /self.?test/i, type: "customapi" },
      tdarr: { group: "Jobs in Progress", service: "Tdarr conversions (live)", index: 0, match: /tdarr conv/i, type: "customapi" },
      prismcast: { group: "Media Mania", service: "Live TV (PrismCast)", index: 0, match: /prismcast/i, type: "customapi" },
      kuma: { group: "Net Surfin", service: "Uptime Kuma", index: 0, type: "uptimekuma" },
      tautulli: { group: "Media Mania", service: "Tautulli", index: 0, type: "tautulli" },
      sabnzbd: { group: "Download-O-Rama", service: "SABnzbd", index: 0, type: "sabnzbd" },
      wud: { group: "Update Patrol", service: "Image updates (WUD)", index: 0, type: "whatsupdocker" },
      glances: { group: "Box Brain", service: "Box vitals", index: 0, type: "glances", version: 4 },
    },
  };
  /* ---------------------------------------------------------------------- */

  if (window.__y2k90s) return;          // never run twice
  window.__y2k90s = true;

  var doc = document;
  var root = doc.documentElement;
  function list(attr, dflt) {
    var v = root.getAttribute(attr);
    return v == null ? dflt : v.split(",").map(function (s) { return s.trim(); }).filter(Boolean);
  }
  var NEW_GROUPS = list("data-y2k-new-groups", CONFIG.newGroups);
  var CONSTR_GROUPS = list("data-y2k-construction-groups", CONFIG.constructionGroups);
  var REFRESH = parseInt(root.getAttribute("data-y2k-refresh-ms"), 10) || CONFIG.refreshMs;
  var SITE_BANNER = CONFIG.siteBanner && root.getAttribute("data-y2k-site-banner") !== "off";
  var rmq = window.matchMedia ? window.matchMedia("(prefers-reduced-motion: reduce)") : { matches: false };
  function reduced() { return !!rmq.matches; }

  /* --------------------------- fallback CSS ----------------------------- */
  // :where() = zero specificity, so any theme rule wins.
  var CSS = [
    ":where(#y2k-marquee){display:block;flex:0 0 auto;min-height:1.6em;overflow:hidden;white-space:nowrap;box-sizing:border-box;margin:0 0 4px;padding:3px 0;",
    "  background:#000080;color:#ffff00;border:2px inset #c0c0c0;font:bold 14px/1.4 'Courier New',monospace;position:relative;z-index:30}",
    ":where(#y2k-marquee) .y2k-marquee-track{display:inline-block;padding-left:100%;will-change:transform;",
    "  animation:y2k-js-scroll var(--y2k-dur,60s) linear infinite}",
    ":where(#y2k-marquee):hover .y2k-marquee-track{animation-play-state:paused}",
    ":where(#y2k-marquee) .y2k-item{margin-right:2.5em}",
    ":where(#y2k-marquee) .y2k-star{color:#ff00ff}",
    ":where(#y2k-marquee) .y2k-bad{color:#ff5555}",
    ":where(#y2k-marquee.y2k-static){white-space:normal;text-align:center}",
    ":where(#y2k-marquee.y2k-static) .y2k-marquee-track{padding-left:0;animation:none;display:block}",
    "@keyframes y2k-js-scroll{from{transform:translateX(0)}to{transform:translateX(-100%)}}",
    ":where(.y2k-construction){display:block;text-align:center;margin:6px auto;padding:4px 8px;font:bold 16px 'Comic Sans MS','Comic Sans',cursive;",
    "  color:#000;background:repeating-linear-gradient(45deg,#ffcc00 0 14px,#111 14px 28px);text-shadow:0 0 3px #ffcc00}",
    ":where(.y2k-construction) .y2k-construction-text{background:#ffcc00;padding:0 8px}",
    ":where(.y2k-construction.y2k-construction-badge){display:inline-block;margin:0 0 0 8px;padding:0 6px;font-size:11px;line-height:1.6;vertical-align:middle;",
    "  background:#ffcc00;border:2px dashed #111;text-shadow:none;pointer-events:none}",
    ":where(.y2k-new){display:inline-block;margin-left:8px;padding:0 4px;font:bold 11px/1.5 'Comic Sans MS',cursive;color:#ff0;background:#f00;",
    "  border:1px outset #ff8080;vertical-align:middle;pointer-events:none;animation:y2k-js-blink 1s steps(2,start) infinite}",
    "@keyframes y2k-js-blink{to{visibility:hidden}}",
    ":where(#y2k-footer){display:block;flex:0 0 auto;text-align:center;margin:12px auto 0;padding:8px;font:13px/1.7 'Times New Roman',serif;color:inherit}",
    ":where(#y2k-footer) a{color:#3399ff;text-decoration:underline}",
    ":where(#y2k-footer) a:visited{color:#cc66ff}",
    ":where(#y2k-footer) .y2k-webring{font-weight:bold}",
    ":where(#y2k-counter){display:inline-flex;gap:1px;padding:2px;background:#000;border:2px inset #808080;vertical-align:middle}",
    ":where(#y2k-counter) .y2k-digit{display:inline-block;min-width:.75em;padding:0 2px;font:bold 16px 'Courier New',monospace;color:#0f0;",
    "  background:linear-gradient(#222,#000 50%,#222);text-align:center}",
    "@media (prefers-reduced-motion: reduce){",
    "  :where(#y2k-marquee) .y2k-marquee-track{animation:none!important;padding-left:0;white-space:normal;display:block}",
    "  :where(#y2k-marquee){white-space:normal;text-align:center}",
    "  :where(.y2k-new),:where(.y2k-construction){animation:none!important}",
    "}",
  ].join("\n");

  function addStyle() {
    if (doc.getElementById("y2k-js-style")) return;
    var s = doc.createElement("style");
    s.id = "y2k-js-style";
    s.textContent = CSS;
    // first in <head> so custom.css / theme rules come later and win ties
    (doc.head || root).insertBefore(s, (doc.head || root).firstChild);
  }

  /* ------------------------------ helpers ------------------------------- */
  function el(tag, attrs, kids) {
    var e = doc.createElement(tag);
    if (attrs) for (var k in attrs) {
      if (k === "text") e.textContent = attrs[k];
      else e.setAttribute(k, attrs[k]);
    }
    (kids || []).forEach(function (c) { if (c) e.appendChild(typeof c === "string" ? doc.createTextNode(c) : c); });
    return e;
  }
  function link(l) { return el("a", { href: l.href, target: "_blank", rel: "noopener noreferrer", text: l.label }); }
  // strip emoji / pictographs and squash whitespace (keeps · and arrows)
  function clean(s) {
    if (s == null) return "";
    return String(s)
      .replace(/[\u{1F000}-\u{1FAFF}\u{2600}-\u{27BF}\u{2B00}-\u{2BFF}\u{FE0F}\u{200D}]/gu, "")
      .replace(/\s+/g, " ").trim();
  }
  function pct(bar) { var m = /([\d.]+)\s*%/.exec(bar || ""); return m ? m[1] + "%" : ""; }
  function plural(n, w) { return n + " " + w + (n === 1 ? "" : "s"); }

  function fetchJSON(url) {
    var ctl = window.AbortController ? new AbortController() : null;
    var t = ctl ? setTimeout(function () { ctl.abort(); }, CONFIG.fetchTimeoutMs) : null;
    return fetch(url, { cache: "no-store", credentials: "same-origin", signal: ctl ? ctl.signal : undefined })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (j) { return j && !j.error ? j : null; })
      .catch(function () { return null; })
      .then(function (j) { if (t) clearTimeout(t); return j; });
  }
  function proxyURL(s, endpoint) {
    var u = "/api/services/proxy?group=" + encodeURIComponent(s.group) +
      "&service=" + encodeURIComponent(s.service) + "&index=" + (s.index || 0);
    if (endpoint) u += "&endpoint=" + encodeURIComponent(endpoint);
    return u;
  }

  /* ---------------- resolve real group/service names once --------------- */
  var resolved = null;
  function resolveServices() {
    if (resolved) return Promise.resolve(resolved);
    return fetchJSON("/api/services").then(function (groups) {
      var map = JSON.parse(JSON.stringify(CONFIG.services, function (k, v) { return v instanceof RegExp ? undefined : v; }));
      if (!Array.isArray(groups)) return (resolved = map);
      var flat = [];
      (function walk(gs) {
        (gs || []).forEach(function (g) {
          (g.services || []).forEach(function (s) { flat.push({ group: g.name, s: s }); });
          walk(g.groups);
        });
      })(groups);
      Object.keys(CONFIG.services).forEach(function (key) {
        var want = CONFIG.services[key];
        for (var i = 0; i < flat.length; i++) {
          var s = flat[i].s;
          var ws = s.widgets || (s.widget ? [s.widget] : []);
          for (var wi = 0; wi < ws.length; wi++) {
            if (ws[wi].type !== want.type) continue;
            if (want.match && !want.match.test(s.name)) continue;
            map[key] = { group: flat[i].group, service: s.name, index: wi, version: ws[wi].version || want.version };
            return;
          }
        }
      });
      return (resolved = map);
    });
  }

  /* ------------------------- ticker data sources ------------------------ */
  // Each returns a Promise of an array of {label, text, bad?} or null (skip).
  var SOURCES = [
    function migration(S) {
      return fetchJSON(proxyURL(S.migration)).then(function (j) {
        if (!j) return null;
        var round = clean(j.round).split("·")[0].trim();           // "3 of 5"
        var stage = clean(j.stage);                                  // "Checksum check · 32/52 shows done"
        var verify = pct(j.verify_bar), copy = pct(j.copy_bar), overall = pct(j.overall_bar);
        var phase = /checksum|verif/i.test(stage) ? "checksum " + verify : (copy ? "copy " + copy : "");
        var eta = clean(j.eta).replace(/^[^:]*:\s*/, "");
        var parts = ["Round " + round];
        if (phase) parts.push(phase);
        if (overall) parts.push("overall " + overall);
        if (eta) parts.push("ETA " + eta);
        var out = [{ label: "MIGRATION", text: parts.join(" · ") }];
        if (stage) out.push({ label: "NOW", text: stage });
        if (j.health) {
          var errs = /errors[^:]*:\s*(\d+)/i.exec(j.health);
          if (errs) out.push({ label: "DISK ERRORS", text: errs[1], bad: errs[1] !== "0" });
        }
        return out;
      });
    },
    function selftest(S) {
      return fetchJSON(proxyURL(S.selftest)).then(function (j) {
        if (!j || !j.now) return null;
        return [{ label: "NEW DRIVES", text: clean(j.now), bad: /fail|error/i.test(j.now) }];
      });
    },
    function tdarr(S) {
      return fetchJSON(proxyURL(S.tdarr)).then(function (j) {
        if (!j) return null;
        var now = clean(j.now);
        var out = [{ label: "TDARR", text: [now, clean(j.totals)].filter(Boolean).join(" · ") }];
        if (j.saved) out.push({ label: "SAVED", text: clean(j.saved) });
        if (j.swap) out.push({ label: "LIBRARY", text: clean(j.swap) });
        return out;
      });
    },
    function kuma(S) {
      return Promise.all([
        fetchJSON(proxyURL(S.kuma, "status_page")),
        fetchJSON(proxyURL(S.kuma, "heartbeat")),
      ]).then(function (r) {
        var sp = r[0], hb = r[1];
        if (!hb || !hb.heartbeatList) return null;
        var mons = [];
        if (sp && sp.publicGroupList) sp.publicGroupList.forEach(function (g) {
          (g.monitorList || []).forEach(function (m) { mons.push({ id: String(m.id), name: m.name }); });
        });
        if (!mons.length) mons = Object.keys(hb.heartbeatList).map(function (id) { return { id: id, name: "#" + id }; });
        var up = 0, down = [], other = 0;
        mons.forEach(function (m) {
          var beats = hb.heartbeatList[m.id] || [];
          var last = beats[beats.length - 1];
          if (!last) { other++; return; }
          if (last.status === 1) up++;
          else if (last.status === 0) down.push(m.name);
          else other++; // 2 pending, 3 maintenance
        });
        var text = up + "/" + mons.length + " UP";
        if (down.length) text += " · DOWN: " + down.join(", ");
        if (other) text += " · " + other + " pending/maint";
        var out = [{ label: "KUMA", text: text, bad: down.length > 0 }];
        if (hb.uptimeList) {
          var vals = mons.map(function (m) { return hb.uptimeList[m.id + "_24"]; }).filter(function (v) { return typeof v === "number"; });
          if (vals.length) {
            var avg = vals.reduce(function (a, b) { return a + b; }, 0) / vals.length;
            out.push({ label: "24H UPTIME", text: (avg * 100).toFixed(2) + "%" });
          }
        }
        return out;
      });
    },
    function plex(S) {
      return fetchJSON(proxyURL(S.tautulli, "get_activity")).then(function (j) {
        var d = j && j.response && j.response.data;
        if (!d) return null;
        var n = parseInt(d.stream_count, 10) || 0;
        var tc = d.stream_count_transcode || 0;
        return [{ label: "PLEX", text: n ? plural(n, "stream") + " now playing" + (tc ? " (" + tc + " transcoding)" : "") : "nobody watching" }];
      });
    },
    function prismcast(S) {
      return fetchJSON(proxyURL(S.prismcast)).then(function (j) {
        if (!j || !j.status) return null;
        var st = j.streams || {};
        return [{ label: "LIVE TV", text: j.status + (st.limit != null ? " · " + (st.active || 0) + "/" + st.limit + " tuners" : ""), bad: j.status !== "healthy" }];
      });
    },
    function sab(S) {
      return fetchJSON(proxyURL(S.sabnzbd, "queue")).then(function (j) {
        var q = j && j.queue;
        if (!q) return null;
        var n = q.noofslots_total != null ? q.noofslots_total : q.noofslots;
        var txt = q.paused ? "paused" : (n ? plural(n, "download") + " · " + (q.speed || "0") + "B/s · " + q.timeleft + " left" : "idle");
        return [{ label: "SABNZBD", text: txt }];
      });
    },
    function wud(S) {
      return fetchJSON(proxyURL(S.wud, "containers")).then(function (j) {
        if (!Array.isArray(j)) return null;
        var n = j.filter(function (c) { return c.updateAvailable; }).length;
        return [{ label: "UPDATES", text: n ? plural(n, "container update") + " available" : "all " + j.length + " containers current" }];
      });
    },
    function glances(S) {
      var v = S.glances.version || 4;
      return fetchJSON(proxyURL(S.glances, v + "/quicklook")).then(function (j) {
        if (!j || typeof j.cpu !== "number") return null;
        return [{ label: "CPU", text: j.cpu.toFixed(0) + "% · RAM " + (j.mem != null ? j.mem.toFixed(0) + "%" : "?") }];
      });
    },
  ];

  /* ------------------------------ marquee ------------------------------- */
  var lastItems = null, lastUpdated = null;
  var WELCOME = [{ label: "WELCOME", text: "to user's Homepage — you are now surfing the information superhighway" }];

  function renderTicker(items) {
    var m = doc.getElementById("y2k-marquee");
    if (!m) return;
    items = items && items.length ? items : WELCOME;
    var track = m.querySelector(".y2k-marquee-track");
    if (!track) { track = el("span", { class: "y2k-marquee-track" }); m.appendChild(track); }
    var plain = items.map(function (i) { return i.label + ": " + i.text; }).join(". ");
    var static_ = reduced();
    // unchanged text + mode: leave the running animation alone (no jump)
    if (track.getAttribute("data-y2k-text") === plain && m.classList.contains("y2k-static") === static_ && track.childNodes.length) return;
    track.setAttribute("data-y2k-text", plain);
    var frag = doc.createDocumentFragment();
    items.forEach(function (it) {
      frag.appendChild(el("span", { class: "y2k-item" + (it.bad ? " y2k-bad" : "") }, [
        el("span", { class: "y2k-star", "aria-hidden": "true", text: "★ " }),
        el("b", { class: "y2k-label", text: it.label + ": " }),
        el("span", { class: "y2k-text", text: it.text }),
      ]));
    });
    frag.appendChild(el("span", { class: "y2k-star", "aria-hidden": "true", text: "★" }));
    track.textContent = "";
    track.appendChild(frag);
    m.setAttribute("aria-label", "Live status: " + plain);
    m.title = lastUpdated ? "Updated " + lastUpdated.toLocaleTimeString() : "";
    // speed: distance = track width (+100% padding) / px per sec
    m.classList.toggle("y2k-static", static_);
    if (!static_) {
      var w = track.scrollWidth || plain.length * 9;
      var dur = Math.max(30, Math.round(w / CONFIG.tickerPxPerSec));
      track.style.setProperty("--y2k-dur", dur + "s");
      // start with the text already at the left edge, not an empty bar while it scrolls in
      track.style.animationDelay = (-dur * Math.min(0.9, (m.clientWidth || 800) * 0.97 / w)).toFixed(1) + "s";
      m.setAttribute("data-y2k-dur", dur);
    }
  }

  var refreshing = false;
  function refresh() {
    if (refreshing) return;
    refreshing = true;
    resolveServices()
      .then(function (S) {
        return Promise.all(SOURCES.map(function (fn) {
          try { return fn(S).catch(function () { return null; }); } catch (e) { return Promise.resolve(null); }
        }));
      })
      .then(function (res) {
        var items = [];
        res.forEach(function (r) { if (r) items = items.concat(r.filter(function (x) { return x && x.text; })); });
        if (items.length) { lastItems = items; lastUpdated = new Date(); }
        renderTicker(lastItems);
        updateFooterDate();
      })
      .catch(function () {})
      .then(function () { refreshing = false; });
  }

  /* ------------------------------ counter ------------------------------- */
  var hits = (function () {
    var n = CONFIG.counterSeed;
    try {
      var stored = parseInt(localStorage.getItem(CONFIG.counterKey), 10);
      n = (isNaN(stored) ? CONFIG.counterSeed : stored) + 1;   // once per page load
      localStorage.setItem(CONFIG.counterKey, String(n));
    } catch (e) {}
    return n;
  })();
  function buildCounter() {
    var s = String(hits);
    while (s.length < CONFIG.counterDigits) s = "0" + s;
    var c = el("span", { id: "y2k-counter", role: "img", "aria-label": "You are visitor number " + hits });
    s.split("").forEach(function (d) { c.appendChild(el("span", { class: "y2k-digit", "aria-hidden": "true", text: d })); });
    return c;
  }

  /* ------------------------------- footer ------------------------------- */
  function fmtDate(d) {
    try {
      return d.toLocaleString(undefined, { weekday: "short", month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit" });
    } catch (e) { return d.toString(); }
  }
  function updateFooterDate() {
    var s = doc.querySelector("#y2k-footer .y2k-updated-date");
    if (s) s.textContent = fmtDate(lastUpdated || new Date());
  }
  function buildFooter() {
    var L = CONFIG.links;
    return el("div", { id: "y2k-footer", role: "contentinfo" }, [
      el("div", { class: "y2k-webring" }, [link(L.prev), " | ", link(L.ring), " | ", link(L.next)]),
      el("div", { class: "y2k-visitors" }, ["You are visitor ", buildCounter(), " since 1996!"]),
      el("div", { class: "y2k-best-viewed", text: "Best viewed in Netscape Navigator 4.0 at 800x600" }),
      el("div", { class: "y2k-guestbook" }, [link(L.guestbook)]),
      el("div", { class: "y2k-updated" }, ["Last updated: ", el("span", { class: "y2k-updated-date", text: fmtDate(lastUpdated || new Date()) })]),
    ]);
  }

  /* --------------------------- DOM injection ---------------------------- */
  function pageContainer() {
    // #inner_wrapper > div.container (flex column holding widgets, tabs, groups, #footer)
    var iw = doc.getElementById("inner_wrapper");
    if (iw) for (var i = 0; i < iw.children.length; i++) if (iw.children[i].tagName === "DIV") return iw.children[i];
    return null;
  }
  function topLevelChild(container, node) {
    while (node && node.parentNode !== container) node = node.parentNode;
    return node;
  }

  function ensureMarquee(container) {
    var m = doc.getElementById("y2k-marquee");
    if (m && m.parentNode === container && container.firstChild === m) return;
    if (!m) {
      m = el("div", { id: "y2k-marquee", role: "marquee", "aria-live": "off" });
      m.appendChild(el("span", { class: "y2k-marquee-track" }));
    }
    container.insertBefore(m, container.firstChild);
    renderTicker(lastItems);
  }

  function ensureSiteBanner(container) {
    if (!SITE_BANNER) return;
    var tabs = doc.getElementById("myTab");
    var top = tabs ? topLevelChild(container, tabs) : null;
    var before = top ? top.nextSibling : null;
    if (!top) {
      // no tabs configured: put it right before the group layout
      var g = doc.getElementById("layout-groups") || doc.querySelector(".services-group");
      before = g ? topLevelChild(container, g) : null;
      if (!before) return;
    }
    var b = doc.getElementById("y2k-construction-banner");
    if (b && b.parentNode === container && b.nextSibling === before) return;
    if (b && b === before) return;
    if (!b) b = el("div", { id: "y2k-construction-banner", class: "y2k-construction", role: "note" },
      [el("span", { class: "y2k-construction-text", text: CONFIG.siteBannerText })]);
    container.insertBefore(b, before);
  }

  function ensureBadges() {
    var h2s = doc.querySelectorAll("h2.service-group-name");
    for (var i = 0; i < h2s.length; i++) {
      var h = h2s[i];
      var name = (h.firstChild && h.firstChild.nodeType === 3 ? h.firstChild.nodeValue : h.textContent).trim();
      var wantNew = NEW_GROUPS.indexOf(name) !== -1, wantC = CONSTR_GROUPS.indexOf(name) !== -1;
      // badges live as siblings right after the <h2> inside the group's header button
      var sib = h.nextElementSibling, haveNew = null, haveC = null;
      while (sib && sib.classList && (sib.classList.contains("y2k-new") || sib.classList.contains("y2k-construction"))) {
        if (sib.classList.contains("y2k-new")) haveNew = sib; else haveC = sib;
        sib = sib.nextElementSibling;
      }
      var after = h;
      if (wantC) {
        if (!haveC) { haveC = el("span", { class: "y2k-construction y2k-construction-badge", "data-y2k-group": name, title: "Under construction", text: "🚧 UNDER CONSTRUCTION" }); h.parentNode.insertBefore(haveC, after.nextSibling); }
        after = haveC;
      } else if (haveC) haveC.remove();
      if (wantNew) {
        if (!haveNew) { haveNew = el("span", { class: "y2k-new", "data-y2k-group": name, text: "NEW!" }); h.parentNode.insertBefore(haveNew, after.nextSibling); }
      } else if (haveNew) haveNew.remove();
    }
  }

  function ensureFooter() {
    var f = doc.getElementById("footer");
    var y = doc.getElementById("y2k-footer");
    if (f) {
      if (y && y.parentNode === f && f.lastElementChild === y) return;
      f.appendChild(y || buildFooter());
    } else {
      var c = pageContainer();
      if (!c) return;
      if (y && y.parentNode === c && c.lastElementChild === y) return;
      c.appendChild(y || buildFooter());
    }
  }

  var observer = null;
  function ensureAll() {
    var c = pageContainer();
    if (!c) return;
    if (observer) observer.disconnect();   // don't observe our own edits
    try {
      addStyle();
      ensureMarquee(c);
      ensureSiteBanner(c);
      ensureBadges();
      ensureFooter();
    } catch (e) { /* fail silently */ }
    observe();
  }

  var scheduled = false;
  function schedule() {
    if (scheduled) return;
    scheduled = true;
    (window.requestAnimationFrame || setTimeout)(function () { scheduled = false; ensureAll(); });
  }
  function observe() {
    var target = doc.getElementById("__next") || doc.body;
    if (!target || !window.MutationObserver) return;
    if (!observer) observer = new MutationObserver(schedule);
    observer.observe(target, { childList: true, subtree: true });
  }

  /* -------------------------------- boot -------------------------------- */
  function boot() {
    ensureAll();
    refresh();
    setInterval(function () { if (!doc.hidden) refresh(); }, REFRESH);
    doc.addEventListener("visibilitychange", function () {
      if (!doc.hidden && (!lastUpdated || Date.now() - lastUpdated > REFRESH)) refresh();
    });
    window.addEventListener("hashchange", function () { schedule(); setTimeout(schedule, 300); });
    var onRM = function () { renderTicker(lastItems); };
    if (rmq.addEventListener) rmq.addEventListener("change", onRM); else if (rmq.addListener) rmq.addListener(onRM);
    // safety net: Homepage re-renders a lot on load (settings/services SWR); poll briefly
    var n = 0, t = setInterval(function () { ensureAll(); if (++n > 10) clearInterval(t); }, 1000);
  }
  if (doc.readyState === "loading") doc.addEventListener("DOMContentLoaded", boot); else boot();
})();
