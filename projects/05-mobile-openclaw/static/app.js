const SESSION_KEY = "openclaw-mobile-session";
const initialSessionId = window.__SESSION_ID__;
const sessionId = localStorage.getItem(SESSION_KEY) || initialSessionId;
localStorage.setItem(SESSION_KEY, sessionId);

const chatWindow = document.getElementById("chatWindow");
const form = document.getElementById("messageForm");
const textInput = document.getElementById("textInput");
const fileInput = document.getElementById("imageInput");
const kbQuickInput = document.getElementById("kbQuickInput");
const kbFileInput = document.getElementById("kbFileInput");
const sendButton = document.getElementById("sendButton");
const clearButton = document.getElementById("clearButton");
const fileHint = document.getElementById("fileHint");
const hiddenSessionInput = document.getElementById("sessionId");
const chips = document.querySelectorAll(".chip");
const uploadPreview = document.getElementById("uploadPreview");
const kbHint = document.getElementById("kbHint");
const docList = document.getElementById("docList");
const menuButton = document.getElementById("menuButton");
const closeMenuButton = document.getElementById("closeMenuButton");
const menuSheet = document.getElementById("menuSheet");
const quickActions = document.getElementById("quickActions");

const knowledgeMenuButton = document.getElementById("knowledgeMenuButton");
const scheduleMenuButton = document.getElementById("scheduleMenuButton");
const skillsMenuButton = document.getElementById("skillsMenuButton");
const memoryMenuButton = document.getElementById("memoryMenuButton");
const emailsMenuButton = document.getElementById("emailsMenuButton");

const knowledgeModal = document.getElementById("knowledgeModal");
const scheduleModal = document.getElementById("scheduleModal");
const skillsModal = document.getElementById("skillsModal");
const memoryModal = document.getElementById("memoryModal");
const emailsModal = document.getElementById("emailsModal");

const taskList = document.getElementById("taskList");
const taskHint = document.getElementById("taskHint");
const refreshTasksButton = document.getElementById("refreshTasksButton");

const skillsList = document.getElementById("skillsList");
const skillsHint = document.getElementById("skillsHint");
const refreshSkillsButton = document.getElementById("refreshSkillsButton");

const memoryList = document.getElementById("memoryList");
const memoryHint = document.getElementById("memoryHint");
const refreshMemoryButton = document.getElementById("refreshMemoryButton");

const emailsList = document.getElementById("emailsList");
const emailsHint = document.getElementById("emailsHint");
const refreshEmailsButton = document.getElementById("refreshEmailsButton");
const mobileBrandTitle = document.querySelector(".brand-title-mobile");

hiddenSessionInput.value = sessionId;

let previewUrl = null;
let activeMenuTab = "knowledge";
let selectedMemoryId = "";
let selectedEmailId = "";
let currentMessages = [];
let isStreamingReply = false;
const taskCardState = new Map();
let lastMessagesSignature = "";

function escapeHtml(text) {
    return String(text || "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
}

function escapeAttr(text) {
    return escapeHtml(text).replace(/`/g, "&#96;");
}

function normalizeMarkdownSource(text) {
    return String(text || "")
        .replace(/\r\n/g, "\n")
        .replace(/<\s*br\s*\/?\s*>/gi, "\n")
        .replace(/&lt;\s*br\s*\/?\s*&gt;/gi, "\n")
        .replace(/&#x3c;\s*br\s*\/?\s*&#x3e;/gi, "\n")
        .replace(/&#60;\s*br\s*\/?\s*&#62;/gi, "\n");
}

function renderInlineMarkdown(text) {
    let html = escapeHtml(text);
    html = html.replace(/`([^`]+)`/g, "<code>$1</code>");
    html = html.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noreferrer">$1</a>');
    html = html.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    html = html.replace(/__([^_]+)__/g, "<strong>$1</strong>");
    html = html.replace(/(^|[\s(])\*([^*\n]+)\*(?=[\s).,!?:;]|$)/g, "$1<em>$2</em>");
    html = html.replace(/(^|[\s(])_([^_\n]+)_(?=[\s).,!?:;]|$)/g, "$1<em>$2</em>");
    return html;
}

function renderParagraphMarkdown(text) {
    return renderInlineMarkdown(text).replace(/\n/g, "<br />");
}

function renderMarkdown(text) {
    const lines = normalizeMarkdownSource(text).split("\n");
    const blocks = [];
    let index = 0;

    while (index < lines.length) {
        const trimmed = lines[index].trim();
        if (!trimmed) {
            index += 1;
            continue;
        }

        if (trimmed.startsWith("```")) {
            const language = trimmed.slice(3).trim();
            const codeLines = [];
            index += 1;
            while (index < lines.length && !lines[index].trim().startsWith("```")) {
                codeLines.push(lines[index]);
                index += 1;
            }
            if (index < lines.length) {
                index += 1;
            }
            const languageHtml = language ? `<div class="code-meta"><span class="code-lang">${escapeHtml(language)}</span></div>` : "";
            blocks.push(`<pre><code>${escapeHtml(codeLines.join("\n"))}</code></pre>${languageHtml}`);
            continue;
        }

        if (/^#{1,6}\s/.test(trimmed)) {
            const level = Math.min(trimmed.match(/^#+/)[0].length, 6);
            const content = trimmed.replace(/^#{1,6}\s+/, "");
            blocks.push(`<h${level}>${renderInlineMarkdown(content)}</h${level}>`);
            index += 1;
            continue;
        }

        if (/^>\s?/.test(trimmed)) {
            const quoteLines = [];
            while (index < lines.length && /^>\s?/.test(lines[index].trim())) {
                quoteLines.push(lines[index].trim().replace(/^>\s?/, ""));
                index += 1;
            }
            blocks.push(`<blockquote>${quoteLines.map((item) => renderInlineMarkdown(item)).join("<br />")}</blockquote>`);
            continue;
        }

        if (/^(-{3,}|\*{3,})$/.test(trimmed)) {
            blocks.push("<hr />");
            index += 1;
            continue;
        }

        if (/^(\-|\*|\+)\s+/.test(trimmed)) {
            const items = [];
            while (index < lines.length && /^(\-|\*|\+)\s+/.test(lines[index].trim())) {
                items.push(lines[index].trim().replace(/^(\-|\*|\+)\s+/, ""));
                index += 1;
            }
            blocks.push(`<ul>${items.map((item) => `<li>${renderInlineMarkdown(item)}</li>`).join("")}</ul>`);
            continue;
        }

        if (/^\d+\.\s+/.test(trimmed)) {
            const items = [];
            while (index < lines.length && /^\d+\.\s+/.test(lines[index].trim())) {
                items.push(lines[index].trim().replace(/^\d+\.\s+/, ""));
                index += 1;
            }
            blocks.push(`<ol>${items.map((item) => `<li>${renderInlineMarkdown(item)}</li>`).join("")}</ol>`);
            continue;
        }

        const paragraph = [];
        while (index < lines.length) {
            const current = lines[index];
            const currentTrimmed = current.trim();
            if (
                !currentTrimmed ||
                currentTrimmed.startsWith("```") ||
                /^#{1,6}\s/.test(currentTrimmed) ||
                /^>\s?/.test(currentTrimmed) ||
                /^(-{3,}|\*{3,})$/.test(currentTrimmed) ||
                /^(\-|\*|\+)\s+/.test(currentTrimmed) ||
                /^\d+\.\s+/.test(currentTrimmed)
            ) {
                break;
            }
            paragraph.push(currentTrimmed);
            index += 1;
        }
        blocks.push(`<p>${renderParagraphMarkdown(paragraph.join("\n"))}</p>`);
    }

    return blocks.join("");
}

function formatDateTime(value) {
    if (!value) {
        return "--";
    }
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
        return String(value);
    }
    return new Intl.DateTimeFormat("zh-CN", {
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
        hour12: false,
    }).format(date).replace(/\//g, "-");
}

function getTaskStatusMeta(status) {
    if (status === "done") {
        return { label: "已完成", className: "done" };
    }
    if (status === "running") {
        return { label: "推送中", className: "running" };
    }
    if (status === "failed") {
        return { label: "失败", className: "failed" };
    }
    return { label: "等待中", className: "pending" };
}

function inferSkillPlan(text, file) {
    const prompt = String(text || "");
    const compact = prompt.replace(/\s+/g, "");
    const skills = [];

    if (file) {
        skills.push("看图分析");
    }
    if (compact.includes("邮件") || compact.includes("群发") || compact.includes("会议纪要") || compact.includes("考试认知")) {
        skills.push("邮件发送");
    }
    if (compact.includes("秒后") && (compact.includes("AI资讯") || compact.includes("AI早报") || compact.includes("推送"))) {
        skills.push("定时任务");
    }
    if ((compact.includes("安装") || compact.includes("install")) && (compact.includes("skill") || compact.includes("技能"))) {
        skills.push("技能安装");
    }
    if (/https?:\/\//i.test(prompt) && (compact.includes("访问") || compact.includes("打开网页") || compact.includes("页面") || compact.includes("点击") || compact.includes("浏览器"))) {
        skills.push("浏览器操作");
    }
    if (compact.includes("数据库技能") || compact.includes("连接数据库") || compact.includes("列出表") || compact.includes("select")) {
        skills.push("数据库技能");
    }
    if (compact.includes("联网") || compact.includes("搜索") || compact.includes("最新")) {
        skills.push("联网搜索");
    }
    if (!file && !skills.includes("联网搜索") && !skills.includes("邮件发送") && !skills.includes("定时任务")) {
        skills.push("会话记忆");
    }
    if (!file && !compact.includes("联网") && !compact.includes("搜索")) {
        skills.push("知识库问答");
    }

    const uniqueSkills = Array.from(new Set(skills));
    return {
        title: uniqueSkills.length ? "智能体思考过程" : "",
        skills: uniqueSkills,
        steps: uniqueSkills.map((skill) => ({
            label: `调用 ${skill}`,
            status: "running",
            detail: "正在准备并执行该能力",
        })),
    };
}

function setActiveMenuTab(tab) {
    activeMenuTab = tab;
    knowledgeMenuButton.classList.toggle("active", tab === "knowledge");
    scheduleMenuButton.classList.toggle("active", tab === "schedule");
    skillsMenuButton.classList.toggle("active", tab === "skills");
    memoryMenuButton.classList.toggle("active", tab === "memory");
    emailsMenuButton.classList.toggle("active", tab === "emails");
    knowledgeModal.classList.toggle("hidden", tab !== "knowledge");
    scheduleModal.classList.toggle("hidden", tab !== "schedule");
    skillsModal.classList.toggle("hidden", tab !== "skills");
    memoryModal.classList.toggle("hidden", tab !== "memory");
    emailsModal.classList.toggle("hidden", tab !== "emails");
}

function toggleMenu(open) {
    menuSheet.classList.toggle("hidden", !open);
}

function syncQuickActionsVisibility() {
    quickActions.classList.toggle("hidden", Boolean(textInput.value.trim()));
}

function renderDocuments(documents) {
    if (!documents.length) {
        docList.innerHTML = '<p class="empty-state">还没有添加本地知识</p>';
        return;
    }
    docList.innerHTML = documents.map((doc) => `
        <article class="doc-card">
            <div class="doc-row">
                <div>
                    <strong>${escapeHtml(doc.file_name)}</strong>
                    <span>${escapeHtml(String(doc.chunk_count || 0))} 个片段</span>
                </div>
                <button type="button" class="doc-delete" data-doc-id="${escapeAttr(doc.doc_id)}">删除</button>
            </div>
        </article>
    `).join("");
    docList.querySelectorAll(".doc-delete").forEach((button) => {
        button.addEventListener("click", () => deleteKnowledgeFile(button.dataset.docId || ""));
    });
}

function renderTasks(tasks) {
    if (!tasks.length) {
        taskList.innerHTML = '<p class="empty-state">最近还没有定时任务</p>';
        return;
    }
    taskList.innerHTML = tasks.map((task) => {
        const statusMeta = getTaskStatusMeta(task.status);
        const timeline = [
            `创建：${formatDateTime(task.created_at)}`,
            `计划：${formatDateTime(task.run_at)}`,
            task.started_at ? `开始：${formatDateTime(task.started_at)}` : "",
            task.finished_at ? `完成：${formatDateTime(task.finished_at)}` : "",
        ].filter(Boolean).join(" · ");
        return `
            <article class="task-history-card">
                <div class="task-history-head">
                    <strong>${escapeHtml(task.prompt_text || "AI 早报定时任务")}</strong>
                    <span class="task-history-status ${statusMeta.className}">${statusMeta.label}</span>
                </div>
                <p class="task-history-time">${escapeHtml(timeline)}</p>
                <p class="task-history-id">任务编号：${escapeHtml(String(task.task_id || "").slice(0, 8))}</p>
            </article>
        `;
    }).join("");
}

function renderSkills(skills) {
    if (!skills.length) {
        skillsList.innerHTML = '<p class="empty-state">当前还没有可展示的 Skills</p>';
        return;
    }
    skillsList.innerHTML = skills.map((skill) => `
        <article class="task-history-card">
            <div class="task-history-head">
                <strong>${escapeHtml(skill.name)}</strong>
                <span class="task-history-status done">已启用</span>
            </div>
            <p class="task-history-time">${escapeHtml(skill.description)}</p>
            <p class="task-history-id">能力标识：${escapeHtml(skill.id)}</p>
        </article>
    `).join("");
}

function renderMemory(memory) {
    if (!memory || !memory.message_count) {
        memoryList.innerHTML = '<p class="empty-state">当前会话还没有形成记忆</p>';
        selectedMemoryId = "";
        return;
    }

    const memories = memory.recent_memories || [];
    if (!memories.length) {
        memoryList.innerHTML = `
            <article class="task-history-card">
                <div class="task-history-head">
                    <strong>会话摘要</strong>
                    <span class="task-history-status done">已激活</span>
                </div>
                <p class="task-history-time">总消息数：${escapeHtml(String(memory.message_count))} · 用户消息：${escapeHtml(String(memory.user_message_count))} · Agent 回复：${escapeHtml(String(memory.assistant_message_count))}</p>
                <p class="task-history-id">最近更新时间：${escapeHtml(formatDateTime(memory.latest_created_at))}</p>
            </article>
            <p class="empty-state">最近还没有可预览的记忆</p>
        `;
        selectedMemoryId = "";
        return;
    }

    if (!memories.some((item) => item.memory_id === selectedMemoryId)) {
        selectedMemoryId = memories[0].memory_id;
    }
    const activeMemory = memories.find((item) => item.memory_id === selectedMemoryId) || memories[0];
    memoryList.innerHTML = `
        <article class="task-history-card">
            <div class="task-history-head">
                <strong>会话摘要</strong>
                <span class="task-history-status done">已激活</span>
            </div>
            <p class="task-history-time">总消息数：${escapeHtml(String(memory.message_count))} · 用户消息：${escapeHtml(String(memory.user_message_count))} · Agent 回复：${escapeHtml(String(memory.assistant_message_count))}</p>
            <p class="task-history-id">最近更新时间：${escapeHtml(formatDateTime(memory.latest_created_at))}</p>
        </article>
        <div class="preview-layout">
            <div class="preview-list">
                ${memories.map((item) => `
                    <button type="button" class="preview-button ${item.memory_id === selectedMemoryId ? "active" : ""}" data-memory-id="${escapeAttr(item.memory_id)}">
                        <strong>${escapeHtml(item.title)}</strong>
                        <span>${escapeHtml(formatDateTime(item.created_at))}</span>
                    </button>
                `).join("")}
            </div>
            <article class="preview-panel">
                <div class="task-history-head">
                    <strong>${escapeHtml(activeMemory.title)}</strong>
                    <span class="task-history-status done">可预览</span>
                </div>
                <p class="task-history-time">提问时间：${escapeHtml(formatDateTime(activeMemory.created_at))}</p>
                <div class="preview-block">
                    <span class="preview-label">用户问题</span>
                    <p>${escapeHtml(activeMemory.user_content)}</p>
                </div>
                <div class="preview-block">
                    <span class="preview-label">Agent 记忆摘要</span>
                    <p>${escapeHtml(activeMemory.assistant_preview || "暂无对应回复预览")}</p>
                </div>
            </article>
        </div>
    `;
}

function renderEmails(emails) {
    if (!emails.length) {
        emailsList.innerHTML = '<p class="empty-state">当前会话还没有发送过邮件</p>';
        selectedEmailId = "";
        return;
    }

    if (!emails.some((item) => item.email_id === selectedEmailId)) {
        selectedEmailId = emails[0].email_id;
    }
    const activeEmail = emails.find((item) => item.email_id === selectedEmailId) || emails[0];
    emailsList.innerHTML = `
        <div class="preview-layout">
            <div class="preview-list">
                ${emails.map((item) => `
                    <button type="button" class="preview-button ${item.email_id === selectedEmailId ? "active" : ""}" data-email-id="${escapeAttr(item.email_id)}">
                        <strong>${escapeHtml(item.subject)}</strong>
                        <span>${escapeHtml(formatDateTime(item.sent_at || item.created_at))}</span>
                    </button>
                `).join("")}
            </div>
            <article class="preview-panel">
                <div class="task-history-head">
                    <strong>${escapeHtml(activeEmail.subject)}</strong>
                    <span class="task-history-status done">已发送</span>
                </div>
                <p class="task-history-time">收件人：${escapeHtml(activeEmail.recipients)} · 发送时间：${escapeHtml(formatDateTime(activeEmail.sent_at || activeEmail.created_at))}</p>
                <div class="message-body email-body">${renderMarkdown(activeEmail.body_markdown || "")}</div>
            </article>
        </div>
    `;
}

function renderSteps(steps) {
    if (!steps || !steps.length) {
        return "";
    }
    return `
        <div class="task-steps">
            ${steps.map((step) => `
                <div class="step-item ${escapeAttr(step.status || "pending")}">
                    <span class="step-dot"></span>
                    <div>
                        <strong>${escapeHtml(step.label)}</strong>
                        <p>${escapeHtml(step.detail)}</p>
                    </div>
                </div>
            `).join("")}
        </div>
    `;
}

function renderSkillTags(skills) {
    if (!skills || !skills.length) {
        return "";
    }
    return `
        <div class="skill-tags">
            ${skills.map((skill) => `<span class="skill-tag">${escapeHtml(skill)}</span>`).join("")}
        </div>
    `;
}

function getTaskCardKey(turn, index) {
    return [turn.role || "", turn.task_title || "", turn.content || "", turn.image_name || "", String(index)].join("::");
}

function renderTaskCard(taskTitle, steps, taskKey, skills) {
    if (!taskTitle) {
        return "";
    }
    const isOpen = taskCardState.get(taskKey) === true;
    const stepCount = Array.isArray(steps) ? `${steps.length} 个步骤` : "查看过程";
    return `
        <details class="task-card"${isOpen ? " open" : ""} data-task-key="${escapeAttr(taskKey)}">
            <summary class="task-summary">
                <div class="task-summary-text">
                    <span class="task-title">${escapeHtml(taskTitle)}</span>
                    <span class="task-meta">${escapeHtml(stepCount)}</span>
                    ${renderSkillTags(skills)}
                </div>
                <span class="task-toggle" aria-hidden="true"></span>
            </summary>
            ${renderSteps(steps)}
        </details>
    `;
}

function setMessages(messages) {
    const nextMessages = Array.isArray(messages) ? messages : [];
    const nextSignature = JSON.stringify(nextMessages);
    if (nextSignature === lastMessagesSignature) {
        currentMessages = nextMessages;
        return;
    }
    currentMessages = nextMessages;
    lastMessagesSignature = nextSignature;
    renderMessages(currentMessages);
}

function renderMessages(messages) {
    const existingStage = chatWindow.querySelector(".chat-stage");
    const scrollHost = existingStage || chatWindow;
    const stickToBottom = scrollHost.scrollHeight - scrollHost.scrollTop - scrollHost.clientHeight < 48;
    const previousScrollTop = scrollHost.scrollTop;
    const previousScrollHeight = scrollHost.scrollHeight;
    if (!messages.length) {
        chatWindow.innerHTML = `
            <div class="chat-stage">
                <div class="welcome-card">
                    <strong>🦞 我是清云小清虾</strong>
                    <p>来自武汉技术平台部，可以陪你聊天、看图分析、结合本地知识回答问题，也能帮你安排和执行任务。</p>
                </div>
            </div>
        `;
        return;
    }

    const messageHtml = messages.map((turn, index) => {
        const imageHtml = turn.image_url
            ? `<img class="message-thumb" src="${escapeAttr(turn.image_url)}" alt="${escapeAttr(turn.image_name || "上传图片")}" />`
            : "";
        const taskHtml = renderTaskCard(turn.task_title, turn.steps, getTaskCardKey(turn, index), turn.skills);
        const isThinking = turn.role === "assistant" && !String(turn.content || "").trim();
        const bodyHtml = turn.role === "assistant"
            ? (isThinking ? '<p class="thinking-text">正在思考中...</p>' : renderMarkdown(turn.content))
            : `<p>${escapeHtml(turn.content).replace(/\n/g, "<br />")}</p>`;
        const copyPayload = [
            turn.task_title ? `${turn.task_title}\n` : "",
            String(turn.content || "").trim(),
        ].filter(Boolean).join("\n\n");
        return `
            <article class="message ${escapeAttr(turn.role)}" data-copy-content="${escapeAttr(copyPayload)}">
                <button type="button" class="copy-button" data-copy-message title="复制这条消息">复制</button>
                <span class="role-label">${turn.role === "assistant" ? "🦞小清虾" : "你"}</span>
                ${imageHtml}
                ${taskHtml}
                <div class="message-body">${bodyHtml}</div>
            </article>
        `;
    }).join("");

    chatWindow.innerHTML = `<div class="chat-stage">${messageHtml}</div>`;

    const nextScrollHost = chatWindow.querySelector(".chat-stage");
    if (nextScrollHost) {
        if (stickToBottom) {
            nextScrollHost.scrollTop = nextScrollHost.scrollHeight;
        } else {
            const heightDelta = nextScrollHost.scrollHeight - previousScrollHeight;
            nextScrollHost.scrollTop = Math.max(0, previousScrollTop + heightDelta);
        }
    }
}

function clearPreview() {
    uploadPreview.classList.add("hidden");
    uploadPreview.innerHTML = "";
    if (previewUrl) {
        URL.revokeObjectURL(previewUrl);
        previewUrl = null;
    }
}

function renderUploadPreview() {
    const file = fileInput.files?.[0];
    if (!file) {
        clearPreview();
        fileHint.textContent = "回车发送，Shift + 回车换行。默认会结合已添加的知识回答。";
        return;
    }
    if (previewUrl) {
        URL.revokeObjectURL(previewUrl);
    }
    previewUrl = URL.createObjectURL(file);
    uploadPreview.innerHTML = `
        <div class="preview-chip">
            <img src="${escapeAttr(previewUrl)}" alt="${escapeAttr(file.name)}" />
            <div class="preview-meta">
                <strong>待发送图片</strong>
                <span>${escapeHtml(file.name)}</span>
            </div>
        </div>
    `;
    uploadPreview.classList.remove("hidden");
    fileHint.textContent = "图片已就绪，发送后会显示在消息里。";
}

async function loadHistory() {
    if (isStreamingReply) {
        return;
    }
    const response = await fetch(`/api/history?session_id=${encodeURIComponent(sessionId)}`);
    const data = await response.json();
    setMessages(data.messages || []);
}

async function loadDocuments() {
    const response = await fetch("/api/kb-docs");
    const data = await response.json();
    renderDocuments(data.documents || []);
}

async function loadTasks() {
    taskHint.textContent = "正在加载最近任务...";
    try {
        const response = await fetch(`/api/tasks?session_id=${encodeURIComponent(sessionId)}`);
        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.detail || "加载任务失败");
        }
        renderTasks(data.tasks || []);
        taskHint.textContent = "展示最近 10 条定时任务，包含状态和时间信息。";
    } catch (error) {
        taskHint.textContent = error.message || "加载任务失败";
        taskList.innerHTML = "";
    }
}

async function loadSkills() {
    skillsHint.textContent = "正在加载 Skills...";
    try {
        const response = await fetch("/api/skills");
        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.detail || "加载 Skills 失败");
        }
        renderSkills(data.skills || []);
        skillsHint.textContent = "这里展示当前 OpenClaw 示例已经接入的能力。";
    } catch (error) {
        skillsHint.textContent = error.message || "加载 Skills 失败";
        skillsList.innerHTML = "";
    }
}

async function loadMemory() {
    memoryHint.textContent = "正在读取当前会话记忆...";
    try {
        const response = await fetch(`/api/memory?session_id=${encodeURIComponent(sessionId)}`);
        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.detail || "加载记忆失败");
        }
        renderMemory(data.memory);
        memoryHint.textContent = "这里会展示当前 session 的最近记忆摘要，并支持点击预览。";
    } catch (error) {
        memoryHint.textContent = error.message || "加载记忆失败";
        memoryList.innerHTML = "";
    }
}

async function loadEmails() {
    emailsHint.textContent = "正在加载最近邮件...";
    try {
        const response = await fetch(`/api/emails?session_id=${encodeURIComponent(sessionId)}`);
        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.detail || "加载邮件失败");
        }
        renderEmails(data.emails || []);
        emailsHint.textContent = "这里会展示当前会话发送过的邮件，并支持点击预览。";
    } catch (error) {
        emailsHint.textContent = error.message || "加载邮件失败";
        emailsList.innerHTML = "";
    }
}

async function uploadKnowledgeFile(file) {
    const formData = new FormData();
    formData.append("file", file);
    kbHint.textContent = "正在解析文档...";
    try {
        const response = await fetch("/api/kb-upload", { method: "POST", body: formData });
        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.detail || "上传失败");
        }
        renderDocuments(data.documents || []);
        kbHint.textContent = `已添加知识：${data.document.file_name}`;
        fileHint.textContent = "知识已更新，后续对话会默认结合这些知识。";
    } catch (error) {
        kbHint.textContent = error.message || "上传失败";
    }
}

async function deleteKnowledgeFile(docId) {
    if (!docId) {
        return;
    }
    const formData = new FormData();
    formData.append("doc_id", docId);
    kbHint.textContent = "正在删除知识...";
    try {
        const response = await fetch("/api/kb-delete", { method: "POST", body: formData });
        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.detail || "删除失败");
        }
        renderDocuments(data.documents || []);
        kbHint.textContent = "知识已删除。";
    } catch (error) {
        kbHint.textContent = error.message || "删除失败";
    }
}

function addOptimisticTurns(text, file) {
    const nextMessages = currentMessages.slice();
    const plan = inferSkillPlan(text, file);
    nextMessages.push({
        role: "user",
        content: text || "请帮我分析这张图片。",
        image_name: file?.name || "",
    });
    nextMessages.push({
        role: "assistant",
        content: "",
        task_title: plan.title,
        steps: plan.steps,
        skills: plan.skills,
        created_at: new Date().toISOString(),
    });
    setMessages(nextMessages);
    if (plan.skills.includes("技能安装")) {
        skillsHint.textContent = "检测到技能安装任务，Skills 面板会自动刷新。";
        window.setTimeout(loadSkills, 1200);
    }
}

function appendStreamingDelta(delta) {
    if (!currentMessages.length) {
        return;
    }
    const assistantTurn = currentMessages[currentMessages.length - 1];
    if (!assistantTurn || assistantTurn.role !== "assistant") {
        return;
    }
    assistantTurn.content = `${assistantTurn.content || ""}${delta || ""}`;
    renderMessages(currentMessages);
}

function parseSseEvent(rawEvent) {
    const lines = rawEvent.split("\n");
    let eventName = "message";
    const dataLines = [];
    for (const line of lines) {
        if (line.startsWith("event:")) {
            eventName = line.slice(6).trim();
        } else if (line.startsWith("data:")) {
            dataLines.push(line.slice(5).trim());
        }
    }
    return {
        event: eventName,
        data: dataLines.length ? JSON.parse(dataLines.join("\n")) : {},
    };
}

async function consumeStreamResponse(response) {
    if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.detail || "请求失败");
    }
    if (!response.body) {
        throw new Error("当前浏览器不支持流式读取");
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder("utf-8");
    let buffer = "";

    while (true) {
        const { value, done } = await reader.read();
        buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
        buffer = buffer.replace(/\r\n/g, "\n");

        let splitIndex = buffer.indexOf("\n\n");
        while (splitIndex >= 0) {
            const rawEvent = buffer.slice(0, splitIndex).trim();
            buffer = buffer.slice(splitIndex + 2);
            if (rawEvent) {
                const { event, data } = parseSseEvent(rawEvent);
                if (event === "delta") {
                    appendStreamingDelta(data.delta || "");
                } else if (event === "done") {
                    setMessages(data.messages || currentMessages);
                    return;
                } else if (event === "error") {
                    throw new Error(data.detail || "流式回复失败");
                }
            }
            splitIndex = buffer.indexOf("\n\n");
        }

        if (done) {
            if (buffer.trim()) {
                const { event, data } = parseSseEvent(buffer.trim());
                if (event === "delta") {
                    appendStreamingDelta(data.delta || "");
                } else if (event === "done") {
                    setMessages(data.messages || currentMessages);
                } else if (event === "error") {
                    throw new Error(data.detail || "流式回复失败");
                }
            }
            break;
        }
    }
}

async function postMessage(formData) {
    sendButton.disabled = true;
    sendButton.textContent = "发送中...";
    fileHint.textContent = "";

    const text = textInput.value.trim();
    const file = fileInput.files?.[0];
    addOptimisticTurns(text, file);
    isStreamingReply = true;

    try {
        const response = await fetch("/api/message-stream", {
            method: "POST",
            body: formData,
        });
        await consumeStreamResponse(response);
        await Promise.all([loadTasks(), loadSkills(), loadMemory(), loadEmails()]);
        textInput.value = "";
        syncQuickActionsVisibility();
        fileInput.value = "";
        clearPreview();
        fileHint.textContent = "";
    } catch (error) {
        fileHint.textContent = error.message || "请求失败";
        await loadHistory().catch(() => {});
    } finally {
        isStreamingReply = false;
        sendButton.disabled = false;
        sendButton.textContent = "发送";
    }
}

async function clearContext() {
    const formData = new FormData();
    formData.append("session_id", sessionId);
    clearButton.disabled = true;
    try {
        const response = await fetch("/api/clear", { method: "POST", body: formData });
        const data = await response.json();
        if (!response.ok || !data.ok) {
            throw new Error(data.detail || "清空失败");
        }
        taskCardState.clear();
        selectedMemoryId = "";
        selectedEmailId = "";
        setMessages([]);
        await loadMemory();
        textInput.value = "";
        syncQuickActionsVisibility();
        fileInput.value = "";
        clearPreview();
        fileHint.textContent = "上下文已清空，可以重新开始对话。";
    } catch (error) {
        fileHint.textContent = error.message || "清空失败";
    } finally {
        clearButton.disabled = false;
    }
}

fileInput.addEventListener("change", renderUploadPreview);

kbFileInput.addEventListener("change", () => {
    const file = kbFileInput.files?.[0];
    if (file) {
        uploadKnowledgeFile(file);
        kbFileInput.value = "";
    }
});

kbQuickInput.addEventListener("change", () => {
    const file = kbQuickInput.files?.[0];
    if (file) {
        uploadKnowledgeFile(file);
        kbQuickInput.value = "";
    }
});

form.addEventListener("submit", (event) => {
    event.preventDefault();
    const text = textInput.value.trim();
    const file = fileInput.files?.[0];
    if (!text && !file) {
        fileHint.textContent = "请输入消息或上传图片。";
        return;
    }
    const formData = new FormData();
    formData.append("session_id", sessionId);
    formData.append("text", text);
    if (file) {
        formData.append("image", file);
    }
    postMessage(formData);
});

textInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        form.requestSubmit();
    }
});

textInput.addEventListener("input", syncQuickActionsVisibility);

chips.forEach((chip) => {
    chip.addEventListener("click", () => {
        textInput.value = chip.dataset.prompt || "";
        syncQuickActionsVisibility();
        textInput.focus();
    });
});

menuButton.addEventListener("click", () => {
    toggleMenu(true);
    if (activeMenuTab === "schedule") {
        loadTasks();
    } else if (activeMenuTab === "skills") {
        loadSkills();
    } else if (activeMenuTab === "memory") {
        loadMemory();
    } else if (activeMenuTab === "emails") {
        loadEmails();
    }
});

closeMenuButton.addEventListener("click", () => toggleMenu(false));
menuSheet.addEventListener("click", (event) => {
    if (event.target === menuSheet) {
        toggleMenu(false);
    }
});

knowledgeMenuButton.addEventListener("click", () => setActiveMenuTab("knowledge"));
scheduleMenuButton.addEventListener("click", () => {
    setActiveMenuTab("schedule");
    loadTasks();
});
skillsMenuButton.addEventListener("click", () => {
    setActiveMenuTab("skills");
    loadSkills();
});
memoryMenuButton.addEventListener("click", () => {
    setActiveMenuTab("memory");
    loadMemory();
});
emailsMenuButton.addEventListener("click", () => {
    setActiveMenuTab("emails");
    loadEmails();
});

refreshTasksButton.addEventListener("click", loadTasks);
refreshSkillsButton.addEventListener("click", loadSkills);
refreshMemoryButton.addEventListener("click", loadMemory);
refreshEmailsButton.addEventListener("click", loadEmails);
clearButton.addEventListener("click", clearContext);

memoryList.addEventListener("click", (event) => {
    const button = event.target.closest("[data-memory-id]");
    if (!button) {
        return;
    }
    selectedMemoryId = button.dataset.memoryId || "";
    loadMemory();
});

emailsList.addEventListener("click", (event) => {
    const button = event.target.closest("[data-email-id]");
    if (!button) {
        return;
    }
    selectedEmailId = button.dataset.emailId || "";
    loadEmails();
});

chatWindow.addEventListener("toggle", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLDetailsElement) || !target.classList.contains("task-card")) {
        return;
    }
    const taskKey = target.dataset.taskKey;
    if (taskKey) {
        taskCardState.set(taskKey, target.open);
    }
}, true);

chatWindow.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-copy-message]");
    if (!button) {
        return;
    }
    const message = button.closest(".message");
    const content = message?.dataset.copyContent || "";
    if (!content) {
        return;
    }
    try {
        if (navigator.clipboard?.writeText && window.isSecureContext) {
            await navigator.clipboard.writeText(content);
        } else {
            const fallbackInput = document.createElement("textarea");
            fallbackInput.value = content;
            fallbackInput.setAttribute("readonly", "readonly");
            fallbackInput.style.position = "fixed";
            fallbackInput.style.top = "-9999px";
            fallbackInput.style.opacity = "0";
            document.body.appendChild(fallbackInput);
            fallbackInput.focus();
            fallbackInput.select();
            const copied = document.execCommand("copy");
            document.body.removeChild(fallbackInput);
            if (!copied) {
                throw new Error("copy_failed");
            }
        }
        const originalText = button.textContent;
        button.textContent = "已复制";
        window.setTimeout(() => {
            button.textContent = originalText || "复制";
        }, 1200);
    } catch (error) {
        fileHint.textContent = "复制失败，请稍后重试";
    }
});

async function boot() {
    if (mobileBrandTitle) {
        mobileBrandTitle.innerHTML = '<span class="brand-title-mobile-main">🦞 清云的</span><span class="brand-title-mobile-accent">小清虾</span>';
    }
    await Promise.all([loadHistory(), loadDocuments(), loadTasks(), loadSkills(), loadMemory(), loadEmails()]);
    syncQuickActionsVisibility();
    setActiveMenuTab("knowledge");
    window.setInterval(() => {
        if (!isStreamingReply) {
            loadHistory();
        }
    }, 2000);
    window.setInterval(loadTasks, 5000);
    window.setInterval(loadSkills, 5000);
    window.setInterval(loadMemory, 5000);
    window.setInterval(loadEmails, 5000);
}

boot();
