const newsGrid = document.getElementById("newsGrid");
const refreshButton = document.getElementById("refreshButton");
const scheduleButton = document.getElementById("scheduleButton");
const lastUpdated = document.getElementById("lastUpdated");
const digestOutput = document.getElementById("digestOutput");
const pushStatus = document.getElementById("pushStatus");
const scheduleStatus = document.getElementById("scheduleStatus");

let scheduleEnabled = false;

function escapeHtml(text) {
    return String(text || "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
}

function renderInlineMarkdown(text) {
    let html = escapeHtml(text);
    html = html.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noreferrer">$1</a>');
    html = html.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    return html;
}

function renderMarkdown(text) {
    const lines = String(text || "").replace(/\r\n/g, "\n").split("\n");
    const blocks = [];
    let index = 0;

    while (index < lines.length) {
        const trimmed = lines[index].trim();
        if (!trimmed) {
            index += 1;
            continue;
        }
        if (/^#{1,6}\s/.test(trimmed)) {
            const level = trimmed.match(/^#+/)[0].length;
            blocks.push(`<h${level}>${renderInlineMarkdown(trimmed.replace(/^#{1,6}\s+/, ""))}</h${level}>`);
            index += 1;
            continue;
        }
        if (/^>\s?/.test(trimmed)) {
            const quotes = [];
            while (index < lines.length && /^>\s?/.test(lines[index].trim())) {
                quotes.push(lines[index].trim().replace(/^>\s?/, ""));
                index += 1;
            }
            blocks.push(`<blockquote>${quotes.map(renderInlineMarkdown).join("<br />")}</blockquote>`);
            continue;
        }
        if (/^(-{3,}|\*{3,})$/.test(trimmed)) {
            blocks.push("<hr />");
            index += 1;
            continue;
        }
        if (/^-\s+/.test(trimmed)) {
            const items = [];
            while (index < lines.length && /^-\s+/.test(lines[index].trim())) {
                items.push(lines[index].trim().replace(/^-\s+/, ""));
                index += 1;
            }
            blocks.push(`<ul>${items.map((item) => `<li>${renderInlineMarkdown(item)}</li>`).join("")}</ul>`);
            continue;
        }

        const paragraph = [];
        while (index < lines.length && lines[index].trim()) {
            paragraph.push(lines[index].trim());
            index += 1;
        }
        blocks.push(`<p>${renderInlineMarkdown(paragraph.join("<br />"))}</p>`);
    }

    return blocks.join("");
}

function renderNews(items) {
    if (!items.length) {
        newsGrid.innerHTML = '<p class="hint">暂无资讯，点击上方按钮获取。</p>';
        return;
    }
    newsGrid.innerHTML = items.map((item) => `
        <article class="news-card">
            <div class="news-meta">
                <span>${escapeHtml(item.source)}</span>
                <span>${escapeHtml(item.published_at)}</span>
            </div>
            <h3>${escapeHtml(item.title)}</h3>
            <p>${escapeHtml(item.summary)}</p>
            <a href="${escapeHtml(item.url)}" target="_blank" rel="noreferrer">查看原文</a>
        </article>
    `).join("");
}

function updateScheduleButton() {
    scheduleButton.textContent = scheduleEnabled ? "关闭定时刷新" : "开启定时刷新";
    scheduleStatus.textContent = `定时刷新：${scheduleEnabled ? "已开启" : "未开启"}`;
}

function renderState(data) {
    renderNews(data.items || []);
    digestOutput.innerHTML = renderMarkdown(data.digest_markdown || data.digest || "暂无摘要");
    pushStatus.textContent = data.push_status || "尚未操作";
    scheduleEnabled = Boolean(data.schedule_enabled);
    updateScheduleButton();
}

async function loadState() {
    const response = await fetch("/api/state");
    const data = await response.json();
    renderState(data);
}

refreshButton.addEventListener("click", async () => {
    refreshButton.disabled = true;
    refreshButton.textContent = "处理中...";
    try {
        const response = await fetch("/api/refresh", { method: "POST" });
        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.detail || "执行失败");
        }
        renderState(data);
        lastUpdated.textContent = `最近执行：${new Date().toLocaleString("zh-CN")}`;
    } catch (error) {
        pushStatus.textContent = error.message;
    } finally {
        refreshButton.disabled = false;
        refreshButton.textContent = "立即获取并推送";
    }
});

scheduleButton.addEventListener("click", async () => {
    scheduleButton.disabled = true;
    try {
        const response = await fetch("/api/schedule", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ enabled: !scheduleEnabled }),
        });
        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.detail || "切换失败");
        }
        scheduleEnabled = Boolean(data.enabled);
        updateScheduleButton();
        pushStatus.textContent = data.status || "状态已更新";
    } catch (error) {
        pushStatus.textContent = error.message;
    } finally {
        scheduleButton.disabled = false;
    }
});

loadState();
