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
 * Minimal markdown → HTML renderer.
 * Handles: bold, italic, inline code, code blocks, headings,
 * unordered/ordered lists, blockquotes, horizontal rules, line breaks.
 * No external dependencies.
 */
function renderMarkdown(text) {
  if (!text) return "";

  let html = text;

  // Code blocks (```...```) — must be processed BEFORE inline rules
  html = html.replace(/```(\w*)\n?([\s\S]*?)```/g, (_, lang, code) => {
    return `<pre><code>${escapeHtml(code.trim())}</code></pre>`;
  });

  // Split into lines for block-level processing
  const lines = html.split("\n");
  const output = [];
  let inList = false;
  let listType = null; // "ul" or "ol"

  for (let i = 0; i < lines.length; i++) {
    let line = lines[i];

    // Skip lines inside code blocks (already processed above)
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

    // Unordered list item
    const ulMatch = line.match(/^[\s]*[-*+]\s+(.+)$/);
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

    // Ordered list item
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

    // Close any open list if this line isn't a list item
    if (inList) {
      output.push(`</${listType}>`);
      inList = false;
    }

    // Empty line → paragraph break
    if (line.trim() === "") {
      output.push("");
      continue;
    }

    // Regular paragraph
    output.push(`<p>${applyInline(line)}</p>`);
  }

  if (inList) output.push(`</${listType}>`);

  return output.join("\n");
}

/** Apply inline markdown: bold, italic, inline code, links */
function applyInline(text) {
  // Inline code (must be first to prevent bold/italic inside code)
  text = text.replace(/`([^`]+)`/g, "<code>$1</code>");
  // Bold + italic
  text = text.replace(/\*\*\*(.+?)\*\*\*/g, "<strong><em>$1</em></strong>");
  // Bold
  text = text.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  // Italic
  text = text.replace(/\*(.+?)\*/g, "<em>$1</em>");
  // Links
  text = text.replace(
    /\[([^\]]+)\]\(([^)]+)\)/g,
    '<a href="$2" target="_blank" rel="noopener">$1</a>',
  );
  return text;
}

// ── Global: called from suggestion buttons in HTML ────────

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

  // Auto-grow textarea
  input.addEventListener("input", () => {
    input.style.height = "auto";
    input.style.height = input.scrollHeight + "px";
  });

  // New chat buttons (header + sidebar)
  document
    .getElementById("newChatBtn")
    ?.addEventListener("click", startNewConversation);
  document
    .getElementById("sidebarNewChat")
    ?.addEventListener("click", startNewConversation);

  // Sidebar toggle
  document
    .getElementById("sidebarToggle")
    ?.addEventListener("click", toggleSidebar);
  document
    .getElementById("sidebarOverlay")
    ?.addEventListener("click", closeSidebar);

  // Logout
  ["logoutBtn", "logoutBtnMobile"].forEach((id) => {
    const btn = document.getElementById(id);
    if (btn) btn.addEventListener("click", logout);
  });

  // Close user menu when clicking outside
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
    // Mobile: slide in/out
    sidebarOpen = !sidebarOpen;
    sidebar.classList.toggle("open", sidebarOpen);
    overlay.classList.toggle("active", sidebarOpen);
  } else {
    // Desktop: collapse/expand
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

/** Fetch conversation list from API and render in sidebar */
async function loadConversationList() {
  const list = document.getElementById("conversationList");
  const empty = document.getElementById("sidebarEmpty");
  if (!list) return;

  // Show loading skeleton
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

  // Click to load conversation
  btn.addEventListener("click", (e) => {
    // Don't load if delete button was clicked
    if (e.target.closest(".conv-item__delete")) return;
    loadConversation(conv.id);
    closeSidebar();
  });

  // Delete button
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

/** Highlight the active conversation in sidebar */
function setActiveConversation(id) {
  document.querySelectorAll(".conv-item").forEach((el) => {
    el.classList.toggle("conv-item--active", el.dataset.convId === id);
  });
}

// ══════════════════════════════════════════════════════════
//  CONVERSATION ACTIONS
// ══════════════════════════════════════════════════════════

/** Load a past conversation from the API */
async function loadConversation(convId) {
  const container = document.getElementById("chatMessages");
  const emptyState = document.getElementById("emptyState");
  if (!container) return;

  // Set as active
  conversationId = convId;
  setActiveConversation(convId);

  // Clear current messages and show skeleton
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

    // Clear skeleton and render messages
    clearMessagesDOM();

    // Filter to only user and assistant messages with actual content
    // Skips: tool messages, system messages, and empty assistant messages
    // (tool-request messages saved with content="" and tool_name="__tool_request__")
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

/** Delete a conversation */
async function deleteConversation(convId) {
  if (!confirm("Delete this conversation? This cannot be undone.")) return;

  try {
    const res = await fetch(`${API_BASE}/conversations/${convId}`, {
      method: "DELETE",
      headers: authHeaders(),
    });

    if (!res.ok) throw new Error("Failed to delete");

    // If we deleted the active conversation, reset to new chat
    if (convId === conversationId) {
      startNewConversation();
    }

    // Refresh sidebar
    loadConversationList();
  } catch (err) {
    console.error("Failed to delete conversation:", err);
    alert("Failed to delete conversation. Please try again.");
  }
}

/** Start a fresh conversation */
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

  await sendMessage(message);
}

async function sendMessage(message) {
  if (isProcessing) return;
  isProcessing = true;

  // Hide empty state
  const emptyState = document.getElementById("emptyState");
  if (emptyState) emptyState.style.display = "none";

  // Append user message
  appendMessage("user", message);

  // Show typing indicator
  const typing = document.getElementById("typingIndicator");
  if (typing) typing.classList.add("active");
  scrollToBottom();

  try {
    const token = getToken();
    const body = { message };

    // Include conversation_id if we're continuing a conversation
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
    if (!res.ok) throw new Error(`Server error: ${res.status}`);

    if (typing) typing.classList.remove("active");
    await handleStreamingResponse(res);

    // Refresh sidebar to show new/updated conversation
    loadConversationList();
  } catch (err) {
    if (typing) typing.classList.remove("active");
    console.error(err);

    // Network / fetch errors
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

/**
 * Map error codes from the backend to user-friendly error objects.
 * Each error has an icon, title, message, and optional action.
 */
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

/** Render a styled error card instead of a plain text message */
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

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });

      // SSE events are separated by double newlines
      const events = buffer.split("\n\n");
      buffer = events.pop() || "";

      for (const event of events) {
        const line = event.trim();
        if (!line || !line.startsWith("data: ")) continue;
        const data = line.substring(6);
        if (data === "[DONE]") continue;

        // All events are now JSON-encoded
        try {
          const parsed = JSON.parse(data);

          // conversation_id event
          if (parsed.conversation_id) {
            conversationId = parsed.conversation_id;
            setActiveConversation(conversationId);
            continue;
          }

          // Error event from backend
          if (parsed.error) {
            fullText += parsed.error;
          }

          // Text chunk event
          if (parsed.text) {
            fullText += parsed.text;
          }
        } catch {
          // Fallback: treat as raw text if JSON parsing fails
          fullText += data;
        }

        // Check if the text is a structured error code
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

    // Process any remaining buffer
    if (buffer.trim()) {
      const line = buffer.trim();
      if (line.startsWith("data: ")) {
        const data = line.substring(6);
        if (data !== "[DONE]") {
          try {
            const parsed = JSON.parse(data);
            if (parsed.text) fullText += parsed.text;
            if (parsed.error) fullText += parsed.error;
          } catch {
            fullText += data;
          }
        }
      }
    }

    // Final check: if remaining text is an error code
    if (fullText) {
      const errorObj = parseErrorMessage(fullText);
      if (errorObj) {
        appendErrorMessage(errorObj);
        return;
      }
    }

    // Final render pass with full markdown
    if (bubbleEl) {
      const content = bubbleEl.querySelector(".msg-content");
      if (content) content.innerHTML = renderMarkdown(fullText);
    }
  } catch (err) {
    if (!bubbleEl) appendMessage("ai", "Error receiving response.");
    console.error("Stream error:", err);
  }
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

/** Remove all message elements (but keep empty state) */
function clearMessagesDOM() {
  const container = document.getElementById("chatMessages");
  if (!container) return;
  // Remove everything except #emptyState
  Array.from(container.children).forEach((child) => {
    if (child.id !== "emptyState") child.remove();
  });
}

/** Show loading skeleton while fetching conversation messages */
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
