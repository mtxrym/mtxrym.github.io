'use strict';

const FEED_PATH = './blog.json';
const STATUS_PATH = './data/status.json';
const FAVORITES_KEY = 'ai-coding-favorites';
const PREFS_KEY = 'ai-coding-prefs';
const NEW_ITEM_HOURS = 24;
const DEFAULT_STALE_HOURS = 96;

// 旧版数据没有 status.json 时的兜底名称；新版以 status.json 里的 label 为准
const FALLBACK_SOURCE_LABELS = {
  arxiv_cs_se: 'arXiv · cs.SE',
  arxiv_cs_cl: 'arXiv · cs.CL',
  arxiv_cs_ai: 'arXiv · cs.AI',
  arxiv_cs_lg: 'arXiv · cs.LG',
  hf_daily_papers: 'HF Daily Papers',
  hf_datasets_code: 'HF 数据集 · code',
  hf_datasets_swe: 'HF 数据集 · SWE'
};
const CATEGORY_LABELS = { papers: '论文', datasets: '数据集' };
const SCORE_PARTS = [
  ['relevance', '相关性'],
  ['popularity', '热度'],
  ['freshness', '新鲜度'],
  ['impact', '影响力']
];

const ICONS = {
  star: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3.5l2.6 5.3 5.9.9-4.3 4.1 1 5.8L12 16.9l-5.2 2.7 1-5.8-4.3-4.1 5.9-.9z" /></svg>',
  external: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 17L17 7M9 7h8v8" /></svg>',
  up: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5l7 8h-4.5v6h-5v-6H5z" /></svg>',
  heart: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 20s-7-4.4-7-10a4 4 0 0 1 7-2.6A4 4 0 0 1 19 10c0 5.6-7 10-7 10z" /></svg>',
  code: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 8l-4 4 4 4M15 8l4 4-4 4" /></svg>',
  chevron: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 9l6 6 6-6" /></svg>'
};

// ---------------------------------------------------------------------------
// 工具
// ---------------------------------------------------------------------------

const storage = {
  get(key, fallback) {
    try {
      const raw = localStorage.getItem(key);
      return raw ? JSON.parse(raw) : fallback;
    } catch (e) {
      return fallback;
    }
  },
  set(key, value) {
    try {
      localStorage.setItem(key, JSON.stringify(value));
    } catch (e) { /* 隐私模式等场景下忽略 */ }
  }
};

const rtf = new Intl.RelativeTimeFormat('zh-CN', { numeric: 'auto' });

function parseDate(raw) {
  if (!raw) return null;
  const date = new Date(raw);
  return Number.isNaN(date.getTime()) ? null : date;
}

function formatDate(date) {
  const sameYear = date.getFullYear() === new Date().getFullYear();
  return date.toLocaleDateString('zh-CN', sameYear
    ? { month: 'long', day: 'numeric' }
    : { year: 'numeric', month: 'long', day: 'numeric' });
}

function formatDateTime(date) {
  return date.toLocaleString('zh-CN', { hour12: false });
}

function relativeTime(date) {
  const hours = (date.getTime() - Date.now()) / 36e5;
  if (Math.abs(hours) < 1) return '刚刚';
  if (Math.abs(hours) < 24) return rtf.format(Math.round(hours), 'hour');
  const days = Math.round(hours / 24);
  if (Math.abs(days) < 30) return rtf.format(days, 'day');
  return formatDate(date);
}

// 论文日期只精确到天，按日历天显示：今天 / 昨天 / N 天前
function relativeDay(date) {
  const startOfDay = (d) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  const days = Math.round((startOfDay(new Date()) - startOfDay(date)) / 864e5);
  if (days <= 0) return '今天';
  if (days < 30) return rtf.format(-days, 'day');
  return formatDate(date);
}

function compactNumber(value) {
  if (value >= 10000) return `${(value / 10000).toFixed(1).replace(/\.0$/, '')}万`;
  if (value >= 1000) return `${(value / 1000).toFixed(1).replace(/\.0$/, '')}k`;
  return String(value);
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function iconLink(href, icon, label, className = 'meta-link') {
  const link = el('a', className);
  link.href = href;
  link.target = '_blank';
  link.rel = 'noopener noreferrer';
  link.innerHTML = icon;
  link.append(label);
  return link;
}

// ---------------------------------------------------------------------------
// 状态
// ---------------------------------------------------------------------------

const $ = (id) => document.getElementById(id);
const elements = {
  feed: $('feed'),
  sourceChips: $('source-chips'),
  categoryTabs: $('category-tabs'),
  kpiTotal: $('kpi-total'),
  kpiSources: $('kpi-sources'),
  kpiAvg: $('kpi-avg'),
  kpiUpdated: $('kpi-updated'),
  policyNote: $('policy-note'),
  policyList: $('policy-list'),
  sourcesBody: $('sources-body'),
  sourcesSummary: $('sources-summary'),
  statusPill: $('status-pill'),
  resultNote: $('result-note'),
  searchInput: $('search-input'),
  sortSelect: $('sort-select'),
  favoritesToggle: $('favorites-toggle'),
  favoriteCount: $('favorite-count'),
  compactToggle: $('compact-toggle'),
  clearFilters: $('clear-filters'),
  themeToggle: $('theme-toggle')
};

const prefs = storage.get(PREFS_KEY, {});
const state = {
  items: [],
  status: null,
  sourceLabels: { ...FALLBACK_SOURCE_LABELS },
  absoluteScores: false,
  maxScore: 0,
  source: 'all',
  category: 'all',
  favorites: new Set(storage.get(FAVORITES_KEY, [])),
  expanded: new Set(),
  showFavoritesOnly: false,
  compactView: Boolean(prefs.compact)
};

function savePrefs(patch) {
  Object.assign(prefs, patch);
  storage.set(PREFS_KEY, prefs);
}

const sourceLabel = (id) => state.sourceLabels[id] || id;
const categoryLabel = (id) => CATEGORY_LABELS[id] || id;

// ---------------------------------------------------------------------------
// 数据归一化（兼容旧版 blog.json）
// ---------------------------------------------------------------------------

function parseLegacyScore(text) {
  const match = (text || '').match(/score=([\d.]+)/);
  return match ? Number(match[1]) : 0;
}

function normalize(raw) {
  const sub = raw.sub_title || '';
  const sourceIds = Array.isArray(raw.source_ids) && raw.source_ids.length
    ? raw.source_ids
    : [raw.source_id || (sub.match(/source=([\w-]+)/) || [])[1] || raw.source_host || 'unknown'];
  const firstSeen = parseDate(raw.first_seen_at);
  return {
    // 与旧版一致的 id 规则，保证已有收藏不丢失
    id: raw.external_url || raw.url_title || raw.title,
    title: raw.title || '（无标题）',
    category: raw.category || (sub.split('·')[0] || '').trim() || 'papers',
    sources: sourceIds,
    score: typeof raw.score === 'number' ? raw.score : parseLegacyScore(sub),
    scores: raw.scores || null,
    summary: raw.summary || '',
    authors: Array.isArray(raw.authors) ? raw.authors : [],
    authorCount: raw.author_count || (raw.authors || []).length,
    keywords: Array.isArray(raw.keywords) ? raw.keywords : [],
    upvotes: raw.upvotes || 0,
    likes: raw.likes || 0,
    githubUrl: raw.github_url || '',
    githubStars: raw.github_stars || 0,
    hfUrl: raw.hf_url || '',
    publishedDate: parseDate(raw.published_at),
    firstSeen,
    isNew: Boolean(firstSeen && Date.now() - firstSeen.getTime() < NEW_ITEM_HOURS * 36e5),
    target: raw.external_url || `./blog/${raw.url_title || ''}/`
  };
}

// 同一篇论文可能出现在多个来源里，合并为一条并保留全部来源
function dedupe(items) {
  const byId = new Map();
  items.forEach((item) => {
    const existing = byId.get(item.id);
    if (!existing) {
      byId.set(item.id, item);
      return;
    }
    item.sources.forEach((s) => { if (!existing.sources.includes(s)) existing.sources.push(s); });
    existing.score = Math.max(existing.score, item.score);
  });
  return [...byId.values()];
}

function popularityOf(item) {
  return item.scores ? item.scores.popularity : item.upvotes + item.likes + item.githubStars;
}

function searchText(item) {
  return [item.title, item.summary, item.authors.join(' '), item.keywords.join(' '), item.sources.map(sourceLabel).join(' ')]
    .join(' ')
    .toLowerCase();
}

// ---------------------------------------------------------------------------
// 渲染：概览 / 数据源
// ---------------------------------------------------------------------------

function setStatus(stateName, label, detail) {
  elements.statusPill.dataset.state = stateName;
  elements.statusPill.lastElementChild.textContent = label;
  elements.statusPill.title = detail || '';
}

function renderOverview(meta) {
  const items = state.items;
  const status = state.status;
  const policy = status?.policy || {};
  const staleHours = policy.stale_after_hours || DEFAULT_STALE_HOURS;

  const newest = items.reduce((acc, item) => {
    const date = item.firstSeen || item.publishedDate;
    return date && (!acc || date > acc) ? date : acc;
  }, null);
  const updatedAt = parseDate(status?.generated_at) || meta.lastModified;
  const avg = items.length ? items.reduce((sum, item) => sum + item.score, 0) / items.length : 0;

  elements.kpiTotal.textContent = String(items.length);
  elements.kpiAvg.textContent = items.length ? avg.toFixed(1) : '–';
  elements.kpiUpdated.textContent = updatedAt ? relativeTime(updatedAt) : '–';
  if (updatedAt) elements.kpiUpdated.title = formatDateTime(updatedAt);

  const totals = status?.totals;
  if (totals) {
    elements.kpiSources.textContent = `${totals.sources_ok}/${totals.sources_total}`;
  } else {
    elements.kpiSources.textContent = String(new Set(items.flatMap((i) => i.sources)).size);
  }

  const ageHours = newest ? (Date.now() - newest.getTime()) / 36e5 : Infinity;
  if (totals && totals.sources_ok === 0) {
    setStatus('error', '抓取失败', '所有数据源本次都抓取失败');
  } else if (ageHours > staleHours) {
    setStatus('warn', '更新滞后', `超过 ${staleHours} 小时没有新条目`);
  } else if (totals && totals.sources_ok < totals.sources_total) {
    setStatus('warn', '部分异常', `${totals.sources_total - totals.sources_ok} 个数据源抓取失败`);
  } else {
    setStatus('ok', '数据正常', newest ? `最新条目收录于 ${formatDateTime(newest)}` : '');
  }

  const noteParts = [];
  if (policy.schedule?.description) noteParts.push(policy.schedule.description);
  if (policy.window_days) noteParts.push(`展示最近 ${policy.window_days} 天`);
  if (policy.min_relevance !== undefined) noteParts.push(`相关性 ≥ ${policy.min_relevance}`);
  elements.policyNote.textContent = noteParts.length
    ? `更新策略：${noteParts.join(' · ')}`
    : '数据由 GitHub Actions 定时更新';
}

function renderSources() {
  const status = state.status;
  if (!status) {
    elements.sourcesBody.innerHTML = '<tr><td colspan="4" class="muted">暂无数据源状态（需要新版数据生成脚本）</td></tr>';
    elements.policyList.innerHTML = '';
    return;
  }

  const policy = status.policy || {};
  const weights = policy.weights || {};
  const rows = [
    ['抓取频率', policy.schedule?.description || policy.schedule?.cron || '–'],
    ['展示窗口', policy.window_days ? `最近 ${policy.window_days} 天首次收录` : '–'],
    ['展示上限', policy.max_items ? `${policy.max_items} 条（数据集最多 ${policy.max_datasets} 条）` : '–'],
    ['相关性门槛', policy.min_relevance !== undefined ? `≥ ${policy.min_relevance} / 100` : '–'],
    ['历史保留', policy.retention_days ? `${policy.retention_days} 天（用于去重）` : '–'],
    ['滞后判定', policy.stale_after_hours ? `${policy.stale_after_hours} 小时无新条目` : '–'],
    ['打分权重', SCORE_PARTS.map(([k, label]) => `${label} ${Math.round((weights[k] || 0) * 100)}%`).join(' · ')]
  ];
  elements.policyList.innerHTML = '';
  rows.forEach(([term, desc]) => {
    const row = el('div');
    row.append(el('dt', '', term), el('dd', '', desc));
    elements.policyList.appendChild(row);
  });

  elements.sourcesBody.innerHTML = '';
  (status.sources || []).forEach((source) => {
    const tr = document.createElement('tr');
    const name = el('td');
    name.append(el('span', 'source-name', source.label || source.id), el('span', 'source-cat', categoryLabel(source.category)));
    const stateCell = el('td');
    const badge = el('span', `state-badge ${source.ok ? 'ok' : 'fail'}`, source.ok ? '正常' : '失败');
    if (source.error) badge.title = source.error;
    stateCell.appendChild(badge);
    tr.append(name, stateCell, el('td', 'num', source.ok ? String(source.fetched) : '–'), el('td', 'num', source.ok ? String(source.relevant) : '–'));
    elements.sourcesBody.appendChild(tr);
  });

  const totals = status.totals || {};
  elements.sourcesSummary.textContent = `${totals.sources_ok}/${totals.sources_total} 正常 · 历史库 ${totals.archive} 条`;
}

// ---------------------------------------------------------------------------
// 渲染：筛选控件
// ---------------------------------------------------------------------------

function renderCategoryTabs() {
  const counts = { all: state.items.length };
  state.items.forEach((item) => { counts[item.category] = (counts[item.category] || 0) + 1; });
  const order = (c) => { const i = Object.keys(CATEGORY_LABELS).indexOf(c); return i === -1 ? 99 : i; };
  const categories = ['all', ...Object.keys(counts).filter((c) => c !== 'all').sort((a, b) => order(a) - order(b) || a.localeCompare(b))];
  if (!categories.includes(state.category)) state.category = 'all';

  elements.categoryTabs.innerHTML = '';
  elements.categoryTabs.hidden = categories.length <= 2;
  categories.forEach((category) => {
    const button = el('button', '', category === 'all' ? '全部' : categoryLabel(category));
    button.type = 'button';
    button.dataset.focusKey = `category:${category}`;
    button.setAttribute('aria-pressed', String(state.category === category));
    button.addEventListener('click', () => {
      state.category = category;
      render();
    });
    elements.categoryTabs.appendChild(button);
  });
}

function renderSourceChips() {
  const counts = {};
  state.items.forEach((item) => item.sources.forEach((s) => { counts[s] = (counts[s] || 0) + 1; }));
  const entries = [['all', state.items.length], ...Object.entries(counts).sort((a, b) => b[1] - a[1])];

  elements.sourceChips.innerHTML = '';
  entries.forEach(([source, count]) => {
    const chip = el('button', 'chip', source === 'all' ? '全部来源' : sourceLabel(source));
    chip.type = 'button';
    chip.dataset.focusKey = `source:${source}`;
    chip.setAttribute('aria-pressed', String(state.source === source));
    chip.appendChild(el('span', 'count', String(count)));
    chip.addEventListener('click', () => {
      state.source = source;
      render();
    });
    elements.sourceChips.appendChild(chip);
  });
}

// ---------------------------------------------------------------------------
// 渲染：列表
// ---------------------------------------------------------------------------

function hasActiveFilters() {
  return Boolean(elements.searchInput.value.trim())
    || state.source !== 'all'
    || state.category !== 'all'
    || state.showFavoritesOnly;
}

function getVisibleItems() {
  const keyword = elements.searchInput.value.trim().toLowerCase();
  const sortBy = elements.sortSelect.value;

  const visible = state.items.filter((item) => (!keyword || searchText(item).includes(keyword))
    && (state.source === 'all' || item.sources.includes(state.source))
    && (state.category === 'all' || item.category === state.category)
    && (!state.showFavoritesOnly || state.favorites.has(item.id)));

  const byDate = (item) => (item.publishedDate || item.firstSeen)?.getTime() || 0;
  visible.sort((a, b) => {
    if (sortBy === 'date_desc') return byDate(b) - byDate(a) || b.score - a.score;
    if (sortBy === 'popularity_desc') return popularityOf(b) - popularityOf(a) || b.score - a.score;
    return b.score - a.score;
  });
  return visible;
}

function toggleFavorite(id) {
  if (state.favorites.has(id)) state.favorites.delete(id);
  else state.favorites.add(id);
  storage.set(FAVORITES_KEY, [...state.favorites]);
  render();
}

function toggleExpanded(id) {
  if (state.expanded.has(id)) state.expanded.delete(id);
  else state.expanded.add(id);
  render();
}

function scoreWidth(score) {
  const ratio = state.absoluteScores ? score / 100 : score / (state.maxScore || 1);
  return `${Math.max(4, Math.min(100, ratio * 100))}%`;
}

function createScore(item) {
  const wrap = el('div', 'score');
  wrap.tabIndex = 0;
  wrap.setAttribute('aria-label', `综合得分 ${item.score.toFixed(1)}`);

  const value = el('span', 'score-value', item.score.toFixed(1));
  const meter = el('span', 'meter');
  const fill = el('span');
  fill.style.width = scoreWidth(item.score);
  meter.appendChild(fill);
  wrap.append(value, meter);

  if (item.scores) {
    const weights = state.status?.policy?.weights || {};
    const pop = el('div', 'score-pop');
    pop.setAttribute('role', 'tooltip');
    pop.appendChild(el('p', 'score-pop-title', '得分构成'));
    const list = el('dl');
    SCORE_PARTS.forEach(([key, label]) => {
      const part = item.scores[key] ?? 0;
      const row = el('div');
      const dt = el('dt', '', label);
      if (weights[key] !== undefined) dt.appendChild(el('small', '', ` ×${weights[key]}`));
      const dd = el('dd');
      const bar = el('span', 'bar');
      const barFill = el('i');
      barFill.style.width = `${Math.max(2, part)}%`;
      bar.appendChild(barFill);
      dd.append(bar, el('b', '', String(Math.round(part))));
      row.append(dt, dd);
      list.appendChild(row);
    });
    pop.appendChild(list);
    wrap.appendChild(pop);
  } else {
    wrap.title = `得分 ${item.score.toFixed(1)}`;
  }
  return wrap;
}

function createTitle(item) {
  const link = el('a', 'item-title');
  link.href = item.target;
  link.target = '_blank';
  link.rel = 'noopener noreferrer';

  let text = item.title;
  // 数据集 id：owner 弱化显示
  if (item.category === 'datasets' && text.includes('/')) {
    const [owner, ...rest] = text.split('/');
    link.appendChild(el('span', 'title-owner', `${owner}/`));
    text = rest.join('/');
  }
  // 最后一个词和外链图标绑在一起，避免图标单独换行
  const splitAt = text.lastIndexOf(' ') + 1;
  const tail = el('span', 'nowrap', text.slice(splitAt));
  tail.insertAdjacentHTML('beforeend', ICONS.external);
  link.append(text.slice(0, splitAt), tail);
  return link;
}

function createMeta(item) {
  const meta = el('div', 'item-meta');
  if (item.isNew) meta.appendChild(el('span', 'badge-new', 'NEW'));
  item.sources.forEach((source) => meta.appendChild(el('span', 'tag', sourceLabel(source))));

  if (item.authors.length) {
    const shown = item.authors.slice(0, 3).join(', ');
    const more = item.authorCount > 3 ? ` 等 ${item.authorCount} 人` : '';
    const authors = el('span', 'authors', shown + more);
    authors.title = item.authors.join(', ');
    meta.appendChild(authors);
  } else {
    meta.appendChild(el('span', 'muted-text', categoryLabel(item.category)));
  }

  const date = item.publishedDate || item.firstSeen;
  if (date) {
    const time = el('time', '', relativeDay(date));
    time.dateTime = date.toISOString();
    time.title = formatDateTime(date);
    meta.appendChild(time);
  }
  return meta;
}

function createFooter(item) {
  const foot = el('div', 'item-foot');
  item.keywords.forEach((keyword) => {
    const topic = el('button', 'topic', `#${keyword}`);
    topic.type = 'button';
    topic.title = `搜索“${keyword}”`;
    topic.addEventListener('click', () => {
      elements.searchInput.value = keyword;
      render();
    });
    foot.appendChild(topic);
  });

  const links = el('span', 'item-links');
  if (item.upvotes) {
    const up = item.hfUrl ? iconLink(item.hfUrl, ICONS.up, compactNumber(item.upvotes)) : el('span', 'meta-link');
    if (!item.hfUrl) { up.innerHTML = ICONS.up; up.append(compactNumber(item.upvotes)); }
    up.title = `Hugging Face ${item.upvotes} 个赞`;
    links.appendChild(up);
  }
  if (item.likes) {
    const likes = el('span', 'meta-link');
    likes.innerHTML = ICONS.heart;
    likes.append(compactNumber(item.likes));
    likes.title = `${item.likes} likes`;
    links.appendChild(likes);
  }
  if (item.githubUrl) {
    const code = iconLink(item.githubUrl, ICONS.code, item.githubStars ? `代码 ★${compactNumber(item.githubStars)}` : '代码');
    code.title = item.githubUrl;
    links.appendChild(code);
  }
  if (links.childElementCount) foot.appendChild(links);
  return foot.childElementCount ? foot : null;
}

function createItem(item, index, highlightTop) {
  const li = el('li', 'item');
  li.appendChild(el('span', `rank${highlightTop && index < 3 ? ' top' : ''}`, String(index + 1).padStart(2, '0')));

  const body = el('div', 'item-body');
  body.append(createTitle(item), createMeta(item));

  if (item.summary) {
    const expanded = state.expanded.has(item.id);
    const summary = el('p', `item-summary${expanded ? ' expanded' : ''}`, item.summary);
    body.appendChild(summary);
    if (item.summary.length > 120) {
      const more = el('button', 'more-btn', expanded ? '收起' : '展开摘要');
      more.type = 'button';
      more.dataset.focusKey = `more:${item.id}`;
      more.setAttribute('aria-expanded', String(expanded));
      more.insertAdjacentHTML('beforeend', ICONS.chevron);
      more.addEventListener('click', () => toggleExpanded(item.id));
      body.appendChild(more);
    }
  }
  const foot = createFooter(item);
  if (foot) body.appendChild(foot);

  const aside = el('div', 'item-aside');
  const isFav = state.favorites.has(item.id);
  const fav = el('button', 'fav-btn');
  fav.type = 'button';
  fav.dataset.focusKey = `fav:${item.id}`;
  fav.setAttribute('aria-pressed', String(isFav));
  fav.setAttribute('aria-label', isFav ? '取消收藏' : '收藏');
  fav.title = isFav ? '取消收藏' : '收藏';
  fav.innerHTML = ICONS.star;
  fav.addEventListener('click', () => toggleFavorite(item.id));
  aside.append(createScore(item), fav);

  li.append(body, aside);
  return li;
}

function renderFeed(visibleItems) {
  elements.feed.innerHTML = '';
  elements.feed.classList.toggle('is-compact', state.compactView);

  if (!visibleItems.length) {
    const empty = el('li', 'empty');
    empty.textContent = state.showFavoritesOnly && !state.favorites.size
      ? '还没有收藏任何条目，点击条目右侧的星标即可收藏。'
      : '没有匹配的内容，试试调整关键词或筛选条件。';
    elements.feed.appendChild(empty);
    return;
  }

  const highlightTop = elements.sortSelect.value === 'score_desc';
  const fragment = document.createDocumentFragment();
  visibleItems.forEach((item, index) => fragment.appendChild(createItem(item, index, highlightTop)));
  elements.feed.appendChild(fragment);
}

function render() {
  // 列表会整体重建，记住焦点所在的按钮以便键盘操作不中断
  const focusKey = document.activeElement?.dataset?.focusKey;
  const visibleItems = getVisibleItems();
  renderCategoryTabs();
  renderSourceChips();
  renderFeed(visibleItems);

  const filtered = hasActiveFilters();
  elements.resultNote.textContent = filtered
    ? `显示 ${visibleItems.length} / ${state.items.length} 条`
    : `共 ${state.items.length} 条`;
  elements.clearFilters.hidden = !filtered;
  elements.favoriteCount.textContent = String(state.favorites.size);
  elements.favoritesToggle.setAttribute('aria-pressed', String(state.showFavoritesOnly));
  elements.compactToggle.setAttribute('aria-pressed', String(state.compactView));

  if (focusKey) {
    [...document.querySelectorAll('[data-focus-key]')].find((node) => node.dataset.focusKey === focusKey)?.focus();
  }
}

// ---------------------------------------------------------------------------
// 事件
// ---------------------------------------------------------------------------

function resetFilters() {
  elements.searchInput.value = '';
  elements.sortSelect.value = 'score_desc';
  state.source = 'all';
  state.category = 'all';
  state.showFavoritesOnly = false;
  render();
}

function currentTheme() {
  if (document.documentElement.dataset.theme) return document.documentElement.dataset.theme;
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

function bindEvents() {
  elements.searchInput.addEventListener('input', render);
  elements.sortSelect.addEventListener('change', render);
  elements.favoritesToggle.addEventListener('click', () => {
    state.showFavoritesOnly = !state.showFavoritesOnly;
    render();
  });
  elements.compactToggle.addEventListener('click', () => {
    state.compactView = !state.compactView;
    savePrefs({ compact: state.compactView });
    render();
  });
  elements.clearFilters.addEventListener('click', resetFilters);
  elements.themeToggle.addEventListener('click', () => {
    const next = currentTheme() === 'dark' ? 'light' : 'dark';
    document.documentElement.dataset.theme = next;
    savePrefs({ theme: next });
  });

  document.addEventListener('keydown', (event) => {
    const typing = /^(INPUT|SELECT|TEXTAREA)$/.test(document.activeElement?.tagName || '');
    if (event.key === '/' && !typing) {
      event.preventDefault();
      elements.searchInput.focus();
    } else if (event.key === 'Escape' && document.activeElement === elements.searchInput) {
      elements.searchInput.value = '';
      elements.searchInput.blur();
      render();
    }
  });
}

// ---------------------------------------------------------------------------
// 启动
// ---------------------------------------------------------------------------

async function loadFeed() {
  const resp = await fetch(FEED_PATH, { cache: 'no-cache' });
  if (!resp.ok) throw new Error(`blog.json ${resp.status}`);
  return { items: await resp.json(), lastModified: parseDate(resp.headers.get('Last-Modified')) };
}

async function loadStatus() {
  try {
    const resp = await fetch(STATUS_PATH, { cache: 'no-cache' });
    return resp.ok ? await resp.json() : null;
  } catch (e) {
    return null;
  }
}

async function init() {
  bindEvents();
  try {
    const [feed, status] = await Promise.all([loadFeed(), loadStatus()]);
    if (!Array.isArray(feed.items)) throw new Error('feed format invalid');

    state.status = status;
    (status?.sources || []).forEach((s) => { state.sourceLabels[s.id] = s.label || s.id; });
    state.items = dedupe(feed.items.map(normalize));
    state.absoluteScores = state.items.some((item) => item.scores);
    state.maxScore = state.items.reduce((max, item) => Math.max(max, item.score), 0);

    renderOverview({ lastModified: feed.lastModified });
    renderSources();
    render();
  } catch (error) {
    setStatus('error', '加载失败', String(error));
    elements.policyNote.textContent = '数据加载失败，请稍后刷新重试。';
    elements.feed.innerHTML = '<li class="empty">读取 blog.json 失败，请检查发布产物是否包含该文件。</li>';
    elements.sourcesBody.innerHTML = '<tr><td colspan="4" class="muted">加载失败</td></tr>';
  }
}

init();

if ('serviceWorker' in navigator && (location.protocol === 'https:' || location.hostname === 'localhost')) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('./sw.js').catch(() => { /* 离线缓存不可用不影响使用 */ });
  });
}
