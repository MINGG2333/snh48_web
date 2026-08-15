/**
 * User Behavior Tracker
 *
 * Automatically tracks user browsing and interaction events on the website.
 * Sends events to the server for logging and notification center integration.
 *
 * Tracked events:
 *   - Page views (on load)
 *   - Button clicks (via data-track attribute)
 *   - Q&A submissions and completions
 *   - Email submissions
 *   - Screenshot saves
 *   - Login attempts
 *   - Form submissions
 *
 * Usage:
 *   Add data-track="event_name" to any HTML element to track clicks on it.
 *   Or call window._trackEvent(type, data) manually.
 */
(function() {
  'use strict';

  // ── Client ID (persistent across page views) ──────────────────────────
  let clientId = sessionStorage.getItem('client_id');
  if (!clientId) {
    clientId = 'user_' + Math.random().toString(36).substring(2, 10) + '_' + Date.now().toString(36);
    sessionStorage.setItem('client_id', clientId);
  }

  // Browser profile ID: stable across tabs and IP changes for this origin.
  // This is an opaque first-party identifier, not a physical-device
  // fingerprint and not proof of a natural person's identity.
  const visitorStorageKey = 'ob_visitor_id';
  let visitorId = '';
  try {
    visitorId = localStorage.getItem(visitorStorageKey) || '';
  } catch (_) {}
  if (!/^visitor_[A-Za-z0-9_-]{8,96}$/.test(visitorId)) {
    try {
      visitorId = sessionStorage.getItem(visitorStorageKey) || '';
    } catch (_) {}
  }
  if (!/^visitor_[A-Za-z0-9_-]{8,96}$/.test(visitorId)) {
    const randomPart = (window.crypto && typeof window.crypto.randomUUID === 'function')
      ? window.crypto.randomUUID().replace(/-/g, '')
      : Math.random().toString(36).substring(2, 14) + Math.random().toString(36).substring(2, 14);
    visitorId = 'visitor_' + randomPart + '_' + Date.now().toString(36);
    try {
      localStorage.setItem(visitorStorageKey, visitorId);
    } catch (_) {
      // Storage-disabled browsers remain session-scoped instead of using
      // invasive fingerprinting as a fallback.
      try { sessionStorage.setItem(visitorStorageKey, visitorId); } catch (_) {}
    }
  }

  // ── Current page info ─────────────────────────────────────────────────
  const currentPage = window.location.pathname;

  // ── Send event to server ──────────────────────────────────────────────
  function sendEvent(eventType, eventData) {
    const payload = {
      client_id: clientId,
      event_type: eventType,
      data: Object.assign({ page: currentPage }, eventData),
    };
    if (eventType === 'page_view') {
      payload.visitor_id = visitorId;
    }

    // Use sendBeacon for reliability (works during page unload)
    try {
      const blob = new Blob([JSON.stringify(payload)], { type: 'application/json' });
      navigator.sendBeacon('/api/track/event', blob);
    } catch (e) {
      // Fallback to fetch
      fetch('/api/track/event', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
        keepalive: true,
      }).catch(() => {});
    }
  }

  // ── Track page view on load ───────────────────────────────────────────
  function trackPageView() {
    const pageNames = {
      '/': '首页',
      '/about': '关于',
      '/qa': 'AI 问答',
      '/terms': '服务条款',
      '/privacy': '隐私政策',
      '/complaint': '投诉举报',
      '/scroller-admin': '滚动管理',
    };
    const pageName = pageNames[currentPage] || currentPage;

    sendEvent('page_view', {
      page: currentPage,
      page_name: pageName,
      referrer: document.referrer || '',
      title: document.title,
    });
  }

  // ── Track clicks on elements with data-track attribute ────────────────
  function setupClickTracking() {
    document.addEventListener('click', function(e) {
      // Check for data-track attribute on clicked element or its parents
      let target = e.target;
      while (target && target !== document.body) {
        const trackAttr = target.getAttribute('data-track');
        if (trackAttr) {
          // Skip tracking if the element (or its closest interactive ancestor) is disabled.
          // This prevents tracking clicks on disabled inputs/buttons before authentication.
          if (target.disabled || target.closest('[disabled]')) {
            return;
          }
          const extraData = {};
          // Collect additional data attributes
          for (const attr of target.attributes) {
            if (attr.name.startsWith('data-track-')) {
              const key = attr.name.replace('data-track-', '');
              extraData[key] = attr.value;
            }
          }
          sendEvent('click', {
            action: trackAttr,
            element: target.tagName.toLowerCase(),
            text: target.textContent.trim().substring(0, 50),
            id: target.id || '',
            class: target.className.substring(0, 100),
            ...extraData,
          });
          return;
        }
        target = target.parentElement;
      }
    });
  }

  // ── Expose global tracking function ───────────────────────────────────
  window._trackEvent = function(eventType, eventData, pushToNotification) {
    sendEvent(eventType, Object.assign({}, eventData, {
      _push_to_notification: pushToNotification ? true : undefined,
    }));
  };

  // ── Init ──────────────────────────────────────────────────────────────
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function() {
      trackPageView();
      setupClickTracking();
    });
  } else {
    trackPageView();
    setupClickTracking();
  }
})();
