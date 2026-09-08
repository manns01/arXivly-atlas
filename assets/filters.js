/* arXivly-atlas — in-browser view filters.

   Re-slices the already-built page: shows/hides paper cards and cluster
   sections and dims the atlas graph to match. Nothing here re-fetches or
   re-clusters; the corpus and the clusters are fixed at build time. State is
   mirrored to the URL hash and localStorage so a view is bookmarkable.

   Predicate for a paper being shown:
     category in the checked set
     AND first-seen day within the chosen window
     AND (priority-authors-only off, or the paper has a priority author)
     AND (no exclude term appears in title+abstract)
     AND ( every topic still checked            -> no topic constraint
           OR the paper matched a checked topic
           OR the paper has a priority author
           OR an "also include" term appears in title+abstract )
*/
(function () {
  "use strict";

  var panel = document.querySelector(".filters");
  var dataEl = document.getElementById("atlas-data");
  if (!panel || !dataEl) return;

  var data;
  try { data = JSON.parse(dataEl.textContent); } catch (e) { return; }

  var nodes = data.nodes || [];
  if (!nodes.length) return;

  var byId = {};
  nodes.forEach(function (n) {
    byId[n.id] = n;
    n._text = ((n.title || "") + " " + (n.abstract || "")).toLowerCase();
  });

  var allKeywords = data.keywords || [];
  var days = (data.days || []).slice();            // newest first

  var STORE_KEY = "arxivly-atlas:filters";

  // --- controls -----------------------------------------------------------
  var catBoxes = toArray(panel.querySelectorAll('input[name="cat"]'));
  var kwBoxes = toArray(panel.querySelectorAll('input[name="kw"]'));
  var incInput = panel.querySelector('input[name="include"]');
  var excInput = panel.querySelector('input[name="exclude"]');
  var prioBox = panel.querySelector('input[name="priority-only"]');
  var winSelect = panel.querySelector('select[name="window"]');
  var resetBtn = panel.querySelector(".filter-reset");
  var countEl = panel.querySelector(".filter-count");

  var cards = toArray(document.querySelectorAll(".clusters .paper"));
  var clusters = toArray(document.querySelectorAll(".clusters .cluster"));
  clusters.forEach(function (c) {
    var el = c.querySelector(".cluster-count");
    if (el) el.dataset.original = el.textContent;
  });

  panel.hidden = false;

  // --- state <-> controls ----------------------------------------------
  function readControls() {
    return {
      catOff: catBoxes.filter(function (b) { return !b.checked; })
        .map(function (b) { return b.value; }),
      kwOff: kwBoxes.filter(function (b) { return !b.checked; })
        .map(function (b) { return b.value; }),
      inc: incInput ? incInput.value.trim() : "",
      exc: excInput ? excInput.value.trim() : "",
      prio: !!(prioBox && prioBox.checked),
      win: winSelect ? winSelect.value : "0"
    };
  }

  function writeControls(s) {
    var catOff = new Set(s.catOff || []);
    var kwOff = new Set(s.kwOff || []);
    catBoxes.forEach(function (b) { b.checked = !catOff.has(b.value); });
    kwBoxes.forEach(function (b) { b.checked = !kwOff.has(b.value); });
    if (incInput) incInput.value = s.inc || "";
    if (excInput) excInput.value = s.exc || "";
    if (prioBox) prioBox.checked = !!s.prio;
    if (winSelect) winSelect.value = s.win || "0";
  }

  function stateToQuery(s) {
    var p = new URLSearchParams();
    if (s.catOff.length) p.set("catoff", s.catOff.join(","));
    if (s.kwOff.length) p.set("kwoff", s.kwOff.join("~"));
    if (s.inc) p.set("inc", s.inc);
    if (s.exc) p.set("exc", s.exc);
    if (s.prio) p.set("prio", "1");
    if (s.win && s.win !== "0") p.set("win", s.win);
    return p.toString();
  }

  function queryToState(q) {
    var p = new URLSearchParams(q);
    return {
      catOff: p.has("catoff") ? p.get("catoff").split(",") : [],
      kwOff: p.has("kwoff") ? p.get("kwoff").split("~") : [],
      inc: p.get("inc") || "",
      exc: p.get("exc") || "",
      prio: p.get("prio") === "1",
      win: p.get("win") || "0"
    };
  }

  function loadState() {
    var hashKeys = ["catoff", "kwoff", "inc", "exc", "prio", "win"];
    var hp = new URLSearchParams(location.hash.replace(/^#/, ""));
    if (hashKeys.some(function (k) { return hp.has(k); })) return queryToState(hp.toString());
    try {
      var saved = localStorage.getItem(STORE_KEY);
      if (saved) return queryToState(saved);
    } catch (e) { /* private mode */ }
    return queryToState("");
  }

  function persist(s) {
    var q = stateToQuery(s);
    try {
      history.replaceState(null, "", q ? "#" + q : location.pathname + location.search);
    } catch (e) { /* file:// */ }
    try {
      if (q) localStorage.setItem(STORE_KEY, q);
      else localStorage.removeItem(STORE_KEY);
    } catch (e) { /* private mode */ }
  }

  // --- the filter ------------------------------------------------------
  function terms(s) {
    return s.split(",").map(function (t) { return t.trim().toLowerCase(); })
      .filter(Boolean);
  }

  function allowedDays(win) {
    if (win === "1") return new Set(days.slice(0, 1));
    if (win === "7") return new Set(days.slice(0, 7));
    return null;                       // "0" -> no window constraint
  }

  function computeVisible(s) {
    var activeCats = new Set(catBoxes.filter(function (b) { return b.checked; })
      .map(function (b) { return b.value; }));
    var activeKws = new Set(kwBoxes.filter(function (b) { return b.checked; })
      .map(function (b) { return b.value; }));
    var noKwConstraint = activeKws.size === allKeywords.length;
    var inc = terms(s.inc);
    var exc = terms(s.exc);
    var winDays = allowedDays(s.win);

    var visible = new Set();
    nodes.forEach(function (n) {
      if (!(n.categories || []).some(function (c) { return activeCats.has(c); })) return;
      if (winDays && !winDays.has(n.first_pubdate)) return;
      if (s.prio && !n.priority) return;
      if (exc.length && exc.some(function (t) { return n._text.indexOf(t) !== -1; })) return;
      var kwOk = noKwConstraint || n.priority
        || (n.keywords || []).some(function (k) { return activeKws.has(k); })
        || inc.some(function (t) { return n._text.indexOf(t) !== -1; });
      if (!kwOk) return;
      visible.add(n.id);
    });

    var narrowed = !(noKwConstraint && !s.prio && !inc.length && !exc.length
      && !winDays && activeCats.size === catBoxes.length);
    return { ids: visible, narrowed: narrowed };
  }

  function apply() {
    var s = readControls();
    var res = computeVisible(s);
    var ids = res.ids;

    cards.forEach(function (card) {
      card.hidden = !ids.has(card.id.replace(/^paper-/, ""));
    });

    clusters.forEach(function (cl) {
      var shown = cl.querySelectorAll(".paper:not([hidden])").length;
      cl.hidden = shown === 0;
      var cEl = cl.querySelector(".cluster-count");
      if (!cEl) return;
      if (res.narrowed) {
        cEl.textContent = shown + " of " + (cEl.dataset.total || shown) + " shown";
      } else {
        cEl.textContent = cEl.dataset.original;
      }
    });

    if (countEl) {
      countEl.textContent = res.narrowed
        ? "showing " + ids.size + " of " + nodes.length
        : nodes.length + " papers";
    }

    if (window.atlasGraph && window.atlasGraph.setVisible) {
      window.atlasGraph.setVisible(res.narrowed ? ids : null);
    }

    persist(s);
  }

  // --- wiring --------------------------------------------------------
  var debounce;
  panel.addEventListener("input", function (e) {
    if (e.target.type !== "text") return;         // checkboxes/select -> "change"
    clearTimeout(debounce);
    debounce = setTimeout(apply, 200);
  });
  panel.addEventListener("change", function (e) {
    if (e.target.type !== "text") apply();
  });
  if (resetBtn) {
    resetBtn.addEventListener("click", function () {
      writeControls(queryToState(""));
      apply();
    });
  }

  writeControls(loadState());
  apply();

  function toArray(nl) { return Array.prototype.slice.call(nl); }
})();
