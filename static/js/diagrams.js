/* Diagram library */
(function () {
  const TT = window.TT;
  const sel = document.getElementById('libraryProject');
  const KINDS = { topology: '逻辑拓扑', architecture: '系统架构', deployment: '部署图', other: '其他' };

  function card(d) {
    return `
      <article class="diagram-card" data-project="${d.project_id}" data-id="${d.id}">
        <div class="diagram-thumb">
          <span class="kind-tag">${TT.esc(KINDS[d.kind] || d.kind || '拓扑图')}</span>
          ${d.followup_count ? `<span class="followup-tag">${d.followup_count} 待跟进</span>` : ''}
          ${TT.icon.diagram}
        </div>
        <div class="diagram-info">
          <b>${TT.esc(d.name)}</b>
          <span>${TT.esc(d.project_name || '')}</span>
          <div class="di-meta"><span>${d.node_count || 0} 个节点</span><span>${d.task_link_count || 0} 个关联任务</span><span>${TT.relative(d.updated_at)}</span></div>
        </div>
      </article>`;
  }

  async function load() {
    try {
      const pid = sel.value;
      const data = await TT.api('/api/diagrams' + (pid ? '?project_id=' + encodeURIComponent(pid) : ''));
      const grid = document.getElementById('diagramGrid');
      const empty = document.getElementById('diagramEmpty');
      if (!data.items.length) {
        grid.innerHTML = ''; grid.classList.add('hidden'); empty.classList.remove('hidden');
      } else {
        empty.classList.add('hidden'); grid.classList.remove('hidden');
        grid.innerHTML = data.items.map(card).join('');
        grid.querySelectorAll('.diagram-card').forEach(el => {
          el.onclick = () => { location.href = `/projects/${el.dataset.project}/diagrams/${el.dataset.id}`; };
        });
      }
    } catch (e) {
      TT.toast('加载失败：' + e.message, 'error');
    }
  }

  (async () => {
    try {
      const data = await TT.api('/api/projects');
      data.items.forEach(p => {
        const opt = document.createElement('option');
        opt.value = p.id; opt.textContent = p.name;
        sel.appendChild(opt);
      });
      const wanted = TT.qs('project_id');
      if (wanted) sel.value = wanted;
    } catch (e) { /* ignore */ }
    load();
  })();

  sel.onchange = load;
  document.addEventListener('tt:project-saved', () => location.reload());
  document.addEventListener('tt:tasks-changed', load);
})();
