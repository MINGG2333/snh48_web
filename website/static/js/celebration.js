/** Homepage celebration for Chen Jiayi's 300th debut day. */
(function() {
  'use strict';

  const overlay = document.getElementById('debutCelebration');
  const replayButton = document.getElementById('celebrationReplay');
  if (!overlay || !replayButton) return;

  const skipButton = document.getElementById('celebrationSkip');
  const confetti = document.getElementById('celebrationConfetti');
  const duration = Number.parseInt(overlay.dataset.duration || '10000', 10);
  const storageKey = `debut_300_seen_${overlay.dataset.celebrationKey || 'active'}`;
  let closeTimer = null;
  let hideFinalizeTimer = null;
  let previousFocus = null;

  function buildConfetti() {
    if (!confetti || confetti.childElementCount > 0) return;
    const colors = ['#ff6b9d', '#ffe08a', '#c084fc', '#60a5fa', '#ffffff'];
    for (let i = 0; i < 54; i++) {
      const piece = document.createElement('span');
      piece.className = 'celebration-confetti-piece';
      piece.style.setProperty('--confetti-x', `${Math.random() * 100}%`);
      piece.style.setProperty('--confetti-delay', `${Math.random() * -8}s`);
      piece.style.setProperty('--confetti-duration', `${5 + Math.random() * 4}s`);
      piece.style.setProperty('--confetti-drift', `${-90 + Math.random() * 180}px`);
      piece.style.setProperty('--confetti-rotate', `${360 + Math.random() * 720}deg`);
      piece.style.backgroundColor = colors[i % colors.length];
      confetti.appendChild(piece);
    }
  }

  function hideCelebration() {
    if (closeTimer) window.clearTimeout(closeTimer);
    if (hideFinalizeTimer) window.clearTimeout(hideFinalizeTimer);
    closeTimer = null;
    overlay.classList.remove('is-visible');
    document.body.classList.remove('celebration-open');
    hideFinalizeTimer = window.setTimeout(() => {
      overlay.hidden = true;
      hideFinalizeTimer = null;
      if (previousFocus && typeof previousFocus.focus === 'function') previousFocus.focus();
    }, 420);
  }

  function showCelebration() {
    if (closeTimer) window.clearTimeout(closeTimer);
    if (hideFinalizeTimer) window.clearTimeout(hideFinalizeTimer);
    hideFinalizeTimer = null;
    previousFocus = document.activeElement;
    buildConfetti();
    overlay.hidden = false;
    document.body.classList.add('celebration-open');
    // Reflow restarts the ten-second progress bar when "再看庆祝" is pressed.
    void overlay.offsetWidth;
    window.requestAnimationFrame(() => {
      overlay.classList.add('is-visible');
      if (skipButton) skipButton.focus({ preventScroll: true });
    });
    closeTimer = window.setTimeout(hideCelebration, Number.isFinite(duration) ? duration : 10000);
  }

  replayButton.addEventListener('click', showCelebration);
  if (skipButton) skipButton.addEventListener('click', hideCelebration);
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && !overlay.hidden) hideCelebration();
  });

  let alreadySeen = false;
  try {
    alreadySeen = window.sessionStorage.getItem(storageKey) === '1';
    if (!alreadySeen) window.sessionStorage.setItem(storageKey, '1');
  } catch (_error) {
    // Storage can be unavailable in strict privacy modes; the animation still works.
  }
  if (!alreadySeen) window.setTimeout(showCelebration, 350);
})();
