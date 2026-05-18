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
      // Center the ring on the toggle button
      circularMenu.style.left = (rect.left + rect.width / 2 - ringSize / 2) + 'px';
      circularMenu.style.top = (rect.top + rect.height / 2 - ringSize / 2) + 'px';
    }

    toggle.addEventListener('click', (e) => {
      e.stopPropagation();
      positionCircularMenu();
      circularMenu.classList.toggle('open');

      // Toggle icon between bars and times
      const icon = toggle.querySelector('i');
      if (circularMenu.classList.contains('open')) {
        icon.className = 'fas fa-times';
      } else {
        icon.className = 'fas fa-bars';
      }
    });

    // Close menu when clicking a link
    circularMenu.querySelectorAll('.circular-menu-item').forEach(link => {
      link.addEventListener('click', () => {
        circularMenu.classList.remove('open');
        const icon = toggle.querySelector('i');
        icon.className = 'fas fa-bars';
      });
    });

    // Close menu when clicking outside
    document.addEventListener('click', (e) => {
      if (circularMenu.classList.contains('open') &&
          !circularMenu.contains(e.target) &&
          e.target !== toggle &&
          !toggle.contains(e.target)) {
        circularMenu.classList.remove('open');
        const icon = toggle.querySelector('i');
        icon.className = 'fas fa-bars';
      }
    });

    // Reposition on scroll and resize
    window.addEventListener('scroll', positionCircularMenu);
    window.addEventListener('resize', positionCircularMenu);
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
