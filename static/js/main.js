// Modern JS for Grocery Store - Cart AJAX, Toasts, Animations, Search

// Update cart count + grandtotal in navbar
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

function showToast(message, type = 'success') {
  // All notifications are now centralized in the notification bell.
  // Toast display has been removed — check the bell for updates.
  console.log(`[Notification] ${message}`);
}

// Cart AJAX functions
document.addEventListener('DOMContentLoaded', function() {
  // Navbar scroll effect
  window.addEventListener('scroll', () => {
    const navbar = document.querySelector('.navbar');
    if (navbar) {
      if (window.scrollY > 50) {
        navbar.classList.add('scrolled');
      } else {
        navbar.classList.remove('scrolled');
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

  // Loading animation for forms (exclude auth forms)
  document.querySelectorAll('form:not([action*="signup"]):not([action*="login"])').forEach(form => {
    form.addEventListener('submit', function(e) {
      const btn = form.querySelector('button[type="submit"]');
      if (btn) {
        const originalText = btn.innerHTML;
        btn.innerHTML = '<span class="loading me-2"></span>Processing...';
        btn.disabled = true;

        // Re-enable after 10s timeout in case of issues
        setTimeout(() => {
          btn.disabled = false;
          btn.innerHTML = originalText;
        }, 10000);
      }
    });
  });

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

  updateCartSummary();
});

// updateGrandTotal DISABLED - using server-side totals
/*
function updateGrandTotal() {
  let total = 0;
  document.querySelectorAll('.total-cell').forEach(cell => {
    total += parseFloat(cell.textContent.replace('₹', ''));
  });
  document.querySelector('.grand-total').textContent = `₹${Math.round(total)}`;
}
*/

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

// Specific handlers for auth forms moved to templates for reliability

// Summary update intervals
setInterval(updateCartSummary, 30000);

// AJAX Add to Cart - prevent redirect and stay on current page
document.addEventListener('DOMContentLoaded', function() {
  const addToCartForms = document.querySelectorAll('form[action*="add_to_cart"]');
  
  addToCartForms.forEach(form => {
    form.addEventListener('submit', function(e) {
      e.preventDefault();
      
      const btn = form.querySelector('button[type="submit"]');
      const originalText = btn ? btn.innerHTML : 'Add to Cart';
      
      if (btn) {
        btn.innerHTML = '<span class="loading me-2"></span>Adding...';
        btn.disabled = true;
      }
      
      const formData = new FormData(form);
      
      fetch(form.action, {
        method: 'POST',
        headers: {
          'X-Requested-With': 'XMLHttpRequest',
        },
        body: formData,
      })
      .then(res => res.json())
      .then(data => {
        if (data.success) {
          showToast(data.message || 'Product added to cart successfully!', 'success');
          updateCartSummary();
        } else {
          showToast(data.error || 'Failed to add product to cart.', 'danger');
        }
      })
      .catch(err => {
        console.error('Add to cart failed:', err);
        showToast('Something went wrong. Please try again.', 'danger');
      })
      .finally(() => {
        if (btn) {
          btn.innerHTML = originalText;
          btn.disabled = false;
        }
      });
    });
  });
});
