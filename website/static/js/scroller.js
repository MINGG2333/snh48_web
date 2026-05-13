/**
 * Screen-saver style scrolling text effect.
 *
 * Creates multiple lines of text that scroll across the screen
 * at different speeds, directions, and vertical positions,
 * reminiscent of classic Windows/Mac screen savers.
 *
 * The text lines continuously loop from one side to the other.
 */

(function() {
  'use strict';

  // ── Configuration ─────────────────────────────────────────────────────
  const CONFIG = {
    lineCount: 12,              // number of text lines
    minSpeed: 40,               // minimum px/s
    maxSpeed: 120,              // maximum px/s
    minFontSize: 14,            // px (overridden by CSS clamp)
    maxFontSize: 40,
    colors: [
      '#ff6b9d', '#c084fc', '#60a5fa', '#34d399',
      '#fbbf24', '#f472b6', '#a78bfa', '#2dd4bf',
    ],
    // 默认文本（确保页面首次加载立刻有内容显示，后由 API 异步更新）
    texts: [
      'SNH48', '偶像', '舞台', '梦想', '闪耀',
      '23期', 'B Rise', '梦之门', 'Team HII', '赫兹共振', '1&1', 'ANYONE',
      '陈嘉仪', '甲鱼', '甲鱼不吃鱼', '萨卡班甲鱼', 'x+1', '楚简儿', 'cjy',
      '仪嘉人', '葬爱家族',
      '顺顺',
    ],
  };

  // ── DOM Setup ─────────────────────────────────────────────────────────
  const container = document.getElementById('scrollContainer');
  if (!container) return;

  // Make sure container covers the full viewport
  container.style.cssText = `
    position: fixed;
    inset: 0;
    z-index: 5;
    pointer-events: none;
    overflow: hidden;
  `;

  // ── Pick a random item from array ─────────────────────────────────────
  function pick(arr) {
    return arr[Math.floor(Math.random() * arr.length)];
  }

  // ── Create all scrolling lines ────────────────────────────────────────
  const lines = [];
  const lineEls = [];

  for (let i = 0; i < CONFIG.lineCount; i++) {
    const el = document.createElement('div');
    el.className = 'scroll-text';
    el.textContent = pick(CONFIG.texts);
    el.style.color = pick(CONFIG.colors);
    // Random font size
    const fontSize = CONFIG.minFontSize + Math.random() * (CONFIG.maxFontSize - CONFIG.minFontSize);
    el.style.fontSize = fontSize + 'px';

    // Determine vertical position
    // Avoid top 10% and bottom 15% to not overlap nav/footer
    const vPos = 10 + Math.random() * 70;  // 10% ~ 80%
    el.style.top = vPos + '%';

    // Direction & speed: 0 = left-to-right, 1 = right-to-left
    const direction = Math.random() < 0.5 ? 0 : 1;
    const speed = CONFIG.minSpeed + Math.random() * (CONFIG.maxSpeed - CONFIG.minSpeed); // px/s

    container.appendChild(el);

    const state = {
      el,
      direction,
      speed,
      x: 0,                // current logical position
      textWidth: 0,        // will be measured
      viewWidth: 0,
      fontSize,
    };

    lines.push(state);
    lineEls.push(el);
  }

  // ── Helper: wait for fonts/metrics ────────────────────────────────────
  function measureLines() {
    const vw = window.innerWidth;
    for (const line of lines) {
      line.textWidth = line.el.offsetWidth;
      line.viewWidth = vw;
      // Initialize starting position
      if (line.direction === 0) {
        // left->right: start off-screen to the left, or somewhere visible
        line.x = -line.textWidth - 50 - Math.random() * 200;
      } else {
        // right->left: start off-screen to the right, or somewhere visible
        line.x = vw + 50 + Math.random() * 200;
      }
    }
    requestAnimationFrame(updatePositions);
  }

  // ── Animation loop ────────────────────────────────────────────────────
  let lastTime = performance.now();

  function updatePositions(now) {
    const dt = (now - lastTime) / 1000;  // seconds
    lastTime = now;

    const vw = window.innerWidth;

    for (const line of lines) {
      const dx = line.speed * dt;

      if (line.direction === 0) {
        // left-to-right
        line.x += dx;
        // If fully off-screen to the right, reset to left
        if (line.x > vw + 50) {
          line.x = -line.textWidth - 50 - Math.random() * 100;
          // Optionally change text/color when looping
          line.el.textContent = pick(CONFIG.texts);
          line.el.style.color = pick(CONFIG.colors);
          // Re-measure after text change
          line.textWidth = line.el.offsetWidth;
        }
      } else {
        // right-to-left
        line.x -= dx;
        // If fully off-screen to the left, reset to right
        if (line.x + line.textWidth < -50) {
          line.x = vw + 50 + Math.random() * 100;
          line.el.textContent = pick(CONFIG.texts);
          line.el.style.color = pick(CONFIG.colors);
          line.textWidth = line.el.offsetWidth;
        }
      }

      line.el.style.transform = `translateX(${line.x}px)`;
    }

    requestAnimationFrame(updatePositions);
  }

  // ── Handle window resize ─────────────────────────────────────────────
  window.addEventListener('resize', () => {
    for (const line of lines) {
      line.textWidth = line.el.offsetWidth;
      line.viewWidth = window.innerWidth;
    }
  });

  // ── Fetch texts from API, then start ───────────────────────────────────
  async function init() {
    try {
      const resp = await fetch('/api/scroller/texts');
      if (resp.ok) {
        const data = await resp.json();
        if (data.texts && data.texts.length > 0) {
          CONFIG.texts = data.texts;
        }
      }
    } catch (_e) {
      // fallback: keep default empty, no crash
    }

    // Use requestAnimationFrame to ensure layout is complete
    requestAnimationFrame(() => {
      // Small delay to let font loading finish
      setTimeout(measureLines, 100);
    });
  }

  init();

})();
