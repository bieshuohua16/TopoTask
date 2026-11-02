/* Dashboard */
(function () {
  const TT = window.TT;
  let currentStage = 'all';
  let allProjects = [];

  function stat(key, value) {
    document.querySelectorAll(`[data-stat="${key}"]`).forEach(el => { el.textContent = value; });
  }

  function projectCard(p) {
    const progress = p.task_progress || 0;
    const next = p.next_due ? `<span><svg viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="8"/><path d="M12 8v4l2.5 2"/></svg>${TT.dueText(p.next_due)}</span>` : '<span>暂无截止</span>';
    return `
      <article class="project-card" data-stage="${p.stage}" style="--card-color:${TT.esc(p.color || '#4f5bd5')}" data-id="${p.id}">
        <div class="pc-top">
          <span class="stage-pill ${p.stage}">${TT.esc(p.stage_label)}</span>
          <span class="status-pill ${p.status}">${TT.esc(p.status_label)}</span>
        </div>
        <h3>${TT.esc(p.name)}</h3>
        <div class="pc-customer"><b>${TT.esc(p.customer || '未填写客户')}</b>${p.owner ? ' · ' + TT.esc(p.owner) : ''}</div>
        <div class="pc-progress">
          <div class="pc-progress-row"><span>任务完成</span><span>${p.task_done}/${p.task_total} · ${progress}%</span></div>
          <div class="progress"><i style="width:${progress}%"></i></div>
        </div>
        <div class="pc-meta">
          <span>${TT.icon.tasks}${p.task_open} 待办</span>
          <span>${TT.icon.diagram}${p.diagram_count} 图</span>
          <span>${TT.icon.flag}${p.followup_count} 待跟进</span>
        </div>
        <div class="pc-foot"><span>${next}</span><span class="go">进入 →</span></div>
      </article>`;
  }

  function renderProjects() {
    const grid = document.getElementById('projectGrid');
    const empty = document.getElementById('projectEmpty');
    const list = currentStage === 'all' ? allProjects : allProjects.filter(p => p.stage === currentStage);
    if (!list.length) {
      grid.innerHTML = '';
      grid.classList.add('hidden');
      empty.classList.remove('hidden');
      empty.querySelector('h3').textContent = currentStage === 'all' ? '还没有项目' : '该阶段暂无项目';
      empty.querySelector('p').textContent = currentStage === 'all'
        ? '创建第一个售前项目，然后开始拆任务、画拓扑图。'
        : '切换其他阶段，或新建一个项目归入该阶段。';
    } else {
      empty.classList.add('hidden');
      grid.classList.remove('hidden');
      grid.innerHTML = list.map(projectCard).join('');
      grid.querySelectorAll('.project-card').forEach(card => {
        card.onclick = () => { location.href = '/projects/' + card.dataset.id; };
      });
    }
  }

  function renderUpcoming(items) {
    const box = document.getElementById('upcomingList');
    if (!items.length) { box.innerHTML = TT.empty('暂无到期任务，节奏不错'); return; }
    box.innerHTML = items.map(t => {
      const overdue = TT.isOverdue(t.due_date) && t.status !== 'done';
      return `
        <div class="task-row p${t.priority}" data-project="${t.project_id}" data-task="${t.id}">
          <span class="prio-bar"></span>
          <div class="tr-main">
            <div class="tr-title">${TT.esc(t.title)}</div>
            <div class="tr-sub"><span class="proj">${TT.esc(t.project_name)}</span><span>${TT.esc(t.status_label)}</span></div>
          </div>
          <span class="tr-due ${overdue ? 'overdue' : ''}">${TT.dueText(t.due_date)}</span>
          <span class="tr-status ${t.status}">${TT.esc(t.status_label)}</span>
        </div>`;
    }).join('');
    box.querySelectorAll('.task-row').forEach(row => {
      row.onclick = () => { location.href = `/projects/${row.dataset.project}?tab=tasks&task=${encodeURIComponent(row.dataset.task)}`; };
    });
  }

  function renderFollowups(items) {
    const box = document.getElementById('followupList');
    document.getElementById('followupCount').textContent = items.length;
    if (!items.length) { box.innerHTML = TT.empty('还没有标记待跟进的节点'); return; }
    box.innerHTML = items.map(n => {
      const task = n.tasks && n.tasks[0];
      return `
        <div class="followup-row" data-project="${n.project_id}" data-diagram="${n.diagram_id}" data-node="${TT.esc(n.node_key)}">
          <span class="fu-dot ${n.followup_status}"></span>
          <div class="fu-main">
            <div class="fu-title">${TT.esc(n.label)}</div>
            <div class="fu-sub">${TT.esc(n.diagram_name)} · ${TT.esc(n.project_name)}${task ? ' · ' + TT.esc(task.title) : ''}</div>
          </div>
          <span class="badge ${n.followup_status === 'done' ? 'teal' : n.followup_status === 'doing' ? 'blue' : 'amber'}">${n.followup_status === 'done' ? '已完成' : n.followup_status === 'doing' ? '进行中' : '待跟进'}</span>
        </div>`;
    }).join('');
    box.querySelectorAll('.followup-row').forEach(row => {
      row.onclick = () => { location.href = `/projects/${row.dataset.project}/diagrams/${row.dataset.diagram}?node=${encodeURIComponent(row.dataset.node)}`; };
    });
  }

  async function load() {
    try {
      const data = await TT.api('/api/views/overview');
      stat('active_projects', data.active_projects);
      stat('project_total', '共 ' + data.project_total + ' 个项目');
      stat('task_open', data.task_open);
      stat('task_overdue', data.task_overdue);
      stat('diagram_total', data.diagram_total);
      stat('followup_total', data.followup_total);
      allProjects = data.projects;
      renderProjects();
      renderUpcoming(data.upcoming);
      renderFollowups(data.followups);
    } catch (e) {
      TT.toast('加载失败：' + e.message, 'error');
    }
  }

  document.querySelectorAll('#stageFilter .chip').forEach(chip => {
    chip.onclick = () => {
      currentStage = chip.dataset.stage;
      document.querySelectorAll('#stageFilter .chip').forEach(c => c.classList.toggle('active', c === chip));
      renderProjects();
    };
  });
  const refresh = document.getElementById('btnRefresh');
  if (refresh) refresh.onclick = load;
  document.querySelectorAll('[data-action="new-project"]').forEach(btn => {
    btn.onclick = () => window.TT_shell && window.TT_shell.projectForm(null);
  });
  document.addEventListener('tt:project-saved', load);
  load();
})();
