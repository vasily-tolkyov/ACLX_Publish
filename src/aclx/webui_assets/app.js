const COLLAPSE_STORAGE_KEY = "aclx-ui-collapsed-workspaces";

const state = {
  workspaces: [],
  candidateWorkspaces: [],
  selectedThreadId: null,
  currentThread: null,
  pendingUserMessage: "",
  selectedWorkspacePath: "",
  currentJobId: null,
  pollTimer: null,
  collapsedWorkspaces: loadCollapsedWorkspaces(),
  archivedThreads: [],
};

const workspaceList = document.getElementById("workspaceList");
const conversation = document.getElementById("conversation");
const composer = document.getElementById("composer");
const messageInput = document.getElementById("messageInput");
const sendButton = document.getElementById("sendButton");
const composerStatus = document.getElementById("composerStatus");
const newThreadButton = document.getElementById("newThreadButton");
const archiveThreadButton = document.getElementById("archiveThreadButton");
const archivedThreadsButton = document.getElementById("archivedThreadsButton");

const workspaceModal = document.getElementById("workspaceModal");
const workspaceCandidates = document.getElementById("workspaceCandidates");
const workspacePathInput = document.getElementById("workspacePathInput");
const workspaceError = document.getElementById("workspaceError");
const confirmWorkspaceButton = document.getElementById("confirmWorkspaceButton");
const cancelModalButton = document.getElementById("cancelModalButton");
const closeModalButton = document.getElementById("closeModalButton");

const archiveModal = document.getElementById("archiveModal");
const archivedList = document.getElementById("archivedList");
const closeArchiveModalButton = document.getElementById("closeArchiveModalButton");

function loadCollapsedWorkspaces() {
  try {
    const raw = window.localStorage.getItem(COLLAPSE_STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed.filter((value) => typeof value === "string") : [];
  } catch {
    return [];
  }
}

function saveCollapsedWorkspaces() {
  window.localStorage.setItem(COLLAPSE_STORAGE_KEY, JSON.stringify(state.collapsedWorkspaces));
}

function esc(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function fmtDate(value) {
  if (!value) return "";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString();
}

function cleanInline(value) {
  return String(value ?? "").replace(/\s+/g, " ").trim();
}

function truncateInline(value, limit = 88) {
  const cleaned = cleanInline(value);
  if (cleaned.length <= limit) return cleaned;
  if (limit <= 1) return cleaned.slice(0, limit);
  return `${cleaned.slice(0, limit - 1)}…`;
}

function roleLabel(entry) {
  if (entry.role === "user") return "你";
  if (entry.role === "assistant") return "Codex";
  if (entry.role === "developer") return "系统";
  return "消息";
}

function messageClass(entry) {
  if (entry.role === "user") return "message user";
  return "message";
}

function maybeParseJson(value) {
  if (typeof value !== "string") return null;
  try {
    return JSON.parse(value);
  } catch {
    return null;
  }
}

function summarizeToolField(value) {
  if (value == null) return "";
  if (typeof value === "string") return truncateInline(value, 86);
  if (Array.isArray(value)) {
    if (!value.length) return "";
    const first = value[0];
    if (typeof first === "string") return truncateInline(first, 86);
    if (first && typeof first === "object") {
      if (typeof first.q === "string") return truncateInline(first.q, 86);
      return truncateInline(JSON.stringify(first), 86);
    }
    return truncateInline(String(first), 86);
  }
  if (typeof value === "object") {
    if (typeof value.command === "string") return truncateInline(value.command, 86);
    if (typeof value.q === "string") return truncateInline(value.q, 86);
    if (typeof value.path === "string") return truncateInline(value.path, 86);
    if (typeof value.location === "string") return truncateInline(value.location, 86);
    if (typeof value.message === "string") return truncateInline(value.message, 86);
    if (typeof value.url === "string") return truncateInline(value.url, 86);
    return truncateInline(JSON.stringify(value), 86);
  }
  return truncateInline(String(value), 86);
}

function summarizeToolEntry(entry) {
  const name = cleanInline(entry.name || "工具");
  const parsed = maybeParseJson(entry.text);
  let detail = "";

  if (entry.kind === "tool_call") {
    if (parsed && typeof parsed === "object") {
      const candidates = [
        parsed.command,
        parsed.path,
        parsed.location,
        parsed.message,
        parsed.url,
        parsed.search_query,
        parsed.image_query,
        parsed.ticker,
        parsed.q,
      ];
      detail = summarizeToolField(candidates.find((item) => item != null) ?? parsed);
    } else {
      detail = truncateInline(entry.text || "", 86);
    }
    return truncateInline(`调用 ${name}${detail ? ` · ${detail}` : ""}`, 96);
  }

  if (parsed && typeof parsed === "object") {
    detail = summarizeToolField(parsed.output ?? parsed.result ?? parsed.message ?? parsed);
  } else {
    detail = truncateInline(entry.text || "已返回", 72);
  }
  return truncateInline(`结果 ${name}${detail ? ` · ${detail}` : ""}`, 96);
}

async function getJson(url, options = {}) {
  const response = await fetch(url, options);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.error || `请求失败：${response.status}`);
  }
  return payload;
}

function isWorkspaceCollapsed(workspaceId) {
  return state.collapsedWorkspaces.includes(workspaceId);
}

function toggleWorkspace(workspaceId) {
  if (!workspaceId) return;
  if (isWorkspaceCollapsed(workspaceId)) {
    state.collapsedWorkspaces = state.collapsedWorkspaces.filter((item) => item !== workspaceId);
  } else {
    state.collapsedWorkspaces = [...state.collapsedWorkspaces, workspaceId];
  }
  saveCollapsedWorkspaces();
  renderWorkspaceList();
}

function renderWorkspaceList() {
  if (!state.workspaces.length) {
    workspaceList.innerHTML = `
      <div class="empty-state compact-empty-state">
        <div class="empty-title">还没有线程</div>
        <div class="empty-text">点击上方“添加新线程”即可创建新的草稿线程。</div>
      </div>
    `;
    return;
  }

  workspaceList.innerHTML = state.workspaces
    .map((workspace) => {
      const collapsed = isWorkspaceCollapsed(workspace.id);
      return `
        <section class="workspace-group ${collapsed ? "collapsed" : ""}">
          <button class="workspace-toggle" type="button" data-workspace-id="${esc(workspace.id)}">
            <div class="workspace-head">
              <div class="workspace-icon">区</div>
              <div class="workspace-meta">
                <div class="workspace-title-row">
                  <div class="workspace-title">${esc(workspace.name)}</div>
                  <div class="workspace-count">${esc(String((workspace.threads || []).length))}</div>
                </div>
                <div class="workspace-path">${esc(workspace.path)}</div>
              </div>
              <div class="workspace-arrow">${collapsed ? "▸" : "▾"}</div>
            </div>
          </button>
          <div class="thread-list">
            ${(workspace.threads || [])
              .map(
                (thread) => `
                  <button class="thread-item ${thread.id === state.selectedThreadId ? "active" : ""}" data-thread-id="${esc(thread.id)}" type="button">
                    <span class="thread-name">${esc(thread.title)}</span>
                    <span class="thread-kind">${thread.kind === "draft" ? "草稿" : ""}</span>
                  </button>
                `
              )
              .join("")}
          </div>
        </section>
      `;
    })
    .join("");

  for (const button of workspaceList.querySelectorAll(".workspace-toggle")) {
    button.addEventListener("click", () => toggleWorkspace(button.dataset.workspaceId));
  }

  for (const item of workspaceList.querySelectorAll(".thread-item")) {
    item.addEventListener("click", () => loadThread(item.dataset.threadId));
  }
}

function renderArchiveAction() {
  const hasThread = Boolean(state.currentThread && state.selectedThreadId);
  archiveThreadButton.disabled = !hasThread || Boolean(state.currentJobId);
}

function renderConversation() {
  renderArchiveAction();

  const thread = state.currentThread;
  const pendingEntry = state.pendingUserMessage
    ? [{ kind: "message", role: "user", timestamp: "", text: state.pendingUserMessage, pending: true }]
    : [];

  if (!thread) {
    conversation.className = "conversation empty";
    conversation.innerHTML = `
      <div class="empty-state">
        <div class="empty-title">请选择一个线程</div>
        <div class="empty-text">左侧展示你保留的线程。点击任意线程后，就可以在右侧继续对话。</div>
      </div>
    `;
    return;
  }

  const entries = [...(thread.entries || []), ...pendingEntry];
  if (!entries.length) {
    conversation.className = "conversation empty";
    conversation.innerHTML = `
      <div class="empty-state">
        <div class="empty-title">这是一个新线程</div>
        <div class="empty-text">发送第一条消息后，会自动创建真实 Codex 会话，并继续在这里展示对话记录。</div>
      </div>
    `;
    return;
  }

  conversation.className = "conversation";
  conversation.innerHTML = entries
    .map((entry) => {
      if (entry.kind === "tool_call" || entry.kind === "tool_output") {
        return `
          <div class="inline-tool-event" title="${esc(cleanInline(entry.text || ""))}">
            <span class="inline-tool-text">${esc(summarizeToolEntry(entry))}</span>
          </div>
        `;
      }
      return `
        <article class="${messageClass(entry)} ${entry.pending ? "pending" : ""}">
          <div class="message-head">
            <span class="message-role">${esc(roleLabel(entry))}</span>
            <span>${esc(entry.pending ? "发送中" : fmtDate(entry.timestamp))}</span>
          </div>
          <div class="message-body">${esc(entry.text || "")}</div>
        </article>
      `;
    })
    .join("");
  conversation.scrollTop = conversation.scrollHeight;
}

function renderArchivedThreads() {
  if (!state.archivedThreads.length) {
    archivedList.innerHTML = `
      <div class="empty-state compact-empty-state">
        <div class="empty-title">暂无归档线程</div>
        <div class="empty-text">归档后的线程会出现在这里，最多保留最近 10 条。</div>
      </div>
    `;
    return;
  }

  archivedList.innerHTML = state.archivedThreads
    .map(
      (thread) => `
        <div class="archived-item">
          <div class="archived-meta">
            <div class="archived-title">${esc(thread.title || "未命名线程")}</div>
            <div class="archived-subtitle">${esc(thread.cwd || "")}</div>
            <div class="archived-time">${esc(fmtDate(thread.archived_at))}</div>
          </div>
          <button class="restore-button" type="button" data-archive-id="${esc(thread.id)}">恢复</button>
        </div>
      `
    )
    .join("");

  for (const button of archivedList.querySelectorAll(".restore-button")) {
    button.addEventListener("click", () => restoreArchivedThread(button.dataset.archiveId).catch(showError));
  }
}

async function refreshArchivedThreads() {
  const data = await getJson("/api/archived");
  state.archivedThreads = data.threads || [];
  renderArchivedThreads();
}

async function refreshWorkspaces() {
  const data = await getJson("/api/workspaces");
  state.workspaces = data.workspaces || [];
  state.candidateWorkspaces = data.candidate_workspaces || [];
  renderWorkspaceList();
  renderWorkspaceCandidates();

  if (!state.selectedThreadId) {
    const firstThread = state.workspaces.flatMap((workspace) => workspace.threads || [])[0];
    if (firstThread) {
      await loadThread(firstThread.id);
    } else {
      state.currentThread = null;
      renderConversation();
    }
    return;
  }

  const exists = state.workspaces.some((workspace) => (workspace.threads || []).some((thread) => thread.id === state.selectedThreadId));
  if (!exists) {
    state.selectedThreadId = null;
    state.currentThread = null;
    renderConversation();
  }
}

async function loadThread(threadId) {
  if (!threadId) return;
  state.selectedThreadId = threadId;
  state.pendingUserMessage = "";
  renderWorkspaceList();
  state.currentThread = await getJson(`/api/thread/${encodeURIComponent(threadId)}`);
  renderConversation();
}

function openWorkspaceModal() {
  workspaceError.textContent = "";
  workspacePathInput.value = state.selectedWorkspacePath || state.currentThread?.cwd || state.candidateWorkspaces[0] || "";
  state.selectedWorkspacePath = workspacePathInput.value.trim();
  renderWorkspaceCandidates();
  workspaceModal.classList.remove("hidden");
}

function closeWorkspaceModal() {
  workspaceModal.classList.add("hidden");
  workspaceError.textContent = "";
}

function openArchiveModal() {
  archiveModal.classList.remove("hidden");
  refreshArchivedThreads().catch(showError);
}

function closeArchiveModal() {
  archiveModal.classList.add("hidden");
}

function renderWorkspaceCandidates() {
  workspaceCandidates.innerHTML = state.candidateWorkspaces
    .map(
      (path) => `
        <button class="candidate-button ${path === state.selectedWorkspacePath ? "active" : ""}" type="button" data-path="${esc(path)}">${esc(path)}</button>
      `
    )
    .join("");
  for (const button of workspaceCandidates.querySelectorAll(".candidate-button")) {
    button.addEventListener("click", () => {
      state.selectedWorkspacePath = button.dataset.path;
      workspacePathInput.value = state.selectedWorkspacePath;
      renderWorkspaceCandidates();
    });
  }
}

async function createDraftThread() {
  const cwd = workspacePathInput.value.trim();
  if (!cwd) {
    workspaceError.textContent = "请选择或输入一个工作区路径。";
    return;
  }
  try {
    const draft = await getJson("/api/thread/new", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ cwd }),
    });
    closeWorkspaceModal();
    await refreshWorkspaces();
    await loadThread(draft.id);
    composerStatus.textContent = "已创建草稿线程。";
  } catch (error) {
    workspaceError.textContent = error.message || String(error);
  }
}

function setSendingState(isSending, text) {
  sendButton.disabled = isSending;
  messageInput.disabled = isSending;
  composerStatus.textContent = text;
  renderArchiveAction();
}

async function sendCurrentMessage() {
  const message = messageInput.value.trim();
  if (!message) {
    composerStatus.textContent = "请输入消息。";
    return;
  }
  if (!state.selectedThreadId) {
    composerStatus.textContent = "请先在左侧选择或创建一个线程。";
    return;
  }

  state.pendingUserMessage = message;
  renderConversation();
  setSendingState(true, "正在发送...");

  try {
    const job = await getJson(`/api/thread/${encodeURIComponent(state.selectedThreadId)}/send`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message }),
    });
    state.currentJobId = job.id;
    messageInput.value = "";
    await pollJob();
  } catch (error) {
    state.pendingUserMessage = "";
    renderConversation();
    setSendingState(false, error.message || String(error));
  }
}

async function archiveCurrentThread() {
  if (!state.selectedThreadId || state.currentJobId) return;
  const threadId = state.selectedThreadId;
  const threadTitle = state.currentThread?.title || "当前线程";
  archiveThreadButton.disabled = true;
  composerStatus.textContent = `正在归档：${threadTitle}`;

  try {
    await getJson(`/api/thread/${encodeURIComponent(threadId)}/archive`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
    state.selectedThreadId = null;
    state.currentThread = null;
    state.pendingUserMessage = "";
    await Promise.all([refreshWorkspaces(), refreshArchivedThreads()]);
    composerStatus.textContent = "线程已归档。";
  } catch (error) {
    composerStatus.textContent = error.message || String(error);
    renderArchiveAction();
  }
}

async function restoreArchivedThread(archiveId) {
  const result = await getJson(`/api/archived/${encodeURIComponent(archiveId)}/restore`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({}),
  });
  await Promise.all([refreshArchivedThreads(), refreshWorkspaces()]);
  if (result.thread_id) {
    await loadThread(result.thread_id);
  }
  composerStatus.textContent = "线程已恢复。";
}

async function pollJob() {
  if (!state.currentJobId) return;
  clearTimeout(state.pollTimer);
  const job = await getJson(`/api/jobs/${encodeURIComponent(state.currentJobId)}`);
  if (job.status === "queued" || job.status === "running") {
    setSendingState(true, "Codex 正在处理...");
    state.pollTimer = window.setTimeout(() => pollJob().catch(showError), 1200);
    return;
  }

  state.pendingUserMessage = "";
  state.currentJobId = null;

  if (job.status !== "completed") {
    renderConversation();
    setSendingState(false, job.error || "发送失败。");
    return;
  }

  await refreshWorkspaces();
  if (job.result_thread_id) {
    await loadThread(job.result_thread_id);
  }
  setSendingState(false, "已完成。");
}

function showError(error) {
  setSendingState(false, error.message || String(error));
}

composer.addEventListener("submit", (event) => {
  event.preventDefault();
  sendCurrentMessage().catch(showError);
});

messageInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    sendCurrentMessage().catch(showError);
  }
});

newThreadButton.addEventListener("click", openWorkspaceModal);
archivedThreadsButton.addEventListener("click", openArchiveModal);
archiveThreadButton.addEventListener("click", () => archiveCurrentThread().catch(showError));
confirmWorkspaceButton.addEventListener("click", createDraftThread);
cancelModalButton.addEventListener("click", closeWorkspaceModal);
closeModalButton.addEventListener("click", closeWorkspaceModal);
closeArchiveModalButton.addEventListener("click", closeArchiveModal);
workspacePathInput.addEventListener("input", () => {
  state.selectedWorkspacePath = workspacePathInput.value.trim();
  workspaceError.textContent = "";
  renderWorkspaceCandidates();
});

for (const element of workspaceModal.querySelectorAll("[data-close-modal='1']")) {
  element.addEventListener("click", closeWorkspaceModal);
}

for (const element of archiveModal.querySelectorAll("[data-close-archive-modal='1']")) {
  element.addEventListener("click", closeArchiveModal);
}

Promise.all([refreshWorkspaces(), refreshArchivedThreads()]).catch(showError);
