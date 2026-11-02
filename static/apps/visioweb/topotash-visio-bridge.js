/* TopoTash 拓扑编辑器桥接。
 * 将画布持久化到 SQLite，并增加节点级「待跟进 / 关联任务」控件。
 * 内置编辑器本身的交互保持不变。 */
(function () {
  'use strict';
  const ctx = window.TOPOTASH_CTX;
  if (!ctx) return;

  const PID = ctx.projectId;
  const DID = ctx.diagramId;
  const BASE = `/api/diagrams/${encodeURIComponent(DID)}`;
  const STATUS_COLOR = { todo: '#d97706', doing: '#2563eb', done: '#0d9488', none: '#94a3b8' };
  const STATUS_TEXT = { todo: '待跟进', doing: '进行中', done: '已完成', none: '未标记' };
  const STATUS_CLASS = { todo: 'todo', doing: 'doing', done: 'done', none: 'none' };

  let booted = false;
  let saving = false;
  let pending = false;
  let saveTimer = null;
  let project = { projectId: PID, diagramId: DID, diagramName: '拓扑图', stage: 'research' };
  let tasks = [];
  let tasksLoading = false;

  function esc(value) {
    return String(value == null ? '' : value).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  }

  async function api(path, options) {
    const opts = Object.assign({ headers: {} }, options || {});
    if (opts.body && typeof opts.body !== 'string') {
      opts.headers['Content-Type'] = 'application/json';
      opts.body = JSON.stringify(opts.body);
    }
    const res = await fetch(path, opts);
    const raw = await res.text();
    let data = null;
    try { data = raw ? JSON.parse(raw) : null; } catch (e) { data = null; }
    if (!res.ok) throw new Error((data && data.error && data.error.message) || raw || ('HTTP ' + res.status));
    return data;
  }

  function post(type, payload) {
    if (window.parent && window.parent !== window) {
      window.parent.postMessage(Object.assign({ type }, payload || {}), '*');
    }
  }

  function hint(text) {
    const el = document.getElementById('statusHint');
    if (el) el.textContent = text;
  }

  // ------------------------------------------------------------ load / save
  function applyDocument(data) {
    model.shapes = data.shapes || {};
    model.order = data.order || Object.keys(model.shapes);
    model.groups = data.groups || {};
    model.imagePool = data.imagePool || {};
    if (typeof imagePoolMigrate === 'function') imagePoolMigrate();
    if (typeof cleanupGroups === 'function') cleanupGroups();
    if (typeof normalizeShapes === 'function') normalizeShapes();
    state.idc = 0;
    for (const id of Object.keys(model.shapes)) {
      const n = parseInt(String(id).replace(/\D/g, '')) || 0;
      if (n > state.idc) state.idc = n;
    }
    state.sel.clear();
    state.primaryId = null;
    state.history = [];
    state.hIndex = -1;
    state.dirty = false;
    commit();
    state.dirty = false;
    if (typeof fitContent === 'function') fitContent();
    syncProps();
    syncDocTitle();
  }

  async function load() {
    try {
      const data = await api(`${BASE}/content`);
      project = data._topotash || project;
      state.docName = project.diagramName || '拓扑图';
      applyDocument(data);
      document.title = (project.diagramName || '拓扑图') + ' · TopoTash 拓事';
      hint(`TopoTash · ${project.projectName || ''} · 画布自动保存`);
      booted = true;
      render();
      syncProps();
      loadTasks();
      if (ctx.node) selectNode(ctx.node);
      post('topotash:visio-ready', { diagramId: DID });
    } catch (e) {
      hint('加载失败：' + e.message);
      if (typeof showToast === 'function') showToast('加载拓扑图失败：' + e.message, 'error');
      post('topotash:visio-error', { message: e.message });
    }
  }

  function scheduleServerSave(delay) {
    if (!booted) return;
    clearTimeout(saveTimer);
    saveTimer = setTimeout(() => saveToServer(false), delay == null ? 900 : delay);
  }

  async function saveToServer(manual) {
    if (!booted) return;
    if (saving) { pending = true; return; }
    saving = true;
    pending = false;
    post('topotash:visio-saving');
    try {
      const res = await api(`${BASE}/content`, {
        method: 'PUT',
        body: {
          content: {
            app: 'topotash', version: 2,
            shapes: model.shapes, order: model.order,
            groups: model.groups, imagePool: model.imagePool
          }
        }
      });
      state.dirty = false;
      syncDocTitle();
      hint(`已保存 · ${res.node_count} 个节点 · ${new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}`);
      post('topotash:visio-saved', { nodeCount: res.node_count, version: res.version });
      if (manual && typeof showToast === 'function') showToast('已保存到 TopoTash', 'success');
    } catch (e) {
      hint('保存失败：' + e.message);
      if (typeof showToast === 'function') showToast('保存失败：' + e.message, 'error');
      post('topotash:visio-error', { message: e.message });
    } finally {
      saving = false;
      if (pending) { pending = false; scheduleServerSave(150); }
    }
  }

  // Replace the local download-based save with a server save.
  window.saveDoc = function () { saveToServer(true); };
  // The local draft is per-browser; in TopoTash the server is the source of truth.
  window.scheduleAutosave = function () {};

  const origCommit = window.commit;
  window.commit = function () {
    origCommit.apply(window, arguments);
    scheduleServerSave();
  };

  // ----------------------------------------------------------- node badges
  function shapeTt(shape) {
    if (!shape.tt) shape.tt = { status: 'none', tasks: [], nodeKey: shape.id };
    if (!Array.isArray(shape.tt.tasks)) shape.tt.tasks = [];
    return shape.tt;
  }

  function primaryTask(tt) {
    return tt.tasks.find(t => t.primary) || tt.tasks[0] || null;
  }

  function decorateBadges() {
    for (const id of model.order) {
      const shape = model.shapes[id];
      if (!shape || shape.type !== 'shape' || !shape.tt || shape.tt.status === 'none') continue;
      const g = document.getElementById('shp-' + id);
      if (!g) continue;
      const tt = shape.tt;
      const color = STATUS_COLOR[tt.status] || STATUS_COLOR.todo;
      const task = primaryTask(tt);
      const badge = document.createElementNS(SVGNS, 'g');
      badge.setAttribute('class', 'tt-followup-badge');
      badge.setAttribute('data-node', id);
      badge.setAttribute('transform', `translate(${shape.x + shape.w - 12} ${shape.y + 12})`);
      badge.innerHTML = `<circle r="9.5" fill="${color}" stroke="#ffffff" stroke-width="2"></circle>`
        + `<path d="M-1.5 -4.5v9M-1.5 -4.5h5.2l-1.3 2.1 1.3 2.1h-5.2" fill="none" stroke="#ffffff" stroke-width="1.4" stroke-linejoin="round" stroke-linecap="round" pointer-events="none"></path>`;
      const title = document.createElementNS(SVGNS, 'title');
      title.textContent = `${STATUS_TEXT[tt.status] || '待跟进'}${task ? '：' + task.title : '（点击标记/创建任务）'}`;
      badge.appendChild(title);
      g.appendChild(badge);
    }
  }

  const origRender = window.render;
  window.render = function () {
    origRender.apply(window, arguments);
    decorateBadges();
  };

  // Clicking a badge jumps to its task, or selects the node for linking.
  document.getElementById('shapesLayer').addEventListener('click', function (e) {
    const badge = e.target && e.target.closest ? e.target.closest('.tt-followup-badge') : null;
    if (!badge) return;
    e.stopPropagation();
    e.preventDefault();
    const id = badge.getAttribute('data-node');
    const shape = model.shapes[id];
    if (!shape) return;
    const task = primaryTask(shapeTt(shape));
    if (task) openTask(task.id);
    else selectNode(id);
  }, true);

  function selectNode(id) {
    if (!model.shapes[id]) return;
    selectOnly(id);
    render();
    syncProps();
    const s = model.shapes[id];
    const host = document.getElementById('canvasHost');
    if (host) {
      state.zoom = 1;
      state.pan.x = s.x + s.w / 2 - host.clientWidth / 2;
      state.pan.y = s.y + s.h / 2 - host.clientHeight / 2;
      if (typeof updateView === 'function') updateView();
    }
  }

  function openTask(taskId) {
    post('topotash:open-task', { taskId });
    if (window.parent === window) {
      location.href = `/projects/${PID}?tab=tasks&task=${encodeURIComponent(taskId)}`;
    }
  }

  // ------------------------------------------------------------ task panel
  async function loadTasks() {
    if (tasksLoading) return;
    tasksLoading = true;
    try {
      const data = await api(`/api/tasks?project_id=${encodeURIComponent(PID)}&limit=500`);
      tasks = data.items || [];
    } catch (e) { /* panel shows a hint */ }
    tasksLoading = false;
    decorateFollowupPanel();
  }

  function applyNode(node) {
    const shape = model.shapes[node.node_key];
    if (!shape) return;
    shape.tt = {
      status: node.followup_status,
      label: node.label,
      nodeKey: node.node_key,
      tasks: (node.linked_tasks || []).map(t => ({
        id: t.task_id, title: t.title, status: t.status, primary: !!t.is_primary
      }))
    };
  }

  async function nodeAction(body) {
    const shape = selShapes()[0];
    if (!shape) return;
    try {
      const res = await api(`${BASE}/nodes/${encodeURIComponent(shape.id)}/followup`, { method: 'POST', body });
      applyNode(res.node);
      if (res.task) {
        const known = tasks.some(t => t.id === res.task.id);
        if (!known) tasks.push({ id: res.task.id, title: res.task.title, status: res.task.status });
      }
      render();
      syncProps();
      post('topotash:project-changed');
      if (typeof showToast === 'function') showToast('节点跟进已更新', 'success');
    } catch (e) {
      if (typeof showToast === 'function') showToast(e.message, 'error');
    }
  }

  function decorateFollowupPanel() {
    const box = document.getElementById('propContent');
    if (!box) return;
    const shapes = (typeof selShapes === 'function') ? selShapes() : [];
    if (shapes.length !== 1) return;
    const shape = shapes[0];
    if (!shape || shape.type !== 'shape') return;
    const stale = box.querySelector('.tt-followup-sec');
    if (stale) stale.remove();

    const tt = shapeTt(shape);
    const task = primaryTask(tt);
    const linkedIds = new Set(tt.tasks.map(t => t.id));
    const options = tasks.filter(t => !linkedIds.has(t.id))
      .map(t => `<option value="${esc(t.id)}">${esc(t.title)}</option>`).join('');

    const sec = document.createElement('div');
    sec.className = 'prop-sec tt-followup-sec';
    sec.innerHTML = `
      <h4>TopoTash 跟进 <span class="tt-sec-state ${STATUS_CLASS[tt.status] || 'none'}">${STATUS_TEXT[tt.status] || '未标记'}</span></h4>
      <div class="tt-status-row">
        <button type="button" data-status="todo" class="${tt.status === 'todo' ? 'on todo' : ''}">待跟进</button>
        <button type="button" data-status="doing" class="${tt.status === 'doing' ? 'on doing' : ''}">进行中</button>
        <button type="button" data-status="done" class="${tt.status === 'done' ? 'on done' : ''}">已完成</button>
        <button type="button" data-status="none" class="${tt.status === 'none' ? 'on' : ''}">清除</button>
      </div>
      ${task
        ? `<div class="tt-linked-task"><span title="${esc(task.title)}">${esc(task.title)}</span><button type="button" data-open>打开任务</button><button type="button" data-unlink="${esc(task.id)}">取消</button></div>`
        : `<div class="tt-empty-task">尚未关联任务，标记后可创建或选择任务。</div>`}
      <div class="tt-task-actions">
        <select class="tt-select" data-link-task>
          <option value="">${tasksLoading ? '任务加载中…' : '关联已有任务…'}</option>
          ${options}
        </select>
        ${!task ? `<div class="tt-create-row"><input data-task-title value="跟进：${esc((shape.text || '节点').split('\n')[0])}"><button type="button" data-create>创建任务</button></div>` : ''}
      </div>
      <div class="tt-note">节点标记会出现在项目「关联视图」；任务也可在任务台里查看。</div>`;

    box.insertBefore(sec, box.firstChild);
    sec.querySelectorAll('[data-status]').forEach(btn => {
      btn.onclick = () => nodeAction({ status: btn.dataset.status });
    });
    const openBtn = sec.querySelector('[data-open]');
    if (openBtn && task) openBtn.onclick = () => openTask(task.id);
    const unlinkBtn = sec.querySelector('[data-unlink]');
    if (unlinkBtn && task) unlinkBtn.onclick = async () => {
      try {
        const node = await api(`${BASE}/nodes/${encodeURIComponent(shape.id)}/links/${encodeURIComponent(task.id)}`, { method: 'DELETE' });
        applyNode(node);
        render(); syncProps();
        post('topotash:project-changed');
      } catch (e) { if (typeof showToast === 'function') showToast(e.message, 'error'); }
    };
    const sel = sec.querySelector('[data-link-task]');
    if (sel) sel.onchange = () => { if (sel.value) nodeAction({ task_id: sel.value }); };
    const createBtn = sec.querySelector('[data-create]');
    if (createBtn) createBtn.onclick = () => {
      const input = sec.querySelector('[data-task-title]');
      const title = (input && input.value.trim()) || `跟进：${(shape.text || '节点').split('\n')[0]}`;
      nodeAction({ create_task: { title, priority: 1, stage: project.stage || 'research' } });
    };
  }

  const origSyncProps = window.syncProps;
  window.syncProps = function () {
    origSyncProps.apply(window, arguments);
    decorateFollowupPanel();
  };

  // Keep title in sync with the diagram name.
  state.docName = project.diagramName;
  load();
})();
