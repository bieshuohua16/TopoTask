/* Project workspace */
(function () {
  const TT = window.TT;
  const CFG = window.TT_CONFIG;
  const PROJECT_ID = CFG.projectId;
  const KINDS = { topology: '逻辑拓扑', architecture: '系统架构', deployment: '部署图', other: '其他' };
  let project = window.TT_PROJECT;
  let activeTab = TT.qs('tab') || 'overview';
  let diagrams = [];

  function setHeader(p) {
    document.getElementById('projectName').textContent = p.name;
    const stage = document.getElementById('projectStage');
    stage.className = 'stage-pill ' + p.stage;
    stage.textContent = p.stage_label;
    const status = document.getElementById('projectStatus');
    status.className = 'status-pill ' + p.status;
    status.textContent = p.status_label;
    document.getElementById('projectMeta').innerHTML =
      `<span>${TT.esc(p.customer || '未填写客户')}</span><i>·</i><span>${TT.esc(p.owner || '未指定负责人')}</span><i>·</i><span>更新于 ${TT.relative(p.updated_at)}</span>`;
    document.getElementById('tabTaskCount').textContent = p.task_total || 0;
    document.getElementById('tabDiagramCount').textContent = p.diagram_count || 0;
    document.getElementById('tabDeviceCount').textContent = p.device_count || 0;
    document.title = p.name + ' · TopoTash 拓事';
  }

  function renderTimeline(p) {
    const stages = CFG.stages || [];
    const idx = stages.findIndex(s => s.key === p.stage);
    document.getElementById('stageNow').textContent = TT.stageLabel(p.stage);
    document.getElementById('stageTimeline').innerHTML = stages.map((s, i) => {
      const cls = i < idx || p.status === 'won' ? 'done' : i === idx ? 'current' : '';
      return `<div class="stage-step ${cls}">
        <div class="step-dot">${i < idx || p.status === 'won' ? '✓' : i + 1}</div>
        <div class="step-label">${TT.esc(s.label)}</div>
        <div class="step-hint">${TT.esc(s.hint)}</div>
      </div>`;
    }).join('');
  }

  function renderInfo(p) {
    const rows = [
      ['客户', p.customer || '—'],
      ['负责人', p.owner || '—'],
      ['阶段', p.stage_label],
      ['状态', p.status_label],
      ['周期', (p.start_date || '—') + ' ~ ' + (p.end_date || '—')],
      ['项目编号', p.code || '—'],
    ];
    document.getElementById('projectInfo').innerHTML = rows.map(([k, v]) =>
      `<dt>${TT.esc(k)}</dt><dd title="${TT.esc(v)}">${TT.esc(v)}</dd>`).join('');
  }

  function taskRow(t) {
    const overdue = TT.isOverdue(t.due_date) && t.status !== 'done';
    return `
      <div class="task-row p${t.priority}" data-task="${t.id}">
        <span class="prio-bar"></span>
        <div class="tr-main">
          <div class="tr-title">${TT.esc(t.title)}</div>
          <div class="tr-sub"><span>${TT.esc(t.stage_label)}</span>${t.diagrams && t.diagrams.length ? `<span>· ${TT.esc(t.diagrams[0].name)}</span>` : ''}</div>
        </div>
        <span class="tr-due ${overdue ? 'overdue' : ''}">${TT.dueText(t.due_date)}</span>
        <span class="tr-status ${t.status}">${TT.esc(t.status_label)}</span>
      </div>`;
  }

  function renderOverview(p) {
    document.getElementById('ovProgress').textContent = (p.task_progress || 0) + '%';
    document.getElementById('ovProgressBar').style.width = (p.task_progress || 0) + '%';
    document.getElementById('ovTaskText').textContent = `${p.task_done} / ${p.task_total} 已完成`;
    document.getElementById('ovDoing').textContent = p.task_doing || 0;
    document.getElementById('ovDiagrams').textContent = p.diagram_count || 0;
    document.getElementById('ovFollowups').textContent = p.followup_count || 0;
    renderTimeline(p);
    renderInfo(p);

    const taskBox = document.getElementById('overviewTasks');
    const tasks = p.recent_tasks || [];
    taskBox.innerHTML = tasks.length ? tasks.map(taskRow).join('') : TT.empty('暂无未完成任务');
    taskBox.querySelectorAll('.task-row').forEach(row => {
      row.onclick = () => switchTab('tasks', { task: row.dataset.task });
    });

    const dBox = document.getElementById('overviewDiagrams');
    const list = (p.diagrams || []).slice(0, 4);
    dBox.innerHTML = list.length ? list.map(d => `
      <div class="mini-diagram" data-id="${d.id}">
        <div class="md-thumb">${TT.icon.diagram}</div>
        <b>${TT.esc(d.name)}</b><span>${d.node_count || 0} 节点 · ${TT.relative(d.updated_at)}</span>
      </div>`).join('') : TT.empty('还没有拓扑图');
    dBox.querySelectorAll('.mini-diagram').forEach(el => {
      el.onclick = () => { location.href = `/projects/${PROJECT_ID}/diagrams/${el.dataset.id}`; };
    });

    const fBox = document.getElementById('overviewFollowups');
    const fns = p.followup_nodes || [];
    fBox.innerHTML = fns.length ? fns.slice(0, 6).map(n => `
      <div class="followup-row" data-diagram="${n.diagram_id}" data-node="${TT.esc(n.node_key)}">
        <span class="fu-dot ${n.followup_status}"></span>
        <div class="fu-main"><div class="fu-title">${TT.esc(n.label)}</div><div class="fu-sub">${TT.esc(n.diagram_name)}</div></div>
      </div>`).join('') : TT.empty('暂无待跟进节点');
    fBox.querySelectorAll('.followup-row').forEach(el => {
      el.onclick = () => { location.href = `/projects/${PROJECT_ID}/diagrams/${el.dataset.diagram}?node=${encodeURIComponent(el.dataset.node)}`; };
    });
  }

  function renderDiagrams() {
    const grid = document.getElementById('projectDiagramGrid');
    if (!diagrams.length) {
      grid.innerHTML = `<div class="empty-state" style="grid-column:1/-1">
        <div class="empty-icon">${TT.icon.diagram}</div>
        <h3>还没有拓扑图</h3><p>新建一张，把系统架构或 POC 部署关系画出来；也可以导入已有画布 JSON。</p>
        <div class="empty-actions">
          <button class="btn btn-ghost" id="btnEmptyImportDiagram">导入拓扑图</button>
          <button class="btn btn-primary" id="btnEmptyNewDiagram">新建拓扑图</button>
        </div></div>`;
      const b = document.getElementById('btnEmptyNewDiagram');
      if (b) b.onclick = newDiagram;
      const ib = document.getElementById('btnEmptyImportDiagram');
      if (ib) ib.onclick = importDiagram;
      return;
    }
    grid.innerHTML = diagrams.map(d => {
      const thumb = window.TTDiagramThumbs
        ? window.TTDiagramThumbs.forKind(d.kind)
        : TT.icon.diagram;
      return `
      <article class="diagram-card" data-id="${d.id}">
        <div class="diagram-thumb">
          ${thumb}
          <span class="kind-tag">${TT.esc(KINDS[d.kind] || d.kind || '拓扑图')}</span>
          ${d.followup_count ? `<span class="followup-tag">${d.followup_count} 待跟进</span>` : ''}
        </div>
        <div class="diagram-info">
          <b>${TT.esc(d.name)}</b>
          <span>${d.node_count || 0} 个节点 · ${d.linked_task_count || 0} 个关联任务</span>
          <div class="di-meta"><span>${TT.relative(d.updated_at)}</span><span>v${d.version}</span></div>
          <div class="di-card-actions">
            <button type="button" data-act="open">打开画布</button>
            <button type="button" data-act="delete" class="danger" title="删除这张拓扑图">删除</button>
          </div>
        </div>
      </article>`;
    }).join('');
    grid.querySelectorAll('.diagram-card').forEach(el => {
      const d = diagrams.find(item => item.id === el.dataset.id);
      if (!d) return;
      el.onclick = () => { location.href = `/projects/${PROJECT_ID}/diagrams/${d.id}`; };
      const open = el.querySelector('[data-act="open"]');
      if (open) open.onclick = (ev) => { ev.stopPropagation(); el.click(); };
      const del = el.querySelector('[data-act="delete"]');
      if (del) del.onclick = (ev) => {
        ev.stopPropagation();
        if (window.TTDiagrams) {
          window.TTDiagrams.remove({ diagram: d, onDone: () => loadProject() });
        }
      };
    });
  }

  function newDiagram() {
    TT.modal({
      title: '新建拓扑图',
      subtitle: '创建后进入画布；节点可在右侧属性面板标记为待跟进并创建任务。',
      body: `<div class="form-grid">
        <div class="field full"><label>图纸名称 *</label><input name="name" required placeholder="例如：POC 环境部署图"></div>
        <div class="field"><label>类型</label><select name="kind">
          <option value="topology">逻辑拓扑</option><option value="architecture">系统架构</option>
          <option value="deployment">部署图</option><option value="other">其他</option></select></div>
        <div class="field full"><label>说明</label><textarea name="description" placeholder="这张图用来表达什么…"></textarea></div>
      </div>`,
      submitText: '创建并打开',
      onSubmit: async (fd) => {
        const payload = { project_id: PROJECT_ID, name: fd.get('name'), kind: fd.get('kind'), description: fd.get('description') };
        if (!payload.name) throw new Error('请填写图纸名称');
        const created = await TT.api('/api/diagrams', { method: 'POST', body: payload });
        location.href = `/projects/${PROJECT_ID}/diagrams/${created.id}`;
      }
    });
  }

  function importDiagram() {
    if (!window.TTDiagrams) return;
    window.TTDiagrams.importDiagram({
      projectId: PROJECT_ID,
      onDone: () => { loadProject(); }
    });
  }

  async function renderLinks() {
    const tableBody = document.querySelector('#taskDiagramTable tbody');
    const nodeBox = document.getElementById('nodeLinkList');
    try {
      const data = await TT.api('/api/views/links?project_id=' + encodeURIComponent(PROJECT_ID));
      const links = data.task_links || [];
      tableBody.innerHTML = links.length ? links.map(l => `
        <tr><td><div class="t-title">${TT.esc(l.title)}</div><div class="t-sub">${TT.esc(l.project_name)}</div></td>
        <td><a class="link-more" href="/projects/${PROJECT_ID}/diagrams/${l.diagram_id}">${TT.esc(l.diagram_name)}</a></td>
        <td><span class="badge ${l.status === 'done' ? 'teal' : l.status === 'doing' ? 'blue' : 'amber'}">${l.status === 'done' ? '已完成' : l.status === 'doing' ? '进行中' : '待办'}</span></td></tr>`).join('')
        : '<tr><td colspan="3" class="node-empty">暂无任务级关联。可在任务详情的「关联拓扑图」中添加。</td></tr>';

      const nodes = [];
      (data.diagrams || []).forEach(d => {
        (d.nodes || []).forEach(n => {
          if (n.followup_status !== 'none' || (n.linked_tasks || []).length) nodes.push(Object.assign({ diagram_name: d.name }, n));
        });
      });
      nodeBox.innerHTML = nodes.length ? nodes.map(n => `
        <div class="node-link-item">
          <div class="node-link-head"><span class="fu-dot ${n.followup_status}" style="width:8px;height:8px;border-radius:50%;background:${n.followup_status === 'done' ? '#0d9488' : n.followup_status === 'doing' ? '#2563eb' : '#d97706'}"></span>
            <b>${TT.esc(n.label)}</b><span style="font-size:10.5px;color:#7c879a">${TT.esc(n.diagram_name)}</span>
            <span class="badge ${n.followup_status === 'done' ? 'teal' : n.followup_status === 'doing' ? 'blue' : 'amber'}">${n.followup_status === 'done' ? '已完成' : n.followup_status === 'doing' ? '进行中' : '待跟进'}</span></div>
          <div class="node-link-tasks">${(n.linked_tasks || []).map(t => `<span class="node-link-task"><span class="dot" style="background:${t.status === 'done' ? '#0d9488' : t.status === 'doing' ? '#2563eb' : '#d97706'}"></span>${TT.esc(t.title)}</span>`).join('') || '<span class="node-empty">未关联任务</span>'}</div>
        </div>`).join('') : TT.empty('暂无节点跟进标记');
    } catch (e) {
      nodeBox.innerHTML = TT.empty('加载失败：' + e.message);
    }
  }

  function switchTab(tab, extra) {
    activeTab = tab;
    document.querySelectorAll('#projectTabs .tab').forEach(a => a.classList.toggle('active', a.dataset.tab === tab));
    ['overview', 'tasks', 'diagrams', 'links', 'devices'].forEach(t => {
      const el = document.getElementById('panel-' + t);
      if (el) el.classList.toggle('hidden', t !== tab);
    });
    const params = new URLSearchParams(location.search);
    params.set('tab', tab);
    if (extra && extra.task) params.set('task', extra.task); else params.delete('task');
    if (extra && extra.device) params.set('device', extra.device); else params.delete('device');
    history.replaceState(null, '', '?' + params.toString());
    if (tab === 'tasks' && window.TTTasks) {
      window.TTTasks.show(PROJECT_ID, extra && extra.task, project);
    }
    if (tab === 'devices' && window.TTDevices) {
      window.TTDevices.show(PROJECT_ID, { device: extra && extra.device });
    }
    if (tab === 'diagrams') {
      TT.api('/api/diagrams?project_id=' + encodeURIComponent(PROJECT_ID))
        .then(d => { diagrams = d.items; renderDiagrams(); })
        .catch(e => TT.toast(e.message, 'error'));
    }
    if (tab === 'links') renderLinks();
  }

  async function loadProject() {
    try {
      const data = await TT.api('/api/projects/' + PROJECT_ID);
      project = data;
      diagrams = data.diagrams || [];
      setHeader(data);
      renderOverview(data);
      renderDiagrams();
    } catch (e) {
      TT.toast('项目加载失败：' + e.message, 'error');
    }
  }

  document.querySelectorAll('#projectTabs .tab').forEach(a => {
    a.onclick = (ev) => { ev.preventDefault(); switchTab(a.dataset.tab); };
  });

  const editBtn = document.getElementById('btnEditProject');
  if (editBtn) editBtn.onclick = () => {
    TT.api('/api/projects/' + PROJECT_ID).then(p => window.TT_shell.projectForm(p)).catch(e => TT.toast(e.message, 'error'));
  };

  const menuBtn = document.getElementById('btnProjectMenu');
  const menu = document.getElementById('projectMenu');
  if (menuBtn) menuBtn.onclick = (e) => { e.stopPropagation(); menu.classList.toggle('open'); };
  document.addEventListener('click', () => { if (menu) menu.classList.remove('open'); });
  if (menu) menu.querySelector('[data-action="delete-project"]').onclick = () => {
    TT.confirm(`删除项目「${project.name}」？项目下的任务、拓扑图和关联会一起删除，且不可恢复。`, async () => {
      await TT.api('/api/projects/' + PROJECT_ID, { method: 'DELETE' });
      TT.toast('项目已删除', 'success');
      setTimeout(() => { location.href = '/'; }, 350);
    });
  };

  const newBtn = document.getElementById('btnNewDiagram');
  if (newBtn) newBtn.onclick = newDiagram;
  const importBtn = document.getElementById('btnImportDiagram');
  if (importBtn) importBtn.onclick = importDiagram;

  document.addEventListener('tt:tasks-changed', () => { loadProject(); });
  document.addEventListener('tt:devices-changed', () => { loadProject(); });

  window.addEventListener('message', (ev) => {
    if (ev.origin !== location.origin) return;
    const msg = ev.data || {};
    if (msg.type === 'topotash:toast') TT.toast(msg.message, msg.level || 'success');
    if (msg.type === 'topotash:project-changed') loadProject();
  });

  loadProject().then(() => {
    const tab = TT.qs('tab');
    if (tab && tab !== 'overview') switchTab(tab, { task: TT.qs('task'), device: TT.qs('device') });
    else if (TT.qs('task')) switchTab('tasks', { task: TT.qs('task') });
    else if (TT.qs('device')) switchTab('devices', { device: TT.qs('device') });
    else if (activeTab !== 'overview') switchTab(activeTab);
  });
})();
