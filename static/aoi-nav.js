// AOI navigator — data-driven from GET /api/aois (the API owns availability +
// facts; no AOIs are hardcoded here). A grouped, persistent sidebar list: zoom to
// each AOI's bbox (fitBounds), the tango curtain only on cross-hazard moves, and
// "not cached" rendered as an intentional, clickable observation state — never
// faked. Classic script: it reaches mapNisar / openStoryChapter / playFeetTransition
// by their shared global bindings. (Council-reviewed: codex + grok.)
(function () {
  "use strict";
  const HAZARD_LABELS = { flood: "Flood", landslide: "Landslide", earthquake: "Earthquake" };
  let aoisById = new Map();
  let orderedAoiIds = [];
  let currentAoiId = null;
  let currentHazard = null;

  const $ = (id) => document.getElementById(id);

  async function initAoiNavigator() {
    const list = $("aoi-list");
    try {
      const res = await fetch("/api/aois");
      if (!res.ok) throw new Error("aois " + res.status);
      renderAoiNavigator(await res.json());
    } catch (err) {
      if (list) list.innerHTML = '<p class="aoi-empty">AOI registry unavailable.</p>';
    }
  }

  function renderAoiNavigator(data) {
    const list = $("aoi-list");
    if (!list) return;
    aoisById = new Map();
    orderedAoiIds = [];
    const frag = document.createDocumentFragment();
    for (const hazard of ["flood", "landslide", "earthquake"]) {
      const items = data[hazard] || [];
      if (!items.length) continue;
      const group = document.createElement("div");
      group.className = "aoi-group";
      const head = document.createElement("div");
      head.className = "aoi-group-label";
      head.textContent = HAZARD_LABELS[hazard] || hazard;
      group.appendChild(head);
      for (const a of items) {
        aoisById.set(a.id, a);
        orderedAoiIds.push(a.id);
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "aoi-btn" + (a.state === "not cached" ? " aoi-muted" : "");
        btn.dataset.aoi = a.id;
        btn.setAttribute("aria-current", "false");
        const cached = a.state === "cached";
        const top = document.createElement("span");
        top.className = "aoi-btn-top";
        const label = document.createElement("span");
        label.className = "aoi-label";
        label.textContent = a.label;
        const badge = document.createElement("span");
        badge.className = "aoi-badge " + (cached ? "aoi-badge-cached" : "aoi-badge-nc");
        badge.textContent = cached ? "cached" : "not cached";
        top.append(label, badge);
        const fact = document.createElement("span");
        fact.className = "aoi-fact";
        fact.textContent = a.fact;
        btn.append(top, fact);
        group.appendChild(btn);
      }
      frag.appendChild(group);
    }
    list.replaceChildren(frag);
    list.addEventListener("click", (e) => {
      const btn = e.target.closest(".aoi-btn");
      if (btn) selectAoi(btn.dataset.aoi, { focus: true });
    });
  }

  function fitAoi(bbox, instant) {
    if (!Array.isArray(bbox) || bbox.length !== 4) return;
    if (typeof mapNisar === "undefined" || !mapNisar || typeof mapNisar.fitBounds !== "function") return;
    const [w, s, e, n] = bbox;
    mapNisar.fitBounds([[w, s], [e, n]], {
      padding: { top: 90, right: 40, bottom: 200, left: 330 },
      duration: instant ? 0 : 900,
      maxZoom: 13,
    });
  }

  function renderAoiDetail(a) {
    const d = $("aoi-detail");
    if (!d) return;
    d.hidden = false;
    d.className = "aoi-detail " + (a.state === "cached" ? "aoi-detail-cached" : "aoi-detail-nc");
    d.replaceChildren();
    const mk = (cls, text) => {
      const p = document.createElement("p");
      p.className = cls;
      p.textContent = text;
      return p;
    };
    d.append(
      mk("aoi-detail-state", (a.state === "cached" ? "Cached" : "Not cached") + " · " + a.label),
      mk("aoi-detail-fact", "Measured: " + a.fact),
      mk("aoi-detail-src", "Source: " + a.source),
    );
    if (typeof a.coverage_pct === "number") {
      d.append(mk("aoi-detail-cov", "NISAR L-band covers " + a.coverage_pct + "% of the AOI (framed to the data footprint)."));
    }
    if (a.state === "not cached") {
      d.append(mk("aoi-detail-note",
        "Map framing is available; processed NISAR/Sentinel layers are not staged for this AOI yet."));
    }
  }

  function selectAoi(id, opts) {
    opts = opts || {};
    const a = aoisById.get(id);
    if (!a) return;
    const crossHazard = a.hazard !== currentHazard;
    currentAoiId = id;
    // Frame the DATA footprint (where NISAR actually covers), not the oversized
    // AOI box — falls back to the config bbox when no footprint is known.
    const target = Array.isArray(a.footprint_bbox) ? a.footprint_bbox : a.bbox;
    if (crossHazard && typeof openStoryChapter === "function") {
      // let fitChapter frame the AOI (not the whole hazard) under the curtain,
      // avoiding a double camera move; then one smooth fitBounds settles it.
      window.__aoiFocusBbox = target;
      if (typeof playFeetTransition === "function") playFeetTransition(a.hazard);
      try { openStoryChapter(a.hazard); } catch (_) {}
      const sel = $("story-chapter");
      if (sel) sel.value = a.hazard;
      setTimeout(() => fitAoi(target), 120);
    } else {
      fitAoi(target);
    }
    currentHazard = a.hazard;
    renderAoiDetail(a);
    document.querySelectorAll(".aoi-btn").forEach((b) => {
      const on = b.dataset.aoi === id;
      b.classList.toggle("aoi-active", on);
      b.setAttribute("aria-current", on ? "true" : "false");
      if (on && opts.focus) b.focus();
    });
  }

  function step(delta) {
    if (!orderedAoiIds.length) return;
    const i = currentAoiId ? orderedAoiIds.indexOf(currentAoiId) : -1;
    const len = orderedAoiIds.length;
    const next = (((i + delta) % len) + len) % len;
    selectAoi(orderedAoiIds[next], { focus: true });
  }

  function wireControls() {
    const prev = $("aoi-prev");
    const next = $("aoi-next");
    if (prev) prev.addEventListener("click", () => step(-1));
    if (next) next.addEventListener("click", () => step(1));
    const nav = $("aoi-navigator");
    if (nav) nav.addEventListener("keydown", (e) => {
      if (e.key === "ArrowDown") { e.preventDefault(); step(1); }
      else if (e.key === "ArrowUp") { e.preventDefault(); step(-1); }
      else if (e.key === "Home") { e.preventDefault(); selectAoi(orderedAoiIds[0], { focus: true }); }
      else if (e.key === "End") { e.preventDefault(); selectAoi(orderedAoiIds[orderedAoiIds.length - 1], { focus: true }); }
    });
  }

  function boot() { initAoiNavigator(); wireControls(); }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
