/* ═══════════════════════════════════════════════════════
   StreamClip AI — Dashboard JavaScript
   Tab navigation, real-time data, clip management
   ═══════════════════════════════════════════════════════ */

// ── State ──────────────────────────────────────────────
let currentTab = 'streamers';
let eventSource = null;
let scoreData = [];

// ── Tab Navigation ─────────────────────────────────────
document.querySelectorAll('.tab-btn').forEach(btn => {
  btn.addEventListener('click', () => switchTab(btn.dataset.tab));
});

function switchTab(tab) {
  currentTab = tab;
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
  const btn = document.querySelector(`[data-tab="${tab}"]`);
  const content = document.getElementById(`tab-${tab}`);
  if (btn) btn.classList.add('active');
  if (content) content.classList.add('active');
  // Load tab-specific data
  if (tab === 'streamers') loadStreamers();
  if (tab === 'clips') loadClips();
  if (tab === 'uploads') loadUploads();
  if (tab === 'pipeline') loadScores();
}

// ── Data Loading ───────────────────────────────────────
async function fetchJSON(url) {
  try {
    const r = await fetch(url);
    return await r.json();
  } catch (e) {
    console.error('Fetch error:', url, e);
    return null;
  }
}

async function loadStatus() {
  const data = await fetchJSON('/api/status');
  if (!data) return;

  // Stats
  const stats = data.stats || {};
  setText('active-count', data.streamers?.filter(s => s.is_live).length || 0);
  setText('pipeline-count', data.active_pipelines || 0);
  setText('clips-count', stats.total_clips || 0);
  setText('pending-count', stats.pending_review || 0);
  setText('uploads-count', `${stats.uploads_today || 0}/6`);
  setText('queue-count', data.queue?.pending || 0);

  // Pending badge on clips tab
  const badge = document.getElementById('clips-badge');
  const pending = stats.pending_review || 0;
  if (badge) {
    if (pending > 0) { badge.textContent = pending; badge.style.display = ''; }
    else { badge.style.display = 'none'; }
  }

  // Update timestamp
  setText('last-update', new Date().toLocaleTimeString());

  // Update streamer cards with live status
  if (data.streamers && currentTab === 'streamers') {
    data.streamers.forEach(s => {
      const card = document.querySelector(`[data-streamer="${s.name}"]`);
      if (card) {
        card.classList.toggle('live', s.is_live);
        const dot = card.querySelector('.live-dot');
        if (dot) { dot.classList.toggle('on', s.is_live); dot.classList.toggle('off', !s.is_live); }
        const statusText = card.querySelector('.streamer-status-text');
        if (statusText) statusText.textContent = s.is_live ? `LIVE — ${s.title || 'Streaming'}` : 'Offline';
      }
    });
  }

  // Quota bar
  const used = stats.uploads_today || 0;
  setText('quota-used', used);
  const fill = document.getElementById('quota-fill');
  if (fill) fill.style.width = `${Math.min(100, (used / 6) * 100)}%`;
}

async function loadStreamers() {
  const data = await fetchJSON('/api/streamers');
  const grid = document.getElementById('streamers-grid');
  if (!data || !grid) return;

  const streamers = data.streamers || [];
  if (streamers.length === 0) {
    grid.innerHTML = `<div class="empty-state"><span class="empty-icon">📺</span><p>No streamers configured</p><p class="empty-hint">Click "Add Streamer" to get started</p></div>`;
    return;
  }

  grid.innerHTML = streamers.map(s => `
    <div class="streamer-card" data-streamer="${esc(s.name)}">
      <div class="streamer-header">
        <span class="streamer-name">${esc(s.name)}</span>
        <span class="streamer-platform platform-${s.platform}">${s.platform}</span>
      </div>
      <div class="streamer-meta">${esc(s.url)}</div>
      <div class="streamer-status">
        <span class="live-dot off"></span>
        <span class="streamer-status-text">Checking...</span>
      </div>
      <div class="streamer-meta" style="margin-top:6px">
        ${s.auto_approve ? '✅ Auto-approve' : '⏳ Manual review'} · ${s.enabled ? 'Enabled' : 'Disabled'}
      </div>
      <div class="streamer-actions">
        <button class="btn btn-secondary btn-sm" onclick="toggleStreamer(${s.id}, ${s.enabled ? 0 : 1})">${s.enabled ? 'Disable' : 'Enable'}</button>
        <button class="btn btn-danger btn-sm" onclick="deleteStreamer(${s.id})">Delete</button>
      </div>
    </div>
  `).join('');

  // Refresh live status
  loadStatus();
}

async function loadClips() {
  const filter = document.getElementById('clips-filter')?.value || '';
  const data = await fetchJSON(`/api/clips?status=${filter}&limit=50`);
  const list = document.getElementById('clips-list');
  if (!data || !list) return;

  const clips = data.clips || [];
  if (clips.length === 0) {
    list.innerHTML = `<div class="empty-state"><span class="empty-icon">🎞️</span><p>No clips found</p><p class="empty-hint">${filter ? 'Try a different filter' : 'Clips appear when highlights are detected'}</p></div>`;
    return;
  }

  list.innerHTML = clips.map(c => {
    const tags = (c.tags || []).slice(0, 5).map(t => `<span class="clip-tag">#${esc(t)}</span>`).join('');
    const time = new Date(c.created_at * 1000).toLocaleString();
    const actions = buildClipActions(c);

    return `
    <div class="clip-card">
      <div class="clip-info">
        <h4>${esc(c.title || c.clip_id)}</h4>
        <div class="clip-meta">
          <span>📡 ${esc(c.streamer_name)}</span>
          <span>⏱ ${c.duration}s</span>
          <span>🎯 ${(c.moment_score * 100).toFixed(0)}%</span>
          <span>${c.emotion ? '😀 ' + c.emotion : ''}</span>
          <span>🕐 ${time}</span>
        </div>
        ${tags ? `<div class="clip-tags">${tags}</div>` : ''}
        ${c.description ? `<div class="clip-seo"><strong>SEO:</strong> ${esc(c.description.substring(0, 150))}${c.description.length > 150 ? '...' : ''}</div>` : ''}
        <div class="clip-meta">
          ${c.has_captions ? '✅ Captions' : ''} ${c.has_hook ? '✅ Hook' : ''} ${c.has_thumbnail ? '✅ Thumbnail' : ''}
          ${c.seo_method ? `· Generated by: ${c.seo_method}` : ''}
        </div>
      </div>
      <div class="clip-actions">
        <span class="clip-status-badge status-${c.status}">${c.status.replace('_', ' ')}</span>
        ${actions}
      </div>
    </div>`;
  }).join('');
}

function buildClipActions(clip) {
  const actions = [];
  if (clip.status === 'pending_review') {
    actions.push(`<button class="btn btn-success btn-sm" onclick="approveClip('${clip.clip_id}')">✓ Approve</button>`);
    actions.push(`<button class="btn btn-danger btn-sm" onclick="rejectClip('${clip.clip_id}')">✗ Reject</button>`);
  }
  if (clip.status === 'rejected' || clip.status === 'failed') {
    actions.push(`<button class="btn btn-secondary btn-sm" onclick="approveClip('${clip.clip_id}')">↻ Retry</button>`);
  }
  return actions.join('');
}

async function loadUploads() {
  const data = await fetchJSON('/api/uploads');
  const list = document.getElementById('uploads-list');
  if (!data || !list) return;

  const uploads = data.uploads || [];
  if (uploads.length === 0) {
    list.innerHTML = `<div class="empty-state"><span class="empty-icon">☁️</span><p>No uploads yet</p></div>`;
    return;
  }

  list.innerHTML = uploads.map(u => {
    const time = new Date(u.uploaded_at * 1000).toLocaleString();
    const icon = u.success ? '✅' : '❌';
    return `
    <div class="upload-card">
      <div class="upload-info">
        <span class="upload-icon">${icon}</span>
        <div>
          <div class="upload-title">${esc(u.title || u.clip_id)}</div>
          <div class="upload-detail">${esc(u.streamer_name || '')} · ${time}</div>
        </div>
      </div>
      ${u.video_url ? `<a href="${esc(u.video_url)}" target="_blank" class="upload-link">Watch ↗</a>` : `<span class="upload-detail">${esc(u.error || 'Failed')}</span>`}
    </div>`;
  }).join('');
}

async function loadScores() {
  const data = await fetchJSON('/api/scores');
  if (!data) return;
  scoreData = data.scores || [];
  drawScoreChart();
}

// ── Actions ────────────────────────────────────────────
function showAddStreamer() {
  document.getElementById('add-streamer-form').style.display = '';
}
function hideAddStreamer() {
  document.getElementById('add-streamer-form').style.display = 'none';
}

async function addStreamer() {
  const name = document.getElementById('streamer-name').value.trim();
  const platform = document.getElementById('streamer-platform').value;
  const channel = document.getElementById('streamer-channel').value.trim();
  const url = document.getElementById('streamer-url').value.trim();
  const autoApprove = document.getElementById('streamer-auto-approve').checked;
  if (!name || !channel || !url) { alert('Please fill in all fields'); return; }

  const r = await fetch('/api/streamers', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, platform, channel, url, enabled: true, auto_approve: autoApprove }),
  });
  const data = await r.json();
  if (r.ok) { hideAddStreamer(); loadStreamers(); } else { alert(data.error || 'Error'); }
}

async function deleteStreamer(id) {
  if (!confirm('Delete this streamer?')) return;
  await fetch(`/api/streamers/${id}`, { method: 'DELETE' });
  loadStreamers();
}

async function toggleStreamer(id, enabled) {
  await fetch(`/api/streamers/${id}`, {
    method: 'PUT', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ enabled }),
  });
  loadStreamers();
}

async function approveClip(clipId) {
  const r = await fetch(`/api/clips/${clipId}/approve`, { method: 'POST' });
  if (r.ok) loadClips(); else alert('Failed to approve');
}

async function rejectClip(clipId) {
  if (!confirm('Reject this clip?')) return;
  const r = await fetch(`/api/clips/${clipId}/reject`, { method: 'POST' });
  if (r.ok) loadClips(); else alert('Failed to reject');
}

// ── Score Chart (Canvas 2D) ────────────────────────────
function drawScoreChart() {
  const canvas = document.getElementById('score-canvas');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const W = canvas.width = canvas.parentElement.offsetWidth;
  const H = canvas.height = 200;

  ctx.clearRect(0, 0, W, H);

  // Background grid
  ctx.strokeStyle = 'rgba(255,255,255,0.04)';
  ctx.lineWidth = 1;
  for (let y = 0; y <= 1; y += 0.25) {
    const py = H - y * H;
    ctx.beginPath(); ctx.moveTo(0, py); ctx.lineTo(W, py); ctx.stroke();
  }

  if (scoreData.length < 2) {
    ctx.fillStyle = 'rgba(255,255,255,0.15)';
    ctx.font = '14px Inter'; ctx.textAlign = 'center';
    ctx.fillText('Waiting for score data...', W / 2, H / 2);
    return;
  }

  // Threshold line
  ctx.strokeStyle = 'rgba(248,113,113,0.3)';
  ctx.setLineDash([6, 4]);
  const threshY = H - 0.65 * H;
  ctx.beginPath(); ctx.moveTo(0, threshY); ctx.lineTo(W, threshY); ctx.stroke();
  ctx.setLineDash([]);

  // Draw lines
  const colors = { audio: '#60a5fa', chat: '#4ade80', sentiment: '#f472b6', combined: '#8b5cf6' };
  const keys = ['audio', 'chat', 'sentiment', 'combined'];

  keys.forEach(key => {
    ctx.strokeStyle = colors[key];
    ctx.lineWidth = key === 'combined' ? 2.5 : 1.5;
    ctx.globalAlpha = key === 'combined' ? 1 : 0.6;
    ctx.beginPath();
    scoreData.forEach((s, i) => {
      const x = (i / (scoreData.length - 1)) * W;
      const y = H - (s[key] || 0) * H;
      i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
    });
    ctx.stroke();
  });
  ctx.globalAlpha = 1;

  // Trigger markers
  scoreData.forEach((s, i) => {
    if (s.triggered) {
      const x = (i / (scoreData.length - 1)) * W;
      ctx.fillStyle = 'rgba(139,92,246,0.8)';
      ctx.beginPath(); ctx.arc(x, H - s.combined * H, 5, 0, Math.PI * 2); ctx.fill();
    }
  });
}

// ── SSE Real-time Updates ──────────────────────────────
function connectSSE() {
  if (eventSource) eventSource.close();
  eventSource = new EventSource('/api/events');
  eventSource.onmessage = (e) => {
    try {
      const data = JSON.parse(e.data);
      setText('active-count', data.active || 0);
      setText('clips-count', data.clips || 0);
      setText('pending-count', data.pending_review || 0);
      setText('uploads-count', `${data.uploads_today || 0}/6`);
      setText('queue-count', data.queue_pending || 0);
      setText('last-update', new Date().toLocaleTimeString());

      // Badge
      const badge = document.getElementById('clips-badge');
      if (badge && data.pending_review > 0) { badge.textContent = data.pending_review; badge.style.display = ''; }
      else if (badge) { badge.style.display = 'none'; }
    } catch (err) {}
  };
  eventSource.onerror = () => {
    const dot = document.querySelector('.status-dot');
    const text = document.querySelector('.status-text');
    if (dot) dot.style.background = 'var(--accent-red)';
    if (text) text.textContent = 'Disconnected';
    setTimeout(connectSSE, 5000);
  };
  eventSource.onopen = () => {
    const dot = document.querySelector('.status-dot');
    const text = document.querySelector('.status-text');
    if (dot) dot.style.background = 'var(--accent-green)';
    if (text) text.textContent = 'Connected';
  };
}

// ── Helpers ────────────────────────────────────────────
function setText(id, val) { const el = document.getElementById(id); if (el) el.textContent = val; }
function esc(s) { const d = document.createElement('div'); d.textContent = s || ''; return d.innerHTML; }

// ── Init ───────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  loadStatus();
  loadStreamers();
  connectSSE();
  // Periodic refresh
  setInterval(loadStatus, 10000);
  setInterval(() => { if (currentTab === 'pipeline') loadScores(); }, 5000);
  // Resize chart
  window.addEventListener('resize', () => { if (currentTab === 'pipeline') drawScoreChart(); });
});
