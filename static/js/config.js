document.addEventListener("DOMContentLoaded", function() {
    
    // --- ALERTS / SMTP TAB ---
    const alertToggle = document.getElementById('alertEnabled');
    const alertsPane = document.getElementById('alerts');
    const smtpTestBtn = document.getElementById('btn-test-smtp'); // 1. Grab the SMTP test button

    if (alertToggle && alertsPane) {
        const alertInputs = alertsPane.querySelectorAll('input:not(#alertEnabled)');
        const alertForm = alertsPane.querySelector('form'); 

        function toggleAlertFields() {
            const isEnabled = alertToggle.checked;
            
            // Toggle all inputs
            alertInputs.forEach(input => {
                input.disabled = !isEnabled;

                if (input.id === "alertCronInput" || input.id === "reportCronInput" || input.id === "SMTPUserPassword" || input.type === "checkbox")
                    return;

                input.required = isEnabled;
            });

            // 2. Toggle the test button disabled state
            if (smtpTestBtn) {
                smtpTestBtn.disabled = !isEnabled;
            }
        }

        // Run once on page load to set initial state
        toggleAlertFields();

        // Listen for clicks on the toggle to dynamically update the fields
        alertToggle.addEventListener('change', toggleAlertFields);

        alertForm.addEventListener('submit', function() {
            alertInputs.forEach(input => {
                input.disabled = false;
            });
        });
    }

    // --- LDAP TAB ---
    const ldapToggle = document.getElementById('ldapEnabled');
    const ldapPane = document.getElementById('ldap');
    const ldapTestBtn = document.getElementById('btn-test-ldap'); // 3. Grab the LDAP test button

    if (ldapToggle && ldapPane) {
        const ldapInputs = ldapPane.querySelectorAll('input:not(#ldapEnabled)');
        const ldapForm = ldapPane.querySelector('form'); 

        function toggleLDAPFields() {
            const isEnabled = ldapToggle.checked;
            
            // Toggle all inputs
            ldapInputs.forEach(input => {
                input.disabled = !isEnabled;
            });

            // 4. Toggle the test button disabled state
            if (ldapTestBtn) {
                ldapTestBtn.disabled = !isEnabled;
            }
        }

        // Set initial state on page load
        toggleLDAPFields();

        // Listen for toggle changes
        ldapToggle.addEventListener('change', toggleLDAPFields);

        // When the user clicks "Save", re-enable all fields so the browser sends them
        ldapForm.addEventListener('submit', function() {
            ldapInputs.forEach(input => {
                input.disabled = false;
            });
        });
    }
});

// Generic function to show alerts
function showConfigAlert(elementId, type, message) {
    const alertBox = document.getElementById(elementId);
    alertBox.className = `alert alert-${type} mt-3 mb-4`;
    alertBox.textContent = message;
    alertBox.classList.remove('d-none');
}

// --- LDAP TEST ---
function testLDAPConfig() {
    // Ask the user for a test username via a browser prompt
    const testUser = prompt("Enter a valid username to verify the LDAP search base:");
    if (!testUser) return; // Cancelled by user

    const btn = document.getElementById('btn-test-ldap');
    const alertBoxId = 'ldap-test-alert';

    const payload = {
        'ldap_server': document.querySelector('input[name="server"]').value.trim(),
        'ldap_port': document.querySelector('input[name="port"]').value.trim() || '389',
        'ldap_base_dn': document.querySelector('input[name="base_dn"]').value.trim(),
        'ldap_bind_dn': document.querySelector('input[name="bind_dn"]').value.trim(),
        'ldap_bind_password': document.querySelector('input[name="bind_password"]').value.trim(),
        'test_username': testUser
    };

    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Testing...';

    fetch('/api/test-ldap', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    })
        .then(response => response.json())
        .then(data => {
            showConfigAlert(alertBoxId, data.success ? 'success' : 'danger', data.message);
        })
        .catch(error => {
            showConfigAlert(alertBoxId, 'danger', `LDAP Test Failed with the following ERROR: ${error}.`);
        })
        .finally(() => {
            btn.disabled = false;
            btn.innerHTML = 'Test Connection';
        });
}

// --- CML TEST ---
async function testCMLConfig() {
    const btn = document.getElementById('btn-test-cml');
    const alertBoxId = 'cml-test-alert';
    const fileInput = document.querySelector('input[name="kubeconfig_file"]');

    const payload = {
        'cml_workspace_domain': document.querySelector('input[name="workspace_domain"]').value.trim(),
        'cml_api_key': document.querySelector('input[name="api_key"]').value.trim(),
        'cml_kubeconfig_content': null // Default to null if no file is provided
    };

    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Testing...';

    try {
        // Only read the file if the user actually selected one
        if (fileInput.files.length > 0) {
            payload['cml_kubeconfig_content'] = await fileInput.files[0].text();
        }

        fetch('/api/config/test-cml', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        })
            .then(response => response.json())
            .then(data => {
                showConfigAlert(alertBoxId, data.success ? 'success' : 'danger', data.message);
            })
            .catch(error => {
                showConfigAlert(alertBoxId, 'danger', `CML Test Failed with the following ERORR: ${error}`);
            })
            .finally(() => {
                btn.disabled = false;
                btn.innerHTML = 'Test Connection';
            });
    }
    catch (error) {
        showConfigAlert(alertBoxId, 'danger', `CML Test Failed with the following ERORR: ${error}`);
    }
    finally {
        btn.disabled = false;
        btn.innerHTML = 'Test Connection';
    }
}

// --- SMTP TEST ---
function testSMTPConfig() {
    const btn = document.getElementById('btn-test-smtp');
    const alertBoxId = 'smtp-test-alert';

    // 1. Get raw values from the alert and report recipient inputs
    const alertEmailsRaw = document.querySelector('input[name="alert_recipient_emails"]').value;
    const reportEmailsRaw = document.querySelector('input[name="report_recipient_emails"]').value;

    // 2. Split by comma, trim whitespace, and filter out empty strings
    const alertEmails = alertEmailsRaw.split(',').map(e => e.trim()).filter(e => e);
    const reportEmails = reportEmailsRaw.split(',').map(e => e.trim()).filter(e => e);

    // 3. Combine and Deduplicate using a Set
    const uniqueEmails = [...new Set([...alertEmails, ...reportEmails])];

    if (uniqueEmails.length === 0) {
        showConfigAlert(alertBoxId, 'warning', 'Please provide at least one recipient email in the Alert or Report recipients fields.');
        return;
    }

    const payload = {
        'smtp_server': document.querySelector('input[name="smtp_server"]').value.trim(),
        'smtp_port': document.querySelector('input[name="smtp_port"]').value.trim() || '587',
        'smtp_user': document.querySelector('input[name="smtp_user"]').value.trim(),
        'smtp_password': document.querySelector('input[name="smtp_password"]').value.trim(),
        'smtp_use_tls': document.querySelector('input[name="use_tls"]').checked ? '1' : '0',
        'smtp_sender_email': document.querySelector('input[name="sender_email"]').value.trim(),
        'recipients': uniqueEmails 
    };

    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Sending...';

    fetch('/api/test-smtp', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    })
        .then(response => response.json())
        .then(data => {
            showConfigAlert(alertBoxId, data.success ? 'success' : 'danger', data.message);
        })
        .catch(error => {
            showConfigAlert(alertBoxId, 'danger', `SMTP Test Failed with the following ERROR: ${error}`);
        })
        .finally(() => {
            btn.disabled = false;
            btn.innerHTML = 'Send Test Email';
        });
}
