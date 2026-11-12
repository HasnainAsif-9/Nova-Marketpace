/* Public seller store page */
(function () {
  const params = new URLSearchParams(window.location.search);
  const ref = params.get("slug") || params.get("id") || "";
  const root = document.getElementById("store-root");
  let symbol = "Rs.";

  async function init() {
    if (!ref) { root.innerHTML = `<div class="empty-state"><h3>Store not found</h3></div>`; return; }
    try {
      const res = await API.get(`/sellers/${encodeURIComponent(ref)}`);
      const s = res.data.seller;
      document.title = `${s.store_name} — NovaMarket`;
      const ogTitle = document.querySelector('meta[property="og:title"]');
      if (ogTitle) ogTitle.content = `${s.store_name} — NovaMarket`;
      const ogDesc = document.querySelector('meta[property="og:description"]');
      if (ogDesc) ogDesc.content = (s.description || `Shop from ${s.store_name} on NovaMarket`).slice(0, 200);
      root.innerHTML = `
        <div class="card mb-6" style="padding:var(--nm-space-6)">
          <div class="flex items-center gap-4 wrap">
            <div style="width:72px;height:72px;border-radius:18px;background:var(--nm-primary);color:#fff;display:flex;align-items:center;justify-content:center;font-size:1.8rem;font-weight:700">
              ${(s.store_name || "S")[0].toUpperCase()}
            </div>
            <div style="flex:1;min-width:200px">
              <h1 style="margin-bottom:4px">${Format.escapeHtml(s.store_name)}</h1>
              <p class="text-muted" style="margin:0">${Format.escapeHtml(s.description || "Trusted seller on NovaMarket")}</p>
              <div class="text-sm text-muted mt-2">
                ${s.city ? `📍 ${Format.escapeHtml(s.city)} · ` : ""}${s.product_count || 0} products
              </div>
            </div>
            ${s.contact_phone ? `<a href="tel:${Format.escapeHtml(s.contact_phone)}" class="btn btn-outline btn-sm"><i class="fas fa-phone"></i> Contact</a>` : ""}
          </div>
        </div>
        <h2 class="mb-4">Products by ${Format.escapeHtml(s.store_name)}</h2>
        <div class="grid grid-4" id="store-products"><div class="spinner"></div></div>`;

      const pres = await API.get(`/sellers/${encodeURIComponent(ref)}/products?limit=48`);
      const products = (pres.data && pres.data.products) || [];
      const grid = document.getElementById("store-products");
      grid.innerHTML = products.length
        ? products.map(p => productCardHtml(p, symbol)).join("")
        : `<div class="empty-state" style="grid-column:1/-1"><i class="fas fa-box-open"></i><p>No products listed yet.</p></div>`;
      bindProductCardActions(grid);
    } catch (e) {
      root.innerHTML = `<div class="empty-state"><i class="fas fa-store-slash"></i><h3>Store not found</h3><a href="/shop.html" class="btn btn-primary mt-4">Browse marketplace</a></div>`;
    }
  }

  API.get("/settings").then(r => {
    if (r.data && r.data.settings && r.data.settings.currency_symbol) symbol = r.data.settings.currency_symbol;
  }).catch(() => {}).finally(init);
})();
