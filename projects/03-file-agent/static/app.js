const taskInput = document.getElementById("taskInput");
const runButton = document.getElementById("runButton");
const statusEl = document.getElementById("status");
const resultCard = document.getElementById("resultCard");
const resultMeta = document.getElementById("resultMeta");
const skillTags = document.getElementById("skillTags");
const activityList = document.getElementById("activityList");
const answerOutput = document.getElementById("answerOutput");
const previewOutput = document.getElementById("previewOutput");
const fileList = document.getElementById("fileList");
const refreshFilesButton = document.getElementById("refreshFilesButton");

function renderFiles(files) {
    if (!files.length) {
        fileList.innerHTML = '<p class="empty">还没有生成文件。先让 Agent 完成一个任务吧。</p>';
        return;
    }

    fileList.innerHTML = files
        .map(
            (file) => `
                <article class="file-item">
                    <strong>${file.name}</strong>
                    <span>${file.path}</span>
                    <p>${file.preview || ""}</p>
                </article>
            `
        )
        .join("");
}

async function refreshFiles() {
    const response = await fetch("/api/files");
    const data = await response.json();
    renderFiles(data.files || []);
}

function renderSkillTags(skills) {
    if (!skillTags) {
        return;
    }
    if (!skills.length) {
        skillTags.innerHTML = "";
        return;
    }
    skillTags.innerHTML = skills
        .map((skill) => `<span class="skill-tag">${skill}</span>`)
        .join("");
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

async function runAgent() {
    const task = taskInput.value.trim();
    if (!task) {
        statusEl.textContent = "请先输入任务";
        return;
    }

    runButton.disabled = true;
    statusEl.textContent = "Agent 正在规划并尝试写文件...";
    resultCard.classList.add("hidden");

    try {
        const response = await fetch("/api/run", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ task }),
        });
        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.detail || "请求失败");
        }

        resultMeta.textContent = `${data.used_tool ? "已调用工具" : "未调用工具"} | 文件路径: ${data.saved_path}`;
        answerOutput.textContent = data.answer || "";
        previewOutput.textContent = data.preview || "";
        resultCard.classList.remove("hidden");
        renderFiles(data.files || []);
        renderSkillTags(data.skills || []);
        renderActivities(data.activities || []);
        statusEl.textContent = "完成";
    } catch (error) {
        statusEl.textContent = error.message;
    } finally {
        runButton.disabled = false;
    }
}

runButton.addEventListener("click", runAgent);
refreshFilesButton.addEventListener("click", refreshFiles);

refreshFiles();
