<?php
/**
 * A!ley Portal — Forum Page
 * Categories: general, feedback, kreativ, technik, offtopic
 */
require_once __DIR__ . '/layout.php';
portal_head(__('forum.title'));
$forumCategories = [
    'general'  => ['icon' => '💬', 'label' => __('forum.cat_general')],
    'feedback' => ['icon' => '📣', 'label' => __('forum.cat_feedback')],
    'kreativ'  => ['icon' => '🎨', 'label' => __('forum.cat_kreativ')],
    'technik'  => ['icon' => '⚙️', 'label' => __('forum.cat_technik')],
    'offtopic' => ['icon' => '🌀', 'label' => __('forum.cat_offtopic')],
];
?>

<div class="page-container forum-page">
    <div class="page-header">
        <h1>💬 <?= __('forum.title') ?></h1>
        <p class="page-subtitle"><?= __('forum.subtitle') ?></p>
    </div>

    <!-- Category Tabs -->
    <div class="forum-categories" id="forum-categories">
        <button class="forum-cat-tab active" data-cat="" onclick="Portal.forumSwitchCategory('')">
            📋 <?= __('forum.cat_all') ?>
        </button>
        <?php foreach ($forumCategories as $key => $cat): ?>
        <button class="forum-cat-tab" data-cat="<?= $key ?>" onclick="Portal.forumSwitchCategory('<?= $key ?>')">
            <?= $cat['icon'] ?> <?= $cat['label'] ?>
        </button>
        <?php endforeach; ?>
    </div>

    <!-- New Topic Button (logged-in only) -->
    <?php if ($user): ?>
    <div class="forum-actions">
        <button class="btn btn-primary" onclick="Portal.forumShowNewTopic()">
            ✏️ <?= __('forum.new_topic') ?>
        </button>
    </div>

    <!-- New Topic Form (hidden by default) -->
    <div class="forum-new-topic" id="forum-new-topic" style="display:none;">
        <div class="card" style="padding:1.5rem; margin-bottom:1.5rem;">
            <h3><?= __('forum.new_topic') ?></h3>
            <div class="form-group">
                <label class="form-label"><?= __('forum.category') ?></label>
                <select class="form-input" id="new-topic-category">
                    <?php foreach ($forumCategories as $key => $cat): ?>
                    <option value="<?= $key ?>"><?= $cat['icon'] ?> <?= $cat['label'] ?></option>
                    <?php endforeach; ?>
                </select>
            </div>
            <div class="form-group">
                <label class="form-label"><?= __('forum.topic_title') ?></label>
                <input class="form-input" type="text" id="new-topic-title" maxlength="200" placeholder="<?= __('forum.topic_title_placeholder') ?>">
            </div>
            <div class="form-group">
                <label class="form-label"><?= __('forum.topic_body') ?></label>
                <textarea class="form-input" id="new-topic-body" rows="5" maxlength="5000" placeholder="<?= __('forum.topic_body_placeholder') ?>"></textarea>
            </div>
            <div class="form-error" id="forum-topic-error"></div>
            <div style="display:flex; gap:0.5rem;">
                <button class="btn btn-primary" onclick="Portal.forumCreateTopic()">
                    📤 <?= __('forum.submit_topic') ?>
                </button>
                <button class="btn btn-secondary" onclick="Portal.forumHideNewTopic()">
                    <?= __('common.cancel') ?>
                </button>
            </div>
        </div>
    </div>
    <?php else: ?>
    <div class="forum-login-hint" style="text-align:center; padding:1rem; opacity:0.7;">
        <a href="/register"><?= __('forum.login_to_post') ?></a>
    </div>
    <?php endif; ?>

    <!-- Topics List -->
    <div class="forum-topics" id="forum-topics">
        <div class="loading-spinner" style="text-align:center; padding:2rem;">⏳ Laden...</div>
    </div>

    <!-- Pagination -->
    <div class="forum-pagination" id="forum-pagination" style="text-align:center; padding:1rem;"></div>
</div>

<!-- Topic Detail View (hidden by default) -->
<div class="page-container forum-detail-page" id="forum-detail" style="display:none;">
    <button class="btn btn-secondary" onclick="Portal.forumBackToList()" style="margin-bottom:1rem;">
        ← <?= __('forum.back_to_list') ?>
    </button>
    <div id="forum-detail-content"></div>

    <!-- Reply Form -->
    <?php if ($user): ?>
    <div class="forum-reply-form" style="margin-top:1.5rem;">
        <h3>💬 <?= __('forum.reply') ?></h3>
        <textarea class="form-input" id="forum-reply-body" rows="4" maxlength="5000" placeholder="<?= __('forum.reply_placeholder') ?>"></textarea>
        <div class="form-error" id="forum-reply-error"></div>
        <button class="btn btn-primary" onclick="Portal.forumCreateReply()" style="margin-top:0.5rem;">
            📤 <?= __('forum.submit_reply') ?>
        </button>
    </div>
    <?php endif; ?>
</div>

<?php portal_footer(); ?>
