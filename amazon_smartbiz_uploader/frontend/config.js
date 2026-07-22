// Centralized API Configuration for SmartBiz Uploader
// Change API_BASE_URL to your Railway deployment URL when backend is live!
const CONFIG = {
    // Replace the live URL below after deploying your backend to Railway
    // Example: 'https://amazon-smartbiz-backend.up.railway.app'
    API_BASE_URL: window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
        ? 'http://localhost:8000'
        : 'https://YOUR_RAILWAY_BACKEND_URL.up.railway.app'
};
