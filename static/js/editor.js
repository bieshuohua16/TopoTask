/* Diagram editor wrapper */
(function () {
  const TT = window.TT || {};
  const frame = document.getElementById('visioFrame');
  const status = document.getElementById('editorStatus');
  if (!frame) return;

  let editorReady = false;
  const node = new URLSearchParams(location.search).get('node');
  if (node) {
    const u = new URL(frame.src, location.origin);
    u.searchParams.set('node', node);
    frame.src = u.toString();
  }

  function setStatus(kind, text) {
    if (!status) return;
    const dot = kind === 'error' ? 'bad' : kind === 'saving' ? 'warn' : 'ok';
    const indicator = document.createElement('i');
    indicator.className = 'dot ' + dot;
    const label = document.createElement('span');
    label.textContent = text;
    status.replaceChildren(indicator, label);
  }

  const exportBtn = document.getElementById('btnExportDiagram');
  if (exportBtn) exportBtn.onclick = () => {
    if (!editorReady || !frame.contentWindow) {
      setStatus('error', '编辑器尚未就绪，请稍后再试');
      return;
    }
    frame.contentWindow.postMessage({ type: 'topotash:export-json' }, location.origin);
    setStatus('saving', '正在导出 JSON…');
  };

  window.addEventListener('message', (ev) => {
    if (ev.origin !== location.origin || ev.source !== frame.contentWindow) return;
    const msg = ev.data || {};
    if (msg.type === 'topotash:visio-saved') {
      setStatus('ok', '已保存 · ' + (msg.nodeCount || 0) + ' 个节点');
    } else if (msg.type === 'topotash:visio-saving') {
      setStatus('saving', '保存中…');
    } else if (msg.type === 'topotash:visio-error') {
      setStatus('error', '保存失败：' + msg.message);
    } else if (msg.type === 'topotash:visio-ready') {
      editorReady = true;
      setStatus('ok', '已连接 TopoTash');
    } else if (msg.type === 'topotash:exported') {
      setStatus('ok', '已导出 ' + (msg.filename || 'JSON'));
    } else if (msg.type === 'topotash:open-task' && msg.taskId && window.TT_EDITOR.project) {
      location.href = `/projects/${window.TT_EDITOR.project.id}?tab=tasks&task=${encodeURIComponent(msg.taskId)}`;
    } else if (msg.type === 'topotash:toast') {
      TT.toast && TT.toast(msg.message, msg.level || 'success');
    }
  });

  frame.addEventListener('load', () => setStatus('ok', '编辑器已加载'));
})();
