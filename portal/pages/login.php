<?php
/**
 * A!ley Portal — Login Page
 */
require_once __DIR__ . '/layout.php';
portal_head(__('login.title'));
?>

<div class="auth-page">
    <div class="auth-card">
        <div class="auth-header">
            <img class="auth-logo" src="/assets/ailey-default.jpg" alt="A!ley">
            <h1 class="auth-title"><?= __('login.welcome') ?> <span class="highlight">A!ley</span></h1>
            <p class="auth-subtitle"><?= __('login.subtitle') ?></p>
        </div>

        <form onsubmit="Portal.handleLogin(event)">
            <div class="form-group">
                <label class="form-label" for="email"><?= __('login.email') ?></label>
                <input class="form-input" type="email" name="email" id="email" required autocomplete="email" placeholder="deine@email.de">
            </div>

            <div class="form-group">
                <label class="form-label" for="password"><?= __('login.password') ?></label>
                <input class="form-input" type="password" name="password" id="password" required autocomplete="current-password" placeholder="••••••••">
            </div>

            <div class="form-error" id="login-error"></div>

            <button type="submit" class="btn btn-primary btn-full" style="margin-top:0.5rem;">
                <?= __('login.submit') ?>
            </button>
        </form>

        <div class="auth-link" style="margin-top:0.75rem;">
            <a href="/forgot-password"><?= __('login.forgot_password') ?></a>
        </div>

        <div class="auth-link">
            <?= __('login.no_account') ?> <a href="/register"><?= __('login.register_link') ?></a>
        </div>
    </div>
</div>

<?php portal_footer(); ?>
