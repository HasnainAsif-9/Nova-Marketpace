/* Shop page — filters, search, sort, pagination */
(function () {
  const params = new URLSearchParams(window.location.search);
  let state = {
    page: 1,
    q: params.get("q") || "",
    category_id: params.get("category_id") || "",
    min_price: params.get("min_price") || "",
    max_price: params.get("max_price") || "",
    min_rating: params.get("min_rating") || "0",
    in_stock: params.get("in_stock") || "",
    on_sale: params.get("on_sale") || "",
    sort: params.get("sort") || "newest",
  };
  let symbol = "Rs.";
  let debounceTimer = null;

  const $ = id => document.getElementById(id);

  function buildQuery() {
    const qs = new URLSearchParams();
    qs.set("page", state.page);
    qs.set("limit", "20");
    qs.set("sort", state.sort);
    if (state.q) qs.set("q", state.q);
    if (state.category_id) qs.set("category_id", state.category_id);
    if (state.min_price) qs.set("min_price", state.min_price);
    if (state.max_price) qs.set("max_price", state.max_price);
    if (state.min_rating && state.min_rating !== "0") qs.set("min_rating", state.min_rating);
    if (state.in_stock) qs.set("in_stock", "1");
    if (state.on_sale) qs.set("on_sale", "1");
    return qs.toString();
  }

  function syncUrl() {
    const qs = new URLSearchParams();
    Object.entries(state).forEach(([k, v]) => { if (v && v !== "0" && v !== "newest") qs.set(k, v); });
    const url = qs.toString() ? `/shop.html?${qs}` : "/shop.html";
    history.replaceState(null, "", url);
  }

  async function loadProducts() {
    const grid = $("product-grid");
    grid.innerHTML = Array(8).fill('<div class="skeleton" style="height:340px"></div>').join("");
    try {
      const res = await API.get(`/products?${buildQuery()}`);
      const data = res.data || {};
      const products = data.products || [];
      const pg = data.pagination || {};
      $("result-count").textContent = `${pg.total || 0} product${(pg.total || 0) === 1 ? "" : "s"} found`;
      grid.innerHTML = products.length
        ? products.map(p => productCardHtml(p, symbol)).join("")
        : `<div class="empty-state" style="grid-column:1/-1"><i class="fas fa-search"></i><h3>No products found</h3><p>Try adjusting your filters or search term.</p></div>`;
      bindProductCardActions(grid);
      $("pagination-wrap").innerHTML = paginationHtml(pg, page => { state.page = page; loadProducts(); syncUrl(); window.scrollTo({ top: 0, behavior: "smooth" }); });
      bindPagination();
    } catch (e) {
      grid.innerHTML = `<div class="empty-state" style="grid-column:1/-1"><i class="fas fa-exclamation-triangle"></i><h3>Something went wrong</h3><p>${Format.escapeHtml(e.message)}</p></div>`;
    }
  }

  function bindPagination() {
    document.querySelectorAll("#pagination-wrap [data-page]").forEach(btn => {
      btn.addEventListener("click", () => {
        const p = parseInt(btn.dataset.page, 10);
        if (p >= 1) { state.page = p; loadProducts(); syncUrl(); }
      });
    });
  }

  async function loadCategories() {
    try {
      const res = await API.get("/categories");
      const cats = (res.data && res.data.categories) || [];
      const el = $("filter-categories");
      el.innerHTML = cats.map(c => `
        <label class="filter-option">
          <input type="radio" name="cat" value="${c.id}" ${state.category_id === c.id ? "checked" : ""}>
          ${Format.escapeHtml(c.name)}
        </label>`).join("");
      el.querySelectorAll('input[name="cat"]').forEach(r => {
        r.addEventListener("change", () => {
          state.category_id = r.checked ? r.value : "";
          state.page = 1; loadProducts(); syncUrl();
        });
      });
    } catch (e) { /* ignore */ }
  }

  function bindFilters() {
    $("filter-q").addEventListener("input", e => {
      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(() => {
        state.q = e.target.value.trim(); state.page = 1; loadProducts(); syncUrl();
      }, 350);
    });
    $("filter-min").addEventListener("change", e => { state.min_price = e.target.value; state.page = 1; loadProducts(); syncUrl(); });
    $("filter-max").addEventListener("change", e => { state.max_price = e.target.value; state.page = 1; loadProducts(); syncUrl(); });
    $("filter-rating").addEventListener("change", e => { state.min_rating = e.target.value; state.page = 1; loadProducts(); syncUrl(); });
    $("filter-instock").addEventListener("change", e => { state.in_stock = e.target.checked ? "1" : ""; state.page = 1; loadProducts(); syncUrl(); });
    $("filter-onsale").addEventListener("change", e => { state.on_sale = e.target.checked ? "1" : ""; state.page = 1; loadProducts(); syncUrl(); });
    $("sort-select").addEventListener("change", e => { state.sort = e.target.value; state.page = 1; loadProducts(); syncUrl(); });
    $("clear-filters").addEventListener("click", () => {
      state = { page: 1, q: "", category_id: "", min_price: "", max_price: "", min_rating: "0", in_stock: "", on_sale: "", sort: "newest" };
      $("filter-q").value = ""; $("filter-min").value = ""; $("filter-max").value = "";
      $("filter-rating").value = "0"; $("filter-instock").checked = false; $("filter-onsale").checked = false;
      $("sort-select").value = "newest";
      document.querySelectorAll('input[name="cat"]').forEach(r => r.checked = false);
      loadProducts(); syncUrl();
    });
  }

  // Init from URL params into controls
  $("filter-q").value = state.q;
  $("filter-min").value = state.min_price;
  $("filter-max").value = state.max_price;
  $("filter-rating").value = state.min_rating || "0";
  $("filter-instock").checked = !!state.in_stock;
  $("filter-onsale").checked = !!state.on_sale;
  $("sort-select").value = state.sort;

  API.get("/settings").then(r => {
    if (r.data && r.data.settings && r.data.settings.currency_symbol) symbol = r.data.settings.currency_symbol;
  }).catch(() => {});

  loadCategories();
  bindFilters();
  loadProducts();
})();
