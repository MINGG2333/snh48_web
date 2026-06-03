/**
 * SNH48 演艺信息站 - 时光轴 Timeline (Phase 2)
 *
 * 功能：水平拖拽滑动时间轴 + 节点分支引出卡片 + 点击弹出详情弹窗
 * 数据：手动硬编码事件 + 服务器直播记录(LIVEPUSH) 自动合并
 */

// ═══════════════════════════════════════════════════════════════════════════
//  Manual Event Data (硬编码，保留)
// ═══════════════════════════════════════════════════════════════════════════

const MANUAL_EVENTS = [
  {
    id: 'join', source: 'manual', date: '2025-09-23',
    title: '加入 SNH48 二十三期生', type: 'milestone', typeLabel: '里程碑',
    description: `2025年9月23日，陈嘉仪正式加入 SNH48 二十三期生，时年20岁。\n\n作为 SNH48 新生代成员，陈嘉仪以独特的气质和才艺获得了关注。官方资料显示，她的特长是"反射弧特长"（官方认证反应慢），爱好包括看国漫、唱歌跳舞、舞团练习室视频和玩游戏。\n\n她的 Catch Phrase 是："陈可以是加减乘除的乘，嘉可以是加减乘除的加，仪可以是一二三四的一。"粉丝亲切地称她为"×＋1"或"甲鱼"。`,
    image: null, icon: 'fa-star',
  },
  {
    id: 'debut', source: 'manual', date: '2025-10-05',
    title: '星梦剧院首演《B·RISE 梦之门》', type: 'milestone', typeLabel: '里程碑 · 公演',
    description: `2025年10月5日 & 10月6日 19:00\n📍 SNH48 星梦剧院\n\nSNH48 23期新生公演《B·RISE 梦之门》在星梦剧院盛大首演！这是陈嘉仪登上 SNH48 舞台的出道首秀。\n\n首演中，陈嘉仪与同期23期生李婷在公演中上演了"小学鸡拌嘴名场面"，活泼可爱的互动给粉丝们留下了深刻印象。`,
    image: null, icon: 'fa-theater-masks',
  },
  {
    id: 'promotion', source: 'manual', date: '2026-02-08',
    title: '升格 TEAM HII 正式成员', type: 'milestone', typeLabel: '里程碑',
    description: `2026年2月8日，陈嘉仪公演考核通过，正式升格为 SNH48 TEAM HII 正式成员！\n\n同期升格的还有刘思雨。\n\n"What time is it ! combat time ! We are the only one ! Team HII !"\n\n愿她们永远怀抱"闪着光的信念"，守护"发芽的梦想"，在 TEAM HII 的篇章里，亲手摘取属于自己的梦想果实。`,
    image: null, icon: 'fa-crown',
  },
  {
    id: 'miluo-external', source: 'manual', date: '2026-06-19',
    title: '湖南汨罗外务', type: 'external', typeLabel: '外务',
    description: `📅 2026年6月19日（星期五）\n🕐 时间待定\n📍 湖南汨罗\n\n陈嘉仪将赴湖南汨罗参加外务活动，这是她升格后的首次外务演出，期待她在舞台上的精彩表现！`,
    image: null, icon: 'fa-plane',
  },
  {
    id: 'guangzhou-tour', source: 'manual', date: '2026-06-28',
    title: '广州巡演', type: 'tour', typeLabel: '巡演',
    description: `📅 2026年6月28日（星期日）\n🕐 时间待定\n📍 广州\n\n广州巡演！作为巡演系列的最后一站，陈嘉仪将在广州带来精彩的舞台表演，与粉丝们近距离互动。`,
    image: null, icon: 'fa-bus',
  },
];

const BADGE_CLASS_MAP = {
  milestone: 'milestone', tour: 'tour', show: 'show',
  event: 'event', external: 'external', live: 'event',
  公演: 'show', 外务: 'external', 见面会: 'event', 其他: 'event',
};

// ── Today's date for comparison ──
const TODAY = new Date();
let activeSources = new Set(['manual', 'room', 'assistant']); // which sources are selected
let allLiveEvents = [];   // fetched from API
let allScheduleEvents = []; // fetched from schedule API

// ── Format date (top-level so data can reference it) ──
function formatDate(dateInput) {
  const d = typeof dateInput === 'string' ? new Date(dateInput) : dateInput;
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}.${m}.${day}`;
}

// ═══════════════════════════════════════════════════════════════════════════
//  Timeline Rendering
// ═══════════════════════════════════════════════════════════════════════════

document.addEventListener('DOMContentLoaded', () => {
  const track = document.getElementById('timelineTrack');
  const trackInner = document.getElementById('timelineTrackInner');
  const wrapper = document.getElementById('timelineWrapper');
  const overlay = document.getElementById('timelineModalOverlay');
  const modalContent = document.getElementById('timelineModalContent');
  const modalClose = document.getElementById('timelineModalClose');
  const hint = document.getElementById('timelineHint');
  const zoomIn = document.getElementById('zoomIn');
  const zoomOut = document.getElementById('zoomOut');
  const dateInput = document.getElementById('timelineDateInput');
  const dateJumpBtn = document.getElementById('timelineDateJump');
  const filterBtns = document.querySelectorAll('.timeline-filter-btn');

  let scale = 1;
  const MIN_SCALE = 0.5;
  const MAX_SCALE = 1.8;
  let mergedEvents = []; // current filtered event list

  // ── Group events by date ──
  function groupByDate(events) {
    const map = {};
    events.forEach(ev => {
      const d = ev.date;
      if (!map[d]) map[d] = [];
      map[d].push(ev);
    });
    return Object.entries(map).sort((a, b) => a[0].localeCompare(b[0]));
  }

  // ── Get filtered event list ──
  function getFilteredEvents() {
    let list = [];
    if (activeSources.has('manual')) {
      list = list.concat(MANUAL_EVENTS);
    }
    if (activeSources.has('room')) {
      list = list.concat(allLiveEvents);
    }
    if (activeSources.has('assistant')) {
      list = list.concat(allScheduleEvents);
    }
    list.sort((a, b) => a.date.localeCompare(b.date) || (a.datetime || '').localeCompare(b.datetime || ''));
    return list;
  }

  // ── Render events (grouped by date) ──
  function renderTimeline(eventList) {
    trackInner.innerHTML = '';
    const groups = groupByDate(eventList);

    groups.forEach(([dateStr, events], groupIdx) => {
      const isAbove = groupIdx % 2 === 0;
      const sideClass = isAbove ? 'timeline-event-above' : 'timeline-event-below';
      const col = document.createElement('div');
      col.className = `timeline-event ${sideClass}`;
      col.dataset.date = dateStr;

      const eventDate = new Date(dateStr);
      const isToday = eventDate.toDateString() === TODAY.toDateString();
      const dateLabel = formatDate(dateStr) + (isToday ? ' <span class="timeline-today-marker">今天</span>' : '');

      // Build card(s) for this date group
      let cardsHtml = '';
      events.forEach(ev => {
        const badgeClass = BADGE_CLASS_MAP[ev.type] || 'event';
        const hasCover = ev.cover_url || ev.image;
        const imgHtml = hasCover
          ? `<img class="timeline-card-img" src="${ev.cover_url || ev.image}" alt="${ev.title}" loading="lazy">`
          : `<div class="timeline-card-img-placeholder"><i class="fas ${ev.icon || 'fa-calendar'}"></i></div>`;

        const imgClass = hasCover ? 'timeline-card-img loading' : 'timeline-card-img-placeholder';
        // Check for title keyword badges (replace default type badge if matched)
        const title_ = ev.title || '';
        const keywordBadge =
          title_.includes('助演') ? 'show|助演' :
          title_.includes('首演') ? 'milestone|首演' :
          title_.includes('巡演') ? 'tour|巡演' : '';
        const showTypeBadge = !keywordBadge;
        cardsHtml += `
          <div class="timeline-card" data-event-id="${ev.id}">
            ${hasCover ? `<img class="${imgClass}" src="${ev.cover_url || ev.image}" alt="${ev.title}" loading="lazy" onload="this.classList.remove('loading')" onerror="this.classList.remove('loading');this.style.display='none'">` : imgHtml}
            <div class="timeline-card-body">
              <div class="timeline-card-date">${formatDate(ev.date)}${ev.datetime ? ' ' + ev.datetime.slice(11, 16) : ''}</div>
              <div class="timeline-card-title">${ev.title}</div>
              ${showTypeBadge ? `<span class="timeline-card-badge ${badgeClass}">${ev.typeLabel}</span>` : ''}
              ${keywordBadge ? `<span class="timeline-card-badge ${keywordBadge.split('|')[0]}" style="margin-left:4px;">${keywordBadge.split('|')[1]}</span>` : ''}
              ${ev.source === 'room' ? `<span class="timeline-card-badge danmu ${ev.has_danmu ? 'available' : 'missing'}" style="margin-left:4px;">${ev.has_danmu ? '<i class="fas fa-comment-dots"></i> 有弹幕' : '<i class="fas fa-comment-slash"></i> 无弹幕'}</span>` : ''}
              ${ev.has_replay ? '<span class="timeline-card-badge replay" style="background:rgba(74,222,128,0.15);color:#4ade80;border:1px solid rgba(74,222,128,0.2);margin-left:4px;"><i class="fas fa-play"></i> 回放</span>' : ''}
            </div>
          </div>
        `;
      });

      // Build column: for multiple cards on same day, stack them
      const cardWrapperHtml = events.length > 1
        ? `<div class="timeline-card-stack">${cardsHtml}</div>`
        : cardsHtml;

      if (isAbove) {
        col.innerHTML = `
          ${cardWrapperHtml}
          <div class="timeline-connector timeline-connector-above"></div>
          <div class="timeline-node"></div>
          <div class="timeline-node-date">${dateLabel}</div>
        `;
      } else {
        col.innerHTML = `
          <div class="timeline-node-date">${dateLabel}</div>
          <div class="timeline-node"></div>
          <div class="timeline-connector timeline-connector-below"></div>
          ${cardWrapperHtml}
        `;
      }

      // Click handlers on each card
      col.querySelectorAll('.timeline-card').forEach(cardEl => {
        const evId = cardEl.dataset.eventId;
        const ev = events.find(e => e.id === evId);
        if (!ev) return;
        cardEl.addEventListener('click', (e) => {
          e.stopPropagation();
          openModal(ev);
        });
        cardEl.addEventListener('touchend', (e) => {
          if (!wrapper.classList.contains('dragging')) openModal(ev);
        });
      });

      trackInner.appendChild(col);
    });
  }

  // ── Center on nearest event column matching a date ──
  function centerOnDate(targetDate) {
    const target = new Date(targetDate);
    const events = trackInner.querySelectorAll('.timeline-event');
    if (events.length === 0) return;
    let best = 0;
    let bestDiff = Infinity;
    events.forEach((el, i) => {
      const d = new Date(el.dataset.date);
      const diff = Math.abs(d - target);
      if (diff < bestDiff) { bestDiff = diff; best = i; }
    });
    centerOnEvent(best);
  }

  // ── Refresh timeline, optionally preserving current center ──
  function refreshTimeline(preserveCenter) {
    // Use the date input as the authoritative center reference
    const prevDate = preserveCenter && dateInput && dateInput.value ? dateInput.value : null;
    mergedEvents = getFilteredEvents();
    renderTimeline(mergedEvents);
    requestAnimationFrame(() => {
      // Force layout so newly rendered elements have valid positions
      void wrapper.offsetHeight;
      if (prevDate) {
        centerOnDate(prevDate);
      } else {
        // Initial load: center on boundary between past and future
        const events = trackInner.querySelectorAll('.timeline-event');
        if (events.length > 0) {
          let idx = events.length - 1;
          for (let i = 0; i < events.length; i++) {
            const d = new Date(events[i].dataset.date);
            if (d > TODAY) { idx = i; break; }
          }
          centerOnEvent(idx);
        }
      }
      updateTransformOrigin();
    });
  }

  // ── Jump to nearest event for a given date ──
  function jumpToDate(targetDate) {
    const target = new Date(targetDate);
    const events = trackInner.querySelectorAll('.timeline-event');
    if (events.length === 0) return;
    let nearestIdx = 0;
    let minDiff = Infinity;
    events.forEach((el, i) => {
      const d = new Date(el.dataset.date);
      const diff = Math.abs(d - target);
      if (diff < minDiff) { minDiff = diff; nearestIdx = i; }
    });
    centerOnEvent(nearestIdx);
  }

  // ── Custom Datepicker (day / month / year views) ──
  let dpCurrentDate = new Date();
  let dpSelectedDate = new Date();
  let dpViewMode = 'day'; // 'day' | 'month' | 'year'
  const dpPopup = document.getElementById('datepickerPopup');
  const dpMonthYear = document.getElementById('datepickerMonthYear');
  const dpDays = document.getElementById('datepickerDays');
  const dpPrev = document.getElementById('datepickerPrev');
  const dpNext = document.getElementById('datepickerNext');
  const dpTodayBtn = document.getElementById('datepickerToday');
  let dpOpen = false;

  const MONTH_NAMES = ['1月','2月','3月','4月','5月','6月','7月','8月','9月','10月','11月','12月'];

  function formatDateInput(d) {
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${y}-${m}-${day}`;
  }

  function renderDatepicker() {
    const year = dpCurrentDate.getFullYear();
    const month = dpCurrentDate.getMonth();
    const today = new Date();
    const todayStr = formatDateInput(today);
    const selStr = formatDateInput(dpSelectedDate);
    let html = '';

    if (dpViewMode === 'day') {
      // ── Day grid ──
      dpMonthYear.textContent = `${year}年${month + 1}月`;
      // Show weekday headers
      document.querySelector('.datepicker-weekdays').style.display = 'grid';

      const firstDay = new Date(year, month, 1);
      let startDay = firstDay.getDay();
      startDay = startDay === 0 ? 6 : startDay - 1;
      const daysInMonth = new Date(year, month + 1, 0).getDate();
      const daysInPrev = new Date(year, month, 0).getDate();

      // Previous month trailing days
      for (let i = startDay - 1; i >= 0; i--) {
        const d = new Date(year, month - 1, daysInPrev - i);
        html += `<button class="datepicker-day other-month" data-date="${formatDateInput(d)}">${daysInPrev - i}</button>`;
      }
      // Current month days
      for (let d = 1; d <= daysInMonth; d++) {
        const dateStr = formatDateInput(new Date(year, month, d));
        let cls = 'datepicker-day';
        if (dateStr === todayStr) cls += ' today';
        if (dateStr === selStr) cls += ' selected';
        html += `<button class="${cls}" data-date="${dateStr}">${d}</button>`;
      }
      // Next month leading days
      const totalCells = startDay + daysInMonth;
      const remaining = (7 - (totalCells % 7)) % 7;
      const nm = month + 1 > 11 ? 0 : month + 1;
      const ny = month + 1 > 11 ? year + 1 : year;
      for (let d = 1; d <= remaining; d++) {
        const dateStr = formatDateInput(new Date(ny, nm, d));
        html += `<button class="datepicker-day other-month" data-date="${dateStr}">${d}</button>`;
      }

      dpDays.innerHTML = html;
      dpDays.querySelectorAll('.datepicker-day').forEach(btn => {
        btn.addEventListener('click', (e) => {
          e.stopPropagation();
          const ds = btn.dataset.date;
          dpSelectedDate = new Date(ds);
          dateInput.value = ds;
          closeDatepicker();
          jumpToDate(ds);
        });
      });

    } else if (dpViewMode === 'month') {
      // ── Month grid (4×3) ──
      dpMonthYear.textContent = `${year}年`;
      document.querySelector('.datepicker-weekdays').style.display = 'none';

      for (let m = 0; m < 12; m++) {
        const isCurrent = m === month;
        html += `<button class="datepicker-day datepicker-month-item${isCurrent ? ' selected' : ''}" data-month="${m}">${MONTH_NAMES[m]}</button>`;
      }
      dpDays.innerHTML = html;
      dpDays.querySelectorAll('.datepicker-month-item').forEach(btn => {
        btn.addEventListener('click', (e) => {
          e.stopPropagation();
          dpCurrentDate = new Date(year, parseInt(btn.dataset.month), 1);
          dpViewMode = 'day';
          renderDatepicker();
        });
      });

    } else if (dpViewMode === 'year') {
      // ── Year grid (4×3) ──
      const decadeStart = Math.floor(year / 12) * 12;
      dpMonthYear.textContent = `${decadeStart}年 – ${decadeStart + 11}年`;
      document.querySelector('.datepicker-weekdays').style.display = 'none';

      for (let y = decadeStart; y < decadeStart + 12; y++) {
        const isCurrent = y === year;
        html += `<button class="datepicker-day datepicker-year-item${isCurrent ? ' selected' : ''}" data-year="${y}">${y}年</button>`;
      }
      dpDays.innerHTML = html;
      dpDays.querySelectorAll('.datepicker-year-item').forEach(btn => {
        btn.addEventListener('click', (e) => {
          e.stopPropagation();
          dpCurrentDate = new Date(parseInt(btn.dataset.year), dpCurrentDate.getMonth(), 1);
          dpViewMode = 'month';
          renderDatepicker();
        });
      });
    }
  }

  // ── Header click: cycle view mode ──
  dpMonthYear.addEventListener('click', (e) => {
    e.stopPropagation();
    if (dpViewMode === 'day') dpViewMode = 'month';
    else if (dpViewMode === 'month') dpViewMode = 'year';
    else dpViewMode = 'day';
    renderDatepicker();
  });

  function openDatepicker() {
    dpOpen = true;
    dpViewMode = 'day';
    dpPopup.classList.add('open');
    renderDatepicker();
  }

  function closeDatepicker() {
    dpOpen = false;
    dpPopup.classList.remove('open');
  }

  function toggleDatepicker() {
    if (dpOpen) closeDatepicker();
    else openDatepicker();
  }

  // Click input to open
  dateInput.addEventListener('click', (e) => {
    e.stopPropagation();
    toggleDatepicker();
  });

  // Prev/Next (adapts to view mode)
  function dpNavigate(dir) {
    if (dpViewMode === 'day') {
      dpCurrentDate.setMonth(dpCurrentDate.getMonth() + dir);
    } else if (dpViewMode === 'month') {
      dpCurrentDate.setFullYear(dpCurrentDate.getFullYear() + dir);
    } else if (dpViewMode === 'year') {
      dpCurrentDate.setFullYear(dpCurrentDate.getFullYear() + dir * 12);
    }
    renderDatepicker();
  }

  dpPrev.addEventListener('click', (e) => { e.stopPropagation(); dpNavigate(-1); });
  dpNext.addEventListener('click', (e) => { e.stopPropagation(); dpNavigate(1); });

  // Today button
  dpTodayBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    const now = new Date();
    dpCurrentDate = new Date(now.getFullYear(), now.getMonth(), 1);
    dpSelectedDate = new Date(now);
    dpViewMode = 'day';
    dateInput.value = formatDateInput(now);
    closeDatepicker();
    jumpToDate(formatDateInput(now));
  });

  // Close on outside click
  document.addEventListener('click', (e) => {
    const picker = document.getElementById('timelineDatepicker');
    if (dpOpen && picker && !picker.contains(e.target)) {
      closeDatepicker();
    }
  });

  // ── Filter buttons (multi-select, "全部" toggles all) ──
  function updateFilterUI() {
    filterBtns.forEach(btn => {
      const src = btn.dataset.source;
      if (src === 'all') {
        btn.classList.toggle('active', activeSources.size === 3);
      } else {
        btn.classList.toggle('active', activeSources.has(src));
      }
    });
  }

  filterBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      const src = btn.dataset.source;
      if (src === 'all') {
        // Toggle all ↔ manual only
        if (activeSources.size === 3) {
          activeSources = new Set(['manual']);
        } else {
          activeSources = new Set(['manual', 'room', 'assistant']);
        }
      } else {
        // Toggle individual source
        if (activeSources.has(src)) {
          activeSources.delete(src);
          // Don't allow empty selection; if empty, re-add
          if (activeSources.size === 0) activeSources.add(src);
        } else {
          activeSources.add(src);
        }
      }
      updateFilterUI();
      refreshTimeline(true);
    });
  });

  // ── Drag-to-select across filter options ──
  let isDraggingFilter = false;
  if (filterOptions) {
    filterOptions.addEventListener('pointerdown', (e) => {
      isDraggingFilter = true;
      filterOptions.setPointerCapture(e.pointerId);
    });

    filterOptions.addEventListener('pointermove', (e) => {
      if (!isDraggingFilter) return;
      const el = document.elementFromPoint(e.clientX, e.clientY);
      if (el && el.classList.contains('timeline-filter-btn') && !el.classList.contains('active')) {
        el.click();
      }
    });

    filterOptions.addEventListener('pointerup', () => {
      isDraggingFilter = false;
    });

    filterOptions.addEventListener('pointerleave', () => {
      isDraggingFilter = false;
    });
  }

  // ── Collapsible filter bar ──
  const filterHeader = document.getElementById('timelineFilterHeader');
  const filterOptions = document.getElementById('timelineFilterOptions');

  function toggleFilterBar() {
    const isOpen = filterOptions.classList.contains('open');
    filterOptions.classList.toggle('open');
    filterHeader.classList.toggle('open');
  }

  function closeFilterBar() {
    filterOptions.classList.remove('open');
    filterHeader.classList.remove('open');
  }

  if (filterHeader) {
    filterHeader.addEventListener('click', (e) => {
      e.stopPropagation();
      toggleFilterBar();
    });
  }

  // Close filter bar when clicking outside
  document.addEventListener('click', (e) => {
    const bar = document.getElementById('timelineFilterBar');
    if (bar && !bar.contains(e.target)) {
      closeFilterBar();
    }
  });

  // ── Fetch schedule data from API ──
  async function fetchScheduleEvents() {
    try {
      const resp = await fetch('/api/timeline/schedule');
      const data = await resp.json();
      if (data.success && Array.isArray(data.data)) {
        allScheduleEvents = data.data.map(ev => ({
          ...ev,
          source: 'assistant',
        }));
      }
    } catch (err) {
      console.warn('[timeline] Failed to fetch schedule events:', err);
    }
  }

  // ── Fetch live data from API ──
  async function fetchLiveEvents() {
    try {
      const resp = await fetch('/api/timeline/live-pushes?limit=500');
      const data = await resp.json();
      if (data.success && Array.isArray(data.data)) {
        allLiveEvents = data.data.map(ev => ({
          ...ev,
          source: 'room',
          image: ev.cover_url || null,
          has_danmu: ev.has_danmu || false,
          danmu_status: ev.danmu_status || '',
        }));
      }
    } catch (err) {
      console.warn('[timeline] Failed to fetch live events:', err);
    }
  }

  // ── Date jump button ──
  if (dateJumpBtn) {
    dateJumpBtn.addEventListener('click', () => {
      if (dateInput.value) {
        jumpToDate(dateInput.value);
      }
    });
  }

  // Init: show today's date
  dateInput.value = formatDateInput(new Date());

  // ── Modal ──
  function openModal(event) {
    const badgeClassMap = {
      milestone: 'milestone', tour: 'tour', show: 'show',
      event: 'event', external: 'external', live: 'event',
    };
    const badgeClass = badgeClassMap[event.type] || 'event';

    // Modal: also replace type badge with keyword badge if matched
    const title_ = event.title || '';
    const modalKeywordBadge =
      title_.includes('助演') ? 'show|助演' :
      title_.includes('首演') ? 'milestone|首演' :
      title_.includes('巡演') ? 'tour|巡演' : '';
    const showModalTypeBadge = !modalKeywordBadge;

    const descHtml = event.description.replace(/\n/g, '<br>');

    // Build cover/gallery: if multiple images, show scrollable gallery; else single cover
    let coverHtml = '';
    if (event.image_urls && event.image_urls.length > 1) {
      coverHtml = '<div class="timeline-modal-gallery">';
      event.image_urls.forEach(url => {
        coverHtml += `<img src="${url}" alt="" class="loading" loading="lazy" onload="this.classList.remove('loading')" onerror="this.classList.remove('loading');this.style.display='none'">`;
      });
      coverHtml += '</div>';
    } else {
      // Single cover (from cover_url or first image_urls item or placeholder)
      const coverSrc = event.cover_url || (event.image_urls && event.image_urls[0]) || '';
      coverHtml = coverSrc
        ? `<img class="timeline-modal-img loading" src="${coverSrc}" alt="${event.title}" onload="this.classList.remove('loading')" onerror="this.classList.remove('loading')">`
        : `<div class="timeline-modal-img-placeholder"><i class="fas ${event.icon || 'fa-calendar'}"></i></div>`;
    }

    // Build B站 links
    let biliHtml = '';
    if (event.bilibili_urls && event.bilibili_urls.length > 0) {
      biliHtml = '<div class="timeline-modal-info" style="margin-top:12px;"><i class="fab fa-bilibili"></i> 相关视频：';
      event.bilibili_urls.forEach((url, i) => {
        biliHtml += `<a href="${url}" target="_blank" rel="noopener" style="color:var(--primary);">视频${i + 1}</a>`;
        if (i < event.bilibili_urls.length - 1) biliHtml += ' · ';
      });
      biliHtml += '</div>';
    }

    modalContent.innerHTML = `
      ${coverHtml}
      <div class="timeline-modal-body">
        <div class="timeline-modal-date">${formatDate(event.date)}</div>
        <div class="timeline-modal-title">${event.title}</div>
        ${showModalTypeBadge ? `<span class="timeline-modal-badge ${badgeClass}">${event.typeLabel}</span>` : ''}
        ${modalKeywordBadge ? `<span class="timeline-modal-badge ${modalKeywordBadge.split('|')[0]}" style="margin-left:0;">${modalKeywordBadge.split('|')[1]}</span>` : ''}
        ${event.source === 'room' ? `<span class="timeline-modal-badge danmu ${event.has_danmu ? 'available' : 'missing'}" style="margin-left:0;">${event.has_danmu ? '<i class="fas fa-comment-dots"></i> 有弹幕' : '<i class="fas fa-comment-slash"></i> 无弹幕'}</span>` : ''}
        ${event.has_replay && event.replay_url ? `<a href="/replay/${event.id.replace('live_', '')}" target="_blank" rel="noopener" class="timeline-modal-replay-btn"><i class="fas fa-play"></i> 观看回放</a>` : ''}
        ${event.location ? `<div class="timeline-modal-info"><i class="fas fa-map-marker-alt"></i> ${event.location}</div>` : ''}
        ${event.source_url ? `<div class="timeline-modal-info"><i class="fas fa-external-link-alt"></i> <a href="${event.source_url}" target="_blank" rel="noopener" style="color:var(--primary);">信息来源</a></div>` : ''}
        ${biliHtml}
        <div class="timeline-modal-desc">${descHtml}</div>
      </div>
    `;
    overlay.classList.add('open');
    document.body.style.overflow = 'hidden';
  }

  function closeModal() {
    overlay.classList.remove('open');
    document.body.style.overflow = '';
  }

  overlay.addEventListener('click', (e) => {
    if (e.target === overlay) closeModal();
  });

  modalClose.addEventListener('click', closeModal);

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeModal();
  });

  // ── Drag to scroll ──
  let isDragging = false;
  let startX = 0;
  let startLeft = 0;
  let dragDistance = 0;
  let velocity = 0;
  let lastX = 0;
  let lastTime = 0;
  let smoothVelocity = 0;
  let animFrame = null;

  function getTrackLeft() {
    return parseFloat(track.style.left) || 0;
  }

  function setTrackLeft(val) {
    track.style.left = val + 'px';
    // Keep transform-origin locked to wrapper center
    updateTransformOrigin();
  }

  function updateTransformOrigin() {
    const wrapperRect = wrapper.getBoundingClientRect();
    const trackRect = track.getBoundingClientRect();
    const originX = wrapperRect.left + wrapperRect.width / 2 - trackRect.left;
    trackInner.style.transformOrigin = `${originX}px center`;
  }

  function startDrag(clientX) {
    isDragging = true;
    dragDistance = 0;
    startX = clientX;
    lastX = clientX;
    lastTime = performance.now();
    startLeft = getTrackLeft();
    wrapper.classList.add('dragging');
    cancelAnimationFrame(animFrame);
  }

  function moveDrag(clientX) {
    if (!isDragging) return;
    const dx = clientX - startX;
    dragDistance = Math.abs(dx);
    setTrackLeft(startLeft + dx);

    const now = performance.now();
    const dt = now - lastTime;
    if (dt > 0) {
      const instantV = (clientX - lastX) / dt;
      // Exponential moving average for smooth velocity
      smoothVelocity = smoothVelocity ? smoothVelocity * 0.7 + instantV * 0.3 : instantV;
      smoothVelocity = Math.max(-1.5, Math.min(1.5, smoothVelocity));
    }
    lastX = clientX;
    lastTime = now;
    hint.classList.add('dim');
  }

  function endDrag() {
    if (!isDragging) return;
    isDragging = false;
    wrapper.classList.remove('dragging');
    hint.classList.add('dim');

    if (dragDistance < 5) {
      syncDateInputWithCenter();
      return;
    }

    const inertiaV = smoothVelocity * 400;
    if (Math.abs(inertiaV) > 8) {
      const current = getTrackLeft();
      const delta = inertiaV;
      const duration = 400;
      const startVal = current;
      const startTime = performance.now();

      function inertiaAnimate(time) {
        const elapsed = time - startTime;
        const progress = Math.min(elapsed / duration, 1);
        const eased = 1 - Math.pow(1 - progress, 3);
        setTrackLeft(startVal + delta * eased);
        if (progress < 1) {
          animFrame = requestAnimationFrame(inertiaAnimate);
        } else {
          requestAnimationFrame(() => syncDateInputWithCenter());
        }
      }
      animFrame = requestAnimationFrame(inertiaAnimate);
    } else {
      syncDateInputWithCenter();
    }
    velocity = 0;
    smoothVelocity = 0;
  }

  // Mouse events
  wrapper.addEventListener('mousedown', (e) => {
    hint.classList.add('dim');
    if (e.button !== 0) return;
    startDrag(e.clientX);
  });

  document.addEventListener('mousemove', (e) => {
    moveDrag(e.clientX);
  });

  document.addEventListener('mouseup', () => {
    endDrag();
  });

  // Touch events (single-finger drag)
  wrapper.addEventListener('touchstart', (e) => {
    if (e.touches.length !== 1) return;
    const touch = e.touches[0];
    startDrag(touch.clientX);
  }, { passive: true });

  wrapper.addEventListener('touchmove', (e) => {
    if (e.touches.length !== 1) return;
    const touch = e.touches[0];
    moveDrag(touch.clientX);
  }, { passive: true });

  wrapper.addEventListener('touchend', () => {
    endDrag();
  }, { passive: true });

  // ── Find which event is closest to the viewport center ──
  function getCenteredEventIndex() {
    const events = trackInner.querySelectorAll('.timeline-event');
    if (events.length === 0) return 0;
    const wrapperRect = wrapper.getBoundingClientRect();
    const cx = wrapperRect.left + wrapperRect.width / 2;
    let best = 0;
    let bestDist = Infinity;
    events.forEach((el, i) => {
      const r = el.getBoundingClientRect();
      const dist = Math.abs(r.left + r.width / 2 - cx);
      if (dist < bestDist) { bestDist = dist; best = i; }
    });
    return best;
  }

  // ── Sync date input to reflect the currently centered date ──
  function syncDateInputWithCenter() {
    if (!dateInput) return;
    const idx = getCenteredEventIndex();
    const events = trackInner.querySelectorAll('.timeline-event');
    if (idx >= 0 && idx < events.length) {
      dateInput.value = events[idx].dataset.date;
    }
  }

  // ── Center a specific event by index ──
  function centerOnEvent(index) {
    const events = trackInner.querySelectorAll('.timeline-event');
    if (index < 0 || index >= events.length) return;
    const target = events[index];
    // Calculate position from known column widths to avoid transform-scale interference
    const wrapperW = wrapper.getBoundingClientRect().width;
    const colW = target.offsetWidth;        // event column width (unscaled)
    const colMargin = parseInt(getComputedStyle(target).marginLeft) || 12;
    const step = colW + colMargin * 2;       // full step between column centers
    // Event i's natural center inside trackInner = 50vw padding + i*step + colW/2
    // We want this center to align with wrapper center:
    //   trackLeft + 50vw + index*step + colW/2 = wrapperW / 2
    const vw50 = wrapperW * 0.5;
    const targetLeft = wrapperW / 2 - vw50 - index * step - colW / 2;
    track.style.left = targetLeft + 'px';
    updateTransformOrigin();
    if (dateInput) dateInput.value = target.dataset.date;
  }

  // ── Zoom (no re-center — transform-origin keeps center stable) ──
  function applyScale(newScale) {
    scale = Math.max(MIN_SCALE, Math.min(MAX_SCALE, newScale));
    trackInner.style.transform = `scale(${scale})`;
    wrapper.style.minHeight = '100vh';
  }

  zoomIn.addEventListener('click', () => applyScale(scale + 0.15));
  zoomOut.addEventListener('click', () => applyScale(scale - 0.15));

  wrapper.addEventListener('wheel', (e) => {
    hint.classList.add('dim');
    if (e.ctrlKey || e.metaKey) {
      e.preventDefault();
      applyScale(scale - e.deltaY * 0.002);
    }
  }, { passive: false });

  // ── Pinch-to-zoom on mobile ──
  let lastPinchDist = 0;
  wrapper.addEventListener('touchstart', (e) => {
    if (e.touches.length === 2) {
      const dx = e.touches[0].clientX - e.touches[1].clientX;
      const dy = e.touches[0].clientY - e.touches[1].clientY;
      lastPinchDist = Math.hypot(dx, dy);
      hint.classList.add('dim');
    }
  }, { passive: true });

  wrapper.addEventListener('touchmove', (e) => {
    if (e.touches.length === 2) {
      e.preventDefault();
      const dx = e.touches[0].clientX - e.touches[1].clientX;
      const dy = e.touches[0].clientY - e.touches[1].clientY;
      const dist = Math.hypot(dx, dy);
      if (lastPinchDist > 0) {
        const delta = dist - lastPinchDist;
        applyScale(scale + delta * 0.005);
      }
      lastPinchDist = dist;
    }
  }, { passive: false });

  // ── Initialize: wait for all data, then render once ──
  const loadingEl = document.getElementById('timelineLoading');
  // Sync initial filter UI state
  updateFilterUI();
  // Fetch all data sources in parallel
  Promise.all([
    fetchLiveEvents(),
    fetchScheduleEvents(),
  ]).then(() => {
    refreshTimeline();
    applyScale(1);
    if (loadingEl) loadingEl.classList.add('hidden');
  });

  setTimeout(() => {
    hint.classList.add('dim');
  }, 8000);
});
