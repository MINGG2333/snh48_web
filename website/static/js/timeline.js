/**
 * SNH48 演艺信息站 - 时光轴 Timeline
 *
 * 功能：水平拖拽滑动时间轴 + 点击弹出详情弹窗
 * 数据：硬编码陈嘉仪历史事件与未来行程
 */

// ═══════════════════════════════════════════════════════════════════════════
//  Event Data
// ═══════════════════════════════════════════════════════════════════════════

const TIMELINE_EVENTS = [
  // ── 历史事件 ──
  {
    id: 'join',
    date: '2025-09-23',
    title: '加入 SNH48 二十三期生',
    type: 'milestone',
    typeLabel: '里程碑',
    description: `2025年9月23日，陈嘉仪正式加入 SNH48 二十三期生，时年20岁。\n\n作为 SNH48 新生代成员，陈嘉仪以独特的气质和才艺获得了关注。官方资料显示，她的特长是"反射弧特长"（官方认证反应慢），爱好包括看国漫、唱歌跳舞、舞团练习室视频和玩游戏。\n\n她的 Catch Phrase 是："陈可以是加减乘除的乘，嘉可以是加减乘除的加，仪可以是一二三四的一。"粉丝亲切地称她为"×＋1"或"甲鱼"。`,
    image: null,
    icon: 'fa-star',
    color: '#fbbf24',
  },
  {
    id: 'debut',
    date: '2025-10-05',
    title: '星梦剧院首演《B·RISE 梦之门》',
    type: 'milestone',
    typeLabel: '里程碑 · 公演',
    description: `2025年10月5日 & 10月6日 19:00\n📍 SNH48 星梦剧院\n\nSNH48 23期新生公演《B·RISE 梦之门》在星梦剧院盛大首演！这是陈嘉仪登上 SNH48 舞台的出道首秀。\n\n首演中，陈嘉仪与同期23期生李婷在公演中上演了"小学鸡拌嘴名场面"，活泼可爱的互动给粉丝们留下了深刻印象。`,
    image: null,
    icon: 'fa-theater-masks',
    color: '#c084fc',
  },
  {
    id: 'promotion',
    date: '2026-02-08',
    title: '升格 TEAM HII 正式成员',
    type: 'milestone',
    typeLabel: '里程碑',
    description: `2026年2月8日，陈嘉仪公演考核通过，正式升格为 SNH48 TEAM HII 正式成员！\n\n同期升格的还有刘思雨。\n\n"What time is it ! combat time ! We are the only one ! Team HII !"\n\n愿她们永远怀抱"闪着光的信念"，守护"发芽的梦想"，在 TEAM HII 的篇章里，亲手摘取属于自己的梦想果实。`,
    image: null,
    icon: 'fa-crown',
    color: '#fbbf24',
  },

  // ── 分隔：历史 / 未来 ──
  { _divider: 'past', label: '历史轨迹', icon: 'fa-history' },
  { _divider: 'future', label: '未来行程', icon: 'fa-calendar-alt' },

  // ── 未来行程 ──
  {
    id: 'work-exhibition',
    date: '2026-06-04',
    title: '作品展演暨青春宣言',
    type: 'event',
    typeLabel: '行程',
    description: `📅 2026年6月4日（星期四）\n🕐 时间待定\n\n作品展演暨青春宣言活动。这是陈嘉仪升格后的一项重要演出活动，将展示她的个人作品和才艺成果。`,
    image: null,
    icon: 'fa-microphone-alt',
    color: '#60a5fa',
  },
  {
    id: 'beijing-tour',
    date: '2026-06-12',
    title: '北京巡演（11人企划）',
    type: 'tour',
    typeLabel: '巡演',
    description: `📅 2026年6月12日（星期五）\n🕐 时间待定\n📍 北京\n\n11人企划巡演——北京站！陈嘉仪将随 TEAM HII 成员一同踏上北京巡演之旅，为首都的粉丝带来精彩演出。`,
    image: null,
    icon: 'fa-bus',
    color: '#4ade80',
  },
  {
    id: 'hertz-show',
    date: '2026-06-14',
    title: '赫兹2.0公演',
    type: 'show',
    typeLabel: '公演',
    description: `📅 2026年6月14日（星期日）\n🕐 时间待定\n\n赫兹2.0公演！SNH48 TEAM HII 将在星梦剧院呈现全新版本的赫兹公演，为观众带来视听盛宴。`,
    image: null,
    icon: 'fa-music',
    color: '#c084fc',
  },
  {
    id: 'miluo-external',
    date: '2026-06-19',
    title: '湖南汨罗外务',
    type: 'external',
    typeLabel: '外务',
    description: `📅 2026年6月19日（星期五）\n🕐 时间待定\n📍 湖南汨罗\n\n陈嘉仪将赴湖南汨罗参加外务活动，这是她升格后的首次外务演出，期待她在舞台上的精彩表现！`,
    image: null,
    icon: 'fa-plane',
    color: '#fb923c',
  },
  {
    id: 'guangzhou-tour',
    date: '2026-06-28',
    title: '广州巡演',
    type: 'tour',
    typeLabel: '巡演',
    description: `📅 2026年6月28日（星期日）\n🕐 时间待定\n📍 广州\n\n广州巡演！作为巡演系列的最后一站，陈嘉仪将在广州带来精彩的舞台表演，与粉丝们近距离互动。`,
    image: null,
    icon: 'fa-bus',
    color: '#4ade80',
  },
];

// ═══════════════════════════════════════════════════════════════════════════
//  Timeline Rendering
// ═══════════════════════════════════════════════════════════════════════════

document.addEventListener('DOMContentLoaded', () => {
  const track = document.getElementById('timelineTrack');
  const wrapper = document.getElementById('timelineWrapper');
  const overlay = document.getElementById('timelineModalOverlay');
  const modalContent = document.getElementById('timelineModalContent');
  const modalClose = document.getElementById('timelineModalClose');
  const hint = document.getElementById('timelineHint');
  const zoomIn = document.getElementById('zoomIn');
  const zoomOut = document.getElementById('zoomOut');

  let scale = 1;
  const MIN_SCALE = 0.5;
  const MAX_SCALE = 1.8;

  // ── Render nodes ──
  function renderTimeline() {
    track.innerHTML = '';
    TIMELINE_EVENTS.forEach((event, index) => {
      if (event._divider) {
        // Section divider
        const div = document.createElement('div');
        div.className = 'timeline-section-label';
        div.innerHTML = `
          <div class="section-icon"><i class="fas ${event.icon}"></i></div>
          <div class="section-text">${event.label}</div>
        `;
        track.appendChild(div);
      } else {
        // Event node
        const node = document.createElement('div');
        node.className = 'timeline-node';
        node.dataset.index = index;

        const badgeClassMap = {
          milestone: 'milestone',
          tour: 'tour',
          show: 'show',
          event: 'event',
          external: 'external',
        };
        const badgeClass = badgeClassMap[event.type] || 'event';

        const imgHtml = event.image
          ? `<img class="timeline-img" src="${event.image}" alt="${event.title}" loading="lazy">`
          : `<div class="timeline-img-placeholder"><i class="fas ${event.icon || 'fa-calendar'}"></i></div>`;

        node.innerHTML = `
          <div class="timeline-card">
            ${imgHtml}
            <div class="timeline-info">
              <div class="timeline-date">${formatDate(event.date)}</div>
              <div class="timeline-title">${event.title}</div>
              <span class="timeline-badge ${badgeClass}">${event.typeLabel}</span>
            </div>
          </div>
        `;

        node.addEventListener('click', () => openModal(event));
        node.addEventListener('touchend', (e) => {
          // Only open on tap, not after drag
          if (!wrapper.classList.contains('dragging')) {
            openModal(event);
          }
        });

        track.appendChild(node);
      }
    });
  }

  // ── Format date ──
  function formatDate(dateStr) {
    const d = new Date(dateStr);
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${y}.${m}.${day}`;
  }

  // ── Center on a specific event ──
  function centerOn(index) {
    const nodes = track.querySelectorAll('.timeline-node');
    if (index >= 0 && index < nodes.length) {
      const node = nodes[index];
      const wrapperRect = wrapper.getBoundingClientRect();
      const nodeRect = node.getBoundingClientRect();
      const offset = wrapperRect.width / 2 - nodeRect.width / 2;
      const currentLeft = parseFloat(track.style.left) || 0;
      const targetLeft = currentLeft - (nodeRect.left - wrapperRect.left - offset);
      track.style.left = targetLeft + 'px';
    }
  }

  // ── Center on the divider between past and future ──
  function centerOnDivider() {
    const dividers = track.querySelectorAll('.timeline-section-label');
    if (dividers.length > 1) {
      // Center on the second divider (未来行程)
      const div = dividers[1];
      const wrapperRect = wrapper.getBoundingClientRect();
      const divRect = div.getBoundingClientRect();
      const offset = wrapperRect.width / 2 - divRect.width / 2;
      const currentLeft = parseFloat(track.style.left) || 0;
      const targetLeft = currentLeft - (divRect.left - wrapperRect.left - offset);
      track.style.left = targetLeft + 'px';
    }
  }

  // ── Modal ──
  function openModal(event) {
    const badgeClassMap = {
      milestone: 'milestone',
      tour: 'tour',
      show: 'show',
      event: 'event',
      external: 'external',
    };
    const badgeClass = badgeClassMap[event.type] || 'event';

    const imgHtml = event.image
      ? `<img class="timeline-modal-img" src="${event.image}" alt="${event.title}">`
      : `<div class="timeline-modal-img-placeholder"><i class="fas ${event.icon || 'fa-calendar'}"></i></div>`;

    // Escape newlines in description to <br>
    const descHtml = event.description.replace(/\n/g, '<br>');

    modalContent.innerHTML = `
      ${imgHtml}
      <div class="timeline-modal-body">
        <div class="timeline-modal-date">${formatDate(event.date)}</div>
        <div class="timeline-modal-title">${event.title}</div>
        <span class="timeline-modal-badge ${badgeClass}">${event.typeLabel}</span>
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
  let animFrame = null;

  function getTrackLeft() {
    return parseFloat(track.style.left) || 0;
  }

  function setTrackLeft(val) {
    track.style.left = val + 'px';
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

    // Track velocity for inertia
    const now = performance.now();
    const dt = now - lastTime;
    if (dt > 0) {
      velocity = (clientX - lastX) / dt;
      // Clamp velocity
      velocity = Math.max(-0.5, Math.min(0.5, velocity));
    }
    lastX = clientX;
    lastTime = now;

    // Hide hint on interaction
    hint.classList.add('dim');
  }

  function endDrag() {
    if (!isDragging) return;
    isDragging = false;
    wrapper.classList.remove('dragging');

    // If barely dragged, treat as click — don't apply inertia
    if (dragDistance < 5) return;

    // Apply inertia
    const inertiaV = velocity * 800; // scale factor
    if (Math.abs(inertiaV) > 5) {
      let current = getTrackLeft();
      const target = current + inertiaV;

      // Animate to target with decay
      const duration = 600;
      const startVal = current;
      const delta = inertiaV;
      const startTime = performance.now();

      function inertiaAnimate(time) {
        const elapsed = time - startTime;
        const progress = Math.min(elapsed / duration, 1);
        // Ease-out cubic
        const eased = 1 - Math.pow(1 - progress, 3);
        setTrackLeft(startVal + delta * eased);

        if (progress < 1) {
          animFrame = requestAnimationFrame(inertiaAnimate);
        }
      }
      animFrame = requestAnimationFrame(inertiaAnimate);
    }

    velocity = 0;
  }

  // Mouse events
  wrapper.addEventListener('mousedown', (e) => {
    if (e.button !== 0) return;
    startDrag(e.clientX);
  });

  document.addEventListener('mousemove', (e) => {
    moveDrag(e.clientX);
  });

  document.addEventListener('mouseup', () => {
    endDrag();
  });

  // Touch events
  wrapper.addEventListener('touchstart', (e) => {
    const touch = e.touches[0];
    startDrag(touch.clientX);
  }, { passive: true });

  wrapper.addEventListener('touchmove', (e) => {
    const touch = e.touches[0];
    moveDrag(touch.clientX);
  }, { passive: true });

  wrapper.addEventListener('touchend', (e) => {
    endDrag();
  }, { passive: true });

  // ── Zoom ──
  function applyScale(newScale) {
    scale = Math.max(MIN_SCALE, Math.min(MAX_SCALE, newScale));
    // Scale the track's transform but keep node sizes fixed
    track.style.transform = `scale(${scale})`;
    // Adjust track height to avoid cutoff
    if (scale < 1) {
      wrapper.style.minHeight = `${100 / scale}vh`;
    } else {
      wrapper.style.minHeight = '100vh';
    }
  }

  zoomIn.addEventListener('click', () => applyScale(scale + 0.15));
  zoomOut.addEventListener('click', () => applyScale(scale - 0.15));

  // Mouse wheel zoom
  wrapper.addEventListener('wheel', (e) => {
    if (e.ctrlKey || e.metaKey) {
      e.preventDefault();
      applyScale(scale - e.deltaY * 0.002);
    }
  }, { passive: false });

  // ── Initialize ──
  renderTimeline();

  // Center on the divider after render
  requestAnimationFrame(() => {
    centerOnDivider();
  });

  // Show hint for a while, then fade
  setTimeout(() => {
    hint.classList.add('dim');
  }, 8000);
});
