document.addEventListener("DOMContentLoaded", () => {
  const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  document.querySelectorAll(".hero-background-video").forEach((video) => {
    const toggle = video.closest(".hero-video")?.querySelector(".hero-video-toggle");
    if (prefersReducedMotion.matches) {
      video.pause();
      if (toggle) {
        toggle.textContent = "Play film";
        toggle.setAttribute("aria-pressed", "true");
      }
    }
    toggle?.addEventListener("click", () => {
      if (video.paused) {
        video.play();
        toggle.textContent = "Pause film";
        toggle.setAttribute("aria-pressed", "false");
      } else {
        video.pause();
        toggle.textContent = "Play film";
        toggle.setAttribute("aria-pressed", "true");
      }
    });
  });

  document.querySelectorAll(".flash").forEach((flash) => {
    window.setTimeout(() => {
      flash.classList.add("flash-hide");
      window.setTimeout(() => flash.remove(), 350);
    }, 4200);
  });

  // ==========================================
  // Admin Inventory Master-Detail Row & Right Corner View
  // ==========================================
  const addProductPanel = document.getElementById("add-product-panel");
  const emptyPlaceholder = document.getElementById("pane-empty-placeholder");
  const productRows = document.querySelectorAll(".product-row");
  const detailCards = document.querySelectorAll(".product-detail-card");
  const openAddBtns = document.querySelectorAll(".open-add-product-btn, #btn-open-add-product");
  const closeAddBtn = document.getElementById("btn-close-add-panel");
  const cancelAddBtn = document.getElementById("btn-cancel-add");
  const newNameInput = document.getElementById("new-product-name-input");
  const rightPane = document.getElementById("inventory-right-pane");

  function hideAllRightPanels() {
    if (addProductPanel) addProductPanel.style.display = "none";
    if (emptyPlaceholder) emptyPlaceholder.style.display = "none";
    detailCards.forEach((card) => {
      card.style.display = "none";
    });
  }

  function showAddProductPanel() {
    hideAllRightPanels();
    productRows.forEach((r) => r.classList.remove("selected-row"));
    if (addProductPanel) {
      addProductPanel.style.display = "block";
      newNameInput?.focus();
      if (window.innerWidth <= 960 && rightPane) {
        rightPane.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    }
  }

  function showProductDetail(productId) {
    hideAllRightPanels();
    productRows.forEach((r) => {
      if (r.getAttribute("data-product-id") === String(productId)) {
        r.classList.add("selected-row");
      } else {
        r.classList.remove("selected-row");
      }
    });
    const targetCard = document.getElementById(`product-detail-${productId}`);
    if (targetCard) {
      targetCard.style.display = "block";
      if (window.innerWidth <= 960 && rightPane) {
        rightPane.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    } else if (emptyPlaceholder) {
      emptyPlaceholder.style.display = "block";
    }
  }

  // Row clicks -> open product detail in right corner
  productRows.forEach((row) => {
    row.addEventListener("click", () => {
      const prodId = row.getAttribute("data-product-id");
      if (prodId) {
        showProductDetail(prodId);
      }
    });
    row.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        const prodId = row.getAttribute("data-product-id");
        if (prodId) showProductDetail(prodId);
      }
    });
  });

  // Dedicated "View ↗" buttons on table row
  document.querySelectorAll(".select-product-btn").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      const prodId = btn.getAttribute("data-product-id");
      if (prodId) showProductDetail(prodId);
    });
  });

  // Add Product button triggers
  openAddBtns.forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.preventDefault();
      showAddProductPanel();
    });
  });

  closeAddBtn?.addEventListener("click", () => {
    hideAllRightPanels();
    const firstRow = document.querySelector(".product-row");
    if (firstRow) {
      showProductDetail(firstRow.getAttribute("data-product-id"));
    } else if (emptyPlaceholder) {
      emptyPlaceholder.style.display = "block";
    }
  });

  cancelAddBtn?.addEventListener("click", () => {
    hideAllRightPanels();
    const firstRow = document.querySelector(".product-row");
    if (firstRow) {
      showProductDetail(firstRow.getAttribute("data-product-id"));
    } else if (emptyPlaceholder) {
      emptyPlaceholder.style.display = "block";
    }
  });

  // Close buttons inside detail cards
  document.querySelectorAll(".close-pane-btn[data-close-target]").forEach((btn) => {
    btn.addEventListener("click", () => {
      hideAllRightPanels();
      productRows.forEach((r) => r.classList.remove("selected-row"));
      if (emptyPlaceholder) emptyPlaceholder.style.display = "block";
    });
  });

  // Check URL hash or query params to auto-open specific product or add form
  const urlParams = new URLSearchParams(window.location.search);
  const hash = window.location.hash;

  if (hash === "#add-product" || urlParams.get("action") === "new") {
    showAddProductPanel();
  } else if (hash && hash.startsWith("#product-")) {
    const targetId = hash.replace("#product-", "");
    const matchingRow = document.getElementById(`product-${targetId}`) || document.getElementById(`product-row-${targetId}`);
    if (matchingRow) {
      matchingRow.classList.add("target-highlight");
      matchingRow.scrollIntoView({ behavior: "smooth", block: "center" });
    }
    showProductDetail(targetId);
  } else if (productRows.length > 0) {
    const firstRow = productRows[0];
    const firstId = firstRow.getAttribute("data-product-id");
    if (firstId) showProductDetail(firstId);
  } else {
    hideAllRightPanels();
    if (emptyPlaceholder) emptyPlaceholder.style.display = "block";
  }

  // ==========================================
  // Sales Module: Record Sale & POS Form
  // ==========================================
  const recordSalePanel = document.getElementById("record-sale-panel");
  const openSaleBtn = document.getElementById("btn-open-sale-form");
  const closeSaleBtn = document.getElementById("btn-close-sale-panel");
  const cancelSaleBtn = document.getElementById("btn-cancel-sale");
  const saleProductSelect = document.getElementById("sale-product-select");
  const saleQuantityInput = document.getElementById("sale-quantity-input");
  const salePriceInput = document.getElementById("sale-price-input");
  const saleSizeInput = document.getElementById("sale-size-input");
  const saleTotalDisplay = document.getElementById("sale-total-display");

  const radioCustExisting = document.getElementById("radio-cust-existing");
  const radioCustNew = document.getElementById("radio-cust-new");
  const existingCustBlock = document.getElementById("existing-customer-block");
  const newCustBlock = document.getElementById("new-customer-block");
  const existingUserSelect = document.getElementById("existing-user-select");

  function openRecordSaleForm() {
    if (recordSalePanel) {
      recordSalePanel.style.display = "block";
      recordSalePanel.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }

  function closeRecordSaleForm() {
    if (recordSalePanel) {
      recordSalePanel.style.display = "none";
    }
  }

  openSaleBtn?.addEventListener("click", () => {
    if (recordSalePanel?.style.display === "none" || !recordSalePanel?.style.display) {
      openRecordSaleForm();
    } else {
      closeRecordSaleForm();
    }
  });

  closeSaleBtn?.addEventListener("click", closeRecordSaleForm);
  cancelSaleBtn?.addEventListener("click", closeRecordSaleForm);

  function recalculateSaleTotal() {
    const qty = parseInt(saleQuantityInput?.value || "1", 10) || 1;
    const price = parseFloat(salePriceInput?.value || "0") || 0;
    const total = qty * price;
    if (saleTotalDisplay) {
      saleTotalDisplay.textContent = `Rs ${total.toFixed(2)}`;
    }
  }

  saleProductSelect?.addEventListener("change", () => {
    const selectedOption = saleProductSelect.options[saleProductSelect.selectedIndex];
    if (selectedOption) {
      const price = selectedOption.getAttribute("data-price") || "0.00";
      const sizes = selectedOption.getAttribute("data-sizes") || "";
      if (salePriceInput) salePriceInput.value = price;
      if (saleSizeInput && sizes) {
        const firstSize = sizes.split(",")[0].trim();
        saleSizeInput.value = firstSize;
      }
      recalculateSaleTotal();
    }
  });

  saleQuantityInput?.addEventListener("input", recalculateSaleTotal);
  salePriceInput?.addEventListener("input", recalculateSaleTotal);

  radioCustExisting?.addEventListener("change", () => {
    if (radioCustExisting.checked) {
      if (existingCustBlock) existingCustBlock.style.display = "block";
      if (newCustBlock) newCustBlock.style.display = "none";
    }
  });

  radioCustNew?.addEventListener("change", () => {
    if (radioCustNew.checked) {
      if (existingCustBlock) existingCustBlock.style.display = "none";
      if (newCustBlock) newCustBlock.style.display = "grid";
    }
  });

  existingUserSelect?.addEventListener("change", () => {
    const opt = existingUserSelect.options[existingUserSelect.selectedIndex];
    if (opt && opt.value) {
      const email = opt.getAttribute("data-email");
      const phone = opt.getAttribute("data-phone");
      const emailField = document.getElementById("cust-email");
      const phoneField = document.getElementById("cust-phone");
      if (emailField && email) emailField.value = email;
      if (phoneField && phone) phoneField.value = phone;
    }
  });

  if (window.location.hash === "#record-sale" || urlParams.get("action") === "sale") {
    openRecordSaleForm();
  }

  // ==========================================
  // Part 1: Order Management Slide-over Drawer
  // ==========================================
  const drawerBackdrop = document.getElementById("order-drawer-backdrop");
  const drawerTriggers = document.querySelectorAll(".order-drawer-trigger");
  const drawerCloseButtons = document.querySelectorAll(".drawer-close-btn, [data-close-drawer]");
  const allOrderDrawers = document.querySelectorAll(".order-slide-drawer");

  function closeAllOrderDrawers() {
    allOrderDrawers.forEach((drawer) => {
      drawer.style.display = "none";
      drawer.setAttribute("aria-hidden", "true");
    });
    if (drawerBackdrop) drawerBackdrop.style.display = "none";
    document.body.style.overflow = "";
  }

  function openOrderDrawer(orderId) {
    closeAllOrderDrawers();
    const targetDrawer = document.getElementById(`order-drawer-${orderId}`);
    if (targetDrawer) {
      targetDrawer.style.display = "flex";
      targetDrawer.setAttribute("aria-hidden", "false");
      if (drawerBackdrop) drawerBackdrop.style.display = "block";
      document.body.style.overflow = "hidden";
      // Highlight table row
      const targetRow = document.getElementById(`order-row-${orderId}`);
      if (targetRow) {
        document.querySelectorAll("tr[id^='order-row-']").forEach((r) => r.classList.remove("selected-row"));
        targetRow.classList.add("selected-row");
      }
    }
  }

  drawerTriggers.forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      const orderId = btn.getAttribute("data-order-id");
      if (orderId) openOrderDrawer(orderId);
    });
  });

  drawerCloseButtons.forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.preventDefault();
      closeAllOrderDrawers();
    });
  });

  drawerBackdrop?.addEventListener("click", closeAllOrderDrawers);

  // Check URL hash to open drawer automatically e.g. #order-3 or #order-drawer-3
  if (window.location.hash) {
    const orderMatch = window.location.hash.match(/#order-(?:(?:drawer|row)-)?(\d+)/);
    if (orderMatch && orderMatch[1]) {
      const orderId = orderMatch[1];
      // If we are on /admin/orders open the drawer, otherwise highlight the table row
      if (document.getElementById(`order-drawer-${orderId}`)) {
        openOrderDrawer(orderId);
      } else {
        const orderRow = document.getElementById(`order-${orderId}`) || document.getElementById(`order-row-${orderId}`);
        if (orderRow) {
          orderRow.style.outline = "2px solid #111";
          orderRow.scrollIntoView({ behavior: "smooth", block: "center" });
        }
      }
    }
  }

  // Escape key closes open drawer or modal
  window.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      closeAllOrderDrawers();
    }
    if (e.key === "/" && !["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement?.tagName)) {
      const searchInput = document.querySelector(".nav-search-input");
      if (searchInput) {
        e.preventDefault();
        searchInput.focus();
        searchInput.select();
      }
    }
  });
});
