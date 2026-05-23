/**
 * About Page - Service Status (LLM API Balance Check)
 *
 * Displays the LLM API service status on the About page.
 * Checks the /api/balance endpoint and shows a status indicator.
 */
(function() {
  'use strict';

  const STATUS_MAP = {
    healthy: { dotClass: 'green', text: 'API 服务正常' },
    low:     { dotClass: 'yellow', text: 'API 余额即将耗尽' },
    exhausted: { dotClass: 'red', text: 'API 余额已耗尽' },
  };

  async function checkApiBalance() {
    const dotEl = document.getElementById('aboutApiStatusDot');
    const textEl = document.getElementById('aboutApiStatusText');
    if (!dotEl || !textEl) return;

    try {
      const resp = await fetch('/api/balance');
      if (!resp.ok) {
        dotEl.className = 'api-status-dot red';
        textEl.textContent = 'API 服务异常';
        return;
      }
      const data = await resp.json();
      const status = STATUS_MAP[data.status] || { dotClass: 'gray', text: '未知状态' };
      dotEl.className = `api-status-dot ${status.dotClass}`;
      textEl.textContent = status.text;
    } catch (err) {
      dotEl.className = 'api-status-dot gray';
      textEl.textContent = '无法检测 API 状态';
    }
  }

  // ── Init ──
  checkApiBalance();
  // 每 1 分钟刷新一次余额状态
  setInterval(checkApiBalance, 60 * 1000);
})();
