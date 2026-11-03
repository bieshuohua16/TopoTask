/* TopoTash native task workspace (replaces the embedded TodoFlow view) */
(function () {
  'use strict';
  const TT = window.TT;
  const CFG = window.TT_CONFIG || {};
  const STAGES = CFG.stages || [];
  const PRIORITY_LABELS = ['P0 紧急', 'P1 重要', 'P2 一般', 'P3 低'];
  const STATUS_LABELS = { todo: '待办', doing: '进行中', done: '已完成' };
  const SOURCE_LABELS = { manual: '手动创建', ai: 'AI 助手', diagram: '拓扑节点跟进', import: '导入' };

  let pid = '';
  let project = null;
  let tasks = [];
  let diagrams = [];
  let selectedId = null;
  let detail = null;
  let view = 'list';
  let loadedFor = '';
  let bound = false;
  let search = '';
  let stageFilter = 'all';
  let statusFilter = 'all';
  let seq = 0;
  let didDrag = false;

  const $ = (sel, root) => (root || document).querySelector(sel);
  const $$ = (sel, root) => Array.from((root || document).querySelectorAll(sel));
  const esc = TT.esc;

  function stageLabel(key) { return (CFG.stageLabels || {})[key] || key || ''; }
  function stagePill(key) { return `<span class="stage-pill ${esc(key)}">${esc(stageLabel(key))}</span>`; }
  function dueClass(value, status) {
    return value && status !== 'done' && new Date(value).getTime() < Date.now() ? 'overdue' : '';
  }
  function dueLabel(t) {
    if (!t.due_date) return '无截止';
    if (t.status === 'done') return TT.date(t.due_date);
    return TT.dueText(t.due_date);
  }
  function toLocalInput(value) {
    if (!value) return '';
    const d = new Date(value);
    if (isNaN(d.getTime())) return '';
    const p = n => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`;
  }
  function fromLocalInput(value) {
    if (!value) return null;
    const d = new Date(value);
    return isNaN(d.getTime()) ? null : d.toISOString();
  }
  function sortTasks(a, b) {
    const ad = a.status === 'done', bd = b.status === 'done';
    if (ad !== bd) return ad ? 1 : -1;
    if (a.priority !== b.priority) return a.priority - b.priority;
    if (!a.due_date && !b.due_date) return (a.sort_order || 0) - (b.sort_order || 0);
    if (!a.due_date) return 1;
    if (!b.due_date) return -1;
    return String(a.due_date).localeCompare(String(b.due_date));
  }

  function filtered() {
    const q = search.trim().toLowerCase();
    return tasks.filter(t => {
      if (stageFilter !== 'all' && t.stage !== stageFilter) return false;
      if (statusFilter !== 'all' && t.status !== statusFilter) return false;
      if (!q) return true;
      const hay = [t.title, t.description, (t.tags || []).join(' '), (t.diagrams || []).map(d => d.name).join(' ')]
        .join(' ').toLowerCase();
      return hay.includes(q);
    }).sort(sortTasks);
  }

  // ---------------------------------------------------------------- rendering
  function metaChips(t) {
    const out = [];
    if (t.subtask_total) out.push(`<span class="tt-meta-chip">子任务 ${t.subtask_done}/${t.subtask_total}</span>`);
    if ((t.diagrams || []).length) out.push(`<span class="tt-meta-chip diagram">${TT.icon.diagram}${esc(t.diagrams[0].name)}</span>`);
    if (t.source === 'diagram') out.push('<span class="tt-meta-chip node">节点跟进</span>');
    (t.tags || []).slice(0, 2).forEach(tag => out.push(`<span class="tt-tag-mini">${esc(tag)}</span>`));
    if ((t.tags || []).length > 2) out.push(`<span class="tt-tag-mini">+${t.tags.length - 2}</span>`);
    return out.join('');
  }

  function taskCard(t) {
    const done = t.status === 'done';
    return `
      <article class="tt-task p${t.priority} ${done ? 'is-done' : ''} ${t.id === selectedId ? 'selected' : ''}"
               data-task-id="${esc(t.id)}" role="button" tabindex="0">
        <button class="tt-check ${done ? 'checked' : ''}" data-check title="${done ? '标记为待办' : '标记完成'}" type="button">
          <svg viewBox="0 0 24 24" fill="none"><path d="M20 6L9 17l-5-5"/></svg>
        </button>
        <div class="tt-task-body">
          <div class="tt-task-title">${esc(t.title)}</div>
          <div class="tt-task-meta">
            <span class="tt-prio p${t.priority}">${PRIORITY_LABELS[t.priority] || 'P2'}</span>
            <span class="tt-status ${t.status}">${STATUS_LABELS[t.status] || t.status}</span>
            <span class="tt-due ${dueClass(t.due_date, t.status)}">${dueLabel(t)}</span>
            ${metaChips(t)}
          </div>
        </div>
        <span class="tt-chevron">›</span>
      </article>`;
  }

  function renderList() {
    const pane = $('#taskListPane');
    if (!pane) return;
    const list = filtered();
    if (!tasks.length) {
      pane.innerHTML = `<div class="task-empty"><div class="task-empty-icon">${TT.icon.tasks}</div>
        <h3>还没有任务</h3><p>从新建任务开始，或用拓扑图节点上的「待跟进」自动生成任务。</p>
        <button class="btn btn-primary" id="btnEmptyNewTask">新建第一个任务</button></div>`;
      const b = $('#btnEmptyNewTask'); if (b) b.onclick = newTask;
      return;
    }
    if (!list.length) {
      pane.innerHTML = `<div class="task-empty"><div class="task-empty-icon">${TT.icon.tasks}</div>
        <h3>没有匹配的任务</h3><p>尝试清除筛选条件或换个关键词。</p></div>`;
      return;
    }
    const groups = [];
    STAGES.forEach(s => {
      const items = list.filter(t => t.stage === s.key);
      if (items.length) groups.push({ key: s.key, label: s.label, hint: s.hint, items });
    });
    const other = list.filter(t => !STAGES.some(s => s.key === t.stage));
    if (other.length) groups.push({ key: '', label: '未分阶段', hint: '', items: other });
    pane.innerHTML = groups.map(g => `
      <section class="tt-stage-group">
        <div class="tt-stage-head">
          ${g.key ? stagePill(g.key) : '<span class="stage-pill">未分阶段</span>'}
          <span class="tt-stage-count">${g.items.length} 个任务</span>
          <span class="tt-stage-hint">${esc(g.hint || '')}</span>
        </div>
        <div class="tt-stage-tasks">${g.items.map(taskCard).join('')}</div>
      </section>`).join('');
    bindListEvents();
  }

  function bindListEvents() {
    $$('#taskListPane .tt-task').forEach(card => {
      const id = card.dataset.taskId;
      card.addEventListener('click', (e) => {
        if (e.target.closest('[data-check]')) return;
        openTask(id);
      });
      card.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); openTask(id); }
      });
      const check = card.querySelector('[data-check]');
      if (check) check.addEventListener('click', async (e) => {
        e.stopPropagation();
        const t = tasks.find(x => x.id === id);
        if (!t) return;
        await saveTask(id, { status: t.status === 'done' ? 'todo' : 'done' }, { refreshDetail: true });
      });
    });
  }

  function boardCard(t) {
    const done = t.status === 'done';
    return `
      <article class="tt-board-card p${t.priority} ${done ? 'is-done' : ''}" data-board-task="${esc(t.id)}" draggable="true">
        <div class="ttb-top">
          <span class="tt-prio p${t.priority}">P${t.priority}</span>
          ${stagePill(t.stage)}
        </div>
        <div class="ttb-title">${esc(t.title)}</div>
        <div class="ttb-meta">
          <span class="tt-due ${dueClass(t.due_date, t.status)}">${dueLabel(t)}</span>
          ${(t.tags || []).slice(0, 2).map(tag => `<span class="tt-tag-mini">${esc(tag)}</span>`).join('')}
        </div>
        ${(t.diagrams || []).length ? `<div class="ttb-diagram">${TT.icon.diagram}${esc(t.diagrams[0].name)}</div>` : ''}
      </article>`;
  }

  function renderBoard() {
    const pane = $('#taskBoardPane');
    if (!pane) return;
    const list = filtered();
    const cols = [['todo', '待办'], ['doing', '进行中'], ['done', '已完成']];
    pane.innerHTML = cols.map(([key, label]) => {
      const items = list.filter(t => t.status === key);
      return `
        <section class="tt-board-col" data-status="${key}">
          <div class="tt-board-head"><span class="status-dot ${key}"></span><b>${label}</b><span class="tt-board-count">${items.length}</span></div>
          <div class="tt-board-drop" data-status="${key}">
            ${items.length ? items.map(boardCard).join('') : '<div class="tt-board-empty">拖拽任务到这里</div>'}
          </div>
        </section>`;
    }).join('');
    bindBoard();
  }

  function bindBoard() {
    const pane = $('#taskBoardPane');
    if (!pane) return;
    $$('.tt-board-card', pane).forEach(card => {
      card.addEventListener('click', () => { if (!didDrag) openTask(card.dataset.boardTask); });
      card.addEventListener('dragstart', (e) => {
        didDrag = true;
        e.dataTransfer.setData('text/plain', card.dataset.boardTask);
        e.dataTransfer.effectAllowed = 'move';
        card.classList.add('dragging');
      });
      card.addEventListener('dragend', () => {
        card.classList.remove('dragging');
        setTimeout(() => { didDrag = false; }, 120);
      });
    });
    $$('.tt-board-col', pane).forEach(col => {
      const drop = col.querySelector('.tt-board-drop');
      col.addEventListener('dragover', (e) => { e.preventDefault(); drop.classList.add('drop-over'); });
      col.addEventListener('dragleave', (e) => { if (!col.contains(e.relatedTarget)) drop.classList.remove('drop-over'); });
      col.addEventListener('drop', async (e) => {
        e.preventDefault();
        drop.classList.remove('drop-over');
        const id = e.dataTransfer.getData('text/plain');
        const t = tasks.find(x => x.id === id);
        const next = col.dataset.status;
        setTimeout(() => { didDrag = false; }, 200);
        if (t && next && t.status !== next) await saveTask(id, { status: next }, { refreshDetail: true });
      });
    });
  }

  function renderSummary() {
    const box = $('#taskSummary');
    if (!box) return;
    const open = tasks.filter(t => t.status !== 'done').length;
    const done = tasks.length - open;
    const overdue = tasks.filter(t => t.status !== 'done' && t.due_date && new Date(t.due_date).getTime() < Date.now()).length;
    const list = filtered();
    box.innerHTML = `
      <span>共 <b>${tasks.length}</b> 个任务</span>
      <span>未完成 <b>${open}</b></span>
      <span>已完成 <b>${done}</b></span>
      ${overdue ? `<span class="overdue">已逾期 <b>${overdue}</b></span>` : ''}
      ${list.length !== tasks.length ? `<span class="muted">筛选结果 ${list.length} 条</span>` : ''}
      <span class="tt-summary-hint">${view === 'list' ? '按售前阶段分组' : '拖动卡片更改状态'}</span>`;
  }

  function render() {
    renderSummary();
    renderList();
    renderBoard();
    $('#taskListPane').classList.toggle('hidden', view !== 'list');
    $('#taskBoardPane').classList.toggle('hidden', view !== 'board');
  }

  // ---------------------------------------------------------------- detail
  function renderDetail(t, resetScroll) {
    const drawer = $('#taskDrawer');
    const box = $('#taskDetail');
    if (!drawer || !box) return;
    const scroll = resetScroll ? 0 : drawer.scrollTop;
    const stageOpts = STAGES.map(s => `<option value="${s.key}" ${t.stage === s.key ? 'selected' : ''}>${esc(s.label)}</option>`).join('');
    const tagPool = Array.from(new Set(tasks.flatMap(x => x.tags || []))).sort();
    const linked = t.diagrams || [];
    const linkedIds = new Set(linked.map(d => d.id));
    const diagramOpts = diagrams.filter(d => !linkedIds.has(d.id))
      .map(d => `<option value="${esc(d.id)}">${esc(d.name)}</option>`).join('');
    const subs = t.subtasks || [];
    const subDone = subs.filter(s => s.completed).length;
    const nodeLinks = t.node_links || [];

    box.innerHTML = `
      <div class="ttd-head">
        <div class="ttd-head-main">
          <div class="ttd-eyebrow">任务详情 · ${esc(SOURCE_LABELS[t.source] || t.source || '手动创建')}</div>
          <input class="ttd-title-input" id="ttdTitle" value="${esc(t.title)}" maxlength="200">
        </div>
        <button class="ttd-close" id="ttdClose" type="button" title="关闭">×</button>
      </div>

      <div class="ttd-status-row">
        ${['todo', 'doing', 'done'].map(s => `<button type="button" data-status="${s}" class="${t.status === s ? 'on ' + s : ''}">${STATUS_LABELS[s]}</button>`).join('')}
      </div>

      <div class="ttd-fields">
        <label class="ttd-field"><span>售前阶段</span><select id="ttdStage">${stageOpts}</select></label>
        <label class="ttd-field"><span>截止时间</span><input type="datetime-local" id="ttdDue" value="${toLocalInput(t.due_date)}"></label>
      </div>

      <div class="ttd-section">
        <div class="ttd-label">优先级</div>
        <div class="ttd-prio-row">
          ${[0, 1, 2, 3].map(p => `<button type="button" data-priority="${p}" class="ttd-prio p${p} ${t.priority === p ? 'on' : ''}">${PRIORITY_LABELS[p]}</button>`).join('')}
        </div>
      </div>

      <div class="ttd-section">
        <div class="ttd-label">描述 / 备注</div>
        <textarea class="ttd-desc" id="ttdDesc" rows="3" placeholder="补充背景、结论或待确认事项…">${esc(t.description || '')}</textarea>
      </div>

      <div class="ttd-section">
        <div class="ttd-label">子任务 <span class="ttd-count">${subDone}/${subs.length}</span></div>
        <div class="ttd-subs">
          ${subs.length ? subs.map(s => `
            <div class="ttd-sub ${s.completed ? 'done' : ''}" data-sub-id="${esc(s.id)}">
              <button type="button" class="ttd-sub-check" data-sub-toggle="${esc(s.id)}">${s.completed ? '✓' : ''}</button>
              <span class="ttd-sub-title">${esc(s.title)}</span>
              <button type="button" class="ttd-sub-del" data-sub-del="${esc(s.id)}">×</button>
            </div>`).join('') : '<div class="ttd-muted">还没有子任务</div>'}
        </div>
        <input class="ttd-inline-input" id="ttdSubInput" placeholder="+ 添加子任务，回车确认">
      </div>

      <div class="ttd-section">
        <div class="ttd-label">标签</div>
        <div class="ttd-tags">
          ${(t.tags || []).map(tag => `<span class="ttd-tag">${esc(tag)}<b data-tag-remove="${esc(tag)}" title="移除">×</b></span>`).join('') || '<span class="ttd-muted">暂无标签</span>'}
        </div>
        <input class="ttd-inline-input" id="ttdTagInput" list="ttdTagList" placeholder="+ 添加标签，回车确认">
        <datalist id="ttdTagList">${tagPool.map(tag => `<option value="${esc(tag)}"></option>`).join('')}</datalist>
      </div>

      <div class="ttd-section">
        <div class="ttd-label">关联拓扑图</div>
        <div class="ttd-diagrams">
          ${linked.length ? linked.map(d => `<span class="ttd-diagram"><a href="/projects/${esc(pid)}/diagrams/${esc(d.id)}">${TT.icon.diagram}${esc(d.name)}</a><b data-diagram-remove="${esc(d.id)}" title="取消关联">×</b></span>`).join('') : '<span class="ttd-muted">尚未关联图纸</span>'}
        </div>
        ${diagramOpts ? `<select class="ttd-select" id="ttdDiagramAdd"><option value="">+ 关联一张拓扑图…</option>${diagramOpts}</select>` : ''}
      </div>

      <div class="ttd-section">
        <div class="ttd-label">拓扑节点</div>
        ${nodeLinks.length ? `<div class="ttd-node-links">${nodeLinks.map(n => `
          <a class="ttd-node-link" href="/projects/${esc(pid)}/diagrams/${esc(n.diagram_id)}?node=${encodeURIComponent(n.node_key)}">
            <span class="ttd-node-dot"></span><span>${esc(n.node_label || n.node_key)}</span><em>${esc(n.diagram_name)}</em>${n.is_primary ? '<b>主</b>' : ''}
          </a>`).join('')}</div>` : '<span class="ttd-muted">该任务没有关联拓扑节点</span>'}
      </div>

      <div class="ttd-meta">
        <span>创建 ${t.created_at ? TT.date(t.created_at, true) : '—'}</span>
        <span>更新 ${t.updated_at ? TT.relative(t.updated_at) : '—'}</span>
      </div>
      <div class="ttd-danger"><button type="button" id="ttdDelete">删除此任务</button></div>`;

    bindDetail(t);
    $('#taskDrawerEmpty').classList.add('hidden');
    box.classList.remove('hidden');
    drawer.scrollTop = scroll;
  }

  function bindDetail(t) {
    const box = $('#taskDetail');
    $('#ttdClose').onclick = closeDetail;
    $$('[data-status]', box).forEach(btn => {
      btn.onclick = () => saveTask(t.id, { status: btn.dataset.status }, { refreshDetail: true });
    });
    $$('[data-priority]', box).forEach(btn => {
      btn.onclick = () => saveTask(t.id, { priority: Number(btn.dataset.priority) }, { refreshDetail: true });
    });
    $('#ttdStage').onchange = (e) => saveTask(t.id, { stage: e.target.value }, { refreshDetail: true });
    $('#ttdDue').onchange = (e) => saveTask(t.id, { due_date: fromLocalInput(e.target.value) }, { refreshDetail: true });
    $('#ttdTitle').onchange = (e) => {
      const value = e.target.value.trim();
      if (value && value !== t.title) saveTask(t.id, { title: value }, { refreshDetail: false });
    };
    $('#ttdTitle').onkeydown = (e) => { if (e.key === 'Enter') e.target.blur(); };
    $('#ttdDesc').onchange = (e) => {
      if (e.target.value !== (t.description || '')) saveTask(t.id, { description: e.target.value }, { refreshDetail: false });
    };

    $$('[data-tag-remove]', box).forEach(el => {
      el.onclick = () => {
        const next = (t.tags || []).filter(x => x !== el.dataset.tagRemove);
        saveTask(t.id, { tags: next }, { refreshDetail: true });
      };
    });
    const tagInput = $('#ttdTagInput');
    if (tagInput) tagInput.onkeydown = (e) => {
      if (e.key !== 'Enter') return;
      e.preventDefault();
      const tag = e.target.value.trim();
      if (!tag) return;
      if ((t.tags || []).includes(tag)) { e.target.value = ''; return; }
      saveTask(t.id, { tags: [...(t.tags || []), tag] }, { refreshDetail: true });
    };

    const subInput = $('#ttdSubInput');
    if (subInput) subInput.onkeydown = async (e) => {
      if (e.key !== 'Enter') return;
      e.preventDefault();
      const title = e.target.value.trim();
      if (!title) return;
      try {
        await TT.api(`/api/tasks/${encodeURIComponent(t.id)}/subtasks`, { method: 'POST', body: { title } });
        await refreshTasks();
        await openTask(t.id, { resetScroll: false });
        fireChanged();
      } catch (err) { TT.toast(err.message, 'error'); }
    };
    $$('[data-sub-toggle]', box).forEach(el => {
      el.onclick = async () => {
        const sub = (t.subtasks || []).find(s => s.id === el.dataset.subToggle);
        if (!sub) return;
        try {
          await TT.api(`/api/tasks/${encodeURIComponent(t.id)}/subtasks/${encodeURIComponent(sub.id)}`, {
            method: 'PATCH', body: { completed: !sub.completed }
          });
          await refreshTasks();
          await openTask(t.id, { resetScroll: false });
          fireChanged();
        } catch (err) { TT.toast(err.message, 'error'); }
      };
    });
    $$('[data-sub-del]', box).forEach(el => {
      el.onclick = async () => {
        try {
          await TT.api(`/api/tasks/${encodeURIComponent(t.id)}/subtasks/${encodeURIComponent(el.dataset.subDel)}`, { method: 'DELETE' });
          await refreshTasks();
          await openTask(t.id, { resetScroll: false });
          fireChanged();
        } catch (err) { TT.toast(err.message, 'error'); }
      };
    });

    $$('[data-diagram-remove]', box).forEach(el => {
      el.onclick = async () => {
        try {
          await TT.api(`/api/tasks/${encodeURIComponent(t.id)}/diagrams/${encodeURIComponent(el.dataset.diagramRemove)}`, { method: 'DELETE' });
          await refreshTasks();
          await openTask(t.id, { resetScroll: false });
          fireChanged();
        } catch (err) { TT.toast(err.message, 'error'); }
      };
    });
    const diagramAdd = $('#ttdDiagramAdd');
    if (diagramAdd) diagramAdd.onchange = async () => {
      if (!diagramAdd.value) return;
      try {
        await TT.api(`/api/tasks/${encodeURIComponent(t.id)}/diagrams`, { method: 'POST', body: { diagram_id: diagramAdd.value } });
        await refreshTasks();
        await openTask(t.id, { resetScroll: false });
        fireChanged();
      } catch (err) { TT.toast(err.message, 'error'); }
    };

    $('#ttdDelete').onclick = () => {
      TT.confirm(`删除任务「${t.title}」？子任务和关联会一起删除。`, async () => {
        await TT.api('/api/tasks/' + encodeURIComponent(t.id), { method: 'DELETE' });
        closeDetail();
        await refreshTasks();
        fireChanged();
        TT.toast('任务已删除', 'success');
      });
    };
  }

  function showDetailPanel(show) {
    $('#taskDrawerEmpty').classList.toggle('hidden', show);
    $('#taskDetail').classList.toggle('hidden', !show);
  }

  function closeDetail() {
    selectedId = null;
    detail = null;
    showDetailPanel(false);
    renderList();
    renderBoard();
  }

  async function openTask(id, { resetScroll = true } = {}) {
    try {
      const t = await TT.api('/api/tasks/' + encodeURIComponent(id));
      selectedId = id;
      detail = t;
      renderList();
      renderBoard();
      renderDetail(t, resetScroll);
    } catch (err) {
      TT.toast('任务加载失败：' + err.message, 'error');
    }
  }

  // ---------------------------------------------------------------- data
  async function fetchTasks() {
    const my = ++seq;
    const projectId = pid;
    const items = [];
    let total;
    do {
      const data = await TT.api(`/api/tasks?project_id=${encodeURIComponent(projectId)}&limit=1000&offset=${items.length}`);
      if (my !== seq || projectId !== pid) return null;
      if (!data.items.length) break;
      items.push(...data.items);
      total = data.total;
    } while (items.length < total);
    tasks = items;
    if (selectedId && !tasks.some(t => t.id === selectedId)) {
      selectedId = null;
      detail = null;
      showDetailPanel(false);
    }
    return tasks;
  }

  async function refreshTasks() {
    if (!await fetchTasks()) return;
    render();
  }

  function fireChanged() {
    document.dispatchEvent(new CustomEvent('tt:tasks-changed', { detail: { projectId: pid } }));
  }

  async function saveTask(id, payload, { refreshDetail = true } = {}) {
    try {
      await TT.api('/api/tasks/' + encodeURIComponent(id), { method: 'PATCH', body: payload });
      await refreshTasks();
      if (refreshDetail && selectedId === id) await openTask(id, { resetScroll: false });
      else if (!refreshDetail && detail && detail.id === id) Object.assign(detail, payload);
      fireChanged();
    } catch (err) {
      TT.toast('保存失败：' + err.message, 'error');
    }
  }

  // ---------------------------------------------------------------- create
  function newTask() {
    const stage = (project && project.stage) || 'research';
    TT.modal({
      title: '新建任务',
      subtitle: '任务会归入当前项目，并按售前阶段聚合到看板。',
      body: `<div class="form-grid">
        <div class="field full"><label>任务标题 *</label><input name="title" required maxlength="200" placeholder="例如：确认 POC 环境与到货时间"></div>
        <div class="field full"><label>描述</label><textarea name="description" placeholder="背景、验收标准、备注…"></textarea></div>
        <div class="field"><label>售前阶段</label><select name="stage">${STAGES.map(s => `<option value="${s.key}" ${s.key === stage ? 'selected' : ''}>${esc(s.label)}</option>`).join('')}</select></div>
        <div class="field"><label>优先级</label><select name="priority">${PRIORITY_LABELS.map((p, i) => `<option value="${i}" ${i === 2 ? 'selected' : ''}>${p}</option>`).join('')}</select></div>
        <div class="field"><label>截止时间</label><input name="due" type="datetime-local"></div>
        <div class="field"><label>标签</label><input name="tags" placeholder="逗号分隔，如 POC, 环境"></div>
      </div>`,
      submitText: '创建任务',
      onSubmit: async (fd) => {
        const title = String(fd.get('title') || '').trim();
        if (!title) throw new Error('请填写任务标题');
        const created = await TT.api('/api/tasks', {
          method: 'POST',
          body: {
            project_id: pid,
            title,
            description: String(fd.get('description') || ''),
            stage: fd.get('stage'),
            priority: Number(fd.get('priority')),
            due_date: fromLocalInput(fd.get('due')),
            tags: String(fd.get('tags') || '').split(/[,，]/).map(s => s.trim()).filter(Boolean)
          }
        });
        await refreshTasks();
        await openTask(created.id);
        fireChanged();
        TT.toast('任务已创建', 'success');
      }
    });
  }

  // ---------------------------------------------------------------- static UI
  function bindStatic() {
    if (bound) return;
    bound = true;
    $$('#taskViewSeg button').forEach(btn => {
      btn.onclick = () => {
        view = btn.dataset.view;
        $$('#taskViewSeg button').forEach(b => b.classList.toggle('active', b === btn));
        render();
      };
    });
    $('#taskStageFilter').onchange = (e) => { stageFilter = e.target.value; render(); };
    $('#taskStatusFilter').onchange = (e) => { statusFilter = e.target.value; render(); };
    let timer = null;
    $('#taskSearch').oninput = (e) => {
      clearTimeout(timer);
      timer = setTimeout(() => { search = e.target.value; render(); }, 120);
    };
    $('#btnNewTask').onclick = newTask;
    const classic = $('#btnClassicTasks');
    if (classic) classic.onclick = () => {
      if (window.TTAI) window.TTAI.open({ projectId: pid });
      else TT.toast('AI 助手未加载，请刷新页面重试', 'error');
    };
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && selectedId && !document.getElementById('modalRoot').classList.contains('open')) closeDetail();
    });
    document.addEventListener('tt:tasks-changed', () => { /* project.js listens for header refresh */ });
  }

  async function loadDiagrams() {
    try {
      const data = await TT.api('/api/diagrams?project_id=' + encodeURIComponent(pid));
      diagrams = data.items || [];
    } catch (e) { diagrams = []; }
  }

  async function show(projectId, focusTaskId, projectArg) {
    const changed = projectId !== pid;
    pid = projectId;
    if (projectArg) project = projectArg;
    if (!project) project = window.TT_PROJECT || {};
    if (changed) {
      tasks = [];
      diagrams = [];
      selectedId = null;
      detail = null;
      search = '';
      stageFilter = 'all';
      statusFilter = 'all';
      const s = $('#taskSearch'); if (s) s.value = '';
      ['#taskStageFilter', '#taskStatusFilter'].forEach(sel => { const el = $(sel); if (el) el.value = 'all'; });
      loadedFor = '';
    }
    bindStatic();
    if (changed || loadedFor !== pid) {
      $('#taskListPane').innerHTML = '<div class="task-loading"><span class="spinner"></span>正在加载任务…</div>';
      await Promise.all([fetchTasks(), loadDiagrams()]);
      loadedFor = pid;
      render();
      if (focusTaskId) await openTask(focusTaskId);
      else if (selectedId) await openTask(selectedId);
      return;
    }
    await refreshTasks();
    await loadDiagrams();
    if (focusTaskId) await openTask(focusTaskId);
    else if (selectedId) await openTask(selectedId, { resetScroll: false });
  }

  window.TTTasks = { show, closeDetail, refresh: refreshTasks };
})();
