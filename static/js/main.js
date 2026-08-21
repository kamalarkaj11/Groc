// Modern JS for Grocery Store - Cart AJAX, Toasts, Animations, Search

// ─── Toast Notification System ───────────────────────────────────────

function ensureToastContainer() {
  let container = document.getElementById('toast-container');
  if (!container) {
    container = document.createElement('div');
    container.id = 'toast-container';
    container.setAttribute('aria-live', 'polite');
    container.setAttribute('aria-relevant', 'additions');
    document.body.appendChild(container);
  }
  return container;
}

function showToast(message, type) {
  // Normalize type
  if (!type || type === 'success') type = 'success';
  else if (type === 'danger' || type === 'error') type = 'error';
  else if (type === 'warning') type = 'warning';
  else if (type === 'info') type = 'info';

  const container = ensureToastContainer();
  const toast = document.createElement('div');
  toast.className = 'toast-notification toast-' + type;

  // Icon based on type
  let iconHtml = '';
  if (type === 'success') iconHtml = '<i class="bi bi-check-circle-fill"></i>';
  else if (type === 'error') iconHtml = '<i class="bi bi-exclamation-circle-fill"></i>';
  else if (type === 'warning') iconHtml = '<i class="bi bi-exclamation-triangle-fill"></i>';
  else iconHtml = '<i class="bi bi-info-circle-fill"></i>';

  toast.innerHTML = iconHtml + '<span>' + message + '</span>';
  container.appendChild(toast);

  // Trigger slide-in
  requestAnimationFrame(() => {
    toast.classList.add('show');
  });

  // Auto-hide after 4 seconds
  const hideTimeout = setTimeout(() => {
    dismissToast(toast);
  }, 4000);

  // Click to dismiss
  toast.addEventListener('click', () => {
    clearTimeout(hideTimeout);
    dismissToast(toast);
  });
}

function dismissToast(toast) {
  toast.classList.remove('show');
  toast.classList.add('hide');
  setTimeout(() => {
    if (toast.parentNode) {
      toast.parentNode.removeChild(toast);
    }
  }, 300);
}

// ─── Cart Summary Update ─────────────────────────────────────────────

function updateCartSummary() {
  fetch('/cart/summary/')
    .then(res => res.json())
    .then(data => {
      document.querySelectorAll('.cart-count').forEach(el => {
        el.textContent = data.count || 0;
      });
    })
    .catch(err => console.error('Cart summary fetch failed:', err));
}

// ─── Add to Cart AJAX ────────────────────────────────────────────────

function addToCart(productId, quantity, button) {
  const originalHtml = button ? button.innerHTML : null;

  if (button) {
    button.disabled = true;
    button.innerHTML = '<span class="grochub-btn-spinner me-1" role="status" aria-hidden="true"></span> Adding...';
  }

  const formData = new FormData();
  formData.append('product_id', productId);
  formData.append('qty', quantity);
  formData.append('csrfmiddlewaretoken', getCookie('csrftoken'));

  fetch('/cart/add/', {
    method: 'POST',
    headers: {
      'X-Requested-With': 'XMLHttpRequest',
    },
    body: formData,
  })
  .then(res => {
    if (!res.ok) {
      return res.json().catch(() => {
        throw new Error('Server returned ' + res.status);
      }).then(data => {
        throw data;
      });
    }
    return res.json();
  })
  .then(data => {
    if (data.success) {
      if (data.cart_count !== undefined) {
        document.querySelectorAll('.cart-count').forEach(el => {
          el.textContent = data.cart_count;
        });
      }
      showToast(data.message || 'Product added to cart successfully', 'success');
      if (button && originalHtml) {
        button.innerHTML = '<i class="bi bi-check-circle-fill"></i> Added';
        setTimeout(() => {
          if (button.dataset && button.dataset.originalHtml) {
            button.innerHTML = button.dataset.originalHtml;
          } else {
            button.innerHTML = originalHtml;
          }
          button.disabled = false;
        }, 1500);
      }
    } else {
      showToast(data.error || 'Unable to add item to cart. Please try again.', 'error');
      if (button && originalHtml) {
        button.innerHTML = originalHtml;
        button.disabled = false;
      }
    }
  })
  .catch(err => {
    console.error('Add to cart failed:', err);
    const msg = (err && err.error) ? err.error : (err && err.message) ? err.message : 'Unable to add item to cart. Please try again.';
    showToast(msg, 'error');
    if (button && originalHtml) {
      button.innerHTML = originalHtml;
      button.disabled = false;
    }
  });
}

// ─── DOM Ready ────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', function() {
  // Navbar scroll effect (on .site-header)
  window.addEventListener('scroll', () => {
    const header = document.querySelector('.site-header');
    if (header) {
      if (window.scrollY > 50) {
        header.classList.add('is-scrolled');
      } else {
        header.classList.remove('is-scrolled');
      }
    }
  });

  // Animate on scroll
  const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        entry.target.classList.add('animate-fadeInUp');
      }
    });
  });
  document.querySelectorAll('.product-card, .glass-card').forEach(el => {
    observer.observe(el);
  });

  // ── AJAX Add to Cart Handler ──
  document.addEventListener('click', function(e) {
    const btn = e.target.closest('[data-add-to-cart]');
    if (!btn) return;
    e.preventDefault();

    const productId = btn.dataset.addToCart;
    if (!productId) return;

    // Store original HTML for restoration
    btn.dataset.originalHtml = btn.innerHTML;

    // Find quantity from nearest quantity input or default to 1
    const form = btn.closest('form');
    let qty = 1;
    if (form) {
      const qtyInput = form.querySelector('[name="qty"]');
      if (qtyInput) qty = parseInt(qtyInput.value, 10) || 1;
    }

    addToCart(productId, qty, btn);
  });

  // Initial cart count fetch
  updateCartSummary();

  // Smooth scroll for anchor links
  document.querySelectorAll('a[href^="#"]').forEach(anchor => {
    anchor.addEventListener('click', function (e) {
      e.preventDefault();
      const target = document.querySelector(this.getAttribute('href'));
      if (target) {
        target.scrollIntoView({ behavior: 'smooth' });
      }
    });
  });
});

// ─── Utility ─────────────────────────────────────────────────────────

function getCookie(name) {
  let cookieValue = null;
  if (document.cookie && document.cookie !== '') {
    const cookies = document.cookie.split(';');
    for (let i = 0; i < cookies.length; i++) {
      const cookie = cookies[i].trim();
      if (cookie.substring(0, name.length + 1) === (name + '=')) {
        cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
        break;
      }
    }
  }
  return cookieValue;
}

// Search with debounce
let searchTimeout;
document.getElementById('searchInput')?.addEventListener('input', function() {
  clearTimeout(searchTimeout);
  searchTimeout = setTimeout(() => {
    const form = this.closest('form');
    if (form) form.submit();
  }, 300);
});

// Periodic cart summary refresh (every 30s)
setInterval(updateCartSummary, 30000);

// ─── GrocHub Loading Animation ──────────────────────────────────────
// Reusable full-screen loader. The overlay is *visible by default* in the
// HTML/CSS so it also covers the initial page request; JS fades it out after
// the page has loaded. For long-running operations (payment, checkout, …)
// call showGrocHubLoader() / hideGrocHubLoader() explicitly.

const GrocHubLoader = {
  _el: null,
  minShowMs: 450,
  shownAt: 0,
  hideTimer: null,

  get el() {
    if (!this._el) this._el = document.getElementById('grochub-loader');
    return this._el;
  },
  set el(v) { this._el = v; },

  reducedMotion() {
    return window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  },

  // Follow the currently selected theme (dark vs light).
  applyTheme() {
    const loader = this.el;
    if (!loader) return;
    const root = document.documentElement;
    let dark =
      root.getAttribute('data-theme') === 'dark' ||
      root.getAttribute('data-bs-theme') === 'dark' ||
      !!document.querySelector('.api-dark, [data-bs-theme="dark"]') ||
      (window.localStorage && window.localStorage.getItem('api-dark-mode') === '1');
    if (!dark && window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
      dark = true;
    }
    loader.classList.toggle('grochub-dark', dark);
  }
};

// Show the full-screen GrocHub loader.
function showGrocHubLoader() {
  const loader = GrocHubLoader.el;
  if (!loader) return;
  clearTimeout(GrocHubLoader.hideTimer);
  GrocHubLoader.shownAt = Date.now();
  GrocHubLoader.applyTheme();
  loader.classList.remove('grochub-leaving', 'grochub-hidden');
  void loader.offsetWidth; // restart any fade-in
}

// Hide the full-screen GrocHub loader (with a smooth fade).
function hideGrocHubLoader() {
  const loader = GrocHubLoader.el;
  if (!loader) return;
  clearTimeout(GrocHubLoader.hideTimer);
  // Keep it for a very short moment so the transition feels smooth.
  const hold = GrocHubLoader.reducedMotion()
    ? 0
    : Math.max(0, GrocHubLoader.minShowMs - (Date.now() - GrocHubLoader.shownAt));
  GrocHubLoader.hideTimer = setTimeout(function () {
    loader.classList.add('grochub-leaving');
    setTimeout(function () {
      loader.classList.add('grochub-hidden');
      loader.classList.remove('grochub-leaving');
    }, GrocHubLoader.reducedMotion() ? 120 : 500);
  }, hold);
}

// ── Initial page-load lifecycle ─────────────────────────────────────
// Fade the loader once the page (including assets) has finished loading.
let grocHubLoadFired = false;
window.addEventListener('load', function () {
  grocHubLoadFired = true;
  hideGrocHubLoader();
});
// If the page was already finished before this script ran, hide shortly.
if (document.readyState === 'complete') {
  setTimeout(hideGrocHubLoader, GrocHubLoader.reducedMotion() ? 0 : 350);
}
// Safety net: never leave the initial loader visible forever.
setTimeout(hideGrocHubLoader, 8000);

// ── Internal navigation support ─────────────────────────────────────
// As soon as the user clicks a same-tab internal link, reveal the loader so
// there is no white flash between pages. The destination page renders its own
// default-visible loader, and a JS-prevented link is restored after a guard.
function looksInternalLink(anchor) {
  if (!anchor) return false;
  const href = (anchor.getAttribute('href') || '').trim();
  if (!href || href.charAt(0) === '#') return false;          // hash / placeholder
  const target = anchor.getAttribute('target') || '';
  if (target && target !== '_self') return false;             // opens elsewhere
  if (anchor.hasAttribute('download')) return false;           // download
  if (/^(mailto:|tel:|javascript:|data:|blob:)/i.test(href)) return false;
  if (anchor.hasAttribute('data-add-to-cart') || anchor.hasAttribute('data-wishlist') || anchor.hasAttribute('data-product')) return false;
  return true;
}

document.addEventListener('click', function (event) {
  const anchor = event.target.closest ? event.target.closest('a') : null;
  if (!looksInternalLink(anchor)) return;
  showGrocHubLoader();
  // If a page-side script prevented navigation / default, hide again shortly.
  setTimeout(hideGrocHubLoader, 2200);
});