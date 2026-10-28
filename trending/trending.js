// 热榜聚合页：读取 data/all.json（GitHub Actions 定时生成），按栏目展示各平台热榜。
// 标题等内容来自第三方网站，一律用 textContent 渲染，链接只接受 http(s)。

const DATA_URL = 'data/all.json';
const PREFS_KEY = 'trending:prefs';
const STALE_RELOAD_MS = 10 * 60 * 1000;

const TABS = [
  { id: 'focus', name: '关注', match: (s, st) => st.focus.has(s.id) },
  { id: 'hottest', name: '最热', match: (s) => s.type === 'hottest' },
  { id: 'realtime', name: '实时', match: (s) => s.type === 'realtime' },
  { id: 'china', name: '国内', match: (s) => s.column === 'china' },
  { id: 'world', name: '国际', match: (s) => s.column === 'world' },
  { id: 'tech', name: '科技', match: (s) => s.column === 'tech' },
  { id: 'finance', name: '财经', match: (s) => s.column === 'finance' },
  { id: 'sports', name: '体育', match: (s) => s.column === 'sports' },
  { id: 'all', name: '全部', match: () => true }
];

const prefs = {
  load() {
    try {
      return JSON.parse(localStorage.getItem(PREFS_KEY)) || {};
    } catch (e) {
      return {};
    }
  },
  save(value) {
    try {
      localStorage.setItem(PREFS_KEY, JSON.stringify(value));
    } catch (e) { /* 隐私模式等场景下忽略 */ }
  }
};

const saved = prefs.load();
const state = {
  data: null,
  loadedAt: 0,
  tab: saved.tab || '',
  focus: new Set(Array.isArray(saved.focus) ? saved.focus : []),
  query: ''
};

const $ = (id) => document.getElementById(id);
const el = (tag, className, text) => {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = text;
  return node;
};

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
  const hm = `${pad(date.getHours())}:${pad(date.getMinutes())}`;
  return date.toDateString() === new Date().toDateString() ? hm : `${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

function safeUrl(url) {
  return typeof url === 'string' && /^https?:\/\//i.test(url) ? url : '';
}

function savePrefs() {
  prefs.save({ tab: state.tab, focus: [...state.focus] });
}

function currentTab() {
  const wanted = state.tab || (state.focus.size ? 'focus' : 'hottest');
  return TABS.find((t) => t.id === wanted) || TABS[1];
}

// ---------------------------------------------------------------------------
// 渲染
// ---------------------------------------------------------------------------

function highlight(text, query) {
  const frag = document.createDocumentFragment();
  if (!query) {
    frag.append(text);
    return frag;
  }
  const lower = text.toLowerCase();
  let start = 0;
  let index = lower.indexOf(query, start);
  while (index !== -1) {
    frag.append(text.slice(start, index), el('mark', '', text.slice(index, index + query.length)));
    start = index + query.length;
    index = lower.indexOf(query, start);
  }
  frag.append(text.slice(start));
  return frag;
}

const ICONS = {
  star: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3.5l2.6 5.3 5.9.9-4.3 4.1 1 5.8L12 16.9l-5.2 2.7 1-5.8-4.3-4.1 5.9-.9z"/></svg>',
  open: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M14 5h5v5M19 5l-8 8M18 14v4a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h4"/></svg>'
};

function renderCard(source, items, query) {
  const card = el('article', 'card');

  const head = el('div', 'card-head');
  head.append(el('span', 'card-name', source.name));
  if (source.title) head.append(el('span', 'card-sub', source.title));

  const actions = el('div', 'card-actions');
  const star = el('button', 'icon-btn');
  star.type = 'button';
  star.innerHTML = ICONS.star; // 固定图标，非第三方内容
  const focused = state.focus.has(source.id);
  star.setAttribute('aria-pressed', String(focused));
  star.title = focused ? '取消关注' : '关注（显示在“关注”栏目）';
  star.addEventListener('click', () => {
    if (state.focus.has(source.id)) state.focus.delete(source.id);
    else state.focus.add(source.id);
    savePrefs();
    render();
  });
  actions.append(star);

  const home = safeUrl(source.home);
  if (home) {
    const link = el('a', 'icon-btn');
    link.href = home;
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
    link.title = `打开${source.name}`;
    link.innerHTML = ICONS.open; // 固定图标
    actions.append(link);
  }
  head.append(actions);
  card.append(head);

  const status = el('div', `card-status${source.status === 'stale' ? ' stale' : ''}`);
  const updated = relative(source.updated_at);
  status.textContent = source.status === 'stale'
    ? `本次抓取失败，显示 ${updated || '之前'} 的数据`
    : `${updated ? `${updated}更新` : ''}${query ? ` · 匹配 ${items.length} 条` : ''}`;
  card.append(status);

  const list = el('ol', 'list');
  const ranked = source.type !== 'realtime';
  items.forEach((item, i) => {
    const li = el('li');
    if (ranked) {
      li.append(el('span', `rank${source.type === 'hottest' && !query ? ' hot' : ''}`, String(i + 1)));
    } else {
      li.append(el('span', 'when', item.time ? clock(item.time) : ''));
    }
    const body = el('div', 'body');
    const url = safeUrl(item.url);
    const title = el(url ? 'a' : 'span', 'title');
    if (url) {
      title.href = url;
      title.target = '_blank';
      title.rel = 'noopener noreferrer';
    }
    title.append(highlight(item.title, query));
    if (item.hover) title.title = item.hover;
    body.append(title);
    if (item.info) body.append(el('span', 'info', item.info));
    li.append(body);
    list.append(li);
  });
  card.append(list);
  return card;
}

function renderTabs(sources) {
  const nav = $('tabs');
  nav.replaceChildren();
  const active = currentTab();
  for (const tab of TABS) {
    const count = sources.filter((s) => tab.match(s, state)).length;
    if (tab.id === 'focus' && !count) continue;
    const button = el('button');
    button.type = 'button';
    button.setAttribute('role', 'tab');
    button.setAttribute('aria-selected', String(tab.id === active.id));
    button.append(tab.name, el('span', '', String(count)));
    button.addEventListener('click', () => {
      state.tab = tab.id;
      savePrefs();
      render();
      window.scrollTo({ top: 0 });
    });
    nav.append(button);
  }
}

function render() {
  const data = state.data;
  if (!data) return;
  const usable = data.sources.filter((s) => s.items && s.items.length);
  const failed = data.sources.filter((s) => !s.items || !s.items.length);
  const query = state.query.trim().toLowerCase();

  renderTabs(usable);
  const tab = currentTab();
  const grid = $('grid');
  grid.replaceChildren();

  let shown = 0;
  for (const source of usable.filter((s) => tab.match(s, state))) {
    const items = query ? source.items.filter((it) => it.title.toLowerCase().includes(query)) : source.items;
    if (query && !items.length) continue;
    grid.append(renderCard(source, items, query));
    shown += 1;
  }
  if (!shown) {
    grid.append(el('p', 'empty', query ? `没有标题包含“${state.query.trim()}”的条目` : '这个栏目暂时没有数据'));
  }

  const box = $('unavailable');
  box.hidden = !failed.length;
  if (failed.length) {
    box.querySelector('summary').textContent = `暂时拿不到的源（${failed.length}）`;
    const list = box.querySelector('ul');
    list.replaceChildren(...failed.map((s) => {
      const li = el('li');
      li.append(el('span', '', s.label || s.name), ' ', el('span', 'err', s.error || '没有数据'));
      return li;
    }));
  }

  const totals = data.totals || {};
  $('meta').textContent = `${relative(data.generated_at)}更新 · ${usable.length}/${totals.total || data.sources.length} 个源可用`;
}

// ---------------------------------------------------------------------------
// 加载
// ---------------------------------------------------------------------------

async function load() {
  try {
    const resp = await fetch(DATA_URL, { cache: 'no-cache' });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    state.data = await resp.json();
    state.loadedAt = Date.now();
    $('notice').hidden = true;
    render();
  } catch (err) {
    const notice = $('notice');
    notice.hidden = false;
    notice.textContent = state.data
      ? `刷新失败（${err.message}），显示的是之前加载的数据。`
      : `热榜数据加载失败（${err.message}）。数据由定时任务生成，首次部署后稍等几分钟再刷新。`;
    if (!state.data) $('meta').textContent = '';
  }
}

let typing;
$('query').addEventListener('input', (event) => {
  clearTimeout(typing);
  typing = setTimeout(() => {
    state.query = event.target.value;
    render();
  }, 120);
});

document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'visible' && Date.now() - state.loadedAt > STALE_RELOAD_MS) load();
});

load();
