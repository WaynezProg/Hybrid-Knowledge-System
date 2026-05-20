"""Static artifact rendering for Graphify."""
# ruff: noqa: E501

from __future__ import annotations

import json

from hks.graphify.models import GraphifyGraph


def _json_script_payload(graph: GraphifyGraph) -> str:
    payload = json.dumps(graph.to_dict(), ensure_ascii=False)
    return payload.replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")


def render_html(graph: GraphifyGraph) -> str:
    payload = _json_script_payload(graph)

    html_content = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>HKS Graphify Dashboard</title>
  <style>
    :root {
      --bg-color: #09090b;
      --panel-bg: rgba(20, 20, 25, 0.65);
      --border-color: rgba(255, 255, 255, 0.08);
      --text-main: #f4f4f5;
      --text-muted: #a1a1aa;
      --accent-color: #3b82f6;

      --color-source: #3b82f6;
      --color-wiki: #10b981;
      --color-entity: #8b5cf6;
      --color-concept: #f59e0b;
      --color-artifact: #ec4899;
      --color-community: #14b8a6;
    }

    * {
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }

    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, "PingFang TC", "Microsoft JhengHei", sans-serif;
      background-color: var(--bg-color);
      color: var(--text-main);
      width: 100vw;
      height: 100vh;
      overflow: hidden;
      display: flex;
      flex-direction: column;
    }

    .bg-grid {
      position: absolute;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
      background-image:
        linear-gradient(to right, rgba(255, 255, 255, 0.02) 1px, transparent 1px),
        linear-gradient(to bottom, rgba(255, 255, 255, 0.02) 1px, transparent 1px);
      background-size: 32px 32px;
      pointer-events: none;
      z-index: 1;
    }

    /* Navbar */
    header {
      height: 64px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0 24px;
      border-bottom: 1px solid var(--border-color);
      background: rgba(9, 9, 11, 0.7);
      backdrop-filter: blur(12px);
      z-index: 100;
    }

    .logo-section {
      display: flex;
      align-items: center;
      gap: 12px;
    }

    .logo-section h1 {
      font-size: 20px;
      font-weight: 700;
      letter-spacing: 0;
      background: linear-gradient(135deg, #fff 30%, #a1a1aa 100%);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
    }

    .badge {
      background: rgba(59, 130, 246, 0.15);
      border: 1px solid rgba(59, 130, 246, 0.3);
      color: #60a5fa;
      font-size: 11px;
      padding: 2px 8px;
      border-radius: 9999px;
      font-weight: 500;
    }

    .stats-container {
      display: flex;
      gap: 16px;
    }

    .stat-card {
      background: rgba(255, 255, 255, 0.03);
      border: 1px solid var(--border-color);
      padding: 6px 16px;
      border-radius: 8px;
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 13px;
    }

    .stat-card .val {
      font-weight: 700;
      color: #fff;
    }

    .stat-card .lbl {
      color: var(--text-muted);
    }

    /* Layout */
    main {
      flex: 1;
      display: flex;
      position: relative;
      overflow: hidden;
      z-index: 10;
    }

    /* Left Sidebar: Controls */
    .sidebar-left {
      width: 320px;
      height: 100%;
      background: var(--panel-bg);
      backdrop-filter: blur(16px);
      border-right: 1px solid var(--border-color);
      display: flex;
      flex-direction: column;
      gap: 24px;
      padding: 24px;
      overflow-y: auto;
      z-index: 50;
    }

    /* Right Sidebar: Details */
    .sidebar-right {
      width: 340px;
      height: 100%;
      background: var(--panel-bg);
      backdrop-filter: blur(16px);
      border-left: 1px solid var(--border-color);
      display: flex;
      flex-direction: column;
      padding: 24px;
      overflow-y: auto;
      z-index: 50;
    }

    /* Canvas */
    .canvas-container {
      flex: 1;
      height: 100%;
      position: relative;
      background: #050507;
      user-select: none;
    }

    svg {
      width: 100%;
      height: 100%;
      cursor: grab;
    }

    svg:active {
      cursor: grabbing;
    }

    /* Controls Elements */
    .section-title {
      font-size: 14px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      color: #fff;
      margin-bottom: 12px;
      display: flex;
      align-items: center;
      justify-content: space-between;
    }

    .search-wrapper {
      position: relative;
    }

    .search-input {
      width: 100%;
      background: rgba(255, 255, 255, 0.05);
      border: 1px solid var(--border-color);
      color: #fff;
      padding: 10px 14px;
      border-radius: 8px;
      font-size: 13px;
      outline: none;
      transition: all 0.2s;
    }

    .search-input:focus {
      border-color: var(--accent-color);
      background: rgba(255, 255, 255, 0.08);
      box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.2);
    }

    .search-results {
      position: absolute;
      top: calc(100% + 4px);
      left: 0;
      right: 0;
      background: #18181b;
      border: 1px solid var(--border-color);
      border-radius: 8px;
      max-height: 200px;
      overflow-y: auto;
      z-index: 60;
      box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.3);
      display: none;
    }

    .search-item {
      padding: 8px 12px;
      font-size: 12px;
      cursor: pointer;
      display: flex;
      justify-content: space-between;
      align-items: center;
      transition: background 0.15s;
    }

    .search-item:hover {
      background: rgba(255, 255, 255, 0.08);
    }

    .search-item .kind-badge {
      font-size: 10px;
      opacity: 0.7;
    }

    /* Filters Checkboxes */
    .filter-list {
      display: flex;
      flex-direction: column;
      gap: 10px;
    }

    .filter-item {
      display: flex;
      align-items: center;
      justify-content: space-between;
      font-size: 13px;
      cursor: pointer;
      user-select: none;
    }

    .filter-checkbox-wrapper {
      display: flex;
      align-items: center;
      gap: 10px;
    }

    .filter-item input {
      cursor: pointer;
      accent-color: var(--accent-color);
    }

    .color-dot {
      width: 10px;
      height: 10px;
      border-radius: 50%;
      display: inline-block;
    }

    .count-badge {
      font-size: 11px;
      color: var(--text-muted);
      background: rgba(255, 255, 255, 0.05);
      padding: 1px 6px;
      border-radius: 4px;
    }

    /* Communities List */
    .community-list {
      display: flex;
      flex-direction: column;
      gap: 8px;
      max-height: 240px;
      overflow-y: auto;
      padding-right: 4px;
    }

    .community-item {
      background: rgba(255, 255, 255, 0.02);
      border: 1px solid var(--border-color);
      padding: 10px;
      border-radius: 6px;
      cursor: pointer;
      font-size: 12px;
      transition: all 0.2s;
    }

    .community-item:hover, .community-item.active {
      background: rgba(20, 184, 166, 0.1);
      border-color: rgba(20, 184, 166, 0.4);
    }

    .community-item-header {
      display: flex;
      justify-content: space-between;
      font-weight: 600;
      color: #fff;
      margin-bottom: 4px;
    }

    .community-item-desc {
      color: var(--text-muted);
      font-size: 11px;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    /* Physics Controls */
    .slider-group {
      display: flex;
      flex-direction: column;
      gap: 6px;
      font-size: 12px;
      color: var(--text-muted);
      margin-bottom: 12px;
    }

    .slider-header {
      display: flex;
      justify-content: space-between;
    }

    .slider-group input {
      width: 100%;
      accent-color: var(--accent-color);
      cursor: pointer;
    }

    .physics-btn {
      width: 100%;
      background: rgba(255, 255, 255, 0.05);
      border: 1px solid var(--border-color);
      color: #fff;
      padding: 8px;
      border-radius: 6px;
      font-size: 12px;
      cursor: pointer;
      font-weight: 500;
      transition: all 0.2s;
    }

    .physics-btn:hover {
      background: rgba(255, 255, 255, 0.1);
      border-color: rgba(255, 255, 255, 0.2);
    }

    /* Float controls */
    .float-controls {
      position: absolute;
      bottom: 24px;
      right: 24px;
      display: flex;
      flex-direction: column;
      gap: 8px;
      z-index: 40;
    }

    .float-btn {
      width: 40px;
      height: 40px;
      border-radius: 8px;
      background: var(--panel-bg);
      backdrop-filter: blur(12px);
      border: 1px solid var(--border-color);
      color: #fff;
      display: flex;
      align-items: center;
      justify-content: center;
      cursor: pointer;
      font-size: 18px;
      font-weight: 600;
      transition: all 0.2s;
      box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.2);
    }

    .float-btn:hover {
      background: rgba(255, 255, 255, 0.12);
      border-color: rgba(255, 255, 255, 0.2);
    }

    /* Details styling */
    .details-placeholder {
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      height: 100%;
      color: var(--text-muted);
      text-align: center;
      gap: 12px;
      font-size: 13px;
    }

    .details-content {
      display: flex;
      flex-direction: column;
      gap: 20px;
      height: 100%;
    }

    .details-header {
      border-bottom: 1px solid var(--border-color);
      padding-bottom: 16px;
    }

    .details-title {
      font-size: 18px;
      font-weight: 700;
      color: #fff;
      word-break: break-word;
      margin-bottom: 6px;
    }

    .details-subtitle {
      font-size: 12px;
      color: var(--text-muted);
      text-transform: uppercase;
      letter-spacing: 0.5px;
      display: flex;
      align-items: center;
      gap: 6px;
    }

    .detail-card {
      background: rgba(255, 255, 255, 0.02);
      border: 1px solid var(--border-color);
      border-radius: 6px;
      padding: 12px;
      font-size: 13px;
    }

    .detail-card-title {
      font-size: 11px;
      text-transform: uppercase;
      color: var(--text-muted);
      margin-bottom: 6px;
      letter-spacing: 0.5px;
      font-weight: 600;
    }

    .detail-card-val {
      color: #e4e4e7;
      word-break: break-all;
    }

    .badge-kind {
      padding: 2px 8px;
      border-radius: 4px;
      font-size: 11px;
      font-weight: 600;
      color: #fff;
      display: inline-block;
    }

    .badge-relation {
      background: rgba(139, 92, 246, 0.15);
      border: 1px solid rgba(139, 92, 246, 0.3);
      color: #a78bfa;
      padding: 2px 6px;
      border-radius: 4px;
      font-family: monospace;
    }

    .badge-layer {
      background: rgba(255, 255, 255, 0.08);
      color: #fff;
      padding: 1px 6px;
      border-radius: 4px;
      font-size: 11px;
    }

    .audit-findings-title {
      font-size: 14px;
      font-weight: 600;
      margin-bottom: 12px;
      color: #fff;
      border-bottom: 1px solid var(--border-color);
      padding-bottom: 6px;
    }

    .audit-list {
      display: flex;
      flex-direction: column;
      gap: 8px;
    }

    .audit-item {
      padding: 10px;
      border-radius: 6px;
      border: 1px solid var(--border-color);
      font-size: 12px;
    }

    .audit-item.error {
      background: rgba(239, 68, 68, 0.08);
      border-color: rgba(239, 68, 68, 0.25);
    }

    .audit-item.warning {
      background: rgba(245, 158, 11, 0.08);
      border-color: rgba(245, 158, 11, 0.25);
    }

    .audit-item.info {
      background: rgba(59, 130, 246, 0.08);
      border-color: rgba(59, 130, 246, 0.25);
    }

    .audit-header {
      font-weight: 600;
      margin-bottom: 4px;
      display: flex;
      justify-content: space-between;
    }

    .audit-desc {
      color: var(--text-muted);
      word-break: break-word;
    }

    /* SVG Style rules */
    .node-group {
      cursor: pointer;
    }

    .node-circle {
      transition: r 0.2s, stroke-width 0.2s;
    }

    .node-label {
      font-size: 11px;
      fill: #e4e4e7;
      pointer-events: none;
      text-anchor: middle;
      font-weight: 500;
    }

    .link {
      fill: none;
      stroke-linecap: round;
      pointer-events: stroke;
      cursor: pointer;
      transition: stroke-width 0.2s, opacity 0.2s;
    }

    .link-overlay {
      fill: none;
      stroke: transparent;
      stroke-width: 12px;
      cursor: pointer;
    }

    /* Scrollbar */
    ::-webkit-scrollbar {
      width: 6px;
    }
    ::-webkit-scrollbar-track {
      background: transparent;
    }
    ::-webkit-scrollbar-thumb {
      background: rgba(255, 255, 255, 0.1);
      border-radius: 9999px;
    }
    ::-webkit-scrollbar-thumb:hover {
      background: rgba(255, 255, 255, 0.2);
    }
  </style>
</head>
<body>
  <div class="bg-grid"></div>

  <header>
    <div class="logo-section">
      <h1>HKS Graphify</h1>
      <span class="badge">v1.0.0-interactive</span>
    </div>

    <div class="stats-container">
      <div class="stat-card">
        <span class="val" id="stats-nodes">0</span>
        <span class="lbl">nodes</span>
      </div>
      <div class="stat-card">
        <span class="val" id="stats-edges">0</span>
        <span class="lbl">edges</span>
      </div>
      <div class="stat-card">
        <span class="val" id="stats-communities">0</span>
        <span class="lbl">communities</span>
      </div>
    </div>
  </header>

  <main>
    <div class="sidebar-left">
      <div>
        <div class="section-title">Search Graph</div>
        <div class="search-wrapper">
          <input type="text" class="search-input" id="search-input" placeholder="Type node name..." autocomplete="off">
          <div class="search-results" id="search-results"></div>
        </div>
      </div>

      <div>
        <div class="section-title">Node Types</div>
        <div class="filter-list" id="type-filters"></div>
      </div>

      <div>
        <div class="section-title">Physics settings</div>
        <div class="slider-group">
          <div class="slider-header">
            <span>Link Distance</span>
            <span id="val-distance">80</span>
          </div>
          <input type="range" id="slide-distance" min="40" max="250" value="80">
        </div>
        <div class="slider-group">
          <div class="slider-header">
            <span>Gravity Strength</span>
            <span id="val-charge">800</span>
          </div>
          <input type="range" id="slide-charge" min="100" max="2000" value="800">
        </div>
        <button class="physics-btn" id="btn-pause">Pause Simulation</button>
      </div>

      <div>
        <div class="section-title">Communities</div>
        <div class="community-list" id="community-list"></div>
      </div>
    </div>

    <!-- Canvas -->
    <div class="canvas-container" id="canvas-container">
      <svg id="graph-svg">
        <defs>
          <!-- Markers for arrowheads -->
          <marker id="arrow-extracted" viewBox="0 -5 10 10" refX="22" refY="0" markerWidth="6" markerHeight="6" orient="auto">
            <path d="M0,-5L10,0L0,5" fill="#3b82f6" opacity="0.8"></path>
          </marker>
          <marker id="arrow-inferred" viewBox="0 -5 10 10" refX="22" refY="0" markerWidth="6" markerHeight="6" orient="auto">
            <path d="M0,-5L10,0L0,5" fill="#c084fc" opacity="0.8"></path>
          </marker>
          <marker id="arrow-ambiguous" viewBox="0 -5 10 10" refX="22" refY="0" markerWidth="6" markerHeight="6" orient="auto">
            <path d="M0,-5L10,0L0,5" fill="#fb923c" opacity="0.8"></path>
          </marker>
          <marker id="arrow-highlighted" viewBox="0 -5 10 10" refX="22" refY="0" markerWidth="7" markerHeight="7" orient="auto">
            <path d="M0,-5L10,0L0,5" fill="#ffffff"></path>
          </marker>
        </defs>
        <g id="zoom-group">
          <g id="links-group"></g>
          <g id="nodes-group"></g>
        </g>
      </svg>

      <div class="float-controls">
        <button class="float-btn" id="zoom-in" title="Zoom In">+</button>
        <button class="float-btn" id="zoom-out" title="Zoom Out">-</button>
        <button class="float-btn" id="zoom-reset" title="Reset View">⊙</button>
      </div>
    </div>

    <!-- Right Sidebar -->
    <div class="sidebar-right" id="details-sidebar">
      <div class="details-placeholder" id="details-placeholder">
        <svg fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg" style="width:48px; height:48px; opacity:0.5; stroke:currentColor;">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path>
        </svg>
        <p>Select a node or edge to inspect its details</p>
      </div>
      <div class="details-content" id="details-content" style="display: none;"></div>
    </div>
  </main>

  <script type="application/json" id="graphify-data">""" + payload + """</script>

  <script>
    // Constants & config
    const colors = {
      source: '#3b82f6',
      wiki_page: '#10b981',
      entity: '#8b5cf6',
      concept: '#f59e0b',
      artifact: '#ec4899',
      community: '#14b8a6'
    };

    function escapeHtml(value) {
      return String(value ?? '').replace(/[&<>"']/g, ch => ({
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#39;'
      })[ch]);
    }

    function escapeAttr(value) {
      return escapeHtml(value);
    }

    function colorForKind(kind) {
      return colors[kind] || '#71717a';
    }

    function formatScore(value, fallback = '1.00') {
      const numeric = Number(value);
      return Number.isFinite(numeric) ? numeric.toFixed(2) : fallback;
    }

    function bindNodeLinks(root) {
      root.querySelectorAll('.node-link').forEach(el => {
        el.addEventListener('click', event => {
          event.preventDefault();
          selectNodeById(el.dataset.nodeId);
        });
      });
    }

    // Load data from the local JSON script tag. The Python side escapes
    // HTML-significant characters as JSON unicode escapes, so no entity
    // decoding is required here.
    const rawData = JSON.parse(document.getElementById('graphify-data').textContent);
    const rawNodes = rawData.nodes || [];
    const rawEdges = rawData.edges || [];
    const communities = rawData.communities || [];
    const auditFindings = rawData.audit_findings || [];

    const nodes = rawNodes.map(n => ({
      id: n.id,
      label: n.label,
      kind: n.kind,
      source_layer: n.source_layer,
      source_ref: n.source_ref,
      provenance: n.provenance,
      community_id: n.community_id,
      x: 0,
      y: 0,
      vx: 0,
      vy: 0,
      isFixed: false,
      degree: rawEdges.filter(e => e.source === n.id || e.target === n.id).length
    }));

    const edges = rawEdges.map(e => ({
      id: e.id,
      source: e.source,
      target: e.target,
      relation: e.relation,
      evidence: e.evidence,
      confidence_score: e.confidence_score,
      weight: e.weight,
      source_layer: e.source_layer,
      source_ref: e.source_ref,
      rationale: e.rationale
    }));

    const nodeMap = {};
    nodes.forEach(n => { nodeMap[n.id] = n; });

    document.getElementById('stats-nodes').textContent = nodes.length;
    document.getElementById('stats-edges').textContent = edges.length;
    document.getElementById('stats-communities').textContent = communities.length;

    const activeKinds = new Set(nodes.map(n => n.kind));
    let selectedNodeId = null;
    let selectedEdgeId = null;
    let activeCommunityId = null;
    let isPaused = false;

    const adjList = {};
    edges.forEach(e => {
      adjList[e.source + '-' + e.target] = true;
      adjList[e.target + '-' + e.source] = true;
    });

    function areConnected(u, v) {
      return u === v || adjList[u + '-' + v];
    }

    let zoomScale = 1;
    let zoomTx = 0;
    let zoomTy = 0;
    const canvasContainer = document.getElementById('canvas-container');
    const svgEl = document.getElementById('graph-svg');
    const zoomGroupEl = document.getElementById('zoom-group');

    let width = canvasContainer.clientWidth || 800;
    let height = canvasContainer.clientHeight || 600;

    nodes.forEach((n, idx) => {
      const angle = (idx / nodes.length) * 2 * Math.PI;
      const radius = 100 + Math.random() * 150;
      n.x = width / 2 + Math.cos(angle) * radius;
      n.y = height / 2 + Math.sin(angle) * radius;
    });

    initFilters();
    initCommunities();
    initSearch();
    initDefaultRightSidebar();

    const linksGroup = document.getElementById('links-group');
    const nodesGroup = document.getElementById('nodes-group');

    const linkDOMs = edges.map(edge => {
      const g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
      g.setAttribute('class', 'link-container');

      const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
      line.setAttribute('class', 'link');
      line.setAttribute('stroke', getEdgeColor(edge.evidence));
      line.setAttribute('stroke-width', 1.5 + (edge.weight || 1) * 1.2);
      line.setAttribute('marker-end', `url(#arrow-${edge.evidence.toLowerCase()})`);

      const strokeDash = getEdgeStrokeDash(edge.evidence);
      if (strokeDash) {
        line.setAttribute('stroke-dasharray', strokeDash);
      }
      line.setAttribute('opacity', 0.4 * (edge.confidence_score || 1));

      const overlay = document.createElementNS('http://www.w3.org/2000/svg', 'line');
      overlay.setAttribute('class', 'link-overlay');

      g.appendChild(line);
      g.appendChild(overlay);
      linksGroup.appendChild(g);

      overlay.addEventListener('click', (e) => {
        e.stopPropagation();
        selectEdge(edge);
      });

      return { edge, line, overlay, container: g };
    });

    const nodeDOMs = nodes.map(node => {
      const g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
      g.setAttribute('class', 'node-group');

      const glow = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
      glow.setAttribute('class', 'node-glow');
      glow.setAttribute('r', 11 + Math.sqrt(node.degree || 0) * 2.5);
      glow.setAttribute('fill', colors[node.kind]);
      glow.setAttribute('opacity', 0.15);

      const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
      circle.setAttribute('class', 'node-circle');
      circle.setAttribute('r', 6 + Math.sqrt(node.degree || 0) * 2.2);
      circle.setAttribute('fill', colors[node.kind]);
      circle.setAttribute('stroke', '#ffffff');
      circle.setAttribute('stroke-width', 1.5);
      circle.setAttribute('stroke-opacity', 0.85);

      const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      text.setAttribute('class', 'node-label');
      text.setAttribute('dy', 18 + Math.sqrt(node.degree || 0) * 2.5);
      text.textContent = node.label;

      g.appendChild(glow);
      g.appendChild(circle);
      g.appendChild(text);
      nodesGroup.appendChild(g);

      g.addEventListener('click', (e) => {
        e.stopPropagation();
        selectNode(node);
      });

      g.addEventListener('mouseover', () => hoverNode(node));
      g.addEventListener('mouseout', () => unhoverNode());

      let isDragging = false;
      g.addEventListener('mousedown', (e) => {
        isDragging = true;
        node.isFixed = true;
        e.stopPropagation();
      });

      window.addEventListener('mousemove', (e) => {
        if (!isDragging) return;
        const rect = svgEl.getBoundingClientRect();
        const screenX = e.clientX - rect.left;
        const screenY = e.clientY - rect.top;
        node.x = (screenX - zoomTx) / zoomScale;
        node.y = (screenY - zoomTy) / zoomScale;
      });

      window.addEventListener('mouseup', () => {
        if (isDragging) {
          isDragging = false;
          if (!isPaused) {
            node.isFixed = false;
          }
        }
      });

      return { node, container: g, circle, glow, text };
    });

    let isPanning = false;
    let startX, startY;

    svgEl.addEventListener('mousedown', (e) => {
      isPanning = true;
      startX = e.clientX - zoomTx;
      startY = e.clientY - zoomTy;
    });

    window.addEventListener('mousemove', (e) => {
      if (!isPanning) return;
      zoomTx = e.clientX - startX;
      zoomTy = e.clientY - startY;
      applyZoomTransform();
    });

    window.addEventListener('mouseup', () => {
      isPanning = false;
    });

    svgEl.addEventListener('wheel', (e) => {
      e.preventDefault();
      const zoomFactor = 1.1;
      const rect = svgEl.getBoundingClientRect();
      const mouseX = e.clientX - rect.left;
      const mouseY = e.clientY - rect.top;

      const graphX = (mouseX - zoomTx) / zoomScale;
      const graphY = (mouseY - zoomTy) / zoomScale;

      if (e.deltaY < 0) {
        zoomScale = Math.min(zoomScale * zoomFactor, 8);
      } else {
        zoomScale = Math.max(zoomScale / zoomFactor, 0.1);
      }

      zoomTx = mouseX - graphX * zoomScale;
      zoomTy = mouseY - graphY * zoomScale;

      applyZoomTransform();
    });

    document.getElementById('zoom-in').addEventListener('click', () => {
      zoomScale = Math.min(zoomScale * 1.3, 8);
      applyZoomTransform();
    });

    document.getElementById('zoom-out').addEventListener('click', () => {
      zoomScale = Math.max(zoomScale / 1.3, 0.1);
      applyZoomTransform();
    });

    document.getElementById('zoom-reset').addEventListener('click', () => {
      zoomScale = 1;
      zoomTx = 0;
      zoomTy = 0;
      applyZoomTransform();
    });

    function applyZoomTransform() {
      zoomGroupEl.setAttribute('transform', `translate(${zoomTx}, ${zoomTy}) scale(${zoomScale})`);
    }

    let restLength = 80;
    let gravityStrength = 800;

    document.getElementById('slide-distance').addEventListener('input', function() {
      restLength = +this.value;
      document.getElementById('val-distance').textContent = restLength;
    });

    document.getElementById('slide-charge').addEventListener('input', function() {
      gravityStrength = +this.value;
      document.getElementById('val-charge').textContent = gravityStrength;
    });

    document.getElementById('btn-pause').addEventListener('click', function() {
      isPaused = !isPaused;
      this.textContent = isPaused ? 'Resume Simulation' : 'Pause Simulation';
      if (!isPaused) {
        nodes.forEach(n => { n.isFixed = false; });
      } else {
        nodes.forEach(n => { n.isFixed = true; });
      }
    });

    function tickPhysics() {
      if (isPaused) return;

      const k_repulsion = gravityStrength;
      const k_attraction = 0.06;
      const center_gravity = 0.015;
      const damping = 0.82;

      for (let i = 0; i < nodes.length; i++) {
        const u = nodes[i];
        if (!activeKinds.has(u.kind)) continue;
        for (let j = i + 1; j < nodes.length; j++) {
          const v = nodes[j];
          if (!activeKinds.has(v.kind)) continue;

          let dx = v.x - u.x;
          let dy = v.y - u.y;
          if (dx === 0) dx = 0.1;
          const dist = Math.sqrt(dx*dx + dy*dy) || 0.1;

          const force = k_repulsion / (dist * dist);
          const fx = (dx / dist) * force;
          const fy = (dy / dist) * force;

          u.vx -= fx;
          u.vy -= fy;
          v.vx += fx;
          v.vy += fy;
        }
      }

      edges.forEach(edge => {
        const sourceNode = nodeMap[edge.source];
        const targetNode = nodeMap[edge.target];
        if (!sourceNode || !targetNode) return;
        if (!activeKinds.has(sourceNode.kind) || !activeKinds.has(targetNode.kind)) return;

        const dx = targetNode.x - sourceNode.x;
        const dy = targetNode.y - sourceNode.y;
        const dist = Math.sqrt(dx*dx + dy*dy) || 0.1;

        const force = k_attraction * (dist - restLength);
        const fx = (dx / dist) * force;
        const fy = (dy / dist) * force;

        sourceNode.vx += fx;
        sourceNode.vy += fy;
        targetNode.vx -= fx;
        targetNode.vy -= fy;
      });

      nodes.forEach(node => {
        if (node.isFixed || !activeKinds.has(node.kind)) return;

        node.vx += (width / 2 - node.x) * center_gravity;
        node.vy += (height / 2 - node.y) * center_gravity;

        node.vx *= damping;
        node.vy *= damping;

        node.x += node.vx;
        node.y += node.vy;
      });
    }

    function frame() {
      tickPhysics();
      renderTick();
      requestAnimationFrame(frame);
    }

    function renderTick() {
      nodeDOMs.forEach(d => {
        d.container.setAttribute('transform', `translate(${d.node.x}, ${d.node.y})`);
      });

      linkDOMs.forEach(d => {
        const s = nodeMap[d.edge.source];
        const t = nodeMap[d.edge.target];
        if (!s || !t) return;

        d.line.setAttribute('x1', s.x);
        d.line.setAttribute('y1', s.y);
        d.line.setAttribute('x2', t.x);
        d.line.setAttribute('y2', t.y);

        d.overlay.setAttribute('x1', s.x);
        d.overlay.setAttribute('y1', s.y);
        d.overlay.setAttribute('x2', t.x);
        d.overlay.setAttribute('y2', t.y);
      });
    }

    requestAnimationFrame(frame);

    window.addEventListener('resize', () => {
      width = canvasContainer.clientWidth;
      height = canvasContainer.clientHeight;
    });

    function getEdgeColor(evidence) {
      if (evidence === 'INFERRED') return '#c084fc';
      if (evidence === 'AMBIGUOUS') return '#fb923c';
      return '#3b82f6';
    }

    function getEdgeStrokeDash(evidence) {
      if (evidence === 'INFERRED') return '4, 4';
      if (evidence === 'AMBIGUOUS') return '2, 3';
      return null;
    }

    function hoverNode(targetNode) {
      if (selectedNodeId || selectedEdgeId || activeCommunityId) return;

      nodeDOMs.forEach(d => {
        const connected = areConnected(targetNode.id, d.node.id);
        d.container.style.opacity = connected ? 1.0 : 0.12;
      });

      linkDOMs.forEach(d => {
        const connected = d.edge.source === targetNode.id || d.edge.target === targetNode.id;
        d.line.style.opacity = connected ? 0.9 : 0.04;
      });
    }

    function unhoverNode() {
      if (selectedNodeId || selectedEdgeId || activeCommunityId) return;

      nodeDOMs.forEach(d => { d.container.style.opacity = 1.0; });
      linkDOMs.forEach(d => { d.line.style.opacity = 0.4 * (d.edge.confidence_score || 1); });
    }

    function selectNode(d) {
      selectedNodeId = d.id;
      selectedEdgeId = null;

      nodeDOMs.forEach(dom => {
        const isSelf = dom.node.id === d.id;
        dom.circle.style.stroke = '#ffffff';
        dom.circle.style.strokeWidth = isSelf ? '3' : '1.5';
        dom.circle.style.filter = isSelf ? `drop-shadow(0 0 8px ${colors[dom.node.kind]})` : 'none';
        dom.container.style.opacity = areConnected(d.id, dom.node.id) ? 1.0 : 0.12;
      });

      linkDOMs.forEach(dom => {
        const connected = dom.edge.source === d.id || dom.edge.target === d.id;
        dom.line.style.opacity = connected ? 0.9 : 0.04;
      });

      zoomScale = 1.4;
      zoomTx = width / 2 - d.x * zoomScale;
      zoomTy = height / 2 - d.y * zoomScale;
      applyZoomTransform();

      renderNodeDetails(d);
    }

    function selectEdge(edge) {
      selectedEdgeId = edge.id;
      selectedNodeId = null;

      linkDOMs.forEach(dom => {
        const isSelf = dom.edge.id === edge.id;
        dom.line.setAttribute('stroke', isSelf ? '#ffffff' : getEdgeColor(dom.edge.evidence));
        dom.line.setAttribute('marker-end', isSelf ? 'url(#arrow-highlighted)' : `url(#arrow-${dom.edge.evidence.toLowerCase()})`);
        dom.line.style.opacity = isSelf ? 1.0 : 0.04;
      });

      nodeDOMs.forEach(dom => {
        const linked = dom.node.id === edge.source || dom.node.id === edge.target;
        dom.container.style.opacity = linked ? 1.0 : 0.12;
      });

      renderEdgeDetails(edge);
    }

    function clearSelection() {
      selectedNodeId = null;
      selectedEdgeId = null;

      nodeDOMs.forEach(dom => {
        dom.circle.style.stroke = '#ffffff';
        dom.circle.style.strokeWidth = '1.5';
        dom.circle.style.filter = 'none';
        dom.container.style.opacity = 1.0;
      });

      linkDOMs.forEach(dom => {
        dom.line.setAttribute('stroke', getEdgeColor(dom.edge.evidence));
        dom.line.setAttribute('marker-end', `url(#arrow-${dom.edge.evidence.toLowerCase()})`);
        dom.line.style.opacity = 0.4 * (dom.edge.confidence_score || 1);
      });

      if (activeCommunityId) {
        highlightCommunity(communities.find(c => c.community_id === activeCommunityId));
      } else {
        initDefaultRightSidebar();
      }
    }

    svgEl.addEventListener('click', (e) => {
      if (e.target === svgEl || e.target === zoomGroupEl) {
        clearSelection();
      }
    });

    function highlightCommunity(community) {
      activeCommunityId = community.community_id;

      nodeDOMs.forEach(dom => {
        dom.container.style.opacity = dom.node.community_id === community.community_id ? 1.0 : 0.12;
      });

      linkDOMs.forEach(dom => {
        const s = nodeMap[dom.edge.source];
        const t = nodeMap[dom.edge.target];
        const inComm = s.community_id === community.community_id && t.community_id === community.community_id;
        dom.line.style.opacity = inComm ? 0.8 : 0.04;
      });

      document.querySelectorAll('.community-item').forEach(el => {
        el.classList.toggle('active', el.dataset.id === community.community_id);
      });

      renderCommunityDetails(community);
    }

    function clearCommunityHighlight() {
      activeCommunityId = null;
      document.querySelectorAll('.community-item').forEach(el => el.classList.remove('active'));
      clearSelection();
    }

    function initFilters() {
      const counts = {};
      nodes.forEach(n => { counts[n.kind] = (counts[n.kind] || 0) + 1; });

      const container = document.getElementById('type-filters');
      Object.keys(colors).forEach(kind => {
        if (!counts[kind]) return;
        const div = document.createElement('div');
        div.className = 'filter-item';
        div.innerHTML = `
          <div class="filter-checkbox-wrapper">
            <input type="checkbox" id="chk-${escapeAttr(kind)}" checked>
            <span class="color-dot" style="background-color: ${colorForKind(kind)}"></span>
            <span>${escapeHtml(kind)}</span>
          </div>
          <span class="count-badge">${counts[kind]}</span>
        `;

        div.querySelector('input').addEventListener('change', function() {
          if (this.checked) {
            activeKinds.add(kind);
          } else {
            activeKinds.delete(kind);
          }
          applyVisibilityFilters();
        });

        container.appendChild(div);
      });
    }

    function applyVisibilityFilters() {
      nodeDOMs.forEach(dom => {
        dom.container.style.display = activeKinds.has(dom.node.kind) ? 'inline' : 'none';
      });

      linkDOMs.forEach(dom => {
        const s = nodeMap[dom.edge.source];
        const t = nodeMap[dom.edge.target];
        const visible = activeKinds.has(s.kind) && activeKinds.has(t.kind);
        dom.container.style.display = visible ? 'inline' : 'none';
      });
    }

    function initCommunities() {
      const list = document.getElementById('community-list');
      communities.forEach(c => {
        const item = document.createElement('div');
        item.className = 'community-item';
        item.dataset.id = c.community_id;
        item.innerHTML = `
          <div class="community-item-header">
            <span>${escapeHtml(c.label)}</span>
            <span class="count-badge" style="background: rgba(20, 184, 166, 0.15); color: #2dd4bf;">${c.node_ids.length} nodes</span>
          </div>
          <div class="community-item-desc">${escapeHtml(c.summary)}</div>
        `;
        item.addEventListener('click', (e) => {
          e.stopPropagation();
          if (activeCommunityId === c.community_id) {
            clearCommunityHighlight();
          } else {
            highlightCommunity(c);
          }
        });
        list.appendChild(item);
      });
    }

    function initSearch() {
      const input = document.getElementById('search-input');
      const results = document.getElementById('search-results');

      input.addEventListener('input', () => {
        const val = input.value.trim().toLowerCase();
        if (!val) {
          results.style.display = 'none';
          return;
        }

        const filtered = nodes.filter(n => n.label.toLowerCase().includes(val)).slice(0, 10);
        if (filtered.length === 0) {
          results.innerHTML = '<div style="padding: 10px; font-size:12px; color:var(--text-muted);">No match found</div>';
        } else {
          results.innerHTML = filtered.map(n => `
            <div class="search-item" data-id="${escapeAttr(n.id)}">
              <span>${escapeHtml(n.label)}</span>
              <span class="kind-badge" style="color: ${colorForKind(n.kind)}">${escapeHtml(n.kind)}</span>
            </div>
          `).join('');

          results.querySelectorAll('.search-item').forEach(el => {
            el.addEventListener('click', () => {
              const node = nodes.find(n => n.id === el.dataset.id);
              if (node) {
                selectNode(node);
                input.value = node.label;
              }
              results.style.display = 'none';
            });
          });
        }
        results.style.display = 'block';
      });

      document.addEventListener('click', (e) => {
        if (e.target !== input) results.style.display = 'none';
      });
    }

    function initDefaultRightSidebar() {
      document.getElementById('details-placeholder').style.display = 'flex';
      const content = document.getElementById('details-content');
      content.style.display = 'none';

      let auditHtml = '';
      if (auditFindings && auditFindings.length > 0) {
        auditHtml = `
          <div class="audit-findings-title">Audit Findings (${auditFindings.length})</div>
          <div class="audit-list">
            ${auditFindings.map(f => `
              <div class="audit-item ${escapeAttr(f.severity)}">
                <div class="audit-header">
                  <span>${escapeHtml(f.code)}</span>
                  <span class="badge" style="background:transparent; border:none; padding:0; color:inherit; font-size:10px;">${escapeHtml(f.severity)}</span>
                </div>
                <div class="audit-desc">${escapeHtml(f.message)}</div>
                ${f.source_ref ? `<div style="font-size:10px; color:var(--text-muted); margin-top:4px; font-family:monospace;">Ref: ${escapeHtml(f.source_ref)}</div>` : ''}
              </div>
            `).join('')}
          </div>
        `;
      } else {
        auditHtml = `
          <div class="audit-findings-title">Audit Findings</div>
          <p style="font-size:12px; color:var(--text-muted);">No audit concerns detected.</p>
        `;
      }

      content.innerHTML = `
        <div class="details-header">
          <div class="details-title">System Overview</div>
          <div class="details-subtitle">Graphify Report Summary</div>
        </div>
        <div class="detail-card">
          <div class="detail-card-title">Analysis details</div>
          <div style="display:flex; flex-direction:column; gap:4px; font-size:12px;">
            <div>Algorithm: <span class="badge-layer">${escapeHtml(rawData.algorithm_version || 'graphify-v1')}</span></div>
            <div>Generated: <span style="color:var(--text-muted); font-family:monospace;">${escapeHtml(rawData.generated_at ? new Date(rawData.generated_at).toLocaleString() : 'N/A')}</span></div>
          </div>
        </div>
        ${auditHtml}
      `;
      content.style.display = 'block';
      document.getElementById('details-placeholder').style.display = 'none';
    }

    function renderNodeDetails(d) {
      const content = document.getElementById('details-content');
      content.style.display = 'block';
      document.getElementById('details-placeholder').style.display = 'none';

      const prov = d.provenance || {};
      const neighbors = edges.filter(e => e.source === d.id || e.target === d.id).map(e => {
        const isOut = e.source === d.id;
        const targetId = isOut ? e.target : e.source;
        const targetNode = nodeMap[targetId];
        return {
          id: targetId,
          label: targetNode ? targetNode.label : targetId,
          relation: e.relation,
          isOutgoing: isOut
        };
      });

      let neighborsHtml = '<p style="font-size:12px; color:var(--text-muted);">No connections</p>';
      if (neighbors.length > 0) {
        neighborsHtml = `
          <div style="display:flex; flex-direction:column; gap:6px;">
            ${neighbors.map(n => `
              <div style="display:flex; justify-content:space-between; align-items:center; background:rgba(255,255,255,0.02); padding:6px 10px; border-radius:4px; border:1px solid var(--border-color); font-size:12px;">
                <a href="#" class="node-link" data-node-id="${escapeAttr(n.id)}" style="color:#60a5fa; text-decoration:none; font-weight:500;">${escapeHtml(n.label)}</a>
                <span style="font-size:10px; color:var(--text-muted); font-family:monospace;">
                  ${n.isOutgoing ? '➔ ' + escapeHtml(n.relation) : '⇠ ' + escapeHtml(n.relation)}
                </span>
              </div>
            `).join('')}
          </div>
        `;
      }

      content.innerHTML = `
        <div class="details-header">
          <div class="details-title">${escapeHtml(d.label)}</div>
          <div class="details-subtitle">
            <span class="badge-kind" style="background-color: ${colorForKind(d.kind)}">${escapeHtml(d.kind)}</span>
            <span class="badge-layer">Layer: ${escapeHtml(d.source_layer)}</span>
          </div>
        </div>

        <div class="detail-card">
          <div class="detail-card-title">Node Metadata</div>
          <div style="display:flex; flex-direction:column; gap:8px;">
            <div><span style="color:var(--text-muted);">ID:</span> <span style="font-family:monospace; font-size:11px;">${escapeHtml(d.id)}</span></div>
            <div><span style="color:var(--text-muted);">Source Reference:</span> <span style="font-family:monospace; font-size:11px; color:#a78bfa;">${escapeHtml(d.source_ref)}</span></div>
            ${d.community_id ? `<div><span style="color:var(--text-muted);">Community ID:</span> <span class="badge-layer">${escapeHtml(d.community_id)}</span></div>` : ''}
          </div>
        </div>

        <div class="detail-card">
          <div class="detail-card-title">Provenance</div>
          <div style="display:flex; flex-direction:column; gap:8px; font-size:12px;">
            <div><span style="color:var(--text-muted);">Source Relpath:</span> <span style="color:#2dd4bf; font-family:monospace;">${escapeHtml(prov.source_relpath || 'N/A')}</span></div>
            <div><span style="color:var(--text-muted);">Wiki Page:</span> <span style="color:#60a5fa; font-family:monospace;">${escapeHtml(prov.wiki_page || 'N/A')}</span></div>
            <div><span style="color:var(--text-muted);">Artifact ID:</span> <span style="font-family:monospace; font-size:10px;">${escapeHtml(prov.artifact_id || 'N/A')}</span></div>
          </div>
        </div>

        <div>
          <div class="section-title">Relationships (${neighbors.length})</div>
          ${neighborsHtml}
        </div>
      `;
      bindNodeLinks(content);
    }

    function renderEdgeDetails(edge) {
      const content = document.getElementById('details-content');
      content.style.display = 'block';
      document.getElementById('details-placeholder').style.display = 'none';

      const sNode = nodeMap[edge.source];
      const tNode = nodeMap[edge.target];

      content.innerHTML = `
        <div class="details-header">
          <div class="details-title">Relationship Details</div>
          <div class="details-subtitle">
            <span class="badge-relation">${escapeHtml(edge.relation)}</span>
            <span class="badge-layer">Layer: ${escapeHtml(edge.source_layer)}</span>
          </div>
        </div>

        <div class="detail-card" style="display:flex; flex-direction:column; gap:8px;">
          <div><span style="color:var(--text-muted);">Source:</span> <a href="#" class="node-link" data-node-id="${escapeAttr(edge.source)}" style="color:#60a5fa; text-decoration:none; font-weight:500; font-family:sans-serif; margin-left:6px;">${escapeHtml(sNode ? sNode.label : edge.source)}</a></div>
          <div style="padding-left:12px; color:var(--text-muted); font-size:10px;">ID: ${escapeHtml(edge.source)}</div>

          <div style="margin-top:6px;"><span style="color:var(--text-muted);">Target:</span> <a href="#" class="node-link" data-node-id="${escapeAttr(edge.target)}" style="color:#60a5fa; text-decoration:none; font-weight:500; font-family:sans-serif; margin-left:6px;">${escapeHtml(tNode ? tNode.label : edge.target)}</a></div>
          <div style="padding-left:12px; color:var(--text-muted); font-size:10px;">ID: ${escapeHtml(edge.target)}</div>
        </div>

        <div class="detail-card">
          <div class="detail-card-title">Reliability</div>
          <div style="display:flex; flex-direction:column; gap:8px;">
            <div><span style="color:var(--text-muted);">Evidence Type:</span> <span style="font-weight:600; color:${getEdgeColor(edge.evidence)};">${escapeHtml(edge.evidence)}</span></div>
            <div><span style="color:var(--text-muted);">Confidence Score:</span> <span style="font-weight:700; font-family:monospace; color:#fff;">${formatScore(edge.confidence_score)}</span></div>
            <div><span style="color:var(--text-muted);">Weight:</span> <span style="font-weight:700; font-family:monospace; color:#fff;">${formatScore(edge.weight)}</span></div>
          </div>
        </div>

        ${edge.rationale ? `
          <div class="detail-card">
            <div class="detail-card-title">Rationale</div>
            <div style="line-height:1.5; color:#d4d4d8; font-size:12px;">${escapeHtml(edge.rationale)}</div>
          </div>
        ` : ''}
      `;
      bindNodeLinks(content);
    }

    function renderCommunityDetails(c) {
      const content = document.getElementById('details-content');
      content.style.display = 'block';
      document.getElementById('details-placeholder').style.display = 'none';

      const commNodes = nodes.filter(n => n.community_id === c.community_id);

      content.innerHTML = `
        <div class="details-header">
          <div class="details-title">${escapeHtml(c.label)}</div>
          <div class="details-subtitle">
            <span class="badge-kind" style="background-color: var(--color-community)">Community</span>
            <span class="badge-layer">Confidence: ${formatScore(c.confidence_score)}</span>
          </div>
        </div>

        <div class="detail-card">
          <div class="detail-card-title">Summary</div>
          <div style="line-height:1.5; font-size:12px; color:#d4d4d8;">${escapeHtml(c.summary)}</div>
        </div>

        <div>
          <div class="section-title">Members (${commNodes.length})</div>
          <div style="display:flex; flex-direction:column; gap:6px; max-height:240px; overflow-y:auto; padding-right:4px;">
            ${commNodes.map(n => `
              <div style="display:flex; justify-content:space-between; align-items:center; background:rgba(255,255,255,0.02); padding:6px 10px; border-radius:4px; border:1px solid var(--border-color); font-size:12px;">
                <a href="#" class="node-link" data-node-id="${escapeAttr(n.id)}" style="color:#60a5fa; text-decoration:none; font-weight:500;">${escapeHtml(n.label)}</a>
                <span class="count-badge" style="color:${colorForKind(n.kind)}">${escapeHtml(n.kind)}</span>
              </div>
            `).join('')}
          </div>
        </div>
      `;
      bindNodeLinks(content);
    }

    function selectNodeById(id) {
      const node = nodes.find(n => n.id === id);
      if (node) {
        selectNode(node);
      }
    }
    window.selectNodeById = selectNodeById;
  </script>
</body>
</html>
"""
    return html_content



def render_report(graph: GraphifyGraph) -> str:
    evidence_counts = {"EXTRACTED": 0, "INFERRED": 0, "AMBIGUOUS": 0}
    for edge in graph.edges:
        evidence_counts[edge.evidence] += 1
    lines = [
        "# GRAPH_REPORT",
        "",
        f"- Nodes: {len(graph.nodes)}",
        f"- Edges: {len(graph.edges)}",
        f"- Communities: {len(graph.communities)}",
        f"- EXTRACTED edges: {evidence_counts['EXTRACTED']}",
        f"- INFERRED edges: {evidence_counts['INFERRED']}",
        f"- AMBIGUOUS edges: {evidence_counts['AMBIGUOUS']}",
        "",
        "## Communities",
        "",
    ]
    for community in graph.communities:
        lines.append(
            f"- {community.community_id}: {community.label} "
            f"({len(community.node_ids)} nodes, confidence {community.confidence_score:.2f})"
        )
    lines.extend(["", "## Audit Findings", ""])
    if not graph.audit_findings:
        lines.append("- none")
    for finding in graph.audit_findings:
        lines.append(f"- {finding.severity}: {finding.code} - {finding.message}")
    return "\n".join(lines) + "\n"
