/**
 * Login page JavaScript
 */

document.addEventListener('DOMContentLoaded', function() {
    const loginForm = document.getElementById('loginForm');
    const usernameInput = document.getElementById('username');
    const passwordInput = document.getElementById('password');
    const loginButton = document.getElementById('loginButton');
    const buttonText = document.getElementById('buttonText');
    const buttonSpinner = document.getElementById('buttonSpinner');
    const errorMessage = document.getElementById('errorMessage');
    const errorText = document.getElementById('errorText');

    // Check if already logged in
    checkSession();

    // Handle form submission
    loginForm.addEventListener('submit', async function(e) {
        e.preventDefault();
        
        const username = usernameInput.value.trim();
        const password = passwordInput.value;

        if (!username || !password) {
            showError('Please enter both username and password');
            return;
        }

        // Show loading state
        setLoading(true);
        hideError();

        try {
            const response = await fetch('/api/auth/login', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ username, password })
            });

            const data = await response.json();

            if (response.ok && data.success) {
                // Login successful
                console.log('✅ Login successful:', data.user);
                
                // Redirect to dashboard
                window.location.href = '/dashboard.html';
            } else {
                // Login failed
                showError(data.error || 'Login failed. Please try again.');
                setLoading(false);
            }
        } catch (error) {
            console.error('Login error:', error);
            showError('Network error. Please check your connection and try again.');
            setLoading(false);
        }
    });

    // Enter key on password field
    passwordInput.addEventListener('keypress', function(e) {
        if (e.key === 'Enter') {
            loginForm.dispatchEvent(new Event('submit'));
        }
    });

    /**
     * Check if user is already logged in
     */
    async function checkSession() {
        try {
            const response = await fetch('/api/auth/check');
            const data = await response.json();

            if (data.authenticated) {
                // Already logged in, redirect to dashboard
                console.log('✅ Already logged in, redirecting...');
                window.location.href = '/dashboard.html';
            }
        } catch (error) {
            console.error('Session check error:', error);
        }
    }

    /**
     * Show error message
     */
    function showError(message) {
        errorText.textContent = message;
        errorMessage.classList.remove('hidden');
        
        // Auto-hide after 5 seconds
        setTimeout(() => {
            hideError();
        }, 5000);
    }

    /**
     * Hide error message
     */
    function hideError() {
        errorMessage.classList.add('hidden');
    }

    /**
     * Set loading state
     */
    function setLoading(loading) {
        if (loading) {
            loginButton.disabled = true;
            buttonText.classList.add('hidden');
            buttonSpinner.classList.remove('hidden');
            usernameInput.disabled = true;
            passwordInput.disabled = true;
        } else {
            loginButton.disabled = false;
            buttonText.classList.remove('hidden');
            buttonSpinner.classList.add('hidden');
            usernameInput.disabled = false;
            passwordInput.disabled = false;
        }
    }

    // Focus username field on load
    usernameInput.focus();
});

