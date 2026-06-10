<?php
/**
 * A!ley Portal — Chat Page (main interface)
 */
require_once __DIR__ . '/layout.php';
portal_head(__('chat.tab_chat'));
$userName = htmlspecialchars($user['display_name'] ?? 'User');
$userEmail = htmlspecialchars($user['email'] ?? '');
$userInitial = mb_strtoupper(mb_substr($user['display_name'] ?? 'U', 0, 1));
$userRole = $user['role'] ?? 'user';
global $config;
$chatLimits = PortalDB::getEffectiveLimits($config['limits'] ?? []);
$maxMsgLen = $chatLimits['max_message_length'];

// Get initial status server-side so we don't flash "Online" when she's offline
$initialStatus = PortalDB::getAileyStatus();
$statusLabels = [
    'online' => __('status.online'),
    'thinking' => __('status.thinking'),
    'offline' => __('status.offline'),
    'sleeping' => __('status.sleeping'),
];
$statusLabel = $statusLabels[$initialStatus] ?? $initialStatus;
$statusDotClass = in_array($initialStatus, ['offline', 'sleeping']) ? 'status-dot offline' : 'status-dot';
?>

<div id="sidebar-overlay" class="sidebar-overlay"></div>

<div class="portal-layout">
    <!-- Sidebar -->
    <aside id="sidebar" class="sidebar">
        <div class="sidebar-header">
            <img class="sidebar-logo ailey-avatar" src="/assets/ailey-default.jpg" alt="A!ley">
            <div>
                <div class="sidebar-title"><?= __('chat.sidebar_title') ?></div>
                <div class="sidebar-subtitle"><?= __('chat.sidebar_subtitle') ?></div>
            </div>
        </div>

        <div class="sidebar-actions">
            <button class="btn btn-primary btn-sm btn-full" onclick="Portal.newConversation()">
            <?= icon('sparkles') ?> <?= __('chat.new_conversation') ?>
            </button>
        </div>

        <div class="conv-list" id="conv-list">
            <div class="conv-empty"><?= __('chat.loading_convs') ?></div>
        </div>

        <div class="sidebar-footer">
            <div class="sidebar-user">
                <div class="sidebar-user-name"><?= $userName ?></div>
                <div class="sidebar-user-email"><?= $userEmail ?></div>
                <div id="vdollars-badge" class="vdollars-badge" title="<?= __('vdollars.balance_title') ?>" style="display:none;">💰 <span id="vdollars-amount">0</span> V$</div>
            </div>
            <a href="/settings" class="btn btn-ghost btn-icon" title="<?= __('settings.title') ?>"><?= icon('settings') ?></a>
            <?php if ($userRole === 'admin'): ?>
                <a href="/admin" class="btn btn-ghost btn-icon" title="Admin"><?= icon('shield') ?></a>
            <?php endif; ?>
        </div>
    </aside>

    <!-- Main Chat Area -->
    <main class="chat-main">
        <!-- Ban Overlay (shown when user is banned) -->
        <div id="ban-overlay" class="ban-overlay" style="display:none;">
            <div class="ban-card">
                <div class="ban-icon">🚫</div>
                <h2 id="ban-title">Du bist gesperrt</h2>
                <p id="ban-message">Du hast gegen die Gesprächsregeln verstoßen.</p>
                <div id="ban-timer" class="ban-timer"></div>
                <p id="ban-contact" class="ban-contact" style="display:none;">
                    Möchtest du dich entschuldigen? Schreib an<br>
                    <a href="mailto:kontakt@sexngears.de">kontakt@sexngears.de</a>
                </p>
            </div>
        </div>
        <div class="chat-header">
            <button id="menu-toggle" class="menu-toggle" aria-label="<?= __('chat.menu') ?>">☰</button>
            <img class="chat-header-avatar ailey-avatar" src="/assets/ailey-default.jpg" alt="A!ley">
            <div class="chat-header-info">
                <div class="chat-header-title">A!ley</div>
                <div class="chat-header-status">
                    <span id="status-dot" class="<?= $statusDotClass ?>"></span>
                    <span id="status-text"><?= htmlspecialchars($statusLabel) ?></span>
                </div>
            </div>
            <!-- Topbar Tabs: Chat / Code / SVG / Songs / Images + Tool Tabs -->
            <div class="header-tabs">
                <button class="header-tab active" data-tab="chat" onclick="Portal.switchTab('chat')"><?= icon('message-circle') ?> <span class="tab-label"><?= __('chat.tab_chat') ?></span></button>
                <button class="header-tab" data-tab="code" onclick="Portal.switchTab('code')"><?= icon('code') ?> <span class="tab-label"><?= __('chat.tab_code') ?></span> <span class="tab-count" id="tab-count-code"></span></button>
                <button class="header-tab" data-tab="svg" onclick="Portal.switchTab('svg')"><?= icon('pen-tool') ?> <span class="tab-label"><?= __('chat.tab_svg') ?></span> <span class="tab-count" id="tab-count-svg"></span></button>
                <button class="header-tab" data-tab="song" onclick="Portal.switchTab('song')"><?= icon('music') ?> <span class="tab-label"><?= __('chat.tab_song') ?></span> <span class="tab-count" id="tab-count-song"></span></button>
                <button class="header-tab" data-tab="image" onclick="Portal.switchTab('image')"><?= icon('image') ?> <span class="tab-label"><?= __('chat.tab_image') ?></span> <span class="tab-count" id="tab-count-image"></span></button>
                <a href="/bildgen" class="header-tab tool-tab-link" title="Bild generieren"><?= icon('wand-2') ?> <span class="tab-label">Bild-Gen</span></a>
                <a href="/songgen" class="header-tab tool-tab-link" title="Song generieren"><?= icon('disc-3') ?> <span class="tab-label">Song-Gen</span></a>
            </div>
            <!-- V$ Balance (always visible in chat header) -->
            <div id="vdollars-header-badge" class="vdollars-header-badge" title="<?= __('vdollars.balance_title') ?>">💰 <span id="vdollars-header-amount">…</span> V$</div>
        </div>

        <div class="chat-messages" id="chat-messages">
            <!-- Filled by JS -->
        </div>

        <!-- Artifact Panels (Code / SVG) -->
        <div class="artifact-panel" id="artifact-panel-code" style="display:none;">
            <div class="artifact-empty" id="artifact-empty-code">
                <div class="artifact-empty-icon"><?= icon('code') ?></div>
                <div class="artifact-empty-text"><?= __('chat.no_code') ?></div>
            </div>
            <div id="artifact-list-code"></div>
        </div>
        <div class="artifact-panel" id="artifact-panel-svg" style="display:none;">
            <div class="artifact-empty" id="artifact-empty-svg">
                <div class="artifact-empty-icon"><?= icon('pen-tool') ?></div>
                <div class="artifact-empty-text"><?= __('chat.no_svg') ?></div>
            </div>
            <div id="artifact-list-svg"></div>
        </div>
        <div class="artifact-panel" id="artifact-panel-song" style="display:none;">
            <div class="artifact-empty" id="artifact-empty-song">
                <div class="artifact-empty-icon"><?= icon('music') ?></div>
                <div class="artifact-empty-text"><?= __('chat.no_song') ?></div>
            </div>
            <div id="artifact-list-song"></div>
        </div>
        <div class="artifact-panel" id="artifact-panel-image" style="display:none;">
            <div class="artifact-empty" id="artifact-empty-image">
                <div class="artifact-empty-icon"><?= icon('image') ?></div>
                <div class="artifact-empty-text"><?= __('chat.no_image') ?></div>
            </div>
            <div id="artifact-list-image"></div>
        </div>

        <!-- ═══ Tool Panels moved to /bildgen and /songgen ═══ -->

        <!-- Sleeping overlay (shown when Simon disables portal support) -->
        <div id="sleeping-overlay" class="sleeping-overlay" style="display:none;">
            <div class="sleeping-content">
                <div class="sleeping-emoji"><?= icon('moon') ?></div>
                <h3><?= __('chat.sleeping_title') ?></h3>
                <p><?= __('chat.sleeping_text') ?></p>
            </div>
        </div>

        <div class="chat-input-area">
            <div class="chat-mode-selector" id="chat-mode-selector">
                <!-- Custom dropdown (smartphone-friendly: tap to open, tap item to select, inline descriptions) -->
                <div class="chat-mode-custom" id="chat-mode-custom" data-open="false">
                    <button type="button" class="chat-mode-trigger" id="chat-mode-trigger"
                            onclick="Portal.toggleChatModeDropdown(event)"
                            aria-haspopup="listbox" aria-expanded="false">
                        <span class="chat-mode-trigger-label" id="chat-mode-trigger-label">
                            <!-- populated by JS: icon + name + cost -->
                        </span>
                        <span class="chat-mode-trigger-chev"><?= icon('chevron-down') ?></span>
                    </button>
                    <ul class="chat-mode-panel" id="chat-mode-panel" role="listbox" aria-label="A!ley Modus">
                        <li class="chat-mode-item" role="option" data-mode="hamster" onclick="Portal.pickChatMode('hamster')">
                            <div class="chat-mode-item-head"><span class="chat-mode-item-icon" aria-hidden="true">🐹</span><span class="chat-mode-item-name">Hamster</span><span class="chat-mode-item-cost">0.2 V$</span></div>
                            <div class="chat-mode-item-desc">Mr. Fluffbytes antwortet — liebenswert, leicht chaotisch, mit Hamster-Logik. Nur zum Spaß.</div>
                        </li>
                        <li class="chat-mode-item" role="option" data-mode="nitro" onclick="Portal.pickChatMode('nitro')">
                            <div class="chat-mode-item-head"><span class="chat-mode-item-icon"><?= icon('zap') ?></span><span class="chat-mode-item-name">A!ley Nitro</span><span class="chat-mode-item-cost">0.5 V$</span></div>
                            <div class="chat-mode-item-desc">Kompaktes Ailey-Modell. Schnell, direkt, leichtfüßig — für alltägliche Fragen.</div>
                        </li>
                        <li class="chat-mode-item" role="option" data-mode="normal" onclick="Portal.pickChatMode('normal')">
                            <div class="chat-mode-item-head"><span class="chat-mode-item-icon"><?= icon('message-circle') ?></span><span class="chat-mode-item-name">A!ley</span><span class="chat-mode-item-cost">1 V$</span></div>
                            <div class="chat-mode-item-desc">Standard-Ailey. Volle Persönlichkeit, ohne sichtbares Reasoning — ideal für normale Gespräche.</div>
                        </li>
                        <li class="chat-mode-item" role="option" data-mode="thinking" onclick="Portal.pickChatMode('thinking')">
                            <div class="chat-mode-item-head"><span class="chat-mode-item-icon"><?= icon('brain') ?></span><span class="chat-mode-item-name">A!ley Tempest<span class="glossary-hint" data-glossary="Tempest = kontrollierter Sturm. Ailey denkt sichtbar nach (Reasoning) — emotional, vielschichtig, für tiefere Gespräche.">?</span></span><span class="chat-mode-item-cost">2 V$</span></div>
                            <div class="chat-mode-item-desc">Ailey mit sichtbarem Reasoning — kontrollierter Sturm: emotional, vielschichtig, für tiefere Gespräche und Kunst.</div>
                        </li>
                        <li class="chat-mode-item" role="option" data-mode="focus" onclick="Portal.pickChatMode('focus')">
                            <div class="chat-mode-item-head"><span class="chat-mode-item-icon"><?= icon('minimize') ?></span><span class="chat-mode-item-name">A!ley SXE<span class="glossary-hint" data-glossary="SXE = Straight Edge — clean, fokussiert, keine Ablenkung. Für Emails, Fakten, Texte ohne Drama.">?</span></span><span class="chat-mode-item-cost">2 V$</span></div>
                            <div class="chat-mode-item-desc">Straight-Edge-Modus: klar, nüchtern, fokussiert. Für Emails, Texte, Fakten — ohne Drama.</div>
                        </li>
                    </ul>
                </div>
                <!-- Hidden legacy select for compatibility (old listeners might still read it) -->
                <select id="chat-mode-dropdown" class="chat-mode-dropdown-legacy" onchange="Portal.setChatMode(this.value)" tabindex="-1" aria-hidden="true" style="display:none;">
                    <option value="hamster">Hamster</option>
                    <option value="nitro">A!ley Nitro</option>
                    <option value="normal">A!ley</option>
                    <option value="thinking" selected>A!ley Tempest</option>
                    <option value="focus">A!ley SXE</option>
                </select>
            </div>
            <!-- File preview bar (shown when file is pending) -->
            <div id="file-preview-bar" class="file-preview-bar" style="display:none;">
                <span id="file-preview-icon"><?= icon('file-text') ?></span>
                <span id="file-preview-name" class="file-preview-name">Datei</span>
                <button class="file-preview-close" onclick="Portal.clearPendingFile()" title="Entfernen">&times;</button>
            </div>
            <div class="chat-input-row">
                <button id="web-search-toggle" class="input-toggle-btn" onclick="Portal.toggleWebSearch()" title="<?= __('chat.web_search') ?>" type="button"><?= icon('search') ?></button>
                <!-- File attach button -->
                <input type="file" id="chat-file-input" class="hidden-file-input" onchange="Portal.handleChatFileSelect(event)"
                    accept="image/png,image/jpeg,image/webp,image/gif,.pdf,.docx,.txt,.md,.json,.xml,.csv,.yaml,.yml,.py,.js,.ts,.html,.css,.java,.c,.cpp,.rs,.go,.rb,.php,.sh,.sql,.swift,.tex,.log"/>
                <button class="input-toggle-btn" onclick="document.getElementById('chat-file-input').click()" title="Datei anhängen (Bilder, PDFs, Dokumente, Code…)" type="button">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:16px;height:16px;">
                        <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"/>
                    </svg>
                </button>
                <textarea 
                    id="chat-input" 
                    class="chat-input" 
                    placeholder="<?= __('chat.placeholder') ?>" 
                    rows="1"
                    maxlength="<?= $maxMsgLen ?>"
                ></textarea>
                <button id="send-btn" class="send-btn" onclick="Portal.sendMessage()" title="<?= __('chat.send') ?>">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <line x1="22" y1="2" x2="11" y2="13"></line>
                        <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
                    </svg>
                </button>
            </div>
            <div class="chat-input-hint">
                <?= __('chat.ki_hint') ?> 
                <a href="/datenschutz" style="color:var(--muted-foreground);text-decoration:underline;"><?= __('footer.datenschutz') ?></a>
            </div>
        </div>
    </main>
</div>

<!-- Avatar Lightbox (click any A!ley avatar to see full mood portrait) -->
<div id="avatar-lightbox" class="avatar-lightbox" onclick="Portal.closeAvatarLightbox(event)">
    <div class="avatar-lightbox-inner">
        <button class="avatar-lightbox-close" onclick="Portal.closeAvatarLightbox()" title="<?= __('chat.close') ?>">✕</button>
        <img id="avatar-lightbox-img" src="/assets/ailey-default.jpg" alt="A!ley">
    </div>
    <div id="avatar-lightbox-mood" class="avatar-lightbox-mood"></div>
</div>

<!-- Generation Lightbox (full-view for user-generated images) -->
<div id="gen-lightbox" class="gen-lightbox" onclick="PortalTools.closeLightbox(event)">
    <div class="gen-lightbox-content">
        <button class="gen-lightbox-close" onclick="PortalTools.closeLightbox()" title="Schließen">✕</button>
        <img id="gen-lightbox-img" src="" alt="Generated Image">
    </div>
    <div class="gen-lightbox-info">
        <div id="gen-lightbox-title" class="lb-title"></div>
        <div id="gen-lightbox-prompt" class="lb-prompt"></div>
    </div>
    <div class="gen-lightbox-actions">
        <a id="gen-lightbox-dl" href="" download title="Herunterladen">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
            Download
        </a>
        <button onclick="PortalTools.openInNewTab()" title="In neuem Tab öffnen">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>
            Neuer Tab
        </button>
    </div>
</div>

<script>
    // i18n strings for JS
    window._i18n = <?= json_encode([
        'delete_artifact_confirm' => __('chat.delete_artifact'),
        'artifact_deleted' => __('chat.artifact_deleted'),
    ]) ?>;

    // ═══════════════════════════════════════════════════════════════
    // PortalTools — Lightbox + tool-tab links visibility
    // ═══════════════════════════════════════════════════════════════
    const PortalTools = {
        _toolsLoaded: false,
        _tools: { image_gen: false, song_gen: false },

        /** Load tool access from server and show link-tabs accordingly */
        async init() {
            try {
                const res = await fetch('/api.php?action=my_tools');
                const data = await res.json();
                if (!data.success) return;
                this._tools = data.tools || {};
                // Link-tabs are always visible (they navigate to /bildgen, /songgen)
                this._toolsLoaded = true;
            } catch (e) {
                console.warn('[PortalTools] init failed:', e);
            }
        },

        // ── Lightbox for generated images (still used for chat artifacts) ──
        _currentLightboxUrl: '',

        openLightbox(url, title, prompt) {
            this._currentLightboxUrl = url;
            document.getElementById('gen-lightbox-img').src = url;
            document.getElementById('gen-lightbox-title').textContent = title || '';
            document.getElementById('gen-lightbox-prompt').textContent = prompt || '';
            document.getElementById('gen-lightbox-dl').href = url;
            document.getElementById('gen-lightbox-dl').download = (title || 'generated-image') + '.png';
            document.getElementById('gen-lightbox').classList.add('visible');
            document.body.style.overflow = 'hidden';
        },

        closeLightbox(e) {
            if (e && e.target !== e.currentTarget) return;
            document.getElementById('gen-lightbox').classList.remove('visible');
            document.body.style.overflow = '';
        },

        openInNewTab() {
            if (this._currentLightboxUrl) window.open(this._currentLightboxUrl, '_blank');
        },

        _esc(s) {
            const el = document.createElement('span');
            el.textContent = s || '';
            return el.innerHTML;
        },
    };

    // Init with current user data
    Portal.init(<?= json_encode([
        'id' => $user['id'],
        'display_name' => $user['display_name'],
        'email' => $user['email'],
        'role' => $user['role'],
    ]) ?>);

    // Init tool tabs (async — shows tabs only if user has access)
    PortalTools.init();
</script>

<?php portal_footer(); ?>
