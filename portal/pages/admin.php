<?php
/**
 * Ailey Portal — Admin Panel
 */
require_once __DIR__ . '/layout.php';
portal_head(__('admin.title'));
?>

<div class="admin-page">
    <div style="display:flex;align-items:center;gap:1rem;margin-bottom:1.5rem;">
        <a href="/chat" class="legal-back" style="margin:0;"><?= __('admin.back') ?></a>
        <h1 style="font-size:1.3rem;font-weight:700;flex:1;"><?= icon('shield') ?> <?= __('admin.header') ?></h1>
    </div>

    <!-- Stats -->
    <div class="admin-stats" id="admin-stats">
        <div class="stat-card"><div class="stat-value"><span class="spinner"></span></div><div class="stat-label"><?= __('admin.loading') ?></div></div>
    </div>

    <!-- Whitelist -->
    <div class="settings-section" style="margin-bottom:1.5rem;">
        <h2><?= icon('mail') ?> <?= __('admin.invite') ?></h2>
        <div style="display:flex;gap:0.5rem;align-items:flex-end;">
            <div class="form-group" style="flex:1;margin:0;">
                <input class="form-input" type="email" id="invite-email" placeholder="email@example.de">
            </div>
            <button class="btn btn-primary btn-sm" onclick="adminInvite()"><?= __('admin.invite_btn') ?></button>
        </div>
        <div id="invite-result" style="font-size:0.8rem;color:var(--muted-foreground);margin-top:0.5rem;"></div>
    </div>

    <!-- Limits / Settings -->
    <div class="settings-section" style="margin-bottom:1.5rem;">
        <h2><?= icon('sliders') ?> Limits & Einstellungen</h2>
        <p style="font-size:0.8rem;color:var(--muted-foreground);margin-bottom:1rem;">Steuere die Nutzungslimits für alle Portal-User.</p>

        <div class="limit-slider-group">
            <label for="limit-max-message-length">
                Max. Nachrichtenlänge: <strong id="limit-max-message-length-val">—</strong> Zeichen
            </label>
            <input type="range" id="limit-max-message-length" min="100" max="10000" step="100"
                   oninput="document.getElementById('limit-max-message-length-val').textContent=this.value">
        </div>

        <div class="limit-slider-group">
            <label for="limit-max-hourly">
                Max. Nachrichten / Stunde: <strong id="limit-max-hourly-val">—</strong>
            </label>
            <input type="range" id="limit-max-hourly" min="1" max="200" step="1"
                   oninput="document.getElementById('limit-max-hourly-val').textContent=this.value">
        </div>

        <div class="limit-slider-group">
            <label for="limit-max-daily">
                Max. Nachrichten / Tag: <strong id="limit-max-daily-val">—</strong>
            </label>
            <input type="range" id="limit-max-daily" min="1" max="1000" step="1"
                   oninput="document.getElementById('limit-max-daily-val').textContent=this.value">
        </div>

        <button class="btn btn-primary btn-sm" onclick="saveLimits()" style="margin-top:0.75rem;">💾 Limits speichern</button>
        <div id="limits-result" style="font-size:0.8rem;color:var(--muted-foreground);margin-top:0.5rem;"></div>
    </div>

    <!-- Intro Song Selection -->
    <div class="settings-section" style="margin-bottom:1.5rem;">
        <h2>🎵 Portal-Intro Song</h2>
        <p style="font-size:0.8rem;color:var(--muted-foreground);margin-bottom:1rem;">Welcher Song spielt beim Portal-Intro (Cinematic Landingpage)?</p>
        <div style="display:flex;gap:0.5rem;align-items:flex-end;">
            <div class="form-group" style="flex:1;margin:0;">
                <select class="form-input" id="intro-song-select" style="padding:0.5rem 0.75rem;">
                    <option value="auto">🔄 Automatisch (neuester Song)</option>
                    <option value="random">🎲 Zufällig</option>
                </select>
            </div>
            <button class="btn btn-primary btn-sm" onclick="saveIntroSong()">💾 Speichern</button>
        </div>
        <div id="intro-song-result" style="font-size:0.8rem;color:var(--muted-foreground);margin-top:0.5rem;"></div>
    </div>

    <!-- Dev-Link: Next.js Mainapp (Admin only, password-gated) -->
    <div class="settings-section" style="margin-bottom:1.5rem;border:1px dashed rgba(255,255,255,0.15);">
        <h2>🔗 Mainapp Dev-Link</h2>
        <p style="font-size:0.8rem;color:var(--muted-foreground);margin-bottom:0.75rem;">
            Direkter Zugang zur Next.js-Mainapp (Mac / Tauri-Frontend) — im Heimnetz via LAN-IP, unterwegs via Public-IP.
            Passwortgeschützt. IP wird automatisch von Ailey Core gemeldet.
        </p>
        <div style="display:flex;gap:0.5rem;align-items:flex-end;flex-wrap:wrap;">
            <div class="form-group" style="flex:1;min-width:200px;margin:0;">
                <input class="form-input" type="password" id="devlink-password" placeholder="Dev-Link Passwort" autocomplete="new-password">
            </div>
            <button class="btn btn-primary btn-sm" onclick="devlinkFetch()">🔓 Links holen</button>
        </div>
        <div id="devlink-urls" style="margin-top:0.75rem;display:none;flex-direction:column;gap:0.5rem;"></div>
        <div id="devlink-error" style="font-size:0.8rem;color:#ff6b6b;margin-top:0.5rem;"></div>
    </div>

    <!-- Users Table -->
    <div class="settings-section">
        <h2><?= icon('users') ?> <?= __('admin.users') ?></h2>
        <div style="overflow-x:auto;">
            <table class="admin-table" id="admin-users-table">
                <thead>
                    <tr>
                        <th><?= __('admin.col_name') ?></th>
                        <th><?= __('admin.col_email') ?></th>
                        <th>🏷️ Tier</th>
                        <th><?= __('admin.col_status') ?></th>
                        <th><?= __('admin.col_messages') ?></th>
                        <th>💰 V$ Balance</th>
                        <th>📅 V$/Woche</th>
                        <th>🔧 Tools</th>
                        <th>📚 Lernen</th>
                        <th>⚠️ Warnung</th>
                        <th><?= __('admin.col_last_active') ?></th>
                        <th><?= __('admin.col_actions') ?></th>
                    </tr>
                </thead>
                <tbody id="admin-users-body">
                    <tr><td colspan="12" style="text-align:center;"><?= __('admin.loading') ?></td></tr>
                </tbody>
            </table>
        </div>
    </div>

    <!-- 🛡️ Moderation Reports -->
    <div class="settings-section" style="margin-bottom:1.5rem;">
        <h2 style="display:flex;align-items:center;gap:0.5rem;">
            🛡️ Moderation
            <span id="moderation-badge" style="background:var(--primary);color:#fff;font-size:0.7rem;padding:2px 8px;border-radius:999px;display:none;">0</span>
        </h2>
        <p style="font-size:0.8rem;color:var(--muted-foreground);margin-bottom:1rem;">
            Automatisch erkannte Troll-Nachrichten. Kein User wird automatisch gesperrt — du entscheidest.
        </p>

        <!-- Filter Buttons -->
        <div style="margin-bottom:0.75rem;display:flex;gap:0.5rem;flex-wrap:wrap;">
            <button class="btn btn-ghost btn-sm mod-filter-active" onclick="filterModReports(null,this)">Alle</button>
            <button class="btn btn-ghost btn-sm" onclick="filterModReports('pending',this)">⏳ Offen</button>
            <button class="btn btn-ghost btn-sm" onclick="filterModReports('reviewed',this)">✅ Bearbeitet</button>
            <button class="btn btn-ghost btn-sm" onclick="filterModReports('dismissed',this)">🗑️ Verworfen</button>
        </div>

        <!-- Reports List -->
        <div id="moderation-empty" style="text-align:center;color:var(--muted-foreground);padding:1rem;display:none;">Keine Moderation-Reports vorhanden 🎉</div>
        <div id="moderation-list" style="display:flex;flex-direction:column;gap:0.75rem;"></div>
    </div>

    <!-- Gallery Management -->
    <div class="settings-section" style="margin-top:1.5rem;">
        <h2><?= icon('palette') ?> <?= __('admin.gallery_title') ?></h2>
        <p style="font-size:0.8rem;color:var(--muted-foreground);margin-bottom:1rem;"><?= __('admin.gallery_desc') ?></p>
        <div style="margin-bottom:0.75rem;display:flex;gap:0.5rem;flex-wrap:wrap;">
            <button class="btn btn-ghost btn-sm filter-active" onclick="filterGallery(null,this)"><?= __('gallery.filter_all') ?></button>
            <button class="btn btn-ghost btn-sm" onclick="filterGallery('song',this)"><?= icon('music') ?> Songs</button>
            <button class="btn btn-ghost btn-sm" onclick="filterGallery('svg',this)"><?= icon('pen-tool') ?> SVGs</button>
            <button class="btn btn-ghost btn-sm" onclick="filterGallery('image',this)"><?= icon('image') ?> 🖼️ Images</button>
            <button class="btn btn-ghost btn-sm" onclick="filterGallery('book',this)"><?= icon('book-open') ?> <?= __('gallery.filter_book') ?></button>
            <button class="btn btn-ghost btn-sm" onclick="filterGallery('code',this)"><?= icon('code') ?> Code</button>
        </div>
        <div style="overflow-x:auto;">
            <table class="admin-table" id="admin-gallery-table">
                <thead>
                    <tr>
                        <th>ID</th>
                        <th><?= __('admin.gallery_col_type') ?></th>
                        <th><?= __('admin.gallery_col_title') ?></th>
                        <th>Source ID</th>
                        <th>Status</th>
                        <th><?= __('admin.gallery_col_date') ?></th>
                        <th><?= __('admin.col_actions') ?></th>
                    </tr>
                </thead>
                <tbody id="admin-gallery-body">
                    <tr><td colspan="7" style="text-align:center;"><?= __('admin.loading') ?></td></tr>
                </tbody>
            </table>
        </div>
    </div>

    <!-- Pending User Submissions -->
    <div class="settings-section" style="margin-top:1.5rem;">
        <h2><?= icon('upload') ?> <?= __('admin.submissions_title') ?></h2>
        <p style="font-size:0.8rem;color:var(--muted-foreground);margin-bottom:1rem;"><?= __('admin.submissions_desc') ?></p>
        <div id="pending-submissions-empty" style="text-align:center;color:var(--muted-foreground);padding:1rem;display:none;"><?= __('admin.no_submissions') ?></div>
        <div id="pending-submissions-list" style="display:flex;flex-direction:column;gap:0.75rem;"></div>
    </div>
</div>

<script>
const I18N_ADMIN = {
    users_total:      <?= json_encode(__('admin.users_total')) ?>,
    active_24h:       <?= json_encode(__('admin.active_24h')) ?>,
    conversations:    <?= json_encode(__('admin.conversations')) ?>,
    messages:         <?= json_encode(__('admin.messages')) ?>,
    today:            <?= json_encode(__('admin.today')) ?>,
    no_users:         <?= json_encode(__('admin.no_users')) ?>,
    today_suffix:     <?= json_encode(__('admin.today_suffix')) ?>,
    suspend:          <?= json_encode(__('admin.suspend')) ?>,
    activate:         <?= json_encode(__('admin.activate')) ?>,
    confirm_suspend:  <?= json_encode(__('admin.confirm_suspend')) ?>,
    confirm_activate: <?= json_encode(__('admin.confirm_activate')) ?>,
    invited:          <?= json_encode(__('admin.invited')) ?>,
    error:            <?= json_encode(__('admin.error')) ?>,
    error_unknown:    <?= json_encode(__('admin.error_unknown')) ?>,
};

async function loadAdminData() {
    try {
    // Stats
    const statsRes = await fetch('/api.php?action=admin_stats');
    const statsData = await statsRes.json();
    if (statsData.success) {
        const s = statsData.stats;
        document.getElementById('admin-stats').innerHTML = `
            <div class="stat-card"><div class="stat-value">${s.users_total}</div><div class="stat-label">${I18N_ADMIN.users_total}</div></div>
            <div class="stat-card"><div class="stat-value">${s.users_active_24h}</div><div class="stat-label">${I18N_ADMIN.active_24h}</div></div>
            <div class="stat-card"><div class="stat-value">${s.conversations ?? s.conversations_total ?? '—'}</div><div class="stat-label">${I18N_ADMIN.conversations}</div></div>
            <div class="stat-card"><div class="stat-value">${s.messages_total}</div><div class="stat-label">${I18N_ADMIN.messages}</div></div>
            <div class="stat-card"><div class="stat-value">${s.messages_today}</div><div class="stat-label">${I18N_ADMIN.today}</div></div>
        `;
    } else {
        document.getElementById('admin-stats').innerHTML = '<div class="stat-card"><div class="stat-value">❌</div><div class="stat-label">' + escH(statsData.error || 'Fehler beim Laden') + '</div></div>';
    }

    // Users + learning access in parallel
    const [usersRes, learningRes] = await Promise.all([
        fetch('/api.php?action=admin_users'),
        fetch('/api.php?action=learning_admin_access_list')
    ]);
    const usersData = await usersRes.json();
    const learningData = await learningRes.json();
    const learningAccess = (learningData.success && learningData.access) ? learningData.access : {};

    if (usersData.success) {
        const tbody = document.getElementById('admin-users-body');
        if (usersData.users.length === 0) {
            tbody.innerHTML = `<tr><td colspan="12" style="text-align:center;">${I18N_ADMIN.no_users}</td></tr>`;
            return;
        }
        tbody.innerHTML = usersData.users.map(u => {
            const statusBadge = u.status === 'active' ? 'badge-active' :
                                u.status === 'suspended' ? 'badge-suspended' : '';
            const roleBadge = u.role === 'admin' ? '<span class="badge badge-admin">Admin</span> ' : '';
            const lastActive = u.last_active ? new Date(u.last_active).toLocaleString('de-DE') : '—';
            const toggleAction = u.status === 'active' ? 'suspended' : 'active';
            const toggleLabel = u.status === 'active' ? '⏸️' : '▶️';
            const toggleTitle = toggleAction === 'suspended' ? I18N_ADMIN.suspend : I18N_ADMIN.activate;
            const imgQuota = u.image_quota_daily || 0;
            const imgUsed = u.images_generated_today || 0;
            const songQuota = u.song_quota_daily || 0;
            const songUsed = u.songs_generated_today || 0;
            const vBalance = parseFloat(u.vdollars_balance || 0).toFixed(0);
            const vAllowance = u.vdollars_weekly_allowance || 100;
            const vActiveDays = (u.vdollars_active_days || '').split(',').filter(Boolean).length;
            const isAdmin = u.role === 'admin';
            const userTier = u.user_tier || 'invited';
            const tierBadge = isAdmin ? '<span class="badge badge-admin">Admin</span>'
                : userTier === 'invited' ? '<span class="badge" style="background:#6366f1;color:#fff;font-size:0.7rem;">⭐ invited</span>'
                : '<span class="badge" style="background:#64748b;color:#fff;font-size:0.7rem;">🌐 public</span>';
            const tierAction = (!isAdmin && userTier === 'public')
                ? ` <button class="btn btn-ghost btn-sm" onclick="adminUpgradeTier('${u.id}')" title="Upgrade zu Invited" style="font-size:0.7rem;">⬆️</button>`
                : '';
            const imgDisplay = isAdmin ? '♾️' : `${imgUsed}/${imgQuota}`;
            const songDisplay = isAdmin ? '♾️' : `${songUsed}/${songQuota}`;
            const hasImageGen = isAdmin || !!(u.tools_image_gen);
            const hasSongGen = isAdmin || !!(u.tools_song_gen);
            const hasLearning = isAdmin || !!learningAccess[u.id];
            const learnToggle = isAdmin
                ? '<span style="font-size:0.85rem;" title="Admins haben immer Zugriff">✅</span>'
                : `<button class="btn btn-ghost btn-sm" onclick="adminToggleLearning('${u.id}',${hasLearning ? 'false' : 'true'})" title="${hasLearning ? 'Lernen deaktivieren' : 'Lernen aktivieren'}" style="font-size:0.85rem;">${hasLearning ? '✅' : '❌'}</button>`;
            const warnLevel = u.warning_level || 0;
            const warnReason = u.warning_reason || '';
            const bannedUntil = u.banned_until || '';
            const warnBadges = ['🟢','⚠️','🔴1h','🔴24h','🔴7d','⛔'];
            const warnBadge = warnBadges[Math.min(warnLevel, 5)];
            const warnTitle = warnLevel > 0 ? `Stufe ${warnLevel}: ${warnReason}${bannedUntil ? ' (bis ' + new Date(bannedUntil).toLocaleString('de-DE') + ')' : ''}` : 'Keine Verwarnung';
            const warnHtml = isAdmin
                ? '<span style="font-size:0.85rem;" title="Admins können nicht verwarnt werden">—</span>'
                : `<div style="display:flex;flex-direction:column;gap:2px;align-items:center;">
                    <span style="font-size:0.85rem;cursor:help;" title="${escH(warnTitle)}">${warnBadge}</span>
                    <select onchange="adminSetWarning('${u.id}',this.value)" style="width:55px;padding:1px 2px;border:1px solid rgba(255,255,255,0.15);border-radius:4px;background:rgba(0,0,0,0.2);color:inherit;font-size:0.7rem;">
                        ${[0,1,2,3,4,5].map(l => `<option value="${l}" ${l===warnLevel?'selected':''}>${l}</option>`).join('')}
                    </select>
                   </div>`;
            const toolsHtml = isAdmin
                ? '<span style="font-size:0.75rem;" title="Admins haben immer Zugriff">🎨✅ 🎵✅</span>'
                : `<div style="display:flex;flex-direction:column;gap:2px;font-size:0.75rem;">
                    <label style="cursor:pointer;white-space:nowrap;" title="Bildgenerierung freischalten">🎨<input type="checkbox" ${hasImageGen ? 'checked' : ''} onchange="adminToggleTool('${u.id}','image_gen',this.checked)" style="margin-left:3px;"></label>
                    <label style="cursor:pointer;white-space:nowrap;" title="Songgenerierung freischalten">🎵<input type="checkbox" ${hasSongGen ? 'checked' : ''} onchange="adminToggleTool('${u.id}','song_gen',this.checked)" style="margin-left:3px;"></label>
                   </div>`;
            return `
                <tr>
                    <td>${roleBadge}${escH(u.display_name)}</td>
                    <td style="font-size:0.8rem;">${escH(u.email)}</td>
                    <td style="text-align:center;">${tierBadge}${tierAction}</td>
                    <td><span class="badge ${statusBadge}">${escH(u.status)}</span></td>
                    <td>${u.messages_total} (${u.messages_today} ${I18N_ADMIN.today_suffix})</td>
                    <td style="white-space:nowrap;">
                        <span style="font-size:0.85rem;" title="V$ Balance">${isAdmin ? '♾️' : vBalance + ' V$'}</span>
                        ${!isAdmin ? `<input type="number" min="0" max="99999" value="${vBalance}" style="width:60px;margin-left:4px;padding:2px 4px;border:1px solid rgba(255,255,255,0.15);border-radius:4px;background:rgba(0,0,0,0.2);color:inherit;font-size:0.8rem;" onchange="adminSetVdollarsBalance('${u.id}',this.value)" title="V$ Balance direkt setzen">
                        <button class="btn btn-ghost btn-sm" onclick="adminSendVdollars('${u.id}')" title="V$ senden" style="font-size:0.75rem;margin-left:2px;">💸</button>` : ''}
                    </td>
                    <td style="white-space:nowrap;">
                        <span style="font-size:0.85rem;" title="Wöchentliches V$ Guthaben (${vActiveDays}/7 Tage aktiv)">${isAdmin ? '♾️' : vAllowance + '/W'}</span>
                        ${!isAdmin ? `<input type="number" min="0" max="9999" value="${vAllowance}" style="width:55px;margin-left:4px;padding:2px 4px;border:1px solid rgba(255,255,255,0.15);border-radius:4px;background:rgba(0,0,0,0.2);color:inherit;font-size:0.8rem;" onchange="adminSetVdollarsAllowance('${u.id}',this.value)" title="V$ pro Woche">` : ''}
                    </td>
                    <td style="text-align:center;">${toolsHtml}</td>
                    <td style="text-align:center;">${learnToggle}</td>
                    <td style="text-align:center;">${warnHtml}</td>
                    <td style="font-size:0.8rem;">${lastActive}</td>
                    <td>
                        <button class="btn btn-ghost btn-sm" onclick="adminToggleUser('${u.id}','${toggleAction}')" title="${toggleTitle}">${toggleLabel}</button>
                    </td>
                </tr>
            `;
        }).join('');
    }
    } catch (err) {
        console.error('loadAdminData error:', err);
        document.getElementById('admin-stats').innerHTML = '<div class="stat-card"><div class="stat-value">❌</div><div class="stat-label">Verbindungsfehler — lade Seite neu</div></div>';
        document.getElementById('admin-users-body').innerHTML = '<tr><td colspan="12" style="text-align:center;color:#f87171;">Fehler: ' + escH(err.message) + '</td></tr>';
    }
}

async function adminInvite() {
    const email = document.getElementById('invite-email').value.trim();
    const result = document.getElementById('invite-result');
    if (!email) return;

    const resp = await fetch('/api.php?action=admin_whitelist_add', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({email})
    });
    const data = await resp.json();
    if (data.success) {
        result.innerHTML = `<strong>${escH(email)}</strong> ${I18N_ADMIN.invited} <code>${escH(data.invite_code)}</code>`;
        document.getElementById('invite-email').value = '';
    } else {
        result.innerHTML = `${I18N_ADMIN.error} ${escH(data.error || I18N_ADMIN.error_unknown)}`;
    }
}

async function adminToggleUser(userId, newStatus) {
    const msg = newStatus === 'suspended' ? I18N_ADMIN.confirm_suspend : I18N_ADMIN.confirm_activate;
    if (!confirm(msg)) return;

    await fetch('/api.php?action=admin_suspend_user', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({user_id: userId, status: newStatus})
    });
    loadAdminData();
}

async function adminSetImageQuota(userId, quota) {
    const val = parseInt(quota) || 0;
    const resp = await fetch('/api.php?action=admin_set_image_quota', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({user_id: userId, quota: val})
    });
    const data = await resp.json();
    if (data.success) {
        event.target.style.borderColor = 'rgba(34,197,94,0.5)';
        setTimeout(() => { event.target.style.borderColor = ''; }, 1500);
    }
}

async function adminSetSongQuota(userId, quota) {
    const val = parseInt(quota) || 0;
    const resp = await fetch('/api.php?action=admin_set_song_quota', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({user_id: userId, quota: val})
    });
    const data = await resp.json();
    if (data.success) {
        event.target.style.borderColor = 'rgba(34,197,94,0.5)';
        setTimeout(() => { event.target.style.borderColor = ''; }, 1500);
    }
}

async function adminSetVdollarsBalance(userId, balance) {
    const val = parseFloat(balance) || 0;
    const resp = await fetch('/api.php?action=admin_set_vdollars_balance', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({user_id: userId, balance: val})
    });
    const data = await resp.json();
    if (data.success && event && event.target) {
        event.target.style.borderColor = 'rgba(34,197,94,0.5)';
        setTimeout(() => { event.target.style.borderColor = ''; }, 1500);
    }
}

async function adminSendVdollars(userId) {
    const amount = prompt('V$ senden — Betrag (1-1000):');
    if (!amount || isNaN(amount) || amount < 1) return;
    const reason = prompt('Grund (optional):', 'Admin-Geschenk') || 'Admin-Geschenk';
    const resp = await fetch('/api.php?action=admin_send_vdollars', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({user_id: userId, amount: parseFloat(amount), reason: reason})
    });
    const data = await resp.json();
    if (data.success) {
        alert(`✅ ${amount} V$ gesendet! Neues Guthaben: ${data.balance} V$`);
        loadAdminData();
    } else {
        alert('Fehler: ' + (data.error || 'Unbekannt'));
    }
}

async function adminUpgradeTier(userId) {
    if (!confirm('User von Public → Invited upgraden? (Bekommt Chat + Generation + 100 V$/Woche)')) return;
    const resp = await fetch('/api.php?action=admin_set_user_tier', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({user_id: userId})
    });
    const data = await resp.json();
    if (data.success) {
        alert('✅ User auf Invited geupgraded!');
        loadAdminData();
    } else {
        alert('Fehler: ' + (data.error || 'Unbekannt'));
    }
}

async function adminSetVdollarsAllowance(userId, allowance) {
    const val = parseInt(allowance) || 0;
    const resp = await fetch('/api.php?action=admin_set_vdollars_allowance', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({user_id: userId, allowance: val})
    });
    const data = await resp.json();
    if (data.success && event && event.target) {
        event.target.style.borderColor = 'rgba(34,197,94,0.5)';
        setTimeout(() => { event.target.style.borderColor = ''; }, 1500);
    }
}

async function adminToggleTool(userId, tool, enabled) {
    const resp = await fetch('/api.php?action=admin_set_tool_access', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({user_id: userId, tool: tool, enabled: enabled})
    });
    const data = await resp.json();
    if (!data.success) {
        alert('Fehler beim Setzen der Tool-Berechtigung');
        loadAdminData();
    }
}

async function adminToggleLearning(userId, enable) {
    const resp = await fetch('/api.php?action=learning_admin_toggle', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({user_id: userId, enabled: enable})
    });
    const data = await resp.json();
    if (data.success) loadAdminData();
}

async function adminSetWarning(userId, level) {
    const val = parseInt(level) || 0;
    const labels = {0:'Verwarnung aufheben',1:'Stufe 1 (Verbale Warnung)',2:'Stufe 2 (1h Ban)',3:'Stufe 3 (24h Ban)',4:'Stufe 4 (1 Woche Ban)',5:'Stufe 5 (Permaban)'};
    if (!confirm(`Warnstufe für diesen User auf ${labels[val] || val} setzen?`)) {
        loadAdminData();
        return;
    }
    const resp = await fetch('/api.php?action=admin_set_warning', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({user_id: userId, level: val})
    });
    const data = await resp.json();
    if (data.success) {
        loadAdminData();
    } else {
        alert('Fehler: ' + (data.error || 'Unbekannt'));
        loadAdminData();
    }
}

function escH(s) {
    const el = document.createElement('span');
    el.textContent = s || '';
    return el.innerHTML;
}

loadAdminData();

// ── Moderation Reports ──
let allModReports = [];
let modFilter = null;

async function loadModerationReports() {
    try {
        const res = await fetch('/api.php?action=admin_moderation_reports');
        const data = await res.json();
        if (!data.success) return;
        allModReports = data.reports || [];
        const badge = document.getElementById('moderation-badge');
        const pendingCount = data.pending_count || 0;
        if (pendingCount > 0) {
            badge.textContent = pendingCount;
            badge.style.display = '';
        } else {
            badge.style.display = 'none';
        }
        renderModReports();
    } catch (err) {
        console.error('loadModerationReports error:', err);
    }
}

function filterModReports(status, btn) {
    modFilter = status;
    document.querySelectorAll('.mod-filter-active').forEach(b => b.classList.remove('mod-filter-active'));
    if (btn) btn.classList.add('mod-filter-active');
    renderModReports();
}

function renderModReports() {
    const list = document.getElementById('moderation-list');
    const empty = document.getElementById('moderation-empty');
    let items = allModReports;
    if (modFilter) items = items.filter(r => r.status === modFilter);

    if (items.length === 0) {
        list.innerHTML = '';
        empty.style.display = '';
        return;
    }
    empty.style.display = 'none';

    list.innerHTML = items.map(r => {
        const isPending = r.status === 'pending';
        const date = r.created_at ? new Date(r.created_at).toLocaleString('de-DE') : '—';
        const statusIcon = r.status === 'pending' ? '⏳' : r.status === 'reviewed' ? '✅' : '🗑️';
        const msgPreview = escH((r.message || '').substring(0, 300));
        const patterns = r.detected_patterns ? escH(r.detected_patterns) : '—';
        const currentWarn = r.warning_level || 0;
        const warnBadges = ['🟢','⚠️','🔴1h','🔴24h','🔴7d','⛔'];
        const warnBadge = warnBadges[Math.min(currentWarn, 5)];

        const resolvedInfo = !isPending && r.resolved_at
            ? `<div style="font-size:0.75rem;color:var(--muted-foreground);margin-top:0.5rem;">
                ${statusIcon} ${escH(r.admin_action || 'Bearbeitet')} ${r.admin_note ? '— ' + escH(r.admin_note) : ''} 
                · ${new Date(r.resolved_at).toLocaleString('de-DE')}
               </div>`
            : '';

        const actionsHtml = isPending ? `
            <div style="display:flex;gap:0.5rem;flex-wrap:wrap;margin-top:0.75rem;align-items:flex-end;">
                <div style="display:flex;flex-direction:column;gap:2px;">
                    <label style="font-size:0.7rem;color:var(--muted-foreground);">Warnstufe setzen:</label>
                    <select id="mod-warn-${r.id}" style="padding:4px 6px;border:1px solid rgba(255,255,255,0.15);border-radius:4px;background:rgba(0,0,0,0.2);color:inherit;font-size:0.8rem;">
                        <option value="">— keine Änderung —</option>
                        <option value="0">🟢 0 – Aufheben</option>
                        <option value="1">⚠️ 1 – Verbale Warnung</option>
                        <option value="2">🔴 2 – 1h Sperre</option>
                        <option value="3">🔴 3 – 24h Sperre</option>
                        <option value="4">🔴 4 – 1 Woche Sperre</option>
                        <option value="5">⛔ 5 – Permaban</option>
                    </select>
                </div>
                <div style="display:flex;flex-direction:column;gap:2px;flex:1;">
                    <label style="font-size:0.7rem;color:var(--muted-foreground);">Nachricht an User senden:</label>
                    <input type="text" id="mod-msg-${r.id}" placeholder="Optional: Verwarnung in den Chat schreiben…" style="padding:4px 8px;border:1px solid rgba(255,255,255,0.15);border-radius:4px;background:rgba(0,0,0,0.2);color:inherit;font-size:0.8rem;width:100%;">
                </div>
                <button class="btn btn-sm" style="background:var(--primary);color:#fff;" onclick="resolveModReport('${r.id}','${r.user_id}','reviewed')">✅ Bearbeiten</button>
                <button class="btn btn-ghost btn-sm" onclick="resolveModReport('${r.id}','${r.user_id}','dismissed')">🗑️ Verwerfen</button>
            </div>
        ` : '';

        return `<div class="submission-card" style="border-left:3px solid ${isPending ? 'var(--primary)' : 'rgba(255,255,255,0.1)'};">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.5rem;">
                <div>
                    <strong>${escH(r.user_name || 'Unbekannt')}</strong>
                    <span style="font-size:0.75rem;color:var(--muted-foreground);margin-left:0.5rem;">Score: ${r.troll_score} · Aktuell: ${warnBadge}</span>
                </div>
                <div style="font-size:0.75rem;color:var(--muted-foreground);">${statusIcon} ${date}</div>
            </div>
            <div style="font-size:0.85rem;background:rgba(0,0,0,0.15);padding:0.5rem 0.75rem;border-radius:6px;margin-bottom:0.25rem;white-space:pre-wrap;word-break:break-word;">${msgPreview}</div>
            <div style="font-size:0.7rem;color:var(--muted-foreground);">Patterns: ${patterns}</div>
            ${resolvedInfo}
            ${actionsHtml}
        </div>`;
    }).join('');
}

async function resolveModReport(reportId, userId, resolution) {
    const warnSelect = document.getElementById('mod-warn-' + reportId);
    const msgInput = document.getElementById('mod-msg-' + reportId);
    const warnLevel = warnSelect ? warnSelect.value : '';
    const chatMsg = msgInput ? msgInput.value.trim() : '';
    let actionParts = [];

    // 1. Set warning level if chosen
    if (warnLevel !== '') {
        const level = parseInt(warnLevel);
        await fetch('/api.php?action=admin_set_warning', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({user_id: userId, level: level})
        });
        const labels = {0:'Aufgehoben',1:'Stufe 1',2:'Stufe 2 (1h)',3:'Stufe 3 (24h)',4:'Stufe 4 (7d)',5:'Permaban'};
        actionParts.push('Warnung: ' + (labels[level] || level));
    }

    // 2. Send chat warning if provided
    if (chatMsg) {
        await fetch('/api.php?action=admin_send_chat_warning', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({user_id: userId, message: chatMsg})
        });
        actionParts.push('Chat-Nachricht gesendet');
    }

    // 3. Resolve the report
    const action = actionParts.length > 0 ? actionParts.join(' + ') : (resolution === 'dismissed' ? 'Verworfen' : 'Ohne Aktion');
    await fetch('/api.php?action=admin_resolve_report', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({report_id: reportId, resolution: resolution, action: action, note: chatMsg || null})
    });

    loadModerationReports();
    loadAdminData();
}

loadModerationReports();

// ── Limits Management ──
async function loadLimits() {
    const res = await fetch('/api.php?action=admin_get_limits');
    const data = await res.json();
    if (!data.success) return;
    const L = data.limits;
    const setSlider = (id, val) => {
        const el = document.getElementById(id);
        el.value = val;
        document.getElementById(id + '-val').textContent = val;
    };
    setSlider('limit-max-message-length', L.max_message_length);
    setSlider('limit-max-hourly', L.max_hourly);
    setSlider('limit-max-daily', L.max_daily);
}

async function saveLimits() {
    const body = {
        max_message_length: parseInt(document.getElementById('limit-max-message-length').value),
        max_hourly:         parseInt(document.getElementById('limit-max-hourly').value),
        max_daily:          parseInt(document.getElementById('limit-max-daily').value),
    };
    const res = await fetch('/api.php?action=admin_set_limits', {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify(body)
    });
    const data = await res.json();
    const el = document.getElementById('limits-result');
    if (data.success) {
        el.innerHTML = '✅ Limits gespeichert!';
        setTimeout(() => { el.innerHTML = ''; }, 3000);
    } else {
        el.innerHTML = '❌ Fehler: ' + escH(data.error || 'Unbekannt');
    }
}

loadLimits();

// ── Intro Song Selection ──
async function loadIntroSongOptions() {
    // Load all songs for dropdown
    const [settingRes, songsRes] = await Promise.all([
        fetch('/api.php?action=admin_get_intro_song'),
        fetch('/api.php?action=get_gallery&type=song&limit=100')
    ]);
    const settingData = await settingRes.json();
    const songsData = await songsRes.json();
    const sel = document.getElementById('intro-song-select');
    const current = settingData.success ? settingData.intro_song : 'auto';

    // Add song options
    if (songsData.success && songsData.items) {
        const sep = document.createElement('option');
        sep.disabled = true;
        sep.textContent = '── Songs ──';
        sel.appendChild(sep);
        songsData.items.forEach(item => {
            const meta = item.metadata || {};
            const hasAudio = meta.audio_url || (item.file_url && item.file_url.match(/\.mp3$/i));
            if (!hasAudio) return;
            const opt = document.createElement('option');
            opt.value = String(item.id);
            const album = meta.album_title ? ` [${meta.album_title}]` : '';
            opt.textContent = `🎵 ${item.title}${album}`;
            sel.appendChild(opt);
        });
    }
    sel.value = current;
}
async function saveIntroSong() {
    const val = document.getElementById('intro-song-select').value;
    const res = await fetch('/api.php?action=admin_set_intro_song', {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({intro_song: val})
    });
    const data = await res.json();
    const el = document.getElementById('intro-song-result');
    if (data.success) {
        el.innerHTML = '✅ Intro-Song gespeichert!';
        setTimeout(() => { el.innerHTML = ''; }, 3000);
    } else {
        el.innerHTML = '❌ Fehler: ' + escH(data.error || 'Unbekannt');
    }
}
loadIntroSongOptions();

// ── Dev-Link: Next.js Mainapp (password-gated) ──
async function devlinkFetch() {
    const pw = document.getElementById('devlink-password').value;
    const errEl = document.getElementById('devlink-error');
    const urlsEl = document.getElementById('devlink-urls');
    errEl.textContent = '';
    urlsEl.style.display = 'none';
    urlsEl.innerHTML = '';
    if (!pw) { errEl.textContent = 'Passwort eingeben.'; return; }
    try {
        const res = await fetch('/api.php?action=admin_get_devlink', {
            method: 'POST',
            headers: {'Content-Type':'application/json'},
            body: JSON.stringify({password: pw})
        });
        const data = await res.json();
        if (!data.success) {
            errEl.textContent = '❌ ' + (data.error || 'Fehler');
            return;
        }
        const lan = data.urls?.lan_url || '';
        const pub = data.urls?.public_url || '';
        const pub6 = data.urls?.public_ipv6_url || '';
        const updated = data.updated_at ? new Date(data.updated_at).toLocaleString('de-DE') : '—';
        const mk = (label, url, hint) => url
            ? `<a href="${escH(url)}" target="_blank" rel="noopener" class="btn btn-primary btn-sm" style="justify-content:flex-start;">${label}: ${escH(url)}</a><div style="font-size:0.7rem;color:var(--muted-foreground);margin-top:-4px;">${hint}</div>`
            : `<div style="font-size:0.8rem;color:var(--muted-foreground);">${label}: (noch nicht gemeldet)</div>`;
        urlsEl.innerHTML = `
            ${mk('🏠 LAN', lan, 'Funktioniert nur im Heimnetzwerk.')}
            ${mk('🌍 IPv6 (Public, mobil/LTE)', pub6, 'Direkt erreichbar, KEIN Port-Forwarding nötig. Client braucht IPv6 (Handy via LTE/5G meist ja).')}
            ${mk('🌐 IPv4 (Public)', pub, 'Nur mit Port-Forwarding + echter IPv4. Bei DS-Lite/CGNAT (o2, 1&1, Vodafone Kabel) meist NICHT nutzbar.')}
            <div style="font-size:0.7rem;color:var(--muted-foreground);margin-top:0.25rem;">Zuletzt aktualisiert: ${escH(updated)}${data.note ? ' · ' + escH(data.note) : ''}</div>
        `;
        urlsEl.style.display = 'flex';
        // Clear password after success
        document.getElementById('devlink-password').value = '';
    } catch (e) {
        errEl.textContent = '❌ Netzwerk-Fehler: ' + e.message;
    }
}
// Enter-key shortcut
document.getElementById('devlink-password')?.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') devlinkFetch();
});

// ── Gallery Management ──
let allGalleryItems = [];
let galleryFilter = null;

async function loadGalleryItems() {
    const res = await fetch('/api.php?action=admin_gallery');
    const data = await res.json();
    if (!data.success) return;
    allGalleryItems = data.items;
    renderGalleryTable();
}

function filterGallery(type, btn) {
    galleryFilter = type;
    document.querySelectorAll('#admin-gallery-table').forEach(t => {
        t.closest('.settings-section').querySelectorAll('.btn-ghost').forEach(b => b.classList.remove('filter-active'));
    });
    if (btn) btn.classList.add('filter-active');
    renderGalleryTable();
}

function renderGalleryTable() {
    const tbody = document.getElementById('admin-gallery-body');
    let items = allGalleryItems;
    if (galleryFilter) items = items.filter(i => i.item_type === galleryFilter);
    if (items.length === 0) {
        tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;">Keine Einträge</td></tr>';
        return;
    }
    const typeIcons = {song:'🎵', svg:'🎨', book:'📖', image:'🖼️', code:'💻'};
    tbody.innerHTML = items.map(i => {
        const pub = i.published == 1;
        const blocked = (i.source_id||'').startsWith('BLOCKED:');
        const statusBadge = blocked ? '<span class="badge badge-suspended">🚫 gesperrt</span>'
            : pub ? '<span class="badge badge-active">✅ live</span>'
            : '<span class="badge badge-suspended">verborgen</span>';
        const title = escH((i.title||'').substring(0, 50));
        const srcId = escH((i.source_id||'').substring(0, 30));
        const date = i.created_at ? new Date(i.created_at).toLocaleDateString('de-DE') : '—';
        return '<tr>'
            + '<td style="font-size:0.75rem;">' + i.id + '</td>'
            + '<td>' + (typeIcons[i.item_type]||'') + ' ' + i.item_type + '</td>'
            + '<td style="max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="' + escH(i.title) + '">' + title + '</td>'
            + '<td style="font-size:0.7rem;max-width:150px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">' + srcId + '</td>'
            + '<td>' + statusBadge + '</td>'
            + '<td style="font-size:0.8rem;">' + date + '</td>'
            + '<td>'
            + (blocked ? '<button class="btn btn-ghost btn-sm" onclick="adminGalleryUnblock(' + i.id + ')" title="Entsperren & wieder veröffentlichen">🔓</button>' : '')
            + (pub && !blocked ? '<button class="btn btn-ghost btn-sm" onclick="adminGalleryAction(' + i.id + ',false)" title="Verbergen + Sync-Sperre">🚫</button>' : '')
            + '<button class="btn btn-ghost btn-sm" onclick="adminGalleryAction(' + i.id + ',true)" title="Permanent löschen">🗑️</button>'
            + '</td>'
            + '</tr>';
    }).join('');
}

async function adminGalleryAction(id, permanent) {
    const msg = permanent
        ? 'Diesen Eintrag PERMANENT löschen und für zukünftige Syncs sperren?'
        : 'Diesen Eintrag verbergen und für zukünftige Syncs sperren?';
    if (!confirm(msg)) return;
    await fetch('/api.php?action=admin_gallery_delete', {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({id: id, permanent: permanent})
    });
    loadGalleryItems();
}

async function adminGalleryUnblock(id) {
    if (!confirm('Diesen Eintrag entsperren und wieder veröffentlichen?')) return;
    await fetch('/api.php?action=admin_gallery_unblock', {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({id: id})
    });
    loadGalleryItems();
}

loadGalleryItems();

// ── Pending Submissions ──
async function loadPendingSubmissions() {
    const res = await fetch('/api.php?action=admin_pending_submissions');
    const data = await res.json();
    if (!data.success) return;
    const list = document.getElementById('pending-submissions-list');
    const empty = document.getElementById('pending-submissions-empty');
    const subs = data.submissions || [];
    if (subs.length === 0) {
        list.innerHTML = '';
        empty.style.display = '';
        return;
    }
    empty.style.display = 'none';
    const subTypeIcons = {song:'🎵', svg:'🎨', book:'📖', image:'🖼️', code:'💻'};
    list.innerHTML = subs.map(s => {
        const ic = subTypeIcons[s.item_type] || '📄';
        const title = escH((s.title || '').substring(0, 80));
        const submitter = escH(s.submitter_name || 'Unbekannt');
        const date = s.created_at ? new Date(s.created_at).toLocaleDateString('de-DE') : '—';
        const preview = s.item_type === 'image' && s.file_url
            ? `<img src="${escH(s.file_url)}" alt="${title}" style="max-width:200px;max-height:120px;border-radius:8px;border:1px solid rgba(168,85,247,0.3);">`
            : escH((s.content_text || '').substring(0, 200));
        return `<div class="submission-card" id="sub-${s.id}">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.5rem;">
                <div><strong>${ic} ${title}</strong></div>
                <div style="font-size:0.75rem;color:var(--muted-foreground);">von ${submitter} · ${date}</div>
            </div>
            <div style="font-size:0.8rem;color:var(--muted-foreground);margin-bottom:0.5rem;max-height:60px;overflow:hidden;">${preview}</div>
            <div style="display:flex;gap:0.5rem;">
                <button class="btn btn-sm" style="background:var(--primary);color:#fff;" onclick="reviewSubmission(${s.id},'approved')">✅ Freigeben</button>
                <button class="btn btn-ghost btn-sm" onclick="reviewSubmission(${s.id},'rejected')">❌ Ablehnen</button>
            </div>
        </div>`;
    }).join('');
}

async function reviewSubmission(id, decision) {
    const label = decision === 'approved' ? 'freigeben' : 'ablehnen';
    if (!confirm('Diesen Beitrag wirklich ' + label + '?')) return;
    await fetch('/api.php?action=admin_review_submission', {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({id, decision})
    });
    const card = document.getElementById('sub-' + id);
    if (card) card.style.display = 'none';
    loadPendingSubmissions();
    if (decision === 'approved') loadGalleryItems();
}

loadPendingSubmissions();
</script>

<?php portal_footer(); ?>
