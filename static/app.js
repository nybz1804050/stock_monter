/* 自选股行情看板前端：定时拉取 /api/quotes 并渲染表格与告警。 */
(function () {
  const interval = (window.APP_CONFIG && window.APP_CONFIG.interval) || 5;
  const body = document.getElementById('quote-body');
  const banner = document.getElementById('banner');
  const filterEl = document.getElementById('filter');
  const alertList = document.getElementById('alert-list');
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
      body.innerHTML = '<tr><td colspan="6" class="empty">' +
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

  tick();
})();
