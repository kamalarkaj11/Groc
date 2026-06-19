document.addEventListener('DOMContentLoaded', function () {
    var csrfToken = document.querySelector('[name=csrfmiddlewaretoken]');
    if (csrfToken) csrfToken = csrfToken.value;
    else {
        var meta = document.querySelector('meta[name="csrf-token"]');
        csrfToken = meta ? meta.getAttribute('content') : '';
    }

    function getCSRF() {
        var cookie = document.cookie.match(/csrftoken=([^;]+)/);
        return cookie ? cookie[1] : csrfToken;
    }

    function escapeHtml(text) {
        var d = document.createElement('div');
        d.appendChild(document.createTextNode(text || ''));
        return d.innerHTML;
    }

    function formatTimestamp(ts) {
        if (!ts) return 'N/A';
        try { return new Date(ts).toLocaleString(); }
        catch (e) { return ts; }
    }

    var toastContainer = document.getElementById('toastContainer');

    function showToast(message, type) {
        if (!toastContainer) return;
        var iconMap = {
            success: 'bi-check-circle-fill',
            error: 'bi-x-circle-fill',
            info: 'bi-info-circle-fill',
            warning: 'bi-exclamation-triangle-fill',
        };
        var toast = document.createElement('div');
        toast.className = 'api-toast api-toast-' + type;
        toast.innerHTML = '<i class="bi ' + (iconMap[type] || iconMap.info) + '"></i><span>' + escapeHtml(message) + '</span>';
        toastContainer.appendChild(toast);
        setTimeout(function () {
            toast.classList.add('toast-out');
            setTimeout(function () { toast.remove(); }, 300);
        }, 4000);
    }

    /* ==========================================================================
       Test Connection
       ========================================================================== */
    document.querySelectorAll('.api-action-test').forEach(function (btn) {
        btn.addEventListener('click', function () {
            var id = this.getAttribute('data-id');
            var origHTML = this.innerHTML;
            this.disabled = true;
            this.innerHTML = '<span class="api-spinner"></span>';

            fetch('/api-settings/' + id + '/test/', {
                method: 'GET',
                headers: {
                    'X-Requested-With': 'XMLHttpRequest',
                    'Accept': 'application/json',
                },
                credentials: 'same-origin',
            })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                showTestResultModal(data);
                if (data.success) {
                    showToast('API connected successfully!', 'success');
                } else {
                    showToast(data.message || 'Connection test failed.', 'error');
                }
                updateRowConnectionStatus(id, data.status, data.message);
            })
            .catch(function (err) {
                showToast('Request failed: ' + err.message, 'error');
            })
            .finally(function () {
                btn.disabled = false;
                btn.innerHTML = origHTML;
            });
        });
    });

    function updateRowConnectionStatus(id, status, message) {
        var row = document.querySelector('tr[data-id="' + id + '"]');
        if (!row) return;
        var badge = row.querySelector('.api-conn-badge');
        if (badge) {
            badge.className = 'api-conn-badge api-conn-' + status;
            badge.textContent = message || status;
        }
    }

    function showTestResultModal(data) {
        var modal = document.getElementById('testResultModal');
        var content = document.getElementById('testResultContent');
        if (!modal || !content) return;

        var iconClass, colorClass, heading;
        if (data.success) {
            iconClass = 'bi-check-circle-fill';
            colorClass = 'success';
            heading = 'Connected';
        } else if (data.status === 'timeout') {
            iconClass = 'bi-clock-fill';
            colorClass = 'warning';
            heading = 'Timeout';
        } else if (data.status === 'auth_failed') {
            iconClass = 'bi-shield-x-fill';
            colorClass = 'error';
            heading = 'Authentication Failed';
        } else if (data.status === 'unavailable') {
            iconClass = 'bi-wifi-off-fill';
            colorClass = 'error';
            heading = 'Service Unavailable';
        } else {
            iconClass = 'bi-x-circle-fill';
            colorClass = 'error';
            heading = 'Connection Failed';
        }

        content.innerHTML =
            '<div class="api-test-result-content">' +
                '<div class="api-test-result-icon ' + colorClass + '">' +
                    '<i class="bi ' + iconClass + '"></i>' +
                '</div>' +
                '<h4>' + escapeHtml(heading) + '</h4>' +
                '<p>' + escapeHtml(data.message || '') + '</p>' +
                '<div class="api-test-result-meta">' +
                    '<span><i class="bi bi-speedometer2"></i> Status: ' + (data.status_code || 'N/A') + '</span>' +
                    '<span><i class="bi bi-clock"></i> ' + formatTimestamp(data.timestamp) + '</span>' +
                '</div>' +
            '</div>';

        modal.style.display = 'flex';
    }

    var closeTestModal = document.getElementById('closeTestModal');
    if (closeTestModal) {
        closeTestModal.addEventListener('click', function () {
            document.getElementById('testResultModal').style.display = 'none';
        });
    }

    /* ==========================================================================
       Toggle Status
       ========================================================================== */
    document.querySelectorAll('.api-action-toggle').forEach(function (btn) {
        btn.addEventListener('click', function () {
            var id = this.getAttribute('data-id');
            var origHTML = this.innerHTML;
            this.disabled = true;
            this.innerHTML = '<span class="api-spinner"></span>';

            fetch('/api-settings/' + id + '/toggle-status/', {
                method: 'POST',
                headers: {
                    'X-CSRFToken': getCSRF(),
                    'X-Requested-With': 'XMLHttpRequest',
                    'Accept': 'application/json',
                },
                credentials: 'same-origin',
            })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (data.success) {
                    var row = document.querySelector('tr[data-id="' + id + '"]');
                    if (row) {
                        var badge = row.querySelector('.api-status-badge');
                        if (badge) {
                            badge.className = 'api-status-badge api-status-' + data.status;
                            badge.textContent = data.status === 'active' ? 'Active' : 'Inactive';
                        }
                    }
                    btn.innerHTML = '<i class="bi bi-toggle-' + (data.status === 'active' ? 'on' : 'off') + '"></i>';
                    showToast('Status changed to ' + (data.status === 'active' ? 'Active' : 'Inactive'), 'success');
                }
            })
            .catch(function (err) {
                showToast('Failed to toggle status: ' + err.message, 'error');
                btn.innerHTML = origHTML;
            })
            .finally(function () {
                btn.disabled = false;
            });
        });
    });

    /* ==========================================================================
       Reveal Key
       ========================================================================== */
    document.querySelectorAll('.api-key-reveal-btn').forEach(function (btn) {
        btn.addEventListener('click', function () {
            var id = this.getAttribute('data-id');
            var keyEl = document.getElementById('key-' + id);
            var icon = this.querySelector('i');

            if (keyEl && keyEl.getAttribute('data-revealed') === 'true') {
                keyEl.textContent = keyEl.getAttribute('data-masked');
                keyEl.setAttribute('data-revealed', 'false');
                icon.className = 'bi bi-eye';
                return;
            }

            fetch('/api-settings/' + id + '/reveal/', {
                method: 'GET',
                headers: {
                    'X-Requested-With': 'XMLHttpRequest',
                    'Accept': 'application/json',
                },
                credentials: 'same-origin',
            })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (data.success && keyEl) {
                    keyEl.setAttribute('data-masked', keyEl.textContent);
                    keyEl.textContent = data.key;
                    keyEl.setAttribute('data-revealed', 'true');
                    icon.className = 'bi bi-eye-slash';
                    showToast('API key revealed. This action was logged.', 'info');
                }
            })
            .catch(function (err) {
                showToast('Failed to reveal key: ' + err.message, 'error');
            });
        });
    });

    /* ==========================================================================
       Delete Modal
       ========================================================================== */
    var deleteModal = document.getElementById('deleteModal');
    var deleteForm = document.getElementById('deleteForm');
    var deleteApiName = document.getElementById('deleteApiName');

    document.querySelectorAll('.api-action-delete').forEach(function (btn) {
        btn.addEventListener('click', function () {
            var id = this.getAttribute('data-id');
            var name = this.getAttribute('data-name');
            if (!deleteModal || !deleteForm || !deleteApiName) return;

            deleteApiName.textContent = name;
            deleteForm.action = '/api-settings/' + id + '/delete/';
            deleteModal.style.display = 'flex';
        });
    });

    var closeDeleteModal = document.getElementById('closeDeleteModal');
    if (closeDeleteModal) {
        closeDeleteModal.addEventListener('click', function () {
            deleteModal.style.display = 'none';
        });
    }

    var cancelDelete = document.getElementById('cancelDelete');
    if (cancelDelete) {
        cancelDelete.addEventListener('click', function () {
            deleteModal.style.display = 'none';
        });
    }

    /* ==========================================================================
       Close modals on overlay click
       ========================================================================== */
    document.querySelectorAll('.api-modal-overlay').forEach(function (overlay) {
        overlay.addEventListener('click', function (e) {
            if (e.target === overlay) {
                overlay.style.display = 'none';
            }
        });
    });

    /* ==========================================================================
       Escape key closes modals
       ========================================================================== */
    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') {
            document.querySelectorAll('.api-modal-overlay').forEach(function (m) {
                m.style.display = 'none';
            });
        }
    });

    /* ==========================================================================
       Real-time Status Refresh
       ========================================================================== */
    var refreshInterval = null;
    var refreshBtn = document.getElementById('refreshStatusBtn');

    function refreshStatuses() {
        fetch('/api-settings/status/', {
            headers: {
                'X-Requested-With': 'XMLHttpRequest',
                'Accept': 'application/json',
            },
            credentials: 'same-origin',
        })
        .then(function (r) { return r.json(); })
        .then(function (data) {
            if (!data.apis) return;
            data.apis.forEach(function (api) {
                var row = document.querySelector('tr[data-id="' + api.id + '"]');
                if (!row) return;

                var connBadge = row.querySelector('.api-conn-badge');
                if (connBadge) {
                    connBadge.className = 'api-conn-badge api-conn-' + api.connection_status;
                    connBadge.textContent = api.connection_status.replace('_', ' ');
                    connBadge.textContent = api.connection_status.charAt(0).toUpperCase() + api.connection_status.slice(1).replace('_', ' ');
                }

                var statusBadge = row.querySelector('.api-status-badge');
                if (statusBadge) {
                    statusBadge.className = 'api-status-badge api-status-' + api.status;
                    statusBadge.textContent = api.status === 'active' ? 'Active' : 'Inactive';
                }
            });

            updateStats(data.apis);
        })
        .catch(function () {});
    }

    function updateStats(apis) {
        var total = apis.length;
        var active = 0, inactive = 0, failed = 0, connected = 0;
        apis.forEach(function (a) {
            if (a.status === 'active') active++;
            else inactive++;
            if (a.connection_status === 'failed') failed++;
            if (a.connection_status === 'connected') connected++;
        });

        setText('statTotal', total);
        setText('statActive', active);
        setText('statInactive', inactive);
        setText('statFailed', failed);
        setText('statConnected', connected);
    }

    function setText(id, val) {
        var el = document.getElementById(id);
        if (el) el.textContent = val;
    }

    if (refreshBtn) {
        refreshBtn.addEventListener('click', function () {
            var origHTML = this.innerHTML;
            this.disabled = true;
            this.innerHTML = '<span class="api-spinner"></span>';
            refreshStatuses();
            setTimeout(function () {
                refreshBtn.disabled = false;
                refreshBtn.innerHTML = origHTML;
            }, 1500);
        });
    }

    /* ==========================================================================
       Dark Mode Toggle
       ========================================================================== */
    var darkToggle = document.getElementById('darkModeToggle');
    var page = document.getElementById('apiSettingsPage');

    function applyDarkMode(on) {
        if (page) page.classList.toggle('api-dark', on);
        localStorage.setItem('api-dark-mode', on ? '1' : '0');
        if (darkToggle) {
            darkToggle.querySelector('i').className = on ? 'bi bi-sun-fill' : 'bi bi-moon-fill';
        }
    }

    if (darkToggle) {
        var saved = localStorage.getItem('api-dark-mode');
        if (saved === '1') applyDarkMode(true);

        darkToggle.addEventListener('click', function () {
            var isDark = page && page.classList.contains('api-dark');
            applyDarkMode(!isDark);
        });
    }

    /* ==========================================================================
       Auto-refresh every 60 seconds
       ========================================================================== */
    if (document.querySelector('.api-table')) {
        refreshInterval = setInterval(refreshStatuses, 60000);
    }
});
