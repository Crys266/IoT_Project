// Global variables
let ws = null;
let lastCommand = '';
let negativeActive = false;
let objectDetectionActive = false;
let allImages = [];
let frameCount = 0;
let moveInterval = null; // Per tastiera
let currentButton = null; // Per bottoni

// Defer canvas/ctx initialization to DOMContentLoaded
let canvas, ctx;

// Initialize system
document.addEventListener('DOMContentLoaded', function() {
    canvas = document.getElementById('video-stream');
    ctx = canvas.getContext('2d');
    setupEventListeners();
    connectWebSocket();
    loadDangerousClassesUI();
    // Nascondi il form di default
    const form = document.getElementById('dangerousClassesForm');
    form.style.display = "none";
    // Mostra/nascondi al click
    document.getElementById('showDangerousClassesBtn').onclick = function() {
        form.style.display = (form.style.display === "none") ? "block" : "none";
    };
    console.log('🚀 IoT Complete System initialized');
});

async function loadDangerousClassesUI() {
    // Fetch all labels
    const labelsRes = await fetch('/api/yolo_labels');
    const labelsData = await labelsRes.json();
    const allLabels = labelsData.labels;
    // Fetch selected dangerous classes
    const selectedRes = await fetch('/api/notification_classes');
    const selectedData = await selectedRes.json();
    const selected = selectedData.dangerous_classes;
    // Build checkboxes
    const listDiv = document.getElementById('yoloLabelsList');
    listDiv.innerHTML = '';
    allLabels.forEach(label => {
        const id = 'dangerous-' + label.replace(/\s/g, '_');
        const checked = selected.includes(label) ? 'checked' : '';
        listDiv.innerHTML += `
            <label style="display:block; margin-bottom:3px;">
                <input type="checkbox" name="dangerous_classes" value="${label}" ${checked}>
                ${label}
            </label>
        `;
    });
    // Add submit handler
    document.getElementById('dangerousClassesForm').onsubmit = async function (e) {
        e.preventDefault();
        const checkboxes = document.querySelectorAll('input[name="dangerous_classes"]:checked');
        const selectedLabels = Array.from(checkboxes).map(cb => cb.value);

        const resp = await fetch('/api/notification_classes', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({dangerous_classes: selectedLabels})
        });
        const data = await resp.json();
        const msg = data.success ? "Saved!" : "Error saving";
        const statusDiv = document.getElementById('dangerousClassesStatus');
        statusDiv.innerText = msg;

        // Nasconde il messaggio dopo 2.5 secondi
        setTimeout(() => {
            if (statusDiv.innerText === msg) statusDiv.innerText = "";
        }, 2500);
    };
}

function setupEventListeners() {
    // Edit form
    document.getElementById('editImageForm').addEventListener('submit', handleEditImage);

    // Keyboard controls
    document.addEventListener('keyup', function(event) {
        switch(event.key) {
            case 'ArrowUp':
            case 'ArrowDown':
            case 'ArrowLeft':
            case 'ArrowRight':
                lastCommand = '';
                if (moveInterval) clearInterval(moveInterval);
                sendCommand('stop');
                showStatus('STOP', 'warning');
                break;
        }
    });

    document.addEventListener('keydown', function(event) {
        let direction = '';
        switch(event.key) {
            case 'ArrowUp':    direction = 'avanti'; break;
            case 'ArrowDown':  direction = 'indietro'; break;
            case 'ArrowLeft':  direction = 'sinistra'; break;
            case 'ArrowRight': direction = 'destra'; break;
            case 'c':
            case 'C':
                if (!event.ctrlKey) {
                    saveCurrentFrame();
                    return;
                }
                break;
        }
        if (direction && direction !== lastCommand) {
            lastCommand = direction;
            if (moveInterval) clearInterval(moveInterval);
            sendCommand(direction); // Invio subito
            moveInterval = setInterval(() => sendCommand(direction), 150); // Ripeti ogni 150ms
            showStatus('Comando: ' + direction, 'info');
        }
    });

    const btns = [
        {id: 'btnAvanti', dir: 'avanti'},
        {id: 'btnIndietro', dir: 'indietro'},
        {id: 'btnSinistra', dir: 'sinistra'},
        {id: 'btnDestra', dir: 'destra'},
    ];

    btns.forEach(({id, dir}) => {
        const btn = document.getElementById(id);
        if (!btn) return;
        // Mouse/touch down: invia comando ripetuto
        const startMove = (e) => {
            e.preventDefault();
            if (currentButton === btn) return;
            if (moveInterval) clearInterval(moveInterval);
            sendCommand(dir); // Invio subito
            moveInterval = setInterval(() => sendCommand(dir), 150);
            lastCommand = dir;
            currentButton = btn;
            showStatus('Comando: ' + dir, 'info');
        };
        // Mouse/touch up/leave: invia stop
        const stopMove = (e) => {
            if (moveInterval) clearInterval(moveInterval);
            sendCommand('stop');
            showStatus('STOP', 'warning');
            lastCommand = '';
            currentButton = null;
        };
        btn.addEventListener('mousedown', startMove);
        btn.addEventListener('touchstart', startMove);
        btn.addEventListener('mouseup', stopMove);
        btn.addEventListener('mouseleave', stopMove);
        btn.addEventListener('touchend', stopMove);
    });

    // Speed slider JS handler
    const speedSlider = document.getElementById('speedSlider');
    if (speedSlider) {
        speedSlider.addEventListener('input', function() {
            document.getElementById('speedValue').innerText = this.value;
            fetch('/control', {
                method: 'POST',
                headers: {'Content-Type': 'application/x-www-form-urlencoded'},
                body: 'direction=speed:' + this.value
            });
        });
    }
}

function connectWebSocket() {
    // Usa sessione Flask, quindi nessun token necessario
    const wsUrl = `ws://${window.location.hostname}:8765`;
    console.log(`🔌 Connecting WebSocket: ${wsUrl}`);
    ws = new WebSocket(wsUrl);

    ws.onopen = () => {
        console.log('✅ WebSocket connected');
        // Manda hello con username
        ws.send(JSON.stringify({
            type: 'web_hello',
            username: (window.username || ''), // You may want to set window.username from backend if on template
            timestamp: Date.now()
        }));
        showStatus('Connected to IoT system', 'success');
    };

    ws.onclose = () => {
        console.log('❌ WebSocket disconnected');
        showStatus('Disconnected from IoT system', 'warning');
        setTimeout(connectWebSocket, 3000);
    };

    ws.onerror = (error) => {
        console.error('❌ WebSocket error:', error);
        showStatus('WebSocket connection error', 'error');
    };

    ws.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            handleWebSocketMessage(data);
        } catch (e) {
            console.error('❌ Error parsing message:', e);
        }
    };
}

function handleWebSocketMessage(data) {
    switch (data.type) {
        case 'connection_ack':
            console.log('✅ Authenticated connection acknowledged');
            updateSystemStatus(data.system_status);
            break;

        case 'video_frame':
            handleVideoFrame(data);
            break;

        case 'esp32_status':
            handleESP32Status(data);
            break;

        case 'sensor_update':
            handleSensorUpdate(data);
            break;

        case 'detection_update':
            handleDetectionUpdate(data);
            break;

        case 'effect_toggled':
            handleEffectToggled(data);
            break;

        case 'save_success':
            handleSaveSuccess(data);
            break;

        case 'save_error':
            showStatus('Save failed: ' + data.error, 'error');
            break;

        case 'image_saved':
            showStatus(`New image saved by ${data.saved_by}`, 'success');
            break;

        case 'telegram_notification':
            showStatus(`Telegram notification sent: ${data.message}`, 'success');
            break;
    }
}

function handleVideoFrame(data) {
    frameCount++;
    if (!canvas || !ctx) return;
    const img = new Image();
    img.onload = () => {
        ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
    };
    img.src = 'data:image/jpeg;base64,' + data.frame;
}

function handleESP32Status(data) {
    const status = data.connected ? 'ESP32 Connected' : 'ESP32 Disconnected';
    showStatus(status, data.connected ? 'success' : 'warning');
}

function handleSensorUpdate(data) {
    if (data.gps) {
        updateGPS(data.gps);
    }
    if (data.environmental) {
        updateEnvironmental(data.environmental);
    }
}

function handleDetectionUpdate(data) {
    if (data.objects_count > 0) {
        showStatus(`Detected ${data.objects_count} objects`, 'info');
    }
}

function handleEffectToggled(data) {
    const btn = document.getElementById(data.effect === 'negative' ? 'negativeBtn' : 'detectionBtn');
    if (btn) {
        if (data.enabled) {
            btn.classList.add('active');
        } else {
            btn.classList.remove('active');
        }
    }
    const effectName = data.effect === 'negative' ? 'Negative effect' : 'Object detection';
    showStatus(`${effectName} ${data.enabled ? 'enabled' : 'disabled'}`, 'success');
}

function handleSaveSuccess(data) {
    let effectsText = '';
    if (data.image.effects_applied && data.image.effects_applied.length > 0) {
        effectsText = ` (${data.image.effects_applied.join(', ')})`;
    }
    showStatus(`Image saved: ${data.image.filename}${effectsText}`, 'success');
}

function updateSystemStatus(status) {
    if (status.negative_effect) {
        document.getElementById('negativeBtn').classList.add('active');
        negativeActive = true;
    }
    if (status.object_detection) {
        document.getElementById('detectionBtn').classList.add('active');
        objectDetectionActive = true;
    }
    updateGPS(status.gps);
    updateEnvironmental(status.environmental);
}

function updateGPS(gpsData) {
    // Large (desktop)
    const gpsText = document.getElementById('gps-info-text');
    // Mini (mobile)
    const gpsMini = document.getElementById('gps-info-mini');
    if (gpsText && gpsMini) {
        if (gpsData && gpsData.lat !== null && gpsData.lon !== null) {
            gpsText.innerHTML = `Lat: <b>${gpsData.lat.toFixed(6)}</b> | Lon: <b>${gpsData.lon.toFixed(6)}</b>`;
            gpsMini.innerHTML = `📍 ${gpsData.lat.toFixed(5)}, ${gpsData.lon.toFixed(5)}`;
        } else {
            gpsText.innerHTML = `<span style="color:#dc5f5f">GPS non disponibile</span>`;
            gpsMini.innerHTML = `<span style="color:#dc5f5f">GPS N/D</span>`;
        }
    }
}
function updateEnvironmental(envData) {
    // Large (desktop)
    const envText = document.getElementById('temp-humi-info-text');
    // Mini (mobile)
    const envMini = document.getElementById('temp-humi-info-mini');
    if (envText && envMini) {
        if (envData && envData.temperature !== null && envData.humidity !== null) {
            envText.innerHTML = `🌡️ Temperatura: <b>${envData.temperature.toFixed(1)} °C</b> | 💧 Umidità: <b>${envData.humidity.toFixed(1)} %</b>`;
            envMini.innerHTML = `🌡️ ${envData.temperature.toFixed(1)}°C<br>💧 ${envData.humidity.toFixed(1)}%`;
        } else {
            envText.innerHTML = `<span style="color:#dc5f5f">Dati temperatura/umidità non disponibili</span>`;
            envMini.innerHTML = `<span style="color:#dc5f5f">Temp/Umid N/D</span>`;
        }
    }
}

function updateStatus(msg, type='info') {
    // Large
    const statusLarge = document.getElementById('status-text');
    // Mini
    const statusMini = document.getElementById('status-mini');
    if (statusLarge) statusLarge.innerText = msg;
    if (statusMini) statusMini.innerText = msg;
    // Add color classes as needed
}

function sendCommand(direction) {
    if (!ws || ws.readyState !== 1) return;
    ws.send(JSON.stringify({
        type: 'command',
        command: direction,
        timestamp: Date.now()
    }));
    console.log('📤 Command sent:', direction);
    if(window.webSocket && window.webSocket.readyState === 1) {
        // Invia comando movimento + velocità
        var speed = document.getElementById('speedSlider').value;
        window.webSocket.send(JSON.stringify({
            type: "control_command",
            command: direction + ":speed:" + speed
        }));
    }
}

function toggleNegative() {
    if (!ws || ws.readyState !== 1) return;
    ws.send(JSON.stringify({
        type: 'toggle_effect',
        effect: 'negative'
    }));
}

function toggleObjectDetection() {
    if (!ws || ws.readyState !== 1) return;
    ws.send(JSON.stringify({
        type: 'toggle_effect',
        effect: 'detection'
    }));
}

function saveCurrentFrame() {
    if (!ws || ws.readyState !== 1) return;
    ws.send(JSON.stringify({
        type: 'save_image'
    }));
    showStatus('Saving current frame...', 'info');
}

async function showSavedImages() {
    showStatus('Loading image gallery...', 'info');

    try {
        const response = await fetch('/api/images', {
            headers: {
                'Authorization': 'Bearer ' + (localStorage.getItem('iot_session') || '')
            }
        });
        const data = await response.json();

        allImages = data.images;
        displayImages(data.images, data.statistics);
        document.getElementById('savedImagesModal').style.display = 'block';
        showStatus(`Gallery loaded: ${data.statistics.total_images} images`, 'success');
    } catch (error) {
        console.error('Error loading images:', error);
        showStatus('Error loading images', 'error');
    }
}

function displayImages(images, stats) {
    // Update statistics
    document.getElementById('totalImages').textContent = stats.total_images;
    document.getElementById('totalSize').textContent = stats.total_size_mb + ' MB';

    // Calculate detected images and today's images
    const detectedCount = images.filter(img => img.detection_results && img.detection_results.objects_count > 0).length;
    const today = new Date().toISOString().split('T')[0];
    const todayCount = images.filter(img => img.created.startsWith(today)).length;

    document.getElementById('detectedImages').textContent = detectedCount;
    document.getElementById('todayImages').textContent = todayCount;

    // Display images
    const grid = document.getElementById('imageGrid');
    if (images.length === 0) {
        grid.innerHTML = '<div style="grid-column: 1/-1; text-align: center; padding: 40px; color: #aaa;"><p>📭 No saved images found.</p></div>';
        return;
    }

    grid.innerHTML = images.map(img => {
        const hasDetection = img.detection_results && img.detection_results.objects_count > 0;
        const detectionInfo = hasDetection ?
            `🔍 ${img.detection_results.objects_count} objects detected<br>` : '';

        const gpsInfo = (typeof img.gps_lat === 'number' && typeof img.gps_lon === 'number') ?
            `📍 ${img.gps_lat.toFixed(6)}, ${img.gps_lon.toFixed(6)}<br>` :
            (img.gps ? `📍 ${img.gps}<br>` : '');

        const envInfo = (typeof img.temperature === 'number' && typeof img.humidity === 'number') ?
            `🌡️ ${img.temperature.toFixed(1)}°C 💧 ${img.humidity.toFixed(1)}%<br>` : '';

        return `
            <div class="image-card">
                <img src="/thumbnails/${img.thumbnail}" class="image-thumbnail"
                     onclick="viewImageFullSize('${img.filename}')"
                     onerror="this.style.background='#333'; this.alt='No Image';">
                <div class="image-info">
                    <div class="image-title">📸 ${img.filename}</div>
                    <div class="image-meta">
                        📏 ${(img.size/1024).toFixed(1)} KB<br>
                        📅 ${new Date(img.created).toLocaleString()}<br>
                        ${gpsInfo}
                        ${envInfo}
                        ${detectionInfo}
                        ${img.negative_effect ? `🌗 Negative effect applied<br>` : ''}
                        ${img.description ? `📝 ${img.description}<br>` : ''}
                        ${img.tags && img.tags.length > 0 ? `🏷️ ${img.tags.join(', ')}<br>` : ''}
                        ${img.category ? `📂 ${img.category}<br>` : ''}
                        👤 ${img.saved_by || 'unknown'}
                    </div>
                    <div class="image-actions">
                        <button onclick="viewImageFullSize('${img.filename}')" class="btn-small btn-view">👁️ View</button>
                        <button onclick="editImageMetadata('${img.id}')" class="btn-small btn-edit">✏️ Edit</button>
                        ${!hasDetection ? `<button onclick="classifyImage('${img.id}')" class="btn-small btn-classify">🔍 Classify</button>` : ''}
                        <button onclick="sendImageTelegram('${img.id}')" class="btn-small btn-telegram">📱 Send</button>
                        <button onclick="deleteImage('${img.id}')" class="btn-small btn-delete">🗑️ Delete</button>
                    </div>
                </div>
            </div>
        `;
    }).join('');
}

function viewImageFullSize(filename) {
    window.open(`/saved_images/${filename}`, '_blank');
}

function editImageMetadata(imageId) {
    const image = allImages.find(img => img.id === imageId);
    if (!image) return;

    // Populate edit form
    document.getElementById('editImageId').value = imageId;
    document.getElementById('editDescription').value = image.description || '';
    document.getElementById('editTags').value = image.tags ? image.tags.join(', ') : '';
    document.getElementById('editCategory').value = image.category || '';
    document.getElementById('editGpsLat').value = image.gps_lat || '';
    document.getElementById('editGpsLon').value = image.gps_lon || '';
    document.getElementById('editTemp').value = image.temperature || '';
    document.getElementById('editHumidity').value = image.humidity || '';

    document.getElementById('editModal').style.display = 'flex';
}

async function handleEditImage(e) {
    e.preventDefault();

    const formData = new FormData(e.target);
    const imageId = formData.get('imageId');

    const updates = {
        description: formData.get('description'),
        tags: formData.get('tags').split(',').map(tag => tag.trim()).filter(tag => tag),
        category: formData.get('category'),
        gps_lat: formData.get('gpsLat') ? parseFloat(formData.get('gpsLat')) : null,
        gps_lon: formData.get('gpsLon') ? parseFloat(formData.get('gpsLon')) : null,
        temperature: formData.get('temperature') ? parseFloat(formData.get('temperature')) : null,
        humidity: formData.get('humidity') ? parseFloat(formData.get('humidity')) : null
    };

    try {
        const response = await fetch(`/api/images/${imageId}`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': 'Bearer ' + (localStorage.getItem('iot_session') || '')
            },
            body: JSON.stringify(updates)
        });

        const result = await response.json();

        if (result.success) {
            showStatus('Image updated successfully', 'success');
            closeEditModal();
            showSavedImages(); // Refresh gallery
        } else {
            showStatus('Update failed: ' + result.error, 'error');
        }
    } catch (error) {
        console.error('Error updating image:', error);
        showStatus('Update error: ' + error.message, 'error');
    }
}

function closeEditModal() {
    document.getElementById('editModal').style.display = 'none';
}

async function classifyImage(imageId) {
    try {
        showStatus('Running object detection on image...', 'info');
        const response = await fetch(`/api/images/${imageId}/classify`, { method: 'POST' });
        let result;
        try { result = await response.json(); }
        catch (e) { showStatus('Classification: risposta non valida dal server', 'error'); return; }
        if (result.success) {
            showStatus(`Classification complete: ${result.objects_count} objects detected`, 'success');
            showSavedImages();
        } else {
            showStatus('Classification failed: ' + result.error, 'error');
        }
    } catch (error) {
        showStatus('Classification error: ' + error.message, 'error');
    }
}

async function sendImageTelegram(imageId) {
    try {
        showStatus('Sending image via Telegram...', 'info');
        const response = await fetch(`/api/images/${imageId}/telegram`, {
            method: 'POST',
            headers: {
                'Authorization': 'Bearer ' + (localStorage.getItem('iot_session') || '')
            }
        });
        const result = await response.json();
        if (result.success) {
            showStatus('Image sent via Telegram', 'success');
        } else {
            showStatus('Telegram send failed: ' + result.error, 'error');
        }
    } catch (error) {
        console.error('Error sending via Telegram:', error);
        showStatus('Telegram error: ' + error.message, 'error');
    }
}

function deleteImage(imageId) {
    const image = allImages.find(img => img.id === imageId);
    if (!image) return;
    if (confirm(`🗑️ Delete ${image.filename}? This cannot be undone.`)) {
        showStatus('🗑️ Deleting image...', 'warning');
        fetch(`/delete_image/${imageId}`, { method: 'DELETE' })
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                showStatus('🗑️ Image deleted', 'success');
                showSavedImages();
            } else if (data.error) {
                showStatus('Delete failed: ' + data.error, 'error');
            } else {
                showStatus('Delete failed: risposta non valida', 'error');
            }
        })
        .catch(error => showStatus('Delete error: ' + error, 'error'));
    }
}

function hideSavedImages() {
    document.getElementById('savedImagesModal').style.display = 'none';
}

function setupTelegram() {
    showStatus('Opening Telegram bot setup...', 'info');
    window.open('https://t.me/IoTprovaCri3335652352_bot', '_blank');
}

async function testTelegram() {
    try {
        const response = await fetch('/api/telegram/test', {
            method: 'POST',
            headers: {
                'Authorization': 'Bearer ' + (localStorage.getItem('iot_session') || '')
            }
        });

        const result = await response.json();

        if (result.success) {
            showStatus('Test notification sent via Telegram', 'success');
        } else {
            showStatus('Telegram test failed: ' + result.error, 'error');
        }
    } catch (error) {
        console.error('Error testing Telegram:', error);
        showStatus('Telegram test error: ' + error.message, 'error');
    }
}

function showStatus(msg, type='info') {
    const statusEl = document.getElementById('status');
    if (statusEl) {
        statusEl.classList.remove('success', 'error', 'info', 'warning');
        statusEl.classList.add(type);
        statusEl.innerText = msg;
        statusEl.style.opacity = 1;
        if (type !== 'error') {
            setTimeout(() => {
                statusEl.style.opacity = 0.7;
                setTimeout(() => {
                    if (statusEl.innerText === msg) {
                        statusEl.innerText = 'Sistema pronto';
                        statusEl.classList.remove('success', 'error', 'info', 'warning');
                    }
                }, 2000);
            }, 3000);
        }
    }
    // AGGIUNGI QUESTO per il mini-banner mobile
    const statusMini = document.getElementById('status-mini');
    if (statusMini) {
        statusMini.innerText = msg;
        statusMini.style.color =
            type === 'success' ? '#5fdc8c' :
            type === 'error' ? '#dc5f5f' :
            type === 'warning' ? '#ffc107' : '#b9e6fe';
    }
}

console.log('🚀 IoT Complete Dashboard System loaded');