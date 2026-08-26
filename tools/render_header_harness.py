"""Render the real header.html template into a standalone harness for headless testing.

Usage:
    python tools/render_header_harness.py [anon|auth] [output_path]
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'grocery_store.settings')
import django
django.setup()

from django.contrib.auth.models import AnonymousUser, User
from django.template.loader import get_template
from django.test import RequestFactory

from store.context_processors import categories_context, cart_context, notification_context


def render_header(user=None):
    factory = RequestFactory()
    request = factory.get('/')
    request.user = user or AnonymousUser()

    context = {
        'user': request.user,
        'request': request,
        'cart_item_count': 3,
        'unread_notification_count': 2,
    }
    # Merge the real context processors exactly as Django would.
    for ctx_fn in (categories_context, cart_context, notification_context):
        try:
            context.update(ctx_fn(request))
        except Exception:
            # The fake user is not persisted to the DB; context processors that
            # hit the DB for an authenticated user are skipped (harness only).
            pass

    template = get_template('header.html')
    html = template.render(context)

    m = re.search(r'<style>([\s\S]*?)</style>', html)
    css = m.group(1) if m else ''
    sm = re.search(r'<script>([\s\S]*?)</script>', html)
    script = sm.group(1) if sm else ''
    # Remove the header's own script block so it can be embedded exactly once.
    html_no_script = html.replace(sm.group(0), '') if sm else html
    return css, html_no_script, script


MEASURE = """
<script>
function openDrawer() {
  var d = document.getElementById('mobileNavDrawer');
  var h = document.getElementById('siteHeader');
  var o = document.getElementById('mobileOverlay');
  if (d) {
    var rect = h.getBoundingClientRect();
    d.style.top = Math.max(8, rect.bottom + 8) + 'px';
    d.style.right = Math.max(0, window.innerWidth - rect.right + 8) + 'px';
    d.classList.add('open');
    o.classList.add('open');
  }
}
function __MEASURE(label) {
  var doc = document.documentElement;
  var drawer = document.getElementById('mobileNavDrawer');
  var search = document.getElementById('mobileSearchInput');
  var result = {
    width: window.innerWidth,
    docClient: doc.clientWidth,
    docScroll: doc.scrollWidth,
    hscroll: doc.scrollWidth > doc.clientWidth,
    drawerWidth: drawer ? Math.round(drawer.getBoundingClientRect().width) : -1,
    drawerLeft: drawer ? Math.round(drawer.getBoundingClientRect().left) : -1,
    drawerRight: drawer ? Math.round(drawer.getBoundingClientRect().right) : -1,
    drawerDisplay: drawer ? getComputedStyle(drawer).display : 'none',
    searchWidth: search ? Math.round(search.getBoundingClientRect().width) : -1,
    menuToggleDisplay: getComputedStyle(document.getElementById('menuToggle')).display,
    navWrapDisplay: getComputedStyle(document.getElementById('navWrap')).display,
    catItems: document.querySelectorAll('#mobileCategoriesList .mobile-submenu-item').length,
    accountItems: document.querySelectorAll('#mobileAccountList .mobile-submenu-item').length,
    cartBadge: (document.getElementById('cart-count-mobile') || {}).textContent || '',
    headerOverflowX: getComputedStyle(document.getElementById('siteHeader')).overflowX
  };
  var pre = document.getElementById('results');
  var d = document.createElement('div');
  d.textContent = 'MEASURE ' + (label||'') + ' ' + JSON.stringify(result);
  pre.appendChild(d);
}
__MEASURE('closed');
openDrawer();
__MEASURE('open');
var catBtn = document.getElementById('mobileCatToggle');
catBtn.setAttribute('aria-expanded', 'true');
var catList = document.getElementById('mobileCategoriesList');
catList.style.maxHeight = catList.scrollHeight + 'px';
var accBtn = document.getElementById('mobileAccountToggle');
accBtn.setAttribute('aria-expanded', 'true');
var accList = document.getElementById('mobileAccountList');
accList.style.maxHeight = accList.scrollHeight + 'px';
setTimeout(function(){
  __MEASURE('open-expanded');
  var d = document.getElementById('mobileNavDrawer');
  var o = document.getElementById('mobileOverlay');
  if (d) { d.classList.remove('open'); d.style.top=''; d.style.right=''; }
  if (o) { o.classList.remove('open'); }
}, 80);
</script>
"""


def build_harness(out_path, user=None):
    css, html, script = render_header(user)
    out = (
        '<!DOCTYPE html><html><head>\n'
        '<meta charset="utf-8">\n'
        '<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.css">\n'
        '<style>body{margin:0;background:#eee;}#results{display:none;white-space:pre-wrap;word-break:break-all;} '
        + css + '</style>\n'
        '</head><body>\n' + html + '\n<pre id="results"></pre>\n'
        '<script>' + script + '</script>\n'
        '<script>window.__ghErr=null;window.addEventListener("error",function(e){window.__ghErr=(window.__ghErr?window.__ghErr+" | ":"")+e.message;});</script>\n'
        + MEASURE + '\n</body></html>'
    )
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(out)
    print('harness written to', out_path)


if __name__ == '__main__':
    mode = sys.argv[1] if len(sys.argv) > 1 else 'anon'
    out_path = sys.argv[2] if len(sys.argv) > 2 else os.path.join('.gh_test', 'harness_anon.html')
    user = None
    if mode == 'auth':
        user = User(username='testuser', first_name='Test')
    build_harness(out_path, user=user)
