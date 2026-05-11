/**
 * SNH48 Q&A System - Frontend Interaction
 *
 * Handles the AI Q&A page: checks KB status, sends questions, displays results.
 */
(function() {
  'use strict';

  const statusEl = document.getElementById('kbStatus');
  const inputEl = document.getElementById('qaInput');
  const submitEl = document.getElementById('qaSubmit');
  const resultEl = document.getElementById('qaResult');

  if (!statusEl || !inputEl || !submitEl || !resultEl) return;

  // ── Check KB Status on Load ───────────────────────────────────────────
  let kbReady = false;

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
        inputEl.disabled = false;
        submitEl.disabled = false;
        inputEl.focus();
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
        <span>正在思考中，请稍候...</span>
      </div>`;

    try {
      const resp = await fetch('/api/qa/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question }),
      });

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
