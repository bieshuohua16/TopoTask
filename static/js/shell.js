/* Shell: sidebar, global search, project form */
(function () {
  const CFG = window.TT_CONFIG || {};
  const TT = window.TT;

  function navActive() {
    const page = CFG.page;
    document.querySelectorAll('.nav-item').forEach(el => {
      el.classList.toggle('active', el.dataset.nav === page);
    });
  }

  async function loadProjects() {
    const box = document.getElementById('projectNav');
    if (!box) return;
    try {
      const data = await TT.api('/api/projects');
      if (!data.items.length) {
        box.innerHTML = '<div class="side-empty">暂无项目，点击 + 创建</div>';
        return;
      }
      box.innerHTML = data.items.map(p => `
        <a class="project-link ${p.id === CFG.projectId ? 'active' : ''}" href="/projects/${p.id}" title="${TT.esc(p.name)}">
          <span class="pdot" style="background:${TT.esc(p.color || '#5b6cf0')}"></span>
          <span class="pname">${TT.esc(p.name)}</span>
          <span class="pcount">${p.task_open || 0}</span>
        </a>`).join('');
    } catch (e) {
      box.innerHTML = `<div class="side-empty">项目加载失败：${TT.esc(e.message)}</div>`;
    }
  }

  function projectForm(project) {
    const isEdit = !!project;
    const p = project || {};
    const stageOpts = (CFG.stages || []).map(s =>
      `<option value="${s.key}" ${p.stage === s.key ? 'selected' : ''}>${TT.esc(s.label)}</option>`).join('');
    const statusOpts = (CFG.statuses || []).map(s =>
      `<option value="${s.key}" ${p.status === s.key ? 'selected' : ''}>${TT.esc(s.label)}</option>`).join('');
    const body = `
      <div class="form-grid">
        <div class="field full"><label>项目名称 *</label><input name="name" required maxlength="120" value="${TT.esc(p.name || '')}" placeholder="例如：XX 银行私有云 POC"></div>
        <div class="field"><label>客户</label><input name="customer" value="${TT.esc(p.customer || '')}" placeholder="客户名称"></div>
        <div class="field"><label>负责人</label><input name="owner" value="${TT.esc(p.owner || '')}" placeholder="售前负责人"></div>
        <div class="field"><label>售前阶段</label><select name="stage">${stageOpts}</select></div>
        <div class="field"><label>项目状态</label><select name="status">${statusOpts}</select></div>
        <div class="field"><label>开始日期</label><input name="start_date" type="date" value="${TT.esc(p.start_date || '')}"></div>
        <div class="field"><label>预计结束</label><input name="end_date" type="date" value="${TT.esc(p.end_date || '')}"></div>
        <div class="field"><label>项目编号</label><input name="code" value="${TT.esc(p.code || '')}" placeholder="商机 / 项目编号"></div>
        <div class="field"><label>主题色</label><input name="color" type="color" value="${TT.esc(p.color || '#5b6cf0')}" style="padding:3px;height:36px"></div>
        <div class="field full"><label>项目描述</label><textarea name="description" placeholder="客户背景、建设目标、竞争态势…">${TT.esc(p.description || '')}</textarea></div>
      </div>`;

    TT.modal({
      title: isEdit ? '编辑项目' : '新建售前项目',
      subtitle: isEdit ? '项目信息会同步到任务台和拓扑图。' : '创建后会自动生成一个默认任务分类，并可开始拆任务、画拓扑。',
      body,
      submitText: isEdit ? '保存修改' : '创建项目',
      onSubmit: async (fd) => {
        const payload = {};
        fd.forEach((v, k) => { payload[k] = typeof v === 'string' ? v.trim() : v; });
        if (!payload.name) throw new Error('项目名称不能为空');
        let projectId = p.id;
        if (isEdit) {
          await TT.api('/api/projects/' + p.id, { method: 'PATCH', body: payload });
          TT.toast('项目已更新', 'success');
        } else {
          const created = await TT.api('/api/projects', { method: 'POST', body: payload });
          projectId = created.id;
          TT.toast('项目已创建', 'success');
        }
        document.dispatchEvent(new CustomEvent('tt:project-saved', { detail: { projectId, isEdit } }));
        await loadProjects();
        if (!isEdit) location.href = '/projects/' + projectId;
        else if (window.TT_PROJECT) location.reload();
      }
    });
  }

  function bindNewProject() {
    ['topNewProject', 'btnSideNewProject'].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.onclick = () => projectForm(null);
    });
  }

  // ---------------- global search ----------------
  function initSearch() {
    const input = document.getElementById('globalSearch');
    const pop = document.getElementById('searchPop');
    if (!input || !pop) return;
    let timer = null;
    let lastItems = [];
    const close = () => { pop.classList.remove('open'); pop.innerHTML = ''; };

    const render = (data, q) => {
      const sections = [];
      if (data.projects.length) {
        sections.push('<div class="search-group-title">项目</div>' + data.projects.map(p =>
          `<a class="search-item" href="/projects/${p.id}"><span class="si-type">项目</span><span>${TT.esc(p.name)}</span><span style="margin-left:auto;color:#7c879a;font-size:11px">${TT.esc(p.stage_label)}</span></a>`).join(''));
      }
      if (data.tasks.length) {
        sections.push('<div class="search-group-title">任务</div>' + data.tasks.map(t =>
          `<a class="search-item" href="/projects/${t.project_id}?tab=tasks&task=${encodeURIComponent(t.id)}"><span class="si-type">任务</span><span>${TT.esc(t.title)}</span><span style="margin-left:auto;color:#7c879a;font-size:11px">${TT.esc(t.project_name)}</span></a>`).join(''));
      }
      if (data.diagrams.length) {
        sections.push('<div class="search-group-title">拓扑图</div>' + data.diagrams.map(d => {
          const href = d.project_id
            ? `/projects/${d.project_id}/diagrams/${d.id}`
            : `/diagrams/${d.id}`;
          return `<a class="search-item" href="${href}"><span class="si-type">拓扑</span><span>${TT.esc(d.name)}</span>${d.project_id ? '' : '<span style="margin-left:auto;color:#7c879a;font-size:11px">未绑定项目</span>'}</a>`;
        }).join(''));
      }
      lastItems = sections;
      pop.innerHTML = sections.length ? sections.join('') : `<div class="search-empty">没有找到「${TT.esc(q)}」相关内容</div>`;
      pop.classList.add('open');
    };

    input.addEventListener('input', () => {
      const q = input.value.trim();
      clearTimeout(timer);
      if (!q) { close(); return; }
      timer = setTimeout(async () => {
        try { render(await TT.api('/api/views/search?q=' + encodeURIComponent(q)), q); }
        catch (e) { pop.innerHTML = `<div class="search-empty">${TT.esc(e.message)}</div>`; pop.classList.add('open'); }
      }, 220);
    });
    input.addEventListener('focus', () => { if (input.value.trim() && lastItems.length) pop.classList.add('open'); });
    document.addEventListener('click', e => { if (!e.target.closest('.top-search')) close(); });
    document.addEventListener('keydown', e => {
      if (e.key === '/' && !['INPUT', 'TEXTAREA', 'SELECT'].includes(e.target.tagName)) {
        e.preventDefault(); input.focus(); input.select();
      }
      if (e.key === 'Escape') { close(); input.blur(); }
    });
    input.addEventListener('keydown', e => {
      if (e.key === 'Enter') {
        const first = pop.querySelector('a');
        if (first) first.click();
      }
    });
  }

  navActive();
  loadProjects();
  bindNewProject();
  initSearch();

  document.addEventListener('tt:projects-changed', loadProjects);
  window.addEventListener('message', (ev) => {
    if (ev.origin !== location.origin) return;
    if ((ev.data || {}).type === 'topotash:project-changed') loadProjects();
  });
  window.TT_shell = { loadProjects, projectForm };
})();
