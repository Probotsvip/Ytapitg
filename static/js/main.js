// API Testing Functions
let currentRequest = null;

async function testAPI() {
    const apiKey = document.getElementById('apiKey').value;
    const query = document.getElementById('query').value;
    const format = document.getElementById('format').value;
    const resultDiv = document.getElementById('result');

    if (!apiKey) {
        showResult('Error: Please enter your API key', 'danger');
        return;
    }

    if (!query) {
        showResult('Error: Please enter a search query', 'danger');
        return;
    }

    // Cancel previous request if any
    if (currentRequest) {
        currentRequest.abort();
    }

    // Show loading state
    showResult('<div class="spinner"></div> Extracting media...', 'info');

    try {
        // Create AbortController for request cancellation
        const controller = new AbortController();
        currentRequest = controller;

        const url = new URL('/api/v1/extract', window.location.origin);
        url.searchParams.append('query', query);
        url.searchParams.append('format', format);
        url.searchParams.append('api_key', apiKey);

        const response = await fetch(url, {
            signal: controller.signal,
            headers: {
                'Accept': 'application/json',
            }
        });

        const data = await response.json();

        if (response.ok) {
            displaySuccessResult(data);
        } else {
            showResult(`Error: ${data.error || 'Unknown error'}`, 'danger');
        }
    } catch (error) {
        if (error.name === 'AbortError') {
            showResult('Request cancelled', 'warning');
        } else {
            showResult(`Error: ${error.message}`, 'danger');
        }
    } finally {
        currentRequest = null;
    }
}

function displaySuccessResult(data) {
    const cached = data.cached ? '✅ Cached' : '🔄 New Download';
    const matchType = data.match_type ? ` (${data.match_type})` : '';
    
    let resultHTML = `
        <div class="alert alert-success">
            <h6><i class="fas fa-check-circle"></i> Success ${cached}${matchType}</h6>
            <hr>
            <p><strong>Title:</strong> ${data.data.title}</p>
            <p><strong>File Type:</strong> ${data.data.file_type}</p>
            <p><strong>Duration:</strong> ${data.data.duration || 'Unknown'}</p>
            <p><strong>Processing Time:</strong> ${data.data.processing_time}s</p>
    `;

    if (data.data.file_size_formatted) {
        resultHTML += `<p><strong>File Size:</strong> ${data.data.file_size_formatted}</p>`;
    }

    if (data.data.source) {
        resultHTML += `<p><strong>Source:</strong> ${data.data.source}</p>`;
    }

    if (data.confidence) {
        resultHTML += `<p><strong>Match Confidence:</strong> ${(data.confidence * 100).toFixed(1)}%</p>`;
    }

    resultHTML += `
            <hr>
            <small class="text-muted">
                <strong>File ID:</strong> <code>${data.data.file_id}</code>
            </small>
        </div>
    `;

    document.getElementById('result').innerHTML = resultHTML;
}

function showResult(message, type) {
    const resultDiv = document.getElementById('result');
    const alertClass = type === 'danger' ? 'alert-danger' : 
                      type === 'warning' ? 'alert-warning' : 
                      type === 'info' ? 'alert-info' : 'alert-success';
    
    resultDiv.innerHTML = `<div class="alert ${alertClass}">${message}</div>`;
}

// Utility Functions
function copyToClipboard(text) {
    navigator.clipboard.writeText(text).then(() => {
        showNotification('Copied to clipboard!', 'success');
    }).catch(() => {
        showNotification('Failed to copy', 'danger');
    });
}

function showNotification(message, type) {
    // Create notification element
    const notification = document.createElement('div');
    notification.className = `alert alert-${type} position-fixed`;
    notification.style.cssText = `
        top: 20px;
        right: 20px;
        z-index: 9999;
        min-width: 300px;
        animation: slideIn 0.3s ease;
    `;
    notification.innerHTML = `
        <div class="d-flex justify-content-between align-items-center">
            <span>${message}</span>
            <button type="button" class="btn-close btn-close-white" onclick="this.parentElement.parentElement.remove()"></button>
        </div>
    `;

    // Add to page
    document.body.appendChild(notification);

    // Auto remove after 3 seconds
    setTimeout(() => {
        if (notification.parentElement) {
            notification.remove();
        }
    }, 3000);
}

// Add CSS for notification animation
const style = document.createElement('style');
style.textContent = `
    @keyframes slideIn {
        from {
            transform: translateX(100%);
            opacity: 0;
        }
        to {
            transform: translateX(0);
            opacity: 1;
        }
    }
`;
document.head.appendChild(style);

// Keyboard shortcuts
document.addEventListener('keydown', function(event) {
    // Ctrl/Cmd + Enter to test API
    if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
        event.preventDefault();
        testAPI();
    }
    
    // Escape to cancel current request
    if (event.key === 'Escape' && currentRequest) {
        currentRequest.abort();
        showResult('Request cancelled', 'warning');
    }
});

// Auto-save form data to localStorage
function saveFormData() {
    const formData = {
        apiKey: document.getElementById('apiKey').value,
        query: document.getElementById('query').value,
        format: document.getElementById('format').value
    };
    localStorage.setItem('apiTestFormData', JSON.stringify(formData));
}

function loadFormData() {
    const saved = localStorage.getItem('apiTestFormData');
    if (saved) {
        try {
            const formData = JSON.parse(saved);
            if (formData.apiKey) document.getElementById('apiKey').value = formData.apiKey;
            if (formData.query) document.getElementById('query').value = formData.query;
            if (formData.format) document.getElementById('format').value = formData.format;
        } catch (e) {
            console.error('Failed to load saved form data:', e);
        }
    }
}

// Add event listeners for auto-save
document.addEventListener('DOMContentLoaded', function() {
    loadFormData();
    
    // Save form data on input
    ['apiKey', 'query', 'format'].forEach(id => {
        const element = document.getElementById(id);
        if (element) {
            element.addEventListener('input', saveFormData);
            element.addEventListener('change', saveFormData);
        }
    });
});

// Add placeholder suggestions for common queries
const commonQueries = [
    'Maiyya Mainu Sachet Tandon',
    'Tum Hi Ho Arijit Singh',
    'Kesariya Brahmastra',
    'Apna Bana Le Bhediya',
    'Agar Tum Saath Ho Tamasha'
];

function showQuerySuggestions() {
    const queryInput = document.getElementById('query');
    if (!queryInput.value) {
        const randomQuery = commonQueries[Math.floor(Math.random() * commonQueries.length)];
        queryInput.placeholder = `e.g., ${randomQuery}`;
    }
}

// Update placeholder on focus
document.addEventListener('DOMContentLoaded', function() {
    const queryInput = document.getElementById('query');
    if (queryInput) {
        queryInput.addEventListener('focus', showQuerySuggestions);
        showQuerySuggestions(); // Set initial placeholder
    }
});

// Format validation
function validateApiKey(apiKey) {
    return apiKey && apiKey.length >= 10;
}

function validateQuery(query) {
    return query && query.trim().length >= 2;
}

// Real-time validation feedback
document.addEventListener('DOMContentLoaded', function() {
    const apiKeyInput = document.getElementById('apiKey');
    const queryInput = document.getElementById('query');

    if (apiKeyInput) {
        apiKeyInput.addEventListener('input', function() {
            const isValid = validateApiKey(this.value);
            this.classList.toggle('is-valid', isValid && this.value.length > 0);
            this.classList.toggle('is-invalid', !isValid && this.value.length > 0);
        });
    }

    if (queryInput) {
        queryInput.addEventListener('input', function() {
            const isValid = validateQuery(this.value);
            this.classList.toggle('is-valid', isValid);
            this.classList.toggle('is-invalid', !isValid && this.value.length > 0);
        });
    }
});
