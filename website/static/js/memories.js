(function() {
  'use strict';

  const PAGE_SIZE = 24;
  const storageKey = 'memories_view_password';

  const state = {
    password: '',
    mode: '',
    modePassword: '',
    page: 1,
    totalPages: 1,
    optionsLoaded: false,
  };

  const els = {};

  document.addEventListener('DOMContentLoaded', init);

  function init() {
    bindElements();
    bindEvents();
    state.password = localStorage.getItem(storageKey) || '';
    if (state.password) {
      els.password.value = state.password;
      loadMemories().then(showApp).catch(() => {
        localStorage.removeItem(storageKey);
        state.password = '';
      });
    }
  }

  function bindElements() {
    [
      'memoriesLogin', 'memoriesLoginForm', 'memoriesPassword', 'memoriesLoginError',
      'memoriesApp', 'memoryTotal', 'memoryPending', 'memoryTypeKinds',
      'memoryPlatformKinds', 'memoryTypeFilter', 'memoryPlatformFilter',
      'memoryConfirmFilter', 'memorySearch', 'memoryApplyFilters',
      'memoryResetFilters', 'memoryModeLabel', 'memoryModeHint',
      'memoryModeForm', 'memoryModeSelect', 'memoryModePassword',
      'memoryExitMode', 'memoryListMeta', 'memoryRefresh', 'memoryList',
      'memoryPrevPage', 'memoryNextPage', 'memoryPageLabel',
      'memorySubmitForm', 'submitType', 'submitTitle', 'submitOccurredAt',
      'submitActor', 'submitPlatform', 'submitSourceUrl', 'submitSummary',
      'submitTags', 'submitSoftPrivate', 'memorySubmitResult',
    ].forEach((id) => {
      els[toKey(id)] = document.getElementById(id);
    });
    els.password = els.memoriesPassword;
  }

  function bindEvents() {
    els.memoriesLoginForm.addEventListener('submit', handleLogin);
    els.memoryApplyFilters.addEventListener('click', () => {
      state.page = 1;
      track('admin_filter', filterTrackPayload('apply'));
      loadMemories();
    });
    els.memoryResetFilters.addEventListener('click', resetFilters);
    els.memoryRefresh.addEventListener('click', () => loadMemories());
    els.memoryPrevPage.addEventListener('click', () => changePage(-1));
    els.memoryNextPage.addEventListener('click', () => changePage(1));
    els.memorySubmitForm.addEventListener('submit', submitMemory);
    els.memoryModeForm.addEventListener('submit', enterMode);
    els.memoryExitMode.addEventListener('click', exitMode);
    els.memorySearch.addEventListener('keydown', (event) => {
      if (event.key === 'Enter') {
        event.preventDefault();
        state.page = 1;
        loadMemories();
      }
    });
  }

  async function handleLogin(event) {
    event.preventDefault();
    const password = els.password.value.trim();
    if (!password) {
      setLoginError('请输入访问密码');
      return;
    }
    state.password = password;
    try {
      await loadMemories();
      localStorage.setItem(storageKey, password);
      setLoginError('');
      showApp();
      track('login_attempt', { area: 'memories', result: 'success', mode: 'view' });
    } catch (error) {
      state.password = '';
      localStorage.removeItem(storageKey);
      setLoginError(error.message || '进入失败');
      track('login_attempt', { area: 'memories', result: 'failure', mode: 'view' });
    }
  }

  function showApp() {
    els.memoriesLogin.classList.add('hidden');
    els.memoriesApp.hidden = false;
  }

  function setLoginError(message) {
    els.memoriesLoginError.textContent = message || '';
  }

  async function loadMemories() {
    if (!state.password && !state.mode) return;
    setListLoading('正在读取记忆...');
    const params = new URLSearchParams({
      page: String(state.page),
      page_size: String(PAGE_SIZE),
      memory_type: els.memoryTypeFilter.value || 'all',
      confirmation_status: els.memoryConfirmFilter.value || 'all',
      q: els.memorySearch.value.trim(),
    });

    let url = '/api/memories/data';
    if (state.mode) {
      url = '/api/memories/manage';
      params.set('mode', state.mode);
      params.set('audit_status', 'all');
    } else {
      params.set('actor_platform', els.memoryPlatformFilter.value || 'all');
    }

    const data = await fetchJson(`${url}?${params.toString()}`, {
      method: 'GET',
      headers: authHeaders(),
    });
    state.totalPages = data.total_pages || 1;
    if (!state.optionsLoaded) {
      renderOptions(data);
      state.optionsLoaded = true;
    }
    renderSummary(data.summary || {});
    renderList(data.items || []);
    renderPagination(data);
    return data;
  }

  async function submitMemory(event) {
    event.preventDefault();
    clearSubmitResult();
    const payload = {
      memory_type: els.submitType.value,
      title: els.submitTitle.value.trim(),
      occurred_at: els.submitOccurredAt.value.trim(),
      summary: els.submitSummary.value.trim(),
      public_note: '',
      actor_display_name: els.submitActor.value.trim(),
      actor_platform: els.submitPlatform.value,
      source_url: els.submitSourceUrl.value.trim(),
      source_label: '粉丝登记',
      evidence_note: '',
      privacy_level: els.submitSoftPrivate.checked ? 'soft_private' : 'public',
      tags: parseTags(els.submitTags.value),
    };
    try {
      const data = await fetchJson('/api/memories/submit', {
        method: 'POST',
        headers: Object.assign(authHeaders(), { 'Content-Type': 'application/json' }),
        body: JSON.stringify(payload),
      });
      els.memorySubmitResult.textContent = data.message || '提交成功';
      els.memorySubmitResult.classList.add('ok');
      els.memorySubmitForm.reset();
      setDefaultSubmitValues();
      state.page = 1;
      await loadMemories();
      track('memory_submit', {
        area: 'memories',
        result: 'success',
        memory_type: payload.memory_type,
        actor_platform: payload.actor_platform,
        has_source_url: Boolean(payload.source_url),
        privacy_level: payload.privacy_level,
      });
    } catch (error) {
      els.memorySubmitResult.textContent = error.message || '提交失败';
      els.memorySubmitResult.classList.remove('ok');
      track('memory_submit', {
        area: 'memories',
        result: 'failure',
        memory_type: payload.memory_type,
        actor_platform: payload.actor_platform,
        has_source_url: Boolean(payload.source_url),
        privacy_level: payload.privacy_level,
      });
    }
  }

  async function enterMode(event) {
    event.preventDefault();
    const mode = els.memoryModeSelect.value;
    const password = els.memoryModePassword.value.trim();
    if (!password) return;
    const oldMode = state.mode;
    const oldPassword = state.modePassword;
    state.mode = mode;
    state.modePassword = password;
    state.page = 1;
    try {
      await loadMemories();
      renderMode();
      track('login_attempt', { area: 'memories', result: 'success', mode });
    } catch (error) {
      state.mode = oldMode;
      state.modePassword = oldPassword;
      renderMode();
      alert(error.message || '进入模式失败');
      track('login_attempt', { area: 'memories', result: 'failure', mode });
    }
  }

  function exitMode() {
    state.mode = '';
    state.modePassword = '';
    state.page = 1;
    els.memoryModePassword.value = '';
    renderMode();
    loadMemories();
  }

  async function reviewMemory(id, action) {
    let reason = '';
    if (action === 'reject' || action === 'hide') {
      reason = window.prompt('可填写处理备注（可留空）') || '';
    }
    try {
      await fetchJson('/api/memories/review', {
        method: 'POST',
        headers: Object.assign(authHeaders(), { 'Content-Type': 'application/json' }),
        body: JSON.stringify({ id, action, reason }),
      });
      track('admin_update', { area: 'memories', action, result: 'success', item_id: id });
      await loadMemories();
    } catch (error) {
      alert(error.message || '操作失败');
      track('admin_update', { area: 'memories', action, result: 'failure', item_id: id });
    }
  }

  function renderOptions(data) {
    fillSelect(els.memoryTypeFilter, data.memory_types || [], '全部类型');
    fillSelect(els.submitType, data.memory_types || [], '');
    fillSelect(els.memoryPlatformFilter, data.platforms || [], '全部平台');
    fillSelect(els.submitPlatform, data.platforms || [], '');
    setDefaultSubmitValues();
  }

  function fillSelect(select, options, allLabel) {
    select.replaceChildren();
    if (allLabel) {
      const all = document.createElement('option');
      all.value = 'all';
      all.textContent = allLabel;
      select.appendChild(all);
    }
    options.forEach((item) => {
      const option = document.createElement('option');
      option.value = item.key;
      option.textContent = item.label;
      select.appendChild(option);
    });
  }

  function setDefaultSubmitValues() {
    if (els.submitType && !els.submitType.value) {
      els.submitType.value = 'fan_expression';
    }
    if (els.submitPlatform && !els.submitPlatform.value) {
      els.submitPlatform.value = 'other';
    }
  }

  function renderSummary(summary) {
    const byType = summary.by_type || [];
    const byPlatform = summary.by_platform || [];
    els.memoryTotal.textContent = String(summary.total_public || 0);
    els.memoryPending.textContent = String(summary.pending_confirmation || 0);
    els.memoryTypeKinds.textContent = String(byType.filter((item) => item.count > 0).length);
    els.memoryPlatformKinds.textContent = String(byPlatform.filter((item) => item.count > 0).length);
  }

  function renderList(items) {
    els.memoryList.replaceChildren();
    if (!items.length) {
      const empty = document.createElement('div');
      empty.className = 'memory-empty';
      empty.textContent = '暂时没有符合条件的记忆。';
      els.memoryList.appendChild(empty);
      return;
    }
    items.forEach((item) => {
      els.memoryList.appendChild(createMemoryCard(item));
    });
  }

  function createMemoryCard(item) {
    const card = document.createElement('article');
    card.className = 'memory-card';

    const imageUrl = item.media && (item.media.thumbnail_url || item.media.image_url);
    if (imageUrl) {
      const img = document.createElement('img');
      img.className = 'memory-thumb';
      img.src = imageUrl;
      img.alt = '';
      img.loading = 'lazy';
      card.appendChild(img);
    } else {
      const placeholder = document.createElement('div');
      placeholder.className = 'memory-thumb';
      placeholder.setAttribute('aria-hidden', 'true');
      card.appendChild(placeholder);
    }

    const body = document.createElement('div');
    body.className = 'memory-body';
    card.appendChild(body);

    const meta = document.createElement('div');
    meta.className = 'memory-meta';
    meta.appendChild(chip(item.memory_type_label, 'type', 'fa-bookmark'));
    if (item.occurred_at) meta.appendChild(chip(item.occurred_at, '', 'fa-calendar-day'));
    body.appendChild(meta);

    const title = document.createElement('h3');
    title.textContent = item.title || '未命名记忆';
    body.appendChild(title);

    const summary = document.createElement('p');
    summary.className = 'memory-summary';
    summary.textContent = item.summary || '';
    body.appendChild(summary);

    if (item.public_note) {
      const note = document.createElement('p');
      note.className = 'memory-note';
      note.textContent = item.public_note;
      body.appendChild(note);
    }

    const tags = document.createElement('div');
    tags.className = 'memory-tags';
    (item.tags || []).forEach((tag) => tags.appendChild(chip(tag, '', 'fa-tag')));
    if (tags.childNodes.length) body.appendChild(tags);

    const statuses = document.createElement('div');
    statuses.className = 'memory-statuses';
    const confirmClass = item.confirmation_status === 'unconfirmed' ? 'pending' : 'confirmed';
    statuses.appendChild(chip(item.confirmation_status_label, confirmClass, 'fa-circle-check'));
    if (state.mode && item.audit_status) {
      const reviewClass = item.audit_status === 'pending_manual' || item.audit_status === 'rejected' ? 'review' : '';
      statuses.appendChild(chip(item.audit_status_label, reviewClass, 'fa-shield-halved'));
      statuses.appendChild(chip(item.visibility || 'public', '', 'fa-eye'));
    }
    body.appendChild(statuses);

    body.appendChild(sourceLine(item));

    const actions = actionButtons(item);
    if (actions) body.appendChild(actions);
    return card;
  }

  function sourceLine(item) {
    const row = document.createElement('div');
    row.className = 'memory-source';
    const actor = item.actor || {};
    const source = item.source || {};
    const actorText = actor.display_name ? `${actor.display_name} · ${actor.platform_label || ''}` : actor.platform_label || '';
    if (actorText) row.appendChild(textSpan(actorText));
    if (source.label) row.appendChild(textSpan(source.label));
    if (source.url) {
      const link = document.createElement('a');
      link.href = source.url;
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
      link.textContent = '来源';
      row.appendChild(link);
    }
    return row;
  }

  function actionButtons(item) {
    if (!state.mode) return null;
    const row = document.createElement('div');
    row.className = 'memory-actions';
    if (state.mode === 'fanclub') {
      if (item.audit_status === 'pending_manual' || item.visibility !== 'public') {
        row.appendChild(actionButton('通过', 'approve', item.id, 'fa-check'));
      }
      if (item.audit_status !== 'rejected') {
        row.appendChild(actionButton('拒绝', 'reject', item.id, 'fa-ban', 'danger'));
      }
      if (item.visibility === 'public') {
        row.appendChild(actionButton('隐藏', 'hide', item.id, 'fa-eye-slash', 'secondary'));
      }
      if (item.confirmation_status !== 'fanclub_confirmed' && item.confirmation_status !== 'idol_confirmed') {
        row.appendChild(actionButton('应援会确认', 'confirm_fanclub', item.id, 'fa-user-shield'));
      }
      if (item.confirmation_status !== 'unconfirmed') {
        row.appendChild(actionButton('取消确认', 'unconfirm', item.id, 'fa-rotate-left', 'secondary'));
      }
    }
    if (state.mode === 'idol' && item.confirmation_status !== 'idol_confirmed') {
      row.appendChild(actionButton('本人确认', 'confirm_idol', item.id, 'fa-heart'));
    }
    return row.childNodes.length ? row : null;
  }

  function actionButton(label, action, id, icon, extraClass) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = `memory-action ${extraClass || ''}`.trim();
    appendIcon(button, icon);
    button.appendChild(document.createTextNode(label));
    button.addEventListener('click', () => reviewMemory(id, action));
    return button;
  }

  function chip(text, extraClass, icon) {
    const span = document.createElement('span');
    span.className = `chip ${extraClass || ''}`.trim();
    if (icon) appendIcon(span, icon);
    span.appendChild(document.createTextNode(text || ''));
    return span;
  }

  function appendIcon(parent, icon) {
    const i = document.createElement('i');
    i.className = `fas ${icon}`;
    parent.appendChild(i);
  }

  function textSpan(text) {
    const span = document.createElement('span');
    span.textContent = text;
    return span;
  }

  function renderPagination(data) {
    const total = data.total || 0;
    const page = data.page || state.page;
    state.totalPages = data.total_pages || 1;
    els.memoryListMeta.textContent = `共 ${total} 条，当前第 ${page} / ${state.totalPages} 页`;
    els.memoryPageLabel.textContent = `第 ${page} / ${state.totalPages} 页`;
    els.memoryPrevPage.disabled = page <= 1;
    els.memoryNextPage.disabled = page >= state.totalPages;
  }

  function renderMode() {
    if (!state.mode) {
      els.memoryModeLabel.textContent = '普通模式';
      els.memoryModeHint.textContent = '普通模式只显示已经通过展示审核的记忆。';
      els.memoryExitMode.hidden = true;
      return;
    }
    const label = state.mode === 'idol' ? '本人模式' : '应援会模式';
    els.memoryModeLabel.textContent = label;
    els.memoryModeHint.textContent = state.mode === 'idol'
      ? '本人模式可确认已经公开展示的记忆。'
      : '应援会模式可审核待处理内容，并进行应援会确认。';
    els.memoryExitMode.hidden = false;
  }

  function changePage(delta) {
    const next = state.page + delta;
    if (next < 1 || next > state.totalPages) return;
    state.page = next;
    loadMemories();
  }

  function resetFilters() {
    els.memoryTypeFilter.value = 'all';
    els.memoryPlatformFilter.value = 'all';
    els.memoryConfirmFilter.value = 'all';
    els.memorySearch.value = '';
    state.page = 1;
    track('admin_filter', filterTrackPayload('reset'));
    loadMemories();
  }

  function setListLoading(message) {
    els.memoryListMeta.textContent = message;
  }

  function clearSubmitResult() {
    els.memorySubmitResult.textContent = '';
    els.memorySubmitResult.classList.remove('ok');
  }

  function parseTags(value) {
    return value
      .split(/[,，、\s]+/)
      .map((item) => item.trim())
      .filter(Boolean)
      .slice(0, 8);
  }

  function authHeaders() {
    const headers = {
      'Accept': 'application/json',
    };
    if (state.password) headers['X-Memories-Password'] = state.password;
    if (state.mode === 'fanclub') headers['X-Memories-Fanclub-Password'] = state.modePassword;
    if (state.mode === 'idol') headers['X-Memories-Idol-Password'] = state.modePassword;
    return headers;
  }

  async function fetchJson(url, options) {
    const response = await fetch(url, options);
    let data = null;
    try {
      data = await response.json();
    } catch (error) {
      data = {};
    }
    if (!response.ok) {
      throw new Error(data.detail || `请求失败：${response.status}`);
    }
    return data;
  }

  function filterTrackPayload(action) {
    return {
      area: 'memories',
      action,
      memory_type: els.memoryTypeFilter.value || 'all',
      actor_platform: els.memoryPlatformFilter.value || 'all',
      confirmation_status: els.memoryConfirmFilter.value || 'all',
      has_query: Boolean(els.memorySearch.value.trim()),
      mode: state.mode || 'view',
    };
  }

  function track(eventType, data) {
    if (!window._trackEvent) return;
    window._trackEvent(eventType, data || {});
  }

  function toKey(id) {
    return id.replace(/^[a-z]/, (char) => char.toLowerCase());
  }
})();
