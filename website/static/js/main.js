/**
 * SNH48 演艺信息站 - Main JavaScript
 */

// ── Mobile Circular Menu ──────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  const toggle = document.getElementById('navToggle');
  const navLinks = document.querySelector('.nav-links');
  const circularMenu = document.getElementById('circularMenu');

  if (toggle && circularMenu) {
    // Position the circular menu relative to the toggle button
    function positionCircularMenu() {
      const rect = toggle.getBoundingClientRect();
      const ringSize = 280;
      // getBoundingClientRect() returns visual viewport coordinates,
      // but position:fixed uses the layout viewport.
      // On iOS pinch-zoom, visualViewport.offsetLeft/Top accounts for the
      // offset between the two — without this the ring drifts away from the toggle.
      const vv = window.visualViewport;
      const offsetLeft = vv ? vv.offsetLeft : 0;
      const offsetTop  = vv ? vv.offsetTop : 0;
      // Center the ring on the toggle button
      circularMenu.style.left = (rect.left + rect.width / 2 - ringSize / 2 - offsetLeft) + 'px';
      circularMenu.style.top  = (rect.top + rect.height / 2 - ringSize / 2 - offsetTop) + 'px';
    }

    function openCircularMenu() {
      positionCircularMenu();
      // Hide the toggle button so the ring's center close icon takes its place
      toggle.classList.add('hidden');
      circularMenu.classList.add('open');
    }

    function closeCircularMenu() {
      circularMenu.classList.remove('open');
      // Show the toggle button again after menu closes
      toggle.classList.remove('hidden');
    }

    toggle.addEventListener('click', (e) => {
      e.stopPropagation();
      if (circularMenu.classList.contains('open')) {
        closeCircularMenu();
      } else {
        openCircularMenu();
      }
    });

    // Close menu when clicking the center close button
    const closeBtn = document.getElementById('circularMenuClose');
    if (closeBtn) {
      closeBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        closeCircularMenu();
      });
    }

    // Close menu when clicking the ring background (not on items)
    const ring = circularMenu.querySelector('.circular-menu-ring');
    if (ring) {
      ring.addEventListener('click', (e) => {
        // Only close if clicking the ring itself or the close button
        if (e.target === ring || e.target.closest('.circular-menu-close')) {
          closeCircularMenu();
        }
      });
    }

    // Close menu when clicking a link
    circularMenu.querySelectorAll('.circular-menu-item').forEach(link => {
      link.addEventListener('click', () => {
        closeCircularMenu();
      });
    });

    // Close menu when clicking outside
    document.addEventListener('click', (e) => {
      if (circularMenu.classList.contains('open') &&
          !circularMenu.contains(e.target) &&
          e.target !== toggle &&
          !toggle.contains(e.target)) {
        closeCircularMenu();
      }
    });

    // Reposition on scroll and resize
    window.addEventListener('scroll', positionCircularMenu);
    window.addEventListener('resize', positionCircularMenu);
    // iOS pinch-zoom changes the visual viewport — listen to its events
    // so the ring stays centred on the toggle button.
    if (window.visualViewport) {
      window.visualViewport.addEventListener('resize', positionCircularMenu);
      window.visualViewport.addEventListener('scroll', positionCircularMenu);
    }
  }

  // ── Highlight "陈嘉仪" in all text nodes ────────────────────────────────
  highlightCJY(document.body);
});

/**
 * Walk all text nodes under root and highlight occurrences of "陈嘉仪".
 * Works on static page content (about, qa descriptions, etc.).
 */
function highlightCJY(root) {
  const treeWalker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, null, false);
  const toReplace = [];

  // Collect text nodes first (walking while modifying DOM can be problematic)
  while (treeWalker.nextNode()) {
    const node = treeWalker.currentNode;
    // Skip script, style, and other non-visible elements
    const parent = node.parentElement;
    if (!parent || parent.tagName === 'SCRIPT' || parent.tagName === 'STYLE' ||
        parent.closest('.scroll-text')) {
      continue;
    }
    if (node.textContent.includes('陈嘉仪')) {
      toReplace.push(node);
    }
  }

  for (const node of toReplace) {
    const frag = document.createDocumentFragment();
    const parts = node.textContent.split(/(陈嘉仪)/g);
    for (const part of parts) {
      if (part === '陈嘉仪') {
        const span = document.createElement('span');
        span.className = 'highlight-cjy';
        span.textContent = part;
        frag.appendChild(span);
      } else if (part) {
        frag.appendChild(document.createTextNode(part));
      }
    }
    node.parentNode.replaceChild(frag, node);
  }
}
