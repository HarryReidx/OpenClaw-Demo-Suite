const queryInput = document.getElementById("queryInput");
const generateButton = document.getElementById("generateButton");
const statusEl = document.getElementById("status");
const summaryBlock = document.getElementById("summaryBlock");
const summaryOutput = document.getElementById("summaryOutput");
const skillTags = document.getElementById("skillTags");
const activityList = document.getElementById("activityList");
const pathMeta = document.getElementById("pathMeta");
const openReportLink = document.getElementById("openReportLink");
const previewPanel = document.getElementById("previewPanel");
const previewFrame = document.getElementById("previewFrame");
const reportList = document.getElementById("reportList");

function renderReports(reports) {
    if (!reports.length) {
        reportList.innerHTML = '<p class="empty">还没有生成过网页报告。</p>';
        return;
    }
    reportList.innerHTML = reports
        .map(
            (report) => `
                <article class="report-item">
                    <a href="${report.url}" target="_blank" rel="noreferrer">${report.name}</a>
                    <span>${report.updated_at}</span>
                </article>
            `
        )
        .join("");
}

function renderSkillTags(skills) {
    if (!skillTags) {
        return;
    }
    if (!skills.length) {
        skillTags.innerHTML = "";
        return;
    }
    skillTags.innerHTML = skills.map((skill) => `<span class="skill-tag">${skill}</span>`).join("");
}

function renderActivities(activities) {
    if (!activityList) {
        return;
    }
    if (!activities.length) {
        activityList.innerHTML = "";
        return;
    }
    activityList.innerHTML = activities
        .map(
            (item) => `
                <div class="activity-item">
                    <div>
                        <strong>${item.label}</strong>
                        <div class="activity-detail">${item.detail}</div>
                    </div>
                    <span class="activity-status ${item.status || "pending"}">${item.status || "pending"}</span>
                </div>
            `
        )
        .join("");
}

async function generateReport() {
    const query = queryInput.value.trim();
    if (!query) {
        statusEl.textContent = "请先输入搜索主题";
        return;
    }

    generateButton.disabled = true;
    statusEl.textContent = "正在联网搜索并生成网页报告...";

    try {
        const response = await fetch("/api/generate", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ query }),
        });
        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.detail || "请求失败");
        }

        summaryOutput.textContent = data.summary || "";
        renderSkillTags(data.skills || []);
        renderActivities(data.activities || []);
        pathMeta.textContent = `已保存：${data.saved_path}`;
        openReportLink.href = data.report_url;
        openReportLink.textContent = `打开 ${data.report_url}`;
        previewFrame.src = data.report_url;
        summaryBlock.classList.remove("hidden");
        previewPanel.classList.remove("hidden");
        renderReports(data.reports || []);
        statusEl.textContent = "完成";
    } catch (error) {
        statusEl.textContent = error.message;
    } finally {
        generateButton.disabled = false;
    }
}

generateButton.addEventListener("click", generateReport);
queryInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        generateReport();
    }
});
