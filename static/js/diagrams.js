/* Diagram library */
(function () {
  const TT = window.TT;
  const ACT = window.TTDiagrams;
  const sel = document.getElementById('libraryProject');
  const KINDS = { topology: '逻辑拓扑', architecture: '系统架构', deployment: '部署图', other: '其他' };
  const UNBOUND = '__unbound__';
  let projects = [];
  let items = [];

  function card(d) {
    return `
      <article class="diagram-card" data-project="${TT.esc(d.project_id)}" data-id="${TT.esc(d.id)}">
        <div class="diagram-thumb">
          <span class="kind-tag">${TT.esc(KINDS[d.kind] || d.kind || '拓扑图')}</span>
          ${d.followup_count ? `<span class="followup-tag">${d.followup_count} 待跟进</span>` : ''}
          ${TT.icon.diagram}
        </div>
        <div class="diagram-info">
          <b>${TT.esc(d.name)}</b>
          <span class="di-project">${TT.esc(d.project_name || '未绑定项目')}</span>
          <div class="di-meta"><span>${d.node_count || 0} 个节点</span><span>${d.task_link_count || 0} 个关联任务</span><span>${TT.relative(d.updated_at)}</span></div>
          <div class="di-card-actions">
            <button type="button" data-act="duplicate" title="复制这张拓扑图">复制</button>
            <button type="button" data-act="bind" title="把这张拓扑图绑定到其他项目">绑定项目</button>
          </div>
        </div>
      </article>`;
  }

  function selectedProject() {
    return sel.value === UNBOUND ? '' : (sel.value || '');
  }

  function editorUrl(d) {
    return d.project_id
      ? `/projects/${d.project_id}/diagrams/${d.id}`
      : `/diagrams/${d.id}`;
  }

  function openDiagram(d) {
    location.href = editorUrl(d);
  }

  async function load() {
    try {
      const pid = sel.value;
      let url = '/api/diagrams';
      if (pid === UNBOUND) url += '?unbound=1';
      else if (pid) url += '?project_id=' + encodeURIComponent(pid);
      const data = await TT.api(url);
      items = data.items;
      const grid = document.getElementById('diagramGrid');
      const empty = document.getElementById('diagramEmpty');
      if (!items.length) {
        grid.innerHTML = ''; grid.classList.add('hidden'); empty.classList.remove('hidden');
      } else {
        empty.classList.add('hidden'); grid.classList.remove('hidden');
        grid.innerHTML = items.map(card).join('');
        grid.querySelectorAll('.diagram-card').forEach(el => {
          const d = items.find(item => item.id === el.dataset.id);
          if (!d) return;
          el.onclick = () => openDiagram(d);
          el.querySelectorAll('[data-act]').forEach(btn => {
            btn.onclick = (ev) => {
              ev.stopPropagation();
              if (btn.dataset.act === 'duplicate') {
                ACT.duplicate({ diagram: d, projects, onDone: load });
              } else if (btn.dataset.act === 'bind') {
                ACT.bind({ diagram: d, projects, onDone: load });
              }
            };
          });
        });
      }
    } catch (e) {
      TT.toast('加载失败：' + e.message, 'error');
    }
  }

  function newDiagram() {
    ACT.create({
      projectId: selectedProject(),
      projects,
      defaultProjectId: sel.value === UNBOUND ? '' : (projects[0] && projects[0].id),
      onDone: (created) => { location.href = editorUrl(created); }
    });
  }

  function importDiagram() {
    ACT.importDiagram({
      projectId: selectedProject(),
      projects,
      defaultProjectId: sel.value === UNBOUND ? '' : (projects[0] && projects[0].id),
      onDone: (created) => {
        sel.value = created.project_id || UNBOUND;
        load();
      }
    });
  }

  (async () => {
    try {
      const data = await TT.api('/api/projects');
      projects = data.items;
      projects.forEach(p => {
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
  const newBtn = document.getElementById('btnNewDiagram');
  if (newBtn) newBtn.onclick = newDiagram;
  const importBtn = document.getElementById('btnImportDiagram');
  if (importBtn) importBtn.onclick = importDiagram;
  const emptyNew = document.getElementById('btnEmptyNew');
  if (emptyNew) emptyNew.onclick = newDiagram;
  const emptyImport = document.getElementById('btnEmptyImport');
  if (emptyImport) emptyImport.onclick = importDiagram;
  document.addEventListener('tt:project-saved', () => location.reload());
  document.addEventListener('tt:tasks-changed', load);
})();
