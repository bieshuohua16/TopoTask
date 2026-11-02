/* TopoTash 任务台桥接。
 * 保留内置任务台的完整 UI，把本地文件存储替换为项目级 TopoTash API。
 * 在主应用脚本之后加载。 */
(function () {
  'use strict';
  const params = new URLSearchParams(location.search);
  const PROJECT_ID = params.get('project_id');
  if (!PROJECT_ID) return;
  window.TOPOTASH_CTX = { projectId: PROJECT_ID, embed: params.get('embed') === '1' };

  const ESC = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
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

  let booted = false;
  let saving = false;
  let pending = false;
  let knownIds = new Set();
  let syncState = { state: 'ok', text: 'TopoTash 已连接' };
  let taskDiagrams = {};
  let allDiagrams = [];
  let projectMeta = null;
  let saveTimer = null;

  function setSync(state, text) {
    syncState = { state, text };
    paintSync();
  }

  function paintSync() {
    const bar = document.getElementById('statusbar');
    if (!bar) return;
    let el = bar.querySelector('.tt-sync-state');
    if (!el) {
      el = document.createElement('span');
      el.className = 'tt-sync-state';
      bar.appendChild(el);
    }
    el.className = 'tt-sync-state ' + (syncState.state === 'saving' ? 'saving' : syncState.state === 'error' ? 'error' : '');
    el.textContent = syncState.text;
    el.title = '数据保存在 TopoTash SQLite（项目级）';
  }

  // ------------------------------------------------------------------ boot
  async function ttBoot() {
    try {
      const state = await api('/api/projects/' + encodeURIComponent(PROJECT_ID) + '/todo-state');
      projectMeta = state.topotash || {};
      window.TT_DEFAULT_STAGE = (projectMeta.stage || 'research');
      store = state;
      ensureAIFields();
      currentFileHandle = null;
      currentFileName = projectMeta.projectName || 'TopoTash';
      knownIds = new Set(store.tasks.map(t => t.id));
      currentFilter = 'all';
      hideWelcome();
      renderAll();
      updateAIStatus();
      updateFileIndicator();
      booted = true;
      setSync('ok', 'TopoTash 已连接');
      await loadDiagrams();
      const focus = params.get('task');
      if (focus && store.tasks.some(t => t.id === focus)) {
        selectedTaskId = focus;
        currentFilter = 'all';
        renderAll();
        setTimeout(() => {
          const dp = document.getElementById('detailPanel');
          if (dp) dp.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        }, 150);
      }
      parent.postMessage({ type: 'topotash:todo-ready' }, '*');
      parent.postMessage({ type: 'topotash:toast', message: '任务台已加载', level: 'success' }, '*');
    } catch (e) {
      const desc = document.getElementById('welcomeDesc');
      if (desc) desc.textContent = '加载项目任务失败：' + e.message;
      const wc = document.getElementById('welcomeContent');
      if (wc) wc.innerHTML = '<div class="welcome-actions"><button class="welcome-btn welcome-btn-primary" onclick="location.reload()">重试</button></div>';
      showWelcome();
      setSync('error', '加载失败');
    }
  }
  window.ttBoot = ttBoot;

  async function loadDiagrams() {
    const [d, links] = await Promise.all([
      api('/api/diagrams?project_id=' + encodeURIComponent(PROJECT_ID)),
      api('/api/views/links?project_id=' + encodeURIComponent(PROJECT_ID))
    ]);
    allDiagrams = d.items || [];
    taskDiagrams = {};
    (links.task_links || []).forEach(l => {
      (taskDiagrams[l.task_id] = taskDiagrams[l.task_id] || []).push({ id: l.diagram_id, name: l.diagram_name });
    });
    if (selectedTaskId) renderDetailPanel();
  }

  // --------------------------------------------------------------- saving
  function buildPayload() {
    return {
      version: '2.0',
      projects: (store.projects || []).map(p => ({ id: p.id, name: p.name, color: p.color, createdAt: p.createdAt })),
      tags: store.tags || [],
      tasks: (store.tasks || []).map(t => ({
        id: t.id, title: t.title, description: t.description || '',
        priority: t.priority, status: t.status,
        stage: t.stage || window.TT_DEFAULT_STAGE || 'research',
        dueDate: t.dueDate || null, recur: t.recur || null, recurDay: t.recurDay == null ? null : t.recurDay,
        projectId: t.projectId || null,
        tags: t.tags || [],
        subtasks: (t.subtasks || []).map(s => ({ id: s.id, title: s.title, completed: !!s.completed })),
        order: t.order == null ? 0 : t.order,
        createdAt: t.createdAt, updatedAt: t.updatedAt
      })),
      aiConfig: store.aiConfig || {},
      aiChatHistory: store.aiChatHistory || [],
      deleted_task_ids: [...knownIds].filter(id => !(store.tasks || []).some(t => t.id === id))
    };
  }

  function scheduleSync(delay) {
    if (!booted) return;
    clearTimeout(saveTimer);
    saveTimer = setTimeout(doSync, delay == null ? 650 : delay);
  }

  async function doSync() {
    if (!booted) return;
    if (saving) { pending = true; return; }
    saving = true;
    pending = false;
    setSync('saving', '同步中…');
    try {
      await api('/api/projects/' + encodeURIComponent(PROJECT_ID) + '/todo-state', {
        method: 'PUT', body: buildPayload()
      });
      knownIds = new Set((store.tasks || []).map(t => t.id));
      setSync('ok', '已同步 ' + new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }));
      parent.postMessage({ type: 'topotash:project-changed' }, '*');
    } catch (e) {
      setSync('error', '同步失败');
      if (typeof toast === 'function') toast('保存到 TopoTash 失败：' + e.message);
      parent.postMessage({ type: 'topotash:toast', message: '同步失败：' + e.message, level: 'error' }, '*');
    } finally {
      saving = false;
      if (pending) { pending = false; scheduleSync(120); }
    }
  }

  // Override the local save path (file handle / localStorage) with API sync.
  const origSaveStore = window.saveStore;
  window.saveStore = function () {
    try { if (origSaveStore) origSaveStore.apply(window, arguments); } catch (e) { /* ignore */ }
    scheduleSync();
  };

  // ----------------------------------------------------- detail panel extras
  function decorateDetail() {
    const dp = document.getElementById('detailPanel');
    if (!dp || dp.classList.contains('collapsed') || !selectedTaskId) return;
    const task = (store.tasks || []).find(t => t.id === selectedTaskId);
    if (!task) return;
    const anchor = dp.querySelector('.det-ts');
    if (!anchor) return;
    const linked = taskDiagrams[task.id] || [];
    const linkedIds = new Set(linked.map(d => d.id));
    const options = allDiagrams.filter(d => !linkedIds.has(d.id))
      .map(d => `<option value="${ESC(d.id)}">${ESC(d.name)}</option>`).join('');
    const block = document.createElement('div');
    block.className = 'det-field tt-diagram-field';
    block.innerHTML = `
      <div class="det-label">关联拓扑图</div>
      <div class="tt-chips">
        ${linked.length ? linked.map(d => `<span class="tt-diagram-chip"><span>${ESC(d.name)}</span><b title="取消关联" data-unlink="${ESC(d.id)}">×</b></span>`).join('') : '<span class="tt-diagram-empty">尚未关联拓扑图</span>'}
      </div>
      ${options ? `<select class="det-select" data-tt-add-diagram><option value="">+ 关联一张拓扑图…</option>${options}</select>` : (allDiagrams.length ? '<div class="tt-hint">已关联本项目全部拓扑图</div>' : '<div class="tt-hint">本项目还没有拓扑图</div>')}
      ${task.source === 'diagram' ? '<div class="tt-node-origin">来自拓扑图节点跟进</div>' : ''}
      <div class="tt-hint">在拓扑图里选中节点，可标记「待跟进」并直接创建任务。</div>`;
    anchor.parentNode.insertBefore(block, anchor);
    block.querySelectorAll('[data-unlink]').forEach(btn => {
      btn.onclick = async () => {
        try {
          await api(`/api/tasks/${encodeURIComponent(task.id)}/diagrams/${encodeURIComponent(btn.dataset.unlink)}`, { method: 'DELETE' });
          taskDiagrams[task.id] = (taskDiagrams[task.id] || []).filter(d => d.id !== btn.dataset.unlink);
          if (typeof toast === 'function') toast('已取消拓扑图关联');
          renderDetailPanel();
        } catch (e) { if (typeof toast === 'function') toast(e.message); }
      };
    });
    const sel = block.querySelector('[data-tt-add-diagram]');
    if (sel) sel.onchange = async () => {
      if (!sel.value) return;
      try {
        const d = allDiagrams.find(x => x.id === sel.value);
        await api(`/api/tasks/${encodeURIComponent(task.id)}/diagrams`, { method: 'POST', body: { diagram_id: sel.value } });
        (taskDiagrams[task.id] = taskDiagrams[task.id] || []).push({ id: sel.value, name: d ? d.name : '' });
        if (typeof toast === 'function') toast('已关联拓扑图');
        renderDetailPanel();
      } catch (e) { if (typeof toast === 'function') toast(e.message); }
    };
  }
  const origRenderDetailPanel = window.renderDetailPanel;
  window.renderDetailPanel = function () {
    origRenderDetailPanel.apply(window, arguments);
    decorateDetail();
  };

  // Status bar is rebuilt by the app; repaint our sync badge after it.
  const origRenderStatusbar = window.renderStatusbar;
  window.renderStatusbar = function () {
    origRenderStatusbar.apply(window, arguments);
    paintSync();
  };

  // 内置状态栏默认用于切换本地 JSON 文件；在 TopoTash 中项目就是数据边界。
  window.switchDataFile = function () {
    if (typeof toast === 'function') toast('任务数据由 TopoTash 按项目管理，无需切换文件');
  };

  const origRenderSidebar = window.renderSidebar;
  window.renderSidebar = function () {
    origRenderSidebar.apply(window, arguments);
    const logo = document.querySelector('.sidebar-logo .logo-text');
    if (logo) logo.textContent = 'TopoTash · 任务';
  };

  // Task focused from another TopoTash view.
  window.addEventListener('message', function (ev) {
    const msg = ev.data || {};
    if (msg.type === 'topotash:focus-task' && msg.taskId) {
      if (!(store.tasks || []).some(t => t.id === msg.taskId)) return;
      selectedTaskId = msg.taskId;
      currentFilter = 'all';
      renderAll();
      const dp = document.getElementById('detailPanel');
      if (dp) dp.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
  });
})();
