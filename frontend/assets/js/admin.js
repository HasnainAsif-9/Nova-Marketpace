/* Admin dashboard */
(function () {
  const content = document.getElementById("dash-content");
  const sidebar = document.getElementById("dash-sidebar");
  let symbol = "Rs.";
  let charts = {};

  const statusBadge = s => {
    const map = { pending: "badge-warning", confirmed: "badge-info", processing: "badge-info",
      shipped: "badge-primary", out_for_delivery: "badge-primary", delivered: "badge-success",
      cancelled: "badge-error", returned: "badge-error", refunded: "badge-muted",
      active: "badge-success", inactive: "badge-muted", approved: "badge-success",
      rejected: "badge-error", suspended: "badge-error", draft: "badge-muted" };
    return `<span class="badge ${map[s] || "badge-muted"}">${String(s).replace(/_/g, " ")}</span>`;
  };

  function destroyCharts() {
    Object.values(charts).forEach(c => c && c.destroy && c.destroy());
    charts = {};
  }

  const tabs = {
    async overview() {
      const res = await API.get("/admin/stats");
      const s = res.data.stats;
      content.innerHTML = `
        <h2 class="mb-4">Admin Overview</h2>
        <div class="stat-grid">
          <div class="stat-card"><div class="stat-label">Total Buyers</div><div class="stat-value">${s.total_buyers}</div></div>
          <div class="stat-card"><div class="stat-label">Total Sellers</div><div class="stat-value">${s.total_sellers} <span class="text-sm text-muted">(${s.pending_sellers} pending)</span></div></div>
          <div class="stat-card"><div class="stat-label">Products</div><div class="stat-value">${s.active_products} <span class="text-sm text-muted">/${s.total_products}</span></div></div>
          <div class="stat-card"><div class="stat-label">Total Orders</div><div class="stat-value">${s.total_orders}</div></div>
          <div class="stat-card"><div class="stat-label">Revenue</div><div class="stat-value">${Format.money(s.total_revenue, symbol)}</div></div>
          <div class="stat-card"><div class="stat-label">Commission Earned</div><div class="stat-value">${Format.money(s.total_commission, symbol)}</div></div>
          <div class="stat-card"><div class="stat-label">Pending Orders</div><div class="stat-value">${s.pending_orders}</div></div>
          <div class="stat-card"><div class="stat-label">Delivered</div><div class="stat-value">${s.delivered_orders}</div></div>
        </div>
        <div class="grid grid-2">
          <div class="card" style="padding:var(--nm-space-5)">
            <h3 class="mb-4">Recent Orders</h3>
            ${s.recent_orders.length ? s.recent_orders.map(o => `
              <div class="flex justify-between items-center" style="padding:var(--nm-space-2) 0;border-bottom:1px solid var(--nm-border)">
                <div><strong>${Format.escapeHtml(o.order_number)}</strong><div class="text-sm text-muted">${Format.date(o.created_at)}</div></div>
                <div class="flex items-center gap-2">${statusBadge(o.status)}<strong>${Format.money(o.total, symbol)}</strong></div>
              </div>`).join("") : `<p class="text-muted">No orders yet.</p>`}
          </div>
          <div class="card" style="padding:var(--nm-space-5)">
            <h3 class="mb-4">Quick Actions</h3>
            <div class="flex flex-col gap-2">
              <a href="#sellers" class="btn btn-outline" style="justify-content:flex-start"><i class="fas fa-store"></i> Review seller applications (${s.pending_sellers})</a>
              <a href="#products" class="btn btn-outline" style="justify-content:flex-start"><i class="fas fa-box"></i> Moderate products (${s.pending_products} pending)</a>
              <a href="#orders" class="btn btn-outline" style="justify-content:flex-start"><i class="fas fa-shopping-bag"></i> Manage orders (${s.pending_orders} pending)</a>
              <a href="#settings" class="btn btn-outline" style="justify-content:flex-start"><i class="fas fa-cog"></i> Marketplace settings</a>
            </div>
          </div>
        </div>`;
    },

    async analytics() {
      const res = await API.get("/admin/analytics/sales?days=30");
      const data = res.data;
      content.innerHTML = `
        <h2 class="mb-4">Analytics (last 30 days)</h2>
        <div class="grid grid-2 mb-4">
          <div class="card" style="padding:var(--nm-space-5)">
            <h3 class="mb-3">Daily Sales</h3>
            <div class="chart-container"><canvas id="chart-sales"></canvas></div>
          </div>
          <div class="card" style="padding:var(--nm-space-5)">
            <h3 class="mb-3">Top Products</h3>
            <div class="chart-container"><canvas id="chart-top"></canvas></div>
          </div>
        </div>
        <div class="card" style="padding:var(--nm-space-5)">
          <h3 class="mb-3">Top Sellers</h3>
          <div class="table-wrap" style="border:none">
            <table class="data-table">
              <thead><tr><th>Store</th><th>Sales</th><th>Commission</th><th>Orders</th></tr></thead>
              <tbody>
                ${(data.seller_performance || []).map(sp => `
                  <tr><td><strong>${Format.escapeHtml(sp.store_name)}</strong></td>
                  <td>${Format.money(sp.sales, symbol)}</td>
                  <td>${Format.money(sp.commission, symbol)}</td>
                  <td>${sp.orders}</td></tr>`).join("") || `<tr><td colspan="4" class="text-center text-muted">No data yet.</td></tr>`}
              </tbody>
            </table>
          </div>
        </div>`;

      const daily = data.daily_sales || [];
      if (window.Chart && daily.length) {
        charts.sales = new Chart(document.getElementById("chart-sales"), {
          type: "line",
          data: {
            labels: daily.map(d => d._id),
            datasets: [{ label: "Revenue", data: daily.map(d => d.revenue), borderColor: "#0F6B5C", backgroundColor: "rgba(15,107,92,.1)", fill: true, tension: 0.3 }],
          },
          options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } } },
        });
        const top = (data.top_products || []).slice(0, 8);
        charts.top = new Chart(document.getElementById("chart-top"), {
          type: "bar",
          data: {
            labels: top.map(t => (t.name || "Product").slice(0, 20)),
            datasets: [{ label: "Revenue", data: top.map(t => t.revenue), backgroundColor: "#E8A33D" }],
          },
          options: { responsive: true, maintainAspectRatio: false, indexAxis: "y", plugins: { legend: { display: false } } },
        });
      }
    },

    async users() {
      const res = await API.get("/admin/users?limit=50");
      const data = res.data || {};
      const users = data.users || [];
      content.innerHTML = `
        <h2 class="mb-4">Users</h2>
        <div class="table-wrap">
          <table class="data-table">
            <thead><tr><th>User</th><th>Role</th><th>Status</th><th>Joined</th><th>Actions</th></tr></thead>
            <tbody>
              ${users.map(u => `
                <tr>
                  <td><strong>${Format.escapeHtml(u.full_name || u.username)}</strong><div class="text-xs text-muted">${Format.escapeHtml(u.email)}</div></td>
                  <td><span class="badge badge-primary">${u.role}</span></td>
                  <td>${statusBadge(u.status)}</td>
                  <td>${Format.date(u.created_at)}</td>
                  <td>
                    ${u.role !== "admin" ? `
                      <button class="btn btn-ghost btn-sm" data-user-status="${u.id}" data-status="${u.status === "active" ? "suspended" : "active"}">${u.status === "active" ? "Suspend" : "Activate"}</button>` : "—"}
                  </td>
                </tr>`).join("")}
            </tbody>
          </table>
        </div>`;
      document.querySelectorAll("[data-user-status]").forEach(b => b.addEventListener("click", async () => {
        const status = b.dataset.status;
        if (!confirm(`Are you sure you want to ${status} this user?`)) return;
        try { await API.put(`/admin/users/${b.dataset.userStatus}/status`, { status }); toast(`User ${status}d`); tabs.users(); }
        catch (e) { toast(e.message, "error"); }
      }));
    },

    async sellers() {
      const res = await API.get("/admin/sellers?limit=50");
      const data = res.data || {};
      const sellers = data.sellers || [];
      content.innerHTML = `
        <h2 class="mb-4">Sellers</h2>
        <div class="table-wrap">
          <table class="data-table">
            <thead><tr><th>Store</th><th>Owner</th><th>Products</th><th>Status</th><th>Actions</th></tr></thead>
            <tbody>
              ${sellers.map(s => `
                <tr>
                  <td><strong>${Format.escapeHtml(s.store_name)}</strong><div class="text-xs text-muted">${Format.escapeHtml(s.store_slug || "")}</div></td>
                  <td>${Format.escapeHtml(s.owner?.email || "—")}</td>
                  <td>${s.product_count || 0}</td>
                  <td>${statusBadge(s.status)}${s.status_reason ? `<div class="text-xs text-muted">${Format.escapeHtml(s.status_reason)}</div>` : ""}</td>
                  <td>
                    ${s.status === "pending" ? `
                      <button class="btn btn-primary btn-sm" data-seller-status="${s.id}" data-status="approved">Approve</button>
                      <button class="btn btn-ghost btn-sm" data-seller-status="${s.id}" data-status="rejected">Reject</button>` : ""}
                    ${s.status === "approved" ? `<button class="btn btn-ghost btn-sm" data-seller-status="${s.id}" data-status="suspended">Suspend</button>` : ""}
                    ${s.status === "suspended" || s.status === "rejected" ? `<button class="btn btn-ghost btn-sm" data-seller-status="${s.id}" data-status="approved">Activate</button>` : ""}
                  </td>
                </tr>`).join("")}
            </tbody>
          </table>
        </div>`;
      document.querySelectorAll("[data-seller-status]").forEach(b => b.addEventListener("click", async () => {
        const status = b.dataset.status;
        let reason = "";
        if (status === "rejected" || status === "suspended") {
          reason = prompt("Reason (optional):", "") || "";
        }
        try { await API.put(`/admin/sellers/${b.dataset.sellerStatus}/status`, { status, reason }); toast(`Seller ${status}`); tabs.sellers(); }
        catch (e) { toast(e.message, "error"); }
      }));
    },

    async products() {
      const res = await API.get("/admin/products?limit=50");
      const data = res.data || {};
      const products = data.products || [];
      content.innerHTML = `
        <h2 class="mb-4">Products</h2>
        <div class="table-wrap">
          <table class="data-table">
            <thead><tr><th>Product</th><th>Store</th><th>Price</th><th>Stock</th><th>Status</th><th>Actions</th></tr></thead>
            <tbody>
              ${products.map(p => `
                <tr>
                  <td><strong>${Format.escapeHtml(p.name)}</strong><div class="text-xs text-muted">${Format.escapeHtml(p.sku || "")}</div></td>
                  <td>${Format.escapeHtml(p.store_name || "—")}</td>
                  <td>${Format.money(p.price, symbol)}</td>
                  <td>${p.stock}</td>
                  <td>${statusBadge(p.status)}</td>
                  <td>
                    ${p.status === "pending" ? `<button class="btn btn-primary btn-sm" data-prod-status="${p.id}" data-status="active">Approve</button>
                    <button class="btn btn-ghost btn-sm" data-prod-status="${p.id}" data-status="rejected">Reject</button>` : ""}
                    ${p.status === "active" ? `<button class="btn btn-ghost btn-sm" data-prod-status="${p.id}" data-status="inactive">Deactivate</button>` : ""}
                    ${p.status === "inactive" || p.status === "rejected" ? `<button class="btn btn-ghost btn-sm" data-prod-status="${p.id}" data-status="active">Activate</button>` : ""}
                  </td>
                </tr>`).join("")}
            </tbody>
          </table>
        </div>`;
      document.querySelectorAll("[data-prod-status]").forEach(b => b.addEventListener("click", async () => {
        try { await API.put(`/admin/products/${b.dataset.prodStatus}/status`, { status: b.dataset.status }); toast("Product updated"); tabs.products(); }
        catch (e) { toast(e.message, "error"); }
      }));
    },

    async categories() {
      const res = await API.get("/categories");
      const cats = (res.data && res.data.categories) || [];
      content.innerHTML = `
        <div class="flex justify-between items-center mb-4">
          <h2 style="margin:0">Categories</h2>
          <button class="btn btn-primary btn-sm" id="add-cat">+ Add Category</button>
        </div>
        <div id="cat-form-wrap" class="hidden mb-4"></div>
        <div class="table-wrap">
          <table class="data-table">
            <thead><tr><th>Name</th><th>Slug</th><th>Status</th><th>Actions</th></tr></thead>
            <tbody>
              ${cats.map(c => `
                <tr>
                  <td><strong>${Format.escapeHtml(c.name)}</strong></td>
                  <td class="text-muted">${Format.escapeHtml(c.slug)}</td>
                  <td>${c.is_active === false ? statusBadge("inactive") : statusBadge("active")}</td>
                  <td>
                    <button class="btn btn-ghost btn-sm" data-edit-cat="${c.id}">Edit</button>
                    <button class="btn btn-ghost btn-sm" data-del-cat="${c.id}" style="color:var(--nm-error)">Delete</button>
                  </td>
                </tr>`).join("")}
            </tbody>
          </table>
        </div>`;

      document.getElementById("add-cat").addEventListener("click", () => showCatForm(null, cats));
      document.querySelectorAll("[data-edit-cat]").forEach(b => {
        b.addEventListener("click", () => {
          const c = cats.find(x => x.id === b.dataset.editCat);
          if (c) showCatForm(c, cats);
        });
      });
      document.querySelectorAll("[data-del-cat]").forEach(b => b.addEventListener("click", async () => {
        if (!confirm("Delete this category?")) return;
        try { await API.del(`/categories/${b.dataset.delCat}`); toast("Category deleted"); tabs.categories(); }
        catch (e) { toast(e.message, "error"); }
      }));
    },

    async orders() {
      const res = await API.get("/admin/all?limit=50");
      const data = res.data || {};
      const orders = data.orders || [];
      content.innerHTML = `
        <h2 class="mb-4">All Orders</h2>
        <div class="table-wrap">
          <table class="data-table">
            <thead><tr><th>Order #</th><th>Date</th><th>Total</th><th>Sellers</th><th>Status</th><th>Actions</th></tr></thead>
            <tbody>
              ${orders.map(o => `
                <tr>
                  <td><strong>${Format.escapeHtml(o.order_number)}</strong></td>
                  <td>${Format.date(o.created_at)}</td>
                  <td>${Format.money(o.total, symbol)}</td>
                  <td>${o.seller_count || "—"}</td>
                  <td>${statusBadge(o.status)}</td>
                  <td>
                    <select class="sort-select" data-order-status="${o.id}" style="padding:4px 8px;font-size:var(--nm-text-xs)">
                      ${["pending","confirmed","processing","shipped","out_for_delivery","delivered","cancelled","returned","refunded"].map(s =>
                        `<option value="${s}" ${o.status === s ? "selected" : ""}>${s.replace(/_/g," ")}</option>`).join("")}
                    </select>
                  </td>
                </tr>`).join("")}
            </tbody>
          </table>
        </div>`;
      document.querySelectorAll("[data-order-status]").forEach(sel => sel.addEventListener("change", async () => {
        try { await API.post(`/orders/${sel.dataset.orderStatus}/status`, { status: sel.value }); toast("Order updated"); }
        catch (e) { toast(e.message, "error"); tabs.orders(); }
      }));
    },

    async commissions() {
      const res = await API.get("/admin/commissions?limit=50");
      const data = res.data || {};
      const comms = data.commissions || [];
      content.innerHTML = `
        <h2 class="mb-4">Commissions</h2>
        <div class="table-wrap">
          <table class="data-table">
            <thead><tr><th>Date</th><th>Store</th><th>Sale</th><th>Rate</th><th>Commission</th><th>Seller Earns</th><th>Status</th></tr></thead>
            <tbody>
              ${comms.map(c => `
                <tr>
                  <td>${Format.date(c.created_at)}</td>
                  <td>${Format.escapeHtml(c.store_name || "—")}</td>
                  <td>${Format.money(c.sale_amount, symbol)}</td>
                  <td>${c.commission_rate}%</td>
                  <td>${Format.money(c.commission_amount, symbol)}</td>
                  <td><strong>${Format.money(c.seller_earning, symbol)}</strong></td>
                  <td>${statusBadge(c.status)}</td>
                </tr>`).join("")}
            </tbody>
          </table>
        </div>`;
    },

    async settings() {
      const res = await API.get("/settings");
      const s = (res.data && res.data.settings) || {};
      content.innerHTML = `
        <h2 class="mb-4">Marketplace Settings</h2>
        <div class="card" style="padding:var(--nm-space-5);max-width:640px">
          <form id="settings-form">
            <div class="form-row">
              <div class="form-group"><label class="form-label">Marketplace Name</label><input name="marketplace_name" class="form-control" value="${Format.escapeHtml(s.marketplace_name || "")}"></div>
              <div class="form-group"><label class="form-label">Logo URL</label><input name="logo" class="form-control" value="${Format.escapeHtml(s.logo || "")}"></div>
            </div>
            <div class="form-row">
              <div class="form-group"><label class="form-label">Currency</label><input name="currency" class="form-control" value="${Format.escapeHtml(s.currency || "PKR")}"></div>
              <div class="form-group"><label class="form-label">Currency Symbol</label><input name="currency_symbol" class="form-control" value="${Format.escapeHtml(s.currency_symbol || "Rs.")}"></div>
            </div>
            <div class="form-row">
              <div class="form-group"><label class="form-label">Commission Rate (%)</label><input name="commission_rate" type="number" step="0.1" min="0" max="100" class="form-control" value="${s.commission_rate ?? 10}"></div>
              <div class="form-group"><label class="form-label">Free Delivery Above (0 = off)</label><input name="free_delivery_threshold" type="number" min="0" class="form-control" value="${s.free_delivery_threshold ?? 0}"></div>
            </div>
            <div class="form-row">
              <div class="form-group"><label class="form-label">Standard Delivery Fee</label><input name="delivery_standard" type="number" step="0.01" min="0" class="form-control" value="${s.delivery_standard ?? 20}"></div>
              <div class="form-group"><label class="form-label">Express Delivery Fee</label><input name="delivery_express" type="number" step="0.01" min="0" class="form-control" value="${s.delivery_express ?? 50}"></div>
            </div>
            <div class="form-row">
              <div class="form-group"><label class="form-label">Contact Email</label><input name="contact_email" type="email" class="form-control" value="${Format.escapeHtml(s.contact_email || "")}"></div>
              <div class="form-group"><label class="form-label">Contact Phone</label><input name="contact_phone" class="form-control" value="${Format.escapeHtml(s.contact_phone || "")}"></div>
            </div>
            <label class="form-check mb-4"><input type="checkbox" name="maintenance_mode" ${s.maintenance_mode ? "checked" : ""}> Maintenance mode (only admins can access)</label>
            <button type="submit" class="btn btn-primary">Save Settings</button>
          </form>
        </div>`;
      document.getElementById("settings-form").addEventListener("submit", async e => {
        e.preventDefault();
        const fd = new FormData(e.target);
        const body = {
          marketplace_name: fd.get("marketplace_name"), logo: fd.get("logo"),
          currency: fd.get("currency"), currency_symbol: fd.get("currency_symbol"),
          commission_rate: parseFloat(fd.get("commission_rate")),
          free_delivery_threshold: parseFloat(fd.get("free_delivery_threshold")),
          delivery_standard: parseFloat(fd.get("delivery_standard")),
          delivery_express: parseFloat(fd.get("delivery_express")),
          contact_email: fd.get("contact_email"), contact_phone: fd.get("contact_phone"),
          maintenance_mode: fd.has("maintenance_mode"),
        };
        try { await API.put("/settings", body); toast("Settings saved"); }
        catch (err) { toast(err.message, "error"); }
      });
    },

    async audit() {
      const res = await API.get("/admin/audit-logs?limit=100");
      const logs = (res.data && res.data.logs) || [];
      content.innerHTML = `
        <h2 class="mb-4">Audit Logs</h2>
        <div class="table-wrap">
          <table class="data-table">
            <thead><tr><th>Time</th><th>Action</th><th>Actor</th><th>Target</th><th>Details</th></tr></thead>
            <tbody>
              ${logs.map(l => `
                <tr>
                  <td>${Format.dateTime(l.created_at)}</td>
                  <td><code>${Format.escapeHtml(l.action)}</code></td>
                  <td>${Format.escapeHtml(l.actor_role || "—")}</td>
                  <td>${Format.escapeHtml(l.target_type || "—")} ${l.target_id ? l.target_id.slice(-6) : ""}</td>
                  <td class="text-xs text-muted">${Format.escapeHtml(JSON.stringify(l.details || {}))}</td>
                </tr>`).join("")}
            </tbody>
          </table>
        </div>`;
    },

    async security() {
      const user = Auth.user() || {};
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
          <p class="text-sm text-muted">Signed in as <strong>${Format.escapeHtml(user.email || "")}</strong></p>
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

  function showCatForm(cat, cats) {
    const wrap = document.getElementById("cat-form-wrap");
    wrap.classList.remove("hidden");
    wrap.innerHTML = `
      <div class="card" style="padding:var(--nm-space-5);max-width:480px">
        <h3 class="mb-4">${cat ? "Edit" : "Add"} Category</h3>
        <form id="cat-form">
          <div class="form-group"><label class="form-label">Name *</label><input name="name" class="form-control" required value="${Format.escapeHtml(cat?.name || "")}"></div>
          <div class="form-group"><label class="form-label">Description</label><input name="description" class="form-control" value="${Format.escapeHtml(cat?.description || "")}"></div>
          <div class="form-group"><label class="form-label">Parent Category</label>
            <select name="parent_id" class="form-select">
              <option value="">None</option>
              ${cats.filter(c => c.id !== cat?.id).map(c => `<option value="${c.id}" ${cat?.parent_id === c.id ? "selected" : ""}>${Format.escapeHtml(c.name)}</option>`).join("")}
            </select>
          </div>
          <label class="form-check mb-3"><input type="checkbox" name="is_active" ${cat?.is_active !== false ? "checked" : ""}> Active</label>
          <div class="flex gap-2">
            <button type="submit" class="btn btn-primary">Save</button>
            <button type="button" class="btn btn-ghost" id="cancel-cat">Cancel</button>
          </div>
        </form>
      </div>`;
    wrap.scrollIntoView({ behavior: "smooth" });
    document.getElementById("cancel-cat").addEventListener("click", () => wrap.classList.add("hidden"));
    document.getElementById("cat-form").addEventListener("submit", async e => {
      e.preventDefault();
      const fd = new FormData(e.target);
      const body = {
        name: fd.get("name"), description: fd.get("description"),
        parent_id: fd.get("parent_id") || null, is_active: fd.has("is_active"),
      };
      try {
        if (cat) await API.put(`/categories/${cat.id}`, body);
        else await API.post("/categories", body);
        toast("Category saved"); wrap.classList.add("hidden"); tabs.categories();
      } catch (err) { toast(err.message, "error"); }
    });
  }

  function switchTab(tab) {
    destroyCharts();
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

  (async function init() {
    await Auth.refresh();
    if (!Auth.isLoggedIn() || Auth.role() !== "admin") {
      content.innerHTML = `<div class="empty-state card" style="padding:var(--nm-space-12)">
        <i class="fas fa-lock"></i><h3>Admin Access Only</h3>
        <p>Please sign in with an admin account.</p>
        <a href="/login.html?redirect=/admin/index.html" class="btn btn-primary mt-4">Sign In</a></div>`;
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
