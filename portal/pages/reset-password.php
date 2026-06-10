<?php
/**
 * A!ley Portal — Reset Password Page (with token from email link)
 */
require_once __DIR__ . '/layout.php';
portal_head(__('reset.title'));

$token = $_GET['token'] ?? '';
?>

<div class="auth-page">
    <div class="auth-card">
        <div class="auth-header">
            <img class="auth-logo" src="/assets/ailey-default.jpg" alt="A!ley">
            <h1 class="auth-title"><?= __('reset.heading') ?></h1>
            <p class="auth-subtitle"><?= __('reset.subtitle') ?></p>
        </div>

<?php if (!$token): ?>
        <div class="form-error visible"><?= __('reset.no_token') ?></div>
        <div class="auth-link" style="margin-top:1rem;">
            <a href="/forgot-password"><?= __('reset.request_new') ?></a>
        </div>
<?php else: ?>
        <form id="reset-form" onsubmit="Portal.handleResetPassword(event)">
            <input type="hidden" name="token" value="<?= htmlspecialchars($token) ?>">

            <div class="form-group">
                <label class="form-label" for="password"><?= __('reset.new_password') ?></label>
                <input class="form-input" type="password" name="password" id="password" required autocomplete="new-password" placeholder="••••••••" minlength="8">
            </div>

            <div class="form-group">
                <label class="form-label" for="password_confirm"><?= __('reset.confirm_password') ?></label>
                <input class="form-input" type="password" name="password_confirm" id="password_confirm" required autocomplete="new-password" placeholder="••••••••" minlength="8">
            </div>

            <div class="form-error" id="reset-error"></div>
            <div class="form-success" id="reset-success"></div>

            <button type="submit" class="btn btn-primary btn-full" style="margin-top:0.5rem;" id="reset-btn">
                <?= __('reset.submit') ?>
            </button>
        </form>
<?php endif; ?>

        <div class="auth-link">
            <a href="/login"><?= __('reset.back_to_login') ?></a>
        </div>
    </div>
</div>

<?php portal_footer(); ?>
