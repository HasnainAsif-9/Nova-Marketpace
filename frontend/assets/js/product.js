/* Product detail page */
(function () {
  const params = new URLSearchParams(window.location.search);
  const id = params.get("id") || params.get("slug") || "";
  const root = document.getElementById("product-root");
  let symbol = "Rs.";
  let currentProduct = null;
  let quantity = 1;

  function requireAuth(action) {
    if (!Auth.isLoggedIn()) {
      if (action === "buy") {
        window.location.href = `/login.html?redirect=${encodeURIComponent(`/checkout.html?buy=${currentProduct.id}`)}`;
      } else {
        Auth.loginRedirect(window.location.pathname + window.location.search);
      }
      return false;
    }
    return true;
  }

  function render(product) {
    currentProduct = product;
    const p = product;
    const img = (p.images && p.images[0]) || "/assets/images/placeholder.svg";
    const price = Format.money(p.price, symbol);
    const compare = p.compare_price && p.compare_price > p.price ? Format.money(p.compare_price, symbol) : "";
    const discount = p.compare_price && p.compare_price > p.price ? Math.round((1 - p.price / p.compare_price) * 100) : 0;
    const inStock = p.stock > 0 && p.status === "active";
    const specs = p.specifications && Object.keys(p.specifications).length
      ? Object.entries(p.specifications).map(([k, v]) => `<tr><td>${Format.escapeHtml(k)}</td><td>${Format.escapeHtml(v)}</td></tr>`).join("")
      : "";

    document.title = `${p.name} — ${symbol} ${p.price} | NovaMarket`;
    const desc = document.querySelector('meta[name="description"]');
    if (desc) desc.content = (p.short_description || p.description || p.name).slice(0, 160);
    const ogTitle = document.querySelector('meta[property="og:title"]');
    if (ogTitle) ogTitle.content = `${p.name} — ${symbol} ${p.price} | NovaMarket`;
    const ogDesc = document.querySelector('meta[property="og:description"]');
    if (ogDesc) ogDesc.content = (p.short_description || p.description || p.name).slice(0, 200);
    const ogImg = document.querySelector('meta[property="og:image"]');
    if (ogImg && p.images && p.images[0]) ogImg.content = p.images[0];
    if (!ogImg && p.images && p.images[0]) {
      const m = document.createElement("meta");
      m.setAttribute("property", "og:image");
      m.content = p.images[0];
      document.head.appendChild(m);
    }

    // JSON-LD structured data for search engines
    let ld = document.getElementById("product-jsonld");
    if (!ld) {
      ld = document.createElement("script");
      ld.type = "application/ld+json";
      ld.id = "product-jsonld";
      document.head.appendChild(ld);
    }
    ld.textContent = JSON.stringify({
      "@context": "https://schema.org",
      "@type": "Product",
      "name": p.name,
      "description": (p.short_description || p.description || "").slice(0, 300),
      "image": p.images && p.images[0] ? [p.images[0]] : undefined,
      "sku": p.sku || undefined,
      "brand": p.brand ? { "@type": "Brand", "name": p.brand } : undefined,
      "offers": {
        "@type": "Offer",
        "price": p.price,
        "priceCurrency": "PKR",
        "availability": p.stock > 0 ? "https://schema.org/InStock" : "https://schema.org/OutOfStock",
      },
      "aggregateRating": p.rating_count > 0 ? {
        "@type": "AggregateRating",
        "ratingValue": p.rating_avg,
        "reviewCount": p.rating_count,
      } : undefined,
    });

    root.innerHTML = `
    <nav class="breadcrumb mb-4"><a href="/">Home</a> / <a href="/shop.html">Shop</a> / <span>${Format.escapeHtml(p.name)}</span></nav>

    <div class="product-detail">
      <div>
        <div class="gallery-main">
          <img id="main-img" src="${Format.escapeHtml(img)}" alt="${Format.escapeHtml(p.name)}">
        </div>
        ${p.images && p.images.length > 1 ? `
        <div class="gallery-thumbs">
          ${p.images.map((im, i) => `<button class="gallery-thumb ${i === 0 ? "active" : ""}" data-img="${Format.escapeHtml(im)}" aria-label="View image ${i + 1}"><img src="${Format.escapeHtml(im)}" alt="" loading="lazy"></button>`).join("")}
        </div>` : ""}
      </div>

      <div>
        ${p.store ? `<div class="product-store mb-2">Sold by <a href="/seller-store.html?slug=${p.store.slug || p.store.id}" style="font-weight:600">${Format.escapeHtml(p.store.name)}</a></div>` : ""}
        <h1>${Format.escapeHtml(p.name)}</h1>
        <div class="flex items-center gap-2 mb-4">
          <span class="product-rating">${starsHtml(p.rating_avg)} <span>${p.rating_avg ? p.rating_avg.toFixed(1) : "New"} (${p.rating_count || 0} reviews)</span></span>
          ${p.sku ? `<span class="badge badge-muted">SKU: ${Format.escapeHtml(p.sku)}</span>` : ""}
        </div>

        <div class="flex items-center gap-3 mb-4" style="font-size:var(--nm-text-2xl)">
          <span style="font-weight:700;color:var(--nm-primary-dark)">${price}</span>
          ${compare ? `<span style="text-decoration:line-through;color:var(--nm-text-3);font-size:var(--nm-text-lg)">${compare}</span>` : ""}
          ${discount ? `<span class="badge badge-accent">Save ${discount}%</span>` : ""}
        </div>

        <div class="mb-4">
          ${inStock
            ? `<span class="badge badge-success"><i class="fas fa-check"></i> In Stock (${p.stock} available)</span>`
            : `<span class="badge badge-error">Out of Stock</span>`}
        </div>

        <p style="color:var(--nm-text-2);margin-bottom:var(--nm-space-5)">${Format.escapeHtml(p.short_description || p.description || "")}</p>

        <div class="flex items-center gap-3 mb-5 wrap">
          <div class="qty-control">
            <button id="qty-minus" aria-label="Decrease quantity">−</button>
            <input id="qty-input" type="number" value="1" min="1" max="${Math.min(p.stock, 100)}" aria-label="Quantity">
            <button id="qty-plus" aria-label="Increase quantity">+</button>
          </div>
          <button class="btn btn-primary btn-lg" id="add-cart" ${inStock ? "" : "disabled"}>
            <i class="fas fa-cart-plus"></i> Add to Cart
          </button>
          <button class="btn btn-accent btn-lg" id="buy-now" ${inStock ? "" : "disabled"}>
            <i class="fas fa-bolt"></i> Buy Now
          </button>
          <button class="btn btn-outline btn-lg" id="add-wishlist" aria-label="Add to wishlist">
            <i class="far fa-heart"></i>
          </button>
        </div>

        <div class="card" style="padding:var(--nm-space-4);margin-bottom:var(--nm-space-5)">
          <div class="summary-row"><span class="text-muted">Category</span><span>${Format.escapeHtml(p.category_name || "—")}</span></div>
          <div class="summary-row"><span class="text-muted">Brand</span><span>${Format.escapeHtml(p.brand || "—")}</span></div>
          <div class="summary-row"><span class="text-muted">Sold</span><span>${p.sold_count || 0} units</span></div>
        </div>

        ${p.description ? `
        <div class="mb-5">
          <h3>Description</h3>
          <p style="color:var(--nm-text-2);white-space:pre-line">${Format.escapeHtml(p.description)}</p>
        </div>` : ""}

        ${specs ? `
        <div class="mb-5">
          <h3>Specifications</h3>
          <table class="spec-table"><tbody>${specs}</tbody></table>
        </div>` : ""}
      </div>
    </div>

    <!-- Reviews -->
    <section class="section-sm" id="reviews-section">
      <h2>Customer Reviews</h2>
      <div id="reviews-list"><div class="spinner"></div></div>
      <div id="review-form-wrap" class="mt-6"></div>
    </section>

    <!-- Related -->
    <section class="section-sm" id="related-section">
      <h2>You may also like</h2>
      <div class="grid grid-4" id="related-grid"></div>
    </section>`;

    bindGallery();
    bindActions();
    loadReviews();
    loadRelated();
  }

  function bindGallery() {
    document.querySelectorAll(".gallery-thumb").forEach(t => {
      t.addEventListener("click", () => {
        document.getElementById("main-img").src = t.dataset.img;
        document.querySelectorAll(".gallery-thumb").forEach(x => x.classList.remove("active"));
        t.classList.add("active");
      });
    });
  }

  function bindActions() {
    const qtyInput = document.getElementById("qty-input");
    const maxQty = Math.min(currentProduct.stock, 100);
    document.getElementById("qty-minus").addEventListener("click", () => {
      quantity = Math.max(1, quantity - 1); qtyInput.value = quantity;
    });
    document.getElementById("qty-plus").addEventListener("click", () => {
      quantity = Math.min(maxQty, quantity + 1); qtyInput.value = quantity;
    });
    qtyInput.addEventListener("change", () => {
      quantity = Math.min(maxQty, Math.max(1, parseInt(qtyInput.value, 10) || 1));
      qtyInput.value = quantity;
    });

    document.getElementById("add-cart").addEventListener("click", async () => {
      if (!requireAuth("cart")) return;
      try {
        await API.post("/cart/items", { product_id: currentProduct.id, quantity });
        toast(`Added ${quantity} × ${currentProduct.name} to cart`);
        const badge = document.getElementById("cart-badge");
        if (badge) { const r = await API.get("/cart"); badge.textContent = r.data.item_count; badge.classList.remove("hidden"); }
      } catch (e) { toast(e.message, "error"); }
    });

    document.getElementById("buy-now").addEventListener("click", async () => {
      if (!requireAuth("buy")) return;
      try {
        await API.post("/cart/items", { product_id: currentProduct.id, quantity });
        window.location.href = "/checkout.html";
      } catch (e) { toast(e.message, "error"); }
    });

    document.getElementById("add-wishlist").addEventListener("click", async () => {
      if (!requireAuth("wishlist")) return;
      try {
        await API.post("/wishlist/items", { product_id: currentProduct.id });
        toast("Saved to wishlist");
        document.getElementById("add-wishlist").innerHTML = '<i class="fas fa-heart"></i>';
      } catch (e) { toast(e.message, "error"); }
    });
  }

  async function loadReviews() {
    const list = document.getElementById("reviews-list");
    const wrap = document.getElementById("review-form-wrap");
    try {
      const res = await API.get(`/reviews/product/${currentProduct.id}?limit=10`);
      const reviews = (res.data && res.data.reviews) || [];
      list.innerHTML = reviews.length ? reviews.map(r => `
        <div class="card" style="padding:var(--nm-space-4);margin-bottom:var(--nm-space-3)">
          <div class="flex items-center gap-2 mb-2">
            <strong>${Format.escapeHtml(r.reviewer_name || "Customer")}</strong>
            <span class="product-rating">${starsHtml(r.rating)}</span>
            <span class="text-xs text-muted">${Format.date(r.created_at)}</span>
          </div>
          ${r.comment ? `<p style="margin:0;color:var(--nm-text-2)">${Format.escapeHtml(r.comment)}</p>` : ""}
        </div>`).join("")
        : `<div class="empty-state"><i class="far fa-comment-dots"></i><p>No reviews yet. Be the first to review!</p></div>`;
    } catch (e) { list.innerHTML = `<p class="text-muted">Could not load reviews.</p>`; }

    // Review form — only for eligible buyers
    if (Auth.isLoggedIn() && Auth.role() === "buyer") {
      wrap.innerHTML = `
      <div class="card" style="padding:var(--nm-space-5)">
        <h3>Write a Review</h3>
        <div class="star-input mb-3" id="star-input">
          ${[1,2,3,4,5].map(i => `<span data-star="${i}">★</span>`).join("")}
        </div>
        <div class="form-group"><textarea id="review-comment" class="form-textarea" placeholder="Share your experience..."></textarea></div>
        <button class="btn btn-primary" id="submit-review">Submit Review</button>
      </div>`;
      let rating = 0;
      document.querySelectorAll("#star-input span").forEach(s => {
        s.addEventListener("click", () => {
          rating = parseInt(s.dataset.star, 10);
          document.querySelectorAll("#star-input span").forEach(x =>
            x.classList.toggle("active", parseInt(x.dataset.star, 10) <= rating));
        });
      });
      document.getElementById("submit-review").addEventListener("click", async () => {
        if (!rating) { toast("Please select a star rating", "warning"); return; }
        try {
          await API.post("/reviews", { product_id: currentProduct.id, rating, comment: document.getElementById("review-comment").value });
          toast("Review submitted!");
          loadReviews();
        } catch (e) { toast(e.message, "error"); }
      });
    }
  }

  async function loadRelated() {
    const grid = document.getElementById("related-grid");
    try {
      const related = currentProduct.related_products || [];
      grid.innerHTML = related.length
        ? related.map(p => productCardHtml(p, symbol)).join("")
        : `<p class="text-muted">No related products.</p>`;
      bindProductCardActions(grid);
    } catch (e) { /* ignore */ }
  }

  async function init() {
    API.get("/settings").then(r => {
      if (r.data && r.data.settings && r.data.settings.currency_symbol) symbol = r.data.settings.currency_symbol;
    }).catch(() => {});

    if (!id) { root.innerHTML = `<div class="empty-state"><i class="fas fa-exclamation-circle"></i><h3>Product not found</h3><a href="/shop.html" class="btn btn-primary">Browse products</a></div>`; return; }
    try {
      const res = await API.get(`/products/${encodeURIComponent(id)}`);
      render(res.data.product);
    } catch (e) {
      root.innerHTML = `<div class="empty-state"><i class="fas fa-exclamation-circle"></i><h3>${Format.escapeHtml(e.message)}</h3><a href="/shop.html" class="btn btn-primary">Browse products</a></div>`;
    }
  }

  init();
})();
