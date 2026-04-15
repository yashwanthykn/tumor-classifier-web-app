/* ============================================================
   chat.js — Clinical Assistant Chat Logic
   ClassifierBT.com
   
   Conversation persistence via backend API.
   ============================================================ */

let conversationId = null; // Current conversation UUID from server
let isProcessing = false;
let sidebarOpen = false; // Mobile sidebar state

const API_BASE = "/api/chat";

// ── Helpers ──────────────────────────────────────────────

function getToken() {
  return localStorage.getItem("token");
}

function authHeaders() {
  return {
    Authorization: `Bearer ${getToken()}`,
    "Content-Type": "application/json",
  };
}

function escapeHtml(text) {
  const d = document.createElement("div");
  d.textContent = text;
  return d.innerHTML;
}

function scrollToBottom() {
  const canvas = document.getElementById("chatCanvas");
  if (canvas) canvas.scrollTop = canvas.scrollHeight;
}

/**
 * Sanitize a URL for use in href attributes.
 * Blocks javascript:, data:, and vbscript: URIs to prevent XSS.
 * Only allows http:, https:, and mailto: schemes.
 */
function sanitizeUrl(url) {
  if (!url) return "#";
  const trimmed = url.trim().toLowerCase();
  if (
    trimmed.startsWith("javascript:") ||
    trimmed.startsWith("data:") ||
    trimmed.startsWith("vbscript:")
  ) {
    return "#";
  }
  if (
    trimmed.startsWith("http://") ||
    trimmed.startsWith("https://") ||
    trimmed.startsWith("mailto:") ||
    trimmed.startsWith("/") ||
    trimmed.startsWith("#")
  ) {
    return url;
  }
  return "https://" + url;
}

/**
 * Minimal markdown → HTML renderer.
 */
function renderMarkdown(text) {
  if (!text) return "";

  let html = text;

  // Code blocks
  html = html.replace(/```(\w*)\n?([\s\S]*?)```/g, (_, lang, code) => {
    return `<pre><code>${escapeHtml(code.trim())}</code></pre>`;
  });

  const lines = html.split("\n");
  const output = [];
  let inList = false;
  let listType = null;

  for (let i = 0; i < lines.length; i++) {
    let line = lines[i];

    if (line.includes("<pre><code>") || line.includes("</code></pre>")) {
      output.push(line);
      continue;
    }

    // Horizontal rule
    if (/^(-{3,}|\*{3,}|_{3,})$/.test(line.trim())) {
      if (inList) {
        output.push(`</${listType}>`);
        inList = false;
      }
      output.push("<hr>");
      continue;
    }

    // Headings
    const headingMatch = line.match(/^(#{1,3})\s+(.+)$/);
    if (headingMatch) {
      if (inList) {
        output.push(`</${listType}>`);
        inList = false;
      }
      const level = headingMatch[1].length;
      output.push(`<h${level}>${applyInline(headingMatch[2])}</h${level}>`);
      continue;
    }

    // Blockquote
    if (line.startsWith("> ")) {
      if (inList) {
        output.push(`</${listType}>`);
        inList = false;
      }
      output.push(`<blockquote>${applyInline(line.substring(2))}</blockquote>`);
      continue;
    }

    // Unordered list
    const ulMatch = line.match(/^[\s]*[-*]\s+(.+)$/);
    if (ulMatch) {
      if (!inList || listType !== "ul") {
        if (inList) output.push(`</${listType}>`);
        output.push("<ul>");
        inList = true;
        listType = "ul";
      }
      output.push(`<li>${applyInline(ulMatch[1])}</li>`);
      continue;
    }

    // Ordered list
    const olMatch = line.match(/^[\s]*\d+\.\s+(.+)$/);
    if (olMatch) {
      if (!inList || listType !== "ol") {
        if (inList) output.push(`</${listType}>`);
        output.push("<ol>");
        inList = true;
        listType = "ol";
      }
      output.push(`<li>${applyInline(olMatch[1])}</li>`);
      continue;
    }

    if (inList && line.trim() !== "") {
      output.push(`</${listType}>`);
      inList = false;
    }

    if (line.trim() === "") {
      output.push("");
      continue;
    }

    output.push(`<p>${applyInline(line)}</p>`);
  }

  if (inList) output.push(`</${listType}>`);
  return output.join("\n");
}

/** Apply inline markdown: bold, italic, inline code, links */
function applyInline(text) {
  text = text.replace(/`([^`]+)`/g, "<code>$1</code>");
  text = text.replace(/\*\*\*(.+?)\*\*\*/g, "<strong><em>$1</em></strong>");
  text = text.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  text = text.replace(/\*(.+?)\*/g, "<em>$1</em>");
  text = text.replace(
    /\[([^\]]+)\]\(([^)]+)\)/g,
    (_, linkText, url) =>
      `<a href="${sanitizeUrl(url)}" target="_blank" rel="noopener noreferrer">${linkText}</a>`,
  );
  return text;
}

// ── Global: called from suggestion buttons ────────────────

function sendSuggestedQuestion(question) {
  const input = document.getElementById("chatInput");
  if (input) {
    input.value = question;
    handleSendMessage();
  }
}

// ── Auth + Init ─────────────────────────────────────────

window.addEventListener("DOMContentLoaded", async () => {
  const token = getToken();
  if (!token) {
    window.location.href = "/index.html";
    return;
  }

  try {
    const res = await fetch("/api/auth/me", {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) throw new Error("Invalid token");

    const user = await res.json();
    const el = document.getElementById("userName");
    if (el) el.textContent = user.username || user.email;

    initChat();
    loadConversationList();
  } catch {
    localStorage.removeItem("token");
    window.location.href = "/index.html";
  }
});

// ── Init Chat ───────────────────────────────────────────

function initChat() {
  const input = document.getElementById("chatInput");
  const sendBtn = document.getElementById("sendBtn");

  if (!input || !sendBtn) return;

  sendBtn.addEventListener("click", handleSendMessage);

  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  });

  input.addEventListener("input", () => {
    input.style.height = "auto";
    input.style.height = input.scrollHeight + "px";
  });

  document
    .getElementById("newChatBtn")
    ?.addEventListener("click", startNewConversation);
  document
    .getElementById("sidebarNewChat")
    ?.addEventListener("click", startNewConversation);

  document
    .getElementById("sidebarToggle")
    ?.addEventListener("click", toggleSidebar);
  document
    .getElementById("sidebarOverlay")
    ?.addEventListener("click", closeSidebar);

  ["logoutBtn", "logoutBtnMobile"].forEach((id) => {
    const btn = document.getElementById(id);
    if (btn) btn.addEventListener("click", logout);
  });

  document.addEventListener("click", (e) => {
    const menu = document.getElementById("userMenu");
    if (menu && !menu.contains(e.target)) menu.classList.remove("show");
  });
}

// ══════════════════════════════════════════════════════════
//  SIDEBAR — Conversation List
// ══════════════════════════════════════════════════════════

function toggleSidebar() {
  const sidebar = document.getElementById("sidebar");
  const overlay = document.getElementById("sidebarOverlay");

  if (window.innerWidth <= 768) {
    sidebarOpen = !sidebarOpen;
    sidebar.classList.toggle("open", sidebarOpen);
    overlay.classList.toggle("active", sidebarOpen);
  } else {
    sidebar.classList.toggle("collapsed");
  }
}

function closeSidebar() {
  const sidebar = document.getElementById("sidebar");
  const overlay = document.getElementById("sidebarOverlay");
  sidebarOpen = false;
  sidebar.classList.remove("open");
  overlay.classList.remove("active");
}

async function loadConversationList() {
  const list = document.getElementById("conversationList");
  if (!list) return;

  list.innerHTML = buildSidebarSkeleton();

  try {
    const res = await fetch(`${API_BASE}/conversations?limit=50`, {
      headers: authHeaders(),
    });

    if (!res.ok) throw new Error(`Failed to load conversations: ${res.status}`);

    const data = await res.json();
    list.innerHTML = "";

    if (data.conversations.length === 0) {
      list.innerHTML = `
        <div class="sidebar__empty">
          <span class="material-symbols-outlined sidebar__empty-icon">forum</span>
          <p>No conversations yet</p>
        </div>`;
      return;
    }

    data.conversations.forEach((conv) => {
      list.appendChild(buildConversationItem(conv));
    });
  } catch (err) {
    console.error("Failed to load conversations:", err);
    list.innerHTML = `
      <div class="sidebar__empty">
        <span class="material-symbols-outlined sidebar__empty-icon">error</span>
        <p>Failed to load conversations</p>
      </div>`;
  }
}

function buildSidebarSkeleton() {
  let html = "";
  for (let i = 0; i < 5; i++) {
    html += `
      <div class="conv-skeleton">
        <div class="conv-skeleton__icon"></div>
        <div style="flex:1; display:flex; flex-direction:column; gap:0.35rem;">
          <div class="conv-skeleton__line"></div>
          <div class="conv-skeleton__line conv-skeleton__line--short"></div>
        </div>
      </div>`;
  }
  return html;
}

function buildConversationItem(conv) {
  const btn = document.createElement("button");
  btn.className =
    "conv-item" + (conv.id === conversationId ? " conv-item--active" : "");
  btn.dataset.convId = conv.id;

  const timeAgo = formatTimeAgo(new Date(conv.updated_at));

  btn.innerHTML = `
    <span class="material-symbols-outlined conv-item__icon">chat_bubble_outline</span>
    <div class="conv-item__text">
      <div class="conv-item__title">${escapeHtml(conv.title || "New conversation")}</div>
      <div class="conv-item__meta">${timeAgo} · ${conv.message_count} msg</div>
    </div>
    <span class="conv-item__delete" title="Delete conversation">
      <span class="material-symbols-outlined">delete</span>
    </span>
  `;

  btn.addEventListener("click", (e) => {
    if (e.target.closest(".conv-item__delete")) return;
    loadConversation(conv.id);
    closeSidebar();
  });

  btn.querySelector(".conv-item__delete").addEventListener("click", (e) => {
    e.stopPropagation();
    deleteConversation(conv.id);
  });

  return btn;
}

function formatTimeAgo(date) {
  const now = new Date();
  const diffMs = now - date;
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMs / 3600000);
  const diffDays = Math.floor(diffMs / 86400000);

  if (diffMins < 1) return "Just now";
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays < 7) return `${diffDays}d ago`;
  return date.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

function setActiveConversation(id) {
  document.querySelectorAll(".conv-item").forEach((el) => {
    el.classList.toggle("conv-item--active", el.dataset.convId === id);
  });
}

// ══════════════════════════════════════════════════════════
//  CONVERSATION ACTIONS
// ══════════════════════════════════════════════════════════

async function loadConversation(convId) {
  const container = document.getElementById("chatMessages");
  const emptyState = document.getElementById("emptyState");
  if (!container) return;

  conversationId = convId;
  setActiveConversation(convId);

  clearMessagesDOM();
  if (emptyState) emptyState.style.display = "none";
  showMessageSkeleton(container);

  try {
    const res = await fetch(`${API_BASE}/conversations/${convId}`, {
      headers: authHeaders(),
    });

    if (res.status === 401) {
      logout();
      return;
    }
    if (!res.ok) throw new Error(`Failed to load conversation: ${res.status}`);

    const data = await res.json();
    clearMessagesDOM();

    const displayMessages = data.messages.filter(
      (m) =>
        (m.role === "user" || m.role === "assistant") &&
        m.content &&
        m.content.trim() !== "" &&
        m.tool_name !== "__tool_request__",
    );

    if (displayMessages.length === 0) {
      if (emptyState) emptyState.style.display = "flex";
      return;
    }

    displayMessages.forEach((msg) => {
      const role = msg.role === "user" ? "user" : "ai";
      const time = new Date(msg.created_at);
      appendMessage(role, msg.content, time);
    });

    scrollToBottom();
  } catch (err) {
    console.error("Failed to load conversation:", err);
    clearMessagesDOM();
    appendMessage("ai", "Failed to load conversation. Please try again.");
  }
}

async function deleteConversation(convId) {
  if (!confirm("Delete this conversation? This cannot be undone.")) return;

  try {
    const res = await fetch(`${API_BASE}/conversations/${convId}`, {
      method: "DELETE",
      headers: authHeaders(),
    });

    if (!res.ok) throw new Error("Failed to delete");

    if (convId === conversationId) {
      startNewConversation();
    }

    loadConversationList();
  } catch (err) {
    console.error("Failed to delete conversation:", err);
    alert("Failed to delete conversation. Please try again.");
  }
}

function startNewConversation() {
  conversationId = null;
  setActiveConversation(null);
  clearMessagesDOM();

  const emptyState = document.getElementById("emptyState");
  if (emptyState) emptyState.style.display = "flex";

  closeSidebar();
}

// ══════════════════════════════════════════════════════════
//  SEND MESSAGE
// ══════════════════════════════════════════════════════════

async function handleSendMessage() {
  const input = document.getElementById("chatInput");
  if (!input) return;
  const message = input.value.trim();
  if (!message || isProcessing) return;

  input.value = "";
  input.style.height = "auto";

  // Remove any existing follow-up chips when sending a new message
  removeFollowUpChips();

  await sendMessage(message);
}

async function sendMessage(message) {
  if (isProcessing) return;
  isProcessing = true;

  const emptyState = document.getElementById("emptyState");
  if (emptyState) emptyState.style.display = "none";

  appendMessage("user", message);

  const typing = document.getElementById("typingIndicator");
  if (typing) typing.classList.add("active");
  scrollToBottom();

  try {
    const token = getToken();
    const body = { message };

    if (conversationId) {
      body.conversation_id = conversationId;
    }

    const res = await fetch(`${API_BASE}/message`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
    });

    if (res.status === 401) {
      alert("Session expired. Please login again.");
      logout();
      return;
    }
    if (res.status === 429) {
      if (typing) typing.classList.remove("active");
      appendErrorMessage({
        type: "rate_limit",
        icon: "schedule",
        title: "Too many requests",
        message: "You're sending messages too quickly. Please wait a moment.",
        hint: "This limit resets automatically.",
      });
      isProcessing = false;
      return;
    }
    if (!res.ok) throw new Error(`Server error: ${res.status}`);

    if (typing) typing.classList.remove("active");
    await handleStreamingResponse(res);

    loadConversationList();
  } catch (err) {
    if (typing) typing.classList.remove("active");
    console.error(err);

    if (err.message && err.message.includes("Failed to fetch")) {
      appendErrorMessage({
        type: "network",
        icon: "wifi_off",
        title: "Connection lost",
        message:
          "Unable to reach the server. Please check your internet connection.",
        hint: "Make sure the backend is running and try again.",
      });
    } else {
      appendErrorMessage({
        type: "unknown",
        icon: "error_outline",
        title: "Something went wrong",
        message: "An unexpected error occurred while sending your message.",
        hint: "Please try again. If this keeps happening, try refreshing the page.",
      });
    }
  } finally {
    isProcessing = false;
  }
}

// ── Streaming Response Handler ──────────────────────────

function parseErrorMessage(text) {
  if (text.startsWith("__ERROR_RATE_LIMIT__")) {
    const waitTime = text.replace("__ERROR_RATE_LIMIT__", "");
    return {
      type: "rate_limit",
      icon: "schedule",
      title: "Daily limit reached",
      message: `The AI service has reached its daily usage limit. Please try again in ${waitTime || "a few minutes"}.`,
      hint: "This resets automatically — your conversations are saved.",
    };
  }
  if (text === "__ERROR_SERVER__") {
    return {
      type: "server",
      icon: "cloud_off",
      title: "Something went wrong",
      message:
        "The AI service is temporarily unavailable. Please try again in a moment.",
      hint: "If this persists, try starting a new conversation.",
    };
  }
  if (text === "__ERROR_TIMEOUT__") {
    return {
      type: "timeout",
      icon: "wifi_off",
      title: "Connection timed out",
      message:
        "The request took too long to complete. This usually means the service is under heavy load.",
      hint: "Try again — it often works on the second attempt.",
    };
  }
  if (text === "__ERROR_MAX_ITERATIONS__") {
    return {
      type: "max_iter",
      icon: "loop",
      title: "Request too complex",
      message:
        "I had trouble processing your request. This can happen with very complex questions.",
      hint: "Try rephrasing or breaking your question into smaller parts.",
    };
  }
  return null;
}

function appendErrorMessage(errorObj) {
  const container = document.getElementById("chatMessages");
  if (!container) return;

  const wrap = document.createElement("div");
  wrap.className = "message message--ai";
  wrap.innerHTML = `
    <div class="msg-avatar msg-avatar--ai" aria-hidden="true">
      <span class="material-symbols-outlined">smart_toy</span>
    </div>
    <div>
      <div class="msg-error-card">
        <div class="msg-error-card__header">
          <span class="material-symbols-outlined msg-error-card__icon">${errorObj.icon}</span>
          <span class="msg-error-card__title">${escapeHtml(errorObj.title)}</span>
        </div>
        <p class="msg-error-card__message">${escapeHtml(errorObj.message)}</p>
        <p class="msg-error-card__hint">${escapeHtml(errorObj.hint)}</p>
      </div>
      <div class="msg-time">Assistant · ${new Date().toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" })}</div>
    </div>
  `;
  container.appendChild(wrap);
  scrollToBottom();
}

async function handleStreamingResponse(response) {
  const reader = response.body.getReader();
  const decoder = new TextDecoder();

  let fullText = "";
  let bubbleEl = null;
  let buffer = "";
  let pendingSuggestions = null;

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });

      const events = buffer.split("\n\n");
      buffer = events.pop() || "";

      for (const event of events) {
        const line = event.trim();
        if (!line || !line.startsWith("data: ")) continue;
        const data = line.substring(6);
        if (data === "[DONE]") continue;

        try {
          const parsed = JSON.parse(data);

          // conversation_id event
          if (parsed.conversation_id) {
            conversationId = parsed.conversation_id;
            setActiveConversation(conversationId);
            continue;
          }

          // Suggestions event — store for rendering after message
          if (parsed.suggestions) {
            pendingSuggestions = parsed.suggestions;
            continue;
          }

          // Error event
          if (parsed.error) {
            fullText += parsed.error;
          }

          // Text chunk event
          if (parsed.text) {
            fullText += parsed.text;
          }
        } catch {
          fullText += data;
        }

        // Check for error codes
        const errorObj = parseErrorMessage(fullText);
        if (errorObj) {
          appendErrorMessage(errorObj);
          fullText = "";
          bubbleEl = null;
          continue;
        }

        if (fullText && !bubbleEl) {
          bubbleEl = createMessageElement("ai", fullText);
          const container = document.getElementById("chatMessages");
          if (container) container.appendChild(bubbleEl);
        } else if (bubbleEl) {
          const content = bubbleEl.querySelector(".msg-content");
          if (content) content.innerHTML = renderMarkdown(fullText);
        }
        scrollToBottom();
      }
    }

    // Process remaining buffer
    if (buffer.trim()) {
      const line = buffer.trim();
      if (line.startsWith("data: ")) {
        const data = line.substring(6);
        if (data !== "[DONE]") {
          try {
            const parsed = JSON.parse(data);
            if (parsed.text) fullText += parsed.text;
            if (parsed.error) fullText += parsed.error;
            if (parsed.suggestions) pendingSuggestions = parsed.suggestions;
          } catch {
            fullText += data;
          }
        }
      }
    }

    // Final error check
    if (fullText) {
      const errorObj = parseErrorMessage(fullText);
      if (errorObj) {
        appendErrorMessage(errorObj);
        return;
      }
    }

    // Final markdown render
    if (bubbleEl) {
      const content = bubbleEl.querySelector(".msg-content");
      if (content) content.innerHTML = renderMarkdown(fullText);
    }

    // Render follow-up suggestion chips
    if (pendingSuggestions && pendingSuggestions.length > 0) {
      renderFollowUpChips(pendingSuggestions);
    }
  } catch (err) {
    if (!bubbleEl) appendMessage("ai", "Error receiving response.");
    console.error("Stream error:", err);
  }
}

// ══════════════════════════════════════════════════════════
//  FOLLOW-UP SUGGESTION CHIPS
// ══════════════════════════════════════════════════════════

/**
 * Render follow-up suggestion chips below the last AI message.
 * Chips are tappable — clicking one sends that question.
 */
function renderFollowUpChips(suggestions) {
  const container = document.getElementById("chatMessages");
  if (!container || !suggestions.length) return;

  // Remove any existing chips first
  removeFollowUpChips();

  const chipsWrap = document.createElement("div");
  chipsWrap.className = "followup-chips";
  chipsWrap.id = "followupChips";

  suggestions.forEach((text, i) => {
    const chip = document.createElement("button");
    chip.className = "followup-chip";
    chip.style.animationDelay = `${i * 0.08}s`;
    chip.innerHTML = `
      <span class="material-symbols-outlined followup-chip__icon">arrow_forward</span>
      <span class="followup-chip__text">${escapeHtml(text)}</span>
    `;
    chip.addEventListener("click", () => {
      removeFollowUpChips();
      sendSuggestedQuestion(text);
    });
    chipsWrap.appendChild(chip);
  });

  container.appendChild(chipsWrap);
  scrollToBottom();
}

/** Remove follow-up chips from the DOM */
function removeFollowUpChips() {
  const existing = document.getElementById("followupChips");
  if (existing) existing.remove();
}

// ══════════════════════════════════════════════════════════
//  DOM HELPERS
// ══════════════════════════════════════════════════════════

function appendMessage(role, content, timestamp) {
  const el = createMessageElement(role, content, timestamp);
  const container = document.getElementById("chatMessages");
  if (container) {
    container.appendChild(el);
    scrollToBottom();
  }
}

function createMessageElement(role, content, timestamp) {
  const isUser = role === "user";
  const wrap = document.createElement("div");
  wrap.className = `message ${isUser ? "message--user" : "message--ai"}`;

  const time = (timestamp || new Date()).toLocaleTimeString("en-US", {
    hour: "2-digit",
    minute: "2-digit",
  });

  const renderedContent = isUser
    ? escapeHtml(content)
    : renderMarkdown(content);

  wrap.innerHTML = `
    <div class="msg-avatar ${isUser ? "msg-avatar--user" : "msg-avatar--ai"}" aria-hidden="true">
      <span class="material-symbols-outlined">${isUser ? "person" : "smart_toy"}</span>
    </div>
    <div>
      <div class="msg-bubble">
        <div class="msg-content">${renderedContent}</div>
      </div>
      <div class="msg-time">${isUser ? "You" : "Assistant"} · ${time}</div>
    </div>
  `;
  return wrap;
}

function clearMessagesDOM() {
  const container = document.getElementById("chatMessages");
  if (!container) return;
  Array.from(container.children).forEach((child) => {
    if (child.id !== "emptyState") child.remove();
  });
}

function showMessageSkeleton(container) {
  const skeleton = document.createElement("div");
  skeleton.id = "msgSkeleton";
  skeleton.innerHTML = `
    <div class="msg-skeleton msg-skeleton--user">
      <div class="msg-skeleton__avatar"></div>
      <div class="msg-skeleton__bubble">
        <div class="msg-skeleton__line msg-skeleton__line--mid"></div>
      </div>
    </div>
    <div class="msg-skeleton msg-skeleton--ai">
      <div class="msg-skeleton__avatar"></div>
      <div class="msg-skeleton__bubble">
        <div class="msg-skeleton__line msg-skeleton__line--full"></div>
        <div class="msg-skeleton__line msg-skeleton__line--full"></div>
        <div class="msg-skeleton__line msg-skeleton__line--mid"></div>
      </div>
    </div>
    <div class="msg-skeleton msg-skeleton--user">
      <div class="msg-skeleton__avatar"></div>
      <div class="msg-skeleton__bubble">
        <div class="msg-skeleton__line msg-skeleton__line--full"></div>
        <div class="msg-skeleton__line msg-skeleton__line--short"></div>
      </div>
    </div>
    <div class="msg-skeleton msg-skeleton--ai">
      <div class="msg-skeleton__avatar"></div>
      <div class="msg-skeleton__bubble">
        <div class="msg-skeleton__line msg-skeleton__line--full"></div>
        <div class="msg-skeleton__line msg-skeleton__line--full"></div>
        <div class="msg-skeleton__line msg-skeleton__line--full"></div>
        <div class="msg-skeleton__line msg-skeleton__line--short"></div>
      </div>
    </div>
  `;
  container.appendChild(skeleton);
}

// ── Logout ───────────────────────────────────────────────

function logout() {
  localStorage.removeItem("token");
  window.location.href = "/index.html";
}
