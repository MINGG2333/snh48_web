/**
 * SNH48 Q&A System - Frontend Interaction
 *
 * Handles the AI Q&A page: password login, KB status check, sends questions, displays results.
 */
(function() {
  'use strict';

  // ── State ──────────────────────────────────────────────────────────────
  let sitePassword = sessionStorage.getItem('site_password') || '';
  let kbReady = false;

  const statusEl = document.getElementById('kbStatus');
  const inputEl = document.getElementById('qaInput');
  const submitEl = document.getElementById('qaSubmit');
  const resultEl = document.getElementById('qaResult');
  const loginOverlay = document.getElementById('loginOverlay');
  const loginInput = document.getElementById('loginPassword');
  const loginBtn = document.getElementById('loginSubmit');
  const loginError = document.getElementById('loginError');

  if (!statusEl || !inputEl || !submitEl || !resultEl) return;

  // ── Password Login ────────────────────────────────────────────────────
  async function verifyPassword(password) {
    try {
      const resp = await fetch('/api/qa/verify-password', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ password }),
      });
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        throw new Error(err.detail || '密码错误');
      }
      const data = await resp.json();
      return data.verified;
    } catch (err) {
      throw err;
    }
  }

  // Check if password is needed and handle login
  async function checkPassword() {
    // First check if the feature is enabled and if password is configured
    try {
      const resp = await fetch('/api/qa/verify-password', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ password: '' }),
      });
      if (resp.ok) {
        const data = await resp.json();
        if (data.verified) {
          // No password set → proceed
          return true;
        }
      }
      // If we get here with status code, it means password is required
      const errData = await resp.json().catch(() => ({}));
      if (resp.status === 403 && resp.statusText) {
        // Feature disabled or password wrong
        throw { status: resp.status, detail: errData.detail || '' };
      }
    } catch (e) {
      if (e && e.detail && e.detail.includes('功能未启用')) {
        // Feature is disabled – show a clear message
        if (statusEl) {
          statusEl.innerHTML = '<i class="fas fa-exclamation-triangle" style="color:#fbbf24;"></i> ' + e.detail;
          statusEl.style.display = 'block';
        }
        return false; // Feature disabled, don't show login
      }
      // Password is configured (normal case)
    }

    // Try stored password
    if (sitePassword) {
      try {
        const ok = await verifyPassword(sitePassword);
        if (ok) return true;
      } catch (e) {
        // Stored password is invalid, clear it
        sessionStorage.removeItem('site_password');
        sitePassword = '';
      }
    }

    // Show login prompt
    if (loginOverlay) {
      loginOverlay.style.display = 'flex';
      loginInput.value = '';
      loginInput.focus();
    }
    return false;
  }

  function getStoredPassword() {
    return sitePassword;
  }

  // ── Auth Header Helper ────────────────────────────────────────────────
  function authHeaders() {
    const headers = { 'Content-Type': 'application/json' };
    if (sitePassword) {
      headers['X-Site-Password'] = sitePassword;
    }
    return headers;
  }

  // ── Check KB Status on Load ───────────────────────────────────────────
  async function checkStatus() {
    try {
      const resp = await fetch('/api/qa/status');
      const data = await resp.json();

      if (data.ready) {
        kbReady = true;
        statusEl.className = 'qa-status ready';
        statusEl.innerHTML = `<i class="fas fa-check-circle"></i> 知识库已就绪
          （${data.stats?.segment_count || '?'} 个片段）
          <button class="btn" style="margin-left:12px;padding:4px 12px;font-size:0.8rem"
                  onclick="window.location.reload()">
            <i class="fas fa-sync"></i> 刷新
          </button>`;

        // Now check if password verification is needed
        const authed = await checkPassword();
        if (authed) {
          inputEl.disabled = false;
          submitEl.disabled = false;
          inputEl.focus();
          inputEl.placeholder = '为什么房间名叫葬爱家族？';
        }
      } else {
        kbReady = false;
        statusEl.className = 'qa-status not-ready';
        statusEl.innerHTML = `<i class="fas fa-exclamation-triangle"></i>
          知识库未就绪：${data.message || '请先构建知识库'}
          <br><small>请先在终端运行 <code>python run_kb_qa.py build</code> 构建知识库</small>`;
        inputEl.disabled = true;
        submitEl.disabled = true;
      }
    } catch (err) {
      statusEl.className = 'qa-status error';
      statusEl.innerHTML = `<i class="fas fa-times-circle"></i>
        无法连接到服务器 (${err.message})`;
      inputEl.disabled = true;
      submitEl.disabled = true;
    }
  }

  // ── Send Question ────────────────────────────────────────────────────
  async function askQuestion(question) {
    resultEl.innerHTML = `
      <div class="qa-loading">
        <div class="spinner"></div>
        <span>正在检索并思考中，请稍候（每个问题花费约5分钟）...</span>
      </div>`;

    try {
      const resp = await fetch('/api/qa/ask', {
        method: 'POST',
        headers: authHeaders(),
        body: JSON.stringify({ question }),
      });

      if (resp.status === 401 || resp.status === 403) {
        // Password expired or invalid
        sessionStorage.removeItem('site_password');
        sitePassword = '';
        if (loginOverlay) {
          loginOverlay.style.display = 'flex';
          loginError.textContent = '密码已过期或无效，请重新输入';
          loginInput.value = '';
          loginInput.focus();
        }
        return;
      }

      if (!resp.ok) {
        const errData = await resp.json().catch(() => ({}));
        throw new Error(errData.detail || `请求失败 (${resp.status})`);
      }

      const data = await resp.json();
      displayResult(data);
    } catch (err) {
      resultEl.innerHTML = `
        <div class="qa-status error">
          <i class="fas fa-times-circle"></i> 问答失败：${err.message}
        </div>`;
    }
  }

  // ── Display Result ───────────────────────────────────────────────────
  function displayResult(data) {
    const hasAnswer = data.answer && data.answer.length > 0;
    const hasCitations = data.citations && data.citations.length > 0;

    let html = '';

    // Answer
    html += `<div class="qa-answer">`;
    html += `<h3><i class="fas fa-comment-dots"></i> 回答</h3>`;
    if (hasAnswer) {
      // Format citations: replace [#N] with styled spans
      let answerText = data.answer;
      answerText = answerText.replace(/\[#(\d+)\]/g, (match, num) => {
        return `<a href="#citation-${num}" class="citation-ref" style="
          color: var(--primary); font-weight: 700; text-decoration: none;
          cursor: pointer;
        " title="查看引用 #${num}">${match}</a>`;
      });
      html += `<div>${answerText}</div>`;
    } else {
      html += `<p style="color: var(--text-dim);">未返回有效答案。</p>`;
    }
    html += `</div>`;

    // Citations
    if (hasCitations) {
      html += `<div class="qa-citations">`;
      html += `<h3><i class="fas fa-book-open"></i> 引用列表 (${data.citations.length})</h3>`;
      for (const cit of data.citations) {
        html += `<div class="citation-item" id="citation-${cit.citation_id?.replace('#', '') || '0'}">`;
        html += `<div class="citation-id">${cit.citation_id || '#'}</div>`;
        html += `<div class="citation-meta">`;
        html += `<span>${cit.source_type || ''}</span>`;
        if (cit.video_offset) html += ` · 视频内: ${cit.video_offset}`;
        if (cit.absolute_time) html += ` · ${cit.absolute_time}`;
        html += `</div>`;
        if (cit.video_title) html += `<div class="citation-meta">📺 ${cit.video_title}</div>`;
        html += `<div class="citation-text">“${cit.quoted_text || ''}”</div>`;
        if (cit.reason) html += `<div class="citation-meta" style="margin-top:4px;font-style:italic;">📝 ${cit.reason}</div>`;
        html += `</div>`;
      }
      html += `</div>`;
    }

    resultEl.innerHTML = html;
  }

  // ── Login Event Handlers ─────────────────────────────────────────────
  if (loginBtn && loginInput && loginOverlay) {
    loginBtn.addEventListener('click', async () => {
      const pwd = loginInput.value.trim();
      if (!pwd) {
        loginError.textContent = '请输入密码';
        return;
      }
      loginBtn.disabled = true;
      loginBtn.textContent = '验证中...';
      loginError.textContent = '';

      try {
        const ok = await verifyPassword(pwd);
        if (ok) {
          sitePassword = pwd;
          sessionStorage.setItem('site_password', pwd);
          loginOverlay.style.display = 'none';
          inputEl.disabled = false;
          submitEl.disabled = false;
          inputEl.focus();
          inputEl.placeholder = '为什么房间名叫葬爱家族？';
        }
      } catch (err) {
        loginError.textContent = '密码错误，请重试';
      } finally {
        loginBtn.disabled = false;
        loginBtn.textContent = '确认';
      }
    });

    loginInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        loginBtn.click();
      }
    });
  }

  // ── Event Listeners ──────────────────────────────────────────────────
  submitEl.addEventListener('click', () => {
    const question = inputEl.value.trim();
    if (!question) return;
    askQuestion(question);
  });

  inputEl.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !submitEl.disabled) {
      submitEl.click();
    }
  });

  // ── Init ──────────────────────────────────────────────────────────────
  checkStatus();
})();
