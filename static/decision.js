// Response posture card. The API owns every light, label, and number.
// This file only renders that JSON. It never computes hectares or aid.
(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);
  let board = null;
  let pinned = null;

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text != null) node.textContent = text;
    return node;
  }

  function stateLabel(state) {
    if (state === "not cached") return "Not cached";
    if (state === "gate result") return "Gate result";
    if (state === "live") return "Live";
    if (state === "error") return "Error";
    if (state === "cached") return "Cached";
    return state || "Not cached";
  }

  function showFailure(message) {
    const card = $("decision-card");
    const body = $("decision-body");
    const state = $("decision-state");
    if (!card || !body) return;
    card.hidden = false;
    if (state) {
      state.textContent = "Error";
      state.className = "dec-state dec-state-error";
    }
    body.replaceChildren(el("p", "dec-note", message));
  }

  function lightRow(order, active, labels) {
    const row = el("div", "dec-lights");
    row.setAttribute("role", "list");
    (order || []).forEach((id) => {
      const on = id === active;
      const item = el("div", "dec-light dec-" + id + (on ? " is-on" : ""));
      item.setAttribute("role", "listitem");
      item.setAttribute("aria-current", on ? "true" : "false");
      const text = labels && labels[id] ? labels[id] : id;
      item.append(el("span", "dec-lamp", ""), el("span", "dec-light-label", text));
      row.append(item);
    });
    return row;
  }

  function extentText(extent) {
    if (!extent || extent.availability === "unavailable") {
      return extent && extent.reason ? extent.reason : "Unavailable";
    }
    if (extent.represents === "analyzed_window") {
      const bits = [extent.label || "Analyzed window"];
      if (Array.isArray(extent.parts)) {
        extent.parts.forEach((part) => {
          const track = part.track != null ? "track " + part.track + ": " : "";
          bits.push(track + part.valid_pixels + " valid pixels");
        });
      } else if (typeof extent.valid_pixels === "number") {
        bits.push(String(extent.valid_pixels) + " valid pixels");
      }
      if (extent.reason) bits.push(extent.reason);
      return bits.join(" · ");
    }
    const bits = [extent.label || "Extent"];
    if (typeof extent.value_ha === "number") bits.push(String(extent.value_ha) + " ha");
    if (typeof extent.pixel_count === "number") bits.push(String(extent.pixel_count) + " pixels");
    if (typeof extent.valid_pixel_count === "number") {
      bits.push(String(extent.valid_pixel_count) + " valid");
    }
    return bits.join(" · ");
  }

  function damageText(level) {
    if (!level || level.availability !== "measured") {
      return level && level.reason ? level.reason : "Not classified";
    }
    return String(level.value);
  }

  function responseBlock(items, open) {
    const details = el("details", "dec-fold");
    details.open = !!open;
    details.append(el("summary", null, "Help to check — quantities unavailable"));
    const list = el("ul", "dec-lines");
    (items || []).forEach((item) => {
      const row = el("li", "dec-line");
      row.append(el("span", "dec-line-esf", item.help));
      row.append(el("span", "dec-note", item.look));
      list.append(row);
    });
    details.append(list);
    return details;
  }

  function impactText(impact) {
    if (!impact || impact.availability !== "measured") {
      return impact && impact.reason ? impact.reason : "Unavailable";
    }
    const unit = impact.unit ? " " + impact.unit : "";
    return String(impact.value) + unit + " (" + impact.field + ")";
  }

  function addFact(parent, term, detail) {
    const row = el("div", "dec-fact");
    row.append(el("dt", "dec-term", term), el("dd", "dec-detail", detail));
    parent.append(row);
  }

  function revealCard() {
    const panel = document.querySelector('[aria-label="Story map"]');
    if (panel) panel.scrollTop = 0;
  }

  function renderProduct(product) {
    const body = $("decision-body");
    const state = $("decision-state");
    if (!body) return;
    if (state) {
      state.textContent = stateLabel(product.state);
      state.className = "dec-state dec-state-" + String(product.state || "").replace(/\s+/g, "-");
    }
    body.replaceChildren();
    const head = el("div", "dec-aoi");
    head.append(el("p", "dec-aoi-name", product.label));
    const back = el("button", "dec-back", "All areas");
    back.type = "button";
    back.addEventListener("click", () => {
      pinned = null;
      if (board) renderBoard(board);
    });
    head.append(back);
    body.append(head);
    if (product.product_label) body.append(el("p", "dec-kicker", product.product_label));
    if (product.lights_applicable) body.append(lightRow(product.rank, product.posture, product.lights));
    body.append(el("p", "dec-action dec-action-" + product.action, product.action_label));
    body.append(el("p", "dec-note", product.action_detail));
    if (product.lights_applicable && product.clearance_text) {
      body.append(el("p", "dec-clearance", product.clearance_text));
    }

    const facts = el("dl", "dec-facts");
    addFact(facts, "Extent", extentText(product.magnitude && product.magnitude.extent));
    addFact(facts, "Damage level", damageText(product.damage_level));
    addFact(facts, "People and buildings", impactText(product.magnitude && product.magnitude.social_impact));
    addFact(facts, "Economic loss", impactText(product.magnitude && product.magnitude.economic_impact));
    body.append(facts);
    body.append(responseBlock(product.response_package, !product.lights_applicable));

    const hazards = el("ul", "dec-hazards");
    (product.hazards || []).forEach((hazard) => {
      const item = el("li", "dec-hazard");
      const name = hazard.domain + (hazard.in_scope ? "" : " · out of scope");
      item.append(el("span", "dec-hazard-name", name));
      item.append(el("span", "dec-pip dec-" + hazard.light, hazard.light.replace(/_/g, " ")));
      if (hazard.note && hazard.in_scope) item.append(el("p", "dec-note", hazard.note));
      if (hazard.reason) item.append(el("p", "dec-note", hazard.reason));
      hazards.append(item);
    });
    body.append(hazards);

    body.append(lifelineBlock(product.lifelines));
    body.append(lineBlock(product.lines_of_effort));
    const prov = product.provenance || {};
    const src = [];
    if (prov.tools && prov.tools.length) src.push(prov.tools.join(", "));
    if (prov.granule_ids && prov.granule_ids.length) src.push(prov.granule_ids.join(", "));
    if (prov.commands && prov.commands.length) src.push(prov.commands.join(" · "));
    if (src.length) body.append(el("p", "dec-src", src.join(" · ")));
    if (product.numbers_policy) body.append(el("p", "dec-src", product.numbers_policy));
    const notA = el("ul", "dec-nota");
    (product.not_a || []).forEach((item) => notA.append(el("li", null, item)));
    if (product.not_a && product.not_a.length) body.append(notA);
    revealCard();
  }

  function lifelineBlock(lifelines) {
    const details = el("details", "dec-fold");
    details.append(el("summary", null, "Community lifelines — not color-classified"));
    const list = el("ul", "dec-lifelines");
    (lifelines || []).forEach((item) => {
      const row = el("li", "dec-lifeline" + (item.check_first ? " is-check" : ""));
      const mark = item.check_first ? "Check first · " : "";
      row.append(el("span", "dec-lifeline-name", item.label));
      row.append(el("span", "dec-note", mark + "not assessed"));
      list.append(row);
    });
    details.append(list);
    if (lifelines && lifelines[0]) details.append(el("p", "dec-note", lifelines[0].reason));
    return details;
  }

  function lineBlock(lines) {
    const details = el("details", "dec-fold");
    details.append(el("summary", null, "Lines of effort — quantities unavailable"));
    const list = el("ul", "dec-lines");
    (lines || []).forEach((item) => {
      const row = el("li", "dec-line");
      row.append(el("span", "dec-line-esf", item.esf));
      row.append(el("span", "dec-lifeline-name", item.label));
      row.append(el("span", "dec-note", item.status.replace(/_/g, " ")));
      list.append(row);
    });
    details.append(list);
    return details;
  }

  function renderBoard(data) {
    const body = $("decision-body");
    const state = $("decision-state");
    if (!body) return;
    if (state) {
      state.textContent = stateLabel(data.state);
      state.className = "dec-state dec-state-" + String(data.state || "").replace(/\s+/g, "-");
    }
    body.replaceChildren();
    if (data.product_label) body.append(el("p", "dec-kicker", data.product_label));
    body.append(el("p", "dec-action dec-action-" + data.action, data.action_label));
    if (data.lights_applicable) body.append(lightRow(data.rank, data.posture, data.lights));
    else if (data.board_note) body.append(el("p", "dec-note", data.board_note));
    body.append(el("p", "dec-note", data.action_detail));
    if (data.doctrine && data.doctrine.note) body.append(el("p", "dec-src", data.doctrine.note));
    paintPips();
    revealCard();
  }

  function paintPips() {
    if (!board || !board.aois) return;
    board.aois.forEach((item) => {
      const btn = document.querySelector('.aoi-btn[data-aoi="' + item.aoi + '"]');
      if (!btn) return;
      let pip = btn.querySelector(".dec-pip");
      if (!pip) {
        pip = el("span", "dec-pip");
        const top = btn.querySelector(".aoi-btn-top");
        if (top) top.append(pip);
      }
      pip.className = item.lights_applicable ? "dec-pip dec-" + item.posture : "dec-pip dec-product";
      pip.textContent = item.chip || item.posture_label;
    });
  }

  async function loadBoard() {
    const res = await fetch("/api/decision");
    if (!res.ok) throw new Error("decision " + res.status);
    board = await res.json();
    return board;
  }

  async function showAoi(id) {
    pinned = id;
    try {
      const res = await fetch("/api/decision/" + encodeURIComponent(id));
      if (!res.ok) throw new Error("decision " + res.status);
      const product = await res.json();
      const card = $("decision-card");
      if (card) card.hidden = false;
      renderProduct(product);
    } catch (err) {
      showFailure("Response posture unavailable.");
    }
  }

  async function showBoard() {
    pinned = null;
    try {
      if (!board) await loadBoard();
      const card = $("decision-card");
      if (card) card.hidden = false;
      renderBoard(board);
    } catch (err) {
      showFailure("Response posture unavailable.");
    }
  }

  function primaryFor(chapter) {
    if (!board) return null;
    return (board.aois || []).find(
      (item) => item.primary && (item.hazards_in_scope || []).indexOf(chapter) !== -1
    );
  }

  window.addEventListener("bailasar-aoi", (event) => {
    if (event.detail && event.detail.id) showAoi(event.detail.id);
  });
  window.addEventListener("bailasar-chapter", (event) => {
    const chapter = event.detail ? event.detail.chapter : "";
    if (!board) return;
    applyChapter(chapter);
  });
  window.addEventListener("bailasar-aois-ready", () => paintPips());

  function applyChapter(chapter) {
    const pin = window.__bailasarAoi;
    if (!chapter) {
      showBoard();
      return;
    }
    if (pin && pin.hazard === chapter) {
      showAoi(pin.id);
      return;
    }
    const primary = primaryFor(chapter);
    if (primary) showAoi(primary.aoi);
  }

  async function boot() {
    try {
      await loadBoard();
    } catch (err) {
      showFailure("Response posture unavailable.");
      return;
    }
    const select = document.getElementById("story-chapter");
    const chapter = select && select.value ? select.value : "";
    if (chapter) applyChapter(chapter);
    else showBoard();
    paintPips();
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
