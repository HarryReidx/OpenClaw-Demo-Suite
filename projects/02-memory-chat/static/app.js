const SESSION_KEY = "openclaw-memory-session";
const sessionIdEl = document.getElementById("sessionId");
const chatPanel = document.getElementById("chatPanel");
const messageInput = document.getElementById("messageInput");
const sendButton = document.getElementById("sendButton");
const statusEl = document.getElementById("status");
const newSessionButton = document.getElementById("newSessionButton");

let currentMessages = [];
let pendingText = "";

function escapeHtml(text) {
    return String(text || "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;");
}

function renderBubble(item) {
    return `<div class="bubble ${item.role}">${escapeHtml(item.content)}</div>`;
}

function renderMessages(messages, pending = "") {
    currentMessages = Array.isArray(messages) ? messages : [];
    if (!currentMessages.length && !pending) {
        chatPanel.innerHTML =
            '<p class="empty">先说一句话，让模型开始构建上下文。例如：“帮助我准备 AI 机构推介。”</p>';
        return;
    }
    const bubbles = currentMessages.map(renderBubble).join("");
    const pendingBubble = pending ? `<div class="bubble assistant pending">${escapeHtml(pending)}</div>` : "";
    chatPanel.innerHTML = bubbles + pendingBubble;
    chatPanel.scrollTop = chatPanel.scrollHeight;
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
        const text = await response.text().catch(() => "");
        throw new Error(text || "请求失败");
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

        let boundaryIndex = buffer.indexOf("\n\n");
        while (boundaryIndex >= 0) {
            const rawEvent = buffer.slice(0, boundaryIndex).trim();
            buffer = buffer.slice(boundaryIndex + 2);
            if (rawEvent) {
                const { event, data } = parseSseEvent(rawEvent);
                if (event === "delta") {
                    pendingText += data.delta || "";
                    renderMessages(currentMessages, pendingText);
                } else if (event === "done") {
                    pendingText = "";
                    renderMessages(data.messages || currentMessages);
                    return;
                } else if (event === "error") {
                    throw new Error(data.detail || "流式回复失败");
                }
            }
            boundaryIndex = buffer.indexOf("\n\n");
        }

        if (done) {
            break;
        }
    }
}

async function createSession() {
    const response = await fetch("/api/session", { method: "POST" });
    const data = await response.json();
    localStorage.setItem(SESSION_KEY, data.session_id);
    sessionIdEl.textContent = data.session_id;
    renderMessages([]);
    statusEl.textContent = "新会话已建立";
}

async function ensureSession() {
    let sessionId = localStorage.getItem(SESSION_KEY);
    if (!sessionId) {
        await createSession();
        sessionId = localStorage.getItem(SESSION_KEY);
    }
    sessionIdEl.textContent = sessionId;
    const response = await fetch(`/api/history/${sessionId}`);
    const data = await response.json();
    renderMessages(data.messages || []);
}

async function sendMessage() {
    const sessionId = localStorage.getItem(SESSION_KEY);
    const message = messageInput.value.trim();
    if (!sessionId || !message) {
        statusEl.textContent = "请先输入消息";
        return;
    }

    sendButton.disabled = true;
    statusEl.textContent = "正在思考中...";
    pendingText = "";

    try {
        const response = await fetch("/api/chat-stream", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ session_id: sessionId, message }),
        });
        await consumeStreamResponse(response);
        messageInput.value = "";
        statusEl.textContent = "完成";
    } catch (error) {
        pendingText = "";
        renderMessages(currentMessages);
        statusEl.textContent = error.message;
    } finally {
        sendButton.disabled = false;
    }
}

newSessionButton.addEventListener("click", createSession);
sendButton.addEventListener("click", sendMessage);
messageInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        sendMessage();
    }
});

ensureSession();
