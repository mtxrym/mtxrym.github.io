// 热榜聚合：热榜页（data-page="home"）与收藏页（data-page="favorites"）共用这份脚本。
// 数据来自 data/all.json（GitHub Actions 每小时生成）；收藏存在浏览器本地。
// 标题等内容来自第三方网站，一律用 textContent 渲染，链接只接受 http(s)。

const DATA_URL = 'data/all.json';
const INDEX_URL = 'data/index.json';
const PREFS_KEY = 'trending:prefs';
const BOOKMARKS_KEY = 'trending:bookmarks';
const POLL_MS = 5 * 60 * 1000;
const MAX_BOOKMARKS = 1000;
const PAGE = document.body.dataset.page || 'home';
const COLORS = ['red', 'orange', 'green', 'emerald', 'teal', 'blue', 'indigo', 'slate', 'gray'];

const TABS = [
  { id: 'hottest', name: '最热', match: (s) => s.type === 'hottest' },
  { id: 'realtime', name: '实时', match: (s) => s.type === 'realtime' },
  { id: 'china', name: '国内', match: (s) => s.column === 'china' },
  { id: 'world', name: '国际', match: (s) => s.column === 'world' },
  { id: 'tech', name: '科技', match: (s) => s.column === 'tech' },
  { id: 'finance', name: '财经', match: (s) => s.column === 'finance' },
  { id: 'sports', name: '体育', match: (s) => s.column === 'sports' },
  { id: 'all', name: '全部', match: () => true }
];

// ---------------------------------------------------------------------------
// 本地存储（隐私模式等场景下读写会失败，页面照常可用）
// ---------------------------------------------------------------------------

const store = {
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
    } catch (e) { /* 忽略 */ }
  }
};

function loadPrefs() {
  const raw = store.get(PREFS_KEY, {}) || {};
  // 兼容第一版的 focus 字段
  const favorites = Array.isArray(raw.favorites) ? raw.favorites : Array.isArray(raw.focus) ? raw.focus : [];
  return {
    tab: typeof raw.tab === 'string' ? raw.tab : '',
    theme: raw.theme === 'dark' || raw.theme === 'light' ? raw.theme : '',
    favorites: [...new Set(favorites.filter((id) => typeof id === 'string'))]
  };
}

function loadBookmarks() {
  const raw = store.get(BOOKMARKS_KEY, []);
  return Array.isArray(raw) ? raw.filter(isBookmark) : [];
}

function isBookmark(b) {
  return b && typeof b.key === 'string' && typeof b.title === 'string' && typeof b.url === 'string';
}

let prefs = loadPrefs();
let bookmarks = loadBookmarks();
const state = { data: null, checkedAt: 0, query: '' };

const savePrefs = () => store.set(PREFS_KEY, prefs);
const saveBookmarks = () => store.set(BOOKMARKS_KEY, bookmarks);

// ---------------------------------------------------------------------------
// 工具
// ---------------------------------------------------------------------------

const $ = (id) => document.getElementById(id);

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = text;
  return node;
}

// 固定的图标（不含第三方内容）
const ICONS = {
  star: '<path d="M12 3.5l2.6 5.3 5.9.9-4.3 4.1 1 5.8L12 16.9l-5.2 2.7 1-5.8-4.3-4.1 5.9-.9z"/>',
  open: '<path d="M14 5h5v5M19 5l-8 8M18 14v4a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h4"/>',
  bookmark: '<path d="M7 4h10a1 1 0 0 1 1 1v15l-6-4-6 4V5a1 1 0 0 1 1-1z"/>',
  up: '<path d="M6 15l6-6 6 6"/>',
  down: '<path d="M6 9l6 6 6-6"/>',
  remove: '<path d="M6 6l12 12M18 6L6 18"/>'
};

function icon(name) {
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('viewBox', '0 0 24 24');
  svg.setAttribute('class', 'i');
  svg.setAttribute('aria-hidden', 'true');
  svg.innerHTML = ICONS[name];
  return svg;
}

function iconButton(name, title, onClick, className = 'icon-btn') {
  const button = el('button', className);
  button.type = 'button';
  button.title = title;
  button.setAttribute('aria-label', title);
  button.append(icon(name));
  button.addEventListener('click', onClick);
  return button;
}

const rtf = new Intl.RelativeTimeFormat('zh-CN', { numeric: 'auto' });

function relative(iso) {
  const time = Date.parse(iso);
  if (Number.isNaN(time)) return '';
  const minutes = Math.round((time - Date.now()) / 60000);
  if (Math.abs(minutes) < 1) return '刚刚';
  if (Math.abs(minutes) < 60) return rtf.format(minutes, 'minute');
  const hours = Math.round(minutes / 60);
  if (Math.abs(hours) < 24) return rtf.format(hours, 'hour');
  return rtf.format(Math.round(hours / 24), 'day');
}

function clock(iso) {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '';
  const pad = (n) => String(n).padStart(2, '0');
  return date.toDateString() === new Date().toDateString()
    ? `${pad(date.getHours())}:${pad(date.getMinutes())}`
    : `${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

const safeUrl = (url) => (typeof url === 'string' && /^https?:\/\//i.test(url) ? url : '');
const colorVar = (color) => `var(--c-${COLORS.includes(color) ? color : 'gray'})`;

// 本轮新上榜：抓取脚本给新出现的条目打上 first_seen = 本次生成时间（没有上一版数据时不打）
function isNew(item) {
  return Boolean(state.data && state.data.previous_generated_at && item.first_seen === state.data.generated_at);
}

function highlight(text, query) {
  const frag = document.createDocumentFragment();
  if (!query) {
    frag.append(text);
    return frag;
  }
  const lower = text.toLowerCase();
  let start = 0;
  let index = lower.indexOf(query);
  while (index !== -1) {
    frag.append(text.slice(start, index), el('mark', '', text.slice(index, index + query.length)));
    start = index + query.length;
    index = lower.indexOf(query, start);
  }
  frag.append(text.slice(start));
  return frag;
}

let toastTimer;
function toast(message) {
  const box = $('toast');
  box.textContent = message;
  box.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => box.classList.remove('show'), 2200);
}

function link(url, className, content) {
  const safe = safeUrl(url);
  const node = el(safe ? 'a' : 'span', className);
  if (safe) {
    node.href = safe;
    node.target = '_blank';
    node.rel = 'noopener noreferrer';
  }
  node.append(content);
  return node;
}

// ---------------------------------------------------------------------------
// 收藏
// ---------------------------------------------------------------------------

const isFavorite = (id) => prefs.favorites.includes(id);

function toggleFavorite(source) {
  if (isFavorite(source.id)) {
    prefs.favorites = prefs.favorites.filter((id) => id !== source.id);
    toast(`已取消收藏 ${source.label || source.name}`);
  } else {
    prefs.favorites.push(source.id);
    toast(`已收藏 ${source.label || source.name}，在“我的收藏”查看`);
  }
  savePrefs();
  renderAll();
}

function moveFavorite(id, delta) {
  const list = prefs.favorites;
  const from = list.indexOf(id);
  const to = from + delta;
  if (from < 0 || to < 0 || to >= list.length) return;
  [list[from], list[to]] = [list[to], list[from]];
  savePrefs();
  renderAll();
}

const bookmarkKey = (sourceId, itemId) => `${sourceId}|${itemId}`;
const findBookmark = (key) => bookmarks.find((b) => b.key === key);

function toggleBookmark(source, item) {
  const key = bookmarkKey(source.id, item.id);
  if (findBookmark(key)) {
    bookmarks = bookmarks.filter((b) => b.key !== key);
    toast('已取消收藏');
  } else {
    bookmarks.unshift({
      key,
      source: source.id,
      label: source.label || source.name,
      color: source.color || 'gray',
      title: item.title,
      url: item.url,
      info: item.info || '',
      saved_at: new Date().toISOString()
    });
    bookmarks = bookmarks.slice(0, MAX_BOOKMARKS);
    toast('已收藏，在“我的收藏”查看');
  }
  saveBookmarks();
  renderAll();
}

function removeBookmark(key) {
  bookmarks = bookmarks.filter((b) => b.key !== key);
  saveBookmarks();
  renderAll();
}

// ---------------------------------------------------------------------------
// 卡片
// ---------------------------------------------------------------------------

function renderItem(source, item, index, query) {
  const li = el('li');
  if (source.type === 'realtime') {
    li.append(el('span', 'when', item.time ? clock(item.time) : ''));
  } else {
    li.append(el('span', `rank${source.type === 'hottest' && !query ? ' hot' : ''}`, String(index + 1)));
  }

  const body = el('div', 'body');
  const title = link(item.url, 'title', highlight(item.title, query));
  if (item.hover) title.title = item.hover;
  body.append(title);
  if (isNew(item)) body.append(el('span', 'tag new', '新'));
  if (source.type === 'hottest' && item.rank_delta) {
    const up = item.rank_delta > 0;
    const tag = el('span', `tag ${up ? 'up' : 'down'}`, `${up ? '↑' : '↓'}${Math.abs(item.rank_delta)}`);
    tag.title = `比上一轮${up ? '上升' : '下降'} ${Math.abs(item.rank_delta)} 名`;
    body.append(tag);
  }
  if (item.info) body.append(el('span', 'info', item.info));
  li.append(body);

  const saved = Boolean(findBookmark(bookmarkKey(source.id, item.id)));
  const bm = iconButton('bookmark', saved ? '取消收藏这条' : '收藏这条', () => toggleBookmark(source, item), 'bm');
  bm.setAttribute('aria-pressed', String(saved));
  li.append(bm);
  return li;
}

function renderCard(source, items, { query = '', favoritesPage = false, position = 0, count = 0 } = {}) {
  const card = el('article', 'card');
  card.style.setProperty('--src', colorVar(source.color));

  const head = el('div', 'card-head');
  head.append(el('span', 'card-dot'), el('span', 'card-name', source.name));
  if (source.title) head.append(el('span', 'card-sub', source.title));

  const actions = el('div', 'card-actions');
  if (favoritesPage) {
    const up = iconButton('up', '上移', () => moveFavorite(source.id, -1));
    const down = iconButton('down', '下移', () => moveFavorite(source.id, 1));
    up.disabled = position === 0;
    down.disabled = position === count - 1;
    actions.append(up, down);
  }
  const favorite = isFavorite(source.id);
  const star = iconButton('star', favorite ? '取消收藏这个源' : '收藏这个源', () => toggleFavorite(source));
  star.setAttribute('aria-pressed', String(favorite));
  actions.append(star);
  const home = safeUrl(source.home);
  if (home) {
    const open = link(home, 'icon-btn', icon('open'));
    open.title = `打开${source.name}`;
    open.setAttribute('aria-label', open.title);
    actions.append(open);
  }
  head.append(actions);
  card.append(head);

  const status = el('div', `card-status${source.status === 'stale' ? ' stale' : ''}`);
  if (!source.items || !source.items.length) {
    status.textContent = `暂时拿不到：${source.error || '没有数据'}`;
  } else if (source.status === 'stale') {
    status.textContent = `本轮抓取失败，显示 ${relative(source.updated_at) || '之前'} 的数据`;
  } else {
    status.append(el('span', '', `${relative(source.updated_at)}更新`));
    const fresh = source.items.filter(isNew).length;
    if (fresh) status.append(el('span', 'fresh', `${fresh} 条新上榜`));
    if (query) status.append(el('span', '', `匹配 ${items.length} 条`));
  }
  card.append(status);

  if (items.length) {
    const list = el('ol', 'list');
    items.forEach((item, i) => list.append(renderItem(source, item, i, query)));
    card.append(list);
  }
  return card;
}

const matchItems = (source, query) =>
  query ? (source.items || []).filter((it) => it.title.toLowerCase().includes(query)) : source.items || [];

// ---------------------------------------------------------------------------
// 热榜页
// ---------------------------------------------------------------------------

function currentTab() {
  return TABS.find((t) => t.id === prefs.tab) || TABS[0];
}

function renderTabs(usable) {
  const nav = $('tabs');
  nav.replaceChildren();
  const active = currentTab();
  for (const tab of TABS) {
    const button = el('button');
    button.type = 'button';
    button.setAttribute('role', 'tab');
    button.setAttribute('aria-selected', String(tab.id === active.id));
    button.append(tab.name, el('span', '', String(usable.filter(tab.match).length)));
    button.addEventListener('click', () => {
      prefs.tab = tab.id;
      savePrefs();
      renderAll();
      window.scrollTo({ top: 0 });
    });
    nav.append(button);
  }
}

function renderHome() {
  const grid = $('grid');
  grid.replaceChildren();
  if (!state.data) return;
  const usable = state.data.sources.filter((s) => s.items && s.items.length);
  const failed = state.data.sources.filter((s) => !s.items || !s.items.length);
  const query = state.query;

  renderTabs(usable);
  let shown = 0;
  for (const source of usable.filter(currentTab().match)) {
    const items = matchItems(source, query);
    if (query && !items.length) continue;
    grid.append(renderCard(source, items, { query }));
    shown += 1;
  }
  if (!shown) grid.append(el('p', 'empty', query ? `没有标题包含“${query}”的条目` : '这个栏目暂时没有数据'));

  const box = $('unavailable');
  box.hidden = !failed.length;
  if (failed.length) {
    box.querySelector('summary').textContent = `暂时拿不到的源（${failed.length}）`;
    box.querySelector('ul').replaceChildren(...failed.map((s) => {
      const li = el('li');
      li.append(el('span', '', s.label || s.name), ' ', el('span', 'err', s.error || '没有数据'));
      return li;
    }));
  }
}

// ---------------------------------------------------------------------------
// 收藏页
// ---------------------------------------------------------------------------

function emptyHint(before, linkText, after) {
  const p = el('p', 'empty', before);
  const a = el('a', '', linkText);
  a.href = './';
  p.append(a, after);
  return p;
}

function renderFavorites() {
  const query = state.query;
  const grid = $('grid');
  grid.replaceChildren();
  const byId = new Map((state.data ? state.data.sources : []).map((s) => [s.id, s]));
  const favorites = prefs.favorites.map((id) => byId.get(id)).filter(Boolean);
  $('src-count').textContent = prefs.favorites.length ? `（${prefs.favorites.length}）` : '';

  if (!prefs.favorites.length) {
    grid.append(emptyHint('还没有收藏的源。去', '热榜页', '点卡片右上角的 ☆ 收藏常看的源。'));
  } else if (!state.data) {
    grid.append(el('p', 'empty', '热榜数据还没加载出来'));
  } else {
    let shown = 0;
    favorites.forEach((source, position) => {
      const items = matchItems(source, query);
      if (query && !items.length) return;
      grid.append(renderCard(source, items, { query, favoritesPage: true, position, count: favorites.length }));
      shown += 1;
    });
    if (!shown) grid.append(el('p', 'empty', query ? `收藏的源里没有标题包含“${query}”的条目` : '收藏的源暂时都没有数据'));
  }

  const list = $('saved');
  list.replaceChildren();
  $('item-count').textContent = bookmarks.length ? `（${bookmarks.length}）` : '';
  const matched = bookmarks
    .filter((b) => !query || b.title.toLowerCase().includes(query) || (b.label || '').toLowerCase().includes(query))
    .sort((a, b) => (b.saved_at || '').localeCompare(a.saved_at || ''));
  if (!matched.length) {
    const li = el('li');
    li.append(bookmarks.length ? el('span', 'sub', `没有匹配“${query}”的收藏`) : emptyHint('还没有收藏的条目。在', '热榜页', '把鼠标移到条目上，点右侧的书签图标。'));
    list.append(li);
    return;
  }
  for (const b of matched) {
    const li = el('li');
    const src = el('span', 'src', b.label || b.source);
    src.style.setProperty('--src', colorVar(b.color));
    const body = el('div', 'body');
    body.append(link(b.url, 'title', highlight(b.title, query)));
    body.append(el('div', 'sub', [b.info, b.saved_at ? `收藏于${relative(b.saved_at)}` : ''].filter(Boolean).join(' · ')));
    li.append(src, body, iconButton('remove', '移除这条收藏', () => removeBookmark(b.key)));
    list.append(li);
  }
}

function exportFavorites() {
  const payload = {
    type: 'mtxrym-trending-favorites',
    version: 1,
    exported_at: new Date().toISOString(),
    favorites: prefs.favorites,
    bookmarks
  };
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
  const a = el('a');
  a.href = URL.createObjectURL(blob);
  a.download = `trending-favorites-${new Date().toISOString().slice(0, 10)}.json`;
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

async function importFavorites(file) {
  try {
    const data = JSON.parse(await file.text());
    if (!data || data.type !== 'mtxrym-trending-favorites') throw new Error('不是热榜收藏的导出文件');
    const sources = (Array.isArray(data.favorites) ? data.favorites : []).filter((id) => typeof id === 'string' && !isFavorite(id));
    const known = new Set(bookmarks.map((b) => b.key));
    const items = (Array.isArray(data.bookmarks) ? data.bookmarks : []).filter((b) => isBookmark(b) && safeUrl(b.url) && !known.has(b.key));
    prefs.favorites.push(...sources);
    bookmarks = [...bookmarks, ...items].slice(0, MAX_BOOKMARKS);
    savePrefs();
    saveBookmarks();
    renderAll();
    toast(`导入了 ${sources.length} 个源、${items.length} 条条目`);
  } catch (err) {
    toast(`导入失败：${err.message}`);
  }
}

// ---------------------------------------------------------------------------
// 总体渲染与数据加载
// ---------------------------------------------------------------------------

function renderMeta() {
  const meta = $('meta');
  meta.replaceChildren();
  if (!state.data) return;
  const sources = state.data.sources;
  const usable = sources.filter((s) => s.items && s.items.length).length;
  const fresh = sources.reduce((n, s) => n + (s.status === 'ok' ? s.items.filter(isNew).length : 0), 0);
  meta.append(`${relative(state.data.generated_at)}更新 · ${usable}/${sources.length} 个源`);
  if (fresh) meta.append(' · ', el('b', '', `新上榜 ${fresh}`));
}

function renderAll() {
  const count = prefs.favorites.length + bookmarks.length;
  $('fav-count').textContent = count ? String(count) : '';
  if (PAGE === 'favorites') renderFavorites();
  else renderHome();
  renderMeta();
}

async function loadData({ silent = false } = {}) {
  try {
    const resp = await fetch(DATA_URL, { cache: 'no-cache' });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    state.data = await resp.json();
    state.checkedAt = Date.now();
    $('notice').hidden = true;
    renderAll();
    if (silent) toast('热榜已更新');
  } catch (err) {
    const notice = $('notice');
    notice.hidden = false;
    notice.textContent = state.data
      ? `刷新失败（${err.message}），显示的是之前加载的数据。`
      : `热榜数据加载失败（${err.message}）。数据由定时任务生成，首次部署后稍等几分钟再刷新。`;
    renderAll();
  }
}

async function checkForUpdate() {
  state.checkedAt = Date.now();
  if (!state.data) return loadData();
  try {
    const resp = await fetch(INDEX_URL, { cache: 'no-store' });
    if (!resp.ok) return;
    const index = await resp.json();
    if (index.generated_at && index.generated_at !== state.data.generated_at) await loadData({ silent: true });
    else renderMeta(); // 刷新“x 分钟前更新”
  } catch (e) { /* 网络抖动时下次再查 */ }
}

function setupChrome() {
  $('theme').addEventListener('click', () => {
    const current = document.documentElement.dataset.theme
      || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
    prefs.theme = current === 'dark' ? 'light' : 'dark';
    document.documentElement.dataset.theme = prefs.theme;
    savePrefs();
  });

  let typing;
  $('query').addEventListener('input', (event) => {
    clearTimeout(typing);
    typing = setTimeout(() => {
      state.query = event.target.value.trim().toLowerCase();
      renderAll();
    }, 120);
  });

  document.addEventListener('keydown', (event) => {
    const tag = (event.target.tagName || '').toLowerCase();
    if (event.key === '/' && !['input', 'textarea', 'select'].includes(tag) && !event.metaKey && !event.ctrlKey) {
      event.preventDefault();
      $('query').focus();
    } else if (event.key === 'Escape' && event.target === $('query')) {
      $('query').value = '';
      state.query = '';
      $('query').blur();
      renderAll();
    }
  });

  const toTop = $('to-top');
  window.addEventListener('scroll', () => toTop.classList.toggle('show', window.scrollY > 600), { passive: true });
  toTop.addEventListener('click', () => window.scrollTo({ top: 0, behavior: 'smooth' }));

  // 其他标签页改了收藏，这里同步
  window.addEventListener('storage', (event) => {
    if (event.key === PREFS_KEY || event.key === BOOKMARKS_KEY) {
      prefs = loadPrefs();
      bookmarks = loadBookmarks();
      renderAll();
    }
  });

  // 页面开着时每 5 分钟看一次有没有新数据（只请求很小的 index.json）
  setInterval(() => {
    if (document.visibilityState === 'visible') checkForUpdate();
  }, POLL_MS);
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible' && Date.now() - state.checkedAt > POLL_MS) checkForUpdate();
  });

  if (PAGE === 'favorites') {
    $('export').addEventListener('click', exportFavorites);
    $('import').addEventListener('click', () => $('import-file').click());
    $('import-file').addEventListener('change', (event) => {
      const [file] = event.target.files;
      if (file) importFavorites(file);
      event.target.value = '';
    });
  }
}

setupChrome();
renderAll();
loadData();
