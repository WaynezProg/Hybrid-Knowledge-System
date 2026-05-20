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
<html lang="zh-Hant">
<head>
  <meta charset="utf-8">
  <title>Graphify Explorer · HKS</title>
  <style>
    :root {
      --bg-color: #1a1618;
      --bg-elev: #221d20;
      --panel-bg: rgba(34, 29, 32, 0.84);
      --panel-solid: #25201f;
      --input-bg: #2c2528;
      --border-color: #38312f;
      --border-strong: #4a4140;
      --text-main: #ece5ea;
      --text-muted: #9a8e93;
      --text-dim: #6d6166;
      --accent-color: #b794f6;
      --accent-bright: #c4a6ff;
      --accent-soft: rgba(183, 148, 246, 0.1);
      --accent-glow: rgba(183, 148, 246, 0.2);
      --amber: #d6a85e;
      --rose: #f0788a;
      --teal: #7dd3fc;
      --mint: #86efac;
      --gold: #fcd34d;

      --color-source: #7dd3fc;
      --color-wiki: #86efac;
      --color-entity: #b794f6;
      --color-concept: #fcd34d;
      --color-artifact: #f0788a;
      --color-community: #c4a6ff;
      --sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, "PingFang TC", "Microsoft JhengHei", sans-serif;
      --mono: "SFMono-Regular", "SF Mono", Menlo, Consolas, ui-monospace, monospace;
      --serif: Georgia, "Times New Roman", "Songti TC", serif;
    }

    * {
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }

    body {
      font-family: var(--sans);
      background-color: var(--bg-color);
      color: var(--text-main);
      width: 100vw;
      height: 100vh;
      overflow: hidden;
      display: flex;
      flex-direction: column;
      line-height: 1.55;
      -webkit-font-smoothing: antialiased;
    }

    .bg-grid {
      position: absolute;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
      background-image:
        radial-gradient(1200px 700px at 60% 45%, rgba(183, 148, 246, 0.045), transparent 70%),
        radial-gradient(800px 500px at 20% 85%, rgba(125, 211, 252, 0.025), transparent 70%),
        linear-gradient(to right, rgba(255, 255, 255, 0.018) 1px, transparent 1px),
        linear-gradient(to bottom, rgba(255, 255, 255, 0.018) 1px, transparent 1px);
      background-size: 100% 100%, 100% 100%, 32px 32px, 32px 32px;
      pointer-events: none;
      z-index: 1;
    }

    /* Navbar */
    header {
      height: 48px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      padding: 0 16px;
      border-bottom: 1px solid var(--border-color);
      background: var(--bg-elev);
      z-index: 100;
      font-family: var(--mono);
      font-size: 12px;
      color: var(--text-muted);
      user-select: none;
    }

    .logo-section {
      display: flex;
      align-items: center;
      gap: 10px;
      min-width: 0;
    }

    .brand-glyph {
      width: 16px;
      height: 16px;
      display: inline-block;
      background: radial-gradient(circle at 30% 30%, var(--accent-bright), var(--accent-color) 60%, transparent 70%);
      border-radius: 50%;
      box-shadow: 0 0 12px var(--accent-glow);
    }

    .logo-section h1 {
      color: var(--text-main);
      font-family: var(--serif);
      font-size: 17px;
      font-weight: 600;
      letter-spacing: 0;
      white-space: nowrap;
    }

    .badge {
      background: var(--accent-soft);
      border: 1px solid rgba(183, 148, 246, 0.32);
      color: var(--accent-bright);
      font-size: 11px;
      padding: 2px 8px;
      border-radius: 9999px;
      font-weight: 500;
    }

    .stats-container {
      display: flex;
      gap: 14px;
      margin-left: auto;
    }

    .stat-card {
      background: transparent;
      border: none;
      padding: 0;
      border-radius: 0;
      display: flex;
      align-items: center;
      gap: 4px;
      font-size: 12px;
    }

    .stat-card .val {
      font-weight: 500;
      color: var(--text-main);
    }

    .stat-card .lbl {
      color: var(--text-dim);
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
      position: absolute;
      top: 16px;
      left: 16px;
      width: 304px;
      max-height: calc(100% - 88px);
      background: var(--panel-bg);
      backdrop-filter: blur(10px);
      border: 1px solid var(--border-color);
      border-radius: 12px;
      display: flex;
      flex-direction: column;
      gap: 18px;
      padding: 16px;
      overflow-y: auto;
      z-index: 50;
      box-shadow: 0 18px 45px rgba(0, 0, 0, 0.2);
    }

    /* Right Sidebar: Details */
    .sidebar-right {
      width: 420px;
      height: 100%;
      background: var(--bg-elev);
      border-left: 1px solid var(--border-color);
      display: flex;
      flex-direction: column;
      padding: 18px 22px 40px;
      overflow-y: auto;
      z-index: 50;
    }

    /* Canvas */
    .canvas-container {
      flex: 1;
      height: 100%;
      position: relative;
      background:
        radial-gradient(900px 520px at 58% 42%, rgba(183, 148, 246, 0.075), transparent 72%),
        radial-gradient(560px 420px at 18% 82%, rgba(125, 211, 252, 0.04), transparent 70%),
        var(--bg-color);
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
      font-family: var(--mono);
      font-size: 10px;
      font-weight: 500;
      text-transform: uppercase;
      letter-spacing: 0.14em;
      color: var(--text-dim);
      margin-bottom: 10px;
      display: flex;
      align-items: center;
      justify-content: space-between;
    }

    .search-wrapper {
      position: relative;
    }

    .search-input {
      width: 100%;
      background: var(--input-bg);
      border: 1px solid var(--border-color);
      color: var(--text-main);
      padding: 8px 12px;
      border-radius: 8px;
      font-family: var(--mono);
      font-size: 12px;
      outline: none;
      transition: all 0.2s;
    }

    .search-input:focus {
      border-color: var(--accent-color);
      background: rgba(44, 37, 40, 0.96);
      box-shadow: 0 0 0 1px var(--accent-glow);
    }

    .search-results {
      position: absolute;
      top: calc(100% + 4px);
      left: 0;
      right: 0;
      background: var(--bg-elev);
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
      background: rgba(255, 255, 255, 0.025);
      border: 1px solid var(--border-color);
      padding: 9px 10px;
      border-radius: 8px;
      cursor: pointer;
      font-size: 12px;
      transition: all 0.2s;
    }

    .community-item:hover, .community-item.active {
      background: var(--accent-soft);
      border-color: var(--border-strong);
    }

    .community-item-header {
      display: flex;
      justify-content: space-between;
      font-weight: 600;
      color: var(--text-main);
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
      background: var(--input-bg);
      border: 1px solid var(--border-color);
      color: var(--text-main);
      padding: 8px;
      border-radius: 6px;
      font-size: 12px;
      cursor: pointer;
      font-weight: 500;
      transition: all 0.2s;
    }

    .physics-btn:hover {
      background: var(--accent-soft);
      border-color: var(--border-strong);
      color: var(--accent-bright);
    }

    .perf-note {
      display: none;
      margin-top: 8px;
      padding: 8px 10px;
      border-radius: 8px;
      border: 1px solid rgba(214, 168, 94, 0.32);
      background: rgba(214, 168, 94, 0.08);
      color: var(--text-muted);
      font-size: 11px;
      line-height: 1.45;
    }

    .perf-note.is-visible {
      display: block;
    }

    /* Float controls */
    .float-controls {
      position: absolute;
      bottom: 24px;
      left: 24px;
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
      backdrop-filter: blur(10px);
      border: 1px solid var(--border-color);
      color: var(--text-muted);
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
      background: var(--accent-soft);
      border-color: var(--border-strong);
      color: var(--accent-bright);
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
      font-family: var(--serif);
      font-size: 22px;
      font-weight: 600;
      color: var(--text-main);
      word-break: break-word;
      margin-bottom: 6px;
    }

    .details-subtitle {
      font-family: var(--mono);
      font-size: 11px;
      color: var(--text-muted);
      text-transform: uppercase;
      letter-spacing: 0.08em;
      display: flex;
      align-items: center;
      gap: 6px;
    }

    .detail-card {
      background: var(--panel-solid);
      border: 1px solid var(--border-color);
      border-radius: 8px;
      padding: 12px;
      font-size: 13px;
    }

    .detail-card-title {
      font-family: var(--mono);
      font-size: 11px;
      text-transform: uppercase;
      color: var(--text-muted);
      margin-bottom: 6px;
      letter-spacing: 0.08em;
      font-weight: 500;
    }

    .detail-card-val {
      color: var(--text-main);
      word-break: break-all;
    }

    .badge-kind {
      padding: 2px 8px;
      border-radius: 999px;
      font-size: 11px;
      font-weight: 500;
      color: var(--bg-color);
      display: inline-block;
      font-family: var(--mono);
    }

    .badge-relation {
      background: var(--accent-soft);
      border: 1px solid rgba(183, 148, 246, 0.3);
      color: var(--accent-bright);
      padding: 2px 6px;
      border-radius: 999px;
      font-family: var(--mono);
    }

    .badge-layer {
      background: var(--input-bg);
      color: var(--text-muted);
      border: 1px solid var(--border-color);
      padding: 1px 6px;
      border-radius: 999px;
      font-size: 11px;
      font-family: var(--mono);
    }

    .audit-findings-title {
      font-family: var(--mono);
      font-size: 11px;
      font-weight: 500;
      margin-bottom: 12px;
      color: var(--text-dim);
      border-bottom: 1px solid var(--border-color);
      padding-bottom: 6px;
      text-transform: uppercase;
      letter-spacing: 0.12em;
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
      background: var(--panel-solid);
    }

    .audit-item.error {
      background: rgba(240, 120, 138, 0.08);
      border-color: rgba(240, 120, 138, 0.25);
    }

    .audit-item.warning {
      background: rgba(214, 168, 94, 0.08);
      border-color: rgba(214, 168, 94, 0.25);
    }

    .audit-item.info {
      background: rgba(125, 211, 252, 0.08);
      border-color: rgba(125, 211, 252, 0.25);
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
      fill: var(--text-muted);
      pointer-events: none;
      text-anchor: middle;
      font-weight: 500;
      paint-order: stroke;
      stroke: var(--bg-color);
      stroke-width: 3px;
      stroke-linejoin: round;
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

    .status-line {
      position: absolute;
      bottom: 24px;
      right: 24px;
      max-width: calc(100% - 120px);
      background: var(--panel-bg);
      backdrop-filter: blur(10px);
      border: 1px solid var(--border-color);
      border-radius: 8px;
      color: var(--text-dim);
      font-family: var(--mono);
      font-size: 11px;
      padding: 6px 10px;
      z-index: 40;
      pointer-events: none;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .status-line b {
      color: var(--text-muted);
      font-weight: 500;
    }

    /* Scrollbar */
    ::-webkit-scrollbar {
      width: 10px;
    }
    ::-webkit-scrollbar-track {
      background: transparent;
    }
    ::-webkit-scrollbar-thumb {
      background: var(--border-color);
      border-radius: 5px;
    }
    ::-webkit-scrollbar-thumb:hover {
      background: var(--border-strong);
    }
  </style>
</head>
<body>
  <div class="bg-grid"></div>

  <header>
    <div class="logo-section">
      <span class="brand-glyph"></span>
      <h1>Graphify Explorer</h1>
      <span class="badge">v1.0.0-interactive</span>
    </div>

    <div class="stats-container">
      <div class="stat-card">
        <span class="val" id="stats-nodes">0</span>
        <span class="lbl">節點</span>
      </div>
      <div class="stat-card">
        <span class="val" id="stats-edges">0</span>
        <span class="lbl">關係</span>
      </div>
      <div class="stat-card">
        <span class="val" id="stats-communities">0</span>
        <span class="lbl">社群</span>
      </div>
    </div>
  </header>

  <main>
    <div class="sidebar-left">
      <div>
        <div class="section-title">搜尋圖譜</div>
        <div class="search-wrapper">
          <input type="text" class="search-input" id="search-input" placeholder="輸入節點名稱..." autocomplete="off">
          <div class="search-results" id="search-results"></div>
        </div>
      </div>

      <div>
        <div class="section-title">節點類型</div>
        <div class="filter-list" id="type-filters"></div>
      </div>

      <div>
        <div class="section-title">力學設定</div>
        <div class="slider-group">
          <div class="slider-header">
            <span>連線距離</span>
            <span id="val-distance">80</span>
          </div>
          <input type="range" id="slide-distance" min="40" max="250" value="80">
        </div>
        <div class="slider-group">
          <div class="slider-header">
            <span>重力強度</span>
            <span id="val-charge">800</span>
          </div>
          <input type="range" id="slide-charge" min="100" max="2000" value="800">
        </div>
        <button class="physics-btn" id="btn-pause">暫停模擬</button>
        <div class="perf-note" id="perf-note">
          節點數超過 500，已自動暫停力學模擬。可先搜尋或篩選，再手動恢復。
        </div>
      </div>

      <div>
        <div class="section-title">社群</div>
        <div class="community-list" id="community-list"></div>
      </div>
    </div>

    <!-- Canvas -->
    <div class="canvas-container" id="canvas-container">
      <svg id="graph-svg">
        <defs>
          <!-- Markers for arrowheads -->
          <marker id="arrow-extracted" viewBox="0 -5 10 10" refX="22" refY="0" markerWidth="6" markerHeight="6" orient="auto">
            <path d="M0,-5L10,0L0,5" fill="#7dd3fc" opacity="0.82"></path>
          </marker>
          <marker id="arrow-inferred" viewBox="0 -5 10 10" refX="22" refY="0" markerWidth="6" markerHeight="6" orient="auto">
            <path d="M0,-5L10,0L0,5" fill="#c4a6ff" opacity="0.82"></path>
          </marker>
          <marker id="arrow-ambiguous" viewBox="0 -5 10 10" refX="22" refY="0" markerWidth="6" markerHeight="6" orient="auto">
            <path d="M0,-5L10,0L0,5" fill="#d6a85e" opacity="0.82"></path>
          </marker>
          <marker id="arrow-highlighted" viewBox="0 -5 10 10" refX="22" refY="0" markerWidth="7" markerHeight="7" orient="auto">
            <path d="M0,-5L10,0L0,5" fill="#ece5ea"></path>
          </marker>
        </defs>
        <g id="zoom-group">
          <g id="links-group"></g>
          <g id="nodes-group"></g>
        </g>
      </svg>

      <div class="float-controls">
        <button class="float-btn" id="zoom-in" title="放大">+</button>
        <button class="float-btn" id="zoom-out" title="縮小">-</button>
        <button class="float-btn" id="zoom-reset" title="重設視角">⊙</button>
      </div>
      <div class="status-line" id="status-line">
        <b>拖曳</b>平移 · <b>滾輪</b>縮放 · <b>點選</b>節點或關係
      </div>
    </div>

    <!-- Right Sidebar -->
    <div class="sidebar-right" id="details-sidebar">
      <div class="details-placeholder" id="details-placeholder">
        <svg fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg" style="width:48px; height:48px; opacity:0.5; stroke:currentColor;">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path>
        </svg>
        <p>選取節點或關係以檢視細節</p>
      </div>
      <div class="details-content" id="details-content" style="display: none;"></div>
    </div>
  </main>

  <script type="application/json" id="graphify-data">""" + payload + """</script>

  <script>
    // Constants & config
    const colors = {
      source: '#7dd3fc',
      wiki_page: '#86efac',
      entity: '#b794f6',
      concept: '#fcd34d',
      artifact: '#f0788a',
      community: '#c4a6ff'
    };

    const kindLabels = {
      source: '來源',
      wiki_page: 'Wiki 頁面',
      entity: '實體',
      concept: '概念',
      artifact: '產物'
    };

    const evidenceLabels = {
      EXTRACTED: '原文擷取',
      INFERRED: '推論',
      AMBIGUOUS: '模糊'
    };

    const AUTO_PAUSE_NODE_LIMIT = 500;

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

    function labelForKind(kind) {
      return kindLabels[kind] || kind;
    }

    function labelForEvidence(evidence) {
      return evidenceLabels[evidence] || evidence;
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
    const autoPausedLargeGraph = nodes.length > AUTO_PAUSE_NODE_LIMIT;
    let isPaused = autoPausedLargeGraph;

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
    const statusLineEl = document.getElementById('status-line');
    const pauseButtonEl = document.getElementById('btn-pause');
    const perfNoteEl = document.getElementById('perf-note');

    let width = canvasContainer.clientWidth || 800;
    let height = canvasContainer.clientHeight || 600;

    nodes.forEach((n, idx) => {
      const angle = (idx / nodes.length) * 2 * Math.PI;
      const radius = 100 + Math.random() * 150;
      n.x = width / 2 + Math.cos(angle) * radius;
      n.y = height / 2 + Math.sin(angle) * radius;
    });

    if (autoPausedLargeGraph) {
      pauseButtonEl.textContent = '恢復模擬';
      perfNoteEl.classList.add('is-visible');
      nodes.forEach(n => { n.isFixed = true; });
      setStatusLine(`<b>效能保護</b> · ${nodes.length} 個節點超過 ${AUTO_PAUSE_NODE_LIMIT}，已自動暫停力學模擬`);
    }

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

    let dragTarget = null;

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
      circle.setAttribute('stroke', '#ece5ea');
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

      g.addEventListener('mousedown', (e) => {
        dragTarget = node;
        node.isFixed = true;
        e.stopPropagation();
      });

      return { node, container: g, circle, glow, text };
    });

    window.addEventListener('mousemove', (e) => {
      if (!dragTarget) return;
      const rect = svgEl.getBoundingClientRect();
      const screenX = e.clientX - rect.left;
      const screenY = e.clientY - rect.top;
      dragTarget.x = (screenX - zoomTx) / zoomScale;
      dragTarget.y = (screenY - zoomTy) / zoomScale;
    });

    window.addEventListener('mouseup', () => {
      if (dragTarget) {
        if (!isPaused) {
          dragTarget.isFixed = false;
        }
        dragTarget = null;
      }
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

    pauseButtonEl.addEventListener('click', function() {
      isPaused = !isPaused;
      this.textContent = isPaused ? '恢復模擬' : '暫停模擬';
      if (!isPaused) {
        nodes.forEach(n => { n.isFixed = false; });
        setStatusLine('<b>模擬中</b> · 力學模擬已恢復');
      } else {
        nodes.forEach(n => { n.isFixed = true; });
        setStatusLine('<b>已暫停</b> · 力學模擬已暫停');
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
      if (evidence === 'INFERRED') return '#c4a6ff';
      if (evidence === 'AMBIGUOUS') return '#d6a85e';
      return '#7dd3fc';
    }

    function getEdgeStrokeDash(evidence) {
      if (evidence === 'INFERRED') return '4, 4';
      if (evidence === 'AMBIGUOUS') return '2, 3';
      return null;
    }

    function setStatusLine(html) {
      statusLineEl.innerHTML = html;
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
      setStatusLine(`<b>停留</b> · ${escapeHtml(targetNode.id)} · ${escapeHtml(labelForKind(targetNode.kind))} · ${targetNode.degree} 個關聯`);
    }

    function unhoverNode() {
      if (selectedNodeId || selectedEdgeId || activeCommunityId) return;

      nodeDOMs.forEach(d => { d.container.style.opacity = 1.0; });
      linkDOMs.forEach(d => { d.line.style.opacity = 0.4 * (d.edge.confidence_score || 1); });
      setStatusLine('<b>拖曳</b>平移 · <b>滾輪</b>縮放 · <b>點選</b>節點或關係');
    }

    function selectNode(d) {
      selectedNodeId = d.id;
      selectedEdgeId = null;

      nodeDOMs.forEach(dom => {
        const isSelf = dom.node.id === d.id;
        dom.circle.style.stroke = '#ece5ea';
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
      setStatusLine(`<b>已選取</b> · ${escapeHtml(d.id)} · ${escapeHtml(labelForKind(d.kind))} · ${d.degree} 個關聯`);
    }

    function selectEdge(edge) {
      selectedEdgeId = edge.id;
      selectedNodeId = null;

      linkDOMs.forEach(dom => {
        const isSelf = dom.edge.id === edge.id;
        dom.line.setAttribute('stroke', isSelf ? '#ece5ea' : getEdgeColor(dom.edge.evidence));
        dom.line.setAttribute('marker-end', isSelf ? 'url(#arrow-highlighted)' : `url(#arrow-${dom.edge.evidence.toLowerCase()})`);
        dom.line.style.opacity = isSelf ? 1.0 : 0.04;
      });

      nodeDOMs.forEach(dom => {
        const linked = dom.node.id === edge.source || dom.node.id === edge.target;
        dom.container.style.opacity = linked ? 1.0 : 0.12;
      });

      renderEdgeDetails(edge);
      setStatusLine(`<b>關係</b> · ${escapeHtml(edge.source)} → ${escapeHtml(edge.target)} · ${escapeHtml(edge.relation)}`);
    }

    function clearSelection() {
      selectedNodeId = null;
      selectedEdgeId = null;

      nodeDOMs.forEach(dom => {
        dom.circle.style.stroke = '#ece5ea';
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
        setStatusLine('<b>拖曳</b>平移 · <b>滾輪</b>縮放 · <b>點選</b>節點或關係');
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
        const inComm = s && t && s.community_id === community.community_id && t.community_id === community.community_id;
        dom.line.style.opacity = inComm ? 0.8 : 0.04;
      });

      document.querySelectorAll('.community-item').forEach(el => {
        el.classList.toggle('active', el.dataset.id === community.community_id);
      });

      renderCommunityDetails(community);
      setStatusLine(`<b>社群</b> · ${escapeHtml(community.community_id)} · ${community.node_ids.length} 個節點`);
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
            <span>${escapeHtml(labelForKind(kind))}</span>
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
        const visible = s && t && activeKinds.has(s.kind) && activeKinds.has(t.kind);
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
            <span class="count-badge" style="background: rgba(183, 148, 246, 0.12); color: var(--accent-bright);">${c.node_ids.length} 節點</span>
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
          results.innerHTML = '<div style="padding: 10px; font-size:12px; color:var(--text-muted);">找不到符合的節點</div>';
        } else {
          results.innerHTML = filtered.map(n => `
            <div class="search-item" data-id="${escapeAttr(n.id)}">
              <span>${escapeHtml(n.label)}</span>
              <span class="kind-badge" style="color: ${colorForKind(n.kind)}">${escapeHtml(labelForKind(n.kind))}</span>
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
          <div class="audit-findings-title">稽核結果 (${auditFindings.length})</div>
          <div class="audit-list">
            ${auditFindings.map(f => `
              <div class="audit-item ${escapeAttr(f.severity)}">
                <div class="audit-header">
                  <span>${escapeHtml(f.code)}</span>
                  <span class="badge" style="background:transparent; border:none; padding:0; color:inherit; font-size:10px;">${escapeHtml(f.severity)}</span>
                </div>
                <div class="audit-desc">${escapeHtml(f.message)}</div>
                ${f.source_ref ? `<div style="font-size:10px; color:var(--text-muted); margin-top:4px; font-family:monospace;">來源: ${escapeHtml(f.source_ref)}</div>` : ''}
              </div>
            `).join('')}
          </div>
        `;
      } else {
        auditHtml = `
          <div class="audit-findings-title">稽核結果</div>
          <p style="font-size:12px; color:var(--text-muted);">未偵測到稽核疑慮。</p>
        `;
      }

      content.innerHTML = `
        <div class="details-header">
          <div class="details-title">系統總覽</div>
          <div class="details-subtitle">Graphify 報告摘要</div>
        </div>
        <div class="detail-card">
          <div class="detail-card-title">分析細節</div>
          <div style="display:flex; flex-direction:column; gap:4px; font-size:12px;">
            <div>演算法: <span class="badge-layer">${escapeHtml(rawData.algorithm_version || 'graphify-v1')}</span></div>
            <div>產生時間: <span style="color:var(--text-muted); font-family:monospace;">${escapeHtml(rawData.generated_at ? new Date(rawData.generated_at).toLocaleString('zh-TW') : '無')}</span></div>
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

      let neighborsHtml = '<p style="font-size:12px; color:var(--text-muted);">沒有關聯</p>';
      if (neighbors.length > 0) {
        neighborsHtml = `
          <div style="display:flex; flex-direction:column; gap:6px;">
            ${neighbors.map(n => `
              <div style="display:flex; justify-content:space-between; align-items:center; background:rgba(255,255,255,0.02); padding:6px 10px; border-radius:4px; border:1px solid var(--border-color); font-size:12px;">
                <a href="#" class="node-link" data-node-id="${escapeAttr(n.id)}" style="color:var(--accent-bright); text-decoration:none; font-weight:500;">${escapeHtml(n.label)}</a>
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
            <span class="badge-kind" style="background-color: ${colorForKind(d.kind)}">${escapeHtml(labelForKind(d.kind))}</span>
            <span class="badge-layer">層級: ${escapeHtml(d.source_layer)}</span>
          </div>
        </div>

        <div class="detail-card">
          <div class="detail-card-title">節點中繼資料</div>
          <div style="display:flex; flex-direction:column; gap:8px;">
            <div><span style="color:var(--text-muted);">ID:</span> <span style="font-family:monospace; font-size:11px;">${escapeHtml(d.id)}</span></div>
            <div><span style="color:var(--text-muted);">來源參照:</span> <span style="font-family:var(--mono); font-size:11px; color:var(--accent-bright);">${escapeHtml(d.source_ref)}</span></div>
            ${d.community_id ? `<div><span style="color:var(--text-muted);">社群 ID:</span> <span class="badge-layer">${escapeHtml(d.community_id)}</span></div>` : ''}
          </div>
        </div>

        <div class="detail-card">
          <div class="detail-card-title">來源脈絡</div>
          <div style="display:flex; flex-direction:column; gap:8px; font-size:12px;">
            <div><span style="color:var(--text-muted);">來源相對路徑:</span> <span style="color:var(--mint); font-family:var(--mono);">${escapeHtml(prov.source_relpath || '無')}</span></div>
            <div><span style="color:var(--text-muted);">Wiki 頁面:</span> <span style="color:var(--accent-bright); font-family:var(--mono);">${escapeHtml(prov.wiki_page || '無')}</span></div>
            <div><span style="color:var(--text-muted);">Artifact ID:</span> <span style="font-family:monospace; font-size:10px;">${escapeHtml(prov.artifact_id || '無')}</span></div>
          </div>
        </div>

        <div>
          <div class="section-title">關聯 (${neighbors.length})</div>
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
          <div class="details-title">關係詳情</div>
          <div class="details-subtitle">
            <span class="badge-relation">${escapeHtml(edge.relation)}</span>
            <span class="badge-layer">層級: ${escapeHtml(edge.source_layer)}</span>
          </div>
        </div>

        <div class="detail-card" style="display:flex; flex-direction:column; gap:8px;">
          <div><span style="color:var(--text-muted);">來源:</span> <a href="#" class="node-link" data-node-id="${escapeAttr(edge.source)}" style="color:var(--accent-bright); text-decoration:none; font-weight:500; font-family:var(--sans); margin-left:6px;">${escapeHtml(sNode ? sNode.label : edge.source)}</a></div>
          <div style="padding-left:12px; color:var(--text-muted); font-size:10px;">ID: ${escapeHtml(edge.source)}</div>

          <div style="margin-top:6px;"><span style="color:var(--text-muted);">目標:</span> <a href="#" class="node-link" data-node-id="${escapeAttr(edge.target)}" style="color:var(--accent-bright); text-decoration:none; font-weight:500; font-family:var(--sans); margin-left:6px;">${escapeHtml(tNode ? tNode.label : edge.target)}</a></div>
          <div style="padding-left:12px; color:var(--text-muted); font-size:10px;">ID: ${escapeHtml(edge.target)}</div>
        </div>

        <div class="detail-card">
          <div class="detail-card-title">可靠度</div>
          <div style="display:flex; flex-direction:column; gap:8px;">
            <div><span style="color:var(--text-muted);">證據類型:</span> <span style="font-weight:600; color:${getEdgeColor(edge.evidence)};">${escapeHtml(labelForEvidence(edge.evidence))}</span></div>
            <div><span style="color:var(--text-muted);">信心分數:</span> <span style="font-weight:700; font-family:var(--mono); color:var(--text-main);">${formatScore(edge.confidence_score)}</span></div>
            <div><span style="color:var(--text-muted);">權重:</span> <span style="font-weight:700; font-family:var(--mono); color:var(--text-main);">${formatScore(edge.weight)}</span></div>
          </div>
        </div>

        ${edge.rationale ? `
          <div class="detail-card">
            <div class="detail-card-title">判斷依據</div>
            <div style="line-height:1.5; color:var(--text-main); font-size:12px;">${escapeHtml(edge.rationale)}</div>
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
            <span class="badge-kind" style="background-color: var(--color-community)">社群</span>
            <span class="badge-layer">信心分數: ${formatScore(c.confidence_score)}</span>
          </div>
        </div>

        <div class="detail-card">
          <div class="detail-card-title">摘要</div>
          <div style="line-height:1.5; font-size:12px; color:var(--text-main);">${escapeHtml(c.summary)}</div>
        </div>

        <div>
          <div class="section-title">成員 (${commNodes.length})</div>
          <div style="display:flex; flex-direction:column; gap:6px; max-height:240px; overflow-y:auto; padding-right:4px;">
            ${commNodes.map(n => `
              <div style="display:flex; justify-content:space-between; align-items:center; background:rgba(255,255,255,0.02); padding:6px 10px; border-radius:4px; border:1px solid var(--border-color); font-size:12px;">
                <a href="#" class="node-link" data-node-id="${escapeAttr(n.id)}" style="color:var(--accent-bright); text-decoration:none; font-weight:500;">${escapeHtml(n.label)}</a>
                <span class="count-badge" style="color:${colorForKind(n.kind)}">${escapeHtml(labelForKind(n.kind))}</span>
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
