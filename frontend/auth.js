/* ============================================================
   auth.js — Login & Registration Logic
   ClassifierBT.com
   ============================================================ */

// ── Tab switching ────────────────────────────────────────────
const loginTab = document.getElementById("loginTab");
const registerTab = document.getElementById("registerTab");
const loginForm = document.getElementById("loginForm");
const registerForm = document.getElementById("registerForm");

function activateTab(tab) {
  if (tab === "login") {
    loginForm.classList.remove("auth-form--hidden");
    registerForm.classList.add("auth-form--hidden");
    loginTab.classList.add("auth-tab--active");
    loginTab.setAttribute("aria-selected", "true");
    registerTab.classList.remove("auth-tab--active");
    registerTab.setAttribute("aria-selected", "false");
  } else {
    registerForm.classList.remove("auth-form--hidden");
    loginForm.classList.add("auth-form--hidden");
    registerTab.classList.add("auth-tab--active");
    registerTab.setAttribute("aria-selected", "true");
    loginTab.classList.remove("auth-tab--active");
    loginTab.setAttribute("aria-selected", "false");
  }
}

loginTab.addEventListener("click", () => activateTab("login"));
registerTab.addEventListener("click", () => activateTab("register"));

// ── Helper: show message ─────────────────────────────────────
function showMessage(divId, text, type) {
  const el = document.getElementById(divId);
  el.textContent = text;
  el.className = `form-message ${type}`;
}

// ── Login form ───────────────────────────────────────────────
loginForm.addEventListener("submit", async (e) => {
  e.preventDefault();

  const email = document.getElementById("login-email").value;
  const password = document.getElementById("login-password").value;

  showMessage("login-message", "Authorizing access", "loading");

  try {
    const response = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });

    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.detail || "Login failed");
    }

    localStorage.setItem("token", data.access_token);
    showMessage("login-message", "Access granted", "success");

    setTimeout(() => {
      window.location.href = "/dashboard.html";
    }, 1000);
  } catch (error) {
    showMessage("login-message", error.message, "error");
  }
});

// ── Register form ────────────────────────────────────────────
registerForm.addEventListener("submit", async (e) => {
  e.preventDefault();

  const username = document.getElementById("register-username").value;
  const email = document.getElementById("register-email").value;
  const password = document.getElementById("register-password").value;

  showMessage("register-message", "Creating account…", "loading");

  try {
    const response = await fetch("/api/auth/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, username, password }),
    });

    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.detail || "Registration failed");
    }

    showMessage(
      "register-message",
      "✓ Account created. Please login.",
      "success",
    );
    registerForm.reset();

    setTimeout(() => {
      activateTab("login");
      document.getElementById("login-email").value = email;
    }, 2000);
  } catch (error) {
    showMessage("register-message", error.message, "error");
  }
});
