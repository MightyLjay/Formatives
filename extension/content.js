// Line Tracker — a read-only overlay that graphs numbers you pick on a page.
//
// v0.3: track SEVERAL numbers at once, each labelled (Over / Under / Total / …). You click "+ Over"
// then click the over price; "+ Under" then the under price; and it graphs both live so you can see
// the whole bet move. Reads by SCREEN POSITION each tick, so it survives live books (1xbet) that
// rebuild their odds elements constantly.
//
// It sends NOTHING anywhere, stores NOTHING, and cannot place a bet. It reads ONE book's own
// numbers, so it gives no edge by itself — an edge needs a sharp fair line to compare against
// (see the repo's FINDINGS.md). Each line is scaled to its OWN range so different-scale numbers
// (a price ~1.9 and a total ~81) can share the chart honestly; read exact values in the legend.
(function () {
  if (window.top !== window) return;
  if (window.__h2LineTracker) return;
  window.__h2LineTracker = true;

  var BLUE = "#0072B2", INK = "#1a1a19", MUTED = "#6b6b68", ORANGE = "#D55E00";
  var PRESETS = [
    { label: "Over", color: "#009E73" },
    { label: "Under", color: "#D55E00" },
    { label: "Total", color: "#0072B2" },
    { label: "Other", color: "#CC79A7" },
  ];
  var state = { tracks: [], t0: null, timer: null, picking: false, pendingLabel: null, pendingColor: null, justPicked: false, intervalMs: 2000 };

  var panel = document.createElement("div");
  panel.style.cssText =
    "position:fixed;z-index:2147483647;right:16px;bottom:16px;width:330px;background:#fff;" +
    "border:1px solid #ccc;border-radius:10px;box-shadow:0 6px 24px rgba(0,0,0,.25);" +
    "font:13px system-ui,-apple-system,sans-serif;color:" + INK + ";overflow:hidden;";
  var btns = PRESETS.map(function (p) {
    return '<button class="h2-add" data-label="' + p.label + '" data-color="' + p.color + '" ' +
      'style="flex:1;padding:5px;border:0;border-radius:6px;background:' + p.color + ';color:#fff;' +
      'cursor:pointer;font-weight:600;font-size:12px;">+ ' + p.label + "</button>";
  }).join("");
  panel.innerHTML =
    '<div id="h2-head" style="cursor:move;background:' + BLUE + ';color:#fff;padding:8px 10px;' +
      'font-weight:600;display:flex;justify-content:space-between;align-items:center;">' +
      "<span>📈 Line Tracker</span><span id=\"h2-close\" style=\"cursor:pointer;\">✕</span></div>" +
    '<div style="padding:10px;">' +
      '<div style="display:flex;gap:5px;margin-bottom:8px;">' + btns + "</div>" +
      '<div id="h2-label" style="color:' + MUTED + ';margin-bottom:8px;line-height:1.3;">' +
        'Click <b>+ Over</b> (or Under/Total), then click straight on the digits on the page.</div>' +
      '<canvas id="h2-canvas" width="310" height="120" style="width:100%;height:120px;background:#fcfcfb;' +
        'border:1px solid #eee;border-radius:6px;display:block;"></canvas>' +
      '<div id="h2-legend" style="margin-top:8px;"></div>' +
      '<div style="display:flex;gap:6px;margin-top:8px;">' +
        '<button id="h2-pause" style="flex:1;padding:5px;border:1px solid #ccc;border-radius:6px;background:#f4f4f2;cursor:pointer;">Pause</button>' +
        '<button id="h2-clear" style="flex:1;padding:5px;border:1px solid #ccc;border-radius:6px;background:#f4f4f2;cursor:pointer;">Clear all</button>' +
      "</div>" +
      '<div id="h2-meta" style="color:' + MUTED + ';margin-top:6px;font-size:11px;">read-only · one book\'s numbers · not an edge on its own</div>' +
    "</div>";
  document.documentElement.appendChild(panel);

  var $ = function (s) { return panel.querySelector(s); };
  var canvas = $("#h2-canvas"), ctx = canvas.getContext("2d");

  (function () {
    var head = $("#h2-head"), down = false, sx, sy, ox, oy;
    head.addEventListener("mousedown", function (e) {
      down = true; sx = e.clientX; sy = e.clientY;
      var r = panel.getBoundingClientRect(); ox = r.left; oy = r.top;
      panel.style.right = "auto"; panel.style.bottom = "auto"; panel.style.left = ox + "px"; panel.style.top = oy + "px"; e.preventDefault();
    });
    window.addEventListener("mousemove", function (e) { if (down) { panel.style.left = (ox + e.clientX - sx) + "px"; panel.style.top = (oy + e.clientY - sy) + "px"; } });
    window.addEventListener("mouseup", function () { down = false; });
  })();

  var outline = document.createElement("div");
  outline.style.cssText = "position:fixed;z-index:2147483646;border:2px solid " + ORANGE + ";background:rgba(213,94,0,.10);pointer-events:none;display:none;";
  document.documentElement.appendChild(outline);

  function onMove(e) {
    if (!state.picking) return;
    var el = document.elementFromPoint(e.clientX, e.clientY);
    if (!el || el === panel || panel.contains(el) || el === outline) { outline.style.display = "none"; return; }
    var r = el.getBoundingClientRect();
    outline.style.display = "block"; outline.style.left = r.left + "px"; outline.style.top = r.top + "px"; outline.style.width = r.width + "px"; outline.style.height = r.height + "px";
  }
  function numberAt(px, py) {
    var el = document.elementFromPoint(px - window.scrollX, py - window.scrollY);
    if (!el || panel.contains(el)) return { v: null, text: "" };
    var raw = (el.textContent || "").replace(/ /g, " ").trim();
    var m = raw.replace(/[,\s]/g, "").match(/-?\d+(?:\.\d+)?/);
    return { v: m ? parseFloat(m[0]) : null, text: raw.slice(0, 24) };
  }
  function onPick(e) {
    if (!state.picking || panel.contains(e.target)) return;
    e.preventDefault(); e.stopPropagation(); if (e.stopImmediatePropagation) e.stopImmediatePropagation();
    var px = e.clientX + window.scrollX, py = e.clientY + window.scrollY;
    endPicking();
    var r = numberAt(px, py);
    if (r.v == null) {
      $("#h2-label").innerHTML = '<span style="color:' + ORANGE + '">No number there. Click <b>directly on the digits</b> (zoom in with Ctrl+ if tiny).</span>';
      return;
    }
    state.tracks.push({ label: state.pendingLabel, color: state.pendingColor, px: px, py: py, series: [], last: r.v });
    $("#h2-label").textContent = "Tracking " + state.pendingLabel + " (currently " + r.v + "). Add another, or watch it move.";
    if (!state.timer) start();
    renderLegend();
  }
  function swallow(e) { if (state.picking || state.justPicked) { e.preventDefault(); e.stopPropagation(); if (e.stopImmediatePropagation) e.stopImmediatePropagation(); } }
  function beginPicking(label, color) {
    state.picking = true; state.pendingLabel = label; state.pendingColor = color;
    $("#h2-label").textContent = "Click the " + label + " number on the page…";
    document.addEventListener("mousemove", onMove, true);
    document.addEventListener("pointerdown", onPick, true);
    document.addEventListener("mousedown", swallow, true);
    document.addEventListener("click", swallow, true);
  }
  function endPicking() {
    state.picking = false; state.justPicked = true; outline.style.display = "none";
    document.removeEventListener("mousemove", onMove, true);
    document.removeEventListener("pointerdown", onPick, true);
    setTimeout(function () { state.justPicked = false; document.removeEventListener("mousedown", swallow, true); document.removeEventListener("click", swallow, true); }, 400);
  }
  panel.querySelectorAll(".h2-add").forEach(function (b) {
    b.addEventListener("click", function () { beginPicking(b.getAttribute("data-label"), b.getAttribute("data-color")); });
  });

  function tick() {
    var now = Date.now(); if (state.t0 == null) state.t0 = now;
    var t = (now - state.t0) / 1000;
    state.tracks.forEach(function (tr) {
      var r = numberAt(tr.px, tr.py);
      if (r.v != null) { tr.last = r.v; tr.series.push({ t: t, v: r.v }); if (tr.series.length > 900) tr.series.shift(); }
    });
    draw(); renderLegend();
  }
  function start() { stop(); tick(); state.timer = setInterval(tick, state.intervalMs); $("#h2-pause").textContent = "Pause"; }
  function stop() { if (state.timer) clearInterval(state.timer); state.timer = null; }

  $("#h2-pause").onclick = function () { if (state.timer) { stop(); $("#h2-pause").textContent = "Resume"; } else if (state.tracks.length) { start(); } };
  $("#h2-clear").onclick = function () { state.tracks = []; state.t0 = null; draw(); renderLegend(); $("#h2-label").textContent = "Cleared. Click + Over / + Under to start again."; };
  $("#h2-close").onclick = function () { stop(); endPicking(); panel.remove(); outline.remove(); window.__h2LineTracker = false; };

  function renderLegend() {
    var leg = $("#h2-legend");
    if (!state.tracks.length) { leg.innerHTML = ""; return; }
    leg.innerHTML = state.tracks.map(function (tr, i) {
      return '<div style="display:flex;align-items:center;gap:6px;margin:2px 0;">' +
        '<span style="width:10px;height:10px;border-radius:2px;background:' + tr.color + ';display:inline-block;"></span>' +
        '<b style="min-width:52px;">' + tr.label + '</b><span style="font-size:15px;font-weight:700;">' + (tr.last != null ? tr.last : "—") + "</span>" +
        '<span class="h2-rm" data-i="' + i + '" style="margin-left:auto;color:' + MUTED + ';cursor:pointer;">✕</span></div>';
    }).join("");
    leg.querySelectorAll(".h2-rm").forEach(function (x) {
      x.addEventListener("click", function () { state.tracks.splice(parseInt(x.getAttribute("data-i")), 1); draw(); renderLegend(); });
    });
  }

  function draw() {
    var w = canvas.width, h = canvas.height, pad = 8;
    ctx.clearRect(0, 0, w, h);
    var any = state.tracks.some(function (tr) { return tr.series.length >= 2; });
    if (!any) { ctx.fillStyle = MUTED; ctx.font = "12px system-ui"; ctx.fillText("pick a number to start…", 10, 22); return; }
    // shared time axis; each series scaled to its OWN value range (no misleading shared y-axis)
    var tmax = 0; state.tracks.forEach(function (tr) { tr.series.forEach(function (p) { if (p.t > tmax) tmax = p.t; }); });
    var tspan = tmax || 1;
    state.tracks.forEach(function (tr) {
      var s = tr.series; if (s.length < 2) return;
      var vs = s.map(function (p) { return p.v; });
      var mn = Math.min.apply(null, vs), mx = Math.max.apply(null, vs), span = (mx - mn) || 1;
      ctx.strokeStyle = tr.color; ctx.lineWidth = 2; ctx.beginPath();
      s.forEach(function (p, i) {
        var x = pad + p.t / tspan * (w - 2 * pad);
        var y = h - pad - (p.v - mn) / span * (h - 2 * pad);
        if (i) ctx.lineTo(x, y); else ctx.moveTo(x, y);
      });
      ctx.stroke();
    });
    var pts = state.tracks.reduce(function (a, tr) { return a + tr.series.length; }, 0);
    $("#h2-meta").textContent = pts + " points · each line scaled to its own range · exact values in the legend";
  }
})();
