/* TopoTash global AI assistant.
 *
 * A single drawer shared by every page. The backend owns the model API key and
 * returns drafts; this file renders the conversation, editable draft cards and
 * refreshes the surrounding views after a confirmed action.
 */
(function () {
  'use strict';
  const TT = window.TT;
  if (!TT) return;
  const CFG = window.TT_CONFIG || {};

  const TOOL_LABELS = {
    list_projects: '查询项目',
    get_project: '读取项目',
    portfolio_summary: '汇总进展',
    list_tasks: '查询任务',
    get_task: '读取任务',
    search: '全局搜索',
    create_project: '起草项目',
    update_project: '起草项目修改',
    delete_project: '起草删除项目',
    create_task: '起草任务',
    update_task: '起草任务修改',
    delete_task: '起草删除任务'
  };

  const state = {
    open: false,
    config: null,
    conversationId: null,
    conversation: null,
    messages: [],
    actions: [],
    conversations: [],
    busy: false,
    showHistory: false,
    contextProjectId: CFG.projectId || '',
    initialized: false
  };

  const els = {};

  const TEMPLATE = `
  <div class="ai-root" id="aiRoot" aria-hidden="true">
    <div class="ai-mask" data-ai-close></div>
    <aside class="ai-panel" role="dialog" aria-modal="true" aria-label="AI 助手">
      <header class="ai-head">
        <div class="ai-head-title">
          <span class="ai-mark" aria-hidden="true">✦</span>
          <div class="ai-head-text">
            <b>AI 助手</b>
            <em><i class="ai-status-dot" id="aiStatusDot"></i><span id="aiStatusText">正在读取配置…</span></em>
          </div>
        </div>
        <div class="ai-head-actions">
          <button type="button" class="ai-icon-btn" id="aiHistoryBtn" title="历史对话" aria-label="历史对话">
            <svg viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 1.8"/></svg>
          </button>
          <button type="button" class="ai-icon-btn" id="aiNewBtn" title="新对话" aria-label="新对话">
            <svg viewBox="0 0 24 24" fill="none"><path d="M12 5v14M5 12h14"/></svg>
          </button>
          <button type="button" class="ai-icon-btn" id="aiSettingsBtn" title="AI 设置" aria-label="AI 设置">
            <svg viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.9.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.9 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1A1.7 1.7 0 0 0 4.6 9a1.7 1.7 0 0 0-.3-1.9l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.9.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.9-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.9V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1Z"/></svg>
          </button>
          <button type="button" class="ai-icon-btn" data-ai-close title="关闭" aria-label="关闭">
            <svg viewBox="0 0 24 24" fill="none"><path d="M18 6 6 18M6 6l12 12"/></svg>
          </button>
        </div>
      </header>
      <div class="ai-context" id="aiContext"></div>
      <div class="ai-history" id="aiHistory" hidden></div>
      <div class="ai-body" id="aiBody">
        <div class="ai-welcome" id="aiWelcome"></div>
        <div class="ai-msgs" id="aiMsgs"></div>
        <div class="ai-actions" id="aiActions"></div>
        <div class="ai-typing" id="aiTyping" hidden><span></span><span></span><span></span></div>
      </div>
      <form class="ai-composer" id="aiComposer" autocomplete="off">
        <textarea id="aiInput" rows="1" placeholder="描述你想做的事，例如：帮我新建一个恒达制造的网络改造项目…"></textarea>
        <div class="ai-composer-foot">
          <span class="ai-hint">Enter 发送 · Shift+Enter 换行 · 写入前会先给草稿</span>
          <button type="submit" class="ai-send" id="aiSendBtn">
            <svg viewBox="0 0 24 24" fill="none"><path d="m22 2-7 20-4-9-9-4 20-7Z"/><path d="M22 2 11 13"/></svg>
            发送
          </button>
        </div>
      </form>
    </aside>
  </div>`;

  // ------------------------------------------------------------------ setup
  function init() {
    if (state.initialized) return;
    state.initialized = true;
    document.body.insertAdjacentHTML('beforeend', TEMPLATE);
    els.root = document.getElementById('aiRoot');
    els.body = document.getElementById('aiBody');
    els.msgs = document.getElementById('aiMsgs');
    els.actions = document.getElementById('aiActions');
    els.welcome = document.getElementById('aiWelcome');
    els.context = document.getElementById('aiContext');
    els.history = document.getElementById('aiHistory');
    els.input = document.getElementById('aiInput');
    els.composer = document.getElementById('aiComposer');
    els.typing = document.getElementById('aiTyping');
    bind();
    loadConfig().catch(function () { /* configuration is optional until first use */ });
  }

  function bind() {
    const top = document.getElementById('btnAiAssistant');
    if (top) top.addEventListener('click', function () { toggle(); });

    els.root.querySelectorAll('[data-ai-close]').forEach(function (el) {
      el.addEventListener('click', close);
    });
    document.getElementById('aiHistoryBtn').addEventListener('click', toggleHistory);
    document.getElementById('aiNewBtn').addEventListener('click', newChat);
    document.getElementById('aiSettingsBtn').addEventListener('click', openConfig);
    window.addEventListener('focus', function () {
      loadConfig().catch(function () {});
    });
    els.composer.addEventListener('submit', function (ev) {
      ev.preventDefault();
      send();
    });
    els.input.addEventListener('keydown', function (ev) {
      if (ev.key === 'Enter' && !ev.shiftKey) {
        ev.preventDefault();
        send();
      }
    });
    els.input.addEventListener('input', autoGrow);

    els.welcome.addEventListener('click', function (ev) {
      const configBtn = ev.target.closest('[data-ai-config]');
      if (configBtn) { openConfig(); return; }
      const prompt = ev.target.closest('[data-ai-prompt]');
      if (prompt) send(prompt.dataset.aiPrompt);
    });

    els.history.addEventListener('click', function (ev) {
      const del = ev.target.closest('[data-del]');
      if (del) {
        ev.stopPropagation();
        removeConversation(del.dataset.del);
        return;
      }
      const item = ev.target.closest('[data-conv]');
      if (item) loadConversation(item.dataset.conv);
    });

    els.actions.addEventListener('click', function (ev) {
      const confirm = ev.target.closest('[data-ai-confirm]');
      if (confirm) { confirmAction(confirm.dataset.aiConfirm, confirm); return; }
      const cancel = ev.target.closest('[data-ai-cancel]');
      if (cancel) cancelAction(cancel.dataset.aiCancel, cancel);
    });

    document.addEventListener('keydown', function (ev) {
      if ((ev.ctrlKey || ev.metaKey) && String(ev.key).toLowerCase() === 'k') {
        ev.preventDefault();
        toggle();
        return;
      }
      if (ev.key === 'Escape' && state.open) {
        const modal = document.getElementById('modalRoot');
        if (!modal || !modal.classList.contains('open')) close();
      }
    });
  }

  // ------------------------------------------------------------------ open/close
  function open(opts) {
    opts = opts || {};
    init();
    if (opts.projectId) state.contextProjectId = opts.projectId;
    const wasOpen = state.open;
    state.open = true;
    els.root.classList.add('open');
    els.root.setAttribute('aria-hidden', 'false');
    document.body.classList.add('ai-open');
    renderContext();
    renderStatus();

    loadConfig().catch(function () {});
    if (!wasOpen) {
      if (state.conversationId) {
        loadConversation(state.conversationId);
      } else {
        loadConversations().then(function () {
          if (state.conversations.length) loadConversation(state.conversations[0].id);
          else render();
        }).catch(function () { render(); });
      }
    }
    if (opts.prompt) {
      els.input.value = opts.prompt;
      autoGrow();
    }
    setTimeout(function () { if (els.input) els.input.focus(); }, 80);
  }

  function close() {
    if (!state.initialized) return;
    state.open = false;
    state.showHistory = false;
    els.root.classList.remove('open');
    els.root.setAttribute('aria-hidden', 'true');
    document.body.classList.remove('ai-open');
    renderHistory();
  }

  function toggle() {
    if (state.open) close(); else open();
  }

  function newChat() {
    state.conversationId = null;
    state.conversation = null;
    state.messages = [];
    state.actions = [];
    state.showHistory = false;
    render();
    if (els.input) {
      els.input.value = '';
      autoGrow();
      els.input.focus();
    }
  }

  // ------------------------------------------------------------------ data
  async function loadConfig() {
    state.config = await TT.api('/api/ai/config');
    renderStatus();
    renderWelcome();
  }

  async function loadConversations() {
    const data = await TT.api('/api/ai/conversations');
    state.conversations = data.items || [];
    renderHistory();
  }

  async function fetchConversation(id) {
    const data = await TT.api('/api/ai/conversations/' + encodeURIComponent(id));
    state.conversationId = id;
    state.conversation = data.conversation;
    state.messages = data.messages || [];
    state.actions = data.actions || [];
    return data;
  }

  async function loadConversation(id) {
    state.busy = true;
    state.showHistory = false;
    render();
    try {
      await fetchConversation(id);
    } catch (err) {
      state.conversationId = null;
      state.messages = [];
      state.actions = [];
      TT.toast('加载对话失败：' + err.message, 'error');
    } finally {
      state.busy = false;
      render();
      scrollToDraftOrBottom();
    }
  }

  async function removeConversation(id) {
    TT.confirm('删除这个对话？聊天记录会一起删除。', async function () {
      await TT.api('/api/ai/conversations/' + encodeURIComponent(id), { method: 'DELETE' });
      state.conversations = state.conversations.filter(function (c) { return c.id !== id; });
      if (state.conversationId === id) {
        newChat();
      } else {
        renderHistory();
      }
      TT.toast('对话已删除', 'success');
    }, { title: '删除对话', submitText: '删除' });
  }

  // ------------------------------------------------------------------ chat
  function buildContext() {
    const pid = state.contextProjectId || CFG.projectId || '';
    return {
      page: CFG.page || '',
      project_id: pid,
      task_id: TT.qs('task') || '',
      path: location.pathname + location.search
    };
  }

  async function send(text) {
    if (state.busy) return;
    const message = String(text == null ? els.input.value : text).trim();
    if (!message) return;
    if (!state.config || !state.config.configured) {
      TT.toast('请先配置 AI 模型', 'error');
      openConfig();
      return;
    }
    if (text == null) {
      els.input.value = '';
      autoGrow();
    }
    state.busy = true;
    state.messages.push({
      id: 'local-' + Date.now(),
      role: 'user',
      content: message,
      optimistic: true
    });
    render();
    scrollBottom();

    try {
      const data = await TT.api('/api/ai/chat', {
        method: 'POST',
        body: {
          conversation_id: state.conversationId,
          message: message,
          context: buildContext()
        }
      });
      if (data.conversation && data.conversation.id) {
        state.conversationId = data.conversation.id;
      }
      if (data.ok === false) {
        if (data.need_config) {
          state.messages = state.messages.filter(function (m) { return !m.optimistic; });
          els.input.value = message;
          autoGrow();
          render();
          openConfig();
          return;
        }
        TT.toast(data.error || 'AI 请求失败', 'error');
      }
      if (state.conversationId) await fetchConversation(state.conversationId);
      loadConversations().catch(function () {});
    } catch (err) {
      TT.toast(err.message || 'AI 请求失败', 'error');
      state.messages = state.messages.filter(function (m) { return !m.optimistic; });
    } finally {
      state.busy = false;
      render();
      scrollBottom();
      if (els.input) els.input.focus();
    }
  }

  // ------------------------------------------------------------------ actions
  async function confirmAction(id, btn) {
    const card = btn.closest('.ai-action');
    if (!card || card.classList.contains('busy')) return;
    const values = {};
    card.querySelectorAll('[data-field]').forEach(function (el) {
      values[el.dataset.field] = el.type === 'datetime-local'
        ? (el.value === el.dataset.initial ? el.dataset.original
          : el.value ? new Date(el.value).toISOString() : '')
        : el.value;
    });
    card.classList.add('busy');
    btn.disabled = true;
    btn.textContent = '执行中…';
    try {
      const data = await TT.api('/api/ai/actions/' + encodeURIComponent(id) + '/confirm', {
        method: 'POST',
        body: { values: values }
      });
      const action = data.action;
      state.actions = state.actions.map(function (item) {
        return item.id === action.id ? action : item;
      });
      if (state.conversationId) {
        try { await fetchConversation(state.conversationId); } catch (err) { /* keep local state */ }
      }
      TT.toast(appliedMessage(action), 'success');
      refreshAfter(action);
      render();
      scrollBottom();
    } catch (err) {
      TT.toast(err.message || '执行失败', 'error');
      card.classList.remove('busy');
      btn.disabled = false;
      btn.textContent = confirmLabel(actionKind(card));
    }
  }

  async function cancelAction(id, btn) {
    const card = btn.closest('.ai-action');
    if (card) card.classList.add('busy');
    try {
      const data = await TT.api('/api/ai/actions/' + encodeURIComponent(id) + '/cancel', {
        method: 'POST'
      });
      state.actions = state.actions.map(function (item) {
        return item.id === data.action.id ? data.action : item;
      });
      if (state.conversationId) {
        try { await fetchConversation(state.conversationId); } catch (err) { /* keep local state */ }
      }
      TT.toast('已取消该草稿', 'success');
      render();
    } catch (err) {
      TT.toast(err.message || '取消失败', 'error');
      if (card) card.classList.remove('busy');
    }
  }

  function actionKind(card) {
    const el = card && card.querySelector('[data-ai-confirm]');
    const action = el && state.actions.find(function (a) { return a.id === el.dataset.aiConfirm; });
    return action ? action.kind : '';
  }

  function appliedMessage(action) {
    const result = action.result || {};
    if (action.kind === 'create_project') {
      return '已创建项目「' + (result.project_name || '') + '」' +
        (result.task_count ? '，含 ' + result.task_count + ' 个任务' : '');
    }
    if (action.kind === 'update_project') return '项目已更新';
    if (action.kind === 'delete_project') return '项目已删除';
    if (action.kind === 'create_task') return '已创建任务「' + (result.title || '') + '」';
    if (action.kind === 'update_task') return '任务已更新';
    if (action.kind === 'delete_task') return '任务已删除';
    return '已执行';
  }

  function refreshAfter(action) {
    const result = action.result || {};
    const projectId = result.project_id || action.project_id || '';
    const projectKinds = { create_project: 1, update_project: 1, delete_project: 1 };
    if (window.TT_shell && window.TT_shell.loadProjects) window.TT_shell.loadProjects();
    if (projectKinds[action.kind]) {
      document.dispatchEvent(new CustomEvent('tt:project-saved', {
        detail: { projectId: projectId, isEdit: action.kind !== 'create_project' }
      }));
    }
    if (projectId) {
      document.dispatchEvent(new CustomEvent('tt:tasks-changed', {
        detail: { projectId: projectId }
      }));
    }
    if (window.TTTasks && projectId && CFG.projectId === projectId && TT.qs('tab') === 'tasks') {
      window.TTTasks.refresh();
    }
    if (action.kind === 'delete_project' && CFG.projectId && CFG.projectId === action.project_id) {
      setTimeout(function () { location.href = '/'; }, 600);
    }
  }

  // ------------------------------------------------------------------ config
  async function openConfig() {
    init();
    try {
      await loadConfig();
    } catch (err) {
      TT.toast('读取全局 AI 配置失败：' + err.message, 'error');
      return;
    }
    const cfg = state.config || {};
    const presetButtons = (cfg.presets || []).map(function (preset) {
      return '<button type="button" class="ai-preset" data-preset-base="' + TT.esc(preset.api_base) +
        '" data-preset-model="' + TT.esc(preset.model) + '">' + TT.esc(preset.label) + '</button>';
    }).join('');
    const keyHint = cfg.api_key_set
      ? '已保存 ' + TT.esc(cfg.api_key_hint || '') + '，留空则不修改'
      : 'sk-...';
    const body = `
      <div class="ai-presets">
        <span class="ai-presets-label">快速填入</span>
        ${presetButtons}
      </div>
      <div class="field full">
        <label>API Base URL *</label>
        <input name="api_base" value="${TT.esc(cfg.api_base || '')}" placeholder="https://api.deepseek.com/v1">
        <small class="ai-field-hint">OpenAI 兼容接口，需支持 tools/function calling，通常以 /v1 结尾</small>
      </div>
      <div class="field full">
        <label>API Key ${cfg.api_key_set ? '' : '*'}</label>
        <input name="api_key" type="password" value="" placeholder="${keyHint}">
        <small class="ai-field-hint">只保存在本机 SQLite，不会返回到浏览器</small>
      </div>
      <div class="field">
        <label>模型名称 *</label>
        <input name="model" value="${TT.esc(cfg.model || '')}" placeholder="deepseek-chat">
      </div>
      <div class="field">
        <label>Temperature</label>
        <input name="temperature" type="number" min="0" max="2" step="0.1" value="${TT.esc(cfg.temperature == null ? 0.7 : cfg.temperature)}">
      </div>
      <div class="field full">
        <label>系统提示词（可选）</label>
        <textarea name="system_prompt" placeholder="不填则使用内置的售前助手提示词">${TT.esc(cfg.system_prompt || '')}</textarea>
      </div>
      <div class="ai-test-row">
        <button type="button" class="btn btn-ghost btn-sm" id="aiTestBtn">测试连接</button>
        <span class="ai-test-result" id="aiTestResult"></span>
      </div>`;
    const modal = TT.modal({
      title: 'AI 助手设置',
      subtitle: '配置一次，所有项目共用；模型调用从本机后端发出，浏览器拿不到 Key。',
      body: body,
      submitText: '保存配置',
      width: 600,
      onSubmit: async function (fd) {
        const payload = {
          api_base: String(fd.get('api_base') || '').trim(),
          model: String(fd.get('model') || '').trim(),
          temperature: Number(fd.get('temperature') || 0.7),
          system_prompt: String(fd.get('system_prompt') || '')
        };
        const key = String(fd.get('api_key') || '').trim();
        if (key) payload.api_key = key;
        if (!payload.api_base || !payload.model) throw new Error('请填写 API Base 与模型名称');
        state.config = await TT.api('/api/ai/config', { method: 'PUT', body: payload });
        renderStatus();
        renderWelcome();
        TT.toast('AI 配置已保存', 'success');
      }
    });

    modal.form.querySelectorAll('[data-preset-base]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        modal.form.querySelector('[name="api_base"]').value = btn.dataset.presetBase;
        modal.form.querySelector('[name="model"]').value = btn.dataset.presetModel;
      });
    });
    const testBtn = modal.form.querySelector('#aiTestBtn');
    const testResult = modal.form.querySelector('#aiTestResult');
    if (testBtn) {
      testBtn.addEventListener('click', async function () {
        const fd = new FormData(modal.form);
        const payload = {
          api_base: String(fd.get('api_base') || '').trim(),
          model: String(fd.get('model') || '').trim(),
          temperature: Number(fd.get('temperature') || 0.7)
        };
        const key = String(fd.get('api_key') || '').trim();
        if (key) payload.api_key = key;
        testBtn.disabled = true;
        testBtn.textContent = '测试中…';
        testResult.className = 'ai-test-result';
        testResult.textContent = '';
        try {
          const data = await TT.api('/api/ai/test', { method: 'POST', body: payload });
          if (data.ok) {
            testResult.className = 'ai-test-result ok';
            testResult.textContent = '连接成功 · ' + (data.model || payload.model);
          } else {
            testResult.className = 'ai-test-result err';
            testResult.textContent = data.error || '连接失败';
          }
        } catch (err) {
          testResult.className = 'ai-test-result err';
          testResult.textContent = err.message;
        } finally {
          testBtn.disabled = false;
          testBtn.textContent = '测试连接';
        }
      });
    }
  }

  // ------------------------------------------------------------------ render
  function render() {
    if (!state.initialized) return;
    renderStatus();
    renderContext();
    renderWelcome();
    renderMessages();
    renderActions();
    renderHistory();
    els.typing.hidden = !state.busy;
    const sendBtn = document.getElementById('aiSendBtn');
    if (sendBtn) sendBtn.disabled = state.busy;
  }

  function renderStatus() {
    const dot = document.getElementById('aiStatusDot');
    const label = document.getElementById('aiStatusText');
    if (!dot || !label) return;
    const cfg = state.config;
    const on = !!(cfg && cfg.configured);
    dot.classList.toggle('on', on);
    if (!cfg) label.textContent = '正在读取配置…';
    else if (on) label.textContent = '已连接 · ' + (cfg.model || '');
    else label.textContent = '未配置模型';
  }

  function renderContext() {
    if (!els.context) return;
    const pid = state.contextProjectId || CFG.projectId || '';
    if (pid) {
      const project = window.TT_PROJECT && window.TT_PROJECT.id === pid ? window.TT_PROJECT : null;
      els.context.innerHTML =
        '<span class="ai-ctx-dot"></span><span>当前项目</span><b>' +
        TT.esc(project ? project.name : '已选中') + '</b>';
    } else {
      els.context.innerHTML =
        '<span class="ai-ctx-dot global"></span><span>全局模式 · 可以管理所有项目</span>';
    }
  }

  function renderWelcome() {
    if (!els.welcome) return;
    const hasMessages = state.messages.some(function (m) {
      return m.role === 'user' || (m.role === 'assistant' && m.content);
    });
    els.welcome.classList.toggle('hidden', hasMessages);
    if (hasMessages) return;

    const configured = !!(state.config && state.config.configured);
    const pid = state.contextProjectId || CFG.projectId;
    const prompts = [
      { label: '新建一个售前项目', text: '帮我新建一个售前项目' },
      { label: '本周要跟进什么', text: '这周需要跟进哪些项目和任务？' },
      { label: pid ? '为当前项目补任务' : '看看项目进展', text: pid ? '我想为当前项目补充任务。请先结合项目现状问我 1–2 个关键问题（任务目标、交付物、截止时间），确认后再生成一个任务草稿，不要一次给多条建议。' : '汇总所有项目的进展和风险' },
      { label: '项目风险汇总', text: '汇总项目风险：逾期任务、待跟进节点和即将到期的事项' }
    ];
    els.welcome.innerHTML = `
      <div class="ai-welcome-mark" aria-hidden="true">✦</div>
      <h2>你好，我是 TopoTash 助手</h2>
      <p>帮你新建售前项目、拆解任务、汇总进展；补任务会先问清目标再起草。所有写入都会先生成草稿，确认后才执行。</p>
      ${configured ? '' : `
        <div class="ai-setup">
          <div><b>还没有配置模型</b><span>配置一次，所有项目通用。</span></div>
          <button type="button" class="btn btn-primary btn-sm" data-ai-config>去配置</button>
        </div>`}
      <div class="ai-quick">
        ${prompts.map(function (p) {
          return '<button type="button" data-ai-prompt="' + TT.esc(p.text) + '">' + TT.esc(p.label) + '</button>';
        }).join('')}
      </div>`;
  }

  function renderMessages() {
    if (!els.msgs) return;
    const html = state.messages.filter(function (m) {
      return m.role === 'user' || m.role === 'assistant';
    }).map(function (m) {
      if (m.role === 'user') {
        return '<div class="ai-msg user"><div class="ai-bubble">' +
          TT.esc(m.content).replace(/\n/g, '<br>') + '</div></div>';
      }
      const toolCalls = m.tool_calls || [];
      const chips = toolCalls.map(function (tc) {
        const name = tc.function && tc.function.name;
        return '<span class="ai-chip">' + TT.esc(TOOL_LABELS[name] || name || '工具') + '</span>';
      }).join('');
      const isError = m.meta && m.meta.error;
      const content = m.content
        ? (isError ? TT.esc(m.content) : renderMarkdown(m.content))
        : '';
      if (!chips && !content) return '';
      return '<div class="ai-msg assistant' + (isError ? ' is-error' : '') + '">' +
        (chips ? '<div class="ai-chips">' + chips + '</div>' : '') +
        (content ? '<div class="ai-bubble">' + content + '</div>' : '') +
        '</div>';
    }).join('');
    els.msgs.innerHTML = html;
  }

  function renderActions() {
    if (!els.actions) return;
    const pending = state.actions.filter(function (a) { return a.status === 'pending'; });
    const applied = state.actions.filter(function (a) { return a.status === 'applied'; });
    let html = '';
    if (pending.length) {
      html += '<div class="ai-actions-title"><span>待确认操作</span><em>' + pending.length + '</em></div>';
      html += pending.map(actionCard).join('');
    }
    if (applied.length) {
      html += '<details class="ai-applied"><summary>已执行的操作（' + applied.length + '）</summary>' +
        applied.map(appliedCard).join('') + '</details>';
    }
    els.actions.innerHTML = html;
  }

  function actionCard(action) {
    const fields = (action.form || []).map(function (field) {
      return fieldHtml(action.id, field, (action.values || {})[field.key]);
    }).join('');
    const summary = (action.summary || []).length
      ? '<ul class="ai-action-summary">' + action.summary.map(function (line) {
        return '<li>' + TT.esc(line) + '</li>';
      }).join('') + '</ul>'
      : '';
    return '<div class="ai-action" data-action="' + TT.esc(action.id) + '">' +
      '<div class="ai-action-head"><span class="ai-badge">草稿</span><b>' + TT.esc(action.title) + '</b></div>' +
      (action.subtitle ? '<div class="ai-action-sub">' + TT.esc(action.subtitle) + '</div>' : '') +
      summary +
      (fields ? '<div class="ai-action-form">' + fields + '</div>' : '') +
      (action.warning ? '<div class="ai-action-warning">' + TT.esc(action.warning) + '</div>' : '') +
      '<div class="ai-action-foot">' +
        '<button type="button" class="btn btn-ghost btn-sm" data-ai-cancel="' + TT.esc(action.id) + '">取消</button>' +
        '<button type="button" class="btn btn-sm ' +
          (action.kind.indexOf('delete') === 0 ? 'btn-danger' : 'btn-primary') +
          '" data-ai-confirm="' + TT.esc(action.id) + '">' + confirmLabel(action.kind) + '</button>' +
      '</div></div>';
  }

  function fieldHtml(actionId, field, value) {
    const key = field.key;
    const inputId = 'af_' + actionId + '_' + key;
    let v = value == null ? '' : String(value);
    if (field.type === 'datetime-local' && v) {
      const date = new Date(v);
      if (!isNaN(date.getTime())) {
        const p = n => String(n).padStart(2, '0');
        v = `${date.getFullYear()}-${p(date.getMonth() + 1)}-${p(date.getDate())}T${p(date.getHours())}:${p(date.getMinutes())}:${p(date.getSeconds())}`;
      }
    }
    let control;
    if (field.type === 'select') {
      control = '<select id="' + inputId + '" data-field="' + TT.esc(key) + '">' +
        (field.options || []).map(function (opt) {
          return '<option value="' + TT.esc(opt.value) + '"' +
            (String(opt.value) === v ? ' selected' : '') + '>' + TT.esc(opt.label) + '</option>';
        }).join('') + '</select>';
    } else if (field.type === 'textarea') {
      control = '<textarea id="' + inputId + '" data-field="' + TT.esc(key) + '" rows="2" placeholder="' +
        TT.esc(field.placeholder || '') + '">' + TT.esc(v) + '</textarea>';
    } else {
      const type = field.type === 'date' ? 'date'
        : field.type === 'datetime-local' ? 'datetime-local'
        : field.type === 'number' ? 'number' : 'text';
      control = '<input id="' + inputId + '" data-field="' + TT.esc(key) + '" type="' + type +
        '" value="' + TT.esc(v) + '"' + (type === 'datetime-local'
          ? ' step="1" data-initial="' + TT.esc(v.replace(/:00$/, '')) +
            '" data-original="' + TT.esc(value || '') + '"' : '') +
        ' placeholder="' + TT.esc(field.placeholder || '') + '">';
    }
    return '<label class="ai-field' + (field.wide ? ' wide' : '') + '" for="' + inputId + '">' +
      '<span>' + TT.esc(field.label) + (field.required ? ' *' : '') + '</span>' +
      control +
      (field.hint ? '<em>' + TT.esc(field.hint) + '</em>' : '') +
      '</label>';
  }

  function appliedCard(action) {
    const result = action.result || {};
    const projectId = (result.project_id || action.project_id) || '';
    const taskId = result.task_id || action.task_id || '';
    let detail = appliedMessage(action);
    if (action.kind === 'create_project' && result.task_count) {
      detail += '，已生成 ' + result.task_count + ' 个起始任务';
    }
    let link = '';
    if (projectId && action.kind !== 'delete_project') {
      link = '<a href="/projects/' + encodeURIComponent(projectId) + '">打开项目 →</a>';
      if (taskId && (action.kind === 'create_task' || action.kind === 'update_task')) {
        link = '<a href="/projects/' + encodeURIComponent(projectId) + '?tab=tasks&task=' +
          encodeURIComponent(taskId) + '">打开任务 →</a>';
      }
    }
    return '<div class="ai-action applied">' +
      '<div class="ai-action-head"><span class="ai-badge ok">已执行</span><b>' + TT.esc(action.title) + '</b></div>' +
      '<div class="ai-action-result"><span>' + TT.esc(detail) + '</span>' + link + '</div>' +
      '</div>';
  }

  function renderHistory() {
    if (!els.history) return;
    els.history.hidden = !state.showHistory;
    if (!state.showHistory) {
      els.history.innerHTML = '';
      return;
    }
    if (!state.conversations.length) {
      els.history.innerHTML = '<div class="ai-history-empty">还没有历史对话</div>';
      return;
    }
    els.history.innerHTML = state.conversations.map(function (conversation) {
      return '<div class="ai-history-item' +
        (conversation.id === state.conversationId ? ' active' : '') +
        '" data-conv="' + TT.esc(conversation.id) + '">' +
        '<div class="ai-history-main"><b>' + TT.esc(conversation.title) + '</b>' +
        '<span>' + TT.esc(conversation.project_name || '全局') + ' · ' +
        TT.esc(TT.relative(conversation.updated_at)) + '</span></div>' +
        '<button type="button" class="ai-history-del" data-del="' + TT.esc(conversation.id) +
        '" title="删除">×</button></div>';
    }).join('');
  }

  function toggleHistory() {
    state.showHistory = !state.showHistory;
    if (state.showHistory) loadConversations().catch(function () {});
    renderHistory();
  }

  function confirmLabel(kind) {
    if (kind === 'delete_project' || kind === 'delete_task') return '确认删除';
    if (kind === 'update_project' || kind === 'update_task') return '保存修改';
    return '确认创建';
  }

  function scrollBottom() {
    if (!els.body) return;
    els.body.scrollTop = els.body.scrollHeight;
  }

  function scrollToDraftOrBottom() {
    const card = els.actions && els.actions.querySelector('.ai-action:not(.applied)');
    if (!card || !els.body) {
      scrollBottom();
      return;
    }
    const delta = card.getBoundingClientRect().top - els.body.getBoundingClientRect().top;
    els.body.scrollTop += delta - 12;
  }

  function autoGrow() {
    if (!els.input) return;
    els.input.style.height = 'auto';
    els.input.style.height = Math.min(120, els.input.scrollHeight) + 'px';
  }

  // ------------------------------------------------------------------ markdown
  function splitRow(row) {
    return row.replace(/^\|/, '').replace(/\|$/, '').split('|').map(function (cell) {
      return cell.trim();
    });
  }

  function inline(text) {
    return text
      .replace(/`([^`]+)`/g, '<code>$1</code>')
      .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
      .replace(/(^|[^*])\*([^*\n]+)\*/g, '$1<em>$2</em>')
      .replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
  }

  function renderMarkdown(text) {
    if (!text) return '';
    const lines = String(text).replace(/\r\n/g, '\n').split('\n');
    let html = '';
    let i = 0;
    let inCode = false;
    let codeLines = [];
    let list = null;

    function closeList() {
      if (list) {
        html += '</' + list + '>';
        list = null;
      }
    }

    while (i < lines.length) {
      const line = lines[i];
      const trimmed = line.trim();

      if (/^```/.test(trimmed)) {
        if (!inCode) {
          closeList();
          inCode = true;
          codeLines = [];
        } else {
          html += '<pre><code>' + TT.esc(codeLines.join('\n')) + '</code></pre>';
          inCode = false;
        }
        i += 1;
        continue;
      }
      if (inCode) {
        codeLines.push(line);
        i += 1;
        continue;
      }
      if (!trimmed) {
        closeList();
        i += 1;
        continue;
      }

      if (trimmed.indexOf('|') >= 0 && i + 1 < lines.length &&
          /^\|?\s*[-:]+[-| :]*\|?$/.test(lines[i + 1].trim())) {
        closeList();
        html += '<table><thead><tr>' + splitRow(trimmed).map(function (cell) {
          return '<th>' + inline(TT.esc(cell)) + '</th>';
        }).join('') + '</tr></thead><tbody>';
        i += 2;
        while (i < lines.length && lines[i].trim().indexOf('|') >= 0) {
          html += '<tr>' + splitRow(lines[i].trim()).map(function (cell) {
            return '<td>' + inline(TT.esc(cell)) + '</td>';
          }).join('') + '</tr>';
          i += 1;
        }
        html += '</tbody></table>';
        continue;
      }

      if (/^#{1,4}\s+/.test(trimmed)) {
        closeList();
        const level = Math.min(trimmed.match(/^#+/)[0].length + 2, 5);
        html += '<h' + level + '>' + inline(TT.esc(trimmed.replace(/^#+\s+/, ''))) +
          '</h' + level + '>';
        i += 1;
        continue;
      }
      if (/^[-*_]{3,}$/.test(trimmed)) {
        closeList();
        html += '<hr>';
        i += 1;
        continue;
      }
      if (/^>\s?/.test(trimmed)) {
        closeList();
        html += '<blockquote>' + inline(TT.esc(trimmed.replace(/^>\s?/, ''))) + '</blockquote>';
        i += 1;
        continue;
      }

      const ordered = trimmed.match(/^(\d+)[.)]\s+(.*)$/);
      const unordered = trimmed.match(/^[-*]\s+(.*)$/);
      if (ordered || unordered) {
        const want = ordered ? 'ol' : 'ul';
        if (list !== want) {
          closeList();
          html += '<' + want + '>';
          list = want;
        }
        html += '<li>' + inline(TT.esc(ordered ? ordered[2] : unordered[1])) + '</li>';
        i += 1;
        continue;
      }

      closeList();
      html += '<p>' + inline(TT.esc(trimmed)) + '</p>';
      i += 1;
    }
    closeList();
    if (inCode) html += '<pre><code>' + TT.esc(codeLines.join('\n')) + '</code></pre>';
    return html;
  }

  window.TTAI = {
    open: open,
    close: close,
    toggle: toggle,
    newChat: newChat,
    openConfig: openConfig,
    state: state
  };

  if (document.body) init();
  else document.addEventListener('DOMContentLoaded', init);
})();
