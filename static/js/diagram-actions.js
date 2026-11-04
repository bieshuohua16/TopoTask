/* Shared topology-diagram actions: create / import / duplicate / bind. */
(function () {
  const TT = window.TT;
  const KINDS = [
    ['topology', '逻辑拓扑'],
    ['architecture', '系统架构'],
    ['deployment', '部署图'],
    ['other', '其他']
  ];

  function kindOptions(selected) {
    return KINDS.map(([key, label]) =>
      `<option value="${key}" ${key === selected ? 'selected' : ''}>${label}</option>`).join('');
  }

  function projectOptions(projects, selected) {
    return projects.map(p =>
      `<option value="${TT.esc(p.id)}" ${p.id === selected ? 'selected' : ''}>${TT.esc(p.name)}</option>`).join('');
  }

  function projectSelect(projects, selected, allowUnbound) {
    const unbound = allowUnbound
      ? `<option value="" ${selected ? '' : 'selected'}>暂不绑定（仅存入拓扑图库）</option>`
      : '';
    return unbound + projectOptions(projects, selected);
  }

  function baseName(filename) {
    let name = String(filename || '').split(/[\\/]/).pop();
    name = name.replace(/\.vweb\.json$/i, '').replace(/\.json$/i, '');
    return name.replace(/_/g, ' ').trim();
  }

  function projectField(projects, selected, { required = false, allowUnbound = false } = {}) {
    return `<div class="field full"><label>目标项目 ${required ? '*' : ''}</label>
      <select name="project_id">${projectSelect(projects, selected, allowUnbound)}</select></div>`;
  }

  function toast(message) {
    if (TT.toast) TT.toast(message, 'success');
  }

  // ------------------------------------------------------------------ create
  function createDiagram({ projectId, projects, defaultProjectId, onDone }) {
    const list = projects || [];
    const defaultProject = defaultProjectId !== undefined
      ? defaultProjectId
      : (list[0] && list[0].id);

    TT.modal({
      title: '新建拓扑图',
      subtitle: projectId
        ? '创建后进入画布；节点可在右侧属性面板标记为待跟进并创建任务。'
        : '可以暂不绑定项目，先存入拓扑图库；之后可随时绑定。',
      body: `<div class="form-grid">
        ${projectId ? '' : projectField(list, defaultProject, { allowUnbound: true })}
        <div class="field full"><label>图纸名称 *</label>
          <input name="name" required maxlength="200" placeholder="例如：POC 环境部署图"></div>
        <div class="field"><label>类型</label><select name="kind">${kindOptions('topology')}</select></div>
        <div class="field full"><label>说明</label>
          <textarea name="description" placeholder="这张图用来表达什么…"></textarea></div>
      </div>`,
      submitText: '创建并打开',
      width: 560,
      onSubmit: async (fd) => {
        const name = String(fd.get('name') || '').trim();
        if (!name) throw new Error('请填写图纸名称');
        const created = await TT.api('/api/diagrams', {
          method: 'POST',
          body: {
            project_id: projectId || fd.get('project_id') || null,
            name,
            kind: fd.get('kind'),
            description: String(fd.get('description') || '').trim()
          }
        });
        toast('拓扑图已创建');
        if (onDone) onDone(created);
      }
    });
  }

  // ------------------------------------------------------------------ import
  function importDiagram({ projectId, projects, defaultProjectId, onDone }) {
    const list = projects || [];
    const defaultProject = defaultProjectId !== undefined
      ? defaultProjectId
      : (list[0] && list[0].id);

    let autoName = '';
    const modal = TT.modal({
      title: '导入拓扑图',
      subtitle: '支持编辑器导出的 .vweb.json / 画布 JSON 文件。',
      body: `<div class="form-grid">
        ${projectId ? '' : projectField(list, defaultProject, { allowUnbound: true })}
        <div class="field full"><label>画布文件 *</label>
          <input type="file" name="file" accept=".json,.vweb.json,application/json" required>
          <span class="field-hint">文件需包含 shapes 对象；导入后可在画布中继续编辑。</span></div>
        <div class="field full"><label>图纸名称</label>
          <input name="name" maxlength="200" placeholder="留空则使用文件名"></div>
        <div class="field"><label>类型</label><select name="kind">${kindOptions('topology')}</select></div>
        <div class="field full"><label>说明</label>
          <textarea name="description" placeholder="留空则记录来源文件名"></textarea></div>
      </div>`,
      submitText: '导入拓扑图',
      width: 560,
      onSubmit: async (fd) => {
        const file = fd.get('file');
        if (!file || !file.size) throw new Error('请选择要导入的 JSON 文件');
        let doc;
        try { doc = JSON.parse(await file.text()); }
        catch (e) { throw new Error('文件不是有效的 JSON'); }
        const content = doc && doc.content && doc.content.shapes ? doc.content : doc;
        if (!content || typeof content.shapes !== 'object' || Array.isArray(content.shapes)) {
          throw new Error('文件格式不正确：缺少 shapes 对象');
        }
        const name = String(fd.get('name') || '').trim() || baseName(file.name);
        const created = await TT.api('/api/diagrams/import', {
          method: 'POST',
          body: {
            project_id: projectId || fd.get('project_id') || null,
            name,
            kind: fd.get('kind'),
            description: String(fd.get('description') || '').trim(),
            source_name: file.name,
            content
          }
        });
        toast(`已导入《${created.name}》`);
        if (onDone) onDone(created);
      }
    });

    const fileInput = modal && modal.form && modal.form.querySelector('[name="file"]');
    if (fileInput) {
      fileInput.onchange = () => {
        const file = fileInput.files && fileInput.files[0];
        if (!file) return;
        const nameInput = modal.form.querySelector('[name="name"]');
        const derived = baseName(file.name);
        if (nameInput && (!nameInput.value.trim() || nameInput.value === autoName)) {
          nameInput.value = derived;
          autoName = derived;
        }
      };
    }
  }

  // --------------------------------------------------------------- duplicate
  function duplicateDiagram({ diagram, projects, onDone }) {
    const list = projects || [];

    TT.modal({
      title: '复制拓扑图',
      subtitle: '复制画布与节点；节点上的任务关联不会一并复制。',
      body: `<div class="form-grid">
        <div class="field full"><label>新图纸名称 *</label>
          <input name="name" required maxlength="200" value="${TT.esc(diagram.name + ' 副本')}"></div>
        <div class="field full"><label>目标项目</label>
          <select name="project_id">${projectSelect(list, diagram.project_id, !diagram.project_id)}</select></div>
      </div>`,
      submitText: '复制',
      width: 520,
      onSubmit: async (fd) => {
        const name = String(fd.get('name') || '').trim();
        if (!name) throw new Error('请填写图纸名称');
        const created = await TT.api(`/api/diagrams/${encodeURIComponent(diagram.id)}/duplicate`, {
          method: 'POST',
          body: { name, project_id: fd.get('project_id') || null }
        });
        toast(`已复制为《${created.name}》`);
        if (onDone) onDone(created);
      }
    });
  }

  // -------------------------------------------------------------------- bind
  function bindDiagram({ diagram, projects, onDone }) {
    const list = (projects || []).filter(p => p.id !== diagram.project_id);
    if (!list.length) {
      TT.toast(diagram.project_id ? '暂无可绑定的其他项目，请先新建项目' : '还没有项目，请先新建项目', 'error');
      return;
    }
    const linkParts = [];
    if (diagram.linked_task_count) linkParts.push(`${diagram.linked_task_count} 个节点任务关联`);
    if (diagram.task_link_count) linkParts.push(`${diagram.task_link_count} 个任务级关联`);
    const warning = linkParts.length
      ? `<div class="bind-warning">该拓扑图有 ${linkParts.join('、')}。绑定到其他项目后，跨项目的关联会自动解除。</div>`
      : '';
    TT.modal({
      title: '绑定到项目',
      subtitle: `把《${diagram.name}》绑定到目标项目，并移动其中的画布与节点。`,
      body: `<div class="form-grid">
        <div class="field full"><label>目标项目 *</label>
          <select name="project_id">${projectOptions(list, list[0].id)}</select></div>
      </div>${warning}`,
      submitText: '绑定',
      width: 480,
      onSubmit: async (fd) => {
        const target = fd.get('project_id');
        if (!target) throw new Error('请选择目标项目');
        const updated = await TT.api(`/api/diagrams/${encodeURIComponent(diagram.id)}`, {
          method: 'PATCH',
          body: { project_id: target }
        });
        toast(`已绑定到「${updated.project_name || '目标项目'}」`);
        if (onDone) onDone(updated);
      }
    });
  }

  // ------------------------------------------------------------------ delete
  function removeDiagram({ diagram, onDone }) {
    TT.confirm(
      `删除拓扑图《${diagram.name}》？画布、节点跟进标记以及它与任务的关联会一并删除，且不可恢复。`,
      async () => {
        await TT.api(`/api/diagrams/${encodeURIComponent(diagram.id)}`, { method: 'DELETE' });
        toast(`已删除《${diagram.name}》`);
        if (onDone) onDone();
      },
      { title: '删除拓扑图', submitText: '删除' }
    );
  }

  window.TTDiagrams = {
    KINDS,
    create: createDiagram,
    importDiagram,
    duplicate: duplicateDiagram,
    bind: bindDiagram,
    remove: removeDiagram
  };
})();
