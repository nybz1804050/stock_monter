/* 主题切换：优先用本地记忆，其次跟随系统偏好，切换结果写回 localStorage。

   这段脚本放在 <head> 里同步执行（不加 defer），因此会在首屏渲染前就把
   data-theme 打到 <html> 上，避免"先闪一下深色再变浅色"。 */
(function () {
  const KEY = 'stockmon-theme';
  const root = document.documentElement;

  function read() {
    try {
      return localStorage.getItem(KEY);
    } catch (e) {
      return null;                 // 隐私模式下 localStorage 可能不可用
    }
  }

  function write(theme) {
    try {
      localStorage.setItem(KEY, theme);
    } catch (e) { /* 存不了就只在本次会话生效 */ }
  }

  function current() {
    // 默认深色：沿用项目原有视觉，不因系统浅色主题而"突然变样"；
    // 用户点过切换按钮后按 localStorage 的记忆走。
    return read() || 'dark';
  }

  function apply(theme) {
    root.setAttribute('data-theme', theme);
    const btn = document.getElementById('btn-theme');
    if (!btn) return;
    const light = theme === 'light';
    btn.textContent = light ? '☀' : '☾';        // 图标表示"当前主题"
    const label = light ? '切换到深色主题' : '切换到浅色主题';
    btn.setAttribute('title', label);
    btn.setAttribute('aria-label', label);
    btn.setAttribute('aria-pressed', light ? 'true' : 'false');
  }

  apply(current());

  document.addEventListener('DOMContentLoaded', function () {
    apply(current());
    const btn = document.getElementById('btn-theme');
    if (!btn) return;
    btn.addEventListener('click', function () {
      const next = current() === 'light' ? 'dark' : 'light';
      write(next);
      apply(next);
    });
  });
})();
