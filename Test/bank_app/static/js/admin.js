// Admin Panel JavaScript

// CSRF token helper
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

// Ripple effect for buttons
document.addEventListener('click', function(e) {
    if (e.target.classList.contains('btn-admin')) {
        const button = e.target;
        const rect = button.getBoundingClientRect();
        const ripple = document.createElement('span');
        const size = Math.max(rect.width, rect.height);
        const x = e.clientX - rect.left - size / 2;
        const y = e.clientY - rect.top - size / 2;
        
        ripple.style.width = ripple.style.height = size + 'px';
        ripple.style.left = x + 'px';
        ripple.style.top = y + 'px';
        ripple.classList.add('admin-ripple');
        
        button.appendChild(ripple);
        
        setTimeout(() => ripple.remove(), 600);
    }
});

// Add ripple CSS
const style = document.createElement('style');
style.textContent = `
    .admin-ripple {
        position: absolute;
        border-radius: 50%;
        background: rgba(255, 255, 255, 0.3);
        transform: scale(0);
        animation: admin-ripple 0.6s ease-out;
        pointer-events: none;
    }
    
    @keyframes admin-ripple {
        to {
            transform: scale(4);
            opacity: 0;
        }
    }
`;
document.head.appendChild(style);

// Toast notifications
function adminToast(message, type = 'success') {
    const toast = document.createElement('div');
    toast.className = `admin-toast admin-toast-${type}`;
    toast.textContent = message;
    
    document.body.appendChild(toast);
    
    setTimeout(() => toast.classList.add('admin-toast-show'), 10);
    setTimeout(() => {
        toast.classList.remove('admin-toast-show');
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

// Add toast CSS
const toastStyle = document.createElement('style');
toastStyle.textContent = `
    .admin-toast {
        position: fixed;
        bottom: 24px;
        right: 24px;
        padding: 16px 24px;
        border-radius: var(--radius-sm);
        background: var(--card);
        border: 1px solid var(--border);
        color: var(--text);
        font-size: 0.9rem;
        font-weight: 500;
        z-index: 1000;
        opacity: 0;
        transform: translateY(20px);
        transition: all 0.3s;
    }
    
    .admin-toast-show {
        opacity: 1;
        transform: translateY(0);
    }
    
    .admin-toast-success {
        border-color: var(--green);
    }
    
    .admin-toast-success::before {
        content: '✓ ';
        color: var(--green);
    }
    
    .admin-toast-error {
        border-color: var(--red);
    }
    
    .admin-toast-error::before {
        content: '✗ ';
        color: var(--red);
    }
`;
document.head.appendChild(toastStyle);

// Confirm dialog with custom styling
function adminConfirm(message) {
    return confirm(message);
}

// Table row highlight on hover
document.querySelectorAll('.admin-table tbody tr').forEach(row => {
    row.addEventListener('mouseenter', function() {
        this.style.background = 'rgba(255, 255, 255, 0.03)';
    });
    row.addEventListener('mouseleave', function() {
        this.style.background = '';
    });
});

// Sidebar navigation active state
const currentPath = window.location.pathname;
document.querySelectorAll('.sidebar-nav .nav-item').forEach(item => {
    if (item.getAttribute('href') === currentPath) {
        item.classList.add('active');
    }
});

// Mobile sidebar toggle
const mobileMenuButton = document.createElement('button');
mobileMenuButton.className = 'admin-mobile-menu';
mobileMenuButton.innerHTML = '☰';
mobileMenuButton.style.display = 'none';

// Add mobile menu CSS
const mobileStyle = document.createElement('style');
mobileStyle.textContent = `
    .admin-mobile-menu {
        position: fixed;
        top: 20px;
        left: 20px;
        z-index: 200;
        width: 44px;
        height: 44px;
        border-radius: 8px;
        background: var(--card);
        border: 1px solid var(--border);
        color: var(--text);
        font-size: 1.2rem;
        cursor: pointer;
        display: none;
    }
    
    @media (max-width: 768px) {
        .admin-mobile-menu {
            display: flex;
            align-items: center;
            justify-content: center;
        }
        
        .admin-sidebar {
            transform: translateX(-100%);
            transition: transform 0.3s;
        }
        
        .admin-sidebar.open {
            transform: translateX(0);
        }
        
        .admin-main {
            margin-left: 0;
        }
    }
`;
document.head.appendChild(mobileStyle);

document.body.appendChild(mobileMenuButton);

mobileMenuButton.addEventListener('click', () => {
    document.querySelector('.admin-sidebar').classList.toggle('open');
});

// Close sidebar when clicking outside on mobile
document.addEventListener('click', (e) => {
    if (window.innerWidth <= 768) {
        const sidebar = document.querySelector('.admin-sidebar');
        const menuButton = document.querySelector('.admin-mobile-menu');
        
        if (!sidebar.contains(e.target) && !menuButton.contains(e.target) && sidebar.classList.contains('open')) {
            sidebar.classList.remove('open');
        }
    }
});
