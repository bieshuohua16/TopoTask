/* Project device list (BOM) */
(function () {
  'use strict';
  const TT = window.TT;
  if (!TT) return;

  const $ = (selector) => document.querySelector(selector);
  let loadSeq = 0;
  const state = {
    projectId: '',
    items: [],
    summary: null,
    categories: [],
    statuses: [],
    category: 'all',
    status: 'all',
    q: '',
    linkedOnly: false,
    loadedFor: '',
    bound: false,
    diagrams: null,
    templates: [],
    links: [],
    highlightId: '',
  };

  const CATEGORY_FALLBACK = [
    { key: 'server', label: '服务器' },
    { key: 'storage', label: '存储' },
    { key: 'network', label: '网络' },
    { key: 'security', label: '安全' },
    { key: 'software', label: '软件' },
    { key: 'other', label: '其他' },
  ];

  function esc(value) { return TT.esc(value); }

  function nodeLinkText(link) {
    const label = link.node_label || link.node_key || '';
    if (/[×xX]\s*\d+\s*$/.test(label)) return label;
    return label + ' ×' + (link.quantity || 0);
  }

  function money(value) {
    if (value == null || value === '') return '—';
    return '¥' + Number(value).toLocaleString('zh-CN', { maximumFractionDigits: 2 });
  }

  function projectName() {
    return (window.TT_PROJECT && window.TT_PROJECT.name) || '当前项目';
  }

  function setTabCount(count) {
    const el = document.getElementById('tabDeviceCount');
    if (el) el.textContent = count == null ? '' : String(count);
  }

  async function show(projectId, opts) {
    opts = opts || {};
    if (!projectId) return;
    const changed = state.projectId !== projectId;
    state.projectId = projectId;
    if (changed) {
      state.category = 'all';
      state.status = 'all';
      state.q = '';
      state.linkedOnly = false;
      state.loadedFor = '';
      state.diagrams = null;
      state.items = [];
      state.summary = null;
      state.categories = [];
      state.statuses = [];
    }
    state.highlightId = opts.device || '';
    if (opts.device) {
      state.highlightId = opts.device;
      state.category = 'all';
      state.status = 'all';
      state.q = '';
      state.linkedOnly = false;
    }
    bindStatic();
    syncFilterUi();
    await load();
    if (opts.device) highlightDevice(opts.device);
  }

  function bindStatic() {
    if (state.bound) return;
    state.bound = true;

    let timer = null;
    const search = $('#deviceSearch');
    if (search) search.addEventListener('input', () => {
      clearTimeout(timer);
      timer = setTimeout(() => { state.q = search.value.trim(); load(); }, 160);
    });
    const status = $('#deviceStatusFilter');
    if (status) status.addEventListener('change', () => { state.status = status.value; load(); });
    const unlinked = $('#deviceUnlinkedFilter');
    if (unlinked) unlinked.addEventListener('change', () => { state.linkedOnly = unlinked.checked; load(); });
    const catRow = $('#deviceCatRow');
    if (catRow) catRow.addEventListener('click', (ev) => {
      const btn = ev.target.closest('[data-category]');
      if (!btn) return;
      state.category = btn.dataset.category;
      syncFilterUi();
      load();
    });
    const add = $('#btnNewDevice');
    if (add) add.addEventListener('click', () => openModal(null));
    const body = $('#deviceTableBody');
    if (body) body.addEventListener('click', (ev) => {
      if (ev.target.closest('[data-node-link]')) return;
      const row = ev.target.closest('tr[data-device-id]');
      if (!row) return;
      const item = state.items.find((d) => d.id === row.dataset.deviceId);
      if (item) openModal(item);
    });
    const exportBtn = $('#btnExportDevices');
    if (exportBtn) exportBtn.addEventListener('click', (ev) => {
      if (!exportBtn.getAttribute('href') || exportBtn.getAttribute('href') === '#') ev.preventDefault();
    });
  }

  function syncFilterUi() {
    const search = $('#deviceSearch');
    if (search && search.value !== state.q) search.value = state.q;
    const status = $('#deviceStatusFilter');
    if (status) status.value = state.status;
    const unlinked = $('#deviceUnlinkedFilter');
    if (unlinked) unlinked.checked = state.linkedOnly;
  }

  async function load() {
    if (!state.projectId) return;
    const projectId = state.projectId;
    const seq = ++loadSeq;
    const body = $('#deviceTableBody');
    if (body && !state.items.length) {
      body.innerHTML = '<tr><td colspan="8"><div class="task-loading"><span class="spinner"></span>正在加载设备…</div></td></tr>';
    }
    const params = new URLSearchParams({ project_id: state.projectId });
    if (state.category && state.category !== 'all') params.set('category', state.category);
    if (state.status && state.status !== 'all') params.set('status', state.status);
    if (state.q) params.set('q', state.q);
    if (state.linkedOnly) params.set('linked', 'no');
    try {
      const data = await TT.api('/api/devices?' + params.toString());
      if (seq !== loadSeq || state.projectId !== projectId) return;
      state.items = data.items || [];
      state.summary = data.summary || null;
      state.categories = data.categories || [];
      state.statuses = data.statuses || [];
      state.loadedFor = state.projectId;
      render();
      const exportBtn = $('#btnExportDevices');
      if (exportBtn) exportBtn.href = '/api/projects/' + encodeURIComponent(state.projectId) + '/devices/export.csv';
    } catch (err) {
      if (seq !== loadSeq || state.projectId !== projectId) return;
      if (body) body.innerHTML = '<tr><td colspan="8"><div class="empty-inline">设备加载失败：' + esc(err.message) + '</div></td></tr>';
      TT.toast('设备加载失败：' + err.message, 'error');
    }
  }

  function render() {
    renderSummary();
    renderCategories();
    renderTable();
    renderFoot();
    setTabCount(state.summary ? state.summary.types : 0);
  }

  function renderSummary() {
    const box = $('#deviceSummary');
    if (!box) return;
    const s = state.summary || { types: 0, quantity: 0, linked_types: 0, node_count: 0, diagram_count: 0, amount: 0 };
    box.innerHTML = `
      <div class="dev-stat"><span>设备种类</span><b>${s.types || 0}</b><em>${state.categories.filter(c => c.count).length || 0} 个类别</em></div>
      <div class="dev-stat"><span>总数量</span><b>${s.quantity || 0}</b><em>台 / 套 / 节点</em></div>
      <div class="dev-stat"><span>已关联拓扑</span><b>${s.linked_types || 0} <small>/ ${s.types || 0}</small></b><em>${s.node_count || 0} 个节点 · ${s.diagram_count || 0} 张图</em></div>
      <div class="dev-stat money"><span>预估金额</span><b>${money(s.amount || 0)}</b><em>含税口径待确认 · 仅方案估算</em></div>`;
  }

  function renderCategories() {
    const box = $('#deviceCatRow');
    if (!box) return;
    const categories = state.categories.length ? state.categories : CATEGORY_FALLBACK.map((c) => ({ ...c, count: 0 }));
    const total = state.summary ? state.summary.types : 0;
    box.innerHTML = `<button type="button" class="dev-cat-filter ${state.category === 'all' ? 'active' : ''}" data-category="all">全部 <b>${total}</b></button>` +
      categories.map((c) => `<button type="button" class="dev-cat-filter ${state.category === c.key ? 'active' : ''}" data-category="${esc(c.key)}">${esc(c.label)} <b>${c.count || 0}</b></button>`).join('') +
      '<span class="dev-order">按类别排序</span>';
  }

  function renderTable() {
    const body = $('#deviceTableBody');
    if (!body) return;
    if (!state.items.length) {
      body.innerHTML = `<tr><td colspan="8"><div class="dev-empty">
        <b>还没有设备</b>
        <span>先新增设备，或在拓扑图节点上「新建并关联设备」。</span>
        <button type="button" class="btn btn-primary btn-sm" data-empty-new>新增设备</button>
      </div></td></tr>`;
      const empty = body.querySelector('[data-empty-new]');
      if (empty) empty.onclick = () => openModal(null);
      return;
    }
    body.innerHTML = state.items.map(deviceRow).join('');
    state.items.forEach((item) => {
      const row = body.querySelector(`tr[data-device-id="${item.id}"]`);
      if (!row) return;
      if (state.highlightId === item.id) row.classList.add('highlight');
    });
  }

  function deviceRow(d) {
    const linked = (d.linked_nodes || []).map((link) => `
      <a class="dev-node" data-node-link title="本节点 ×${link.quantity || 0}" href="/projects/${encodeURIComponent(state.projectId)}/diagrams/${encodeURIComponent(link.diagram_id)}?node=${encodeURIComponent(link.node_key)}">
        <svg viewBox="0 0 24 24" fill="none"><circle cx="6" cy="6" r="2.5"/><circle cx="18" cy="7" r="2.5"/><circle cx="12" cy="18" r="2.5"/><path d="M8.3 7.2 15.7 8.8M7.4 8.2l3.4 7.4M17 9.3l-3.7 6.4"/></svg>
        <span>${esc(link.diagram_name || '拓扑图')} · ${esc(nodeLinkText(link))}</span>
      </a>`).join('');
    return `<tr data-device-id="${esc(d.id)}">
      <td><div class="dev-name">${esc(d.name)}</div><div class="dev-model">${esc([d.brand, d.model].filter(Boolean).join(' ') || '未填写品牌型号')}</div></td>
      <td><span class="dev-cat ${esc(d.category)}">${esc(d.category_label || d.category)}</span></td>
      <td class="dev-spec">${esc(d.spec || '—')}</td>
      <td class="dev-qty"><b>${d.quantity || 0}</b> ${esc(d.unit || '台')}</td>
      <td><span class="dev-status ${esc(d.status)}">${esc(d.status_label || d.status)}</span></td>
      <td>${linked ? '<div class="dev-node-list">' + linked + '</div>' : '<span class="dev-unlinked">未关联</span>'}</td>
      <td class="dev-money">${d.total == null ? '—' : money(d.total)}${d.unit_price == null ? '<small>未填单价</small>' : ''}</td>
      <td class="dev-row-actions"><button type="button" data-device-edit="${esc(d.id)}" title="编辑">⋯</button></td>
    </tr>`;
  }

  function renderFoot() {
    const box = $('#deviceFoot');
    if (!box) return;
    const s = state.summary || {};
    box.innerHTML = `<span>共 <b>${s.types || 0}</b> 种设备 · 数量合计 <b>${s.quantity || 0}</b> · 已关联拓扑 <b>${s.linked_types || 0}</b> 种 / <b>${s.node_count || 0}</b> 个节点</span>` +
      `<span>预估金额 <b>${money(s.amount || 0)}</b> · 仅用于方案估算</span>`;
  }

  function highlightDevice(id) {
    const row = document.querySelector('#deviceTableBody tr[data-device-id="' + id + '"]');
    if (!row) return;
    row.scrollIntoView({ block: 'center', behavior: 'smooth' });
    row.classList.add('highlight');
    setTimeout(() => row.classList.remove('highlight'), 2800);
  }

  // ------------------------------------------------------------------ modal
  async function openModal(device) {
    const isEdit = !!device;
    state.links = (device && device.linked_nodes ? device.linked_nodes : []).map((link) => ({
      diagram_id: link.diagram_id,
      diagram_name: link.diagram_name || '',
      node_key: link.node_key,
      node_label: link.node_label || link.node_key,
      quantity: link.quantity == null ? 1 : link.quantity,
    }));
    try {
      const requests = [
        TT.api('/api/diagrams?project_id=' + encodeURIComponent(state.projectId)),
      ];
      if (!isEdit) requests.push(TT.api('/api/device-templates'));
      const results = await Promise.all(requests);
      state.diagrams = results[0].items || [];
      if (!isEdit) state.templates = (results[1] && results[1].items) || [];
    } catch (err) {
      state.diagrams = state.diagrams || [];
      if (!isEdit) state.templates = [];
    }
    if (!state.categories.length) state.categories = CATEGORY_FALLBACK;
    if (!state.statuses.length) state.statuses = [
      { key: 'planned', label: '规划中' }, { key: 'selected', label: '已选型' },
      { key: 'quoted', label: '已报价' }, { key: 'ordered', label: '已下单' },
      { key: 'delivered', label: '已到货' },
    ];

    const modal = TT.modal({
      title: isEdit ? '编辑设备' : '新增设备',
      subtitle: '设备属于「' + projectName() + '」。关联拓扑节点后，节点左上角会显示设备角标。',
      width: 760,
      body: formHtml(device),
      submitText: isEdit ? '保存设备' : '创建设备',
      onSubmit: async (fd) => {
        const name = String(fd.get('name') || '').trim();
        if (!name) throw new Error('设备名称不能为空');
        const payload = {
          name,
          category: fd.get('category'),
          brand: String(fd.get('brand') || ''),
          model: String(fd.get('model') || ''),
          spec: String(fd.get('spec') || ''),
          quantity: Number(fd.get('quantity') || 0),
          unit: fd.get('unit'),
          status: fd.get('status'),
          unit_price: String(fd.get('unit_price') || '').trim() === '' ? null : Number(fd.get('unit_price')),
          vendor: String(fd.get('vendor') || ''),
          owner: String(fd.get('owner') || ''),
          note: String(fd.get('note') || ''),
          links: state.links,
        };
        if (isEdit) {
          await TT.api('/api/devices/' + encodeURIComponent(device.id), { method: 'PATCH', body: payload });
        } else {
          payload.project_id = state.projectId;
          await TT.api('/api/devices', { method: 'POST', body: payload });
        }
        TT.toast(isEdit ? '设备已更新' : '设备已创建', 'success');
        document.dispatchEvent(new CustomEvent('tt:devices-changed', { detail: { projectId: state.projectId } }));
        await load();
      },
    });
    modal.form.closest('.modal').classList.add('dev-modal');
    bindModal(modal, device);
  }

  function formHtml(device) {
    const d = device || {};
    const categories = state.categories.length ? state.categories : CATEGORY_FALLBACK;
    const statuses = state.statuses.length ? state.statuses : [
      { key: 'planned', label: '规划中' }, { key: 'selected', label: '已选型' },
      { key: 'quoted', label: '已报价' }, { key: 'ordered', label: '已下单' },
      { key: 'delivered', label: '已到货' },
    ];
    const categoryOptions = categories.map((c) =>
      `<option value="${esc(c.key)}" ${d.category === c.key ? 'selected' : ''}>${esc(c.label)}</option>`).join('');
    const statusOptions = statuses.map((s) =>
      `<option value="${esc(s.key)}" ${(d.status || 'planned') === s.key ? 'selected' : ''}>${esc(s.label)}</option>`).join('');
    const units = ['台', '套', '节点', '个', '块'];
    const unitOptions = units.map((u) => `<option value="${u}" ${(d.unit || '台') === u ? 'selected' : ''}>${u}</option>`).join('');
    const diagramOptions = (state.diagrams || []).map((diagram) =>
      `<option value="${esc(diagram.id)}">${esc(diagram.name)}</option>`).join('');
    const templateOptions = (state.templates || []).map((template) =>
      `<option value="${esc(template.id)}">${esc(template.display_label || template.name || '')}</option>`).join('');
    const templatePicker = device ? '' : `<div class="dev-tpl-picker">
      <div class="dev-tpl-head"><b>从设备模板开始</b><a href="/device-templates" target="_blank" rel="noopener">管理模板</a></div>
      <div class="dev-tpl-search">
        <svg viewBox="0 0 24 24" fill="none"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>
        <input id="devTplSearch" placeholder="搜索模板名称、品牌、型号…" autocomplete="off">
      </div>
      <div class="dev-tpl-row">
        <select id="devTplSelect"><option value="">${state.templates.length ? '不使用模板，直接填写' : '模板库为空，可直接填写'}</option>${templateOptions}</select>
        <button type="button" id="devTplClear">清空</button>
      </div>
      <div class="dev-tpl-hint" id="devTplHint">选择模板会带入字段，可继续按项目修改；不会修改模板。</div>
    </div>`;
    return `${templatePicker}<div class="form-grid">
      <div class="field"><label>设备名称 *</label><input name="name" required maxlength="160" value="${esc(d.name || '')}"></div>
      <div class="field"><label>类别 *</label><select name="category">${categoryOptions}</select></div>
      <div class="field"><label>品牌</label><input name="brand" maxlength="80" value="${esc(d.brand || '')}"></div>
      <div class="field"><label>型号</label><input name="model" maxlength="120" value="${esc(d.model || '')}"></div>
      <div class="field full"><label>关键参数 / 配置</label><textarea name="spec">${esc(d.spec || '')}</textarea></div>
      <div class="field"><label>数量 *</label><input name="quantity" type="number" min="0" step="1" value="${d.quantity == null ? 1 : d.quantity}"></div>
      <div class="field"><label>单位</label><select name="unit">${unitOptions}</select></div>
      <div class="field"><label>状态</label><select name="status">${statusOptions}</select></div>
      <div class="field"><label>单价（元）</label><input name="unit_price" type="number" min="0" step="0.01" value="${d.unit_price == null ? '' : d.unit_price}"></div>
      <div class="field"><label>供应商</label><input name="vendor" maxlength="120" value="${esc(d.vendor || '')}"></div>
      <div class="field"><label>负责人</label><input name="owner" maxlength="80" value="${esc(d.owner || '')}"></div>
      <div class="field full"><label>备注</label><textarea name="note">${esc(d.note || '')}</textarea></div>
      <div class="field full">
        <label>关联拓扑节点 <span class="dev-count" id="devLinkCount">${state.links.length} 个</span></label>
        <div class="node-links-box">
          <div id="devNodeChips" style="display:flex;flex-wrap:wrap;gap:6px;width:100%"></div>
          <div class="node-link-controls" style="width:100%">
            <select id="devDiagramSelect"><option value="">选择拓扑图…</option>${diagramOptions}</select>
            <select id="devNodeSelect" disabled><option value="">先选拓扑图</option></select>
            <button type="button" id="devAddLink">添加关联</button>
          </div>
        </div>
        <small class="dev-hint">一个设备可以关联同一张或多张拓扑图里的多个节点；节点删除后关联会自动清理。</small>
      </div>
    </div>`;
  }

  async function bindModal(modal, device) {
    const form = modal.form;
    const chips = form.querySelector('#devNodeChips');
    const diagramSelect = form.querySelector('#devDiagramSelect');
    const nodeSelect = form.querySelector('#devNodeSelect');
    const addBtn = form.querySelector('#devAddLink');
    const count = form.querySelector('#devLinkCount');

    const renderChips = () => {
      if (!chips) return;
      chips.innerHTML = state.links.length ? state.links.map((link, index) => `
        <span class="node-chip" title="本节点 ×${link.quantity}">
          <b>${esc(link.diagram_name || '拓扑图')}</b><em>/ ${esc(nodeLinkText(link))}</em>
          <button type="button" data-remove-link="${index}" title="取消关联">×</button>
        </span>`).join('') : '<span class="dev-hint">尚未关联拓扑节点</span>';
      if (count) count.textContent = state.links.length + ' 个';
    };
    renderChips();

    const tplSelect = form.querySelector('#devTplSelect');
    const tplSearch = form.querySelector('#devTplSearch');
    const tplClear = form.querySelector('#devTplClear');
    const tplHint = form.querySelector('#devTplHint');
    const field = (name) => form.querySelector('[name="' + name + '"]');
    const applyTemplate = (template) => {
      if (!template) return;
      field('name').value = template.name || template.display_label || '';
      field('category').value = template.category || 'other';
      field('brand').value = template.brand || '';
      field('model').value = template.model || '';
      field('spec').value = template.spec || '';
      field('unit').value = template.unit || '台';
      field('unit_price').value = template.unit_price == null ? '' : template.unit_price;
      field('note').value = template.note || '';
      if (tplHint) tplHint.textContent = `已带入模板「${template.display_label || template.name}」；可继续按项目修改，不会修改模板。`;
    };
    const renderTemplateOptions = () => {
      if (!tplSelect) return;
      const keyword = (tplSearch && tplSearch.value || '').trim().toLowerCase();
      const selected = tplSelect.value;
      const list = (state.templates || []).filter((template) => {
        if (!keyword) return true;
        return [template.display_label, template.name, template.brand, template.model, template.spec, template.category_label]
          .filter(Boolean).join(' ').toLowerCase().includes(keyword);
      });
      tplSelect.innerHTML = '<option value="">' +
        (state.templates.length ? '不使用模板，直接填写' : '模板库为空，可直接填写') + '</option>' +
        list.map((template) => `<option value="${esc(template.id)}">${esc(template.display_label || template.name || '')}</option>`).join('');
      if (selected && list.some((template) => template.id === selected)) tplSelect.value = selected;
    };
    if (tplSelect) {
      renderTemplateOptions();
      if (tplSearch) tplSearch.addEventListener('input', renderTemplateOptions);
      tplSelect.addEventListener('change', () => {
        const template = (state.templates || []).find((item) => item.id === tplSelect.value);
        if (template) applyTemplate(template);
      });
      if (tplClear) tplClear.addEventListener('click', () => {
        tplSelect.value = '';
        ['name', 'brand', 'model', 'spec', 'unit_price', 'note'].forEach((key) => {
          const el = field(key);
          if (el) el.value = '';
        });
        if (tplHint) tplHint.textContent = '已清空模板字段；可填写一台全新的设备。';
      });
    }

    if (chips) chips.addEventListener('click', (ev) => {
      const btn = ev.target.closest('[data-remove-link]');
      if (!btn) return;
      state.links.splice(Number(btn.dataset.removeLink), 1);
      renderChips();
    });

    if (diagramSelect) diagramSelect.addEventListener('change', async () => {
      const diagramId = diagramSelect.value;
      nodeSelect.innerHTML = '<option value="">加载节点…</option>';
      nodeSelect.disabled = true;
      if (!diagramId) {
        nodeSelect.innerHTML = '<option value="">先选拓扑图</option>';
        return;
      }
      try {
        const data = await TT.api('/api/diagrams/' + encodeURIComponent(diagramId) + '/nodes');
        const nodes = data.items || [];
        nodeSelect.innerHTML = nodes.length
          ? '<option value="">选择节点…</option>' + nodes.map((node) =>
            `<option value="${esc(node.node_key)}">${esc(node.label || node.node_key)}</option>`).join('')
          : '<option value="">该图还没有保存节点</option>';
        nodeSelect.disabled = !nodes.length;
      } catch (err) {
        nodeSelect.innerHTML = '<option value="">节点加载失败</option>';
      }
    });

    if (addBtn) addBtn.addEventListener('click', () => {
      const diagramId = diagramSelect.value;
      const nodeKey = nodeSelect.value;
      if (!diagramId || !nodeKey) { TT.toast('先选择拓扑图和节点', 'error'); return; }
      const diagram = (state.diagrams || []).find((item) => item.id === diagramId);
      const nodeLabel = nodeSelect.options[nodeSelect.selectedIndex].textContent;
      const quantity = Math.max(0, Number(form.querySelector('[name="quantity"]').value || 1));
      const existing = state.links.find((link) => link.diagram_id === diagramId && link.node_key === nodeKey);
      if (existing) {
        existing.quantity = quantity;
      } else {
        state.links.push({
          diagram_id: diagramId,
          diagram_name: diagram ? diagram.name : '',
          node_key: nodeKey,
          node_label: nodeLabel,
          quantity,
        });
      }
      renderChips();
    });

    if (device) {
      const actions = form.querySelector('.modal-actions');
      if (actions) {
        const del = document.createElement('button');
        del.type = 'button';
        del.className = 'btn btn-sm dev-delete-btn';
        del.textContent = '删除设备';
        del.style.marginRight = 'auto';
        actions.insertBefore(del, actions.firstChild);
        del.addEventListener('click', () => {
          TT.confirm(`删除设备「${device.name}」？设备与拓扑节点的关联会一起清理，且不可恢复。`, async () => {
            await TT.api('/api/devices/' + encodeURIComponent(device.id), { method: 'DELETE' });
            modal.close();
            TT.toast('设备已删除', 'success');
            document.dispatchEvent(new CustomEvent('tt:devices-changed', { detail: { projectId: state.projectId } }));
            await load();
          }, { title: '删除设备', submitText: '删除' });
        });
      }
    }
  }

  window.TTDevices = {
    show,
    refresh: load,
  };
})();
