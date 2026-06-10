<?php
/**
 * A!ley Portal — FAQ (Public)
 */
require_once __DIR__ . '/layout.php';
portal_head(__('faq.title'), showKiBanner: false, isPublic: true, description: __('faq.description'));
?>

<div class="faq-page">

    <section class="faq-header">
        <h1><?= icon('help-circle') ?> <?= __('faq.header') ?></h1>
        <p class="faq-subtitle"><?= __('faq.subtitle') ?></p>
    </section>

    <div class="faq-list">

        <details class="faq-item" open>
            <summary><?= __('faq.q1') ?></summary>
            <div class="faq-answer"><p><?= __('faq.a1') ?></p></div>
        </details>

        <details class="faq-item">
            <summary><?= __('faq.q2') ?></summary>
            <div class="faq-answer"><p><?= __('faq.a2') ?></p></div>
        </details>

        <details class="faq-item">
            <summary><?= __('faq.q3') ?></summary>
            <div class="faq-answer"><p><?= __('faq.a3') ?></p></div>
        </details>

        <details class="faq-item">
            <summary><?= __('faq.q4') ?></summary>
            <div class="faq-answer"><p><?= __('faq.a4') ?></p></div>
        </details>

        <details class="faq-item">
            <summary><?= __('faq.q5') ?></summary>
            <div class="faq-answer"><p><?= __('faq.a5') ?></p></div>
        </details>

        <details class="faq-item">
            <summary><?= __('faq.q6') ?></summary>
            <div class="faq-answer"><p><?= __('faq.a6') ?></p></div>
        </details>

        <details class="faq-item">
            <summary><?= __('faq.q7') ?></summary>
            <div class="faq-answer"><p><?= __('faq.a7') ?></p></div>
        </details>

        <details class="faq-item">
            <summary><?= __('faq.q8') ?></summary>
            <div class="faq-answer"><p><?= __('faq.a8') ?></p></div>
        </details>

        <details class="faq-item">
            <summary><?= __('faq.q9') ?></summary>
            <div class="faq-answer"><p><?= __('faq.a9') ?></p></div>
        </details>

        <details class="faq-item">
            <summary><?= __('faq.q10') ?></summary>
            <div class="faq-answer"><p><?= __('faq.a10') ?></p></div>
        </details>

    </div>

    <section class="faq-cta">
        <a href="/ueber-ailey" class="btn btn-secondary"><?= __('faq.cta_about') ?></a>
        <a href="/galerie" class="btn btn-primary"><?= icon('palette') ?> <?= __('faq.cta_gallery') ?></a>
    </section>

</div>

<?php portal_footer(); ?>
