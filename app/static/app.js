const sessionId = crypto.randomUUID();
const form = document.getElementById("chat-form");
const apiKeyInput = document.getElementById("api-key");
const messageInput = document.getElementById("message");
const modeInput = document.getElementById("mode");
const webSearchInput = document.getElementById("web-search");
const messages = document.getElementById("messages");
const originalPanel = document.getElementById("original-panel");
const sanitizedPanel = document.getElementById("sanitized-panel");
const transparencyList = document.getElementById("transparency-list");
const artifactList = document.getElementById("artifact-list");
const riskPanel = document.getElementById("risk-panel");
const jobPanel = document.getElementById("job-panel");
const adminJobList = document.getElementById("admin-job-list");
const auditList = document.getElementById("audit-list");
const adminDetail = document.getElementById("admin-detail");
const clearButton = document.getElementById("clear-session");
const refreshJobsButton = document.getElementById("refresh-jobs");
const refreshAuditsButton = document.getElementById("refresh-audits");
const fileInput = document.getElementById("file-input");
const pathInput = document.getElementById("path-input");
const directoryInput = document.getElementById("directory-input");
const recursiveInput = document.getElementById("recursive-input");
let activeJobTimer = null;

function apiHeaders(extra = {}) {
  const headers = { ...extra };
  const apiKey = apiKeyInput.value.trim();
  if (apiKey) {
    headers["X-API-Key"] = apiKey;
  }
  return headers;
}

function addBubble(role, text, meta = "") {
  const bubble = document.createElement("div");
  bubble.className = `bubble ${role}`;
  bubble.textContent = text;
  if (meta) {
    const metaNode = document.createElement("div");
    metaNode.className = "meta";
    metaNode.textContent = meta;
    bubble.appendChild(metaNode);
  }
  messages.appendChild(bubble);
  messages.scrollTop = messages.scrollHeight;
}

function renderTransformations(items) {
  transparencyList.innerHTML = "";
  if (!items.length) {
    const item = document.createElement("li");
    item.textContent = "No sensitive entities were transformed.";
    transparencyList.appendChild(item);
    return;
  }
  for (const transformation of items) {
    const item = document.createElement("li");
    item.innerHTML =
      `<span class="entity">${transformation.entity_type}</span> ` +
      `${transformation.original} → ${transformation.replacement} ` +
      `(${transformation.strategy})`;
    transparencyList.appendChild(item);
  }
}

function renderArtifacts(items) {
  artifactList.innerHTML = "";
  if (!items || !items.length) {
    const item = document.createElement("li");
    item.textContent = "No file artifacts in this request.";
    artifactList.appendChild(item);
    return;
  }
  for (const artifact of items) {
    const item = document.createElement("li");
    const warning = artifact.warnings?.length ? ` | Warnings: ${artifact.warnings.join("; ")}` : "";
    item.textContent = `${artifact.path} | ${artifact.parser} | ${artifact.chars_extracted} chars | ${artifact.chunks} chunks${warning}`;
    artifactList.appendChild(item);
  }
}

function renderRisk(risk) {
  if (!risk) {
    riskPanel.textContent = "No residual-risk assessment yet.";
    return;
  }
  const reasons = risk.reasons?.length ? risk.reasons.join("\n- ") : "none";
  riskPanel.textContent =
    `Level: ${risk.level}\n` +
    `Blocked: ${risk.blocked ? "yes" : "no"}\n` +
    `Reasons:\n- ${reasons}\n\n` +
    `Preview:\n${risk.sanitized_preview || ""}`;
}

function renderJob(job) {
  if (!job) {
    jobPanel.textContent = "No background jobs yet.";
    return;
  }
  const eta = typeof job.eta_seconds === "number" ? `${job.eta_seconds}s` : "estimating";
  const recentItems = job.recent_items?.length ? job.recent_items.join(", ") : "none";
  jobPanel.textContent =
    `Job: ${job.job_id}\n` +
    `Status: ${job.status}\n` +
    `Step: ${job.current_step}\n` +
    `Progress: ${job.progress_percent}%\n` +
    `Items: ${job.items_processed}/${job.total_items}\n` +
    `Current Item: ${job.current_item_label || "none"}\n` +
    `Current Parser: ${job.current_item_parser || "none"}\n` +
    `ETA: ${eta}\n` +
    `Recent Items: ${recentItems}\n` +
    `Created: ${job.created_at}\n` +
    `${job.completed_at ? `Completed: ${job.completed_at}\n` : ""}` +
    `${job.error ? `Error: ${job.error}` : ""}`;
}

function renderAdminJobs(jobs) {
  adminJobList.innerHTML = "";
  if (!jobs?.length) {
    const item = document.createElement("li");
    item.textContent = "No admin-visible jobs yet.";
    adminJobList.appendChild(item);
    return;
  }
  for (const job of jobs) {
    const item = document.createElement("li");
    item.textContent = `${job.job_id} | ${job.status} | ${job.progress_percent}% | ${job.current_step}`;
    item.addEventListener("click", () => {
      adminDetail.textContent = JSON.stringify(job, null, 2);
    });
    adminJobList.appendChild(item);
  }
}

function renderAuditList(items) {
  auditList.innerHTML = "";
  if (!items?.length) {
    const item = document.createElement("li");
    item.textContent = "No audit snapshots available.";
    auditList.appendChild(item);
    return;
  }
  for (const auditId of items) {
    const item = document.createElement("li");
    item.textContent = auditId;
    item.addEventListener("click", async () => {
      const response = await fetch(`/api/audits/${auditId}`, { headers: apiHeaders() });
      const data = await response.json();
      adminDetail.textContent = response.ok
        ? JSON.stringify(data, null, 2)
        : `Unable to load audit ${auditId}: ${data.detail || "unknown error"}`;
    });
    auditList.appendChild(item);
  }
}

async function pollJob(jobId) {
  if (activeJobTimer) {
    clearInterval(activeJobTimer);
  }

  async function tick() {
    const response = await fetch(`/api/jobs/${jobId}`, { headers: apiHeaders() });
    if (!response.ok) {
      renderJob({
        job_id: jobId,
        status: "failed",
        current_step: "polling failed",
        progress_percent: 0,
        items_processed: 0,
        total_items: 0,
        created_at: "",
        error: "Unable to fetch job status",
      });
      clearInterval(activeJobTimer);
      activeJobTimer = null;
      return;
    }
    const job = await response.json();
    renderJob(job);
    if (job.status === "completed" && job.result) {
      const data = job.result;
      const meta = `Provider: ${data.provider} | Local LLM: ${data.local_llm_used ? "yes" : "no"} | Cloud LLM: ${data.cloud_llm_used ? "yes" : "no"} | Job: ${job.job_id}`;
      addBubble("assistant", data.answer, meta);
      sanitizedPanel.textContent = data.sanitized_input + "\n\nRefined Prompt:\n" + data.refined_prompt;
      renderTransformations(data.transformations);
      renderArtifacts(data.artifacts);
      renderRisk(data.residual_risk);
      clearInterval(activeJobTimer);
      activeJobTimer = null;
    } else if (job.status === "failed") {
      addBubble("assistant", `Background job failed: ${job.error || "unknown error"}`);
      clearInterval(activeJobTimer);
      activeJobTimer = null;
    }
  }

  await tick();
  activeJobTimer = setInterval(tick, 1500);
}

async function refreshAdminJobs() {
  const response = await fetch("/api/admin/jobs", { headers: apiHeaders() });
  const data = await response.json();
  if (!response.ok) {
    adminDetail.textContent = `Unable to load jobs: ${data.detail || "unknown error"}`;
    return;
  }
  renderAdminJobs(data.jobs);
}

async function refreshAudits() {
  const response = await fetch("/api/audits", { headers: apiHeaders() });
  const data = await response.json();
  if (!response.ok) {
    adminDetail.textContent = `Unable to load audits: ${data.detail || "unknown error"}`;
    return;
  }
  renderAuditList(data.audit_ids);
}

async function sendMessage(event) {
  event.preventDefault();
  const message = messageInput.value.trim();
  if (!message) {
    return;
  }

  addBubble("user", message, `Mode: ${modeInput.value}`);
  originalPanel.textContent = message;
  messageInput.value = "";

  let response;
  const selectedFile = fileInput.files[0];
  const localPath = pathInput.value.trim();
  const localDirectory = directoryInput.value.trim();

  if (selectedFile) {
    const formData = new FormData();
    formData.append("session_id", sessionId);
    formData.append("message", message);
    formData.append("mode", modeInput.value);
    formData.append("use_web_search", webSearchInput.checked ? "true" : "false");
    formData.append("file", selectedFile);
    response = await fetch("/api/chat/file", {
      method: "POST",
      body: formData,
      headers: apiHeaders(),
    });
  } else if (localPath) {
    response = await fetch("/api/chat/path", {
      method: "POST",
      headers: apiHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({
        session_id: sessionId,
        path: localPath,
        message,
        mode: modeInput.value,
        use_web_search: webSearchInput.checked,
      }),
    });
  } else if (localDirectory) {
    response = await fetch("/api/jobs/directory", {
      method: "POST",
      headers: apiHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({
        session_id: sessionId,
        path: localDirectory,
        message,
        mode: modeInput.value,
        use_web_search: webSearchInput.checked,
        recursive: recursiveInput.checked,
      }),
    });
  } else {
    response = await fetch("/api/chat", {
      method: "POST",
      headers: apiHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({
        session_id: sessionId,
        message,
        mode: modeInput.value,
        use_web_search: webSearchInput.checked,
      }),
    });
  }

  const data = await response.json();
  if (!response.ok) {
    addBubble("assistant", `Request failed: ${data.detail || "unknown error"}`);
    return;
  }

  if (localDirectory) {
    renderJob({
      job_id: data.job_id,
      status: data.status,
      current_step: "queued",
      progress_percent: 0,
      items_processed: 0,
      total_items: 0,
      created_at: new Date().toISOString(),
    });
    addBubble("assistant", `Queued background job ${data.job_id}. I’ll keep tracking progress locally.`);
    await pollJob(data.job_id);
    return;
  }

  const meta = `Provider: ${data.provider} | Local LLM: ${data.local_llm_used ? "yes" : "no"} | Cloud LLM: ${data.cloud_llm_used ? "yes" : "no"}`;
  addBubble("assistant", data.answer, meta);
  sanitizedPanel.textContent = data.sanitized_input + "\n\nRefined Prompt:\n" + data.refined_prompt;
  renderTransformations(data.transformations);
  renderArtifacts(data.artifacts);
  renderRisk(data.residual_risk);
  fileInput.value = "";
}

async function clearSession() {
  await fetch(`/api/session/${sessionId}`, { method: "DELETE", headers: apiHeaders() });
  messages.innerHTML = "";
  originalPanel.textContent = "No message yet.";
  sanitizedPanel.textContent = "No sanitized prompt yet.";
  transparencyList.innerHTML = "";
  artifactList.innerHTML = "";
  riskPanel.textContent = "No residual-risk assessment yet.";
  jobPanel.textContent = "No background jobs yet.";
  adminJobList.innerHTML = "";
  auditList.innerHTML = "";
  adminDetail.textContent = "No admin item selected.";
  if (activeJobTimer) {
    clearInterval(activeJobTimer);
    activeJobTimer = null;
  }
}

form.addEventListener("submit", sendMessage);
clearButton.addEventListener("click", clearSession);
refreshJobsButton.addEventListener("click", refreshAdminJobs);
refreshAuditsButton.addEventListener("click", refreshAudits);
