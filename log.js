(function() {
  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function formatMs(ms) {
    const n = Math.max(0, Number(ms) || 0);
    if (n < 1000) return `${n}ms`;
    return `${(n / 1000).toFixed(2)}s`;
  }

  function formatIso(tsMs) {
    return new Date(tsMs).toISOString();
  }

  function formatTimeOnly(tsMs) {
    const d = new Date(tsMs);
    const hh = String(d.getHours()).padStart(2, "0");
    const mm = String(d.getMinutes()).padStart(2, "0");
    const ss = String(d.getSeconds()).padStart(2, "0");
    return `${hh}:${mm}:${ss}`;
  }

  window.LogUtils = {
    escapeHtml,
    formatIso,
    formatMs,
    formatTimeOnly
  };
})();
