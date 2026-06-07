/**
 * Scroller admin page – manage scrolling background texts.
 *
 * Features:
 *   - Load current texts from API
 *   - Add / remove / edit text items
 *   - Login via HttpOnly cookie (password never stored in JS)
 *   - Save via cookie-authenticated PUT endpoint
 */
(function () {
  'use strict';

  // Password is no longer stored in sessionStorage.
  // Auth uses HttpOnly cookie set by POST /api/scroller/login.

  // ── DOM refs ──────────────────────────────────────────────────────────
  const container = document.getElementById('textItems');
  const countEl   = document.getElementById('textCount');
  const btnAdd    = document.getElementById('btnAdd');
  const btnSave   = document.getElementById('btnSave');
  const statusMsg = document.getElementById('statusMsg');

  const loginOverlay = document.getElementById('loginOverlay');
  const loginInput   = document.getElementById('loginPassword');
  const loginError   = document.getElementById('loginError');
  const loginSubmit  = document.getElementById('loginSubmit');

  // ── State ─────────────────────────────────────────────────────────────
  let texts = [];

  // ── Render the text list ──────────────────────────────────────────────
  function render() {
    container.innerHTML = '';
    texts.forEach((t, i) => {
      const div = document.createElement('div');
      div.className = 'text-item';
      div.innerHTML = `
        <span class="drag-handle"><i class="fas fa-grip-vertical"></i></span>
        <input type="text" value="${escapeHtml(t)}" data-index="${i}" />
        <button class="remove-btn" data-index="${i}" title="删除"><i class="fas fa-times"></i></button>
      `;
      container.appendChild(div);

      // Input change → update texts array
      const input = div.querySelector('input');
      input.addEventListener('input', () => {
        texts[i] = input.value;
        updateCount();
      });

      // Remove
      const removeBtn = div.querySelector('.remove-btn');
      removeBtn.addEventListener('click', () => {
        texts.splice(i, 1);
        render();
      });
    });
    updateCount();
  }

  function updateCount() {
    countEl.textContent = texts.length;
  }

  function escapeHtml(str) {
    const d = document.createElement('div');
    d.textContent = str;
    return d.innerHTML;
  }

  // ── Show status message ───────────────────────────────────────────────
  function showStatus(msg, type) {
    statusMsg.className = 'status-msg ' + type;
    statusMsg.textContent = msg;
    setTimeout(() => {
      statusMsg.className = 'status-msg';
    }, 4000);
  }

  // ── Load texts from API ──────────────────────────────────────────────
  async function loadTexts() {
    try {
      const resp = await fetch('/api/scroller/texts');
      if (resp.ok) {
        const data = await resp.json();
        texts = data.texts || [];
        render();
      }
    } catch (e) {
      showStatus('加载背景词失败: ' + e.message, 'error');
    }
  }

  // ── Check if the feature is available (password configured) ────────────
  async function checkFeatureEnabled() {
    try {
      const resp = await fetch('/api/scroller/texts');
      if (resp.ok) return true;
      const data = await resp.json().catch(() => ({}));
      showStatus('❌ 功能不可用: ' + (data.detail || '无法访问'), 'error');
      btnSave.disabled = true;
      btnAdd.disabled = true;
      return false;
    } catch {
      return false;
    }
  }

  // ── Save texts via API ────────────────────────────────────────────────
  async function saveTexts() {
    btnSave.disabled = true;
    btnSave.innerHTML = '<i class="fas fa-spinner fa-pulse"></i> 保存中...';

    try {
      // Cookie is sent automatically by the browser; no header needed
      const resp = await fetch('/api/scroller/texts', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ texts }),
      });

      if (resp.status === 401 || resp.status === 403) {
        // Cookie expired or invalid – re-prompt login
        showLogin(() => saveTexts());
        return;
      }

      if (resp.ok) {
        const data = await resp.json();
        texts = data.texts || [];
        render();
        showStatus('✅ 保存成功！共 ' + texts.length + ' 条背景词，刷新首页即可看到效果', 'success');
      } else {
        const err = await resp.json().catch(() => ({ detail: '未知错误' }));
        showStatus('❌ 保存失败: ' + (err.detail || resp.statusText), 'error');
      }
    } catch (e) {
      showStatus('❌ 保存失败: ' + e.message, 'error');
    } finally {
      btnSave.disabled = false;
      btnSave.innerHTML = '<i class="fas fa-save"></i> 保存修改';
    }
  }

  // ── Login overlay ─────────────────────────────────────────────────────
  function showLogin(callback) {
    loginOverlay.style.display = 'flex';
    loginInput.value = '';
    loginError.textContent = '';
    loginInput.focus();

    // Remove old listeners to avoid stacking
    const newLoginSubmit = loginSubmit.cloneNode(true);
    loginSubmit.parentNode.replaceChild(newLoginSubmit, loginSubmit);

    async function doLogin() {
      const pwd = loginInput.value.trim();
      if (!pwd) {
        loginError.textContent = '请输入密码';
        return;
      }

      loginError.textContent = '验证中...';
      try {
        const resp = await fetch('/api/scroller/login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ password: pwd }),
        });

        if (resp.ok) {
          // HttpOnly cookie is now set by the server
          loginOverlay.style.display = 'none';
          if (callback) callback();
        } else {
          const err = await resp.json().catch(() => ({ detail: '密码错误' }));
          loginError.textContent = err.detail || '密码错误，请重试';
        }
      } catch (e) {
        loginError.textContent = '网络错误，请重试';
      }
    }

    newLoginSubmit.addEventListener('click', doLogin);
    loginInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') doLogin();
    });
  }

  // ── Events ────────────────────────────────────────────────────────────

  // Add new text
  btnAdd.addEventListener('click', () => {
    texts.push('新词');
    render();
    // Focus the last input
    const inputs = container.querySelectorAll('input');
    if (inputs.length > 0) inputs[inputs.length - 1].focus();
  });

  // Save
  btnSave.addEventListener('click', saveTexts);

  // ── Init ──────────────────────────────────────────────────────────────
  loadTexts();
  checkFeatureEnabled();

})();
