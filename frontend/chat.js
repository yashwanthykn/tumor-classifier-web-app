/* ============================================================
   chat.js — Clinical Assistant Chat Logic
   ClassifierBT.com
   ============================================================ */

let conversationId = null;
let isProcessing = false;

// ── Global: called from suggestion buttons in HTML ────────────
function sendSuggestedQuestion(question) {
  const input = document.getElementById("chatInput");
  if (input) {
    input.value = question;
    handleSendMessage();
  }
}

// ── Auth + init ───────────────────────────────────────────────
window.addEventListener("DOMContentLoaded", async () => {
  const token = localStorage.getItem("token");
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
  } catch {
    localStorage.removeItem("token");
    window.location.href = "/index.html";
  }
});

// ── Init chat ─────────────────────────────────────────────────
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

  // New chat button
  const newChatBtn = document.getElementById("newChatBtn");
  if (newChatBtn) newChatBtn.addEventListener("click", clearConversation);

  // Logout buttons
  ["logoutBtn", "logoutBtnMobile"].forEach((id) => {
    const btn = document.getElementById(id);
    if (btn) btn.addEventListener("click", logout);
  });

  // Close user menu when clicking outside
  document.addEventListener("click", (e) => {
    const menu = document.getElementById("userMenu");
    if (menu && !menu.contains(e.target)) menu.classList.remove("show");
  });

  conversationId = "conv_" + Math.random().toString(36).substring(2, 14);
}

// ── Handle send ───────────────────────────────────────────────
async function handleSendMessage() {
  const input = document.getElementById("chatInput");
  if (!input) return;
  const message = input.value.trim();
  if (!message || isProcessing) return;

  input.value = "";
  input.style.height = "auto";

  await sendMessage(message);
}

// ── Send message ──────────────────────────────────────────────
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
    const token = localStorage.getItem("token");
    const res = await fetch("/api/chat/message", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ message, conversation_id: conversationId }),
    });

    if (res.status === 401) {
      alert("Session expired. Please login again.");
      logout();
      return;
    }
    if (!res.ok) throw new Error(`Server error: ${res.status}`);

    if (typing) typing.classList.remove("active");
    await handleStreamingResponse(res);
  } catch (err) {
    if (typing) typing.classList.remove("active");
    appendMessage("ai", "❌ Sorry, I encountered an error. Please try again.");
    console.error(err);
  } finally {
    isProcessing = false;
  }
}

// ── Streaming response handler ────────────────────────────────
async function handleStreamingResponse(response) {
  const reader = response.body.getReader();
  const decoder = new TextDecoder();

  let fullText = "";
  let bubbleEl = null;

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      const raw = decoder.decode(value, { stream: true });
      const lines = raw.split("\n\n");

      for (const line of lines) {
        if (!line.trim() || !line.startsWith("data: ")) continue;
        const data = line.substring(6).trim();
        if (data === "[DONE]") continue;

        fullText += data;

        if (!bubbleEl) {
          bubbleEl = createMessageElement("ai", fullText);
          const container = document.getElementById("chatMessages");
          if (container) container.appendChild(bubbleEl);
        } else {
          const content = bubbleEl.querySelector(".msg-content");
          if (content) content.textContent = fullText;
        }
        scrollToBottom();
      }
    }
  } catch (err) {
    if (!bubbleEl) appendMessage("ai", "❌ Error receiving response.");
    console.error("Stream error:", err);
  }
}

// ── DOM helpers ───────────────────────────────────────────────
function appendMessage(role, content) {
  const el = createMessageElement(role, content);
  const container = document.getElementById("chatMessages");
  if (container) {
    container.appendChild(el);
    scrollToBottom();
  }
}

function createMessageElement(role, content) {
  const isUser = role === "user";
  const wrap = document.createElement("div");
  wrap.className = `message ${isUser ? "message--user" : "message--ai"}`;

  const time = new Date().toLocaleTimeString("en-US", {
    hour: "2-digit",
    minute: "2-digit",
  });

  wrap.innerHTML = `
    <div class="msg-avatar ${isUser ? "msg-avatar--user" : "msg-avatar--ai"}" aria-hidden="true">
      <span class="material-symbols-outlined">${isUser ? "person" : "smart_toy"}</span>
    </div>
    <div>
      <div class="msg-bubble">
        <span class="msg-content">${escapeHtml(content)}</span>
      </div>
      <div class="msg-time">${isUser ? "You" : "Assistant"} · ${time}</div>
    </div>
  `;
  return wrap;
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

// ── Clear conversation ────────────────────────────────────────
function clearConversation() {
  if (!confirm("Start a new conversation? Current chat will be cleared."))
    return;

  const container = document.getElementById("chatMessages");
  if (container) {
    Array.from(container.querySelectorAll(".message")).forEach((m) =>
      m.remove(),
    );
  }

  const emptyState = document.getElementById("emptyState");
  if (emptyState) emptyState.style.display = "flex";

  conversationId = "conv_" + Math.random().toString(36).substring(2, 14);
}

// ── Logout ────────────────────────────────────────────────────
function logout() {
  localStorage.removeItem("token");
  window.location.href = "/index.html";
}
