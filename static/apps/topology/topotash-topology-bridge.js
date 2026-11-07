/* TopoTash 拓扑编辑器桥接。
 * 将画布持久化到 SQLite，并增加节点级「待跟进 / 关联任务」控件。
 * 内置编辑器本身的交互保持不变。 */
(function () {
  'use strict';
  const ctx = window.TOPOTASH_CTX;
  if (!ctx) return;

  const PID = ctx.projectId || null;
  const DID = ctx.diagramId;
  const BASE = `/api/diagrams/${encodeURIComponent(DID)}`;
  const STATUS_COLOR = { todo: '#d97706', doing: '#2563eb', done: '#0d9488', none: '#94a3b8' };
  const STATUS_TEXT = { todo: '待跟进', doing: '进行中', done: '已完成', none: '未标记' };
  const STATUS_CLASS = { todo: 'todo', doing: 'doing', done: 'done', none: 'none' };

  let booted = false;
  let saving = false;
  let pending = false;
  let saveTimer = null;
  let revision = 0;
  let project = { projectId: PID, diagramId: DID, diagramName: '拓扑图', stage: 'research' };
  let tasks = [];
  let tasksLoading = false;
  let devices = [];
  let devicesLoading = false;
  let deviceTemplates = [];
  let templatesLoading = false;
  let deviceBusy = false;

  function esc(value) {
    return String(value == null ? '' : value).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  }

  async function api(path, options) {
    const opts = Object.assign({ headers: {} }, options || {});
    if (opts.body && typeof opts.body !== 'string') {
      opts.headers['Content-Type'] = 'application/json';
      opts.body = JSON.stringify(opts.body);
    }
    const res = await fetch(path, opts);
    const raw = await res.text();
    let data = null;
    try { data = raw ? JSON.parse(raw) : null; } catch (e) { data = null; }
    if (!res.ok) throw new Error((data && data.error && data.error.message) || raw || ('HTTP ' + res.status));
    return data;
  }

  function post(type, payload) {
    if (window.parent && window.parent !== window) {
      window.parent.postMessage(Object.assign({ type }, payload || {}), location.origin);
    }
  }

  function hint(text) {
    const el = document.getElementById('statusHint');
    if (el) el.textContent = text;
  }

  // ------------------------------------------------------------ load / save
  function ensureShapeDefaults() {
    for (const id of Object.keys(model.shapes || {})) {
      const s = model.shapes[id];
      if (!s || typeof s !== 'object') continue;
      if (typeof s.kind !== 'string') s.kind = 'rect';
      if (typeof s.text !== 'string') s.text = '';
      if (typeof s.fill !== 'string') s.fill = '#5b6cf0';
      if (typeof s.stroke !== 'string') s.stroke = '#000000';
      if (typeof s.textColor !== 'string') s.textColor = '#1f2329';
      if (typeof s.fontSize !== 'number') s.fontSize = 12.5;
      if (typeof s.fontFamily !== 'string') s.fontFamily = 'Microsoft YaHei';
      if (typeof s.textAlign !== 'string') s.textAlign = 'center';
      if (typeof s.textVAlign !== 'string') s.textVAlign = 'middle';
      if (typeof s.opacity !== 'number') s.opacity = 1;
      if (typeof s.fillOpacity !== 'number') s.fillOpacity = 1;
      if (typeof s.strokeWidth !== 'number') s.strokeWidth = 1.6;
      if (typeof s.radius !== 'number') s.radius = 10;
      if (typeof s.x !== 'number') s.x = 0;
      if (typeof s.y !== 'number') s.y = 0;
      if (typeof s.w !== 'number') s.w = 120;
      if (typeof s.h !== 'number') s.h = 120;
      if (!Array.isArray(s.fields)) s.fields = [];
      if (s.type === 'shape') {
        if (typeof s.bold !== 'boolean') s.bold = false;
        if (typeof s.italic !== 'boolean') s.italic = false;
      }
    }
  }

  function applyDocument(data) {
    model.shapes = data.shapes || {};
    model.order = data.order || Object.keys(model.shapes);
    model.groups = data.groups || {};
    model.imagePool = data.imagePool || {};
    ensureShapeDefaults();
    if (typeof imagePoolMigrate === 'function') imagePoolMigrate();
    if (typeof cleanupGroups === 'function') cleanupGroups();
    if (typeof normalizeShapes === 'function') normalizeShapes();
    state.idc = 0;
    for (const id of Object.keys(model.shapes)) {
      const n = parseInt(String(id).replace(/\D/g, '')) || 0;
      if (n > state.idc) state.idc = n;
    }
    state.sel.clear();
    state.primaryId = null;
    state.history = [];
    state.hIndex = -1;
    state.dirty = false;
    commit();
    state.dirty = false;
    if (typeof fitContent === 'function') fitContent();
    syncProps();
    syncDocTitle();
  }

  async function load() {
    try {
      const data = await api(`${BASE}/content`);
      project = data._topotash || project;
      state.docName = project.diagramName || '拓扑图';
      applyDocument(data);
      document.title = (project.diagramName || '拓扑图') + ' · TopoTash 拓事';
      hint(`TopoTash · ${project.projectName || '未绑定项目'} · 画布自动保存`);
      booted = true;
      render();
      syncProps();
      loadTasks();
      loadDevices();
      loadDeviceTemplates();
      if (ctx.node) selectNode(ctx.node);
      post('topotash:visio-ready', { diagramId: DID });
    } catch (e) {
      hint('加载失败：' + e.message);
      if (typeof showToast === 'function') showToast('加载拓扑图失败：' + e.message, 'error');
      post('topotash:visio-error', { message: e.message });
    }
  }

  function scheduleServerSave(delay) {
    if (!booted) return;
    state.dirty = true;
    syncDocTitle();
    clearTimeout(saveTimer);
    saveTimer = setTimeout(() => saveToServer(false), delay == null ? 900 : delay);
  }

  async function saveToServer(manual) {
    if (!booted) return;
    clearTimeout(saveTimer);
    saveTimer = null;
    if (saving) { pending = true; return; }
    saving = true;
    pending = false;
    const savedRevision = revision;
    post('topotash:visio-saving');
    try {
      const res = await api(`${BASE}/content`, {
        method: 'PUT',
        body: {
          content: {
            app: 'topotash', version: 2,
            shapes: model.shapes, order: model.order,
            groups: model.groups, imagePool: model.imagePool
          }
        }
      });
      state.dirty = revision !== savedRevision;
      syncDocTitle();
      if (state.dirty) {
        pending = true;
        return;
      }
      hint(`已保存 · ${res.node_count} 个节点 · ${new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}`);
      post('topotash:visio-saved', { nodeCount: res.node_count, version: res.version });
      if (manual && typeof showToast === 'function') showToast('已保存到 TopoTash', 'success');
    } catch (e) {
      hint('保存失败：' + e.message);
      if (typeof showToast === 'function') showToast('保存失败：' + e.message, 'error');
      post('topotash:visio-error', { message: e.message });
    } finally {
      saving = false;
      if (pending) { pending = false; scheduleServerSave(150); }
    }
  }

  // Replace the local download-based save with a server save.
  window.saveDoc = function () { saveToServer(true); };
  // The local draft is per-browser; in TopoTash the server is the source of truth.
  window.scheduleAutosave = function () {
    revision += 1;
    scheduleServerSave();
  };
  window.addEventListener('beforeunload', (ev) => {
    if (!state.dirty && !saving) return;
    ev.preventDefault();
    ev.returnValue = '';
  });

  // ------------------------------------------------------------ JSON export
  // Export the live canvas in the same shape as the editor's .vweb.json so the
  // 拓扑图库 / 项目「导入拓扑图」flow can import it again.
  function exportJson() {
    if (typeof model === 'undefined' || !model) {
      if (typeof showToast === 'function') showToast('画布尚未就绪，无法导出', 'error');
      return;
    }
    const shapes = {};
    const order = [];
    for (const id of (model.order || [])) {
      if (model.shapes && model.shapes[id]) order.push(id);
    }
    for (const id of Object.keys(model.shapes || {})) {
      if (order.indexOf(id) === -1) order.push(id);
    }
    for (const id of order) {
      const shape = model.shapes[id];
      if (!shape) continue;
      const copy = JSON.parse(JSON.stringify(shape));
      delete copy.tt;
      shapes[id] = copy;
    }
    const data = {
      app: 'topotash',
      version: 3,
      saved: new Date().toISOString(),
      shapes,
      order,
      groups: model.groups || {},
      imagePool: model.imagePool || {}
    };
    const blob = new Blob([JSON.stringify(data)], { type: 'application/json' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    const rawName = String((project && project.diagramName) || state.docName || '拓扑图');
    const base = rawName.replace(/[\\/:*?"<>|]+/g, '_').replace(/\.vweb\.json$/i, '').trim() || '拓扑图';
    a.download = base + '.vweb.json';
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 3000);
    post('topotash:exported', { filename: a.download });
    if (window.parent === window && typeof showToast === 'function') {
      showToast('已导出 JSON：' + a.download, 'success');
    }
  }
  window.exportTopotashJson = exportJson;
  window.addEventListener('message', (ev) => {
    if (ev.origin !== location.origin || ev.source !== window.parent) return;
    const msg = ev.data || {};
    if (msg.type === 'topotash:export-json') exportJson();
  });

  // Add a JSON item to the editor's built-in 导出 menu.
  function installExportMenuItem() {
    const pop = document.querySelector('#fileMenu .menu-pop');
    if (!pop || pop.querySelector('[data-act="exportJson"]')) return;
    const item = document.createElement('div');
    item.className = 'mi';
    item.dataset.act = 'exportJson';
    item.textContent = '导出 JSON（可再次导入）';
    item.addEventListener('click', () => {
      exportJson();
      const menu = document.getElementById('fileMenu');
      if (menu) menu.removeAttribute('open');
    });
    pop.appendChild(item);
  }
  installExportMenuItem();

  // ----------------------------------------------------------- node badges
  function shapeTt(shape) {
    if (!shape.tt) shape.tt = { status: 'none', tasks: [], devices: [], nodeKey: shape.id };
    if (!Array.isArray(shape.tt.tasks)) shape.tt.tasks = [];
    if (!Array.isArray(shape.tt.devices)) shape.tt.devices = [];
    return shape.tt;
  }

  function primaryTask(tt) {
    return tt.tasks.find(t => t.primary) || tt.tasks[0] || null;
  }

  function decorateBadges() {
    for (const id of model.order) {
      const shape = model.shapes[id];
      if (!shape || shape.type !== 'shape' || !shape.tt || shape.tt.status === 'none') continue;
      const g = document.getElementById('shp-' + id);
      if (!g) continue;
      const tt = shape.tt;
      const color = STATUS_COLOR[tt.status] || STATUS_COLOR.todo;
      const task = primaryTask(tt);
      const badge = document.createElementNS(SVGNS, 'g');
      badge.setAttribute('class', 'tt-followup-badge');
      badge.setAttribute('data-node', id);
      badge.setAttribute('transform', `translate(${shape.x + shape.w - 12} ${shape.y + 12})`);
      badge.innerHTML = `<circle r="9.5" fill="${color}" stroke="#ffffff" stroke-width="2"></circle>`
        + `<path d="M-1.5 -4.5v9M-1.5 -4.5h5.2l-1.3 2.1 1.3 2.1h-5.2" fill="none" stroke="#ffffff" stroke-width="1.4" stroke-linejoin="round" stroke-linecap="round" pointer-events="none"></path>`;
      const title = document.createElementNS(SVGNS, 'title');
      title.textContent = `${STATUS_TEXT[tt.status] || '待跟进'}${task ? '：' + task.title : '（点击标记/创建任务）'}`;
      badge.appendChild(title);
      g.appendChild(badge);
    }
  }

  const origRender = window.render;
  window.render = function () {
    origRender.apply(window, arguments);
    decorateBadges();
    decorateDeviceBadges();
  };

  function deviceTotal(items) {
    return (items || []).reduce((n, item) => n + (Number(item.quantity) || 0), 0);
  }

  let badgeMeasureCanvas = null;
  function measureBadgeText(value) {
    if (!badgeMeasureCanvas) badgeMeasureCanvas = document.createElement('canvas');
    const context = badgeMeasureCanvas.getContext('2d');
    context.font = '9.5px "Microsoft YaHei", sans-serif';
    return context.measureText(String(value || '')).width;
  }

  function fitBadgeLabel(value, maxWidth) {
    let label = String(value || '设备');
    if (measureBadgeText(label) <= maxWidth) return label;
    while (label.length > 1 && measureBadgeText(label + '…') > maxWidth) {
      label = label.slice(0, -1);
    }
    return label + '…';
  }

  function decorateDeviceBadges() {
    for (const id of model.order) {
      const shape = model.shapes[id];
      if (!shape || shape.type !== 'shape' || !shape.tt || !Array.isArray(shape.tt.devices)) continue;
      if (!shape.tt.devices.length) continue;
      const g = document.getElementById('shp-' + id);
      if (!g) continue;

      const devices = shape.tt.devices;
      // Show at most two device models, then a +N marker. Full list is in the
      // property panel and in the badge tooltip.
      const visible = devices.slice(0, 2);
      const maxText = Math.max(42, Math.min(116, (shape.w || 120) - 26));
      const title = devices
        .map(d => `${d.model || d.name || '设备'}${d.quantity ? ` ×${d.quantity}` : ''}`)
        .join('；') + '（点击查看设备）';

      visible.forEach((device, index) => {
        const label = fitBadgeLabel(device.model || device.name || '设备', maxText);
        const width = Math.max(38, Math.ceil(measureBadgeText(label)) + 14);
        const badge = document.createElementNS(SVGNS, 'g');
        badge.setAttribute('class', 'tt-device-badge');
        badge.setAttribute('data-node', id);
        badge.setAttribute('transform', `translate(${shape.x + 10} ${shape.y + 10 + index * 22})`);
        badge.innerHTML = `<rect x="0" y="0" width="${width}" height="20" rx="7" fill="#162033" stroke="#ffffff" stroke-width="1.5"></rect>`
          + `<text x="${width / 2}" y="13.8" text-anchor="middle" fill="#ffffff" font-size="9.5" font-family="Microsoft YaHei, sans-serif" pointer-events="none">${esc(label)}</text>`;
        const badgeTitle = document.createElementNS(SVGNS, 'title');
        badgeTitle.textContent = title;
        badge.appendChild(badgeTitle);
        g.appendChild(badge);
      });

      if (devices.length > visible.length) {
        const remaining = devices.length - visible.length;
        const index = visible.length;
        const width = 34;
        const badge = document.createElementNS(SVGNS, 'g');
        badge.setAttribute('class', 'tt-device-badge');
        badge.setAttribute('data-node', id);
        badge.setAttribute('transform', `translate(${shape.x + 10} ${shape.y + 10 + index * 22})`);
        badge.innerHTML = `<rect x="0" y="0" width="${width}" height="20" rx="7" fill="#475569" stroke="#ffffff" stroke-width="1.5"></rect>`
          + `<text x="${width / 2}" y="13.8" text-anchor="middle" fill="#ffffff" font-size="9.5" font-family="Microsoft YaHei, sans-serif" pointer-events="none">+${remaining}</text>`;
        const badgeTitle = document.createElementNS(SVGNS, 'title');
        badgeTitle.textContent = title;
        badge.appendChild(badgeTitle);
        g.appendChild(badge);
      }
    }
  }

  // Clicking a device badge selects the node and focuses the device section.
  document.getElementById('shapesLayer').addEventListener('click', function (e) {
    const badge = e.target && e.target.closest ? e.target.closest('.tt-device-badge') : null;
    if (!badge) return;
    e.stopPropagation();
    e.preventDefault();
    const id = badge.getAttribute('data-node');
    if (model.shapes[id]) {
      selectNode(id);
      setTimeout(() => {
        const sec = document.querySelector('.tt-device-sec');
        if (!sec) return;
        sec.classList.add('tt-device-flash');
        setTimeout(() => sec.classList.remove('tt-device-flash'), 1200);
      }, 60);
    }
  }, true);

  // Clicking a badge jumps to its task, or selects the node for linking.
  document.getElementById('shapesLayer').addEventListener('click', function (e) {
    const badge = e.target && e.target.closest ? e.target.closest('.tt-followup-badge') : null;
    if (!badge) return;
    e.stopPropagation();
    e.preventDefault();
    const id = badge.getAttribute('data-node');
    const shape = model.shapes[id];
    if (!shape) return;
    const task = primaryTask(shapeTt(shape));
    if (task) openTask(task.id);
    else selectNode(id);
  }, true);

  function selectNode(id) {
    if (!model.shapes[id]) return;
    selectOnly(id);
    render();
    syncProps();
    const s = model.shapes[id];
    const host = document.getElementById('canvasHost');
    if (host) {
      state.zoom = 1;
      state.pan.x = s.x + s.w / 2 - host.clientWidth / 2;
      state.pan.y = s.y + s.h / 2 - host.clientHeight / 2;
      if (typeof updateView === 'function') updateView();
    }
  }

  function openTask(taskId) {
    if (!PID) {
      if (typeof showToast === 'function') showToast('这张拓扑图尚未绑定项目', 'error');
      return;
    }
    post('topotash:open-task', { taskId });
    if (window.parent === window) {
      location.href = `/projects/${PID}?tab=tasks&task=${encodeURIComponent(taskId)}`;
    }
  }

  function openDevice(deviceId) {
    if (!PID) {
      if (typeof showToast === 'function') showToast('这张拓扑图尚未绑定项目', 'error');
      return;
    }
    post('topotash:open-device', { deviceId });
    if (window.parent === window) {
      location.href = `/projects/${PID}?tab=devices&device=${encodeURIComponent(deviceId)}`;
    }
  }

  // ------------------------------------------------------------ task panel
  async function loadTasks() {
    if (!PID) {
      tasks = [];
      tasksLoading = false;
      decorateFollowupPanel();
      return;
    }
    if (tasksLoading) return;
    tasksLoading = true;
    try {
      const items = [];
      let total;
      do {
        const data = await api(`/api/tasks?project_id=${encodeURIComponent(PID)}&limit=1000&offset=${items.length}`);
        if (!data.items.length) break;
        items.push(...data.items);
        total = data.total;
      } while (items.length < total);
      tasks = items;
    } catch (e) { /* panel shows a hint */ }
    tasksLoading = false;
    decorateFollowupPanel();
  }

  // ---------------------------------------------------------- device panel
  async function loadDevices() {
    if (!PID) {
      devices = [];
      devicesLoading = false;
      decorateDevicePanel();
      return;
    }
    if (devicesLoading) return;
    devicesLoading = true;
    try {
      const data = await api(`/api/devices?project_id=${encodeURIComponent(PID)}`);
      devices = data.items || [];
    } catch (e) {
      devices = [];
    }
    devicesLoading = false;
    decorateDevicePanel();
  }

  async function loadDeviceTemplates() {
    if (templatesLoading) return;
    templatesLoading = true;
    try {
      const data = await api('/api/device-templates');
      deviceTemplates = data.items || [];
    } catch (e) {
      deviceTemplates = [];
    }
    templatesLoading = false;
    decorateDevicePanel();
  }

  async function deviceLinkAction(body) {
    if (deviceBusy) return;
    if (!PID) {
      if (typeof showToast === 'function') showToast('请先把拓扑图绑定到项目', 'error');
      return;
    }
    const shape = selShapes()[0];
    if (!shape) return;
    deviceBusy = true;
    try {
      const res = await api(`${BASE}/nodes/${encodeURIComponent(shape.id)}/devices`, {
        method: 'POST', body
      });
      applyNode(res.node);
      if (res.device) {
        const index = devices.findIndex(d => d.id === res.device.id);
        if (index >= 0) devices[index] = res.device;
        else devices.push(res.device);
      }
      render();
      syncProps();
      post('topotash:project-changed');
      if (typeof showToast === 'function') showToast('节点设备已更新', 'success');
    } catch (e) {
      if (typeof showToast === 'function') showToast(e.message, 'error');
    } finally {
      deviceBusy = false;
    }
  }

  async function deviceUnlink(deviceId) {
    if (deviceBusy) return;
    const shape = selShapes()[0];
    if (!shape) return;
    deviceBusy = true;
    try {
      const res = await api(
        `${BASE}/nodes/${encodeURIComponent(shape.id)}/devices/${encodeURIComponent(deviceId)}`,
        { method: 'DELETE' }
      );
      applyNode(res.node);
      render();
      syncProps();
      post('topotash:project-changed');
    } catch (e) {
      if (typeof showToast === 'function') showToast(e.message, 'error');
    } finally {
      deviceBusy = false;
    }
  }

  function decorateDevicePanel() {
    const box = document.getElementById('propContent');
    if (!box) return;
    box.querySelectorAll('.tt-device-sec').forEach(el => el.remove());
    const shapes = (typeof selShapes === 'function') ? selShapes() : [];
    if (shapes.length !== 1) return;
    const shape = shapes[0];
    if (!shape || shape.type !== 'shape' || !PID) return;

    const tt = shapeTt(shape);
    const linked = tt.devices || [];
    const linkedIds = new Set(linked.map(d => d.device_id || d.id));
    const total = deviceTotal(linked);
    const available = devices.filter(d => !linkedIds.has(d.id));
    const options = available.map(d =>
      `<option value="${esc(d.id)}">${esc(d.name)}${d.model ? ' · ' + esc(d.model) : ''}</option>`
    ).join('');
    const kindCategory = {
      server: 'server', db: 'storage', cluster: 'server', storage: 'storage',
      switch: 'network', router: 'network', cloud: 'network', globe: 'network',
      firewall: 'security', pc: 'other', laptop: 'other', phone: 'other',
      printer: 'other'
    };
    const linkedCategory = linked.length ? linked[0].category : '';
    const defaultCategory = linkedCategory || kindCategory[String(shape.kind || '').toLowerCase()] || 'network';
    const categories = [
      ['server', '服务器'], ['storage', '存储'], ['network', '网络'],
      ['security', '安全'], ['software', '软件'], ['other', '其他']
    ].map(([key, label]) =>
      `<option value="${key}" ${key === defaultCategory ? 'selected' : ''}>${label}</option>`
    ).join('');
    const templateOptions = deviceTemplates.map(template =>
      `<option value="${esc(template.id)}">${esc(template.display_label || template.name || '')}</option>`
    ).join('');
    const rawName = ((shape.text || '节点').split('\n')[0] || '节点').trim();
    const defaultName = rawName.replace(/\s*[×xX]\s*\d+\s*$/, '');
    const qtyMatch = rawName.match(/[×xX]\s*(\d+)\s*$/);
    const defaultQty = qtyMatch ? Math.max(1, Number(qtyMatch[1])) : 1;

    const sec = document.createElement('div');
    sec.className = 'prop-sec tt-device-sec';
    sec.innerHTML = `
      <h4>TopoTash 设备 <span class="tt-sec-state device">${linked.length} 项 · ${total} 台</span></h4>
      <div class="tt-device-list">
        ${linked.length ? linked.map(d => `
          <div class="tt-device-row" data-device-row="${esc(d.device_id || d.id)}">
            <div class="tt-device-main">
              <b>${esc(d.name)}</b>
              <em>${esc([d.brand, d.model].filter(Boolean).join(' ') || '未填写型号')} · ×${d.quantity || 0}</em>
            </div>
            <span class="tt-device-state ${esc(d.status)}">${esc(d.status_label || d.status)}</span>
            <div class="tt-device-acts">
              <button type="button" data-open-device="${esc(d.device_id || d.id)}">打开</button>
              <button type="button" class="muted" data-unlink-device="${esc(d.device_id || d.id)}">取消</button>
            </div>
          </div>`).join('') : '<div class="tt-empty-task">尚未关联设备。</div>'}
      </div>
      <select class="tt-select" data-device-link>
        <option value="">${devicesLoading ? '设备加载中…' : '关联已有设备…'}</option>
        ${options}
      </select>
      <div class="tt-device-create">
        <select class="tt-select" data-device-template>
          <option value="">${deviceTemplates.length ? '从模板选择…' : '模板库为空，可直接填写'}</option>
          ${templateOptions}
        </select>
        <input data-device-name value="${esc(defaultName)}" maxlength="120">
        <div class="tt-device-create-row">
          <select data-device-category>${categories}</select>
          <input data-device-qty type="number" min="1" step="1" value="${defaultQty}" title="本节点数量">
          <button type="button" data-device-create>新建并关联</button>
        </div>
      </div>
      <div class="tt-note">设备清单在项目「设备清单」统一维护；节点删除只解除关联，不删除设备。</div>`;

    box.insertBefore(sec, box.firstChild);

    const sel = sec.querySelector('[data-device-link]');
    if (sel) sel.onchange = () => {
      if (sel.value) deviceLinkAction({ device_id: sel.value });
    };
    sec.querySelectorAll('[data-open-device]').forEach(btn => {
      btn.onclick = () => openDevice(btn.dataset.openDevice);
    });
    sec.querySelectorAll('[data-unlink-device]').forEach(btn => {
      btn.onclick = () => deviceUnlink(btn.dataset.unlinkDevice);
    });
    const createBtn = sec.querySelector('[data-device-create]');
    const templateSelect = sec.querySelector('[data-device-template]');
    if (templateSelect) templateSelect.onchange = () => {
      const template = deviceTemplates.find(item => item.id === templateSelect.value);
      if (!template) return;
      const nameInput = sec.querySelector('[data-device-name]');
      if (nameInput) nameInput.value = template.name || template.display_label || '';
      const categorySelect = sec.querySelector('[data-device-category]');
      if (categorySelect) categorySelect.value = template.category || 'other';
    };
    if (createBtn) createBtn.onclick = () => {
      const nameInput = sec.querySelector('[data-device-name]');
      const name = (nameInput && nameInput.value.trim()) || defaultName;
      const category = sec.querySelector('[data-device-category]').value;
      const quantity = Math.max(1, Number(sec.querySelector('[data-device-qty]').value || 1));
      const template = deviceTemplates.find(item => item.id === (templateSelect && templateSelect.value));
      const create = { name, category, quantity };
      if (template) {
        create.brand = template.brand || '';
        create.model = template.model || '';
        create.spec = template.spec || '';
        create.unit = template.unit || '台';
        create.unit_price = template.unit_price == null ? null : template.unit_price;
        create.note = template.note || '';
      }
      deviceLinkAction({ create_device: create });
    };
  }

  function applyNode(node) {
    const shape = model.shapes[node.node_key];
    if (!shape) return;
    shape.tt = {
      status: node.followup_status,
      label: node.label,
      nodeKey: node.node_key,
      tasks: (node.linked_tasks || []).map(t => ({
        id: t.task_id, title: t.title, status: t.status, primary: !!t.is_primary
      })),
      devices: (node.linked_devices || []).map(d => ({
        id: d.device_id, device_id: d.device_id, name: d.name,
        brand: d.brand, model: d.model, category: d.category,
        category_label: d.category_label, status: d.status,
        status_label: d.status_label, quantity: d.quantity, unit: d.unit
      }))
    };
  }

  async function nodeAction(body) {
    if (!PID) {
      if (typeof showToast === 'function') showToast('请先把拓扑图绑定到项目', 'error');
      return;
    }
    const shape = selShapes()[0];
    if (!shape) return;
    try {
      const res = await api(`${BASE}/nodes/${encodeURIComponent(shape.id)}/followup`, { method: 'POST', body });
      applyNode(res.node);
      if (res.task) {
        const known = tasks.some(t => t.id === res.task.id);
        if (!known) tasks.push({ id: res.task.id, title: res.task.title, status: res.task.status });
      }
      render();
      syncProps();
      post('topotash:project-changed');
      if (typeof showToast === 'function') showToast('节点跟进已更新', 'success');
    } catch (e) {
      if (typeof showToast === 'function') showToast(e.message, 'error');
    }
  }

  function decorateFollowupPanel() {
    const box = document.getElementById('propContent');
    if (!box) return;
    const shapes = (typeof selShapes === 'function') ? selShapes() : [];
    if (shapes.length !== 1) return;
    const shape = shapes[0];
    if (!shape || shape.type !== 'shape') return;
    const stale = box.querySelector('.tt-followup-sec');
    if (stale) stale.remove();

    if (!PID) {
      const note = document.createElement('div');
      note.className = 'prop-sec tt-followup-sec';
      note.innerHTML = `
        <h4>TopoTash 跟进 <span class="tt-sec-state none">未绑定项目</span></h4>
        <div class="tt-note">这张拓扑图还没有绑定项目。回到拓扑图库把它绑定到项目后，就可以在节点上创建或关联任务。</div>`;
      const deviceSec = box.querySelector('.tt-device-sec');
      if (deviceSec) box.insertBefore(note, deviceSec.nextSibling);
      else box.insertBefore(note, box.firstChild);
      return;
    }

    const tt = shapeTt(shape);
    const task = primaryTask(tt);
    const linkedIds = new Set(tt.tasks.map(t => t.id));
    const options = tasks.filter(t => !linkedIds.has(t.id))
      .map(t => `<option value="${esc(t.id)}">${esc(t.title)}</option>`).join('');

    const sec = document.createElement('div');
    sec.className = 'prop-sec tt-followup-sec';
    sec.innerHTML = `
      <h4>TopoTash 跟进 <span class="tt-sec-state ${STATUS_CLASS[tt.status] || 'none'}">${STATUS_TEXT[tt.status] || '未标记'}</span></h4>
      <div class="tt-status-row">
        <button type="button" data-status="todo" class="${tt.status === 'todo' ? 'on todo' : ''}">待跟进</button>
        <button type="button" data-status="doing" class="${tt.status === 'doing' ? 'on doing' : ''}">进行中</button>
        <button type="button" data-status="done" class="${tt.status === 'done' ? 'on done' : ''}">已完成</button>
        <button type="button" data-status="none" class="${tt.status === 'none' ? 'on' : ''}">清除</button>
      </div>
      ${task
        ? `<div class="tt-linked-task"><span title="${esc(task.title)}">${esc(task.title)}</span><button type="button" data-open>打开任务</button><button type="button" data-unlink="${esc(task.id)}">取消</button></div>`
        : `<div class="tt-empty-task">尚未关联任务，标记后可创建或选择任务。</div>`}
      <div class="tt-task-actions">
        <select class="tt-select" data-link-task>
          <option value="">${tasksLoading ? '任务加载中…' : '关联已有任务…'}</option>
          ${options}
        </select>
        ${!task ? `<div class="tt-create-row"><input data-task-title value="跟进：${esc((shape.text || '节点').split('\n')[0])}"><button type="button" data-create>创建任务</button></div>` : ''}
      </div>
      <div class="tt-note">节点标记会出现在项目「关联视图」；任务也可在任务台里查看。</div>`;

    const deviceSec = box.querySelector('.tt-device-sec');
    if (deviceSec) box.insertBefore(sec, deviceSec.nextSibling);
    else box.insertBefore(sec, box.firstChild);
    sec.querySelectorAll('[data-status]').forEach(btn => {
      btn.onclick = () => nodeAction({ status: btn.dataset.status });
    });
    const openBtn = sec.querySelector('[data-open]');
    if (openBtn && task) openBtn.onclick = () => openTask(task.id);
    const unlinkBtn = sec.querySelector('[data-unlink]');
    if (unlinkBtn && task) unlinkBtn.onclick = async () => {
      try {
        const node = await api(`${BASE}/nodes/${encodeURIComponent(shape.id)}/links/${encodeURIComponent(task.id)}`, { method: 'DELETE' });
        applyNode(node);
        render(); syncProps();
        post('topotash:project-changed');
      } catch (e) { if (typeof showToast === 'function') showToast(e.message, 'error'); }
    };
    const sel = sec.querySelector('[data-link-task]');
    if (sel) sel.onchange = () => { if (sel.value) nodeAction({ task_id: sel.value }); };
    const createBtn = sec.querySelector('[data-create]');
    if (createBtn) createBtn.onclick = () => {
      const input = sec.querySelector('[data-task-title]');
      const title = (input && input.value.trim()) || `跟进：${(shape.text || '节点').split('\n')[0]}`;
      nodeAction({ create_task: { title, priority: 1, stage: project.stage || 'research' } });
    };
  }

  const origSyncProps = window.syncProps;
  window.syncProps = function () {
    origSyncProps.apply(window, arguments);
    decorateFollowupPanel();
    // Keep the device section above the follow-up section on the node panel.
    decorateDevicePanel();
  };

  // Keep title in sync with the diagram name.
  state.docName = project.diagramName;
  load();
})();
