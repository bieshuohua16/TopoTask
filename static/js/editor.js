/* Diagram editor wrapper */
(function () {
  const TT = window.TT || {};
  const frame = document.getElementById('visioFrame');
  const status = document.getElementById('editorStatus');
  if (!frame) return;

  const node = new URLSearchParams(location.search).get('node');
  if (node) {
    const u = new URL(frame.src, location.origin);
    u.searchParams.set('node', node);
    frame.src = u.toString();
  }

  function setStatus(kind, text) {
    if (!status) return;
    const dot = kind === 'error' ? 'bad' : kind === 'saving' ? 'warn' : 'ok';
    status.innerHTML = `<i class="dot ${dot}"></i><span>${TT.esc ? TT.esc(text) : text}</span>`;
  }

  window.addEventListener('message', (ev) => {
    const msg = ev.data || {};
    if (msg.type === 'topotash:visio-saved') {
      setStatus('ok', '已保存 · ' + (msg.nodeCount || 0) + ' 个节点');
    } else if (msg.type === 'topotash:visio-saving') {
      setStatus('saving', '保存中…');
    } else if (msg.type === 'topotash:visio-error') {
      setStatus('error', '保存失败：' + msg.message);
    } else if (msg.type === 'topotash:visio-ready') {
      setStatus('ok', '已连接 TopoTash');
    } else if (msg.type === 'topotash:open-task' && msg.taskId) {
      location.href = `/projects/${window.TT_EDITOR.project.id}?tab=tasks&task=${encodeURIComponent(msg.taskId)}`;
    } else if (msg.type === 'topotash:toast') {
      TT.toast && TT.toast(msg.message, msg.level || 'success');
    }
  });

  frame.addEventListener('load', () => setStatus('ok', '编辑器已加载'));
})();
