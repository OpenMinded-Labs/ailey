<?php
/**
 * A!ley Portal — Forgot Password Page
 */
require_once __DIR__ . '/layout.php';
portal_head(__('forgot.title'));
?>

<div class="auth-page">
    <div class="auth-card">
        <div class="auth-header">
            <img class="auth-logo" src="/assets/ailey-default.jpg" alt="A!ley">
            <h1 class="auth-title"><?= __('forgot.heading') ?></h1>
            <p class="auth-subtitle"><?= __('forgot.subtitle') ?></p>
        </div>

        <form id="forgot-form" onsubmit="Portal.handleForgotPassword(event)">
            <div class="form-group">
                <label class="form-label" for="email"><?= __('forgot.email') ?></label>
                <input class="form-input" type="email" name="email" id="email" required autocomplete="email" placeholder="deine@email.de">
            </div>

            <div class="form-error" id="forgot-error"></div>
            <div class="form-success" id="forgot-success"></div>

            <button type="submit" class="btn btn-primary btn-full" style="margin-top:0.5rem;" id="forgot-btn">
                <?= __('forgot.submit') ?>
            </button>
        </form>

        <div class="auth-link">
            <?= __('forgot.back_to_login') ?> <a href="/login"><?= __('forgot.login_link') ?></a>
        </div>
    </div>
</div>

<?php portal_footer(); ?>
