/**
 * SNH48 演艺信息站 - Main JavaScript
 */

// ── Mobile Nav Toggle ──────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  const toggle = document.getElementById('navToggle');
  const navLinks = document.querySelector('.nav-links');
  if (toggle && navLinks) {
    toggle.addEventListener('click', () => {
      navLinks.classList.toggle('open');
    });
    // Close nav on link click
    navLinks.querySelectorAll('a').forEach(link => {
      link.addEventListener('click', () => {
        navLinks.classList.remove('open');
      });
    });
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
