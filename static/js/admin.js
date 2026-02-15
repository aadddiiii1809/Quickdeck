// static/admin/js/admin.js
// Admin Utility Functions

// Show notification
function showNotification(message, type = 'success') {
    // Remove existing notifications
    const existingNotifications = document.querySelectorAll('.notification');
    existingNotifications.forEach(notification => notification.remove());

    const notification = document.createElement('div');
    notification.className = `notification ${type}`;
    notification.innerHTML = `
        <i class="fas fa-${type === 'success' ? 'check-circle' : 'exclamation-circle'}"></i>
        <span>${message}</span>
    `;

    // Add styles if not already added
    if (!document.querySelector('#notification-styles')) {
        const styles = document.createElement('style');
        styles.id = 'notification-styles';
        styles.textContent = `
            .notification {
                position: fixed;
                top: 100px;
                right: 30px;
                background: white;
                padding: 15px 25px;
                border-radius: 10px;
                box-shadow: 0 5px 15px rgba(0,0,0,0.2);
                display: flex;
                align-items: center;
                gap: 15px;
                z-index: 3000;
                animation: slideIn 0.3s ease forwards;
                border-left: 4px solid #4CAF50;
            }
            .notification.success { border-left-color: #4CAF50; }
            .notification.error { border-left-color: #F44336; }
            .notification.warning { border-left-color: #FF9800; }
            .notification i { font-size: 20px; }
            .notification.success i { color: #4CAF50; }
            .notification.error i { color: #F44336; }
            @keyframes slideIn {
                from { transform: translateX(100%); opacity: 0; }
                to { transform: translateX(0); opacity: 1; }
            }
            @keyframes slideOut {
                from { transform: translateX(0); opacity: 1; }
                to { transform: translateX(100%); opacity: 0; }
            }
        `;
        document.head.appendChild(styles);
    }

    document.body.appendChild(notification);

    // Auto remove after 3 seconds
    setTimeout(() => {
        notification.style.animation = 'slideOut 0.3s ease forwards';
        setTimeout(() => notification.remove(), 300);
    }, 3000);
}

// API request helper
async function makeRequest(url, method = 'GET', data = null) {
    const options = {
        method,
        headers: {
            'Content-Type': 'application/json',
            'X-Requested-With': 'XMLHttpRequest'
        },
        credentials: 'same-origin'
    };

    if (data) {
        options.body = JSON.stringify(data);
    }

    try {
        const response = await fetch(url, options);

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const result = await response.json();

        if (!result.success) {
            throw new Error(result.message || 'Request failed');
        }

        return result;
    } catch (error) {
        console.error('Request failed:', error);
        showNotification(error.message || 'Request failed. Please try again.', 'error');
        return null;
    }
}

// Confirm dialog
function showConfirm(message, callback) {
    const confirmed = confirm(message);
    if (confirmed && callback) {
        callback();
    }
    return confirmed;
}

// Load dashboard stats
async function loadDashboardStats() {
    try {
        const result = await makeRequest('/admin/api/stats');
        if (result) {
            // Update UI with stats
            const elements = {
                'total-products': result.total_products,
                'total-orders': result.total_orders,
                'total-customers': result.total_customers,
                'total-revenue': '₹' + result.total_revenue.toLocaleString()
            };

            Object.entries(elements).forEach(([id, value]) => {
                const element = document.getElementById(id);
                if (element) element.textContent = value;
            });
        }
    } catch (error) {
        console.error('Error loading stats:', error);
    }
}

// Initialize admin features
document.addEventListener('DOMContentLoaded', function() {
    // Set current date
    const now = new Date();
    const options = { day: 'numeric', month: 'long', year: 'numeric' };
    const dateElement = document.getElementById('current-date');
    if (dateElement) {
        dateElement.textContent = now.toLocaleDateString('en-GB', options);
    }

    // Logout confirmation
    const logoutBtn = document.querySelector('.logout a');
    if (logoutBtn) {
        logoutBtn.addEventListener('click', function(e) {
            if (!confirm('Are you sure you want to logout?')) {
                e.preventDefault();
            }
        });
    }
});