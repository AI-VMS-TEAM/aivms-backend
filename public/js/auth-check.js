/**
 * Authentication check script
 * Include this in all protected pages to ensure user is logged in
 */

(async function() {
    // Skip auth check for login page
    if (window.location.pathname === '/login.html') {
        return;
    }

    try {
        const response = await fetch('/api/auth/check');
        const data = await response.json();

        if (!data.authenticated) {
            // Not logged in, redirect to login page
            console.log('❌ Not authenticated, redirecting to login...');
            window.location.href = '/login.html';
            return;
        }

        // User is authenticated
        console.log('✅ Authenticated as:', data.user.username, `(${data.user.role})`);
        
        // Store user info globally for other scripts to use
        window.currentUser = data.user;

        // Dispatch event that authentication is complete
        window.dispatchEvent(new CustomEvent('auth-ready', { detail: data.user }));

    } catch (error) {
        console.error('❌ Authentication check failed:', error);
        // On error, redirect to login to be safe
        window.location.href = '/login.html';
    }
})();

