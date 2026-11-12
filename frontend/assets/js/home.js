/* Homepage logic */
(async function () {
  let symbol = "Rs.";
  API.get("/settings").then(r => {
    if (r.data && r.data.settings && r.data.settings.currency_symbol) {
      symbol = r.data.settings.currency_symbol;
    }
  }).catch(() => {});

  // Categories
  try {
    const res = await API.get("/categories?limit=50");
    const cats = (res.data && res.data.categories) || [];
    const el = document.getElementById("home-categories");
    el.innerHTML = cats.slice(0, 8).map(c => `
      <a href="/shop.html?category_id=${c.id}" class="card card-hover" style="padding:var(--nm-space-5);text-align:center;display:flex;flex-direction:column;align-items:center;gap:var(--nm-space-2);color:var(--nm-text)">
        <div style="width:52px;height:52px;border-radius:14px;background:var(--nm-primary-light);color:var(--nm-primary);display:flex;align-items:center;justify-content:center;font-size:1.4rem">
          <i class="fas fa-tag"></i>
        </div>
        <span style="font-weight:600;font-size:var(--nm-text-sm)">${Format.escapeHtml(c.name)}</span>
      </a>`).join("") || `<p class="text-muted">No categories yet.</p>`;
  } catch (e) { /* ignore */ }

  // Deals (products with compare_price > price)
  try {
    const res = await API.get("/products?on_sale=1&limit=8");
    const products = (res.data && res.data.products) || [];
    const el = document.getElementById("home-deals");
    el.innerHTML = products.length
      ? products.map(p => productCardHtml(p, symbol)).join("")
      : `<div class="empty-state" style="grid-column:1/-1"><i class="fas fa-tag"></i>No deals right now — check back soon!</div>`;
    bindProductCardActions(el);
  } catch (e) { /* ignore */ }

  // New arrivals
  try {
    const res = await API.get("/products?sort=newest&limit=8");
    const products = (res.data && res.data.products) || [];
    const el = document.getElementById("home-new");
    el.innerHTML = products.length
      ? products.map(p => productCardHtml(p, symbol)).join("")
      : `<div class="empty-state" style="grid-column:1/-1"><i class="fas fa-box-open"></i>No products yet.</div>`;
    bindProductCardActions(el);
  } catch (e) { /* ignore */ }

  // Top sellers
  try {
    const res = await API.get("/sellers?limit=8");
    const sellers = (res.data && res.data.sellers) || [];
    const el = document.getElementById("home-sellers");
    el.innerHTML = sellers.length
      ? sellers.map(s => `
        <a href="/seller-store.html?slug=${s.store_slug || s.id}" class="card card-hover" style="padding:var(--nm-space-4);display:flex;align-items:center;gap:var(--nm-space-3);color:var(--nm-text)">
          <div style="width:48px;height:48px;border-radius:12px;background:var(--nm-primary);color:#fff;display:flex;align-items:center;justify-content:center;font-weight:700;font-size:1.1rem">
            ${(s.store_name || "S")[0].toUpperCase()}
          </div>
          <div>
            <div style="font-weight:600;font-size:var(--nm-text-sm)">${Format.escapeHtml(s.store_name)}</div>
            <div class="text-xs text-muted">${s.product_count || 0} products</div>
          </div>
        </a>`).join("")
      : `<p class="text-muted">No sellers yet.</p>`;
  } catch (e) { /* ignore */ }

  // Newsletter (frontend-only subscription notice — stores nothing server-side yet)
  const form = document.getElementById("newsletter-form");
  if (form) {
    form.addEventListener("submit", e => {
      e.preventDefault();
      toast("Thanks for subscribing! We'll keep you posted.");
      form.reset();
    });
  }
})();
