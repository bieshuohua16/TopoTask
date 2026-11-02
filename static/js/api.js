/* TopoTash shared helpers */
(function () {
  const TT = window.TT = window.TT || {};
  const CFG = window.TT_CONFIG || {};
  TT.config = CFG;

  TT.api = async function (path, options = {}) {
    const opts = Object.assign({ headers: {} }, options);
    if (opts.body && typeof opts.body !== 'string') {
      opts.headers['Content-Type'] = 'application/json';
      opts.body = JSON.stringify(opts.body);
    }
    const res = await fetch(path, opts);
    const text = await res.text();
    let data = null;
    try { data = text ? JSON.parse(text) : null; } catch (e) { data = null; }
    if (!res.ok) {
      const msg = (data && data.error && data.error.message) || text || ('请求失败 (' + res.status + ')');
      throw new Error(msg);
    }
    return data;
  };

  TT.esc = function (value) {
    return String(value == null ? '' : value)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  };

  TT.stageLabel = function (key) { return (CFG.stageLabels || {})[key] || key || ''; };
  TT.statusLabel = function (key) { return (CFG.statusLabels || {})[key] || key || ''; };

  TT.date = function (value, withTime) {
    if (!value) return '—';
    const d = new Date(value);
    if (isNaN(d.getTime())) return value;
    const p = n => String(n).padStart(2, '0');
    const s = d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate());
    return withTime ? s + ' ' + p(d.getHours()) + ':' + p(d.getMinutes()) : s;
  };

  TT.relative = function (value) {
    if (!value) return '—';
    const d = new Date(value);
    if (isNaN(d.getTime())) return value;
    const diff = Date.now() - d.getTime();
    const min = Math.round(diff / 60000);
    if (min < 1) return '刚刚';
    if (min < 60) return min + ' 分钟前';
    const hr = Math.round(min / 60);
    if (hr < 24) return hr + ' 小时前';
    const day = Math.round(hr / 24);
    if (day < 30) return day + ' 天前';
    return TT.date(value);
  };

  TT.dueText = function (value) {
    if (!value) return '无截止';
    const d = new Date(value);
    if (isNaN(d.getTime())) return value;
    const today = new Date(); today.setHours(0, 0, 0, 0);
    const target = new Date(d); target.setHours(0, 0, 0, 0);
    const days = Math.round((target - today) / 86400000);
    if (days === 0) return '今天到期';
    if (days === 1) return '明天到期';
    if (days === -1) return '昨天逾期';
    if (days < 0) return '逾期 ' + Math.abs(days) + ' 天';
    if (days <= 7) return days + ' 天后';
    return TT.date(value);
  };

  TT.isOverdue = function (value) {
    if (!value) return false;
    const d = new Date(value);
    return !isNaN(d.getTime()) && d.getTime() < Date.now();
  };

  TT.qs = function (key) { return new URLSearchParams(location.search).get(key); };

  TT.toast = function (message, type) {
    const root = document.getElementById('toastRoot');
    if (!root) return;
    const el = document.createElement('div');
    el.className = 'toast ' + (type || '');
    el.textContent = message;
    root.appendChild(el);
    setTimeout(() => { el.style.opacity = '0'; el.style.transform = 'translateY(6px)'; }, 2600);
    setTimeout(() => el.remove(), 2950);
  };

  TT.icon = {
    tasks: '<svg viewBox="0 0 24 24" fill="none"><path d="M9 6h11M9 12h11M9 18h11"/><path d="m3 6 1 1 2-2M3 12l1 1 2-2M3 18l1 1 2-2"/></svg>',
    diagram: '<svg viewBox="0 0 24 24" fill="none"><circle cx="6" cy="6" r="2.5"/><circle cx="18" cy="7" r="2.5"/><circle cx="12" cy="18" r="2.5"/><path d="M8.3 7.2 15.7 8.8M7.4 8.2l3.4 7.4M17 9.3l-3.7 6.4"/></svg>',
    flag: '<svg viewBox="0 0 24 24" fill="none"><path d="M5 21V4M5 4h11l-2 4 2 4H5"/></svg>',
    arrow: '<svg viewBox="0 0 24 24" fill="none"><path d="M5 12h14M13 6l6 6-6 6"/></svg>'
  };

  TT.modal = function ({ title, subtitle, body, submitText, submitClass, onSubmit, width }) {
    const root = document.getElementById('modalRoot');
    root.classList.add('open');
    root.innerHTML = `
      <div class="modal-mask"></div>
      <div class="modal" role="dialog" aria-modal="true" ${width ? `style="width:min(${width}px, calc(100vw - 32px))"` : ''}>
        <h3>${TT.esc(title || '')}</h3>
        ${subtitle ? `<div class="modal-sub">${TT.esc(subtitle)}</div>` : ''}
        <form id="ttModalForm">${body || ''}<div class="form-error" id="ttFormError"></div>
          <div class="modal-actions">
            <button type="button" class="btn btn-ghost" data-close>取消</button>
            <button type="submit" class="btn ${submitClass || 'btn-primary'}">${TT.esc(submitText || '保存')}</button>
          </div>
        </form>
      </div>`;
    const close = () => { root.classList.remove('open'); root.innerHTML = ''; };
    root.querySelector('.modal-mask').onclick = close;
    root.querySelector('[data-close]').onclick = close;
    const form = root.querySelector('#ttModalForm');
    form.onsubmit = async (ev) => {
      ev.preventDefault();
      const err = root.querySelector('#ttFormError');
      err.classList.remove('show');
      try {
        await onSubmit(new FormData(form), form);
        close();
      } catch (e) {
        err.textContent = e.message || '操作失败';
        err.classList.add('show');
      }
    };
    setTimeout(() => { const first = form.querySelector('input,select,textarea'); if (first) first.focus(); }, 40);
    return { close, form };
  };

  TT.confirm = function (message, onConfirm, { danger = true, title = '确认操作', submitText = '确定' } = {}) {
    return TT.modal({
      title, subtitle: message, submitText, submitClass: danger ? 'btn-danger' : 'btn-primary', width: 420,
      body: '',
      onSubmit: async () => { await onConfirm(); }
    });
  };

  TT.empty = function (text) { return `<div class="empty-inline">${TT.esc(text)}</div>`; };
})();
