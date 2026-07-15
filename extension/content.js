// Line Tracker — a read-only overlay that graphs any number you pick on a page.
//
// It runs entirely in your browser: it reads the text of the element you click, every couple of
// seconds, parses a number out of it, and draws a live line. It sends NOTHING anywhere, stores
// NOTHING, and cannot place a bet. Use it to see the tracking/graphing concept work against a real
// page (including 1xbet). It gives you no edge on its own — that still needs a sharp fair line to
// compare against (see the project's FINDINGS.md).
(function () {
  if (window.__h2LineTracker) return;
  window.__h2LineTracker = true;

  var BLUE = "#0072B2", ORANGE = "#D55E00", INK = "#1a1a19", MUTED = "#6b6b68";
  var state = { el: null, series: [], t0: null, timer: null, picking: false, intervalMs: 2000 };

  // ----- floating panel -----
  var panel = document.createElement("div");
  panel.style.cssText =
    "position:fixed;z-index:2147483647;right:16px;bottom:16px;width:320px;background:#fff;" +
    "border:1px solid #ccc;border-radius:10px;box-shadow:0 6px 24px rgba(0,0,0,.25);" +
    "font:13px system-ui,-apple-system,sans-serif;color:" + INK + ";overflow:hidden;";
  panel.innerHTML =
    '<div id="h2-head" style="cursor:move;background:' + BLUE + ';color:#fff;padding:8px 10px;' +
      'font-weight:600;display:flex;justify-content:space-between;align-items:center;">' +
      "<span>📈 Line Tracker</span><span id=\"h2-close\" style=\"cursor:pointer;\">✕</span></div>" +
    '<div style="padding:10px;">' +
      '<div style="display:flex;gap:6px;margin-bottom:8px;">' +
        '<button id="h2-pick" style="flex:1;padding:6px;border:0;border-radius:6px;background:' + BLUE +
          ';color:#fff;cursor:pointer;font-weight:600;">🎯 Pick a number</button>' +
        '<button id="h2-pause" style="padding:6px 8px;border:1px solid #ccc;border-radius:6px;background:#f4f4f2;cursor:pointer;">Pause</button>' +
        '<button id="h2-clear" style="padding:6px 8px;border:1px solid #ccc;border-radius:6px;background:#f4f4f2;cursor:pointer;">Clear</button>' +
      "</div>" +
      '<div id="h2-label" style="color:' + MUTED + ';margin-bottom:6px;line-height:1.3;">' +
        'Click <b>Pick a number</b>, then click the odds or total on the page you want to watch.</div>' +
      '<div id="h2-value" style="font-size:24px;font-weight:800;margin-bottom:6px;">—</div>' +
      '<canvas id="h2-canvas" width="300" height="120" style="width:100%;height:120px;background:#fcfcfb;' +
        'border:1px solid #eee;border-radius:6px;display:block;"></canvas>' +
      '<div id="h2-meta" style="color:' + MUTED + ';margin-top:6px;font-size:11px;">read-only · nothing is sent or placed</div>' +
    "</div>";
  document.documentElement.appendChild(panel);

  var $ = function (sel) { return panel.querySelector(sel); };
  var canvas = $("#h2-canvas"), ctx = canvas.getContext("2d");

  // ----- draggable by header -----
  (function () {
    var head = $("#h2-head"), down = false, sx, sy, ox, oy;
    head.addEventListener("mousedown", function (e) {
      down = true; sx = e.clientX; sy = e.clientY;
      var r = panel.getBoundingClientRect(); ox = r.left; oy = r.top;
      panel.style.right = "auto"; panel.style.bottom = "auto";
      panel.style.left = ox + "px"; panel.style.top = oy + "px"; e.preventDefault();
    });
    window.addEventListener("mousemove", function (e) {
      if (!down) return;
      panel.style.left = (ox + e.clientX - sx) + "px";
      panel.style.top = (oy + e.clientY - sy) + "px";
    });
    window.addEventListener("mouseup", function () { down = false; });
  })();

  // ----- element picker -----
  var hoverEl = null;
  var outline = document.createElement("div");
  outline.style.cssText =
    "position:fixed;z-index:2147483646;border:2px solid " + ORANGE +
    ";background:rgba(213,94,0,.10);pointer-events:none;display:none;";
  document.documentElement.appendChild(outline);

  function onMove(e) {
    var el = document.elementFromPoint(e.clientX, e.clientY);
    if (!el || el === panel || panel.contains(el) || el === outline) return;
    hoverEl = el;
    var r = el.getBoundingClientRect();
    outline.style.display = "block";
    outline.style.left = r.left + "px"; outline.style.top = r.top + "px";
    outline.style.width = r.width + "px"; outline.style.height = r.height + "px";
  }
  function onClick(e) {
    if (!state.picking || panel.contains(e.target)) return;
    e.preventDefault(); e.stopPropagation();
    state.el = hoverEl; state.picking = false; outline.style.display = "none";
    document.removeEventListener("mousemove", onMove, true);
    document.removeEventListener("click", onClick, true);
    $("#h2-pick").textContent = "🎯 Pick a number";
    var txt = (state.el.textContent || "").trim().replace(/\s+/g, " ").slice(0, 48);
    $("#h2-label").textContent = "Tracking: " + txt;
    state.series = []; state.t0 = null;
    start();
  }
  $("#h2-pick").onclick = function () {
    state.picking = true;
    $("#h2-pick").textContent = "Click the number…";
    document.addEventListener("mousemove", onMove, true);
    document.addEventListener("click", onClick, true);
  };

  // ----- read + poll + draw -----
  function readNumber() {
    if (!state.el) return null;
    var m = (state.el.textContent || "").replace(/[,\s]/g, "").match(/-?\d+(?:\.\d+)?/);
    return m ? parseFloat(m[0]) : null;
  }
  function tick() {
    var v = readNumber();
    if (v == null) return;
    var now = Date.now();
    if (state.t0 == null) state.t0 = now;
    state.series.push({ t: (now - state.t0) / 1000, v: v });
    if (state.series.length > 900) state.series.shift();
    $("#h2-value").textContent = v;
    draw();
  }
  function start() { stop(); tick(); state.timer = setInterval(tick, state.intervalMs); $("#h2-pause").textContent = "Pause"; }
  function stop() { if (state.timer) clearInterval(state.timer); state.timer = null; }

  $("#h2-pause").onclick = function () {
    if (state.timer) { stop(); $("#h2-pause").textContent = "Resume"; }
    else if (state.el) { start(); }
  };
  $("#h2-clear").onclick = function () { state.series = []; state.t0 = null; draw(); };
  $("#h2-close").onclick = function () {
    stop();
    document.removeEventListener("mousemove", onMove, true);
    document.removeEventListener("click", onClick, true);
    panel.remove(); outline.remove(); window.__h2LineTracker = false;
  };

  function draw() {
    var w = canvas.width, h = canvas.height, pad = 8;
    ctx.clearRect(0, 0, w, h);
    var s = state.series;
    if (s.length < 2) {
      ctx.fillStyle = MUTED; ctx.font = "12px system-ui";
      ctx.fillText("waiting for data…", 10, 22);
      return;
    }
    var vs = s.map(function (p) { return p.v; });
    var mn = Math.min.apply(null, vs), mx = Math.max.apply(null, vs), span = (mx - mn) || 1;
    var t0 = s[0].t, t1 = s[s.length - 1].t, tspan = (t1 - t0) || 1;
    ctx.strokeStyle = BLUE; ctx.lineWidth = 2; ctx.beginPath();
    s.forEach(function (p, i) {
      var x = pad + (p.t - t0) / tspan * (w - 2 * pad);
      var y = h - pad - (p.v - mn) / span * (h - 2 * pad);
      if (i) ctx.lineTo(x, y); else ctx.moveTo(x, y);
    });
    ctx.stroke();
    ctx.fillStyle = MUTED; ctx.font = "10px system-ui";
    ctx.fillText(String(mx), 3, 11);
    ctx.fillText(String(mn), 3, h - 3);
    $("#h2-meta").textContent =
      s.length + " points · min " + mn + " · max " + mx +
      " · every " + (state.intervalMs / 1000) + "s · read-only";
  }
})();
