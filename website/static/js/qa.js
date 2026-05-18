/**
 * SNH48 Q&A System - Frontend Interaction
 *
 * Handles the AI Q&A page: password login, KB status check, async polling for results.
 * Shows real-time timer, gracefully handles nginx timeout with email collection.
 */
(function() {
  'use strict';

  // ── Config ──────────────────────────────────────────────────────────────
  const TIMEOUT_SECONDS = 300;       // nginx proxy_read_timeout
  const POLL_INTERVAL_MS = 3000;     // poll every 3 seconds
  const WARN_SECONDS = 240;          // show warning at 4 minutes
  const MAX_QUESTION_LENGTH = 20;    // max meaningful chars allowed
  // Allowed characters in a question (whitelist)
  const QUESTION_ALLOWED_RE = /^[\u4e00-\u9fff a-zA-Z0-9，。！？、；：""''（）【】《》—…·,.?!;:()\[\]{}\-～~\s]+$/;
  // Count only meaningful chars: Chinese, English letters, digits
  function countMeaningful(str) {
    const m = str.match(/[\u4e00-\u9fffa-zA-Z0-9]/g);
    return m ? m.length : 0;
  }
  // Check for disallowed special symbols
  function hasBadChars(str) {
    return !QUESTION_ALLOWED_RE.test(str);
  }

  // ── State ────────────────────────────────────────────────────────────────
  let sitePassword = '';       // 仅内存变量，刷新后需重新输入密码
  let kbReady = false;
  let timerInterval = null;
  let pollInterval = null;
  let startTime = null;

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

    // Always show login prompt — password is not stored across refreshes
    if (loginOverlay) {
      loginOverlay.style.display = 'flex';
      loginInput.value = '';
      loginInput.focus();
    }
    return false;
  }

  // ── Client ID ──────────────────────────────────────────────────────────
  // Generate a random client_id to identify this user session
  let clientId = sessionStorage.getItem('client_id');
  if (!clientId) {
    clientId = 'user_' + Math.random().toString(36).substring(2, 10) + '_' + Date.now().toString(36);
    sessionStorage.setItem('client_id', clientId);
  }

  // ── Auth Header Helper ────────────────────────────────────────────────
  function authHeaders() {
    const headers = {
      'Content-Type': 'application/json',
      'X-Client-Id': clientId,
    };
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

  // ── Timer Display ─────────────────────────────────────────────────────
  function formatElapsed(seconds) {
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return `${m}分${s}秒`;
  }

  function updateTimer(seconds) {
    const timerEl = document.getElementById('qaTimer');
    if (!timerEl) return;
    timerEl.textContent = formatElapsed(seconds);

    if (seconds >= TIMEOUT_SECONDS) {
      timerEl.className = 'qa-timer timeout';
    } else if (seconds >= WARN_SECONDS) {
      timerEl.className = 'qa-timer warn';
    } else {
      timerEl.className = 'qa-timer';
    }
  }

  function stopTimers() {
    if (timerInterval) {
      clearInterval(timerInterval);
      timerInterval = null;
    }
    if (pollInterval) {
      clearInterval(pollInterval);
      pollInterval = null;
    }
  }

  // ── Show Timeout / Email Form ─────────────────────────────────────────
  function showTimeoutForm(taskId, question, elapsed) {
    const timerWrap = document.getElementById('qaTimerWrap');
    if (timerWrap) timerWrap.style.display = 'none';

    resultEl.innerHTML = `
      <div class="qa-timeout-card">
        <div class="qa-timeout-icon">
          <i class="fas fa-hourglass-end"></i>
        </div>
        <h3>处理超时提示</h3>
        <p>您的提问「<strong>${escapeHtml(question)}</strong>」处理已超过 <strong>${formatElapsed(elapsed)}</strong>。</p>
        <p><strong>原因：</strong>LLM 分析耗时较长（超过 nginx 代理的超时限制 5 分钟），所以页面无法直接显示结果。</p>
        <p><strong>但服务端仍在继续处理中！</strong>处理完成后，结果会自动保存。</p>
        <div class="qa-email-section">
          <label for="timeoutEmail">如需获取最终处理结果，请留下您的邮箱：</label>
          <div class="qa-email-row">
            <input type="email" id="timeoutEmail" class="qa-input" placeholder="example@email.com"
                   style="flex:1; margin-right:8px;">
            <button class="qa-submit" onclick="window._qaLeaveEmail('${taskId}')" id="emailSubmitBtn">
              <i class="fas fa-paper-plane"></i> 提交
            </button>
          </div>
          <p class="qa-email-hint">提交后，处理完成时会通过存档路径获取结果。</p>
          <div id="emailFeedback" style="margin-top:8px;font-size:0.9rem;"></div>
        </div>
        <div class="qa-poll-again" style="margin-top:16px;">
          <button class="btn" onclick="window._qaRetryPoll('${taskId}')">
            <i class="fas fa-redo"></i> 再次尝试获取结果
          </button>
          <span style="color:var(--text-dim);font-size:0.85rem;margin-left:8px;">结果可能随时返回</span>
        </div>
      </div>`;
  }

  // ── Escape HTML ───────────────────────────────────────────────────────
  function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

  // ── Comprehensiveness Banner ──────────────────────────────────────────
  function buildComprehensivenessBanner(comp, question) {
    if (!comp || comp.ratio === undefined) return '';
    const ratio = comp.ratio;
    const pct = Math.round(ratio * 100);
    const surveyTotal = comp.survey_total_relevant || 0;
    const usedCount = comp.used_base_count || 0;

    // Only show warning if ratio is significantly below 100%
    if (ratio >= 0.95) return '';

    // Severity classes for styling
    let severity = 'low';
    let icon = 'fa-info-circle';
    if (pct < 30) {
      severity = 'high';
      icon = 'fa-exclamation-triangle';
    } else if (pct < 60) {
      severity = 'medium';
      icon = 'fa-exclamation-circle';
    }

    const summaryText = surveyTotal > 0
      ? `预估相关片段共约 ${surveyTotal} 段，当前分析使用了其中 ${usedCount} 段`
      : `当前分析使用了 ${usedCount} 段相关片段`;

    // Use the actual query keywords for the "high-frequency keywords" explanation
    const bm25Query = comp.bm25_query || '';
    const keywordHint = bm25Query
      ? `对于包含高频关键词"${escapeHtml(bm25Query)}"的问题，可能因数据量过大而未能全面覆盖所有相关片段。`
      : '对于包含高频关键词的问题，可能因数据量过大而未能全面覆盖所有相关片段。';

    // Generate a stable email subject / identifier
    const questionForEmail = encodeURIComponent(question || '未指定问题');

    return `
      <div class="qa-comp-banner qa-comp-banner--${severity}">
        <div class="qa-comp-header">
          <i class="fas ${icon}"></i>
          <span>回答全面性提醒</span>
        </div>
        <div class="qa-comp-body">
          <p><strong>本回答仅分析了预估相关内容的 ${pct}%</strong>，${summaryText}。</p>
          <p>${keywordHint}</p>
        </div>
        <div class="qa-email-section">
          <label for="compEmail">如需获取更全面的回答，请留下您的邮箱和问题：</label>
          <div class="qa-email-row">
            <input type="email" id="compEmail" class="qa-input" placeholder="your@email.com"
                   style="flex:1; margin-right:8px;">
            <button class="qa-submit" onclick="window._qaCompRequest('${questionForEmail}')">
              <i class="fas fa-paper-plane"></i> 提交请求
            </button>
          </div>
          <p class="qa-email-hint">提交后，管理员会尽快为您提供更全面的回答。</p>
          <div id="compEmailFeedback" style="margin-top:8px;font-size:0.9rem;"></div>
        </div>
      </div>`;
  }

  // Global: handle comprehensiveness email request
  window._qaCompRequest = function(encodedQuestion) {
    const emailInput = document.getElementById('compEmail');
    const feedback = document.getElementById('compEmailFeedback');
    const email = emailInput ? emailInput.value.trim() : '';
    const question = decodeURIComponent(encodedQuestion);

    if (!email) {
      if (feedback) feedback.innerHTML = '<span style="color:#fbbf24;">请输入邮箱地址</span>';
      return;
    }
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      if (feedback) feedback.innerHTML = '<span style="color:#ef4444;">邮箱格式不正确</span>';
      return;
    }

    if (feedback) feedback.innerHTML = '<span style="color:#4ade80;"><i class="fas fa-check-circle"></i> 已记录！感谢您的反馈。</span>';

    fetch('/api/qa/archive-email', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ task_id: 'comprehensiveness_request', email, question }),
    }).catch(() => {});
  };

  // ── QR Code Generation ──────────────────────────────────────────────
  function generateQRCode(url, size) {
    try {
      const typeNumber = 0; // auto-detect
      const errorCorrectionLevel = 'H'; // High error correction
      const qr = qrcode(typeNumber, errorCorrectionLevel);
      qr.addData(url);
      qr.make();
      return qr.createImgTag(size, size, ' margin: 0 auto; display: block;');
    } catch (e) {
      console.warn('QR generation failed:', e);
      return '';
    }
  }

  // ── Download as Image (Screenshot) ──────────────────────────────────
  function getSiteUrl() {
    return window.location.protocol + '//' + window.location.host;
  }

  // ── Trigger file download (cross-browser compatible) ────────────────
  function triggerDownload(blob, filename) {
    if (window.navigator && window.navigator.msSaveBlob) {
      window.navigator.msSaveBlob(blob, filename);
      return;
    }
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    setTimeout(() => {
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
    }, 100);
  }

  async function downloadAsImage() {
    const resultEl = document.getElementById('qaResult');
    const shareBtn = document.getElementById('qaShareBtn');
    if (!resultEl || resultEl.children.length === 0) return;

    // ── Show immediate loading feedback ──
    if (shareBtn) {
      shareBtn.disabled = true;
      shareBtn.innerHTML = '<i class="fas fa-spinner fa-pulse"></i> 正在生成截图...';
    }

    // Let the UI update before heavy work
    await new Promise(r => setTimeout(r, 50));

    try {
      // ── Step 1: Build an off-screen wrapper ──
      const wrapper = document.createElement('div');
      wrapper.style.cssText = [
        'background: #0a0a1a;',
        'padding: 24px;',
        'border-radius: 16px;',
        "font-family: 'Noto Sans SC', -apple-system, BlinkMacSystemFont, sans-serif;",
        'color: #f0f0f0;',
        'font-size: 16px;',
        'line-height: 1.8;',
        'position: absolute;',
        'left: -9999px;',
        'top: 0;',
        'width: 780px;',
      ].join(' ');
      document.body.appendChild(wrapper);

      // ── Step 2: Clone result content (keep all info, no truncation) ──
      const clone = resultEl.cloneNode(true);

      // Remove the share button area from the clone
      const shareArea = clone.querySelector('.qa-share-area');
      if (shareArea) shareArea.remove();

      // Remove comprehensiveness banner (email form is interactive)
      const compBanner = clone.querySelector('.qa-comp-banner');
      if (compBanner) compBanner.remove();

      // Fix link-based citation refs to static styled text (can't click in image)
      const citationRefs = clone.querySelectorAll('.citation-ref');
      citationRefs.forEach(el => {
        el.style.color = '#ff6b9d';
        el.style.fontWeight = '700';
        el.style.textDecoration = 'none';
        el.style.cursor = 'default';
        el.removeAttribute('href');
      });

      wrapper.appendChild(clone);

      // ── Step 3: Build footer with QR code ──
      const footer = document.createElement('div');
      footer.style.cssText = [
        'margin-top: 24px;',
        'padding-top: 18px;',
        'border-top: 1px solid rgba(255,255,255,0.12);',
        'display: flex;',
        'align-items: center;',
        'gap: 14px;',
        'text-align: left;',
      ].join(' ');
      const qrContainer = document.createElement('div');
      const siteUrl = getSiteUrl();
      const qrHtml = generateQRCode(siteUrl, 80);
      qrContainer.innerHTML = qrHtml;
      qrContainer.style.flexShrink = '0';
      footer.appendChild(qrContainer);
      const info = document.createElement('div');
      info.style.cssText = [
        'flex: 1;',
        'font-size: 0.8rem;',
        'color: rgba(255,255,255,0.5);',
        'line-height: 1.5;',
      ].join(' ');
      const question = document.getElementById('qaInput')?.value?.trim() || '';
      info.innerHTML = [
        '<div style="font-size:0.9rem;color:rgba(255,255,255,0.7);font-weight:500;margin-bottom:4px;">',
        '  <i class="fas fa-star" style="color:#ff6b9d;"></i> AI 智能问答',
        '</div>',
        '<div>' + (question ? 'Q: ' + escapeHtml(question) : '') + '</div>',
        '<div style="margin-top:3px;">扫描二维码访问网站 · ' + siteUrl + '</div>',
        '<div style="margin-top:1px;font-size:0.72rem;">生成时间：' + new Date().toLocaleString('zh-CN') + '</div>',
      ].join('');
      footer.appendChild(info);
      wrapper.appendChild(footer);

      // ── Step 4: Wait for layout to settle ──
      await new Promise(r => setTimeout(r, 200));

      // ── Step 5: Capture at 1x to avoid exceeding browser canvas limits ──
      // For very long content (82+ citations), higher scale values cause
      // the canvas to exceed browser maximum dimensions (typically 16384px).
      // We capture at 1x first, then upscale the result for crisp text.
      const rawCanvas = await html2canvas(wrapper, {
        scale: 1,
        useCORS: true,
        backgroundColor: '#0a0a1a',
        allowTaint: true,
        logging: false,
        width: wrapper.scrollWidth,
        height: wrapper.scrollHeight,
        windowWidth: wrapper.scrollWidth,
        windowHeight: wrapper.scrollHeight,
      });

      // Clean up the temporary wrapper
      document.body.removeChild(wrapper);

      // ── Step 6: Upscale canvas 2x for crisp text ──
      // Create a new canvas at 2x the dimensions and draw the original onto it
      const upscaleFactor = 2;
      const finalCanvas = document.createElement('canvas');
      finalCanvas.width = rawCanvas.width * upscaleFactor;
      finalCanvas.height = rawCanvas.height * upscaleFactor;
      const ctx = finalCanvas.getContext('2d');
      // Use image smoothing for better quality when upscaling
      ctx.imageSmoothingEnabled = true;
      ctx.imageSmoothingQuality = 'high';
      ctx.scale(upscaleFactor, upscaleFactor);
      ctx.drawImage(rawCanvas, 0, 0);

      // ── Step 7: Download PNG ──
      const filename = 'AI问答_' + new Date().toISOString().slice(0, 19).replace(/[:-]/g, '') + '.png';

      // Wrap toBlob in a Promise to ensure it completes before finally block
      await new Promise(function(resolve) {
        finalCanvas.toBlob(function(blob) {
          if (blob && blob.size > 0) {
            triggerDownload(blob, filename);
          } else {
            // Fallback: try toDataURL
            try {
              var dataUrl = finalCanvas.toDataURL('image/png');
              if (dataUrl && dataUrl.length > 100) {
                var link = document.createElement('a');
                link.download = filename;
                link.href = dataUrl;
                link.click();
              } else {
                console.error('Screenshot failed: empty canvas data');
                alert('截图生成失败，图片内容为空。请尝试减少引用数量后重试。');
              }
            } catch (e) {
              console.error('toDataURL fallback failed:', e);
              alert('截图保存失败：浏览器画布尺寸超限。请尝试减少引用数量后重试。');
            }
          }
          resolve();
        }, 'image/png');
      });
    } catch (err) {
      console.error('Screenshot failed:', err);
      // Check for common canvas size errors
      if (err.message && (err.message.indexOf('size') > -1 || err.message.indexOf('limit') > -1 || err.message.indexOf('maximum') > -1)) {
        alert('截图保存失败：内容过长超出浏览器画布尺寸限制。');
      } else {
        alert('截图保存失败，请重试。错误信息：' + err.message);
      }
    } finally {
      if (shareBtn) {
        shareBtn.disabled = false;
        shareBtn.innerHTML = '<i class="fas fa-download"></i> 保存为图片';
      }
    }
  }

  // ── Display Result ───────────────────────────────────────────────────
  function displayResult(data) {
    stopTimers();
    const hasAnswer = data.answer && data.answer.length > 0;
    const hasCitations = data.citations && data.citations.length > 0;
    const elapsed = data.completed_at && data.created_at
      ? Math.round((new Date(data.completed_at) - new Date(data.created_at)) / 1000)
      : 0;

    let html = '';

    // Elapsed time info
    html += `<div style="text-align:right;font-size:0.85rem;color:var(--text-dim);margin-bottom:8px;">
      <i class="fas fa-clock"></i> 处理耗时：${formatElapsed(elapsed)}</div>`;

    // ── Compliance notice (below processing time, above answer) ──
    html += `<div class="qa-compliance-notice" style="margin: 0 0 12px 0; padding: 10px 14px; background: rgba(255, 107, 157, 0.08); border: 1px solid rgba(255, 107, 157, 0.15); border-radius: 8px; font-size: 0.85rem; color: var(--text-dim); display: flex; align-items: flex-start; gap: 8px;">
      <i class="fas fa-shield-alt" style="color: var(--primary); margin-top: 2px; flex-shrink: 0;"></i>
      <span>本服务使用生成式人工智能技术，生成内容仅供参考，不代表陈嘉仪本人立场，请理性看待。</span>
    </div>`;

    // Answer
    html += `<div class="qa-answer">`;
    html += `<h3><i class="fas fa-comment-dots"></i> 回答</h3>`;

    if (hasAnswer) {
      // Format citations: replace [#N] with styled spans
      let answerText = data.answer;
      let citationRefIndex = 0;
      answerText = answerText.replace(/\[#(\d+)\]/g, (match, num) => {
        citationRefIndex++;
        return `<a href="#citation-${num}" class="citation-ref" data-ref-index="${citationRefIndex}" style="
          color: var(--primary); font-weight: 700; text-decoration: none;
          cursor: pointer;
        " title="查看引用 #${num}">${match}</a>`;
      });
      html += `<div id="qaAnswerText">${answerText}</div>`;

    } else {
      html += `<p style="color: var(--text-dim);">未返回有效答案。</p>`;
    }
    html += `</div>`;

    // Citations

    if (hasCitations) {
      html += `<div class="qa-citations">`;
      html += `<h3><i class="fas fa-book-open"></i> 引用列表 (${data.citations.length})</h3>`;
      for (const cit of data.citations) {
        const citId = cit.citation_id?.replace('#', '') || '0';
        html += `<div class="citation-item" id="citation-${citId}">`;
        html += `<div class="citation-id">${cit.citation_id || '#'}</div>`;
        html += `<div class="citation-meta">`;
        html += `<span>${cit.source_type || ''}</span>`;
        if (cit.video_offset) html += ` · 视频内: ${cit.video_offset}`;
        if (cit.absolute_time) html += ` · ${cit.absolute_time}`;
        html += `</div>`;
        if (cit.video_title) html += `<div class="citation-meta">📺 ${cit.video_title}</div>`;
        html += `<div class="citation-text">“${cit.quoted_text || ''}”</div>`;
        if (cit.reason) html += `<div class="citation-meta" style="margin-top:4px;font-style:italic;">📝 ${cit.reason}</div>`;
        // Back-to-answer link
        html += `<div class="citation-back"><a href="#qaAnswerText" class="citation-back-link" data-citation-id="${citId}"><i class="fas fa-arrow-up"></i> 回到回答</a></div>`;
        html += `</div>`;
      }
      html += `</div>`;
    }


    // Comprehensiveness warning banner (after the citation list)
    if (data.comprehensiveness) {
      html += buildComprehensivenessBanner(data.comprehensiveness, data.question || '');
    }

    // ── AI Generated Content Disclaimer (after citation list) ──
    html += `<div class="qa-answer-disclaimer">
      <i class="fas fa-robot"></i> 以上内容由人工智能（AI）生成，仅供参考，不代表陈嘉仪本人立场。请结合其他信息源自行判断。
    </div>`;

    // ── Share / Save as Image button ──

    html += `<div class="qa-share-area">
      <button id="qaShareBtn" class="qa-share-btn" onclick="window._qaDownloadImage()">
        <i class="fas fa-download"></i> 保存为图片
      </button>
    </div>`;

    resultEl.innerHTML = html;

    // Helper: smooth scroll to element with navbar offset
    function smoothScrollTo(el) {
      const navHeight = 80; // navbar height + some padding
      const targetPos = el.getBoundingClientRect().top + window.scrollY - navHeight;
      window.scrollTo({ top: targetPos, behavior: 'smooth' });
    }

    // Click handler for "back to answer" links — also highlight the corresponding citation ref
    resultEl.querySelectorAll('.citation-back-link').forEach(link => {
      link.addEventListener('click', (e) => {
        e.preventDefault();
        const targetId = link.getAttribute('href').substring(1);
        const targetEl = document.getElementById(targetId);
        if (targetEl) {
          smoothScrollTo(targetEl);
          // Highlight the corresponding citation ref in the answer
          const citId = link.getAttribute('data-citation-id');
          const refLink = targetEl.querySelector(`.citation-ref[href="#citation-${citId}"]`);
          if (refLink) {
            refLink.classList.add('citation-ref--highlight');
            setTimeout(() => refLink.classList.remove('citation-ref--highlight'), 2000);
          }
        }
      });
    });


    // Click handler for citation refs ([#N] links) — scroll to middle of viewport + highlight
    resultEl.querySelectorAll('.citation-ref').forEach(link => {
      link.addEventListener('click', (e) => {
        e.preventDefault();
        const targetId = link.getAttribute('href').substring(1);
        const targetEl = document.getElementById(targetId);
        if (targetEl) {
          // Scroll to middle of viewport
          const targetPos = targetEl.getBoundingClientRect().top + window.scrollY - (window.innerHeight / 2) + (targetEl.offsetHeight / 2);
          window.scrollTo({ top: targetPos, behavior: 'smooth' });
          // Highlight the citation item
          targetEl.classList.add('citation-item--highlight');
          setTimeout(() => targetEl.classList.remove('citation-item--highlight'), 2000);
        }
      });
    });


    resultEl.scrollIntoView({ behavior: 'smooth', block: 'start' });

  }


  // ── Global: Download Image ────────────────────────────────────────────
  window._qaDownloadImage = downloadAsImage;

  // ── Poll for Result ──────────────────────────────────────────────────
  async function pollResult(taskId, question) {
    try {
      const resp = await fetch(`/api/qa/ask-async/${taskId}`);
      if (!resp.ok) {
        throw new Error(`轮询失败 (${resp.status})`);
      }
      const data = await resp.json();

      if (data.status === 'completed') {
        displayResult(data);
        return true;  // done
      }

      if (data.status === 'error') {
        resultEl.innerHTML = `
          <div class="qa-status error">
            <i class="fas fa-times-circle"></i> 问答处理失败：${escapeHtml(data.error || '未知错误')}
          </div>`;
        stopTimers();
        return true;
      }

      return false;  // still processing
    } catch (err) {
      // Could be a network error (e.g., nginx timeout), ignore and keep polling
      console.warn('Poll error:', err);
      return false;
    }
  }

  // ── Send Question (Async) ────────────────────────────────────────────
  async function askQuestionAsync(question) {
    stopTimers();

    // Show loading with timer
    resultEl.innerHTML = `
      <div class="qa-loading">
        <div class="spinner"></div>
        <div>
          <span>正在检索并思考中，请稍候...</span>
          <div id="qaTimerWrap" style="margin-top:8px;">
            <span id="qaTimer" class="qa-timer">0分0秒</span>
            <span style="color:var(--text-dim);font-size:0.85rem;margin-left:8px;">
              （每个问题预计需要约 5 分钟，超过 5 分钟将不在页面直接回复）
            </span>
          </div>
        </div>
      </div>`;

    try {
      // Step 1: Submit async task
      const submitResp = await fetch('/api/qa/ask-async', {
        method: 'POST',
        headers: authHeaders(),
        body: JSON.stringify({ question }),
      });

      if (submitResp.status === 401 || submitResp.status === 403) {
        sitePassword = '';
        if (loginOverlay) {
          loginOverlay.style.display = 'flex';
          loginError.textContent = '密码已过期或无效，请重新输入';
          loginInput.value = '';
          loginInput.focus();
        }
        return;
      }

      if (!submitResp.ok) {
        const errData = await submitResp.json().catch(() => ({}));
        const errMsg = errData.detail || `请求失败 (${submitResp.status})`;
        // 429 限速提示用温和友好的风格展示
        if (submitResp.status === 429) {
          stopTimers();
          const friendly = friendlyLimitHint(errMsg);
          resultEl.innerHTML = `
            <div class="qa-rate-limited" style="
              background: rgba(251, 191, 36, 0.12); border: 1px solid rgba(251, 191, 36, 0.3);
              border-radius: 12px; padding: 20px; text-align: center; margin: 16px 0;
            ">
              <div style="font-size: 2.5rem; margin-bottom: 8px;">⏳</div>
              <div style="font-size: 1.05rem; color: #fcd34d; font-weight: 600; margin-bottom: 4px;">
                ${escapeHtml(friendly)}
              </div>
            </div>`;
          return;
        }
        throw new Error(errMsg);
      }

      const submitData = await submitResp.json();
      const taskId = submitData.task_id;

      // Step 2: Persist task info to sessionStorage for refresh recovery
      const pendingTask = {
        taskId: taskId,
        question: question,
        timestamp: Date.now(),
      };
      sessionStorage.setItem('pending_task', JSON.stringify(pendingTask));

      // Step 3: Start timer and polling
      let timedOut = false;
      startTime = Date.now();

      // Timer: update every second
      timerInterval = setInterval(() => {
        const elapsed = Math.round((Date.now() - startTime) / 1000);
        updateTimer(elapsed);

        if (elapsed >= TIMEOUT_SECONDS && !timedOut) {
          timedOut = true;
          showTimeoutForm(taskId, question, elapsed);
        }
      }, 1000);

      // Poll: check every POLL_INTERVAL_MS
      pollInterval = setInterval(async () => {
        const done = await pollResult(taskId, question);
        if (done) {
          stopTimers();
          const finalElapsed = Math.round((Date.now() - startTime) / 1000);
          updateTimer(finalElapsed);
          sessionStorage.removeItem('pending_task');
        }
      }, POLL_INTERVAL_MS);

      // Also do an immediate first poll
      const done = await pollResult(taskId, question);
      if (done) {
        stopTimers();
        const finalElapsed = Math.round((Date.now() - startTime) / 1000);
        updateTimer(finalElapsed);
        sessionStorage.removeItem('pending_task');
      }

    } catch (err) {
      stopTimers();
      resultEl.innerHTML = `
        <div class="qa-status error">
          <i class="fas fa-times-circle"></i> 问答失败：${escapeHtml(err.message)}
        </div>`;
    }
  }

  // ── Global Functions (for inline onclick) ──────────────────────────────
  window._qaLeaveEmail = function(taskId) {
    const emailInput = document.getElementById('timeoutEmail');
    const feedback = document.getElementById('emailFeedback');
    const btn = document.getElementById('emailSubmitBtn');
    const email = emailInput ? emailInput.value.trim() : '';

    if (!email) {
      if (feedback) feedback.innerHTML = '<span style="color:#fbbf24;">请输入邮箱地址</span>';
      return;
    }

    // Simple email validation
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      if (feedback) feedback.innerHTML = '<span style="color:#ef4444;">邮箱格式不正确</span>';
      return;
    }

    if (feedback) feedback.innerHTML = '<span style="color:#4ade80;"><i class="fas fa-check-circle"></i> 已记录！处理完成后可通过存档路径获取结果。</span>';
    if (btn) btn.disabled = true;

    // Log the email request (server can pick this up later)
    console.log(`[Email Request] task=${taskId}, email=${email}`);
    // Also try to send to server if available
    fetch('/api/qa/archive-email', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ task_id: taskId, email }),
    }).catch(() => {});
  };

  window._qaRetryPoll = function(taskId) {
    const feedback = document.getElementById('emailFeedback');
    if (feedback) feedback.innerHTML = '<span style="color:var(--text-dim);"><i class="fas fa-spinner fa-pulse"></i> 正在重试...</span>';

    pollResult(taskId, '').then(done => {
      if (done) {
        stopTimers();
      } else {
        if (feedback) feedback.innerHTML = '<span style="color:#fbbf24;">尚未完成，请稍后再试</span>';
      }
    }).catch(() => {
      if (feedback) feedback.innerHTML = '<span style="color:#ef4444;">重试失败，请稍后再试</span>';
    });
  };

  // ── Convert backend rate-limit messages to user-friendly text ────────
  function friendlyLimitHint(msg) {
    // 普通密码错误 → 直接显示
    if (msg === '密码错误') return '密码错误，请重试';
    // 用户冷却 → 提取剩余秒数
    let m = msg.match(/请\s*(\d+)\s*秒/);
    if (m) return `提问速度太快了，请 ${m[1]} 秒后再试 🕐`;
    // 每日配额 → 友好提示
    if (msg.includes('已达上限')) return `今天已经问了够多啦，明天再来吧 😊`;
    // 并发限制 → 友好提示
    if (msg.includes('正在处理')) return `您有一个问题还在处理中，请稍等片刻 ⏳`;
    // IP 级限速（纯"请求过于频繁"）
    if (msg === '请求过于频繁，请稍后再试' || msg.includes('请求过于频繁') && !msg.includes('密码')) return `访问太频繁了，请稍后再试 🙏`;
    // 密码限速 — 包含"密码"且包含"频繁"
    if (msg.includes('密码') && msg.includes('频繁')) return `密码验证次数过多，请过一会儿再试 🔒`;
    // 兜底
    return '操作太频繁了，请稍后重试';
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
          loginOverlay.style.display = 'none';
          inputEl.disabled = false;
          submitEl.disabled = false;
          inputEl.focus();
          inputEl.placeholder = '为什么房间名叫葬爱家族？';
          if (window._qaPendingOnLogin) {
            window._qaPendingOnLogin = false;
            setTimeout(checkPendingTask, 100);
          }
        }
      } catch (err) {
        const msg = err.message || '';
        loginError.textContent = friendlyLimitHint(msg);
        // 限速用黄色警告，密码错误用红色
        if (msg.includes('密码') && !msg.includes('过频繁')) {
          loginError.className = 'login-error';           // red
        } else {
          loginError.className = 'login-error login-error--warn';  // yellow
        }
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

  // ── Character Counter ────────────────────────────────────────────────
  const charCountEl = document.getElementById('qaCharCount');

  function updateCharCount() {
    if (!charCountEl) return;
    const str = inputEl.value;
    const meaningful = countMeaningful(str);
    const other = str.length - str.replace(/[\u4e00-\u9fff a-zA-Z0-9]/g, '').length;
    const displayCount = meaningful + other;
    charCountEl.textContent = meaningful + '/' + MAX_QUESTION_LENGTH;

    charCountEl.classList.remove('warn', 'limit');
    if (meaningful >= MAX_QUESTION_LENGTH) {
      charCountEl.classList.add('limit');
    } else if (meaningful >= MAX_QUESTION_LENGTH * 0.85) {
      charCountEl.classList.add('warn');
    }
  }

  inputEl.addEventListener('input', updateCharCount);

  // ── Event Listeners ──────────────────────────────────────────────────
  submitEl.addEventListener('click', () => {
    const question = inputEl.value.trim();
    if (!question) return;

    // Check for disallowed special symbols
    if (hasBadChars(question)) {
      resultEl.innerHTML = `
        <div class="qa-status error">
          <i class="fas fa-exclamation-triangle"></i>
          问题中包含不支持的特殊符号，请使用中文、英文字母、数字和常用标点符号
        </div>`;
      return;
    }

    // Check meaningful character count
    const meaningful = countMeaningful(question);
    if (meaningful > MAX_QUESTION_LENGTH) {
      resultEl.innerHTML = `
        <div class="qa-status error">
          <i class="fas fa-exclamation-triangle"></i>
          问题过长（有效字符 ${meaningful} 字），请控制在 ${MAX_QUESTION_LENGTH} 字以内
        </div>`;
      return;
    }
    askQuestionAsync(question);
  });


  inputEl.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !submitEl.disabled) {
      submitEl.click();
    }
  });

  // ── Refresh Recovery: Detect Pending Tasks on Page Load ──────────────
  function checkPendingTask() {
    const pendingRaw = sessionStorage.getItem('pending_task');
    if (!pendingRaw) return;

    let pending;
    try {
      pending = JSON.parse(pendingRaw);
    } catch (e) {
      sessionStorage.removeItem('pending_task');
      return;
    }

    const overlay = document.getElementById('refreshOverlay');
    const questionText = document.getElementById('refreshQuestionText');
    const statusEl_ = document.getElementById('refreshTaskStatus');
    if (!overlay || !questionText || !statusEl_) return;

    // Show the question
    questionText.textContent = escapeHtml(pending.question || '未知');

    // If login overlay is also showing, defer refresh overlay until after login
    if (loginOverlay && loginOverlay.style.display === 'flex') {
      window._qaPendingOnLogin = true;
      return;
    }

    // Show overlay
    overlay.style.display = 'flex';

    // Immediately poll the server to check status
    (async function pollPending() {
      try {
        const resp = await fetch(`/api/qa/ask-async/${pending.taskId}`);
        if (!resp.ok) {
          throw new Error(`查询失败 (${resp.status})`);
        }
        const data = await resp.json();

        if (data.status === 'completed') {
          // Task completed! Show result directly in overlay
          statusEl_.innerHTML = '<span style="color:#4ade80;"><i class="fas fa-check-circle"></i> 已完成！</span>';
          // Hide the email/retry section, show result in overlay
          document.getElementById('refreshOverlayContent').style.display = 'none';
          const resultContent = document.getElementById('refreshResultContent');
          resultContent.style.display = 'block';
          // Build a mini result view inside the overlay
          const answer = data.answer || '未返回有效答案。';
          resultContent.innerHTML = `
            <div style="padding:12px 0;">
              <h3 style="margin-bottom:8px;"><i class="fas fa-comment-dots"></i> 回答</h3>
              <div style="background:var(--surface2);border-radius:8px;padding:12px;margin-bottom:12px;max-height:300px;overflow-y:auto;">${escapeHtml(answer)}</div>
              <button class="btn" onclick="window._qaRefreshDismiss()" style="width:100%;">
                <i class="fas fa-check"></i> 查看完毕
              </button>
            </div>
          `;
          // Also update main page result area
          displayResult(data);
          sessionStorage.removeItem('pending_task');
          return;
        }

        if (data.status === 'error') {
          statusEl_.innerHTML = '<span style="color:#ef4444;"><i class="fas fa-times-circle"></i> 处理失败</span>';
          document.querySelector('#refreshOverlay .qa-email-section')?.remove();
          document.getElementById('refreshRetryBtn')?.remove();
          return;
        }

        // Still processing
        const elapsed = data.created_at
          ? Math.round((Date.now() - new Date(data.created_at).getTime()) / 1000)
          : 0;
        statusEl_.innerHTML = `<i class="fas fa-spinner fa-pulse"></i> 处理中...（已耗时 ${formatElapsed(elapsed)}）`;

        // Poll again after interval
        setTimeout(pollPending, POLL_INTERVAL_MS);
      } catch (err) {
        statusEl_.innerHTML = `<span style="color:#fbbf24;"><i class="fas fa-exclamation-triangle"></i> 查询失败：${escapeHtml(err.message)}</span>`;
        // Still retry
        setTimeout(pollPending, POLL_INTERVAL_MS);
      }
    })();
  }

  // ── Refresh Overlay: Global Functions ────────────────────────────────
  window._qaRefreshLeaveEmail = function() {
    const pendingRaw = sessionStorage.getItem('pending_task');
    if (!pendingRaw) return;
    let pending;
    try { pending = JSON.parse(pendingRaw); } catch (e) { return; }

    const emailInput = document.getElementById('refreshEmail');
    const feedback = document.getElementById('refreshEmailFeedback');
    const btn = document.getElementById('refreshEmailBtn');
    const email = emailInput ? emailInput.value.trim() : '';

    if (!email) {
      if (feedback) feedback.innerHTML = '<span style="color:#fbbf24;">请输入邮箱地址</span>';
      return;
    }

    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      if (feedback) feedback.innerHTML = '<span style="color:#ef4444;">邮箱格式不正确</span>';
      return;
    }

    if (feedback) feedback.innerHTML = '<span style="color:#4ade80;"><i class="fas fa-check-circle"></i> 已记录！处理完成后可通过存档路径获取结果。</span>';
    if (btn) btn.disabled = true;

    fetch('/api/qa/archive-email', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ task_id: pending.taskId, email }),
    }).catch(() => {});
  };

  window._qaRefreshRetryPoll = function() {
    const pendingRaw = sessionStorage.getItem('pending_task');
    if (!pendingRaw) return;
    let pending;
    try { pending = JSON.parse(pendingRaw); } catch (e) { return; }

    const statusEl_ = document.getElementById('refreshTaskStatus');
    if (statusEl_) statusEl_.innerHTML = '<i class="fas fa-spinner fa-pulse"></i> 正在重新查询...';

    fetch(`/api/qa/ask-async/${pending.taskId}`).then(resp => {
      if (!resp.ok) throw new Error(`查询失败 (${resp.status})`);
      return resp.json();
    }).then(data => {
      if (data.status === 'completed') {
        if (statusEl_) statusEl_.innerHTML = '<span style="color:#4ade80;"><i class="fas fa-check-circle"></i> 已完成！</span>';
        document.getElementById('refreshOverlayContent').style.display = 'none';
        const resultContent = document.getElementById('refreshResultContent');
        resultContent.style.display = 'block';
        resultContent.innerHTML = `
          <div style="padding:12px 0;">
            <h3 style="margin-bottom:8px;"><i class="fas fa-comment-dots"></i> 回答</h3>
            <div style="background:var(--surface2);border-radius:8px;padding:12px;margin-bottom:12px;max-height:300px;overflow-y:auto;">${escapeHtml(data.answer || '未返回有效答案。')}</div>
            <button class="btn" onclick="window._qaRefreshDismiss()" style="width:100%;">
              <i class="fas fa-check"></i> 查看完毕
            </button>
          </div>
        `;
        displayResult(data);
        sessionStorage.removeItem('pending_task');
      } else if (data.status === 'error') {
        if (statusEl_) statusEl_.innerHTML = '<span style="color:#ef4444;"><i class="fas fa-times-circle"></i> 处理失败</span>';
        document.querySelector('#refreshOverlay .qa-email-section')?.remove();
      } else {
        const elapsed = data.created_at
          ? Math.round((Date.now() - new Date(data.created_at).getTime()) / 1000)
          : 0;
        if (statusEl_) statusEl_.innerHTML = `<i class="fas fa-spinner fa-pulse"></i> 处理中...（已耗时 ${formatElapsed(elapsed)}）`;
      }
    }).catch(err => {
      if (statusEl_) statusEl_.innerHTML = `<span style="color:#fbbf24;"><i class="fas fa-exclamation-triangle"></i> 查询失败：${escapeHtml(err.message)}</span>`;
    });
  };

  window._qaRefreshDismiss = function() {
    const overlay = document.getElementById('refreshOverlay');
    if (overlay) overlay.style.display = 'none';
    sessionStorage.removeItem('pending_task');
  };

  // ── Init ──────────────────────────────────────────────────────────────
  checkStatus().then(() => {
    // After checking KB status, check if there's a pending task from before refresh
    checkPendingTask();
  }, () => {
    // Even if checkStatus fails, still look for pending tasks
    checkPendingTask();
  });
})();
