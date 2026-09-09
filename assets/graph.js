/* arXivly-atlas atlas graph. Reads JSON from <script id="atlas-data"> and
   renders into #atlas-graph. Needs d3 v7 (loaded just before this file).

   Two views share one force layout:
     - "map"    : one node per subject in the recent window (few, always legible)
     - "papers" : one node per paper, scoped to today + its direct neighbours

   The default comes from site.graph_default; a toggle switches when both are
   available. filters.js dims the *papers* view to a filtered subset. */
(function () {
  "use strict";

  var mount = document.getElementById("atlas-graph");
  var dataEl = document.getElementById("atlas-data");
  if (!mount || !dataEl || typeof d3 === "undefined") return;

  var atlas;
  try {
    atlas = JSON.parse(dataEl.textContent);
  } catch (e) {
    mount.innerHTML = '<div class="graph-empty">Could not parse atlas data.</div>';
    return;
  }

  var hintEl = document.querySelector(".atlas-hint");
  var toggleEl = document.querySelector(".graph-toggle");
  var legendEl = document.querySelector(".graph-legend");

  var CAT_COLOUR = {
    "astro-ph": "#3b82f6", "gr-qc": "#8b5cf6", "hep-ph": "#f59e0b",
    "hep-th": "#ef4444", "math-ph": "#10b981"
  };
  var MIXED_COLOUR = "#9aa0a6";
  function catColour(c) { return CAT_COLOUR[c] || MIXED_COLOUR; }

  // ---- build the two datasets -------------------------------------------
  var allNodes = (atlas.nodes || []).map(function (n) { return Object.assign({}, n); });
  var allLinks = (atlas.links || []).map(function (l) { return Object.assign({}, l); });

  function papersDataset() {
    var byId = {};
    allNodes.forEach(function (n) { byId[n.id] = n; });
    var keep = new Set();
    allNodes.forEach(function (n) { if (n.is_today) keep.add(n.id); });
    allLinks.forEach(function (l) {
      if (keep.has(l.source) || keep.has(l.target)) { keep.add(l.source); keep.add(l.target); }
    });
    if (keep.size < 2) allNodes.forEach(function (n) { keep.add(n.id); });

    var nodes = allNodes.filter(function (n) { return keep.has(n.id); })
      .map(function (n) { return Object.assign({}, n); });
    var links = allLinks.filter(function (l) { return keep.has(l.source) && keep.has(l.target); })
      .map(function (l) { return Object.assign({}, l); });

    var limit = atlas.graph_labels || 20;
    var labelIds = new Set(
      nodes.slice().sort(function (a, b) { return (b.score || 0) - (a.score || 0); })
        .slice(0, limit).map(function (n) { return n.id; })
    );

    var clusterIds = Array.from(new Set(nodes.map(function (n) { return n.cluster; })))
      .filter(function (c) { return c !== -1; });
    var palette = d3.schemeTableau10.concat(d3.schemeSet3 || []);
    var colour = d3.scaleOrdinal().domain(clusterIds).range(palette);
    var scoreExtent = d3.extent(nodes, function (n) { return n.score || 0; });
    var rscale = d3.scaleSqrt().domain([scoreExtent[0] || 0, scoreExtent[1] || 1]).range([4, 9]);

    return {
      kind: "papers", nodes: nodes, links: links,
      radius: function (n) { return rscale(n.score || 0) + (n.is_today ? 2 : 0); },
      fill: function (n) { return n.cluster === -1 ? MIXED_COLOUR : colour(n.cluster); },
      ring: function (n) { return n.is_today; },
      labelled: function (n) { return labelIds.has(n.id); },
      labelText: function (n) {
        return n.title.length > 40 ? n.title.slice(0, 38) + "…" : n.title;
      },
      tip: function (n) {
        return "<strong>" + escapeHtml(n.title) + "</strong><br>" +
          escapeHtml(n.primary_category || "") + (n.is_today ? " · today" : "");
      }
    };
  }

  function mapDataset() {
    var m = atlas.map;
    if (!m || !m.nodes || m.nodes.length < 2) return null;
    var nodes = m.nodes.map(function (n) { return Object.assign({}, n); });
    var links = (m.links || []).map(function (l) { return Object.assign({}, l); });
    var maxCount = d3.max(nodes, function (n) { return n.count || 1; }) || 1;
    var rscale = d3.scaleSqrt().domain([1, maxCount]).range([10, 34]);
    return {
      kind: "map", nodes: nodes, links: links,
      radius: function (n) { return rscale(Math.max(1, n.count || 1)); },
      fill: function (n) { return catColour(n.cat); },
      ring: function (n) { return (n.today || 0) > 0; },
      labelled: function () { return true; },
      labelText: function (n) { return n.label; },
      tip: function (n) {
        return "<strong>" + escapeHtml(n.label) + "</strong><br>" +
          (n.count || 0) + " papers, " + (n.today || 0) + " today";
      }
    };
  }

  var datasets = { papers: papersDataset(), map: mapDataset() };
  var current = (atlas.graph_default === "map" && datasets.map) ? "map" : "papers";

  if (datasets.map && toggleEl) {
    toggleEl.hidden = false;
    toArray(toggleEl.querySelectorAll("button")).forEach(function (b) {
      b.addEventListener("click", function () { switchTo(b.dataset.graph); });
    });
  }

  // ---- render ----------------------------------------------------------
  var width = mount.clientWidth || 800;
  var height = mount.clientHeight || 520;

  var svg = d3.select(mount).append("svg").attr("viewBox", [0, 0, width, height]);
  var root = svg.append("g");
  svg.call(d3.zoom().scaleExtent([0.2, 6])
    .on("zoom", function (event) { root.attr("transform", event.transform); }));

  var tooltip = d3.select(mount).append("div").attr("class", "graph-tooltip");
  var tipMaxW = parseFloat(getComputedStyle(tooltip.node()).maxWidth) || 352;

  var link, node, label, sim, activeData;

  function render(kind) {
    current = kind;
    activeData = datasets[kind];
    root.selectAll("*").remove();
    if (sim) sim.stop();

    var D = activeData;

    link = root.append("g").selectAll("line")
      .data(D.links).join("line")
      .attr("class", "link")
      .attr("stroke-width", function (d) { return Math.max(0.5, (d.weight || 0.1) * 6); });

    node = root.append("g").selectAll("circle")
      .data(D.nodes).join("circle")
      .attr("class", function (d) {
        return "node" + (D.ring(d) ? " today" : "") + (d.spotlight ? " spot" : "");
      })
      .attr("r", D.radius)
      .attr("fill", D.fill)
      .attr("stroke", "var(--card)")
      .call(drag());

    label = root.append("g").selectAll("text")
      .data(D.nodes.filter(D.labelled)).join("text")
      .attr("class", "label")
      .attr("dx", function (d) { return D.radius(d) + 2; })
      .attr("dy", 3)
      .text(D.labelText);

    node
      .on("mouseover", function (event, d) {
        tooltip.style("opacity", 1).html(D.tip(d));
        placeTooltip(event);
      })
      .on("mousemove", placeTooltip)
      .on("mouseout", function () { tooltip.style("opacity", 0); })
      .on("click", function (event, d) { onNodeClick(d); });

    sim = d3.forceSimulation(D.nodes)
      .force("link", d3.forceLink(D.links).id(function (d) { return d.id; })
        .distance(function (l) { return 40 + 60 * (1 - Math.min(1, l.weight || 0)); })
        .strength(function (l) { return 0.2 + 0.6 * Math.min(1, l.weight || 0); }))
      .force("charge", d3.forceManyBody().strength(kind === "map" ? -420 : -140))
      .force("center", d3.forceCenter(width / 2, height / 2))
      .force("collide", d3.forceCollide().radius(function (d) { return D.radius(d) + 4; }))
      .on("tick", ticked);

    // Map nodes with no cross-subject link (e.g. a small, self-contained
    // cluster like "Gravitational waves" on a light day) have nothing to
    // pull them back against the charge force and drift off-canvas. A weak
    // pull toward center only affects those otherwise-unanchored nodes --
    // linked nodes are dominated by the much stronger link force.
    if (kind === "map") {
      sim.force("x", d3.forceX(width / 2).strength(0.05))
        .force("y", d3.forceY(height / 2).strength(0.05));
    }

    updateChrome();
  }

  function updateChrome() {
    if (hintEl) {
      var k = current === "map" ? "hintMap" : "hintPapers";
      if (hintEl.dataset[k]) hintEl.textContent = hintEl.dataset[k];
    }
    if (toggleEl) {
      toArray(toggleEl.querySelectorAll("button")).forEach(function (b) {
        b.classList.toggle("active", b.dataset.graph === current);
      });
    }
    if (legendEl) {
      if (current === "map") {
        var cats = Array.from(new Set(activeData.nodes.map(function (n) { return n.cat; })))
          .filter(Boolean);
        var swatches = cats.map(function (c) {
          return '<span class="lg-item"><span class="lg-dot" style="background:' +
            catColour(c) + '"></span>' + escapeHtml(c) + "</span>";
        }).join("");
        var note = activeData.links.length === 0
          ? '<span class="lg-note">no strong links between subjects today — position is not meaningful</span>'
          : "";
        legendEl.innerHTML = swatches + note;
        legendEl.hidden = !(swatches || note);
      } else {
        legendEl.hidden = true;
      }
    }
  }

  function switchTo(kind) {
    if (kind === current || !datasets[kind]) return;
    render(kind);
  }

  function onNodeClick(d) {
    if (current === "map") {
      var subj = findSubjectByLabel(d.label);
      if (subj) {
        openAncestors(subj);
        subj.open = true;
        subj.scrollIntoView({ behavior: "smooth", block: "start" });
      }
      return;
    }
    var card = document.getElementById("paper-" + d.id);
    if (!card) return;
    var inner = card.querySelector("details.paper-more");
    if (inner) inner.open = true;
    openAncestors(card);
    card.scrollIntoView({ behavior: "smooth", block: "center" });
    try { history.replaceState(null, "", "#paper-" + d.id); } catch (e) { /* file:// */ }
  }

  function openAncestors(el) {
    for (var p = el.parentElement; p; p = p.parentElement) {
      if (p.tagName === "DETAILS") p.open = true;
    }
  }

  function findSubjectByLabel(labelText) {
    var subs = document.querySelectorAll(".clusters .subject");
    for (var i = 0; i < subs.length; i++) {
      var lab = subs[i].querySelector(".subject-label");
      if (lab && lab.textContent.trim() === String(labelText).trim()) return subs[i];
    }
    return null;
  }

  function ticked() {
    link
      .attr("x1", function (d) { return d.source.x; })
      .attr("y1", function (d) { return d.source.y; })
      .attr("x2", function (d) { return d.target.x; })
      .attr("y2", function (d) { return d.target.y; });
    node.attr("cx", function (d) { return d.x; }).attr("cy", function (d) { return d.y; });
    label.attr("x", function (d) { return d.x; }).attr("y", function (d) { return d.y; });
  }

  function drag() {
    return d3.drag()
      .on("start", function (event, d) {
        if (!event.active) sim.alphaTarget(0.3).restart();
        d.fx = d.x; d.fy = d.y;
      })
      .on("drag", function (event, d) { d.fx = event.x; d.fy = event.y; })
      .on("end", function (event, d) {
        if (!event.active) sim.alphaTarget(0);
        d.fx = null; d.fy = null;
      });
  }

  function placeTooltip(event) {
    var pad = 12;
    var tip = tooltip.node();
    var w = mount.clientWidth;
    var h = mount.clientHeight;
    var box = mount.getBoundingClientRect();
    tip.style.maxWidth = Math.max(120, Math.min(tipMaxW, w - 2 * pad)) + "px";
    var px = event.clientX - box.left - mount.clientLeft;
    var py = event.clientY - box.top - mount.clientTop;
    var tw = tip.offsetWidth;
    var th = tip.offsetHeight;
    var left = px + pad;
    var top = py + pad;
    if (left + tw + pad > w && px - pad - tw >= 4) left = px - pad - tw;
    if (top + th + pad > h && py - pad - th >= 4) top = py - pad - th;
    if (tw && th) {
      left = Math.max(4, Math.min(left, w - tw - 4));
      top = Math.max(4, Math.min(top, h - th - 4));
    }
    tooltip.style("left", left + "px").style("top", top + "px");
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function toArray(nl) { return Array.prototype.slice.call(nl); }

  // filters.js dims the *papers* view to a filtered subset; a no-op elsewhere.
  window.atlasGraph = {
    setVisible: function (ids) {
      if (current !== "papers" || !node) return;
      var show = ids == null ? null : (ids instanceof Set ? ids : new Set(ids));
      var visible = function (d) { return !show || show.has(d.id); };
      var ratio = show ? show.size / datasets.papers.nodes.length : 1;
      var hardHide = show && ratio < 0.4;
      node.classed("dimmed", function (d) { return !visible(d); })
        .classed("gone", function (d) { return hardHide && !visible(d); })
        .attr("pointer-events", function (d) { return visible(d) ? null : "none"; });
      label.classed("dimmed", function (d) { return !visible(d); })
        .classed("gone", function (d) { return hardHide && !visible(d); });
      link.classed("dimmed", function (d) {
        return show && !(show.has(d.source.id) && show.has(d.target.id));
      }).classed("gone", function (d) {
        return hardHide && show && !(show.has(d.source.id) && show.has(d.target.id));
      });
    }
  };

  render(current);
})();
