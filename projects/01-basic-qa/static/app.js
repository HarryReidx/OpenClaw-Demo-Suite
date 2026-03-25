const promptInput = document.getElementById("prompt");
const answerEl = document.getElementById("answer");
const statusEl = document.getElementById("status");
const askButton = document.getElementById("askButton");

async function askModel() {
    const prompt = promptInput.value.trim();
    if (!prompt) {
        statusEl.textContent = "请输入问题";
        return;
    }

    askButton.disabled = true;
    statusEl.textContent = "大模型思考中...";
    answerEl.textContent = "正在生成回答...";

    try {
        const response = await fetch("/api/ask", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ prompt }),
        });
        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.detail || "请求失败");
        }
        answerEl.textContent = data.answer || "模型未返回内容。";
        statusEl.textContent = "完成";
    } catch (error) {
        answerEl.textContent = error.message;
        statusEl.textContent = "调用失败";
    } finally {
        askButton.disabled = false;
    }
}

askButton.addEventListener("click", askModel);
promptInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        askModel();
    }
});
