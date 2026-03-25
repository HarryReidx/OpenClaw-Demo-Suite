const uploadForm = document.getElementById("uploadForm");
const fileInput = document.getElementById("fileInput");
const uploadStatus = document.getElementById("uploadStatus");
const docList = document.getElementById("docList");
const questionInput = document.getElementById("questionInput");
const askButton = document.getElementById("askButton");
const askStatus = document.getElementById("askStatus");
const answerOutput = document.getElementById("answerOutput");
const citationList = document.getElementById("citationList");
const previewModal = document.getElementById("previewModal");
const previewBackdrop = document.getElementById("previewBackdrop");
const closePreviewButton = document.getElementById("closePreviewButton");
const chunkModeButton = document.getElementById("chunkModeButton");
const mergedModeButton = document.getElementById("mergedModeButton");
const previewMeta = document.getElementById("previewMeta");
const docPreview = document.getElementById("docPreview");

let documentsState = [];
let selectedDocId = null;
let previewMode = "chunk";
let currentDocument = null;

function renderDocuments(documents) {
    documentsState = documents;
    docList.innerHTML = "";

    if (!documents.length) {
        const empty = document.createElement("p");
        empty.className = "meta";
        empty.textContent = "No documents uploaded yet.";
        docList.appendChild(empty);
        if (!previewModal.hidden) {
            closePreview();
        }
        return;
    }

    documents.forEach((doc) => {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "doc-item";
        button.dataset.docId = doc.doc_id;

        if (doc.doc_id === selectedDocId) {
            button.classList.add("active");
        }

        const title = document.createElement("strong");
        title.textContent = doc.file_name;

        const meta = document.createElement("span");
        meta.textContent = `${doc.chunk_count} chunks`;

        button.append(title, meta);
        button.addEventListener("click", () => loadDocumentPreview(doc.doc_id));
        docList.appendChild(button);
    });
}

function renderCitations(citations) {
    citationList.innerHTML = "";

    if (!citations.length) {
        const empty = document.createElement("p");
        empty.className = "meta";
        empty.textContent = "Retrieved chunks will appear here.";
        citationList.appendChild(empty);
        return;
    }

    citations.forEach((item) => {
        const article = document.createElement("article");
        article.className = "citation-item";

        const title = document.createElement("strong");
        title.textContent = item.file_name;

        const content = document.createElement("p");
        content.textContent = item.content;

        article.append(title, content);
        citationList.appendChild(article);
    });
}

function openPreview() {
    previewModal.hidden = false;
    previewModal.setAttribute("aria-hidden", "false");
    document.body.classList.add("modal-open");
}

function closePreview() {
    previewModal.hidden = true;
    previewModal.setAttribute("aria-hidden", "true");
    document.body.classList.remove("modal-open");
    selectedDocId = null;
    currentDocument = null;
    previewMeta.textContent = "Click a document to load its details.";
    docPreview.textContent = "Preview content will appear here.";
    renderDocuments(documentsState);
}

function setPreviewMode(mode) {
    previewMode = mode;
    chunkModeButton.classList.toggle("active", mode === "chunk");
    mergedModeButton.classList.toggle("active", mode === "merged");
    chunkModeButton.setAttribute("aria-pressed", String(mode === "chunk"));
    mergedModeButton.setAttribute("aria-pressed", String(mode === "merged"));
    renderPreviewContent();
}

function renderPreviewContent() {
    if (!currentDocument) {
        docPreview.textContent = "Preview content will appear here.";
        return;
    }

    if (previewMode === "merged") {
        docPreview.innerHTML = "";
        const content = document.createElement("pre");
        content.className = "merged-preview";
        content.textContent = currentDocument.content || "This document has no previewable content.";
        docPreview.appendChild(content);
        return;
    }

    const chunks = currentDocument.chunks || [];
    docPreview.innerHTML = "";

    if (!chunks.length) {
        const empty = document.createElement("p");
        empty.className = "meta";
        empty.textContent = "This document has no chunks.";
        docPreview.appendChild(empty);
        return;
    }

    chunks.forEach((chunk) => {
        const card = document.createElement("article");
        card.className = "chunk-card";

        const header = document.createElement("div");
        header.className = "chunk-card-head";

        const title = document.createElement("strong");
        title.textContent = `Chunk ${chunk.index}`;

        const tag = document.createElement("span");
        tag.className = "chunk-tag";
        tag.textContent = chunk.chunk_id || "chunk";

        header.append(title, tag);

        const body = document.createElement("pre");
        body.className = "chunk-card-body";
        body.textContent = chunk.content || "";

        card.append(header, body);
        docPreview.appendChild(card);
    });
}

async function loadDocuments() {
    const response = await fetch("/api/documents");
    const data = await response.json();
    renderDocuments(data.documents || []);
}

async function loadDocumentPreview(docId) {
    selectedDocId = docId;
    renderDocuments(documentsState);
    openPreview();
    setPreviewMode("chunk");
    previewMeta.textContent = "Loading preview...";
    docPreview.textContent = "";

    try {
        const response = await fetch(`/api/documents/${docId}`);
        const data = await response.json();

        if (!response.ok) {
            currentDocument = null;
            previewMeta.textContent = data.detail || "Failed to load preview.";
            docPreview.textContent = "";
            return;
        }

        const documentInfo = data.document || {};
        currentDocument = documentInfo;
        previewMeta.textContent = `${documentInfo.file_name || "Untitled"} - ${documentInfo.chunk_count || 0} chunks`;
        renderPreviewContent();
        renderDocuments(documentsState);
    } catch (error) {
        currentDocument = null;
        previewMeta.textContent = "Failed to load preview.";
        docPreview.textContent = String(error);
    }
}

uploadForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const file = fileInput.files?.[0];

    if (!file) {
        uploadStatus.textContent = "Please choose a file first.";
        return;
    }

    uploadStatus.textContent = "Parsing and indexing file...";
    const formData = new FormData();
    formData.append("file", file);

    const response = await fetch("/api/upload", { method: "POST", body: formData });
    const data = await response.json();

    if (!response.ok) {
        uploadStatus.textContent = data.detail || "Upload failed.";
        return;
    }

    uploadStatus.textContent = `Indexed: ${data.document.file_name}`;
    renderDocuments(data.documents || []);
    fileInput.value = "";
});

async function askQuestion() {
    const question = questionInput.value.trim();

    if (!question) {
        askStatus.textContent = "Please enter a question.";
        return;
    }

    askButton.disabled = true;
    askStatus.textContent = "Searching knowledge base and generating answer...";

    const formData = new FormData();
    formData.append("question", question);

    const response = await fetch("/api/ask", { method: "POST", body: formData });
    const data = await response.json();

    if (!response.ok) {
        askStatus.textContent = data.detail || "Question failed.";
        askButton.disabled = false;
        return;
    }

    answerOutput.textContent = data.answer || "";
    renderCitations(data.citations || []);
    askStatus.textContent = "Done";
    askButton.disabled = false;
}

closePreviewButton.addEventListener("click", closePreview);
previewBackdrop.addEventListener("click", closePreview);
chunkModeButton.addEventListener("click", () => setPreviewMode("chunk"));
mergedModeButton.addEventListener("click", () => setPreviewMode("merged"));
askButton.addEventListener("click", askQuestion);

document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !previewModal.hidden) {
        closePreview();
        return;
    }

    if (event.key === "Enter" && event.target === questionInput && !event.shiftKey) {
        event.preventDefault();
        askQuestion();
    }
});

loadDocuments();
renderCitations([]);
