/* Stage board */
(function () {
  const TT = window.TT;
  const projectSel = document.getElementById('boardProject');
  const doneToggle = document.getElementById('includeDone');
  const colors = {};

  function card(t) {
    const overdue = TT.isOverdue(t.due_date) && t.status !== 'done';
    const diagrams = (t.diagrams || []).slice(0, 1).map(d => `<span class="mini-tag">图 · ${TT.esc(d.name)}</span>`).join('');
    return `
      <article class="board-card" data-project="${t.project_id}" data-task="${t.id}">
        <div class="bc-proj"><span style="display:inline-block;width:6px;height:6px;border-radius:50%;background:${TT.esc(colors[t.project_id] || '#4f5bd5')}"></span>${TT.esc(t.project_name)}</div>
        <div class="bc-title">${TT.esc(t.title)}</div>
        <div class="bc-meta">
          <span class="tr-status ${t.status}">${TT.esc(t.status_label)}</span>
          <span class="due ${overdue ? 'overdue' : ''}">${TT.dueText(t.due_date)}</span>
          ${t.priority <= 1 ? `<span>P${t.priority}</span>` : ''}
        </div>
        ${diagrams || (t.subtask_total ? `<div class="bc-links"><span class="mini-tag">子任务 ${t.subtask_done}/${t.subtask_total}</span></div>` : '')}
      </article>`;
  }

  async function load() {
    const params = new URLSearchParams();
    if (projectSel.value) params.set('project_id', projectSel.value);
    if (doneToggle.checked) params.set('include_done', '1');
    try {
      const data = await TT.api('/api/views/stage-board?' + params.toString());
      const board = document.getElementById('board');
      board.innerHTML = data.stages.map(s => `
        <section class="board-col" data-stage="${s.key}">
          <div class="col-head">
            <span class="stage-pill ${s.key}">${TT.esc(s.label)}</span>
            <span class="count">${s.task_count} 任务 · ${s.project_count} 项目</span>
          </div>
          <div class="col-body">
            ${s.tasks.length ? s.tasks.map(card).join('') : `<div class="col-empty">${TT.esc(s.hint)}<br>暂无任务</div>`}
          </div>
        </section>`).join('');
      board.querySelectorAll('.board-card').forEach(el => {
        el.onclick = () => { location.href = `/projects/${el.dataset.project}?tab=tasks&task=${encodeURIComponent(el.dataset.task)}`; };
      });
    } catch (e) {
      TT.toast('加载失败：' + e.message, 'error');
    }
  }

  async function init() {
    try {
      const data = await TT.api('/api/projects');
      data.items.forEach(p => {
        colors[p.id] = p.color;
        const opt = document.createElement('option');
        opt.value = p.id; opt.textContent = p.name;
        projectSel.appendChild(opt);
      });
      const wanted = TT.qs('project_id');
      if (wanted) projectSel.value = wanted;
    } catch (e) {
      TT.toast('项目加载失败：' + e.message, 'error');
    }
    await load();
  }

  projectSel.onchange = load;
  doneToggle.onchange = load;
  document.addEventListener('tt:project-saved', () => location.reload());
  document.addEventListener('tt:tasks-changed', load);
  init();
})();
