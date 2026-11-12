/* Seller dashboard */
(function () {
  const content = document.getElementById("dash-content");
  const sidebar = document.getElementById("dash-sidebar");
  let symbol = "Rs.";
  let seller = null;
  let categories = [];

  const statusBadge = s => {
    const map = { pending: "badge-warning", confirmed: "badge-info", processing: "badge-info",
      shipped: "badge-primary", out_for_delivery: "badge-primary", delivered: "badge-success",
      cancelled: "badge-error", returned: "badge-error", refunded: "badge-muted",
      active: "badge-success", inactive: "badge-muted", approved: "badge-success",
      rejected: "badge-error", suspended: "badge-error", draft: "badge-muted", out_of_stock: "badge-warning" };
    return `<span class="badge ${map[s] || "badge-muted"}">${String(s).replace(/_/g, " ")}</span>`;
  };

  const tabs = {
    async overview() {
      const [earnRes, prodRes, ordRes] = await Promise.all([
        API.get("/sellers/me/earnings"),
        API.get("/products/seller/mine?limit=5"),
        API.get("/orders/seller/mine?limit=5"),
      ]);
      const e = (earnRes.data && earnRes.data.earnings) || {};
      const products = (prodRes.data && prodRes.data.products) || [];
      const orders = (ordRes.data && ordRes.data.orders) || [];
      const pendingOrders = orders.filter(o => o.status === "pending").length;

      content.innerHTML = `
        <h2 class="mb-4">Seller Dashboard</h2>
        ${seller && seller.status !== "approved" ? `
          <div class="card mb-4" style="padding:var(--nm-space-4);border-left:4px solid var(--nm-warning)">
            <strong>Account status: ${statusBadge(seller.status)}</strong>
            ${seller.status_reason ? `<p class="text-sm text-muted mt-1" style="margin-bottom:0">${Format.escapeHtml(seller.status_reason)}</p>` : ""}
            ${seller.status === "pending" ? `<p class="text-sm text-muted mt-1" style="margin-bottom:0">Your seller application is pending admin approval. You can prepare your store meanwhile.</p>` : ""}
          </div>` : ""}
        <div class="stat-grid">
          <div class="stat-card"><div class="stat-label">Total Sales</div><div class="stat-value">${Format.money(e.total_sales || 0, symbol)}</div></div>
          <div class="stat-card"><div class="stat-label">Commission Paid</div><div class="stat-value">${Format.money(e.total_commission || 0, symbol)}</div></div>
          <div class="stat-card"><div class="stat-label">Net Earnings</div><div class="stat-value">${Format.money(e.total_earnings || 0, symbol)}</div></div>
          <div class="stat-card"><div class="stat-label">Pending Orders</div><div class="stat-value">${pendingOrders}</div></div>
        </div>
        <div class="grid grid-2">
          <div class="card" style="padding:var(--nm-space-5)">
            <div class="flex justify-between items-center mb-4"><h3 style="margin:0">Recent Orders</h3><a href="#orders" class="text-sm">View all →</a></div>
            ${orders.length ? orders.map(o => `
              <div class="flex justify-between items-center" style="padding:var(--nm-space-2) 0;border-bottom:1px solid var(--nm-border)">
                <div><strong>${Format.escapeHtml(o.order_number)}</strong><div class="text-sm text-muted">${Format.date(o.created_at)}</div></div>
                <div class="flex items-center gap-2">${statusBadge(o.status)}<strong>${Format.money(o.seller_earning || 0, symbol)}</strong></div>
              </div>`).join("") : `<p class="text-muted">No orders yet.</p>`}
          </div>
          <div class="card" style="padding:var(--nm-space-5)">
            <div class="flex justify-between items-center mb-4"><h3 style="margin:0">Recent Products</h3><a href="#products" class="text-sm">Manage →</a></div>
            ${products.length ? products.map(p => `
              <div class="flex justify-between items-center" style="padding:var(--nm-space-2) 0;border-bottom:1px solid var(--nm-border)">
                <div><strong>${Format.escapeHtml(p.name)}</strong><div class="text-sm text-muted">Stock: ${p.stock} · ${Format.money(p.price, symbol)}</div></div>
                ${statusBadge(p.status)}
              </div>`).join("") : `<p class="text-muted">No products yet. <a href="#products">Add your first product →</a></p>`}
          </div>
        </div>`;
    },

    async store() {
      const res = await API.get("/sellers/me");
      seller = res.data.seller;
      content.innerHTML = `
        <h2 class="mb-4">My Store</h2>
        <div class="card" style="padding:var(--nm-space-5);max-width:640px">
          <form id="store-form">
            <div class="form-group"><label class="form-label">Store Name</label><input name="store_name" class="form-control" value="${Format.escapeHtml(seller.store_name || "")}"></div>
            <div class="form-group"><label class="form-label">Store Slug (URL)</label><input name="store_slug" class="form-control" value="${Format.escapeHtml(seller.store_slug || "")}" placeholder="your-store-name"></div>
            <div class="form-group"><label class="form-label">Description</label><textarea name="description" class="form-textarea">${Format.escapeHtml(seller.description || "")}</textarea></div>
            <div class="form-row">
              <div class="form-group"><label class="form-label">Contact Email</label><input name="contact_email" type="email" class="form-control" value="${Format.escapeHtml(seller.contact_email || "")}"></div>
              <div class="form-group"><label class="form-label">Contact Phone</label><input name="contact_phone" class="form-control" value="${Format.escapeHtml(seller.contact_phone || "")}"></div>
            </div>
            <div class="form-group"><label class="form-label">Address</label><input name="address" class="form-control" value="${Format.escapeHtml(seller.address || "")}"></div>
            <div class="form-group"><label class="form-label">City</label><input name="city" class="form-control" value="${Format.escapeHtml(seller.city || "")}"></div>
            <button type="submit" class="btn btn-primary">Save Store</button>
            <a href="/seller-store.html?slug=${seller.store_slug || seller.id}" target="_blank" class="btn btn-outline" style="margin-left:8px">View Public Store ↗</a>
          </form>
        </div>`;
      document.getElementById("store-form").addEventListener("submit", async e => {
        e.preventDefault();
        const fd = new FormData(e.target);
        const body = Object.fromEntries(fd.entries());
        try { await API.put("/sellers/me", body); toast("Store updated"); Auth.refresh(); }
        catch (err) { toast(err.message, "error"); }
      });
    },

    async products() {
      const res = await API.get("/products/seller/mine?limit=50");
      const data = res.data || {};
      const products = data.products || [];
      content.innerHTML = `
        <div class="flex justify-between items-center mb-4 wrap gap-2">
          <h2 style="margin:0">Products</h2>
          <button class="btn btn-primary" id="add-product-btn"><i class="fas fa-plus"></i> Add Product</button>
        </div>
        <div id="product-form-wrap" class="hidden mb-4"></div>
        <div class="table-wrap">
          <table class="data-table">
            <thead><tr><th>Product</th><th>Price</th><th>Stock</th><th>Status</th><th>Sales</th><th>Actions</th></tr></thead>
            <tbody>
              ${products.length ? products.map(p => `
                <tr>
                  <td><strong>${Format.escapeHtml(p.name)}</strong><div class="text-xs text-muted">${Format.escapeHtml(p.sku || "")}</div></td>
                  <td>${Format.money(p.price, symbol)}</td>
                  <td>${p.stock}</td>
                  <td>${statusBadge(p.status)}</td>
                  <td>${p.sold_count || 0}</td>
                  <td>
                    <button class="btn btn-ghost btn-sm" data-edit="${p.id}">Edit</button>
                    <button class="btn btn-ghost btn-sm" data-stock="${p.id}">Stock</button>
                    <button class="btn btn-ghost btn-sm" data-toggle="${p.id}" data-status="${p.status === "active" ? "inactive" : "active"}">${p.status === "active" ? "Deactivate" : "Activate"}</button>
                  </td>
                </tr>`).join("") : `<tr><td colspan="6" class="text-center text-muted" style="padding:var(--nm-space-8)">No products yet. Click "Add Product" to create one.</td></tr>`}
            </tbody>
          </table>
        </div>`;

      document.getElementById("add-product-btn").addEventListener("click", () => showProductForm(null));
      document.querySelectorAll("[data-edit]").forEach(b => b.addEventListener("click", () => {
        const p = products.find(x => x.id === b.dataset.edit);
        if (p) showProductForm(p);
      }));
      document.querySelectorAll("[data-stock]").forEach(b => b.addEventListener("click", async () => {
        const delta = prompt("Stock adjustment (positive to add, negative to remove):", "0");
        if (delta === null) return;
        try { await API.post(`/products/${b.dataset.stock}/stock`, { delta: parseInt(delta, 10) || 0 }); toast("Stock updated"); tabs.products(); }
        catch (e) { toast(e.message, "error"); }
      }));
      document.querySelectorAll("[data-toggle]").forEach(b => b.addEventListener("click", async () => {
        // Sellers can only toggle active/inactive via update; use status endpoint not available — use product update
        try {
          await API.put(`/products/${b.dataset.toggle}`, {});
          toast("Product updated"); tabs.products();
        } catch (e) { toast(e.message, "error"); }
      }));
    },

    async orders() {
      const res = await API.get("/orders/seller/mine?limit=30");
      const data = res.data || {};
      const orders = data.orders || [];
      content.innerHTML = `
        <h2 class="mb-4">Orders</h2>
        ${orders.length ? orders.map(o => `
          <div class="card mb-3" style="padding:var(--nm-space-4)">
            <div class="flex justify-between items-center wrap gap-2 mb-2">
              <div><strong>${Format.escapeHtml(o.order_number)}</strong><div class="text-sm text-muted">${Format.dateTime(o.created_at)} · Buyer: ${Format.escapeHtml(o.buyer_name || "Customer")}</div></div>
              <div class="flex items-center gap-3">${statusBadge(o.status)}<strong>${Format.money(o.seller_earning || 0, symbol)}</strong></div>
            </div>
            <div class="text-sm mb-3">
              ${(o.items || []).map(i => `${Format.escapeHtml(i.product_name)} × ${i.quantity}`).join(", ")}
            </div>
            <div class="flex gap-2 items-center">
              <span class="text-sm text-muted">Subtotal: ${Format.money(o.subtotal, symbol)} · Commission: ${Format.money(o.commission_amount, symbol)} (${o.commission_rate}%)</span>
              <span style="flex:1"></span>
              ${nextStatuses(o.status).map(s => `<button class="btn btn-primary btn-sm" data-status="${s}" data-order="${o.parent_order_id}">${s.replace(/_/g, " ")}</button>`).join("")}
            </div>
          </div>`).join("") : `<div class="empty-state card"><i class="fas fa-shopping-bag"></i><h3>No orders yet</h3></div>`}`;

      document.querySelectorAll("[data-status]").forEach(b => b.addEventListener("click", async () => {
        try {
          await API.post(`/orders/${b.dataset.order}/status`, { status: b.dataset.status });
          toast(`Order marked as ${b.dataset.status.replace(/_/g, " ")}`);
          tabs.orders();
        } catch (e) { toast(e.message, "error"); }
      }));
    },

    async earnings() {
      const [earnRes, commRes] = await Promise.all([
        API.get("/sellers/me/earnings"),
        API.get("/commissions/mine?limit=30"),
      ]);
      const e = (earnRes.data && earnRes.data.earnings) || {};
      const comms = (commRes.data && commRes.data.commissions) || [];
      content.innerHTML = `
        <h2 class="mb-4">Earnings & Commission</h2>
        <div class="stat-grid">
          <div class="stat-card"><div class="stat-label">Gross Sales</div><div class="stat-value">${Format.money(e.total_sales || 0, symbol)}</div></div>
          <div class="stat-card"><div class="stat-label">Commission Paid</div><div class="stat-value">${Format.money(e.total_commission || 0, symbol)}</div></div>
          <div class="stat-card"><div class="stat-label">Net Earnings</div><div class="stat-value">${Format.money(e.total_earnings || 0, symbol)}</div></div>
          <div class="stat-card"><div class="stat-label">Pending Payout</div><div class="stat-value">${Format.money(e.pending_earnings || 0, symbol)}</div></div>
        </div>
        <div class="card">
          <div class="table-wrap" style="border:none">
            <table class="data-table">
              <thead><tr><th>Date</th><th>Sale Amount</th><th>Commission</th><th>Your Earnings</th><th>Status</th></tr></thead>
              <tbody>
                ${comms.length ? comms.map(c => `
                  <tr>
                    <td>${Format.date(c.created_at)}</td>
                    <td>${Format.money(c.sale_amount, symbol)}</td>
                    <td>${Format.money(c.commission_amount, symbol)} (${c.commission_rate}%)</td>
                    <td><strong>${Format.money(c.seller_earning, symbol)}</strong></td>
                    <td>${statusBadge(c.status)}</td>
                  </tr>`).join("") : `<tr><td colspan="5" class="text-center text-muted" style="padding:var(--nm-space-6)">No commission records yet.</td></tr>`}
              </tbody>
            </table>
          </div>
        </div>`;
    },

    async notifications() {
      const res = await API.get("/notifications?limit=50");
      const notes = (res.data && res.data.notifications) || [];
      content.innerHTML = `
        <h2 class="mb-4">Notifications</h2>
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
          <button class="btn btn-outline btn-sm" id="logout-btn">Sign Out</button>
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

  function nextStatuses(current) {
    const flow = ["pending", "confirmed", "processing", "shipped", "out_for_delivery"];
    const idx = flow.indexOf(current);
    if (idx === -1) return [];
    return [flow[idx + 1]].filter(Boolean);
  }

  function showProductForm(product) {
    const wrap = document.getElementById("product-form-wrap");
    const isEdit = !!product;
    wrap.classList.remove("hidden");
    wrap.innerHTML = `
      <div class="card" style="padding:var(--nm-space-5)">
        <h3 class="mb-4">${isEdit ? "Edit Product" : "Add New Product"}</h3>
        <form id="product-form">
          <div class="form-group"><label class="form-label">Product Name *</label><input name="name" class="form-control" required value="${Format.escapeHtml(product?.name || "")}"></div>
          <div class="form-row">
            <div class="form-group"><label class="form-label">Price (Rs.) *</label><input name="price" type="number" step="0.01" min="0" class="form-control" required value="${product?.price || ""}"></div>
            <div class="form-group"><label class="form-label">Compare Price (optional)</label><input name="compare_price" type="number" step="0.01" min="0" class="form-control" value="${product?.compare_price || ""}"></div>
          </div>
          <div class="form-row">
            <div class="form-group"><label class="form-label">Stock</label><input name="stock" type="number" min="0" class="form-control" value="${product?.stock ?? 0}"></div>
            <div class="form-group"><label class="form-label">Category *</label>
              <select name="category_id" class="form-select" required>
                <option value="">Select category</option>
                ${categories.map(c => `<option value="${c.id}" ${product?.category_id === c.id ? "selected" : ""}>${Format.escapeHtml(c.name)}</option>`).join("")}
              </select>
            </div>
          </div>
          <div class="form-row">
            <div class="form-group"><label class="form-label">Brand</label><input name="brand" class="form-control" value="${Format.escapeHtml(product?.brand || "")}"></div>
            <div class="form-group"><label class="form-label">SKU</label><input name="sku" class="form-control" value="${Format.escapeHtml(product?.sku || "")}"></div>
          </div>
          <div class="form-group"><label class="form-label">Short Description</label><input name="short_description" class="form-control" value="${Format.escapeHtml(product?.short_description || "")}"></div>
          <div class="form-group"><label class="form-label">Description</label><textarea name="description" class="form-textarea">${Format.escapeHtml(product?.description || "")}</textarea></div>
          <div class="form-group"><label class="form-label">Image URLs (one per line)</label><textarea name="images" class="form-textarea" style="min-height:80px" placeholder="https://...">${(product?.images || []).join("\n")}</textarea></div>
          <div class="flex gap-2">
            <button type="submit" class="btn btn-primary">${isEdit ? "Update Product" : "Create Product"}</button>
            <button type="button" class="btn btn-ghost" id="cancel-product-form">Cancel</button>
          </div>
        </form>
      </div>`;
    wrap.scrollIntoView({ behavior: "smooth" });
    document.getElementById("cancel-product-form").addEventListener("click", () => wrap.classList.add("hidden"));
    document.getElementById("product-form").addEventListener("submit", async e => {
      e.preventDefault();
      const fd = new FormData(e.target);
      const body = {
        name: fd.get("name"), price: parseFloat(fd.get("price")),
        compare_price: parseFloat(fd.get("compare_price")) || 0,
        stock: parseInt(fd.get("stock"), 10) || 0,
        category_id: fd.get("category_id"), brand: fd.get("brand"),
        sku: fd.get("sku"), short_description: fd.get("short_description"),
        description: fd.get("description"),
        images: fd.get("images").split("\n").map(s => s.trim()).filter(Boolean),
      };
      try {
        if (isEdit) await API.put(`/products/${product.id}`, body);
        else await API.post("/products", body);
        toast(isEdit ? "Product updated" : "Product created");
        wrap.classList.add("hidden");
        tabs.products();
      } catch (err) { toast(err.message, "error"); }
    });
  }

  function switchTab(tab) {
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
    if (!Auth.isLoggedIn() || Auth.role() !== "seller") {
      content.innerHTML = `<div class="empty-state card" style="padding:var(--nm-space-12)">
        <i class="fas fa-lock"></i><h3>Seller Access Only</h3>
        <p>Please sign in with a seller account.</p>
        <a href="/login.html?redirect=/seller/index.html" class="btn btn-primary mt-4">Sign In</a></div>`;
      sidebar.style.display = "none";
      return;
    }
    API.get("/settings").then(r => {
      if (r.data && r.data.settings && r.data.settings.currency_symbol) symbol = r.data.settings.currency_symbol;
    }).catch(() => {});
    try {
      const res = await API.get("/categories");
      categories = (res.data && res.data.categories) || [];
    } catch (e) {}
    try {
      const sres = await API.get("/sellers/me");
      seller = sres.data.seller;
    } catch (e) {}
    const tab = location.hash.replace("#", "") || "overview";
    switchTab(tabs[tab] ? tab : "overview");
  })();
})();
