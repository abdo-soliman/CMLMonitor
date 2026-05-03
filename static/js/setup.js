// Data object to collect configurations across steps
let setupData = {};


function nextStep(step) {
    document.querySelectorAll('.setup-card').forEach(card => card.classList.remove('active'));
    document.getElementById(`step-${step}`).classList.add('active');
}


async function testCML() {
    const domain = document.getElementById('cml_domain').value.trim();
    const apiKey = document.getElementById('cml_apikey').value.trim();
    const prefix = document.getElementById('cml_prefix').value.trim();
    const fileInput = document.getElementById('cml_kubeconfig'); // The new file input
    const alertBox = document.getElementById('cml-alert');
    const btn = document.getElementById('btn-test-cml');

    if (!domain || !apiKey || !prefix || fileInput.files.length === 0) {
        showAlert(alertBox, 'danger', 'Please fill in all CML fields and upload the rke2.yaml file.');
        return;
    }

    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Reading File...';

    let fileText = "";
    try {
        // Read the file content as text
        const file = fileInput.files[0];
        fileText = await file.text();
    } catch (e) {
        showAlert(alertBox, 'danger', 'Failed to read the uploaded file.');
        btn.disabled = false;
        btn.innerHTML = 'Verify & Continue <i class="fa-solid fa-arrow-right ms-2"></i>';
        return;
    }

    // Temporarily store CML configs, including the raw file content
    setupData['cml_workspace_domain'] = domain;
    setupData['cml_api_key'] = apiKey;
    setupData['cml_namespace_prefix'] = prefix;
    setupData['cml_kubeconfig_content'] = fileText; 

    btn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Verifying...';

    try {
        const response = await fetch('/api/setup/test-cml', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(setupData) // Note: Make sure test-cml route is fine receiving the extra content key
        });

        const result = await response.json();

        if (result.success) {
            nextStep(2);
        } else {
            showAlert(alertBox, 'danger', result.message || 'Connection failed. Please check your credentials.');
        }
    } catch (error) {
        showAlert(alertBox, 'danger', 'An error occurred while testing the connection.');
    } finally {
        btn.disabled = false;
        btn.innerHTML = 'Verify & Continue <i class="fa-solid fa-arrow-right ms-2"></i>';
    }
}


async function testLDAP() {
    const server = document.getElementById('ldap_server').value.trim();
    const port = document.getElementById('ldap_port').value.trim() || '389';
    const baseDn = document.getElementById('ldap_base').value.trim();
    const bindDn = document.getElementById('ldap_bind').value.trim();
    const bindPass = document.getElementById('ldap_pass').value.trim();
    const testUser = document.getElementById('ldap_test_user').value.trim();

    const alertBox = document.getElementById('ldap-alert');
    const btn = document.getElementById('btn-test-ldap');

    if (!server || !baseDn || !bindDn || !bindPass || !testUser) {
        showAlert(alertBox, 'danger', 'Please fill in all LDAP fields and a test username to verify, or click Skip.');
        return;
    }

    // Temporarily construct the payload for verification
    const verifyPayload = {
        'ldap_server': server,
        'ldap_port': port,
        'ldap_base_dn': baseDn,
        'ldap_bind_dn': bindDn,
        'ldap_bind_password': bindPass,
        'test_username': testUser
    };

    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Verifying...';

    try {
        const response = await fetch('/api/test-ldap', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(verifyPayload)
        });

        const result = await response.json();

        if (result.success) {
            // Test passed. Save to global setupData (excluding the test username)
            setupData['ldap_enabled'] = '1';
            setupData['ldap_server'] = server;
            setupData['ldap_port'] = port;
            setupData['ldap_base_dn'] = baseDn;
            setupData['ldap_bind_dn'] = bindDn;
            setupData['ldap_bind_password'] = bindPass;

            nextStep(3);
        } else {
            showAlert(alertBox, 'danger', result.message);
        }
    } catch (error) {
        showAlert(alertBox, 'danger', 'An error occurred while testing the LDAP connection.');
    } finally {
        btn.disabled = false;
        btn.innerHTML = 'Verify & Continue <i class="fa-solid fa-arrow-right ms-2"></i>';
    }
}


async function testSMTP() {
    const server = document.getElementById('smtp_server').value.trim();
    const port = document.getElementById('smtp_port').value.trim() || '587';
    const user = document.getElementById('smtp_user').value.trim();
    const pass = document.getElementById('smtp_pass').value.trim();
    const useTLS = document.getElementById('useTls').checked ? '1' : '0';
    const sender = document.getElementById('smtp_sender').value.trim();
    const testEmail = document.getElementById('smtp_test_email').value.trim();

    const alertBox = document.getElementById('smtp-alert');
    const btn = document.getElementById('btn-test-smtp');

    if (!server || !sender || !testEmail) {
        showAlert(alertBox, 'danger', 'Server URL, Sender Email, and a Verification Recipient Email are required to test.');
        return;
    }

    const verifyPayload = {
        'smtp_server': server,
        'smtp_port': port,
        'smtp_user': user,
        'smtp_password': pass,
        'smtp_use_tls': useTLS,
        'smtp_sender_email': sender,
        'recipients': [testEmail]
    };

    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Verifying...';

    try {
        const response = await fetch('/api/test-smtp', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(verifyPayload)
        });

        const result = await response.json();

        if (result.success) {
            // Test passed. Save SMTP configs to global setupData
            setupData['alert_enabled'] = '1';
            setupData['smtp_server'] = server;
            setupData['smtp_port'] = port;
            setupData['smtp_user'] = user;
            setupData['smtp_password'] = pass;
            setupData['use_tls'] = useTLS === '1';
            setupData['sender_email'] = sender;

            // Proceed to save everything to the database
            submitSetup(true); 
        } else {
            showAlert(alertBox, 'danger', result.message);
            btn.disabled = false;
            btn.innerHTML = 'Verify & Complete <i class="fa-solid fa-check ms-2"></i>';
        }
    } catch (error) {
        showAlert(alertBox, 'danger', 'An error occurred while testing the SMTP connection.');
        btn.disabled = false;
        btn.innerHTML = 'Verify & Complete <i class="fa-solid fa-check ms-2"></i>';
    }
}


// Updated submitSetup function (No longer blindly collects HTML inputs)
async function submitSetup(calledFromVerification = false) {
    const btnSkip = document.querySelector('button[onclick="submitSetup()"]');
    const btnVerify = document.getElementById('btn-test-smtp');

    if (!calledFromVerification) {
            btnSkip.disabled = true;
            btnSkip.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Saving...';
            btnVerify.disabled = true;
    }

    try {
        const response = await fetch('/api/setup/save', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(setupData) // Send the globally collected, verified data
        });

        const result = await response.json();

        if (result.success) {
            window.location.href = '/'; // Redirect to dashboard on success
        } else {
            alert('Failed to save setup: ' + result.message);
            if (!calledFromVerification) {
                btnSkip.disabled = false;
                btnSkip.innerHTML = 'Skip & Finish';
                btnVerify.disabled = false;
            }
        }
    } catch (error) {
        alert('A network error occurred.');
        if (!calledFromVerification) {
            btnSkip.disabled = false;
            btnSkip.innerHTML = 'Skip & Finish';
            btnVerify.disabled = false;
        }
    }
}


function showAlert(element, type, message) {
    element.className = `alert alert-${type} mb-3`;
    element.textContent = message;
    element.classList.remove('d-none');
}
