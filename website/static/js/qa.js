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
      // Prevent body scrolling while overlay is shown
      document.body.style.overflow = 'hidden';
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
        <p><strong>原因：</strong>分析耗时较长，页面暂时无法显示结果。</p>
        <p><strong>但处理仍在继续！</strong>完成后结果会自动保存。</p>
        <div class="qa-email-section">
          <label for="timeoutEmail">如需获取最终答复，请留下您的邮箱：</label>
          <div class="qa-email-row">
            <input type="email" id="timeoutEmail" class="qa-input" placeholder="example@email.com">
            <button class="qa-submit" onclick="window._qaLeaveEmail('${taskId}')" id="emailSubmitBtn">
              <i class="fas fa-paper-plane"></i> 提交
            </button>
          </div>
          <p class="qa-email-hint">提交后，处理完成时会通过邮箱发送答复。</p>
          <div id="emailFeedback" style="margin-top:8px;font-size:0.9rem;"></div>
        </div>
        <div class="qa-poll-again" style="margin-top:16px;">
          <button class="btn" onclick="window._qaRetryPoll('${taskId}')">
            <i class="fas fa-redo"></i> 再次尝试获取结果
          </button>
        </div>
        <div style="color:var(--text-dim);font-size:0.85rem;margin-top:8px;">结果可能随时返回</div>
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

    // Only show warning if ratio is significantly below 100%
    if (ratio >= 0.95) return '';

    // Severity classes for styling
    let severity = 'low';
    let icon = 'fa-info-circle';
    if (ratio < 0.3) {
      severity = 'high';
      icon = 'fa-exclamation-triangle';
    } else if (ratio < 0.6) {
      severity = 'medium';
      icon = 'fa-exclamation-circle';
    }

    // Generate a stable email subject / identifier
    const questionForEmail = encodeURIComponent(question || '未指定问题');

    return `
      <div class="qa-comp-banner qa-comp-banner--${severity}">
        <div class="qa-comp-header">
          <i class="fas ${icon}"></i>
          <span>回答全面性提醒</span>
        </div>
        <div class="qa-comp-body">
          <p>当前回答可能未能覆盖所有相关内容。</p>
          <p>如需获取更全面的回答，请留下您的邮箱，会尽快为您处理。</p>
        </div>
        <div class="qa-email-section">
          <label for="compEmail">如需获取更全面的回答，请留下您的邮箱：</label>
          <div class="qa-email-row">
            <input type="email" id="compEmail" class="qa-input" placeholder="your@email.com">
            <button class="qa-submit" onclick="window._qaCompRequest('${questionForEmail}')">
              <i class="fas fa-paper-plane"></i> 提交请求
            </button>
          </div>
          <p class="qa-email-hint">提交后，会尽快为您提供更全面的回答。</p>
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
      body: JSON.stringify({ task_id: 'comprehensiveness_request', email, question, client_id: clientId }),
    }).catch(() => {});

    // Track event
    if (window._trackEvent) {
      window._trackEvent('email_submit', {
        action: 'comprehensiveness_request',
        email: email,
        question: question,
      }, true);
    }
  };

  // Global: handle content safety email request
  window._qaSafetyEmail = function() {
    const emailInput = document.getElementById('safetyEmail');
    const feedback = document.getElementById('safetyEmailFeedback');
    const email = emailInput ? emailInput.value.trim() : '';

    if (!email) {
      if (feedback) feedback.innerHTML = '<span style="color:#fbbf24;">请输入邮箱地址</span>';
      return;
    }
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      if (feedback) feedback.innerHTML = '<span style="color:#ef4444;">邮箱格式不正确</span>';
      return;
    }

    if (feedback) feedback.innerHTML = '<span style="color:#4ade80;"><i class="fas fa-check-circle"></i> 已记录！审核通过后会通过邮箱发送答复。</span>';

    fetch('/api/qa/archive-email', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ task_id: 'content_safety_review', email, question: '内容安全审核', client_id: clientId }),
    }).catch(() => {});

    // Track event
    if (window._trackEvent) {
      window._trackEvent('email_submit', {
        action: 'safety_review',
        email: email,
        question: '内容安全审核',
      }, true);
    }
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

  /**
   * Capture a single DOM element as a canvas at the given scale.
   * Each element is captured independently with its own html2canvas call,
   * ensuring consistent font rendering within each component.
   */
  async function captureElement(el, scale, bgColor) {
    return await html2canvas(el, {
      scale: scale,
      useCORS: true,
      backgroundColor: bgColor,
      allowTaint: true,
      logging: false,
      width: el.scrollWidth,
      height: el.scrollHeight,
      windowWidth: el.scrollWidth,
      windowHeight: el.scrollHeight,
    });
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
      // ── Strategy: Component-based capture ──
      // Instead of splitting by fixed pixel height (which causes font size
      // inconsistencies on iOS Safari due to html2canvas windowHeight
      // differences between segments), we capture each logical component
      // as an independent element. This ensures consistent font rendering
      // within each component.
      const CAPTURE_SCALE = 3;          // 3x for crisp text
      const BG_COLOR = '#0a0a1a';

      // ── Step 1: Build off-screen wrapper with ALL content ──
      const wrapper = document.createElement('div');
      wrapper.style.cssText = [
        'background: ' + BG_COLOR + ';',
        "font-family: 'Noto Sans SC', -apple-system, BlinkMacSystemFont, sans-serif;",
        'color: #f0f0f0;',
        'font-size: 24px;',
        'line-height: 1.7;',
        'position: absolute;',
        'left: -9999px;',
        'top: 0;',
        'width: 780px;',
        'padding: 0 24px;',
      ].join(' ');
      document.body.appendChild(wrapper);

      const question = document.getElementById('qaInput')?.value?.trim() || '';

      // ── Component 1: Navigation bar (site title bar) ──
      // Clone the actual navbar from the live page to preserve all CSS styles,
      // colors, hover effects, and responsive behavior exactly as rendered.
      const navbar = document.getElementById('mainNav').cloneNode(true);
      navbar.style.position = 'relative';  // override fixed positioning for screenshot
      navbar.style.left = 'auto';
      navbar.style.top = 'auto';
      navbar.style.marginBottom = '24px';
      // Remove mobile toggle button from screenshot (not needed)
      const navToggle = navbar.querySelector('.nav-toggle');
      if (navToggle) navToggle.remove();
      wrapper.appendChild(navbar);

      // ── Component 2: Page header (title + subtitle with icon) ──
      // Clone the actual header from the live page to preserve all CSS styles.
      const header = document.querySelector('.qa-header').cloneNode(true);
      header.style.marginBottom = '32px';
      wrapper.appendChild(header);

      // ── Component 3: KB status ──
      const kbStatus = document.getElementById('kbStatus');
      if (kbStatus) {
        const isReady = kbStatus.classList.contains('ready');
        const statusDiv = document.createElement('div');
        statusDiv.style.cssText = [
          'text-align:center;',
          'margin-bottom:24px;',
          'padding:12px;',
          'border-radius:10px;',
          'font-size:20px;',
          isReady
            ? 'background:rgba(74,222,128,0.1);color:#4ade80;border:1px solid rgba(74,222,128,0.2);'
            : 'background:rgba(251,191,36,0.1);color:#fbbf24;border:1px solid rgba(251,191,36,0.2);',
        ].join(' ');
        statusDiv.innerHTML = kbStatus.innerHTML;
        wrapper.appendChild(statusDiv);
      }

      // ── Component 4: Question input area ──
      if (question) {
        const inputArea = document.createElement('div');
        inputArea.style.cssText = 'display:flex;gap:12px;margin-bottom:24px;';
        inputArea.innerHTML = [
          '<div style="flex:1;padding:14px 20px;border-radius:12px;border:1.5px solid rgba(255,255,255,0.12);background:rgba(255,255,255,0.08);color:#f0f0f0;font-size:24px;">',
          escapeHtml(question),
          '</div>',
          '<div style="padding:14px 28px;border-radius:12px;background:linear-gradient(135deg,#ff6b9d,#e0558a);color:#fff;font-size:24px;white-space:nowrap;display:flex;align-items:center;gap:8px;">',
          '<i class="fas fa-paper-plane"></i> 提问',
          '</div>',
        ].join('');
        wrapper.appendChild(inputArea);
      }

      // ── Component 5: Result content (answer + citations + disclaimer) ──
      const clone = resultEl.cloneNode(true);

      // Remove interactive elements from clone
      const shareArea = clone.querySelector('.qa-share-area');
      if (shareArea) shareArea.remove();
      const compBanner = clone.querySelector('.qa-comp-banner');
      if (compBanner) compBanner.remove();

      // Fix citation refs for static display
      const citationRefs = clone.querySelectorAll('.citation-ref');
      citationRefs.forEach(el => {
        el.style.color = '#ff6b9d';
        el.style.fontWeight = '700';
        el.style.textDecoration = 'none';
        el.style.cursor = 'default';
        el.removeAttribute('href');
      });

      wrapper.appendChild(clone);

      // ── Component 6: Footer with QR code ──
      const footer = document.createElement('div');
      footer.style.cssText = [
        'margin-top: 32px;',
        'padding-top: 20px;',
        'padding-bottom: 40px;',
        'border-top: 1px solid rgba(255,255,255,0.12);',
        'display: flex;',
        'flex-direction: column;',
        'align-items: center;',
        'text-align: center;',
        'gap: 12px;',
        'width: 50%;',
        'margin-left: auto;',
        'margin-right: auto;',
      ].join(' ');
      const siteUrl = getSiteUrl();
      const qrHtml = generateQRCode(siteUrl, 28);
      const qrContainer = document.createElement('div');
      qrContainer.innerHTML = qrHtml;
      qrContainer.style.cssText = 'line-height: 0; display: flex; justify-content: center;';
      const qrImg = qrContainer.querySelector('img');
      if (qrImg) {
        qrImg.style.maxWidth = '100%';
        qrImg.style.height = 'auto';
      }
      footer.appendChild(qrContainer);
      const info = document.createElement('div');
      info.style.cssText = [
        'font-size: 0.8rem;',
        'color: rgba(255,255,255,0.5);',
        'line-height: 1.5;',
      ].join(' ');
      info.innerHTML = [
        '<div style="font-size:0.9rem;color:rgba(255,255,255,0.7);font-weight:500;margin-bottom:4px;">',
        '  <i class="fas fa-star" style="color:#ff6b9d;"></i> AI 智能问答',
        '</div>',
        '<div>' + (question ? 'Q: ' + escapeHtml(question) : '') + '</div>',
        '<div style="margin-top:3px;">' + siteUrl + '</div>',
        '<div style="margin-top:1px;font-size:0.72rem;">生成时间：' + new Date().toLocaleString('zh-CN') + '</div>',
      ].join('');
      footer.appendChild(info);
      wrapper.appendChild(footer);

      // ── Apply "陈嘉仪" highlighting to match the live page ──
      // The live page runs highlightCJY(document.body) on DOMContentLoaded,
      // which wraps "陈嘉仪" in <span class="highlight-cjy"> with special styling.
      // We apply the same transformation to the screenshot wrapper so that
      // all "陈嘉仪" occurrences (in navbar, header, etc.) appear highlighted
      // just like on the real page.
      if (typeof highlightCJY === 'function') {
        highlightCJY(wrapper);
      }

      // ── Step 2: Wait for layout ──
      await new Promise(r => setTimeout(r, 200));

      // ── Step 3: Identify component boundaries ──
      // We split the wrapper into logical components by finding direct children
      // that represent distinct visual sections. Each component is captured
      // independently to ensure consistent font rendering.
      const components = [];
      const children = Array.from(wrapper.children);

      // Group children into components:
      // - header (title + subtitle)
      // - kb status
      // - question input area
      // - result content (answer + citations + disclaimer)
      // - footer
      // If the result content is too tall, we further split it into:
      //   - answer section
      //   - citation items (each individually, if many)
      //   - disclaimer + share area

      for (const child of children) {
        // Check if this is the result clone (contains answer + citations)
        const hasAnswer = child.querySelector('.qa-answer');
        const hasCitations = child.querySelector('.qa-citations');
        const hasDisclaimer = child.querySelector('.qa-answer-disclaimer');

        if (hasAnswer || hasCitations || hasDisclaimer) {
          // This is the result content — split into sub-components
          // to avoid capturing an overly tall element

          // Sub-component: elapsed time (the div containing "处理耗时" text)
          const elapsedDiv = child.querySelector('[style*="text-align:right"]');
          if (elapsedDiv && elapsedDiv.textContent.indexOf('处理耗时') !== -1) {
            components.push(elapsedDiv);
          }

          // Sub-component: compliance notice
          const complianceNotice = child.querySelector('.qa-compliance-notice');
          if (complianceNotice) {
            components.push(complianceNotice);
          }

          // Sub-component: answer section
          const answerSection = child.querySelector('.qa-answer');
          if (answerSection) {
            components.push(answerSection);
          }

          // Sub-component: each citation item individually
          const citationItems = child.querySelectorAll('.citation-item');
          if (citationItems.length > 0) {
            // If there are many citations, capture each one individually
            // to keep each component small and avoid canvas memory issues
            for (const citItem of citationItems) {
              components.push(citItem);
            }
          }

          // Sub-component: disclaimer
          const disclaimer = child.querySelector('.qa-answer-disclaimer');
          if (disclaimer) {
            components.push(disclaimer);
          }

          // Sub-component: comprehensiveness banner (if present)
          const compBannerInClone = child.querySelector('.qa-comp-banner');
          if (compBannerInClone) {
            components.push(compBannerInClone);
          }
        } else {
          // Other components (header, status, input, footer) — capture as-is
          components.push(child);
        }
      }

      // ── Step 4: Capture each component independently ──
      const componentCanvases = [];

      for (let i = 0; i < components.length; i++) {
        const comp = components[i];

        // Create a wrapper for this component with the same background and font
        const compWrapper = document.createElement('div');
        compWrapper.style.cssText = [
          'background: ' + BG_COLOR + ';',
          "font-family: 'Noto Sans SC', -apple-system, BlinkMacSystemFont, sans-serif;",
          'color: #f0f0f0;',
          'font-size: 24px;',
          'line-height: 1.7;',
          'position: absolute;',
          'left: -9999px;',
          'top: 0;',
          'width: 780px;',
          'padding: 0 24px;',
          'margin: 0;',
        ].join('');

        // Clone the component element
        // Preserve original margins so spacing between components
        // (e.g. margin-bottom on navbar, header) is maintained in the final image.
        const compClone = comp.cloneNode(true);
        compWrapper.appendChild(compClone);
        document.body.appendChild(compWrapper);

        // Wait a brief moment for layout
        await new Promise(r => setTimeout(r, 20));

        // Capture this component independently
        const compCanvas = await captureElement(compWrapper, CAPTURE_SCALE, BG_COLOR);
        componentCanvases.push(compCanvas);

        // Clean up
        document.body.removeChild(compWrapper);
      }

      // Clean up the full wrapper
      document.body.removeChild(wrapper);

      // ── Step 5: Stitch components together ──
      // No overlap trimming needed since components are distinct elements
      // with no vertical overlap. We simply stack them vertically.
      const finalWidth = componentCanvases[0].width;
      let finalHeight = 0;
      for (let ci = 0; ci < componentCanvases.length; ci++) {
        finalHeight += componentCanvases[ci].height;
      }

      const finalCanvas = document.createElement('canvas');
      finalCanvas.width = finalWidth;
      finalCanvas.height = finalHeight;
      const ctx = finalCanvas.getContext('2d');

      let yOffset = 0;
      for (let ci = 0; ci < componentCanvases.length; ci++) {
        const compCanvas = componentCanvases[ci];
        ctx.drawImage(compCanvas, 0, yOffset);
        yOffset += compCanvas.height;
      }

      // Track screenshot event
      if (window._trackEvent) {
        window._trackEvent('screenshot', {
          question: document.getElementById('qaInput')?.value?.trim() || '',
          citation_count: document.querySelectorAll('.citation-item').length,
          capture_scale: CAPTURE_SCALE,
          num_components: componentCanvases.length,
        }, true);
      }

      // ── Step 6: Download PNG ──
      const filename = 'AI问答_' + new Date().toISOString().slice(0, 19).replace(/[:-]/g, '') + '.png';

      const downloaded = await new Promise(function(resolve) {
        finalCanvas.toBlob(function(blob) {
          if (blob && blob.size > 0) {
            triggerDownload(blob, filename);
            resolve(true);
          } else {
            resolve(false);
          }
        }, 'image/png');
        // Timeout: if toBlob doesn't call back within 5s, treat as failure
        setTimeout(function() { resolve(false); }, 5000);
      });

      if (!downloaded) {
        // Fallback: try toDataURL
        try {
          var dataUrl = finalCanvas.toDataURL('image/png');
          if (dataUrl && dataUrl.length > 100) {
            var link = document.createElement('a');
            link.download = filename;
            link.href = dataUrl;
            link.click();
          } else {
            throw new Error('empty data URL');
          }
        } catch (e) {
          console.warn('Stitched canvas download failed, falling back to component-by-component download:', e);
          // Fallback: download each component as a separate image.
          if (componentCanvases.length > 1) {
            var zipFilename = filename.replace('.png', '');
            function downloadComponent(index) {
              if (index >= componentCanvases.length) {
                alert('内容较长，已分段保存为多张图片（共 ' + componentCanvases.length + ' 张），请按文件名顺序查看。');
                return;
              }
              var compFilename = zipFilename + '_part' + (index + 1) + '.png';
              componentCanvases[index].toBlob(function(compBlob) {
                if (compBlob && compBlob.size > 0) {
                  triggerDownload(compBlob, compFilename);
                  setTimeout(function() { downloadComponent(index + 1); }, 500);
                } else {
                  setTimeout(function() { downloadComponent(index + 1); }, 100);
                }
              }, 'image/png');
            }
            downloadComponent(0);
          } else {
            alert('截图生成失败，图片内容为空。请尝试减少引用数量后重试。');
          }
        }
      }
    } catch (err) {
      console.error('Screenshot failed:', err);
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

    // Track Q&A complete event
    if (window._trackEvent) {
      window._trackEvent('qa_complete', {
        question: data.question || '',
        has_answer: !!(data.answer && data.answer.length > 0),
        has_citations: !!(data.citations && data.citations.length > 0),
        citation_count: (data.citations || []).length,
        content_safety_flagged: !!data.content_safety_flagged,
        elapsed_seconds: data.completed_at && data.created_at
          ? Math.round((new Date(data.completed_at) - new Date(data.created_at)) / 1000) : 0,
        archive_path: data.archive_path || '',
      }, true);
    }

    const hasAnswer = data.answer && data.answer.length > 0;
    const hasCitations = data.citations && data.citations.length > 0;
    const elapsed = data.completed_at && data.created_at
      ? Math.round((new Date(data.completed_at) - new Date(data.created_at)) / 1000)
      : 0;

    let html = '';

    // Elapsed time info
    html += `<div style="text-align:right;font-size:0.85rem;color:var(--text-dim);margin-bottom:8px;">
      <i class="fas fa-clock"></i> 处理耗时：${formatElapsed(elapsed)}</div>`;

    // ── Content Safety Flagged ──────────────────────────────────────────
    if (data.content_safety_flagged) {
      html += `<div class="qa-content-safety-block" style="
        background: rgba(251, 191, 36, 0.12);
        border: 1px solid rgba(251, 191, 36, 0.3);
        border-radius: 12px;
        padding: 24px;
        text-align: center;
        margin: 16px 0;
      ">
        <div style="font-size: 2.5rem; margin-bottom: 8px;">🛡️</div>
        <div style="font-size: 1.05rem; color: #fcd34d; font-weight: 600; margin-bottom: 8px;">
          该回答需要审核
        </div>
        <p style="color: var(--text-dim); font-size: 0.9rem; margin-bottom: 16px;">
          为保障网站合规与内容安全，该回答已进入人工审核流程，暂时无法直接显示。
        </p>
        <p style="color: var(--text-dim); font-size: 0.85rem; margin-bottom: 16px; line-height: 1.6;">
          <i class="fas fa-info-circle" style="color: #fcd34d;"></i>
          由于 AI 输出有不确定性风险，为保证网站合规和内容安全，采取较保守的内容展示策略。
        </p>
        <div class="qa-email-section">
          <label for="safetyEmail">如需获取回复，请留下您的邮箱：</label>
          <div class="qa-email-row">
            <input type="email" id="safetyEmail" class="qa-input" placeholder="your@email.com">
            <button class="qa-submit" onclick="window._qaSafetyEmail()">
              <i class="fas fa-paper-plane"></i> 提交
            </button>
          </div>
          <p class="qa-email-hint">提交后，审核通过后会通过邮箱发送答复。</p>
          <div id="safetyEmailFeedback" style="margin-top:8px;font-size:0.9rem;"></div>
        </div>
      </div>`;


      resultEl.innerHTML = html;
      resultEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
      return;
    }

    // ── Compliance notice (below processing time, above answer) ──
    html += `<div class="qa-compliance-notice" style="margin: 0 0 12px 0; padding: 10px 14px; background: rgba(255, 107, 157, 0.08); border: 1px solid rgba(255, 107, 157, 0.15); border-radius: 8px; font-size: 0.85rem; color: var(--text-dim); display: flex; align-items: flex-start; gap: 8px;">
      <i class="fas fa-shield-alt" style="color: var(--primary); margin-top: 2px; flex-shrink: 0;"></i>
      <span>本服务使用生成式人工智能技术，生成内容仅供参考，不代表陈嘉仪本人立场，请理性看待。</span>
    </div>`;

    // Answer
    html += `<div class="qa-answer">`;
    html += `<h3><i class="fas fa-comment-dots"></i> 回答</h3>`;

    if (hasAnswer) {
      // Format citations: expand [#...] into individual clickable refs
      // Supports: [#1], [#2-#5], [#1, #2, #3], [#1, #3, #5-7], etc.
      // Rules:
      //   - Comma-separated items each become their own link (e.g. [#1, #2, #3])
      //   - Range like #2-#5 stays as one link pointing to the first citation
      let answerText = data.answer;
      let citationRefIndex = 0;
      answerText = answerText.replace(/\[([^\]]*?#\d+[^\]]*?)\]/g, (match, inner) => {
        const trimmed = inner.trim();
        // Parse all #number and #number-number tokens
        const parts = trimmed.split(/[,，\s]+/).filter(Boolean);
        const links = [];
        for (const part of parts) {
          const rangeMatch = part.match(/^#(\d+)\s*-\s*#?(\d+)$/);
          if (rangeMatch) {
            // Range like #2-#5 — keep as one link, point to first citation
            citationRefIndex++;
            const firstNum = rangeMatch[1];
            links.push(`<a href="#citation-${firstNum}" class="citation-ref" data-ref-index="${citationRefIndex}" style="
              color: var(--primary); font-weight: 700; text-decoration: none;
              cursor: pointer;
            " title="查看引用 #${firstNum} 到 #${rangeMatch[2]}">${part}</a>`);
          } else {
            // Single #number
            const numMatch = part.match(/#(\d+)/);
            if (numMatch) {
              citationRefIndex++;
              const num = numMatch[1];
              links.push(`<a href="#citation-${num}" class="citation-ref" data-ref-index="${citationRefIndex}" style="
                color: var(--primary); font-weight: 700; text-decoration: none;
                cursor: pointer;
              " title="查看引用 #${num}">${part}</a>`);
            }
          }
        }
        // Wrap in brackets, join with comma+space
        return '[' + links.join(', ') + ']';
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
        const segs = cit.segments || [];

        html += `<div class="citation-item" id="citation-${citId}">`;
        // ── Citation header: ID + type badge + video title/date ──
        html += `<div class="citation-header">`;
        html += `<span class="citation-id">${cit.citation_id || '#'}</span>`;
        if (cit.citation_type) {
          html += `<span class="citation-type-badge">${escapeHtml(cit.citation_type)}</span>`;
        }
        // Video title + date from first segment (if any)
        if (segs.length > 0) {
          const firstSeg = segs[0];
          if (firstSeg.video_title) {
            html += `<span class="citation-header-video">📺 ${escapeHtml(firstSeg.video_title)}`;
            if (firstSeg.absolute_time) {
              const dateStr = firstSeg.absolute_time.slice(0, 10);
              html += ` <span class="segment-video-date">${escapeHtml(dateStr)}</span>`;
            }
            html += `</span>`;
          }
        }
        html += `</div>`;

        // ── Segments list ──
        if (segs.length > 0) {
          html += `<div class="citation-segments">`;
          let prevAnchor = '';
          let prevVideoTitle = '';
          for (const seg of segs) {
            const sameAnchor = seg.anchor_name && seg.anchor_name === prevAnchor;
            const sameVideo = seg.video_title && seg.video_title === prevVideoTitle;

            html += `<div class="citation-segment">`;
            // Source info row: anchor_name (dedup), source_type, offset
            html += `<div class="segment-source">`;
            if (seg.anchor_name && !sameAnchor) {
              html += `<span class="segment-anchor">${escapeHtml(seg.anchor_name)}</span>`;
            }
            if (seg.source_type) {
              html += `<span class="segment-type">${escapeHtml(seg.source_type)}</span>`;
            }

            if (seg.video_offset) {
              html += `<span class="segment-offset">⏱ ${escapeHtml(seg.video_offset)}</span>`;
            }
            html += `</div>`;


            // Quoted text
            html += `<div class="segment-text">“${escapeHtml(seg.quoted_text || '')}”</div>`;
            html += `</div>`;

            prevAnchor = seg.anchor_name || prevAnchor;
            prevVideoTitle = seg.video_title || prevVideoTitle;
          }
          html += `</div>`;
        }

        // ── Reason (at the bottom of each citation) ──
        if (cit.reason) {
          html += `<div class="citation-reason">📝 ${escapeHtml(cit.reason)}</div>`;
        }

        // Back-to-answer link
        html += `<div class="citation-back"><a href="#qaAnswerText" class="citation-back-link" data-citation-id="${citId}"><i class="fas fa-arrow-up"></i> 回到回答</a></div>`;
        html += `</div>`;

      }
      html += `</div>`;
    }

    // ── AI Generated Content Disclaimer (after citation list) ──
    html += `<div class="qa-answer-disclaimer">
      <i class="fas fa-robot"></i> 以上内容由人工智能（AI）生成，仅供参考，不代表陈嘉仪本人立场。请结合其他信息源自行判断。
    </div>`;


    // Comprehensiveness warning banner (after the citation list)
    if (data.comprehensiveness) {
      html += buildComprehensivenessBanner(data.comprehensiveness, data.question || '');
    }

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
            setTimeout(() => refLink.classList.remove('citation-ref--highlight'), 5000);

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
          setTimeout(() => targetEl.classList.remove('citation-item--highlight'), 5000);

        }
      });
    });


    // Scroll to the compliance notice (just above the answer), so users see
    // the disclaimer first before reading the AI-generated content.
    const complianceNotice = resultEl.querySelector('.qa-compliance-notice');
    if (complianceNotice) {
      const navHeight = 80;
      const targetPos = complianceNotice.getBoundingClientRect().top + window.scrollY - navHeight;
      window.scrollTo({ top: targetPos, behavior: 'smooth' });
    }

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

    // Track Q&A submit event
    if (window._trackEvent) {
      window._trackEvent('qa_submit', {
        question: question,
      }, true);
    }

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

    if (feedback) feedback.innerHTML = '<span style="color:#4ade80;"><i class="fas fa-check-circle"></i> 已记录！处理完成后会通过邮箱发送答复。</span>';
    if (btn) btn.disabled = true;

    // Recover question from sessionStorage
    let question = '';
    try {
      const pendingRaw = sessionStorage.getItem('pending_task');
      if (pendingRaw) {
        const pending = JSON.parse(pendingRaw);
        question = pending.question || '';
      }
    } catch (e) {}

    // Log the email request (server can pick this up later)
    console.log(`[Email Request] task=${taskId}, email=${email}`);
    // Also try to send to server if available
    fetch('/api/qa/archive-email', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ task_id: taskId, email, question, client_id: clientId }),
    }).catch(() => {});

    // Track event
    if (window._trackEvent) {
      window._trackEvent('email_submit', {
        action: 'timeout_email',
        task_id: taskId,
        email: email,
        question: question,
      }, true);
    }
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

      // Track login attempt
      if (window._trackEvent) {
        window._trackEvent('login_attempt', {
          action: 'attempt',
        }, true);
      }

      try {
        const ok = await verifyPassword(pwd);
        if (ok) {
          sitePassword = pwd;
          loginOverlay.style.display = 'none';
          document.body.style.overflow = '';
          inputEl.disabled = false;
          submitEl.disabled = false;
          inputEl.placeholder = '为什么房间名叫葬爱家族？';

          // Scroll to top so the "AI 智能问答" title is visible below the navbar
          window.scrollTo({ top: 0, behavior: 'instant' });

          if (window._qaPendingOnLogin) {
            window._qaPendingOnLogin = false;
            setTimeout(checkPendingTask, 100);
          }

          // Track successful login
          if (window._trackEvent) {
            window._trackEvent('login_attempt', {
              action: 'success',
            }, true);
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

        // Track failed login
        if (window._trackEvent) {
          window._trackEvent('login_attempt', {
            action: 'failed',
            reason: msg.includes('频繁') ? 'rate_limited' : 'wrong_password',
          }, true);
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

    if (feedback) feedback.innerHTML = '<span style="color:#4ade80;"><i class="fas fa-check-circle"></i> 已记录！处理完成后会通过邮箱发送答复。</span>';
    if (btn) btn.disabled = true;

    const question = pending.question || '';

    fetch('/api/qa/archive-email', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ task_id: pending.taskId, email, question, client_id: clientId }),
    }).catch(() => {});

    // Track event
    if (window._trackEvent) {
      window._trackEvent('email_submit', {
        action: 'refresh_email',
        task_id: pending.taskId,
        email: email,
        question: question,
      }, true);
    }
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

  // ── CHANGED: DeepSeek API 余额状态检查 ──────────────────────────────
  async function checkApiBalance() {
    const dotEl = document.getElementById('apiStatusDot');
    const textEl = document.getElementById('apiStatusText');
    if (!dotEl || !textEl) return;

    try {
      const resp = await fetch('/api/balance');
      if (!resp.ok) {
        dotEl.className = 'api-status-dot red';
        textEl.textContent = 'API 服务异常';
        return;
      }
      // CHANGED: 前端只拿状态级别，不接触具体余额数字
      const data = await resp.json();
      if (data.status === 'healthy') {
        dotEl.className = 'api-status-dot green';
        textEl.textContent = 'API 服务正常';
      } else if (data.status === 'low') {
        dotEl.className = 'api-status-dot yellow';
        textEl.textContent = 'API 余额即将耗尽';
      } else {
        dotEl.className = 'api-status-dot red';
        textEl.textContent = 'API 余额已耗尽';
      }
    } catch (err) {
      dotEl.className = 'api-status-dot gray';
      textEl.textContent = '无法检测 API 状态';
    }
  }

  // ── Init ──────────────────────────────────────────────────────────────
  checkStatus().then(() => {
    // After checking KB status, check if there's a pending task from before refresh
    checkPendingTask();
  }, () => {
    // Even if checkStatus fails, still look for pending tasks
    checkPendingTask();
  });

  // CHANGED: 启动时检查 API 余额
  checkApiBalance();
  // 每 5 分钟刷新一次余额状态
  setInterval(checkApiBalance, 5 * 60 * 1000);
})();
