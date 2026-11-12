/* Shared product card renderer */
function productCardHtml(p, symbol = "Rs.") {
  const img = (p.images && p.images[0]) || "/assets/images/placeholder.svg";
  const price = Format.money(p.price, symbol);
  const compare = p.compare_price && p.compare_price > p.price ? Format.money(p.compare_price, symbol) : "";
  const discount = p.compare_price && p.compare_price > p.price
    ? Math.round((1 - p.price / p.compare_price) * 100) : 0;
  const store = p.store ? p.store.name : "";
  const rating = p.rating_avg ? `${p.rating_avg.toFixed(1)}` : "New";
  const ratingCount = p.rating_count ? `(${p.rating_count})` : "";
  const outOfStock = !p.stock || p.stock <= 0;

  return `
  <article class="card product-card card-hover">
    <div class="product-media">
      <a href="/product.html?id=${p.id}" aria-label="${Format.escapeHtml(p.name)}">
        <img src="${Format.escapeHtml(img)}" alt="${Format.escapeHtml(p.name)}" loading="lazy">
      </a>
      <div class="product-badges">
        ${discount ? `<span class="badge badge-accent">-${discount}%</span>` : ""}
        ${outOfStock ? `<span class="badge badge-error">Sold out</span>` : ""}
      </div>
      <div class="product-actions">
        <button class="btn-icon" data-action="wishlist" data-id="${p.id}" title="Add to wishlist" aria-label="Add to wishlist"><i class="far fa-heart"></i></button>
        <button class="btn-icon" data-action="cart" data-id="${p.id}" title="Add to cart" aria-label="Add to cart"><i class="fas fa-cart-plus"></i></button>
      </div>
    </div>
    <div class="product-body">
      ${store ? `<div class="product-store">by ${Format.escapeHtml(store)}</div>` : ""}
      <h3 class="product-title"><a href="/product.html?id=${p.id}">${Format.escapeHtml(p.name)}</a></h3>
      <div class="product-rating mb-2">${starsHtml(p.rating_avg)} <span>${rating} ${ratingCount}</span></div>
      <div class="product-price-row">
        <span class="product-price">${price}</span>
        ${compare ? `<span class="product-compare">${compare}</span>` : ""}
      </div>
    </div>
  </article>`;
}

function bindProductCardActions(container) {
  container.querySelectorAll("[data-action]").forEach(btn => {
    btn.addEventListener("click", async (e) => {
      e.preventDefault();
      const action = btn.dataset.action;
      const id = btn.dataset.id;
      if (!Auth.isLoggedIn()) {
        Auth.loginRedirect(window.location.pathname + window.location.search);
        return;
      }
      try {
        if (action === "cart") {
          await API.post("/cart/items", { product_id: id, quantity: 1 });
          toast("Added to cart");
          const badge = document.getElementById("cart-badge");
          if (badge) {
            const res = await API.get("/cart");
            badge.textContent = res.data.item_count;
            badge.classList.remove("hidden");
          }
        } else if (action === "wishlist") {
          await API.post("/wishlist/items", { product_id: id });
          toast("Saved to wishlist");
          btn.innerHTML = '<i class="fas fa-heart"></i>';
        }
      } catch (err) {
        toast(err.message || "Action failed", "error");
      }
    });
  });
}

/* Pagination renderer */
function paginationHtml(pagination, onPage) {
  const { page, pages } = pagination;
  if (!pages || pages <= 1) return "";
  let html = `<div class="pagination" role="navigation" aria-label="Pagination">`;
  html += `<button ${page <= 1 ? "disabled" : ""} data-page="${page - 1}" aria-label="Previous page">‹</button>`;
  const start = Math.max(1, page - 2);
  const end = Math.min(pages, page + 2);
  for (let i = start; i <= end; i++) {
    html += `<button class="${i === page ? "active" : ""}" data-page="${i}">${i}</button>`;
  }
  html += `<button ${page >= pages ? "disabled" : ""} data-page="${page + 1}" aria-label="Next page">›</button>`;
  html += `</div>`;
  return html;
}
