// ── Scanner Controls ─────────────────────────────────────────

function scannerAction(action) {
    fetch(`/api/scanner/${action}`, { method: 'POST' })
        .then(r => r.json())
        .then(data => {
            showToast(`Scanner: ${data.status}`);
            // Refresh stats after action
            if (typeof refreshStats === 'function') {
                setTimeout(refreshStats, 500);
            }
        })
        .catch(err => showToast('Error: ' + err.message));
}

// ── Job Actions ──────────────────────────────────────────────

function updateJobStatus(jobId, status) {
    fetch(`/api/jobs/${jobId}/status`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status })
    })
    .then(r => r.json())
    .then(data => {
        showToast(`Job ${data.new_status}`);
        setTimeout(() => location.reload(), 500);
    })
    .catch(err => showToast('Error: ' + err.message));
}

// ── Toast Notification ───────────────────────────────────────

function showToast(message) {
    // Remove existing toast
    const existing = document.getElementById('toast');
    if (existing) existing.remove();

    const toast = document.createElement('div');
    toast.id = 'toast';
    toast.textContent = message;
    Object.assign(toast.style, {
        position: 'fixed',
        bottom: '24px',
        right: '24px',
        background: '#1a1d27',
        border: '1px solid #2a2e3d',
        color: '#e4e6ed',
        padding: '12px 20px',
        borderRadius: '8px',
        fontSize: '14px',
        boxShadow: '0 4px 12px rgba(0,0,0,.4)',
        zIndex: '9999',
        transition: 'opacity 0.3s',
    });
    document.body.appendChild(toast);
    setTimeout(() => {
        toast.style.opacity = '0';
        setTimeout(() => toast.remove(), 300);
    }, 2500);
}
