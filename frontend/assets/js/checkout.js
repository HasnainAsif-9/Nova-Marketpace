/* Checkout — multi-step: address → delivery → payment → confirm */
(function () {
  const $ = id => document.getElementById(id);
  let symbol = "Rs.";
  let addresses = [];
  let selectedAddress = null;
  let deliveryOption = "standard";
  let deliveryFee = 0;
  let cart = null;
  let step = 1;

  const steps = ["step-address", "step-delivery", "step-payment", "step-confirm"];

  function showStep(n) {
    step = n;
    steps.forEach((id, i) => $(id).classList.toggle("hidden", i + 1 !== n));
    document.querySelectorAll("#checkout-steps .step").forEach((el, i) => {
      el.classList.toggle("active", i + 1 === n);
      el.classList.toggle("done", i + 1 < n);
    });
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function addNavButtons(container, onNext, nextLabel = "Continue") {
    const div = document.createElement("div");
    div.className = "flex gap-2 mt-4";
    div.innerHTML = `<button type="button" class="btn btn-primary" id="step-next">${nextLabel}</button>
      ${step > 1 ? `<button type="button" class="btn btn-ghost" id="step-back">Back</button>` : ""}`;
    container.appendChild(div);
    $("step-next").addEventListener("click", onNext);
    const back = $("step-back");
    if (back) back.addEventListener("click", () => showStep(step - 1));
  }

  async function loadAddresses() {
    const res = await API.get("/buyers/addresses");
    addresses = (res.data && res.data.addresses) || [];
    const el = $("address-list");
    if (!addresses.length) {
      el.innerHTML = `<p class="text-muted mb-3">No saved addresses. Add one below to continue.</p>`;
    } else {
      el.innerHTML = addresses.map(a => `
        <label class="card mb-2" style="padding:var(--nm-space-3);display:flex;gap:var(--nm-space-3);cursor:pointer;${selectedAddress === a.id ? "border:2px solid var(--nm-primary)" : ""}">
          <input type="radio" name="addr" value="${a.id}" ${selectedAddress === a.id ? "checked" : ""}>
          <div>
            <strong>${Format.escapeHtml(a.label)}</strong> — ${Format.escapeHtml(a.recipient_name)}<br>
            <span class="text-sm text-muted">${Format.escapeHtml(a.address_line1)}${a.address_line2 ? ", " + Format.escapeHtml(a.address_line2) : ""}, ${Format.escapeHtml(a.city)} ${Format.escapeHtml(a.postal_code || "")} · ${Format.escapeHtml(a.phone)}</span>
            ${a.is_default ? `<span class="badge badge-primary" style="margin-left:6px">Default</span>` : ""}
          </div>
        </label>`).join("");
      el.querySelectorAll('input[name="addr"]').forEach(r => {
        r.addEventListener("change", () => { selectedAddress = r.value; });
      });
      if (!selectedAddress) selectedAddress = addresses.find(a => a.is_default)?.id || addresses[0].id;
    }
  }

  async function loadDeliveryOptions() {
    const res = await API.get("/orders/delivery-options");
    const options = (res.data && res.data.options) || [];
    const el = $("delivery-options");
    el.innerHTML = options.map(o => `
      <label class="card mb-2" style="padding:var(--nm-space-4);display:flex;align-items:center;gap:var(--nm-space-3);cursor:pointer;${deliveryOption === o.id ? "border:2px solid var(--nm-primary)" : ""}">
        <input type="radio" name="delivery" value="${o.id}" ${deliveryOption === o.id ? "checked" : ""}>
        <i class="fas ${o.id === "express" ? "fa-bolt" : "fa-truck"}" style="font-size:1.3rem;color:var(--nm-primary)"></i>
        <div style="flex:1">
          <strong>${Format.escapeHtml(o.name)}</strong> <span class="text-sm text-muted">(${o.days} days)</span>
          <div class="text-sm">${Format.money(o.fee, symbol)}</div>
        </div>
      </label>`).join("");
    el.querySelectorAll('input[name="delivery"]').forEach(r => {
      r.addEventListener("change", () => { deliveryOption = r.value; updateSummary(); });
    });
  }

  function updateSummary() {
    if (!cart) return;
    const subtotal = cart.subtotal || 0;
    // Estimate delivery fee client-side for display; server recalculates at order time
    const opts = { standard: 20, express: 50 };
    deliveryFee = opts[deliveryOption] || 20;
    $("sum-subtotal").textContent = Format.money(subtotal, symbol);
    $("sum-delivery").textContent = Format.money(deliveryFee, symbol);
    $("sum-total").textContent = Format.money(subtotal + deliveryFee, symbol);
  }

  function renderSummaryItems() {
    const el = $("summary-items");
    const items = (cart && cart.items) || [];
    el.innerHTML = items.map(i => {
      const p = i.product || {};
      const img = (p.images && p.images[0]) || "/assets/images/placeholder.svg";
      return `<div class="flex gap-3 mb-3 items-center">
        <img src="${Format.escapeHtml(img)}" alt="" loading="lazy" style="width:48px;height:48px;border-radius:8px;object-fit:cover">
        <div style="flex:1;font-size:var(--nm-text-sm)">
          <div style="font-weight:600">${Format.escapeHtml(p.name || "Product")}</div>
          <div class="text-muted">Qty: ${i.quantity}</div>
        </div>
        <div style="font-weight:600">${Format.money(i.line_total, symbol)}</div>
      </div>`;
    }).join("");
  }

  function renderReview() {
    const addr = addresses.find(a => a.id === selectedAddress);
    const items = (cart && cart.items) || [];
    $("order-review").innerHTML = `
      <div class="card" style="padding:var(--nm-space-4);margin-bottom:var(--nm-space-3)">
        <h4 class="mb-2">Deliver to</h4>
        <p style="margin:0">${addr ? `${Format.escapeHtml(addr.recipient_name)} — ${Format.escapeHtml(addr.address_line1)}, ${Format.escapeHtml(addr.city)} · ${Format.escapeHtml(addr.phone)}` : "No address"}</p>
      </div>
      <div class="card" style="padding:var(--nm-space-4);margin-bottom:var(--nm-space-3)">
        <h4 class="mb-2">Items (${items.length})</h4>
        ${items.map(i => `<div class="summary-row"><span>${Format.escapeHtml((i.product || {}).name || "Product")} × ${i.quantity}</span><span>${Format.money(i.line_total, symbol)}</span></div>`).join("")}
      </div>
      <div class="card" style="padding:var(--nm-space-4)">
        <div class="summary-row"><span>Delivery</span><span>${deliveryOption === "express" ? "Express" : "Standard"}</span></div>
        <div class="summary-row"><span>Payment</span><span>Cash on Delivery</span></div>
      </div>`;
  }

  async function placeOrder() {
    const btn = $("place-order-btn");
    btn.disabled = true;
    btn.innerHTML = `<span class="spinner" style="width:20px;height:20px;border-width:2px;margin:0"></span> Placing order...`;
    try {
      const res = await API.post("/orders/checkout", {
        address_id: selectedAddress,
        delivery_option: deliveryOption,
        payment_method: "cod",
        notes: $("order-notes").value,
      });
      const order = res.data && res.data.order;
      toast("Order placed successfully!");
      setTimeout(() => {
        window.location.href = `/buyer/index.html#orders`;
      }, 800);
    } catch (e) {
      toast(e.message || "Order failed", "error");
      btn.disabled = false;
      btn.innerHTML = `<i class="fas fa-check"></i> Place Order`;
    }
  }

  async function init() {
    if (!Auth.isLoggedIn()) {
      Auth.loginRedirect("/checkout.html");
      return;
    }
    if (Auth.role() !== "buyer") {
      toast("Only buyer accounts can checkout", "error");
      window.location.href = "/";
      return;
    }

    API.get("/settings").then(r => {
      if (r.data && r.data.settings && r.data.settings.currency_symbol) symbol = r.data.settings.currency_symbol;
    }).catch(() => {});

    try {
      const res = await API.get("/cart");
      cart = res.data;
      if (!cart || !cart.items || !cart.items.length) {
        document.querySelector("main .grid").innerHTML = `<div class="empty-state card" style="grid-column:1/-1;padding:var(--nm-space-12)">
          <i class="fas fa-shopping-cart"></i><h3>Your cart is empty</h3>
          <a href="/shop.html" class="btn btn-primary mt-4">Start Shopping</a></div>`;
        return;
      }
    } catch (e) {
      toast(e.message, "error");
      return;
    }

    renderSummaryItems();
    updateSummary();

    await loadAddresses();
    await loadDeliveryOptions();

    // Step 1 → 2
    addNavButtons($("step-address"), async () => {
      if (!selectedAddress) { toast("Please select or add a shipping address", "warning"); return; }
      showStep(2);
      addNavButtons($("step-delivery"), () => { showStep(3); addNavButtons($("step-payment"), () => { renderReview(); showStep(4); addNavButtons($("step-confirm"), placeOrder, "Place Order"); }, "Review Order"); }, "Continue to Payment");
    }, "Continue to Delivery");

    $("new-address-form").addEventListener("submit", async e => {
      e.preventDefault();
      const fd = new FormData(e.target);
      const body = Object.fromEntries(fd.entries());
      body.is_default = fd.has("is_default");
      try {
        const res = await API.post("/buyers/addresses", body);
        toast("Address saved");
        e.target.reset();
        await loadAddresses();
        selectedAddress = res.data.address.id;
      } catch (err) { toast(err.message, "error"); }
    });

    $("place-order-btn").addEventListener("click", placeOrder);
  }

  init();
})();
