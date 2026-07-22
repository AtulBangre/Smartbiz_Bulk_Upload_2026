const apiBaseUrl = (typeof CONFIG !== 'undefined' && CONFIG.API_BASE_URL) ? CONFIG.API_BASE_URL : 'http://localhost:8000';
const API_BASE = `${apiBaseUrl}/api`;

// Auth Check
const token = localStorage.getItem('access_token');
if (!token) {
    window.location.href = 'login.html';
}

const headers = {
    'Authorization': `Bearer ${token}`
};
const jsonHeaders = {
    ...headers,
    'Content-Type': 'application/json'
};

document.addEventListener('DOMContentLoaded', () => {
    
    // Elements
    const logoutBtn = document.getElementById('logout-btn');
    const tabBtns = document.querySelectorAll('.tab-btn');
    const tabContents = document.querySelectorAll('.tab-content');
    
    const draftTableBody = document.getElementById('draft-table-body');
    const draftCountSpan = document.getElementById('draft-count');
    const addItemForm = document.getElementById('add-item-form');
    const clearDraftBtn = document.getElementById('clear-draft-btn');
    const generateBtn = document.getElementById('generate-btn');
    const sheetNameInput = document.getElementById('sheet-name');
    const uploadBtn = document.getElementById('upload-btn');
    const excelUploadInput = document.getElementById('excel-upload');
    
    const historyTableBody = document.getElementById('history-table-body');

    // Logout
    logoutBtn.addEventListener('click', () => {
        localStorage.removeItem('access_token');
        window.location.href = 'login.html';
    });

    // Tabs
    tabBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            tabBtns.forEach(b => b.classList.remove('active'));
            tabContents.forEach(c => c.classList.remove('active'));
            
            btn.classList.add('active');
            document.getElementById(btn.dataset.target).classList.add('active');
            
            if (btn.dataset.target === 'history-tab') {
                loadHistory();
            }
        });
    });

    // --- DRAFT LOGIC ---
    
    async function loadDrafts() {
        try {
            const res = await fetch(`${API_BASE}/draft`, { headers });
            if (res.status === 401) return logout();
            const items = await res.json();
            
            draftTableBody.innerHTML = '';
            draftCountSpan.textContent = items.length;
            
            items.forEach(item => {
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td title="${item.url}">${item.url.substring(0, 30)}...</td>
                    <td>${item.custom_sku || '-'}</td>
                    <td>${item.business_category} / ${item.product_category}</td>
                    <td>${item.variant_relationship || '-'}</td>
                    <td>
                        <button class="remove-btn" data-id="${item._id}" style="color:red; background:none; border:none; cursor:pointer;">Delete</button>
                    </td>
                `;
                draftTableBody.appendChild(tr);
            });
            
            // Bind delete buttons
            document.querySelectorAll('.remove-btn').forEach(btn => {
                btn.addEventListener('click', async (e) => {
                    const id = e.target.dataset.id;
                    if(confirm("Delete this item?")) {
                        await fetch(`${API_BASE}/draft/item/${id}`, { method: 'DELETE', headers });
                        loadDrafts();
                    }
                });
            });
            
        } catch (e) {
            console.error("Failed to load drafts", e);
        }
    }

    // Add manual item
    addItemForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const item = {
            url: document.getElementById('add-url').value,
            custom_sku: document.getElementById('add-sku').value,
            business_category: document.getElementById('add-business-cat').value,
            product_category: document.getElementById('add-product-cat').value,
            variant_relationship: document.getElementById('add-variant').value,
            size: document.getElementById('add-size').value,
            color_name: document.getElementById('add-color').value,
            best_seller: document.getElementById('add-best-seller').value,
        };
        
        try {
            const res = await fetch(`${API_BASE}/draft/item`, {
                method: 'POST',
                headers: jsonHeaders,
                body: JSON.stringify(item)
            });
            if (res.ok) {
                addItemForm.reset();
                loadDrafts();
            }
        } catch (e) {
            alert("Error adding item");
        }
    });

    // Clear Draft
    clearDraftBtn.addEventListener('click', async () => {
        if(confirm("Are you sure you want to clear the entire draft?")) {
            await fetch(`${API_BASE}/draft/clear`, { method: 'DELETE', headers });
            loadDrafts();
        }
    });
    
    // Download Draft Template
    const downloadTemplateBtn = document.getElementById('download-template-btn');
    if (downloadTemplateBtn) {
        downloadTemplateBtn.addEventListener('click', () => {
            window.open(`${API_BASE}/draft/template`, '_blank');
        });
    }

    // Upload Excel Draft
    uploadBtn.addEventListener('click', async () => {
        const file = excelUploadInput.files[0];
        if (!file) return alert("Please select an Excel file first.");
        
        const formData = new FormData();
        formData.append("file", file);
        
        uploadBtn.textContent = "Uploading...";
        uploadBtn.disabled = true;
        
        try {
            const res = await fetch(`${API_BASE}/draft/upload-excel`, {
                method: 'POST',
                headers: headers, // Do NOT set Content-Type for FormData, let browser handle boundary
                body: formData
            });
            const data = await res.json();
            if (res.ok) {
                alert(data.message);
                excelUploadInput.value = '';
                loadDrafts();
            } else {
                alert(data.detail || "Upload failed");
            }
        } catch (e) {
            alert("Upload error: " + e.message);
        } finally {
            uploadBtn.textContent = "Upload to Draft";
            uploadBtn.disabled = false;
        }
    });

    // Generate Excel
    generateBtn.addEventListener('click', async () => {
        const sheetName = sheetNameInput.value.trim();
        if (!sheetName) return alert("Please enter a Final Sheet Name.");
        if (draftCountSpan.textContent === "0") return alert("Your draft is empty.");
        
        setLoading(true);
        
        try {
            const res = await fetch(`${API_BASE}/generate`, {
                method: 'POST',
                headers: jsonHeaders,
                body: JSON.stringify({ sheet_name: sheetName })
            });
            
            const data = await res.json();
            if (res.ok) {
                alert("Sheet generated successfully and saved to History!");
                sheetNameInput.value = '';
                loadDrafts();
                // Switch to history tab
                document.querySelector('[data-target="history-tab"]').click();
            } else {
                alert("Error: " + data.detail);
            }
        } catch (e) {
            alert("Error generating sheet: " + e.message);
        } finally {
            setLoading(false);
        }
    });

    // --- HISTORY LOGIC ---
    
    async function loadHistory() {
        try {
            const res = await fetch(`${API_BASE}/sheets/history`, { headers });
            const items = await res.json();
            
            historyTableBody.innerHTML = '';
            
            items.forEach(item => {
                const date = new Date(item.date_generated).toLocaleString();
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td><strong>${item.sheet_name}</strong>.xlsx</td>
                    <td>${date}</td>
                    <td>${item.item_count} products</td>
                    <td style="display: flex; gap: 0.5rem;">
                        <button class="download-hist-btn primary-btn" data-id="${item.file_id}" style="padding: 0.25rem 0.5rem; font-size: 0.8rem;">Download</button>
                        <button class="delete-hist-btn secondary-btn" data-id="${item._id}" style="padding: 0.25rem 0.5rem; font-size: 0.8rem; color: #e74c3c; border-color: #e74c3c;">Delete</button>
                    </td>
                `;
                historyTableBody.appendChild(tr);
            });
            
            // Bind Download buttons
            document.querySelectorAll('.download-hist-btn').forEach(btn => {
                btn.addEventListener('click', async (e) => {
                    const fileId = e.target.dataset.id;
                    window.open(`${API_BASE}/sheets/download/${fileId}`, '_blank');
                });
            });
            
            // Bind Delete buttons
            document.querySelectorAll('.delete-hist-btn').forEach(btn => {
                btn.addEventListener('click', async (e) => {
                    const id = e.target.dataset.id;
                    if(confirm("Are you sure you want to permanently delete this sheet?")) {
                        await fetch(`${API_BASE}/sheets/${id}`, { method: 'DELETE', headers });
                        loadHistory();
                    }
                });
            });
            
        } catch (e) {
            console.error("Failed to load history", e);
        }
    }

    function setLoading(isLoading) {
        const btnText = generateBtn.querySelector('.btn-text');
        const spinner = generateBtn.querySelector('.spinner');
        if (isLoading) {
            generateBtn.disabled = true;
            btnText.classList.add('hidden');
            spinner.classList.remove('hidden');
        } else {
            generateBtn.disabled = false;
            btnText.classList.remove('hidden');
            spinner.classList.add('hidden');
        }
    }
    
    function logout() {
        localStorage.removeItem('access_token');
        window.location.href = 'login.html';
    }

    // Initial load
    loadDrafts();
});
