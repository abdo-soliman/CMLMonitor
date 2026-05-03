async function createAdmin() {
    const username = document.getElementById('admin_username').value.trim();
    const fullname = document.getElementById('admin_fullname').value.trim();
    const mail = document.getElementById('admin_email').value.trim();
    const password = document.getElementById('admin_password').value;
    const confirmPassword = document.getElementById('admin_confirm_password').value;
    
    const alertBox = document.getElementById('admin-alert');
    const btn = document.getElementById('btn-create-admin');

    // 1. Client-Side Validation
    if (!username || !password || !confirmPassword) {
        showAlert(alertBox, 'danger', 'Username and Password fields are required.');
        return;
    }
    
    if (password !== confirmPassword) {
        showAlert(alertBox, 'danger', 'Passwords do not match.');
        return;
    }

    if (!mail) {
        showAlert(alertBox, 'danger', 'Email field is required.');
        return;
    }

    if (!fullname) {
        showAlert(alertBox, 'danger', 'Full Name field is required.');
        return;
    }

    // 2. Prepare Request
    const payload = {
        username: username,
        full_name: fullname,
        email: mail,
        password: password
    };

    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Initializing...';

    // 3. Submit
    try {
        const response = await fetch('/api/setup/admin', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        
        const result = await response.json();
        
        if (result.success) {
            // Success! Redirect to login page.
            // Once logged in, the app will automatically route them to the setup wizard.
            window.location.href = '/login';
        } else {
            showAlert(alertBox, 'danger', result.message || 'Initialization failed.');
        }
    } catch (error) {
        showAlert(alertBox, 'danger', 'A network error occurred. Please try again.');
    } finally {
        btn.disabled = false;
        btn.innerHTML = 'Initialize System <i class="fa-solid fa-power-off ms-2"></i>';
    }
}


function showAlert(element, type, message) {
    element.className = `alert alert-${type} mb-3`;
    element.textContent = message;
    element.classList.remove('d-none');
}
