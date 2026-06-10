<?php
/**
 * A!ley Portal — 404 Page
 */
require_once __DIR__ . '/layout.php';
portal_head(__('notfound.title'));
?>

<div class="not-found">
    <img src="/assets/ailey-confused.jpg" alt="A!ley confused" style="width:100px;height:100px;border-radius:50%;border:3px solid var(--primary);box-shadow:0 0 20px var(--glow);">
    <h1><?= __('notfound.heading') ?></h1>
    <p><?= __('notfound.text') ?></p>
    <a href="/chat" class="btn btn-primary"><?= __('notfound.back') ?></a>
</div>

<?php portal_footer(); ?>
