<?php
/**
 * A!ley Portal — Settings Page
 */
require_once __DIR__ . '/layout.php';
portal_head(__('settings.title'));
$userName = htmlspecialchars($user['display_name'] ?? '');
$userEmail = htmlspecialchars($user['email'] ?? '');
?>

<div class="settings-page">
    <a href="/chat" class="legal-back"><?= __('back_to_chat') ?></a>

    <h1 style="font-size:1.3rem; font-weight:700; margin-bottom:1.5rem;"><?= __('settings.title') ?></h1>

    <!-- Theme -->
    <div class="settings-section">
        <h2><?= icon('palette') ?> <?= __('settings.theme') ?></h2>
        <div class="theme-selector">
            <div class="theme-option" data-theme="ailey">
                <div class="theme-option-icon"><?= icon('theater') ?></div>
                <div class="theme-option-label">A!ley</div>
            </div>
            <div class="theme-option" data-theme="dark">
                <div class="theme-option-icon"><?= icon('moon') ?></div>
                <div class="theme-option-label">Dark</div>
            </div>
            <div class="theme-option" data-theme="light">
                <div class="theme-option-icon"><?= icon('sun') ?></div>
                <div class="theme-option-label">Light</div>
            </div>
            <div class="theme-option" data-theme="cyber">
                <div class="theme-option-icon"><?= icon('zap') ?></div>
                <div class="theme-option-label">Cyber</div>
            </div>
        </div>
    </div>

    <!-- Profile -->
    <div class="settings-section">
        <h2><?= icon('user') ?> <?= __('settings.profile') ?></h2>

        <!-- Avatar Upload -->
        <div class="profile-avatar-section">
            <div class="profile-avatar-preview" id="profile-avatar-preview">
                <?php if (!empty($user['avatar_url'])): ?>
                <img src="<?= e($user['avatar_url']) ?>" alt="Avatar" class="profile-avatar-img">
                <?php else: ?>
                <div class="profile-avatar-placeholder"><?= mb_strtoupper(mb_substr($user['display_name'] ?? 'U', 0, 1)) ?></div>
                <?php endif; ?>
            </div>
            <div class="profile-avatar-controls">
                <input type="file" id="avatar-file-input" accept="image/jpeg,image/png,image/webp,image/gif" style="display:none" onchange="uploadAvatar(this)">
                <button class="btn btn-sm" onclick="document.getElementById('avatar-file-input').click()">
                    📷 <?= __('settings.upload_avatar') ?>
                </button>
                <span class="profile-avatar-hint"><?= __('settings.avatar_hint') ?></span>
            </div>
        </div>

        <!-- Display Name -->
        <div class="form-group">
            <label class="form-label"><?= __('settings.name') ?></label>
            <input class="form-input" type="text" id="profile-display-name" value="<?= $userName ?>" maxlength="50">
        </div>
        <div class="form-group">
            <label class="form-label"><?= __('settings.email') ?></label>
            <input class="form-input" type="email" value="<?= $userEmail ?>" disabled>
        </div>
        <!-- Bio -->
        <div class="form-group">
            <label class="form-label"><?= __('settings.bio') ?></label>
            <textarea class="form-input" id="profile-bio" maxlength="500" rows="3" placeholder="<?= __('settings.bio_placeholder') ?>"><?= e($user['bio'] ?? '') ?></textarea>
        </div>
        <button class="btn btn-primary btn-sm" onclick="saveProfile()" style="margin-top:0.5rem;">
            <?= icon('save') ?> <?= __('settings.save_profile') ?>
        </button>
    </div>

    <!-- Badges -->
    <div class="settings-section">
        <h2>🏆 <?= __('settings.badges') ?></h2>
        <p style="font-size:0.8rem; color:var(--muted-foreground); margin-bottom:1rem;">
            <?= __('settings.badges_hint') ?>
        </p>
        <div class="badge-grid" id="badge-grid">
            <div class="loading-spinner" style="text-align:center; padding:1rem;">⏳</div>
        </div>
    </div>

    <!-- Custom Instructions -->
    <div class="settings-section">
        <h2><?= icon('pencil') ?> <?= __('settings.custom') ?></h2>
        <p style="font-size:0.8rem; color:var(--muted-foreground); margin-bottom:1rem;">
            <?= __('settings.custom_hint') ?>
        </p>
        <div class="custom-instructions-section">
            <div>
                <label for="ci-about"><?= __('settings.ci_about') ?></label>
                <p class="ci-hint"><?= __('settings.ci_about_hint') ?></p>
                <textarea id="ci-about" placeholder="<?= __('settings.ci_about_placeholder') ?>"></textarea>
            </div>
            <div>
                <label for="ci-style"><?= __('settings.ci_style') ?></label>
                <p class="ci-hint"><?= __('settings.ci_style_hint') ?></p>
                <textarea id="ci-style" placeholder="<?= __('settings.ci_style_placeholder') ?>"></textarea>
            </div>
            <div>
                <label for="ci-other"><?= __('settings.ci_other') ?></label>
                <p class="ci-hint"><?= __('settings.ci_other_hint') ?></p>
                <textarea id="ci-other" placeholder="<?= __('settings.ci_other_placeholder') ?>"></textarea>
            </div>
            <button class="btn" onclick="saveCustomInstructions()" style="align-self:flex-start;">
                <?= icon('save') ?> <?= __('settings.ci_save') ?>
            </button>
        </div>
    </div>

    <!-- About -->
    <div class="settings-section">
        <h2><?= icon('info') ?> <?= __('settings.about_ailey') ?></h2>
        <p style="font-size:0.85rem; color:var(--muted-foreground); line-height:1.7;">
            <?= __('settings.about_desc') ?>
        </p>
        <p style="font-size:0.75rem; color:var(--muted-foreground); margin-top:0.5rem; opacity:0.6;">
            <?= __('settings.version') ?>
        </p>
        <p style="font-size:0.8rem; color:var(--muted-foreground); margin-top:0.75rem;">
            <a href="/impressum"><?= __('footer.impressum') ?></a> · <a href="/datenschutz"><?= __('footer.datenschutz') ?></a>
        </p>
    </div>

    <!-- Danger Zone -->
    <div class="settings-section danger-zone">
        <h2><?= icon('alert-triangle') ?> <?= __('settings.danger') ?></h2>
        <p style="font-size:0.85rem; color:var(--muted-foreground); margin-bottom:1rem;">
            <?= __('settings.danger_text') ?>
        </p>
        <button class="btn" onclick="Portal.deleteMyData()" style="background:var(--destructive);color:white;">
            <?= icon('trash') ?> <?= __('settings.delete') ?>
        </button>
    </div>

    <div style="text-align:center; margin-top:2rem;">
        <button class="btn btn-ghost" onclick="Portal.logout()"><?= __('settings.logout') ?></button>
    </div>
</div>

<script>
    // Highlight active theme
    const currentTheme = localStorage.getItem('ailey-portal-theme') || 'ailey';
    document.querySelectorAll('.theme-option').forEach(el => {
        el.classList.toggle('active', el.dataset.theme === currentTheme);
        el.addEventListener('click', () => Portal.setTheme(el.dataset.theme));
    });

    // ── Avatar Upload ──
    async function uploadAvatar(input) {
        if (!input.files || !input.files[0]) return;
        const file = input.files[0];
        if (file.size > 5 * 1024 * 1024) { Portal.showToast('Max 5 MB!', 'error'); return; }
        const fd = new FormData();
        fd.append('avatar', file);
        fd.append('action', 'upload_avatar');
        try {
            const resp = await fetch('/api.php', { method: 'POST', body: fd, credentials: 'same-origin' });
            const data = await resp.json();
            if (data.success) {
                document.getElementById('profile-avatar-preview').innerHTML =
                    `<img src="${data.avatar_url}?t=${Date.now()}" alt="Avatar" class="profile-avatar-img">`;
                Portal.showToast('Avatar hochgeladen! 📷', 'success');
                if (data.new_badges && data.new_badges.length) showBadgePopups(data.new_badges);
            } else {
                Portal.showToast(data.error || 'Fehler beim Upload', 'error');
            }
        } catch(e) { Portal.showToast('Upload fehlgeschlagen', 'error'); }
    }

    // ── Save Profile ──
    async function saveProfile() {
        const displayName = document.getElementById('profile-display-name').value.trim();
        const bio = document.getElementById('profile-bio').value.trim();
        try {
            const resp = await fetch('/api.php', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                credentials: 'same-origin',
                body: JSON.stringify({ action: 'update_profile', display_name: displayName, bio: bio })
            });
            const data = await resp.json();
            if (data.success) {
                Portal.showToast('Profil gespeichert! ✨', 'success');
                if (data.new_badges && data.new_badges.length) showBadgePopups(data.new_badges);
            } else {
                Portal.showToast(data.error || 'Fehler', 'error');
            }
        } catch(e) { Portal.showToast('Speichern fehlgeschlagen', 'error'); }
    }

    // ── Badge Grid ──
    async function loadBadges() {
        try {
            const resp = await fetch('/api.php?action=get_profile', { credentials: 'same-origin' });
            const data = await resp.json();
            if (!data.success) return;
            const grid = document.getElementById('badge-grid');
            const allBadges = data.all_badges;
            const unlockedIds = (data.badges || []).map(b => b.badge_id);
            const equippedBadge = data.profile?.equipped_badge;
            let html = '';
            for (const [id, badge] of Object.entries(allBadges)) {
                const unlocked = unlockedIds.includes(id);
                const equipped = equippedBadge === id;
                html += `<div class="badge-card ${unlocked ? 'unlocked' : 'locked'} ${equipped ? 'equipped' : ''}"
                              data-badge-id="${id}" onclick="${unlocked ? `equipBadge('${id}')` : ''}">
                    <div class="badge-icon">${getBadgeSVG(id, unlocked)}</div>
                    <div class="badge-name">${badge.name_de || badge.name}</div>
                    <div class="badge-desc">${badge.desc_de || badge.desc}</div>
                    ${equipped ? '<div class="badge-equipped-tag">✅ Ausgerüstet</div>' : ''}
                    ${unlocked && !equipped ? '<div class="badge-equip-hint">Klicken zum Ausrüsten</div>' : ''}
                </div>`;
            }
            grid.innerHTML = html;
        } catch(e) { console.warn('Badge load error', e); }
    }

    async function equipBadge(badgeId) {
        // Toggle: if already equipped, unequip
        const cards = document.querySelectorAll('.badge-card.equipped');
        const currentId = cards.length ? cards[0].dataset.badgeId : null;
        const newId = (currentId === badgeId) ? null : badgeId;
        try {
            await fetch('/api.php', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                credentials: 'same-origin',
                body: JSON.stringify({ action: 'equip_badge', badge_id: newId })
            });
            Portal.showToast(newId ? 'Badge ausgerüstet! 🏆' : 'Badge abgelegt', 'success');
            loadBadges();
        } catch(e) {}
    }

    // ── Badge SVG icons (inline) ──
    function getBadgeSVG(badgeId, unlocked) {
        const color = unlocked ? 'var(--primary)' : '#555';
        const icons = {
            'first_chat':       '💬', 'chat_10':          '🗣️', 'chat_100':         '💭',
            'chat_1000':        '💍', 'forum_starter':    '📢', 'forum_regular':    '🥜',
            'forum_popular':    '🌟', 'gallery_critic':   '⭐', 'gallery_commenter':'🖼️',
            'first_image':      '🎨', 'first_song':       '🎵', 'image_10':         '🖌️',
            'song_10':          '🎤', 'vdollars_100':     '💰', 'vdollars_1000':    '🐋',
            'rater_5':          '📊', 'rater_50':         '🍺', 'night_owl':        '🦉',
            'profile_complete': '👤', 'week_streak':      '🔥',
        };
        const emoji = icons[badgeId] || '🏅';
        return `<span style="font-size:2rem;${unlocked ? '' : 'filter:grayscale(1);opacity:0.4;'}">${emoji}</span>`;
    }

    // ── Badge popup (achievement unlocked!) ──
    function showBadgePopups(badges) {
        if (!badges || !badges.length) return;
        badges.forEach((badge, i) => {
            setTimeout(() => {
                const popup = document.createElement('div');
                popup.className = 'badge-popup';
                popup.innerHTML = `
                    <div class="badge-popup-inner">
                        <div class="badge-popup-icon">${getBadgeSVG(badge.badge_id, true)}</div>
                        <div class="badge-popup-title">🏆 Achievement Unlocked!</div>
                        <div class="badge-popup-name">${badge.name_de || badge.name}</div>
                        <div class="badge-popup-ailey">${badge.ailey_msg || ''}</div>
                        <button class="btn btn-sm" onclick="this.closest('.badge-popup').remove()">Nice! 😎</button>
                    </div>
                `;
                document.body.appendChild(popup);
                requestAnimationFrame(() => popup.classList.add('visible'));
                setTimeout(() => { popup.classList.remove('visible'); setTimeout(() => popup.remove(), 400); }, 8000);
            }, i * 2000);
        });
    }
    // Make showBadgePopups available globally for other pages
    window.showBadgePopups = showBadgePopups;
    window.getBadgeSVG = getBadgeSVG;

    // Custom Instructions
    (async function loadCustomInstructions() {
        const prefs = await Portal.loadPreferences();
        if (prefs.about_me) document.getElementById('ci-about').value = prefs.about_me;
        if (prefs.response_style) document.getElementById('ci-style').value = prefs.response_style;
        if (prefs.other) document.getElementById('ci-other').value = prefs.other;
    })();

    async function saveCustomInstructions() {
        await Portal.savePreferences({
            about_me: document.getElementById('ci-about').value.trim(),
            response_style: document.getElementById('ci-style').value.trim(),
            other: document.getElementById('ci-other').value.trim()
        });
    }

    // Load badges on page load
    loadBadges();
</script>

<?php portal_footer(); ?>
