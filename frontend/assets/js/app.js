/* NovaMarket app shell — injects header/footer, manages auth UI state */
(function () {
  const MARKETPLACE_NAME = "NovaMarket";

  function headerHtml() {
    return `
    <a href="#main-content" class="skip-link">Skip to main content</a>
    <header class="site-header">
      <div class="header-top">
        <div class="container flex justify-between items-center">
          <span>Free delivery on qualifying orders</span>
        </div>
      </div>
      <div class="container header-main">
        <button class="btn btn-ghost btn-icon mobile-menu-btn" id="mobile-menu-btn" aria-label="Open menu">
          <i class="fas fa-bars"></i>
        </button>
        <a href="/" class="logo" aria-label="${MARKETPLACE_NAME} home">
          <span class="logo-mark">N</span><span>${MARKETPLACE_NAME}</span>
        </a>
        <form class="search-bar" id="header-search" role="search">
          <label class="sr-only" for="header-search-input">Search products</label>
          <input id="header-search-input" type="search" placeholder="Search products, brands, categories..." autocomplete="off">
          <button type="submit" aria-label="Search"><i class="fas fa-search"></i></button>
        </form>
        <div class="header-actions">
          <div style="position:relative" id="notif-wrap">
            <button class="header-action" id="notif-btn" aria-label="Notifications">
              <i class="far fa-bell"></i><span class="label">Alerts</span>
            </button>
            <div class="notif-dropdown hidden" id="notif-dropdown"></div>
          </div>
          <a href="/cart.html" class="header-action" aria-label="Cart">
            <i class="fas fa-shopping-cart"></i><span class="label">Cart</span>
            <span class="cart-badge hidden" id="cart-badge">0</span>
          </a>
          <div id="auth-area"></div>
        </div>
      </div>
      <nav class="cat-nav" aria-label="Categories">
        <div class="container">
          <div class="cat-nav-inner" id="cat-nav-inner">
            <a href="/shop.html" class="cat-link">All Products</a>
          </div>
        </div>
      </nav>
      <div class="mobile-search">
        <form class="search-bar" id="mobile-search" role="search" style="max-width:none">
          <input type="search" placeholder="Search products..." aria-label="Search products">
          <button type="submit" aria-label="Search"><i class="fas fa-search"></i></button>
        </form>
      </div>
    </header>
    <div class="mobile-nav" id="mobile-nav">
      <div class="mobile-nav-panel" id="mobile-nav-panel"></div>
    </div>`;
  }

  function footerHtml() {
    return `
    <footer class="site-footer">
      <div class="container footer-grid">
        <div>
          <a href="/" class="logo" style="color:#fff;margin-bottom:12px;display:inline-flex">
            <span class="logo-mark">N</span><span>${MARKETPLACE_NAME}</span>
          </a>
          <p style="font-size:var(--nm-text-sm);color:#A8A29E;max-width:280px">
            A modern multi-vendor marketplace. Shop from trusted sellers, sell to thousands of buyers.
          </p>
          <p id="footer-contact" style="font-size:var(--nm-text-sm);color:#A8A29E;margin-top:12px"></p>
        </div>
        <div>
          <h4>Shop</h4>
          <a href="/shop.html">All Products</a>
          <a href="/shop.html?sort=newest">New Arrivals</a>
          <a href="/shop.html?on_sale=1">Deals</a>
          <a href="/shop.html?sort=rating">Top Rated</a>
        </div>
        <div>
          <h4>Sell</h4>
          <a href="/register.html?role=seller">Become a Seller</a>
          <a href="/seller/index.html">Seller Dashboard</a>
          <a href="/shop.html">Browse Marketplace</a>
        </div>
        <div>
          <h4>Account</h4>
          <a href="/login.html">Login</a>
          <a href="/register.html">Create Account</a>
          <a href="/buyer/index.html">My Orders</a>
          <a href="/buyer/index.html#wishlist">Wishlist</a>
        </div>
      </div>
      <div class="footer-bottom">
        <div class="container">© ${new Date().getFullYear()} ${MARKETPLACE_NAME}. All rights reserved. Developed by Hasnain</div>
      </div>
    </footer>`;
  }

  function authAreaHtml(user) {
    if (!user) {
      return `
        <a href="/login.html" class="header-action"><i class="far fa-user"></i><span class="label">Sign In</span></a>
        <a href="/register.html" class="btn btn-primary btn-sm" style="margin-left:4px">Join Free</a>`;
    }
    const dashLink = user.role === "admin" ? "/admin/index.html"
      : user.role === "seller" ? "/seller/index.html" : "/buyer/index.html";
    const dashLabel = user.role === "admin" ? "Admin" : user.role === "seller" ? "Seller" : "Account";
    return `
      <div style="position:relative" id="user-menu-wrap">
        <button class="header-action" id="user-menu-btn" aria-label="Account menu">
          <i class="far fa-user-circle" style="font-size:1.3rem"></i><span class="label">${Format.escapeHtml(user.full_name || user.username)}</span>
        </button>
        <div class="notif-dropdown hidden" id="user-dropdown" style="width:220px">
          <div style="padding:12px 16px;border-bottom:1px solid var(--nm-border)">
            <div style="font-weight:600">${Format.escapeHtml(user.full_name || user.username)}</div>
            <div class="text-xs text-muted">${Format.escapeHtml(user.email)}</div>
          </div>
          <a href="${dashLink}" style="display:block;padding:10px 16px;font-size:var(--nm-text-sm);color:var(--nm-text)">Dashboard</a>
          <a href="/buyer/index.html" style="display:block;padding:10px 16px;font-size:var(--nm-text-sm);color:var(--nm-text)">My Orders</a>
          <a href="/cart.html" style="display:block;padding:10px 16px;font-size:var(--nm-text-sm);color:var(--nm-text)">Cart</a>
          <button id="logout-btn" style="display:block;width:100%;text-align:left;padding:10px 16px;font-size:var(--nm-text-sm);color:var(--nm-error);background:none;border:none">Sign Out</button>
        </div>
      </div>`;
  }

  async function loadCategories() {
    try {
      const res = await API.get("/categories");
      const inner = document.getElementById("cat-nav-inner");
      if (!inner || !res.data) return;
      res.data.categories.forEach(c => {
        const a = document.createElement("a");
        a.href = `/shop.html?category_id=${c.id}`;
        a.className = "cat-link";
        a.textContent = c.name;
        inner.appendChild(a);
      });
    } catch (e) { /* non-critical */ }
  }

  async function updateCartBadge() {
    const badge = document.getElementById("cart-badge");
    if (!badge) return;
    if (!Auth.isLoggedIn()) { badge.classList.add("hidden"); return; }
    try {
      const res = await API.get("/cart");
      const count = res.data ? res.data.item_count : 0;
      badge.textContent = count;
      badge.classList.toggle("hidden", count === 0);
    } catch (e) { badge.classList.add("hidden"); }
  }

  async function loadNotifications() {
    const btn = document.getElementById("notif-btn");
    if (!btn) return;
    if (!Auth.isLoggedIn()) { btn.style.visibility = "hidden"; return; }
    try {
      const res = await API.get("/notifications?limit=8");
      const dd = document.getElementById("notif-dropdown");
      const notes = (res.data && res.data.notifications) || [];
      const unread = res.data ? res.data.unread_count : 0;
      if (unread > 0) {
        btn.innerHTML = `<i class="far fa-bell"></i><span class="label">Alerts</span><span class="cart-badge">${unread}</span>`;
      }
      dd.innerHTML = notes.length ? notes.map(n => `
        <div class="notif-item ${n.read ? "" : "unread"}">
          <div class="notif-title">${Format.escapeHtml(n.title)}</div>
          <div>${Format.escapeHtml(n.message)}</div>
          <div class="notif-time">${Format.dateTime(n.created_at)}</div>
        </div>`).join("") + `<div style="padding:10px;text-align:center"><a href="/buyer/index.html#notifications" class="text-sm">View all</a></div>`
        : `<div class="notif-item text-muted">No notifications yet</div>`;
    } catch (e) { /* ignore */ }
  }

  function bindEvents() {
    // Search
    document.querySelectorAll(".search-bar").forEach(form => {
      form.addEventListener("submit", e => {
        e.preventDefault();
        const input = form.querySelector("input[type=search]");
        const q = (input.value || "").trim();
        window.location.href = `/shop.html${q ? `?q=${encodeURIComponent(q)}` : ""}`;
      });
    });

    // Mobile menu
    const menuBtn = document.getElementById("mobile-menu-btn");
    const mobileNav = document.getElementById("mobile-nav");
    if (menuBtn && mobileNav) {
      menuBtn.addEventListener("click", () => mobileNav.classList.toggle("open"));
      mobileNav.addEventListener("click", e => { if (e.target === mobileNav) mobileNav.classList.remove("open"); });
      const panel = document.getElementById("mobile-nav-panel");
      const user = Auth.user();
      const links = [
        ["/", "Home", "fas fa-home"], ["/shop.html", "Shop", "fas fa-store"],
        ["/cart.html", "Cart", "fas fa-shopping-cart"],
        ["/buyer/index.html", "My Account", "far fa-user"],
        ["/buyer/index.html#wishlist", "Wishlist", "far fa-heart"],
      ];
      if (user && user.role === "seller") links.push(["/seller/index.html", "Seller Dashboard", "fas fa-chart-line"]);
      if (user && user.role === "admin") links.push(["/admin/index.html", "Admin Panel", "fas fa-shield-alt"]);
      if (!user) links.push(["/login.html", "Sign In", "far fa-sign-in-alt"], ["/register.html", "Create Account", "fas fa-user-plus"]);
      panel.innerHTML = links.map(([h, t, i]) => `<a href="${h}"><i class="${i}" style="width:20px"></i>${t}</a>`).join("");
    }

    // Notifications dropdown
    const notifBtn = document.getElementById("notif-btn");
    const notifDd = document.getElementById("notif-dropdown");
    if (notifBtn && notifDd) {
      notifBtn.addEventListener("click", e => { e.stopPropagation(); notifDd.classList.toggle("hidden"); });
      document.addEventListener("click", e => {
        if (!notifDd.contains(e.target)) notifDd.classList.add("hidden");
      });
    }

    // User menu
    const userBtn = document.getElementById("user-menu-btn");
    const userDd = document.getElementById("user-dropdown");
    if (userBtn && userDd) {
      userBtn.addEventListener("click", e => { e.stopPropagation(); userDd.classList.toggle("hidden"); });
      document.addEventListener("click", e => {
        if (!userDd.contains(e.target)) userDd.classList.add("hidden");
      });
      const logout = document.getElementById("logout-btn");
      if (logout) logout.addEventListener("click", async () => {
        try { await API.post("/auth/logout"); } catch (e) {}
        Auth.refresh().then(() => window.location.href = "/");
      });
    }
  }

  async function init() {
    const headerMount = document.getElementById("site-header");
    const footerMount = document.getElementById("site-footer");
    if (headerMount) headerMount.innerHTML = headerHtml();
    if (footerMount) footerMount.innerHTML = footerHtml();

    // Ensure the main landmark is a skip-link target
    const mainEl = document.querySelector("main");
    if (mainEl && !mainEl.id) mainEl.id = "main-content";
    if (mainEl) mainEl.setAttribute("tabindex", "-1");

    await Auth.refresh();
    const authArea = document.getElementById("auth-area");
    if (authArea) authArea.innerHTML = authAreaHtml(Auth.user());

    bindEvents();
    loadCategories();
    updateCartBadge();
    loadNotifications();

    // Contact info in footer
    API.get("/settings").then(r => {
      const el = document.getElementById("footer-contact");
      if (el && r.data && r.data.settings) {
        const s = r.data.settings;
        const parts = [];
        if (s.contact_email) parts.push(s.contact_email);
        if (s.contact_phone) parts.push(s.contact_phone);
        if (parts.length) el.textContent = parts.join(" · ");
      }
    }).catch(() => {});
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
