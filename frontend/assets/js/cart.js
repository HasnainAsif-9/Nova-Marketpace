/* Cart page */
(function () {
  const itemsEl = document.getElementById("cart-items");
  const emptyEl = document.getElementById("cart-empty");
  const layout = document.getElementById("cart-layout");
  let symbol = "Rs.";

  async function loadCart() {
    if (!Auth.isLoggedIn()) {
      itemsEl.innerHTML = `<div class="empty-state card" style="padding:var(--nm-space-10)">
        <i class="fas fa-lock"></i><h3>Login Required</h3>
        <p>Please log in to view your cart.</p>
        <a href="/login.html?redirect=/cart.html" class="btn btn-primary mt-4">Login</a>
        <a href="/register.html" class="btn btn-outline mt-4" style="margin-left:8px">Create Account</a>
      </div>`;
      layout.querySelector("aside").style.display = "none";
      return;
    }
    try {
      const res = await API.get("/cart");
      const data = res.data || { items: [], subtotal: 0 };
      render(data);
    } catch (e) {
      itemsEl.innerHTML = `<div class="empty-state"><i class="fas fa-exclamation-circle"></i><p>${Format.escapeHtml(e.message)}</p></div>`;
    }
  }

  function render(data) {
    const items = data.items || [];
    if (!items.length) {
      itemsEl.innerHTML = "";
      emptyEl.classList.remove("hidden");
      layout.querySelector("aside").style.display = "none";
      return;
    }
    emptyEl.classList.add("hidden");
    layout.querySelector("aside").style.display = "";

    itemsEl.innerHTML = items.map(item => {
      const p = item.product;
      if (!p) return "";
      const img = (p.images && p.images[0]) || "/assets/images/placeholder.svg";
      const unavailable = !item.available;
      return `
      <div class="cart-item card" style="padding:var(--nm-space-4);margin-bottom:var(--nm-space-3)">
        <a href="/product.html?id=${p.id}"><img class="cart-item-img" src="${Format.escapeHtml(img)}" alt="${Format.escapeHtml(p.name)}" loading="lazy"></a>
        <div>
          <a href="/product.html?id=${p.id}" style="font-weight:600;color:var(--nm-text)">${Format.escapeHtml(p.name)}</a>
          <div class="text-sm text-muted mt-1">${Format.money(p.price, symbol)} each</div>
          ${unavailable ? `<div class="mt-1"><span class="badge badge-error">Unavailable</span></div>` : ""}
        </div>
        <div class="qty-control">
          <button data-qty="-1" data-id="${p.id}" aria-label="Decrease">−</button>
          <input type="number" value="${item.quantity}" min="0" max="${Math.min(p.stock, 100)}" data-id="${p.id}" aria-label="Quantity" style="width:50px">
          <button data-qty="1" data-id="${p.id}" aria-label="Increase">+</button>
        </div>
        <div style="text-align:right">
          <div style="font-weight:700">${Format.money(item.line_total, symbol)}</div>
          <button class="btn btn-ghost btn-sm text-sm" data-remove="${p.id}" style="color:var(--nm-error)"><i class="fas fa-trash"></i> Remove</button>
        </div>
      </div>`;
    }).join("");

    document.getElementById("cart-subtotal").textContent = Format.money(data.subtotal, symbol);
    document.getElementById("cart-total").textContent = Format.money(data.subtotal, symbol);

    // Bind qty controls
    itemsEl.querySelectorAll("[data-qty]").forEach(btn => {
      btn.addEventListener("click", async () => {
        const id = btn.dataset.id;
        const input = itemsEl.querySelector(`input[data-id="${id}"]`);
        const current = parseInt(input.value, 10) || 1;
        const delta = parseInt(btn.dataset.qty, 10);
        const product = items.find(i => i.product && i.product.id === id);
        const max = product ? Math.min(product.product.stock, 100) : 100;
        const newQty = Math.min(max, Math.max(0, current + delta));
        await updateQty(id, newQty);
      });
    });
    itemsEl.querySelectorAll("input[data-id]").forEach(input => {
      input.addEventListener("change", () => updateQty(input.dataset.id, parseInt(input.value, 10) || 0));
    });
    itemsEl.querySelectorAll("[data-remove]").forEach(btn => {
      btn.addEventListener("click", () => removeItem(btn.dataset.remove));
    });
  }

  async function updateQty(id, qty) {
    try {
      const res = await API.put(`/cart/items/${id}`, { quantity: qty });
      render(res.data);
      updateBadge(res.data.item_count);
    } catch (e) { toast(e.message, "error"); }
  }

  async function removeItem(id) {
    try {
      const res = await API.del(`/cart/items/${id}`);
      render(res.data);
      updateBadge(res.data.item_count);
      toast("Item removed");
    } catch (e) { toast(e.message, "error"); }
  }

  function updateBadge(count) {
    const badge = document.getElementById("cart-badge");
    if (badge) { badge.textContent = count; badge.classList.toggle("hidden", !count); }
  }

  document.getElementById("checkout-btn").addEventListener("click", e => {
    if (!Auth.isLoggedIn()) { e.preventDefault(); Auth.loginRedirect("/checkout.html"); }
  });

  API.get("/settings").then(r => {
    if (r.data && r.data.settings && r.data.settings.currency_symbol) symbol = r.data.settings.currency_symbol;
    loadCart();
  }).catch(loadCart);
})();
