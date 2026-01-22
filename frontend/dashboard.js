// Check authentication on page load
window.addEventListener('DOMContentLoaded', async () => {
  const token = localStorage.getItem('token');
  
  if (!token) {
    // Not logged in, redirect to login page
    window.location.href = '/index.html';
    return;
  }

  // Verify token and get user info
  await loadUserInfo();
  await loadHistory();
  await loadStatistics();
});

// Load current user information
async function loadUserInfo() {
  const token = localStorage.getItem('token');

  try {
    const response = await fetch('/api/auth/me', {
      headers: {
        'Authorization': `Bearer ${token}`
      }
    });

    if (!response.ok) {
      throw new Error('Invalid token');
    }

    const user = await response.json();
    document.getElementById('user-email').textContent = user.email;

  } catch (error) {
    console.error('Auth error:', error);
    logout();
  }
}

// Logout function
function logout() {
  localStorage.removeItem('token');
  window.location.href = '/index.html';
}

// Prediction functionality
const imageInput = document.getElementById('imageInput');
const uploadBtn = document.getElementById('uploadBtn');
const resultDiv = document.getElementById('result');
const previewDiv = document.getElementById('preview');

uploadBtn.addEventListener('click', async () => {
  if (!imageInput.files.length) {
    alert('Please select an image first.');
    return;
  }

  const file = imageInput.files[0];
  const token = localStorage.getItem('token');

  // Show preview
  previewDiv.innerHTML = `<img src="${URL.createObjectURL(file)}" alt="Preview" />`;
  resultDiv.innerHTML = '<p class="loading">Analyzing image...</p>';

  const formData = new FormData();
  formData.append('file', file);

  try {
    const response = await fetch('/api/predict', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`  // ← Send token with request
      },
      body: formData,
    });

    if (response.status === 401) {
      // Token expired or invalid
      alert('Session expired. Please login again.');
      logout();
      return;
    }

    if (!response.ok) {
      throw new Error(`Server error: ${response.status}`);
    }

    const data = await response.json();
    
    // Display result
    const confidencePercent = (data.confidence * 100).toFixed(2);
    const resultClass = data.label === 'Tumor' ? 'tumor-detected' : 'no-tumor';
    
    resultDiv.innerHTML = `
      <div class="result-box ${resultClass}">
        <h3>Prediction Result</h3>
        <p class="label">${data.label}</p>
        <p class="confidence">Confidence: ${confidencePercent}%</p>
      </div>
    `;

    // Refresh history after new prediction
    setTimeout(loadHistory, 1000);

  } catch (error) {
    resultDiv.innerHTML = `<p class="error">❌ ${error.message}</p>`;
  }
});

// Load prediction history
async function loadHistory() {
  const token = localStorage.getItem('token');
  const historyDiv = document.getElementById('history-list');

  try {
    const response = await fetch('/api/predictions?limit=10', {
      headers: {
        'Authorization': `Bearer ${token}`
      }
    });

    if (!response.ok) {
      throw new Error('Failed to load history');
    }

    const data = await response.json();
    const predictions = data.predictions;

    if (predictions.length === 0) {
      historyDiv.innerHTML = '<p class="empty">No predictions yet. Upload an image to get started!</p>';
      return;
    }

    // Build history list
    let historyHTML = '<div class="history-items">';
    
    predictions.forEach(pred => {
      const date = new Date(pred.created_at).toLocaleString();
      const confidencePercent = (pred.confidence_score * 100).toFixed(2);
      const labelClass = pred.prediction_label === 'Tumor' ? 'tumor' : 'no-tumor';
      
      historyHTML += `
        <div class="history-item">
          <div class="history-info">
            <span class="history-label ${labelClass}">${pred.prediction_label}</span>
            <span class="history-confidence">${confidencePercent}%</span>
          </div>
          <div class="history-meta">
            <span class="history-date">${date}</span>
            <span class="history-file">${pred.filename}</span>
          </div>
        </div>
      `;
    });
    
    historyHTML += '</div>';
    historyDiv.innerHTML = historyHTML;

  } catch (error) {
    historyDiv.innerHTML = `<p class="error">Failed to load history</p>`;
  }
}

// Load statistics
async function loadStatistics() {
  const token = localStorage.getItem('token');
  const statsDiv = document.getElementById('statistics');

  try {
    const response = await fetch('/api/statistics', {
      headers: {
        'Authorization': `Bearer ${token}`
      }
    });

    if (!response.ok) {
      throw new Error('Failed to load statistics');
    }

    const stats = await response.json();

    statsDiv.innerHTML = `
      <div class="stats-grid">
        <div class="stat-item">
          <h3>${stats.total_predictions}</h3>
          <p>Total Predictions</p>
        </div>
        <div class="stat-item tumor">
          <h3>${stats.tumor_detected}</h3>
          <p>Tumors Detected</p>
        </div>
        <div class="stat-item no-tumor">
          <h3>${stats.no_tumor_detected}</h3>
          <p>No Tumor</p>
        </div>
        <div class="stat-item">
          <h3>${(stats.average_confidence * 100).toFixed(1)}%</h3>
          <p>Avg Confidence</p>
        </div>
      </div>
    `;

  } catch (error) {
    statsDiv.innerHTML = `<p class="error">Failed to load statistics</p>`;
  }
}