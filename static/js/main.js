[file name]: main.js
[file content begin]
document.addEventListener('DOMContentLoaded', function() {
    const addToCartButtons = document.querySelectorAll('.add-to-cart-btn');
    
    addToCartButtons.forEach(button => {
        button.addEventListener('click', function() {
            const productId = this.dataset.productId;
            
            const formData = new FormData();
            formData.append('quantity', 1);
            
            fetch(`/add_to_cart/${productId}`, {
                method: 'POST',
                body: formData
            })
            .then(response => {
                if (response.redirected) {
                    window.location.href = response.url;
                    return;
                }
                return response.json();
            })
            .then(data => {
                if (data && data.success) {
                    showNotification('Product added to cart!', 'success');
                    updateCartCount();
                } else if (data && data.message) {
                    showNotification(data.message, 'error');
                }
            })
            .catch(error => {
                console.error('Error:', error);
                showNotification('An error occurred', 'error');
            });
        });
    });
    
    function showNotification(message, type) {
        const notification = document.createElement('div');
        notification.className = `alert alert-${type === 'success' ? 'success' : 'danger'} position-fixed`;
        notification.style.cssText = 'top: 100px; right: 20px; z-index: 9999; min-width: 300px;';
        notification.innerHTML = `
            ${message}
            <button type="button" class="btn-close" onclick="this.parentElement.remove()"></button>
        `;
        document.body.appendChild(notification);
        
        setTimeout(() => {
            notification.remove();
        }, 3000);
    }
    
    function updateCartCount() {
        const cartBadge = document.getElementById('cartCount');
        if (cartBadge) {
            const currentCount = parseInt(cartBadge.textContent) || 0;
            cartBadge.textContent = currentCount + 1;
            cartBadge.style.display = 'flex';
        }
    }
    
    const scrollElements = document.querySelectorAll('.product-card, .feature-card, .category-card');
    
    const elementInView = (el, offset = 100) => {
        const elementTop = el.getBoundingClientRect().top;
        return elementTop <= (window.innerHeight - offset);
    };
    
    const displayScrollElement = (element) => {
        element.style.opacity = '1';
        element.style.transform = 'translateY(0)';
    };
    
    const hideScrollElement = (element) => {
        element.style.opacity = '0';
        element.style.transform = 'translateY(30px)';
    };
    
    const handleScrollAnimation = () => {
        scrollElements.forEach((el) => {
            if (elementInView(el, 100)) {
                displayScrollElement(el);
            }
        });
    };
    
    scrollElements.forEach((el) => {
        el.style.transition = 'all 0.6s ease';
        hideScrollElement(el);
    });
    
    window.addEventListener('scroll', handleScrollAnimation);
    handleScrollAnimation();
});
[file content end]