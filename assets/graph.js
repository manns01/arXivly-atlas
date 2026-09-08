/* arXivly-atlas force graph. Reads JSON from <script id="atlas-data"> and
   renders into #atlas-graph. Needs d3 v7 (loaded just before this file). */
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

  var nodes = (atlas.nodes || []).map(function (n) { return Object.assign({}, n); });
  var links = (atlas.links || []).map(function (l) { return Object.assign({}, l); });

  if (nodes.length < 2) {
    mount.innerHTML = '<div class="graph-empty">The atlas needs at least two papers in the window.</div>';
    return;
  }

  var width = mount.clientWidth || 800;
  var height = mount.clientHeight || 520;

  // Distinct colour per cluster id; grey for unclustered (-1).
  var clusterIds = Array.from(new Set(nodes.map(function (n) { return n.cluster; })))
    .filter(function (c) { return c !== -1; });
  var palette = d3.schemeTableau10.concat(d3.schemeSet3 || []);
  var colour = d3.scaleOrdinal().domain(clusterIds).range(palette);
  function nodeColour(n) { return n.cluster === -1 ? "#9aa0a6" : colour(n.cluster); }

  var scoreExtent = d3.extent(nodes, function (n) { return n.score || 0; });
  var radius = d3.scaleSqrt().domain([scoreExtent[0] || 0, scoreExtent[1] || 1]).range([4, 9]);
  function nodeRadius(n) { return radius(n.score || 0) + (n.is_today ? 2 : 0); }

  var svg = d3.select(mount).append("svg")
    .attr("viewBox", [0, 0, width, height]);

  var root = svg.append("g");

  svg.call(d3.zoom()
    .scaleExtent([0.2, 6])
    .on("zoom", function (event) { root.attr("transform", event.transform); }));

  var link = root.append("g").selectAll("line")
    .data(links).join("line")
    .attr("class", "link")
    .attr("stroke-width", function (d) { return Math.max(0.5, (d.weight || 0.1) * 6); });

  var node = root.append("g").selectAll("circle")
    .data(nodes).join("circle")
    .attr("class", function (d) { return "node" + (d.is_today ? " today" : ""); })
    .attr("r", nodeRadius)
    .attr("fill", nodeColour)
    .attr("stroke", "var(--card)")
    .call(drag());

  var label = root.append("g").selectAll("text")
    .data(nodes.filter(function (n) { return n.is_today; })).join("text")
    .attr("class", "label")
    .attr("dx", function (d) { return nodeRadius(d) + 2; })
    .attr("dy", 3)
    .text(function (d) {
      return d.title.length > 40 ? d.title.slice(0, 38) + "…" : d.title;
    });

  var tooltip = d3.select(mount).append("div").attr("class", "graph-tooltip");

  node
    .on("mouseover", function (event, d) {
      tooltip.style("opacity", 1)
        .html("<strong>" + escapeHtml(d.title) + "</strong><br>" +
              escapeHtml(d.primary_category || "") +
              (d.is_today ? " · today" : ""));
    })
    .on("mousemove", function (event) {
      var box = mount.getBoundingClientRect();
      tooltip
        .style("left", (event.clientX - box.left + 12) + "px")
        .style("top", (event.clientY - box.top + 12) + "px");
    })
    .on("mouseout", function () { tooltip.style("opacity", 0); })
    .on("click", function (event, d) {
      var card = document.getElementById("paper-" + d.id);
      if (card) {
        var open = card.closest("details");
        if (open && !open.open) open.open = true;
        card.scrollIntoView({ behavior: "smooth", block: "center" });
        window.history.replaceState(null, "", "#paper-" + d.id);
      }
    });

  var sim = d3.forceSimulation(nodes)
    .force("link", d3.forceLink(links).id(function (d) { return d.id; })
      .distance(function (l) { return 40 + 60 * (1 - Math.min(1, l.weight || 0)); })
      .strength(function (l) { return 0.2 + 0.6 * Math.min(1, l.weight || 0); }))
    .force("charge", d3.forceManyBody().strength(-140))
    .force("center", d3.forceCenter(width / 2, height / 2))
    .force("collide", d3.forceCollide().radius(function (d) { return nodeRadius(d) + 3; }))
    .on("tick", ticked);

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

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
})();
