<?php
/**
 * A!ley Portal — Register Page (two-tier: invited + public)
 */
require_once __DIR__ . '/layout.php';
portal_head(__('register.title'));
?>

<div class="auth-page">
    <div class="auth-card" style="max-width:560px;">
        <div class="auth-header">
            <img class="auth-logo" src="/assets/ailey-default.jpg" alt="A!ley">
            <h1 class="auth-title"><?= __('register.welcome') ?> <span class="highlight">A!ley's</span> <?= __('register.welcome_suffix') ?></h1>
            <p class="auth-subtitle"><?= __('register.subtitle') ?></p>
        </div>

        <!-- Tier Chooser -->
        <div class="register-tier-tabs" id="tier-tabs">
            <button class="tier-tab active" data-tier="invited" onclick="Portal.switchRegisterTier('invited')">
                ⭐ <?= __('register.tab_invited') ?>
            </button>
            <button class="tier-tab" data-tier="public" onclick="Portal.switchRegisterTier('public')">
                🌐 <?= __('register.tab_public') ?>
            </button>
        </div>

        <!-- Invited Tier Info -->
        <div class="tier-info" id="tier-info-invited" style="margin-bottom:1rem;">
            <div class="tier-badge tier-invited">⭐ Invited</div>
            <ul class="tier-features">
                <li>💬 Chat mit Ailey (alle Modi)</li>
                <li>🎨 Bilder & Songs generieren</li>
                <li>📖 Forum, Galerie, Blog, Bücher</li>
                <li>💰 100 V$ Start + 100 V$/Woche</li>
            </ul>
            <p class="tier-note"><?= __('register.invited_note') ?></p>
        </div>
        <!-- Public Tier Info -->
        <div class="tier-info" id="tier-info-public" style="margin-bottom:1rem; display:none;">
            <div class="tier-badge tier-public">🌐 Public</div>
            <ul class="tier-features">
                <li>📖 Forum, Galerie, Blog, Bücher</li>
                <li>⭐ Bewerten & Kommentieren</li>
                <li>💰 20 V$ Start + 20 V$/Woche</li>
                <li>❌ Kein Chat, keine Bild-/Songgeneration</li>
            </ul>
            <p class="tier-note"><?= __('register.public_note') ?></p>
        </div>

        <form onsubmit="Portal.handleRegister(event)">
            <input type="hidden" name="register_tier" id="register_tier" value="invited">

            <div class="form-group">
                <label class="form-label" for="email"><?= __('register.email') ?></label>
                <input class="form-input" type="email" name="email" id="email" required autocomplete="email" placeholder="deine@email.de">
            </div>

            <div class="form-group">
                <label class="form-label" for="display_name"><?= __('register.display_name') ?></label>
                <input class="form-input" type="text" name="display_name" id="display_name" required minlength="2" maxlength="50" autocomplete="name" placeholder="<?= __('register.display_placeholder') ?>">
            </div>

            <div class="form-group">
                <label class="form-label" for="password"><?= __('register.password') ?></label>
                <input class="form-input" type="password" name="password" id="password" required minlength="8" autocomplete="new-password" placeholder="••••••••">
            </div>

            <div class="form-checkbox">
                <input type="checkbox" name="dsgvo" id="dsgvo" required>
                <label for="dsgvo"><?= __('register.dsgvo') ?></label>
            </div>

            <div class="form-checkbox">
                <input type="checkbox" name="ki_disclosure" id="ki_disclosure" required>
                <label for="ki_disclosure"><?= __('register.ki_disclosure') ?></label>
            </div>

            <div class="form-checkbox">
                <input type="checkbox" name="agb" id="agb" required>
                <label for="agb"><?= __('register.agb_consent') ?></label>
            </div>

            <div class="form-error" id="register-error"></div>

            <button type="submit" class="btn btn-primary btn-full" style="margin-top:0.5rem;">
                <?= __('register.submit') ?>
            </button>
        </form>

        <div class="auth-link">
            <?= __('register.has_account') ?> <a href="/login"><?= __('register.login_link') ?></a>
        </div>
    </div>
</div>

<?php portal_footer(); ?>
