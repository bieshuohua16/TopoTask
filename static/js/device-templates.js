/* Global device template library */
(function () {
  'use strict';
  const TT = window.TT;
  if (!TT) return;

  const $ = (selector) => document.querySelector(selector);
  const state = {
    items: [],
    summary: null,
    categories: [],
    brands: [],
    category: 'all',
    brand: 'all',
    q: '',
    preview: null,
    file: null,
    bound: false,
    loadSeq: 0,
  };

  const CATEGORY_FALLBACK = [
    { key: 'server', label: '服务器' },
    { key: 'storage', label: '存储' },
    { key: 'network', label: '网络' },
    { key: 'security', label: '安全' },
    { key: 'software', label: '软件' },
    { key: 'other', label: '其他' },
  ];
  const UNITS = ['台', '套', '节点', '个', '块'];

  function esc(value) { return TT.esc(value); }

  function money(value) {
    if (value == null || value === '') return '—';
    return '¥' + Number(value).toLocaleString('zh-CN', { maximumFractionDigits: 2 });
  }

  async function load() {
    const seq = ++state.loadSeq;
    const params = new URLSearchParams();
    if (state.category && state.category !== 'all') params.set('category', state.category);
    if (state.brand && state.brand !== 'all') params.set('brand', state.brand);
    if (state.q) params.set('q', state.q);
    try {
      const data = await TT.api('/api/device-templates?' + params.toString());
      if (seq !== state.loadSeq) return;
      state.items = data.items || [];
      state.summary = data.summary || {};
      state.categories = data.categories || [];
      state.brands = data.brands || [];
      render();
    } catch (err) {
      TT.toast('设备模板加载失败：' + err.message, 'error');
    }
  }

  function render() {
    renderSummary();
    renderCategories();
    renderBrands();
    renderTable();
    renderFoot();
  }

  function renderSummary() {
    const box = $('#templateSummary');
    if (!box) return;
    const s = state.summary || { total: 0, categories: 0, brands: 0 };
    box.innerHTML = `
      <div class="dev-stat tpl-stat">
        <span class="tpl-stat-icon"><svg viewBox="0 0 24 24" fill="none"><path d="M4 7.5 12 4l8 3.5v9L12 20l-8-3.5v-9Z"/><path d="m4 7.5 8 3.5 8-3.5M12 11v9"/></svg></span>
        <div><span>模板数量</span><b>${s.total || 0}</b><em>可复用的设备预设</em></div>
      </div>
      <div class="dev-stat tpl-stat">
        <span class="tpl-stat-icon"><svg viewBox="0 0 24 24" fill="none"><rect x="4" y="4" width="7" height="7" rx="2"/><rect x="13" y="4" width="7" height="7" rx="2"/><rect x="4" y="13" width="7" height="7" rx="2"/><rect x="13" y="13" width="7" height="7" rx="2"/></svg></span>
        <div><span>覆盖类别</span><b>${s.categories || 0}</b><em>服务器 / 网络 / 安全…</em></div>
      </div>
      <div class="dev-stat tpl-stat">
        <span class="tpl-stat-icon"><svg viewBox="0 0 24 24" fill="none"><path d="M4 20V6a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v14"/><path d="M8 8h8M8 12h5M8 16h8"/></svg></span>
        <div><span>覆盖品牌</span><b>${s.brands || 0}</b><em>${esc((state.brands || []).slice(0, 3).join(' / ') || '暂无品牌')}</em></div>
      </div>`;
  }

  function renderCategories() {
    const box = $('#templateCatRow');
    if (!box) return;
    const categories = state.categories.length ? state.categories : CATEGORY_FALLBACK.map((c) => ({ ...c, count: 0 }));
    const total = state.summary ? state.summary.total : 0;
    box.innerHTML = `<button type="button" class="dev-cat-filter ${state.category === 'all' ? 'active' : ''}" data-tpl-category="all">全部 <b>${total}</b></button>` +
      categories.map((c) => `<button type="button" class="dev-cat-filter ${state.category === c.key ? 'active' : ''}" data-tpl-category="${esc(c.key)}">${esc(c.label)} <b>${c.count || 0}</b></button>`).join('') +
      '<span class="dev-order">按更新时间排序</span>';
  }

  function renderBrands() {
    const select = $('#templateBrandFilter');
    if (!select) return;
    if (state.brand !== 'all' && !state.brands.includes(state.brand)) state.brand = 'all';
    select.innerHTML = '<option value="all">全部品牌</option>' +
      state.brands.map((brand) => `<option value="${esc(brand)}" ${state.brand === brand ? 'selected' : ''}>${esc(brand)}</option>`).join('');
  }

  function renderTable() {
    const body = $('#templateTableBody');
    if (!body) return;
    if (!state.items.length) {
      body.innerHTML = `<tr><td colspan="8"><div class="tpl-empty">
        <b>还没有设备模板</b>
        <span>新增模板，或从 CSV 导入一批常用设备。</span>
      </div></td></tr>`;
      return;
    }
    body.innerHTML = state.items.map((template) => `
      <tr data-template-id="${esc(template.id)}">
        <td><div class="dev-name">${esc(template.model || '未填写型号')}</div></td>
        <td><span class="dev-cat ${esc(template.category)}">${esc(template.category_label || template.category)}</span></td>
        <td class="tpl-brand">${esc(template.brand || '—')}</td>
        <td class="dev-spec">${esc(template.spec || '—')}</td>
        <td class="tpl-unit">${esc(template.unit || '台')}</td>
        <td class="dev-money">${money(template.unit_price)}</td>
        <td class="tpl-date">${TT.relative(template.updated_at)}</td>
        <td><div class="tpl-row-actions">
          <button type="button" data-tpl-edit="${esc(template.id)}">编辑</button>
          <button type="button" class="danger" data-tpl-delete="${esc(template.id)}">删除</button>
        </div></td>
      </tr>`).join('') + '';
  }

  function renderFoot() {
    const box = $('#templateFoot');
    if (!box) return;
    const s = state.summary || {};
    box.innerHTML = `<span>共 <b>${s.total || 0}</b> 个模板 · ${s.categories || 0} 个类别 · ${s.brands || 0} 个品牌</span>` +
      `<span>${s.updated_at ? '最近更新 ' + TT.relative(s.updated_at) : '模板全局共享，不绑定项目'}</span>`;
  }

  function bind() {
    if (state.bound) return;
    state.bound = true;
    let timer = null;
    const search = $('#templateSearch');
    if (search) search.addEventListener('input', () => {
      clearTimeout(timer);
      timer = setTimeout(() => { state.q = search.value.trim(); load(); }, 160);
    });
    const brand = $('#templateBrandFilter');
    if (brand) brand.addEventListener('change', () => { state.brand = brand.value; load(); });
    const catRow = $('#templateCatRow');
    if (catRow) catRow.addEventListener('click', (ev) => {
      const btn = ev.target.closest('[data-tpl-category]');
      if (!btn) return;
      state.category = btn.dataset.tplCategory;
      load();
    });
    const newBtn = $('#btnNewTemplate');
    if (newBtn) newBtn.onclick = () => openEditor(null);
    const importBtn = $('#btnImportTemplates');
    if (importBtn) importBtn.onclick = openImport;
    const body = $('#templateTableBody');
    if (body) body.addEventListener('click', (ev) => {
      const edit = ev.target.closest('[data-tpl-edit]');
      if (edit) {
        const item = state.items.find((t) => t.id === edit.dataset.tplEdit);
        if (item) openEditor(item);
        return;
      }
      const del = ev.target.closest('[data-tpl-delete]');
      if (del) {
        const item = state.items.find((t) => t.id === del.dataset.tplDelete);
        if (item) deleteTemplate(item);
        return;
      }
      const row = ev.target.closest('tr[data-template-id]');
      if (!row) return;
      const item = state.items.find((t) => t.id === row.dataset.templateId);
      if (item) openEditor(item);
    });
  }

  function openEditor(template) {
    const isEdit = !!template;
    const t = template || {};
    const categories = state.categories.length ? state.categories : CATEGORY_FALLBACK.map((c) => ({ ...c, count: 0 }));
    const currentCategory = t.category || 'server';
    const categoryOptions = categories.map((c) =>
      `<option value="${esc(c.key)}" ${currentCategory === c.key ? 'selected' : ''}>${esc(c.label)}</option>`).join('');
    const unitOptions = UNITS.map((unit) =>
      `<option value="${unit}" ${(t.unit || '台') === unit ? 'selected' : ''}>${unit}</option>`).join('');
    const modal = TT.modal({
      title: isEdit ? '编辑设备模板' : '新增设备模板',
      subtitle: '模板全局共享；项目设备只是复制字段，不会反向修改模板。',
      width: 600,
      submitText: isEdit ? '保存模板' : '创建模板',
      body: `<div class="form-grid">
        <div class="field"><label>类别 *</label><select name="category">${categoryOptions}</select></div>
        <div class="field"><label>品牌</label><input name="brand" maxlength="80" value="${esc(t.brand || '')}"></div>
        <div class="field"><label>型号</label><input name="model" maxlength="120" value="${esc(t.model || '')}"></div>
        <div class="field"><label>默认单位</label><select name="unit">${unitOptions}</select></div>
        <div class="field full"><label>关键参数 / 配置</label><textarea name="spec">${esc(t.spec || '')}</textarea></div>
        <div class="field"><label>参考单价（元）</label><input name="unit_price" type="number" min="0" step="0.01" value="${t.unit_price == null ? '' : t.unit_price}"></div>
        <div class="field full"><label>备注</label><textarea name="note">${esc(t.note || '')}</textarea></div>
      </div>`,
      onSubmit: async (fd) => {
        const payload = {
          category: fd.get('category'),
          brand: String(fd.get('brand') || ''),
          model: String(fd.get('model') || ''),
          spec: String(fd.get('spec') || ''),
          unit: fd.get('unit'),
          unit_price: String(fd.get('unit_price') || '').trim() === '' ? null : Number(fd.get('unit_price')),
          note: String(fd.get('note') || ''),
        };
        if (isEdit) {
          await TT.api('/api/device-templates/' + encodeURIComponent(template.id), { method: 'PATCH', body: payload });
        } else {
          await TT.api('/api/device-templates', { method: 'POST', body: payload });
        }
        TT.toast(isEdit ? '模板已更新' : '模板已创建', 'success');
        await load();
      },
    });
    modal.form.closest('.modal').classList.add('tpl-edit-modal');
    if (isEdit) {
      const actions = modal.form.querySelector('.modal-actions');
      if (!actions) return;
      const del = document.createElement('button');
      del.type = 'button';
      del.className = 'btn btn-sm dev-delete-btn';
      del.textContent = '删除模板';
      del.style.marginRight = 'auto';
      actions.insertBefore(del, actions.firstChild);
      del.onclick = () => deleteTemplate(template, modal);
    }
  }

  function deleteTemplate(template, parentModal) {
    TT.confirm(`删除模板「${template.name}」？已经创建到项目里的设备不受影响。`, async () => {
      await TT.api('/api/device-templates/' + encodeURIComponent(template.id), { method: 'DELETE' });
      if (parentModal) parentModal.close();
      TT.toast('模板已删除', 'success');
      await load();
    }, { title: '删除设备模板', submitText: '删除' });
  }

  async function upload(path, formData) {
    const res = await fetch(path, { method: 'POST', body: formData });
    const raw = await res.text();
    let data = null;
    try { data = raw ? JSON.parse(raw) : null; } catch (err) { data = null; }
    if (!res.ok) throw new Error((data && data.error && data.error.message) || raw || ('HTTP ' + res.status));
    return data;
  }

  function openImport() {
    state.file = null;
    state.preview = null;
    const modal = TT.modal({
      title: '导入设备模板',
      subtitle: '使用 UTF-8 / UTF-8 BOM 编码；第一行必须是表头。建议先下载系统 CSV 模板。',
      width: 760,
      submitText: '导入',
      body: `<label class="tpl-drop" for="tplFile">
          <input id="tplFile" type="file" accept=".csv,text/csv" style="display:none">
          <span class="tpl-drop-icon"><svg viewBox="0 0 24 24" fill="none"><path d="M12 16V4"/><path d="m7 9 5-5 5 5"/><path d="M5 20h14"/></svg></span>
          <b>拖入 CSV 或点击选择文件</b>
          <span>支持 .csv，最大 2 MB</span>
        </label>
        <div class="tpl-file" id="tplFileInfo" hidden>
          <svg viewBox="0 0 24 24" fill="none" style="width:15px;height:15px;color:#7c879a"><path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9Z"/><path d="M14 3v6h6"/></svg>
          <b id="tplFileName"></b><span id="tplFileSize"></span>
        </div>
        <div class="tpl-preview-head"><b>导入预览</b><span id="tplPreviewSummary">选择 CSV 后显示预览。</span><a href="/api/device-templates/sample.csv">下载标准 CSV 模板</a></div>
        <div id="tplPreview"></div>
        <div class="tpl-import-options">
          <span>重复项处理</span>
          <label><input type="radio" name="tplMode" value="skip" checked> 跳过重复（推荐）</label>
          <label><input type="radio" name="tplMode" value="overwrite"> 覆盖更新已有模板</label>
        </div>
        <div class="tpl-import-hint">重复判定：品牌 + 型号相同。CSV 列：类别、品牌、型号、关键参数、单位、参考单价、备注；类别可写中文。</div>`,
      onSubmit: async () => {
        if (!state.file) throw new Error('请选择要导入的 CSV 文件');
        const mode = (modal.form.querySelector('input[name="tplMode"]:checked') || {}).value || 'skip';
        const fd = new FormData();
        fd.append('file', state.file);
        fd.append('mode', mode);
        const result = await upload('/api/device-templates/import', fd);
        TT.toast(`导入完成：新增 ${result.imported || 0} 条 · 更新 ${result.updated || 0} 条 · 跳过 ${result.skipped || 0} 条`, 'success');
        await load();
      },
    });
    modal.form.closest('.modal').classList.add('tpl-import-modal');
    const fileInput = modal.form.querySelector('#tplFile');
    const preview = modal.form.querySelector('#tplPreview');
    const previewSummary = modal.form.querySelector('#tplPreviewSummary');
    const fileInfo = modal.form.querySelector('#tplFileInfo');
    const fileName = modal.form.querySelector('#tplFileName');
    const fileSize = modal.form.querySelector('#tplFileSize');
    const submit = modal.form.querySelector('button[type="submit"]');

    const refreshSubmitLabel = () => {
      if (!submit) return;
      if (!state.preview) { submit.textContent = '导入'; return; }
      const mode = (modal.form.querySelector('input[name="tplMode"]:checked') || {}).value || 'skip';
      const s = state.preview.summary || {};
      const count = (s.new || 0) + (mode === 'overwrite' ? (s.duplicate || 0) : 0);
      submit.textContent = count > 0 ? `导入 ${count} 条` : '导入';
    };

    const previewFile = async () => {
      if (!state.file) return;
      fileInfo.hidden = false;
      fileName.textContent = state.file.name;
      fileSize.textContent = Math.max(1, Math.round(state.file.size / 1024)) + ' KB';
      preview.innerHTML = '<div class="task-loading"><span class="spinner"></span>正在解析 CSV…</div>';
      if (previewSummary) previewSummary.textContent = '正在解析…';
      const fd = new FormData();
      fd.append('file', state.file);
      fd.append('dry_run', '1');
      try {
        const data = await upload('/api/device-templates/import', fd);
        state.preview = data;
        const s = data.summary || {};
        const rows = (data.items || []).slice(0, 8);
        const statusText = { new: '新增', duplicate: '重复', invalid: '错误' };
        if (previewSummary) {
          previewSummary.textContent = `已识别 ${s.total || 0} 行 · ${s.new || 0} 行可导入 · ${s.duplicate || 0} 行重复 · ${s.invalid || 0} 行错误`;
        }
        preview.innerHTML = `<div class="tpl-preview"><table><thead><tr><th>型号</th><th>类别</th><th>品牌</th><th>参考单价</th><th>结果</th></tr></thead><tbody>` +
          (rows.length ? rows.map((row) => `<tr class="${row.status === 'duplicate' ? 'dup' : row.status === 'invalid' ? 'invalid' : ''}">
            <td>${esc(row.model || '—')}</td><td>${esc(row.category_label || '—')}</td><td>${esc(row.brand || '—')}</td>
            <td>${money(row.unit_price)}</td>
            <td class="${row.status === 'new' ? 'tpl-ok' : row.status === 'duplicate' ? 'tpl-dup' : 'tpl-invalid'}">${statusText[row.status] || row.status}${row.error ? '：' + esc(row.error) : ''}</td>
          </tr>`).join('') : '<tr><td colspan="5" class="tpl-import-hint">没有可识别的数据行。</td></tr>') +
          '</tbody></table></div>' +
          ((data.items || []).length > 8 ? '<div class="tpl-import-hint">预览只显示前 8 行，导入时会处理全部数据。</div>' : '');
        state.preview = data;
        refreshSubmitLabel();
      } catch (err) {
        state.preview = null;
        if (previewSummary) previewSummary.textContent = '预览失败';
        preview.innerHTML = '<div class="tpl-import-hint tpl-invalid">' + esc(err.message) + '</div>';
        refreshSubmitLabel();
      }
    };

    if (fileInput) fileInput.addEventListener('change', () => {
      state.file = fileInput.files && fileInput.files[0] ? fileInput.files[0] : null;
      if (!state.file) {
        fileInfo.hidden = true;
        state.preview = null;
        if (previewSummary) previewSummary.textContent = '选择 CSV 后显示预览。';
        preview.innerHTML = '';
        refreshSubmitLabel();
        return;
      }
      previewFile();
    });
    const drop = modal.form.querySelector('.tpl-drop');
    if (drop) {
      ['dragenter', 'dragover'].forEach((name) => drop.addEventListener(name, (ev) => {
        ev.preventDefault();
        drop.classList.add('drag');
      }));
      ['dragleave', 'drop'].forEach((name) => drop.addEventListener(name, (ev) => {
        ev.preventDefault();
        drop.classList.remove('drag');
      }));
      drop.addEventListener('drop', (ev) => {
        const files = ev.dataTransfer && ev.dataTransfer.files;
        if (!files || !files.length) return;
        state.file = files[0];
        previewFile();
      });
    }
    modal.form.querySelectorAll('input[name="tplMode"]').forEach((radio) => {
      radio.addEventListener('change', refreshSubmitLabel);
    });
  }

  bind();
  load();
})();
