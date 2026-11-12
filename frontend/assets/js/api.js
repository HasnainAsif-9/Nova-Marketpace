/* NovaMarket API client — consistent JSON envelope handling */
const API = (() => {
  const BASE = "/api";

  async function request(method, path, body, opts = {}) {
    const headers = { "Accept": "application/json" };
    if (body !== undefined) headers["Content-Type"] = "application/json";
    const res = await fetch(BASE + path, {
      method,
      headers,
      credentials: "same-origin",
      body: body !== undefined ? JSON.stringify(body) : undefined,
      ...opts,
    });
    let data = null;
    try { data = await res.json(); } catch (e) { /* non-JSON */ }
    if (!res.ok) {
      const err = new Error((data && data.message) || `Request failed (${res.status})`);
      err.status = res.status;
      err.code = data && data.error_code;
      err.data = data && data.data;
      throw err;
    }
    return data;
  }

  return {
    get: (p) => request("GET", p),
    post: (p, b) => request("POST", p, b),
    put: (p, b) => request("PUT", p, b),
    del: (p) => request("DELETE", p),
    upload: async (p, formData) => {
      const res = await fetch(BASE + p, {
        method: "POST", credentials: "same-origin", body: formData,
      });
      const data = await res.json().catch(() => null);
      if (!res.ok) {
        const err = new Error((data && data.message) || "Upload failed");
        err.status = res.status; err.code = data && data.error_code;
        throw err;
      }
      return data;
    },
  };
})();

/* Auth state helpers */
const Auth = (() => {
  let currentUser = null;

  async function refresh() {
    try {
      const res = await API.get("/auth/me");
      currentUser = res.data && res.data.user ? res.data.user : null;
    } catch (e) {
      currentUser = null;
    }
    return currentUser;
  }

  function user() { return currentUser; }
  function isLoggedIn() { return !!currentUser; }
  function role() { return currentUser ? currentUser.role : null; }

  function loginRedirect(backTo) {
    const target = backTo || window.location.pathname + window.location.search;
    window.location.href = `/login.html?redirect=${encodeURIComponent(target)}`;
  }

  return { refresh, user, isLoggedIn, role, loginRedirect };
})();

/* Toast notifications */
function toast(message, type = "success", duration = 3500) {
  let container = document.querySelector(".toast-container");
  if (!container) {
    container = document.createElement("div");
    container.className = "toast-container";
    container.setAttribute("aria-live", "polite");
    container.setAttribute("role", "status");
    document.body.appendChild(container);
  }
  const el = document.createElement("div");
  el.className = `toast ${type}`;
  el.setAttribute("role", type === "error" ? "alert" : "status");
  const icons = { success: "✓", error: "✕", warning: "!" };
  el.innerHTML = `<span>${icons[type] || "•"}</span><span></span>`;
  el.querySelector("span:last-child").textContent = message;
  container.appendChild(el);
  setTimeout(() => { el.style.opacity = "0"; el.style.transition = "opacity .3s"; setTimeout(() => el.remove(), 300); }, duration);
}

/* Format helpers */
const Format = {
  money(n, symbol = "Rs.") {
    const num = Number(n || 0);
    return `${symbol} ${num.toLocaleString("en-PK", { minimumFractionDigits: num % 1 ? 2 : 0, maximumFractionDigits: 2 })}`;
  },
  date(d) {
    if (!d) return "—";
    return new Date(d).toLocaleDateString("en-PK", { year: "numeric", month: "short", day: "numeric" });
  },
  dateTime(d) {
    if (!d) return "—";
    return new Date(d).toLocaleString("en-PK", { year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
  },
  escapeHtml(s) {
    return String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  },
};

/* Stars renderer */
function starsHtml(avg, count) {
  const full = Math.round(avg || 0);
  let s = `<span class="stars" aria-label="${avg || 0} out of 5 stars">`;
  for (let i = 1; i <= 5; i++) s += i <= full ? "★" : "☆";
  s += `</span>`;
  if (count !== undefined) s += `<span>(${count})</span>`;
  return s;
}
