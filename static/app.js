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

  const fmt = (v, suffix) => (v === null || v === undefined) ? '--' : Number(v).toFixed(2) + (suffix || '');
  const cls = (direction) => direction === 'up' ? 'up' : direction === 'down' ? 'down' : 'flat';

  function render() {
    const keyword = (filterEl.value || '').trim().toLowerCase();
    const visible = rows.filter(r =>
      !keyword || r.code.toLowerCase().includes(keyword) ||
      (r.name || '').toLowerCase().includes(keyword));
    if (!visible.length) {
      body.innerHTML = '<tr><td colspan="7" class="empty">' +
        (rows.length ? '没有匹配的股票' : '暂无数据') + '</td></tr>';
      return;
    }
    body.innerHTML = visible.map(r => {
      const c = cls(r.direction);
      const star = (r.pct !== null && Math.abs(r.pct) >= 3) ? '<span class="star">★</span>' : '';
      return '<tr>' +
        '<td>' + r.code + '</td>' +
        '<td>' + (r.name || '--') + '</td>' +
        '<td class="num ' + c + '">' + fmt(r.price) + '</td>' +
        '<td class="num ' + c + '">' + fmt(r.pct, '%') + '</td>' +
        '<td class="num ' + c + '">' + fmt(r.chg) + '</td>' +
        '<td class="num">' + star + '</td>' +
        '<td class="num"><button class="link-btn" data-remove="' + r.code + '">移除</button></td>' +
        '</tr>';
    }).join('');
  }

  function renderAlerts(alerts) {
    if (!alerts || !alerts.length) {
      alertList.innerHTML = '<li class="empty">暂无告警</li>';
      return;
    }
    alertList.innerHTML = alerts.map(a => {
      const c = a.pct > 0 ? 'up' : 'down';
      return '<li class="' + c + '"><strong>' + a.time + '</strong><br>' +
        a.name + '(' + a.code + ') ' + a.kind + ' ' +
        Number(a.pct).toFixed(2) + '% · 现价 ' + fmt(a.price) + '</li>';
    }).join('');
  }

  function renderWatchlist(codes) {
    if (!codes || !codes.length) {
      watchlistEl.innerHTML = '<li class="empty">还没有自选股</li>';
      return;
    }
    watchlistEl.innerHTML = codes.map(c =>
      '<li class="chip">' + c +
      ' <button class="chip-x" data-remove="' + c + '" title="移除">×</button></li>').join('');
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

  async function tick() {
    try {
      const resp = await fetch('/api/quotes', { cache: 'no-store' });
      const data = await resp.json();
      rows = data.quotes || [];
      pillSource.textContent = '数据源 ' + (data.source || '--');
      pillTime.textContent = '更新 ' + (data.time || '--');
      banner.classList.toggle('hidden', !data.error);
      if (data.error) banner.textContent = '⚠ ' + data.error;
      render();
      renderAlerts(data.alerts);
    } catch (err) {
      banner.classList.remove('hidden');
      banner.textContent = '⚠ 无法连接服务：' + err;
    }
  }

  let left = interval;
  setInterval(function () {
    left -= 1;
    if (left <= 0) { left = interval; tick(); }
    pillCountdown.textContent = left + 's 后刷新';
  }, 1000);

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
      '<li>' + line + '</li>').join('');
  });

  document.getElementById('btn-clear').addEventListener('click', async function () {
    await fetch('/api/alerts', { method: 'DELETE' });
    renderAlerts([]);
  });

  loadWatchlist();
  tick();
})();
