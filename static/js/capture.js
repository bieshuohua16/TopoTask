/* TopoTash 速记 · 一行输入记待办 / 建项目 */
(function () {
  'use strict';

  const TT = window.TT;
  const $ = (id) => document.getElementById(id);

  const input = $('input');
  const backdrop = $('backdrop');
  const suggestBox = $('suggest');
  const taskList = $('taskList');
  const toast = $('toast');
  const toastText = $('toastText');

  const STORE_KEY = 'tt_capture_project';
  const DRAFT_KEY = 'tt_capture_draft';
  const IS_SHELL = new URLSearchParams(location.search).get('shell') === '1';

  // 售前阶段（# 选择器）
  const STAGES = [
    { label: '需求调研', key: 'research' },
    { label: '方案编写', key: 'proposal' },
    { label: 'POC 验证', key: 'poc' },
    { label: '招投标', key: 'bidding' },
  ];
  const STAGE_KEYS = STAGES.reduce((acc, s) => { acc[s.label] = s.key; return acc; }, {});
  const STAGE_LABELS = STAGES.reduce((acc, s) => { acc[s.key] = s.label; return acc; }, {});

  const TOK = /(@[^\s@#!~+，。；：]{1,60}|#(?:需求调研|方案编写|POC 验证|招投标))/g;
  const PRIORITY_CLASS = { 0: 'p0', 1: 'p1', 2: 'p2', 3: 'p3' };

  const S = {
    projects: [],
    project: null,
    tasks: [],
    today: 0,
    mode: 'record',
    composing: false,
    saving: false,
    lastCreated: null,
    suggest: { open: false, items: [], idx: 0, kind: '' },
    window: null,
  };

  const esc = TT.esc;

  /* ------------------------------------------------------------ 工具 */
  function dueLabel(value) {
    if (!value) return '';
    const d = new Date(value);
    if (isNaN(d.getTime())) return '';
    const p = (n) => String(n).padStart(2, '0');
    return p(d.getMonth() + 1) + '-' + p(d.getDate());
  }

  function isToday(value) {
    if (!value) return false;
    const d = new Date(value);
    if (isNaN(d.getTime())) return false;
    const now = new Date();
    return d.getFullYear() === now.getFullYear() && d.getMonth() === now.getMonth() && d.getDate() === now.getDate();
  }

  function toastMsg(text, withUndo) {
    toastText.textContent = text;
    $('toastUndo').hidden = !withUndo;
    toast.hidden = false;
    clearTimeout(toastMsg._t);
    toastMsg._t = setTimeout(() => { toast.hidden = true; }, 2600);
  }

  function setHint() {
    const el = $('hint');
    if (S.suggest.open) {
      el.innerHTML = '<b>↑</b><b>↓</b> 选择 · <b>Enter</b> 确认 · <b>Esc</b> 关闭';
    } else if (S.mode === 'new') {
      el.innerHTML = '<b>Enter</b> 创建 · <b>Esc</b> 取消';
    } else {
      el.innerHTML = '<b>Enter</b> 记待办 · <b>@</b> 换项目 · <b>#</b> 售前阶段';
    }
  }

  /* ------------------------------------------------------------ 渲染 */
  function renderInput() {
    const v = input.value;
    const plus = v.charAt(0) === '+';
    const body = plus ? v.slice(1) : v;
    let out = '';
    let idx = 0;
    let m;
    TOK.lastIndex = 0;
    while ((m = TOK.exec(body)) !== null) {
      out += esc(body.slice(idx, m.index));
      const t = m[0];
      const cls = t.charAt(0) === '#' ? 'tok-stage' : 'tok-at';
      out += '<span class="' + cls + '">' + esc(t) + '</span>';
      idx = m.index + t.length;
    }
    out += esc(body.slice(idx));
    backdrop.innerHTML = (plus ? '<span class="tok-plus">+</span>' : '') + out;
    input.style.height = 'auto';
    input.style.height = Math.max(44, input.scrollHeight) + 'px';
  }

  function setMode(mode) {
    S.mode = mode;
    $('btnSave').textContent = mode === 'new' ? '创建项目' : '记待办';
    input.placeholder = mode === 'new' ? '项目名称，可加 @客户' : '记一条待办…（+ 新建项目）';
    closeSuggest();
    setHint();
  }

  function renderProject() {
    const p = S.project;
    $('projName').textContent = p ? p.name : '还没有项目';
    $('projStage').textContent = p ? (p.stage_label || '') : '';
    $('projDot').style.background = (p && p.color) || '#6366f1';
  }

  function renderTasks() {
    const open = S.tasks.filter((t) => t.status !== 'done');
    $('taskCount').textContent = open.length ? String(open.length) : '';
    if (!open.length) {
      taskList.innerHTML = '<div class="cap-empty">没有未完成的待办</div>';
    } else {
      taskList.innerHTML = open.slice(0, 6).map((t) => {
        const p = PRIORITY_CLASS[Number(t.priority)] || 'p2';
        return '<div class="cap-task" title="' + esc(t.title) + '">'
          + '<i class="cap-prio ' + p + '"></i>'
          + '<span class="cap-task-title">' + esc(t.title) + '</span>'
          + (t.due_date ? '<span class="cap-task-due">' + dueLabel(t.due_date) + '</span>' : '')
          + '</div>';
      }).join('');
    }
    S.today = S.tasks.filter((t) => isToday(t.created_at)).length;
    // 今日条数只放在收起态标题栏里，展开时标题不抢空间
    $('pillMeta').textContent = '今日 ' + S.today + ' 条';
  }

  /* ------------------------------------------------------------ 数据 */
  async function loadProjects() {
    const data = await TT.api('/api/projects');
    S.projects = data.items || [];
  }

  function pickProject() {
    let saved = null;
    try { saved = localStorage.getItem(STORE_KEY); } catch (e) { saved = null; }
    const found = S.projects.find((p) => p.id === saved);
    S.project = found || S.projects[0] || null;
    if (S.project) {
      try { localStorage.setItem(STORE_KEY, S.project.id); } catch (e) { /* ignore */ }
    }
  }

  async function loadTasks() {
    if (!S.project) { S.tasks = []; renderTasks(); return; }
    try {
      const data = await TT.api('/api/tasks?project_id=' + encodeURIComponent(S.project.id) + '&limit=200');
      S.tasks = data.items || [];
    } catch (e) {
      S.tasks = [];
    }
    renderTasks();
  }

  async function setProject(p) {
    S.project = p;
    try { localStorage.setItem(STORE_KEY, p.id); } catch (e) { /* ignore */ }
    renderProject();
    await loadTasks();          // @ 选了项目，下面立刻换成它的待办
  }

  /* ------------------------------------------------------------ 选择器 */
  function suggestCtx() {
    const m = /([@#])([^\s@#!~+，。；：]*)$/.exec(input.value);
    if (!m) return null;
    return { kind: m[1] === '@' ? 'project' : 'stage', frag: m[2], start: m.index };
  }

  function openSuggest() {
    const ctx = suggestCtx();
    if (!ctx) { closeSuggest(); return; }
    let items;
    if (ctx.kind === 'project') {
      const frag = ctx.frag;
      items = S.projects.filter((p) =>
        !frag || p.name.indexOf(frag) !== -1 || (p.customer || '').indexOf(frag) !== -1
      ).slice(0, 6).map((p) => ({
        text: p.name,
        sub: p.stage_label || '',
        run: () => {
          replaceCtx(ctx, '@' + p.name + ' ');
          setProject(p).catch(() => {});
        },
      }));
    } else {
      items = STAGES.filter((s) => !ctx.frag || s.label.indexOf(ctx.frag) === 0).map((s) => ({
        text: s.label,
        sub: '',
        dot: 'k-stage',
        run: () => replaceCtx(ctx, '#' + s.label + ' '),
      }));
    }
    S.suggest = { open: items.length > 0, items, idx: 0, kind: ctx.kind };
    renderSuggest();
    suggestBox.hidden = !S.suggest.open;
    setHint();
  }

  function renderSuggest() {
    suggestBox.innerHTML = (S.suggest.items || []).map((it, i) =>
      '<div class="cap-srow' + (i === S.suggest.idx ? ' on' : '') + '" data-i="' + i + '">'
      + (it.dot ? '<i class="k ' + it.dot + '"></i>' : '')
      + '<span class="nm">' + esc(it.text) + '</span>'
      + (it.sub ? '<span class="st">' + esc(it.sub) + '</span>' : '')
      + '</div>'
    ).join('');
  }

  function closeSuggest() {
    S.suggest.open = false;
    suggestBox.hidden = true;
    suggestBox.innerHTML = '';
    setHint();
  }

  function moveSuggest(delta) {
    const n = S.suggest.items.length;
    if (!n) return;
    S.suggest.idx = (S.suggest.idx + delta + n) % n;
    renderSuggest();
  }

  function applySuggest() {
    const it = S.suggest.items[S.suggest.idx];
    if (it) it.run();
  }

  function replaceCtx(ctx, text) {
    let v = input.value.slice(0, ctx.start) + input.value.slice(ctx.start + 1 + ctx.frag.length);
    if (ctx.kind === 'stage') {
      v = v.replace(/#(需求调研|方案编写|POC 验证|招投标)\s*/g, '');
    }
    v = v.replace(/\s+$/, '');
    input.value = (v ? v + ' ' : '') + text;
    closeSuggest();
    renderInput();
    input.focus();
    try { localStorage.setItem(DRAFT_KEY, input.value); } catch (e) { /* ignore */ }
  }

  /* ------------------------------------------------------------ 提交 */
  function parseStage(text) {
    const m = /#(需求调研|方案编写|POC 验证|招投标)/.exec(text);
    return m ? (STAGE_KEYS[m[1]] || '') : '';
  }

  function stripTokens(text) {
    return text
      .replace(/#(需求调研|方案编写|POC 验证|招投标)/g, '')
      .replace(/@[^\s@#!~+，。；：]+/g, '')
      .replace(/\s+/g, ' ')
      .trim();
  }

  function projectFromToken(text) {
    const m = /@([^\s@#!~+，。；：]+)/.exec(text);
    if (!m) return null;
    const frag = m[1];
    return S.projects.find((p) => p.name === frag)
      || S.projects.find((p) => p.name.indexOf(frag) === 0)
      || null;
  }

  async function submit() {
    if (S.saving) return;
    const v = input.value.trim();
    if (!v) return;
    if (S.mode === 'new') { await createProject(v); return; }
    await createTask(v);
  }

  async function createTask(raw) {
    if (!S.project) { toastMsg('先新建一个项目', false); return; }
    const title = stripTokens(raw);
    if (!title) return;
    const target = projectFromToken(raw) || S.project;
    const stage = parseStage(raw) || target.stage || 'research';
    S.saving = true;
    try {
      const task = await TT.api('/api/tasks', {
        method: 'POST',
        body: {
          project_id: target.id,
          title,
          stage,
          status: 'todo',
          source: 'floating',
        },
      });
      S.lastCreated = { type: 'task', id: task.id, title: task.title };
      if (target.id !== S.project.id) {
        await setProject(target);
      } else {
        await loadTasks();
      }
      input.value = '';
      try { localStorage.removeItem(DRAFT_KEY); } catch (e) { /* ignore */ }
      renderInput();
      toastMsg('已记待办「' + task.title + '」', true);
    } catch (e) {
      toastMsg(e.message || '记录失败', false);
    } finally {
      S.saving = false;
    }
  }

  function parseProjectInput(raw) {
    const body = raw.replace(/^\+/, '').trim();
    const customer = /@([^\s@#!~+，。；：]+)/.exec(body);
    const stage = /\/(需求调研|方案编写|POC 验证|POC|招投标)/.exec(body);
    const name = body
      .replace(/@[^\s@#!~+，。；：]+/g, '')
      .replace(/\/(需求调研|方案编写|POC 验证|POC|招投标)/g, '')
      .replace(/\s+/g, ' ')
      .trim();
    return { name, customer: customer ? customer[1] : '', stage: stage ? (STAGE_KEYS[stage[1]] || 'research') : 'research' };
  }

  async function createProject(raw) {
    const fields = parseProjectInput(raw);
    if (!fields.name) { toastMsg('先写项目名称', false); return; }
    S.saving = true;
    try {
      const project = await TT.api('/api/projects', { method: 'POST', body: fields });
      S.lastCreated = { type: 'project', id: project.id, name: project.name };
      input.value = '';
      try { localStorage.removeItem(DRAFT_KEY); } catch (e) { /* ignore */ }
      setMode('record');
      renderInput();
      await loadProjects();
      await setProject(S.projects.find((p) => p.id === project.id) || project);
      toastMsg('已创建「' + project.name + '」', true);
    } catch (e) {
      toastMsg(e.message || '创建失败', false);
    } finally {
      S.saving = false;
    }
  }

  async function undo() {
    const last = S.lastCreated;
    if (!last) return;
    S.lastCreated = null;
    try {
      if (last.type === 'task') {
        await TT.api('/api/tasks/' + encodeURIComponent(last.id), { method: 'DELETE' });
        await loadTasks();
        toastMsg('已撤销', false);
      } else if (last.type === 'project') {
        await TT.api('/api/projects/' + encodeURIComponent(last.id), { method: 'DELETE' });
        await loadProjects();
        pickProject();
        renderProject();
        await loadTasks();
        toastMsg('已撤销项目', false);
      }
    } catch (e) {
      toastMsg(e.message || '撤销失败', false);
    }
    toast.hidden = true;
  }

  /* ------------------------------------------------------------ 拖动窗口 */
  // 不走 WM_NCLBUTTONDOWN 的模态循环（WebView2 下会吞消息，点击也一起坏），
  // 改成 mousedown 记起点、mousemove 发一次 SetWindowPos（16ms 节流）。
  const IGNORE_DRAG = '.cap-wbtn, .cap-newbtn, .cap-link, #input, .cap-srow, #settings';
  const DPR = window.devicePixelRatio || 1;

  function bindDrag(el, onClick) {
    if (!el) return;
    let start = null;
    let moved = false;
    let pending = null;
    let timer = null;

    function flush() {
      timer = null;
      if (!pending || !S.window) return;
      const { x, y } = pending;
      pending = null;
      S.window.x = x;
      S.window.y = y;
      TT.api('/api/capture/window', { method: 'POST', body: { action: 'move', x, y } }).catch(() => {});
    }

    function queue(x, y) {
      pending = { x, y };
      if (!timer) timer = setTimeout(flush, 16);
    }

    function onMove(e) {
      if (!start) return;
      const dx = e.screenX - start.sx;
      const dy = e.screenY - start.sy;
      if (!moved && Math.abs(dx) + Math.abs(dy) < 5) return;
      moved = true;
      queue(Math.round(start.wx + dx * DPR), Math.round(start.wy + dy * DPR));
    }

    function onUp() {
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseup', onUp);
      const wasClick = start && !moved;
      start = null;
      if (wasClick && onClick) onClick();
    }

    function onDown(e) {
      if (e.button !== 0) return;
      if (e.target.closest(IGNORE_DRAG)) return;
      if (!S.window) return;
      e.preventDefault();
      start = { sx: e.screenX, sy: e.screenY, wx: S.window.x, wy: S.window.y };
      moved = false;
      document.addEventListener('mousemove', onMove);
      document.addEventListener('mouseup', onUp);
    }

    el.addEventListener('mousedown', onDown);
  }

  /* ------------------------------------------------------------ 收起 / 展开 */
  function isCollapsed() {
    return document.body.classList.contains('is-collapsed');
  }

  async function collapseToPill() {
    try {
      await TT.api('/api/capture/window', { method: 'POST', body: { action: 'collapse' } });
      document.body.classList.add('is-collapsed');
    } catch (e) {
      toastMsg(e.message || '收起失败', false);
    }
  }

  async function expandFromPill() {
    try {
      await TT.api('/api/capture/window', { method: 'POST', body: { action: 'expand' } });
    } catch (e) {
      toastMsg(e.message || '展开失败', false);
    }
    document.body.classList.remove('is-collapsed');
    setTimeout(() => input.focus(), 60);
  }

  let stateTimer = null;
  function startStatePoll() {
    if (!IS_SHELL || stateTimer) return;
    stateTimer = setInterval(async () => {
      try {
        const data = await TT.api('/api/capture/state');
        S.window = data;
        if (!!data.collapsed !== isCollapsed()) {
          document.body.classList.toggle('is-collapsed', !!data.collapsed);
        }
      } catch (e) { /* 服务短暂不可用时忽略 */ }
    }, 800);
  }

  /* ------------------------------------------------------------ 事件 */
  input.addEventListener('compositionstart', () => { S.composing = true; });
  input.addEventListener('compositionend', () => { S.composing = false; renderInput(); });

  input.addEventListener('input', () => {
    renderInput();
    try { localStorage.setItem(DRAFT_KEY, input.value); } catch (e) { /* ignore */ }
    const plus = input.value.charAt(0) === '+';
    if (plus && S.mode !== 'new') setMode('new');
    if (!plus && S.mode === 'new') setMode('record');
    openSuggest();
  });

  input.addEventListener('keydown', (e) => {
    if (e.isComposing) return;

    if (e.key === 'Backspace' && input.selectionStart === input.selectionEnd) {
      const head = input.value.slice(0, input.selectionStart);
      const mt = /#(?:需求调研|方案编写|POC 验证|招投标)\s?$/.exec(head);
      if (mt) {
        e.preventDefault();
        input.value = head.slice(0, mt.index) + input.value.slice(input.selectionEnd);
        const caret = mt.index;
        renderInput();
        closeSuggest();
        input.setSelectionRange(caret, caret);
        return;
      }
    }

    if (e.key === 'Escape') {
      e.preventDefault();
      if (S.suggest.open) { closeSuggest(); return; }
      if (S.mode === 'new') { input.value = ''; setMode('record'); renderInput(); return; }
      if (IS_SHELL) collapseToPill();
      return;
    }

    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      if (S.suggest.open) { applySuggest(); return; }
      submit();
      return;
    }

    if (S.suggest.open) {
      if (e.key === 'ArrowDown') { e.preventDefault(); moveSuggest(1); }
      if (e.key === 'ArrowUp') { e.preventDefault(); moveSuggest(-1); }
    }

    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'z') {
      if (input.value.trim()) return;
      e.preventDefault();
      undo();
    }
  });

  suggestBox.addEventListener('click', (e) => {
    const row = e.target.closest('.cap-srow');
    if (!row) return;
    S.suggest.idx = Number(row.dataset.i);
    applySuggest();
  });

  $('btnSave').addEventListener('click', () => submit());
  $('btnNew').addEventListener('click', () => {
    setMode('new');
    input.value = '+ ';
    input.focus();
    renderInput();
    input.setSelectionRange(2, 2);
  });
  $('toastUndo').addEventListener('click', () => undo());

  bindDrag(document.querySelector('.cap-head'));
  bindDrag($('pill'), () => expandFromPill());

  // 浮窗（?shell=1）：最小化 / 设置 / 关闭 走本地 HTTP
  if (IS_SHELL) {
    document.body.classList.add('is-shell');
    $('winBtns').hidden = false;
    $('btnMin').onclick = () => collapseToPill();
    $('btnClose').onclick = () => {
      TT.api('/api/capture/window', { method: 'POST', body: { action: 'close' } }).catch(() => {});
    };
    $('btnSet').onclick = (e) => {
      e.stopPropagation();
      const box = $('settings');
      box.hidden = !box.hidden;
      if (!box.hidden) {
        TT.api('/api/capture/autostart')
          .then((data) => { $('autostart').checked = !!(data && data.enabled); })
          .catch(() => {});
      }
    };
    $('autostart').onchange = async (e) => {
      try {
        const data = await TT.api('/api/capture/autostart', {
          method: 'PUT',
          body: { enabled: e.target.checked },
        });
        e.target.checked = !!(data && data.enabled);
      } catch (err) {
        e.target.checked = !e.target.checked;
        toastMsg(err.message || '开机自启设置失败', false);
      }
    };
    document.addEventListener('click', (e) => {
      const box = $('settings');
      if (box.hidden) return;
      if (e.target.closest('#settings') || e.target.closest('#btnSet')) return;
      box.hidden = true;
    });
    startStatePoll();
  }

  /* ------------------------------------------------------------ 启动 */
  (async function init() {
    try {
      await loadProjects();
    } catch (e) {
      toastMsg('项目加载失败：' + e.message, false);
    }
    pickProject();
    renderProject();
    await loadTasks();

    const prefill = new URLSearchParams(location.search).get('t');
    let initial = prefill;
    if (!initial) {
      try { initial = localStorage.getItem(DRAFT_KEY) || ''; } catch (e) { initial = ''; }
    }
    if (initial) {
      input.value = initial;
      if (initial.charAt(0) === '+') setMode('new');
      renderInput();
      openSuggest();
    }
    setHint();
    setTimeout(() => input.focus(), 80);
  })();
})();
