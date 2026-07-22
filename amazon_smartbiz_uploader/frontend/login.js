document.addEventListener('DOMContentLoaded', () => {
    // If already logged in, redirect
    if (localStorage.getItem('access_token')) {
        window.location.href = 'index.html';
    }
    
    const loginForm = document.getElementById('login-form');
    const errorDiv = document.getElementById('login-error');
    
    loginForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        const username = document.getElementById('username').value;
        const password = document.getElementById('password').value;
        const btn = loginForm.querySelector('button');
        
        btn.textContent = 'Logging in...';
        btn.disabled = true;
        errorDiv.style.display = 'none';
        
        try {
            const formData = new URLSearchParams();
            formData.append('username', username);
            formData.append('password', password);
            
            const apiBase = (typeof CONFIG !== 'undefined' && CONFIG.API_BASE_URL) ? CONFIG.API_BASE_URL : 'http://localhost:8000';
            const response = await fetch(`${apiBase}/api/login`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded'
                },
                body: formData
            });
            
            if (!response.ok) {
                throw new Error('Invalid credentials');
            }
            
            const data = await response.json();
            localStorage.setItem('access_token', data.access_token);
            window.location.href = 'index.html';
            
        } catch (error) {
            errorDiv.textContent = error.message || 'Login failed';
            errorDiv.style.display = 'block';
        } finally {
            btn.textContent = 'Login';
            btn.disabled = false;
        }
    });
});
