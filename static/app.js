/* 自选股行情看板前端：定时拉取 /api/quotes 并渲染表格与告警。 */
(function () {
  const interval = (window.APP_CONFIG && window.APP_CONFIG.interval) || 5;
  const body = document.getElementById('quote-body');
  const banner = document.getElementById('banner');
  const filterEl = document.getElementById('filter');
  const alertList = document.getElementById('alert-list');
  const watchlistEl = document.getElementById('watchlist');
  const addForm = document.getElementById('add-form');
  const addCode = document.getElementById('add-code');
  const addMsg = document.getElementById('add-msg');
  const pillSource = document.getElementById('pill-source');
  const pillTime = document.getElementById('pill-time');
  const pillCountdown = document.getElementById('pill-countdown');
  let rows = [];
  let sortKey = null;        // 当前排序字段
  let sortAsc = false;       // 升降序（点表头切换）

  const fmt = (v, suffix) => (v === null || v === undefined) ? '--' : Number(v).toFixed(2) + (suffix || '');
  const history = {};        // code -> 最近价格序列（稀疏更新，避免频繁请求）
  const ma5 = {};            // code -> 5 日均线，来自 /api/indicators，与 history 等长
  const cls = (direction) => direction === 'up' ? 'up' : direction === 'down' ? 'down' : 'flat';

  /* 所有拼进 innerHTML 的动态内容都要先转义：股票名来自外部接口、告警日志来自本地文件，
     直接拼接会让特殊字符（< > " '）有机会变成标签或脚本。 */
  const escapeHtml = (v) => String(v === null || v === undefined ? '' : v)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');

  let threshold = (window.APP_CONFIG && window.APP_CONFIG.threshold) || 3;  // 星标阈值，随后端快照更新

  function sortRows(list) {
    if (!sortKey) return list;
    const dir = sortAsc ? 1 : -1;
    return list.slice().sort(function (a, b) {
      const va = a[sortKey], vb = b[sortKey];
      if (va === null || va === undefined) return 1;      // 无值排最后
      if (vb === null || vb === undefined) return -1;
      if (typeof va === 'number' && typeof vb === 'number') return (va - vb) * dir;
      return String(va).localeCompare(String(vb)) * dir;
    });
  }

  function render() {
    const keyword = (filterEl.value || '').trim().toLowerCase();
    const visible = sortRows(rows.filter(r =>
      !keyword || r.code.toLowerCase().includes(keyword) ||
      (r.name || '').toLowerCase().includes(keyword)));
    if (!visible.length) {
      body.innerHTML = '<tr><td colspan="8" class="empty">' +
        (rows.length ? '没有匹配的股票' : '暂无数据') + '</td></tr>';
      return;
    }
    body.innerHTML = visible.map(r => {
      const c = cls(r.direction);
      const star = (r.pct !== null && Math.abs(r.pct) >= threshold) ? '<span class="star">★</span>' : '';
      return '<tr>' +
        '<td>' + escapeHtml(r.code) + '</td>' +
        '<td>' + escapeHtml(r.name || '--') + '</td>' +
        '<td class="num ' + c + '">' + fmt(r.price) + '</td>' +
        '<td class="num ' + c + '">' + fmt(r.pct, '%') + '</td>' +
        '<td class="num ' + c + '">' + fmt(r.chg) + '</td>' +
        '<td class="num">' + star + '</td>' +
        '<td class="num"><canvas class="spark" width="96" height="24" data-spark="' + escapeHtml(r.code) + '"></canvas></td>' +
        '<td class="num"><button class="link-btn" data-remove="' + escapeHtml(r.code) + '">移除</button></td>' +
        '</tr>';
    }).join('');
  }

  function drawSparks() {
    document.querySelectorAll('canvas[data-spark]').forEach(function (cv) {
      const code = cv.getAttribute('data-spark');
      const points = history[code] || [];
      const ctx = cv.getContext('2d');
      const w = cv.width, h = cv.height;
      ctx.clearRect(0, 0, w, h);
      if (points.length < 2) return;

      const prices = points.map(p => p.price);
      const vals = prices.filter(v => v !== null && v !== undefined);
      if (vals.length < 2) return;

      // 均线与价格共用同一坐标系，否则"价格在均线上还是下"就看不出来了
      const ma = (ma5[code] || []).filter(v => v !== null && v !== undefined);
      const all = vals.concat(ma);
      const min = Math.min.apply(null, all), max = Math.max.apply(null, all);
      const span = (max - min) || 1;
      const n = prices.length;
      const xAt = (i) => (i / (n - 1)) * (w - 2) + 1;
      const yAt = (v) => h - 2 - ((v - min) / span) * (h - 4);

      function drawLine(values, color, width, dash) {
        if (values.length < 2) return;
        ctx.save();
        ctx.strokeStyle = color;
        ctx.lineWidth = width;
        if (dash) ctx.setLineDash(dash);
        ctx.beginPath();
        let started = false;
        values.forEach(function (v, i) {
          if (v === null || v === undefined) { started = false; return; }   // 断点不连线
          if (!started) { ctx.moveTo(xAt(i), yAt(v)); started = true; }
          else { ctx.lineTo(xAt(i), yAt(v)); }
        });
        ctx.stroke();
        ctx.restore();
      }

      const rising = vals[vals.length - 1] >= vals[0];
      drawLine(ma5[code] || [], '#8b97ad', 1, [3, 2]);          // 均线先画，压在价格线之下
      drawLine(prices, rising ? '#ff5b5b' : '#35c46a', 1.5);
    });
  }

  async function refreshHistory() {
    const codes = rows.map(r => r.code);
    for (const code of codes) {
      // 价格序列与 5 日均线并行拉取；均线拿不到（如历史库未启用）不影响走势图本身
      const [hist, ind] = await Promise.all([
        fetch('/api/history?code=' + code + '&limit=60', { cache: 'no-store' })
          .then(r => r.json()).catch(() => null),
        fetch('/api/indicators?code=' + code + '&name=sma&window=5&limit=60',
              { cache: 'no-store' })
          .then(r => r.json()).catch(() => null),
      ]);
      if (hist && hist.ok) history[code] = hist.points || [];
      if (ind && ind.ok && ind.series && ind.series.values) ma5[code] = ind.series.values;
    }
    drawSparks();
  }
  setInterval(refreshHistory, 60000);

  function renderAlerts(alerts) {
    if (!alerts || !alerts.length) {
      alertList.innerHTML = '<li class="empty">暂无告警</li>';
      return;
    }
    alertList.innerHTML = alerts.map(a => {
      const c = a.pct > 0 ? 'up' : 'down';
      return '<li class="' + c + '"><strong>' + escapeHtml(a.time) + '</strong><br>' +
        escapeHtml(a.name) + '(' + escapeHtml(a.code) + ') ' + escapeHtml(a.kind) + ' ' +
        Number(a.pct).toFixed(2) + '% · 现价 ' + fmt(a.price) + '</li>';
    }).join('');
  }

  function renderWatchlist(codes) {
    if (!codes || !codes.length) {
      watchlistEl.innerHTML = '<li class="empty">还没有自选股</li>';
      return;
    }
    watchlistEl.innerHTML = codes.map(c =>
      '<li class="chip">' + escapeHtml(c) +
      ' <button class="chip-x" data-remove="' + escapeHtml(c) + '" title="移除">×</button></li>').join('');
  }

  function flash(text, ok) {
    addMsg.textContent = text;
    addMsg.classList.remove('hidden');
    addMsg.classList.toggle('err', !ok);
    setTimeout(function () { addMsg.classList.add('hidden'); }, 2600);
  }

  async function loadWatchlist() {
    const resp = await fetch('/api/watchlist', { cache: 'no-store' });
    const data = await resp.json();
    renderWatchlist(data.codes);
  }

  async function removeCode(code) {
    await fetch('/api/watchlist/' + encodeURIComponent(code), { method: 'DELETE' });
    await loadWatchlist();
    tick();
  }

  document.addEventListener('click', function (ev) {
    const target = ev.target.closest('[data-remove]');
    if (target) removeCode(target.getAttribute('data-remove'));
  });

  addForm.addEventListener('submit', async function (ev) {
    ev.preventDefault();
    const code = (addCode.value || '').trim();
    if (!/^\d{6}$/.test(code)) { flash('代码必须是 6 位数字', false); return; }
    const resp = await fetch('/api/watchlist', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code: code }),
    });
    const data = await resp.json();
    if (data.ok) {
      addCode.value = '';
      flash('已添加 ' + code, true);
      renderWatchlist(data.codes);
      tick();
    } else {
      flash(data.error || '添加失败', false);
    }
  });

  function apply(data) {
    rows = data.quotes || [];
    if (typeof data.threshold === 'number' && data.threshold > 0) threshold = data.threshold;
    pillSource.textContent = '数据源 ' + (data.source || '--');
    pillTime.textContent = '更新 ' + (data.time || '--');
    banner.classList.toggle('hidden', !data.error);
    if (data.error) banner.textContent = '⚠ ' + data.error;
    render();
    renderAlerts(data.alerts);
    drawSparks();
  }

  async function tick() {
    try {
      const resp = await fetch('/api/quotes', { cache: 'no-store' });
      apply(await resp.json());
    } catch (err) {
      banner.classList.remove('hidden');
      banner.textContent = '⚠ 无法连接服务：' + err;
    }
  }

  // 优先用 SSE 实时推送；不可用时自动退回定时轮询
  let stream = null;
  let streamOk = false;
  function connectStream() {
    if (!window.EventSource) return;
    try {
      stream = new EventSource('/api/stream');
    } catch (e) { return; }
    stream.onmessage = function (ev) {
      streamOk = true;
      pillCountdown.textContent = '实时推送';
      try { apply(JSON.parse(ev.data)); } catch (e) { /* 忽略坏帧 */ }
    };
    stream.onerror = function () {
      streamOk = false;
      if (stream) { stream.close(); stream = null; }
      setTimeout(connectStream, 15000);      // 稍后重连，期间走轮询
    };
  }
  connectStream();

  let left = interval;
  setInterval(function () {
    left -= 1;
    if (left <= 0) {
      left = interval;
      if (!streamOk) tick();                 // SSE 正常时不再重复拉取
    }
    if (!streamOk) pillCountdown.textContent = left + 's 后刷新';
  }, 1000);

  document.querySelectorAll('th.sortable').forEach(function (th) {
    th.addEventListener('click', function () {
      const key = th.getAttribute('data-sort');
      if (sortKey === key) { sortAsc = !sortAsc; } else { sortKey = key; sortAsc = (key === 'code' || key === 'name'); }
      document.querySelectorAll('th.sortable').forEach(function (x) { x.classList.remove('asc', 'desc'); });
      th.classList.add(sortAsc ? 'asc' : 'desc');
      render();
      drawSparks();
    });
  });

  document.getElementById('btn-refresh').addEventListener('click', function () {
    left = interval; tick();
  });
  filterEl.addEventListener('input', render);

  document.getElementById('btn-history').addEventListener('click', async function () {
    const resp = await fetch('/api/alerts?history=1', { cache: 'no-store' });
    const data = await resp.json();
    const history = data.history || [];
    if (!history.length) { alertList.innerHTML = '<li class="empty">日志里还没有记录</li>'; return; }
    alertList.innerHTML = history.slice().reverse().map(line =>
      '<li>' + escapeHtml(line) + '</li>').join('');
  });

  document.getElementById('btn-clear').addEventListener('click', async function () {
    await fetch('/api/alerts', { method: 'DELETE' });
    renderAlerts([]);
  });

  loadWatchlist();
  // 行情就绪后立刻拉一次历史与均线：refreshHistory 依赖 rows 里的代码列表，
  // 若只靠 setInterval，首次要等满 60 秒，这段时间走势图是空白的。
  tick().then(function () { refreshHistory(); });
})();
