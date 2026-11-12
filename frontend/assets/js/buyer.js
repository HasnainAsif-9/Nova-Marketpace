/* Buyer dashboard — tabbed: overview, orders, wishlist, addresses, notifications, profile, security */
(function () {
  const content = document.getElementById("dash-content");
  const sidebar = document.getElementById("dash-sidebar");
  let symbol = "Rs.";
  let currentTab = "overview";

  const statusBadge = s => {
    const map = { pending: "badge-warning", confirmed: "badge-info", processing: "badge-info",
      shipped: "badge-primary", out_for_delivery: "badge-primary", delivered: "badge-success",
      cancelled: "badge-error", returned: "badge-error", refunded: "badge-muted" };
    return `<span class="badge ${map[s] || "badge-muted"}">${s.replace(/_/g, " ")}</span>`;
  };

  const tabs = {
    async overview() {
      const [ordersRes, wlRes] = await Promise.all([
        API.get("/orders?limit=5"),
        API.get("/wishlist"),
      ]);
      const orders = (ordersRes.data && ordersRes.data.orders) || [];
      const wishlist = (wlRes.data && wlRes.data.products) || [];
      const user = Auth.user() || {};
      content.innerHTML = `
        <h2 class="mb-4">Hello, ${Format.escapeHtml(user.full_name || user.username)} 👋</h2>
        <div class="stat-grid">
          <div class="stat-card"><div class="stat-label">Total Orders</div><div class="stat-value">${ordersRes.data?.pagination?.total || 0}</div></div>
          <div class="stat-card"><div class="stat-label">Wishlist Items</div><div class="stat-value">${wishlist.length}</div></div>
          <div class="stat-card"><div class="stat-label">Saved Addresses</div><div class="stat-value" id="addr-count">—</div></div>
        </div>
        <div class="card" style="padding:var(--nm-space-5)">
          <div class="flex justify-between items-center mb-4"><h3 style="margin:0">Recent Orders</h3><a href="#orders" class="text-sm">View all →</a></div>
          ${orders.length ? orders.map(o => `
            <div class="flex justify-between items-center" style="padding:var(--nm-space-3) 0;border-bottom:1px solid var(--nm-border)">
              <div><strong>${Format.escapeHtml(o.order_number)}</strong><div class="text-sm text-muted">${Format.date(o.created_at)} · ${o.seller_count || 0} seller(s)</div></div>
              <div class="flex items-center gap-3">${statusBadge(o.status)}<strong>${Format.money(o.total, symbol)}</strong></div>
            </div>`).join("") : `<p class="text-muted">No orders yet. <a href="/shop.html">Start shopping →</a></p>`}
        </div>`;
      API.get("/buyers/addresses").then(r => {
        const el = document.getElementById("addr-count");
        if (el) el.textContent = ((r.data && r.data.addresses) || []).length;
      }).catch(() => {});
    },

    async orders() {
      const res = await API.get("/orders?limit=20");
      const data = res.data || {};
      const orders = data.orders || [];
      const pg = data.pagination || {};
      content.innerHTML = `
        <h2 class="mb-4">My Orders</h2>
        <div id="orders-list">
          ${orders.length ? orders.map(o => `
            <div class="card mb-3" style="padding:var(--nm-space-4)">
              <div class="flex justify-between items-center wrap gap-2 mb-3">
                <div><strong>${Format.escapeHtml(o.order_number)}</strong><div class="text-sm text-muted">${Format.dateTime(o.created_at)}</div></div>
                <div class="flex items-center gap-3">${statusBadge(o.status)}<strong>${Format.money(o.total, symbol)}</strong></div>
              </div>
              <div class="text-sm text-muted mb-3">${o.item_count || 0} item(s) from ${o.seller_count || 0} seller(s) · ${o.delivery_option === "express" ? "Express" : "Standard"} delivery · ${Format.money(o.delivery_fee, symbol)} delivery</div>
              <div class="flex gap-2">
                <button class="btn btn-outline btn-sm" data-view-order="${o.id}">View Details</button>
                ${o.status === "pending" ? `<button class="btn btn-ghost btn-sm" data-cancel-order="${o.id}" style="color:var(--nm-error)">Cancel</button>` : ""}
              </div>
            </div>`).join("") : `<div class="empty-state card"><i class="fas fa-box-open"></i><h3>No orders yet</h3><a href="/shop.html" class="btn btn-primary mt-4">Start Shopping</a></div>`}
        </div>
        <div id="order-pagination"></div>`;
      document.querySelectorAll("[data-view-order]").forEach(b => b.addEventListener("click", () => viewOrder(b.dataset.viewOrder)));
      document.querySelectorAll("[data-cancel-order]").forEach(b => b.addEventListener("click", async () => {
        if (!confirm("Cancel this order?")) return;
        try { await API.post(`/orders/${b.dataset.cancelOrder}/cancel`); toast("Order cancelled"); tabs.orders(); }
        catch (e) { toast(e.message, "error"); }
      }));
    },

    async wishlist() {
      const res = await API.get("/wishlist");
      const products = (res.data && res.data.products) || [];
      content.innerHTML = `
        <h2 class="mb-4">My Wishlist</h2>
        <div class="grid grid-4" id="wishlist-grid">
          ${products.length ? products.map(p => productCardHtml(p, symbol)).join("") : `<div class="empty-state" style="grid-column:1/-1"><i class="far fa-heart"></i><h3>Wishlist is empty</h3><a href="/shop.html" class="btn btn-primary mt-4">Discover products</a></div>`}
        </div>`;
      bindProductCardActions(document.getElementById("wishlist-grid"));
    },

    async addresses() {
      const res = await API.get("/buyers/addresses");
      const addrs = (res.data && res.data.addresses) || [];
      content.innerHTML = `
        <h2 class="mb-4">Saved Addresses</h2>
        <div class="grid grid-2 mb-6">
          ${addrs.length ? addrs.map(a => `
            <div class="card" style="padding:var(--nm-space-4)">
              <div class="flex justify-between items-center mb-2">
                <strong>${Format.escapeHtml(a.label)}</strong>
                ${a.is_default ? `<span class="badge badge-primary">Default</span>` : ""}
              </div>
              <p class="text-sm" style="margin:0">${Format.escapeHtml(a.recipient_name)} · ${Format.escapeHtml(a.phone)}<br>
              ${Format.escapeHtml(a.address_line1)}${a.address_line2 ? ", " + Format.escapeHtml(a.address_line2) : ""}<br>
              ${Format.escapeHtml(a.city)} ${Format.escapeHtml(a.postal_code || "")} ${Format.escapeHtml(a.country || "")}</p>
              <div class="flex gap-2 mt-3">
                <button class="btn btn-ghost btn-sm" data-edit-addr="${a.id}">Edit</button>
                <button class="btn btn-ghost btn-sm" data-del-addr="${a.id}" style="color:var(--nm-error)">Delete</button>
              </div>
            </div>`).join("") : `<div class="empty-state card" style="grid-column:1/-1"><i class="fas fa-map-marker-alt"></i><h3>No saved addresses</h3></div>`}
        </div>
        <div class="card" style="padding:var(--nm-space-5)">
          <h3 class="mb-4">Add New Address</h3>
          <form id="addr-form">
            <div class="form-row">
              <div class="form-group"><label class="form-label">Label</label><input name="label" class="form-control" placeholder="Home / Office"></div>
              <div class="form-group"><label class="form-label">Recipient Name *</label><input name="recipient_name" class="form-control" required></div>
            </div>
            <div class="form-row">
              <div class="form-group"><label class="form-label">Phone *</label><input name="phone" class="form-control" required></div>
              <div class="form-group"><label class="form-label">Address Line 1 *</label><input name="address_line1" class="form-control" required></div>
            </div>
            <div class="form-group"><label class="form-label">Address Line 2</label><input name="address_line2" class="form-control"></div>
            <div class="form-row">
              <div class="form-group"><label class="form-label">City *</label><input name="city" class="form-control" required></div>
              <div class="form-group"><label class="form-label">State</label><input name="state" class="form-control"></div>
            </div>
            <div class="form-row">
              <div class="form-group"><label class="form-label">Postal Code</label><input name="postal_code" class="form-control"></div>
              <div class="form-group"><label class="form-label">Country</label><input name="country" class="form-control" value="Pakistan"></div>
            </div>
            <label class="form-check mb-3"><input type="checkbox" name="is_default"> Set as default</label>
            <button type="submit" class="btn btn-primary">Save Address</button>
          </form>
        </div>`;
      document.getElementById("addr-form").addEventListener("submit", async e => {
        e.preventDefault();
        const fd = new FormData(e.target);
        const body = Object.fromEntries(fd.entries());
        body.is_default = fd.has("is_default");
        try { await API.post("/buyers/addresses", body); toast("Address saved"); tabs.addresses(); }
        catch (err) { toast(err.message, "error"); }
      });
      document.querySelectorAll("[data-del-addr]").forEach(b => b.addEventListener("click", async () => {
        if (!confirm("Delete this address?")) return;
        try { await API.del(`/buyers/addresses/${b.dataset.delAddr}`); toast("Address deleted"); tabs.addresses(); }
        catch (e) { toast(e.message, "error"); }
      }));
    },

    async notifications() {
      const res = await API.get("/notifications?limit=50");
      const notes = (res.data && res.data.notifications) || [];
      content.innerHTML = `
        <div class="flex justify-between items-center mb-4">
          <h2 style="margin:0">Notifications</h2>
          <button class="btn btn-outline btn-sm" id="mark-all-read">Mark all read</button>
        </div>
        <div class="card">
          ${notes.length ? notes.map(n => `
            <div class="notif-item ${n.read ? "" : "unread"}" style="border-bottom:1px solid var(--nm-border)">
              <div class="flex justify-between items-center">
                <strong>${Format.escapeHtml(n.title)}</strong>
                <span class="text-xs text-muted">${Format.dateTime(n.created_at)}</span>
              </div>
              <div class="text-sm" style="color:var(--nm-text-2)">${Format.escapeHtml(n.message)}</div>
            </div>`).join("") : `<div class="empty-state"><i class="far fa-bell"></i><p>No notifications</p></div>`}
        </div>`;
      document.getElementById("mark-all-read")?.addEventListener("click", async () => {
        await API.post("/notifications/read-all"); toast("All marked as read"); tabs.notifications();
      });
    },

    async profile() {
      const user = Auth.user() || {};
      content.innerHTML = `
        <h2 class="mb-4">Profile Settings</h2>
        <div class="card" style="padding:var(--nm-space-5);max-width:560px">
          <form id="profile-form">
            <div class="form-group"><label class="form-label">Username</label><input class="form-control" value="${Format.escapeHtml(user.username || "")}" disabled></div>
            <div class="form-group"><label class="form-label">Email</label><input class="form-control" value="${Format.escapeHtml(user.email || "")}" disabled></div>
            <div class="form-group"><label class="form-label">Full Name</label><input name="full_name" class="form-control" value="${Format.escapeHtml(user.full_name || "")}"></div>
            <div class="form-group"><label class="form-label">Phone</label><input name="phone" class="form-control" value="${Format.escapeHtml(user.phone || "")}"></div>
            <button type="submit" class="btn btn-primary">Save Changes</button>
          </form>
        </div>`;
      document.getElementById("profile-form").addEventListener("submit", async e => {
        e.preventDefault();
        const fd = new FormData(e.target);
        try {
          await API.put("/users/me", { full_name: fd.get("full_name"), phone: fd.get("phone") });
          toast("Profile updated");
          Auth.refresh();
        } catch (err) { toast(err.message, "error"); }
      });
    },

    async security() {
      content.innerHTML = `
        <h2 class="mb-4">Security</h2>
        <div class="card" style="padding:var(--nm-space-5);max-width:480px">
          <h3 class="mb-4">Change Password</h3>
          <form id="pw-form">
            <div class="form-group"><label class="form-label">Current Password</label><input name="current_password" type="password" class="form-control" required></div>
            <div class="form-group"><label class="form-label">New Password</label><input name="new_password" type="password" class="form-control" required minlength="8"></div>
            <button type="submit" class="btn btn-primary">Update Password</button>
          </form>
        </div>
        <div class="card mt-4" style="padding:var(--nm-space-5);max-width:480px">
          <h3 class="mb-2">Session</h3>
          <p class="text-sm text-muted">You are signed in as <strong>${Format.escapeHtml((Auth.user() || {}).email || "")}</strong></p>
          <button class="btn btn-outline btn-sm mt-2" id="logout-btn">Sign Out</button>
        </div>`;
      document.getElementById("pw-form").addEventListener("submit", async e => {
        e.preventDefault();
        const fd = new FormData(e.target);
        try {
          await API.post("/auth/change-password", { current_password: fd.get("current_password"), new_password: fd.get("new_password") });
          toast("Password changed"); e.target.reset();
        } catch (err) { toast(err.message, "error"); }
      });
      document.getElementById("logout-btn").addEventListener("click", async () => {
        await API.post("/auth/logout"); window.location.href = "/";
      });
    },
  };

  async function viewOrder(id) {
    try {
      const res = await API.get(`/orders/${id}`);
      const o = res.data.order;
      const subs = o.sub_orders || [];
      content.innerHTML = `
        <button class="btn btn-ghost mb-4" id="back-orders">← Back to orders</button>
        <h2 class="mb-2">Order ${Format.escapeHtml(o.order_number)}</h2>
        <p class="text-muted mb-4">Placed ${Format.dateTime(o.created_at)} · ${statusBadge(o.status)}</p>
        <div class="grid grid-2 mb-4">
          <div class="card" style="padding:var(--nm-space-4)">
            <h4 class="mb-2">Delivery Address</h4>
            <p class="text-sm" style="margin:0">${Format.escapeHtml(o.address_snapshot?.recipient_name)}<br>
            ${Format.escapeHtml(o.address_snapshot?.address_line1)}${o.address_snapshot?.address_line2 ? ", " + Format.escapeHtml(o.address_snapshot.address_line2) : ""}<br>
            ${Format.escapeHtml(o.address_snapshot?.city)} ${Format.escapeHtml(o.address_snapshot?.postal_code || "")} · ${Format.escapeHtml(o.address_snapshot?.phone)}</p>
          </div>
          <div class="card" style="padding:var(--nm-space-4)">
            <h4 class="mb-2">Payment</h4>
            <p class="text-sm" style="margin:0">Method: Cash on Delivery<br>Status: ${o.payment_status}<br>Total: <strong>${Format.money(o.total, symbol)}</strong></p>
          </div>
        </div>
        ${subs.map(s => `
          <div class="card mb-3" style="padding:var(--nm-space-4)">
            <h4 class="mb-3">Seller Order · ${statusBadge(s.status)}</h4>
            ${s.items.map(i => `
              <div class="flex justify-between items-center" style="padding:var(--nm-space-2) 0;border-bottom:1px solid var(--nm-border)">
                <div><strong>${Format.escapeHtml(i.product_name)}</strong><div class="text-sm text-muted">Qty ${i.quantity} × ${Format.money(i.unit_price, symbol)}</div></div>
                <strong>${Format.money(i.line_total, symbol)}</strong>
              </div>`).join("")}
            <div class="summary-row mt-2"><span>Seller subtotal</span><span>${Format.money(s.subtotal, symbol)}</span></div>
          </div>`).join("")}
        <div class="card" style="padding:var(--nm-space-4)">
          <div class="summary-row"><span>Subtotal</span><span>${Format.money(o.subtotal, symbol)}</span></div>
          <div class="summary-row"><span>Delivery (${o.delivery_option})</span><span>${Format.money(o.delivery_fee, symbol)}</span></div>
          <div class="summary-row total"><span>Total</span><span>${Format.money(o.total, symbol)}</span></div>
        </div>`;
      document.getElementById("back-orders").addEventListener("click", () => { location.hash = "#orders"; });
    } catch (e) { toast(e.message, "error"); }
  }

  function switchTab(tab) {
    currentTab = tab;
    sidebar.querySelectorAll(".dash-link").forEach(l => l.classList.toggle("active", l.dataset.tab === tab));
    content.innerHTML = `<div class="spinner"></div>`;
    tabs[tab] ? tabs[tab]() : tabs.overview();
  }

  sidebar.querySelectorAll(".dash-link").forEach(l => {
    l.addEventListener("click", e => { e.preventDefault(); location.hash = l.dataset.tab; });
  });
  window.addEventListener("hashchange", () => {
    const tab = location.hash.replace("#", "") || "overview";
    if (tabs[tab]) switchTab(tab);
  });

  // Auth guard
  (async function init() {
    await Auth.refresh();
    if (!Auth.isLoggedIn() || Auth.role() !== "buyer") {
      content.innerHTML = `<div class="empty-state card" style="padding:var(--nm-space-12)">
        <i class="fas fa-lock"></i><h3>Login Required</h3>
        <p>Please sign in with a buyer account.</p>
        <a href="/login.html?redirect=/buyer/index.html" class="btn btn-primary mt-4">Sign In</a></div>`;
      sidebar.style.display = "none";
      return;
    }
    API.get("/settings").then(r => {
      if (r.data && r.data.settings && r.data.settings.currency_symbol) symbol = r.data.settings.currency_symbol;
    }).catch(() => {});
    const tab = location.hash.replace("#", "") || "overview";
    switchTab(tabs[tab] ? tab : "overview");
  })();
})();
