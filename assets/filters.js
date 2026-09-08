/* arXivly-atlas — in-browser view filters (free-form).

   Re-slices the already-built page: shows / hides paper cards and cluster
   sections and dims the atlas graph to match. Nothing here re-fetches or
   re-clusters — the corpus and the clusters are fixed at build time; the
   browser can only narrow within what the daily job already fetched.

   All four fields are comma-separated free text, seeded from config.yaml.

   show(paper) =
         paper.first_pubdate is inside the chosen window
     AND (Categories empty OR paper matches any typed category)
     AND (Exclude    empty OR no typed exclude term is in title+abstract)
     AND (starred-only off OR paper has a starred author)
     AND ( (Topics empty AND Authors empty)
           OR any typed topic is a substring of title+abstract
           OR any typed author matches )

   Category match is exact, or a whole archive: "astro-ph" matches "astro-ph.*".
   Author match reuses arXiv's normalization: the paper side ships already
   LaTeX/Unicode-normalized from Python (node.au); only the typed query is
   normalized here (Unicode accents only — users type plain text, not LaTeX).

   State is mirrored to the URL hash and localStorage. Because config.yaml seeds
   the fields, a saved state must distinguish "user cleared Topics" from "no
   saved state": a "v=1" marker is written whenever any field differs from its
   data-default, and only the differing fields are stored.
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

  var days = (data.days || []).slice();              // newest first
  var corpus = (data.corpus_categories || []).map(function (c) { return c.toLowerCase(); });

  var STORE_KEY = "arxivly-atlas:filters:2";
  var FIELDS = ["topics", "authors", "categories", "exclude"];

  // Name particles that belong with the surname -- mirror of
  // arxiv_text._PARTICLES (keep in sync).
  var PARTICLES = {
    "de": 1, "del": 1, "della": 1, "der": 1, "den": 1, "van": 1, "von": 1,
    "di": 1, "da": 1, "dos": 1, "das": 1, "la": 1, "le": 1, "el": 1, "al": 1,
    "bin": 1, "ibn": 1, "ter": 1, "ten": 1, "st": 1
  };

  nodes.forEach(function (n) {
    n._t = ((n.title || "").toLowerCase()) + " " + (n.text || "");
    n._au = (n.au ? String(n.au).split(";") : []).map(function (x) {
      var bar = x.indexOf("|");
      return bar < 0 ? ["", x] : [x.slice(0, bar), x.slice(bar + 1)];
    });
  });

  // --- controls -----------------------------------------------------------
  var inputs = {};
  FIELDS.forEach(function (k) { inputs[k] = panel.querySelector('input[name="' + k + '"]'); });
  var prioBox = panel.querySelector('input[name="priority-only"]');
  var winSelect = panel.querySelector('select[name="window"]');
  var resetBtn = panel.querySelector(".filter-reset");
  var countEl = panel.querySelector(".filter-count");
  var warnEl = panel.querySelector(".filter-warn");

  var cards = toArray(document.querySelectorAll(".clusters .paper"));
  var clusterEls = toArray(document.querySelectorAll(".clusters .cluster"));
  clusterEls.forEach(function (c) {
    var el = c.querySelector(".cluster-count");
    if (el) el.dataset.original = el.textContent;
  });

  panel.hidden = false;

  function fieldDefault(k) {
    return (inputs[k] && inputs[k].dataset.default) || "";
  }

  // --- state <-> controls ----------------------------------------------
  function readControls() {
    var s = {};
    FIELDS.forEach(function (k) { s[k] = inputs[k] ? inputs[k].value.trim() : ""; });
    s.prio = !!(prioBox && prioBox.checked);
    s.win = winSelect ? winSelect.value : "0";
    return s;
  }

  function writeControls(s) {
    FIELDS.forEach(function (k) { if (inputs[k]) inputs[k].value = s[k] || ""; });
    if (prioBox) prioBox.checked = !!s.prio;
    if (winSelect) winSelect.value = s.win || "0";
  }

  function stateToQuery(s) {
    var p = new URLSearchParams();
    FIELDS.forEach(function (k) {
      if ((s[k] || "") !== fieldDefault(k)) p.set(k, s[k] || "");
    });
    if (s.prio) p.set("prio", "1");
    if (s.win && s.win !== "0") p.set("win", s.win);
    var q = p.toString();
    return q ? "v=1&" + q : "";
  }

  function queryToState(q) {
    var p = new URLSearchParams(q);
    var s = {};
    FIELDS.forEach(function (k) { s[k] = p.has(k) ? p.get(k) : fieldDefault(k); });
    s.prio = p.get("prio") === "1";
    s.win = p.get("win") || "0";
    return s;
  }

  function loadState() {
    var hp = new URLSearchParams(location.hash.replace(/^#/, ""));
    if (hp.get("v")) return queryToState(hp.toString());
    try {
      var saved = localStorage.getItem(STORE_KEY);
      if (saved && new URLSearchParams(saved).get("v")) return queryToState(saved);
    } catch (e) { /* private mode */ }
    return queryToState("");                 // all config defaults
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

  // --- matching helpers ------------------------------------------------
  function parseTerms(s) {
    return String(s || "").split(",")
      .map(function (t) { return t.trim().toLowerCase(); })
      .filter(Boolean);
  }

  function normQuery(s) {
    return String(s || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "")
      .toLowerCase().trim();
  }

  // Port of arxiv_text.name_key / _split_name for the typed query side.
  function authorSpecKey(raw) {
    var given, surn;
    if (raw.indexOf(",") !== -1) {
      var bits = raw.split(",");
      surn = normQuery(bits[0]).split(/\s+/).filter(Boolean);
      given = normQuery(bits[1] || "").split(/\s+/).filter(Boolean);
    } else {
      var toks = normQuery(raw).split(/\s+/).filter(Boolean);
      if (!toks.length) return ["", ""];
      surn = [toks[toks.length - 1]];
      var i = toks.length - 2;
      while (i >= 0 && PARTICLES[toks[i]]) { surn.unshift(toks[i]); i--; }
      given = toks.slice(0, i + 1);
    }
    if (!surn.length) return ["", ""];
    var initial = (given[0] && given[0].charAt(0)) || "";
    return [initial, surn.join(" ")];
  }

  function authorMatches(pairs, specs) {
    return specs.some(function (spec) {
      var si = spec[0], ss = spec[1];
      return ss && pairs.some(function (p) {
        return p[1] === ss && (!si || si === p[0]);
      });
    });
  }

  function catHit(c, term) {
    return c === term || c.slice(0, term.length + 1) === term + ".";
  }

  function catMatches(node, terms) {
    var cats = (node.categories || []).map(function (c) { return c.toLowerCase(); });
    return terms.some(function (t) {
      return cats.some(function (c) { return catHit(c, t); });
    });
  }

  function allowedDays(win) {
    if (win === "1") return new Set(days.slice(0, 1));
    if (win === "3") return new Set(days.slice(0, 3));
    return null;
  }

  // --- apply ---------------------------------------------------------
  function apply() {
    var s = readControls();
    var topicTerms = parseTerms(s.topics);
    var catTerms = parseTerms(s.categories);
    var excTerms = parseTerms(s.exclude);
    var authorSpecs = parseTerms(s.authors).map(authorSpecKey)
      .filter(function (k) { return k[1]; });
    var winDays = allowedDays(s.win);
    var openQuery = topicTerms.length === 0 && authorSpecs.length === 0;

    var ids = new Set();
    nodes.forEach(function (n) {
      if (winDays && !winDays.has(n.first_pubdate)) return;
      if (catTerms.length && !catMatches(n, catTerms)) return;
      if (excTerms.length && excTerms.some(function (t) { return n._t.indexOf(t) !== -1; })) return;
      if (s.prio && !n.priority) return;
      var q = openQuery
        || topicTerms.some(function (t) { return n._t.indexOf(t) !== -1; })
        || authorMatches(n._au, authorSpecs);
      if (q) ids.add(n.id);
    });

    var narrowed = ids.size < nodes.length;

    cards.forEach(function (card) {
      card.hidden = !ids.has(card.id.replace(/^paper-/, ""));
    });

    clusterEls.forEach(function (cl) {
      var shown = cl.querySelectorAll(".paper:not([hidden])").length;
      cl.hidden = shown === 0;
      var cEl = cl.querySelector(".cluster-count");
      if (!cEl) return;
      cEl.textContent = narrowed
        ? shown + " of " + (cEl.dataset.total || shown) + " shown"
        : cEl.dataset.original;
    });

    if (countEl) {
      countEl.textContent = narrowed
        ? "showing " + ids.size + " of " + nodes.length
        : nodes.length + " papers";
    }

    if (window.atlasGraph && window.atlasGraph.setVisible) {
      window.atlasGraph.setVisible(narrowed ? ids : null);
    }

    updateWarn(catTerms);
    persist(s);
  }

  function updateWarn(catTerms) {
    if (!warnEl) return;
    var unknown = catTerms.filter(function (t) {
      return !corpus.some(function (c) { return catHit(c, t); });
    });
    warnEl.textContent = "";
    if (!unknown.length) { warnEl.hidden = true; return; }

    var archives = [];
    corpus.forEach(function (c) {
      var a = c.split(".")[0];
      if (archives.indexOf(a) === -1) archives.push(a);
    });
    warnEl.hidden = false;
    warnEl.textContent = "No papers in this window are in " + unknown.join(", ")
      + ". This site currently has: " + archives.join(", ")
      + " — add yours to `categories` in config.yaml and the next daily run picks it up. ";
    if (data.repo_url) {
      var a = document.createElement("a");
      a.href = data.repo_url.replace(/\/+$/, "") + "/blob/main/config.yaml";
      a.textContent = "Open config.yaml";
      warnEl.appendChild(a);
    }
  }

  // --- wiring --------------------------------------------------------
  var debounce;
  panel.addEventListener("input", function (e) {
    if (e.target.type !== "text") return;
    clearTimeout(debounce);
    debounce = setTimeout(apply, 200);
  });
  panel.addEventListener("change", function (e) {
    if (e.target.type !== "text") apply();
  });
  panel.addEventListener("click", function (e) {
    var chip = e.target.closest && e.target.closest(".chip");
    if (chip) {
      var field = inputs[chip.dataset.field];
      var val = chip.dataset.value;
      if (field && val) {
        var have = parseTerms(field.value).indexOf(val.toLowerCase()) !== -1;
        if (!have) {
          var base = field.value.replace(/\s*,?\s*$/, "");
          field.value = base ? base + ", " + val : val;
          apply();
        }
      }
      return;
    }
    if (e.target === resetBtn) {
      e.preventDefault();
      writeControls(queryToState(""));
      apply();
    }
  });

  writeControls(loadState());
  apply();

  function toArray(nl) { return Array.prototype.slice.call(nl); }
})();
