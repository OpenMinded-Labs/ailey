<?php
/**
 * A!ley Portal — Book Reader (Public)
 *
 * Two modes:
 *   /buch/BOOK_SOURCE_ID              → overview (synopsis, chapters list, progress)
 *   /buch/BOOK_SOURCE_ID/kapitel/NUM  → read a single chapter
 *
 * Books are synced from A!ley's local files via portal_poller.
 * Book metadata is in ailey_gallery_items, chapter content in ailey_book_chapters.
 */
require_once __DIR__ . '/layout.php';

$bookSlug = $_GET['book_slug'] ?? null;
$chapterNum = isset($_GET['chapter']) ? (int)$_GET['chapter'] : 0;

if (!$bookSlug) {
    http_response_code(404);
    portal_head(__('book.not_found'));
    echo '<div class="book-page"><div class="book-not-found">';
    echo '<h1>' . __('book.not_found') . '</h1>';
    echo '<a href="/galerie?type=book" class="btn btn-secondary">' . __('book.back_gallery') . '</a>';
    echo '</div></div>';
    portal_footer();
    return;
}

// Find the book gallery item by source_id
$bookSourceId = "book_" . $bookSlug;
// Query gallery item with matching source_id
$stmt = PortalDB::get()->prepare(
    'SELECT * FROM ailey_gallery_items WHERE source_id = ? AND item_type = "book" AND published = 1 LIMIT 1'
);
$stmt->execute([$bookSourceId]);
$book = $stmt->fetch();

if (!$book) {
    http_response_code(404);
    portal_head(__('book.not_found'));
    echo '<div class="book-page"><div class="book-not-found">';
    echo '<h1>' . __('book.not_exists') . '</h1>';
    echo '<a href="/galerie?type=book" class="btn btn-secondary">' . __('book.back_gallery') . '</a>';
    echo '</div></div>';
    portal_footer();
    return;
}

$meta = $book['metadata_json'] ? json_decode($book['metadata_json'], true) : [];
$chapters = PortalDB::getBookChapters($bookSourceId);

// ── Single Chapter View ──────────────────────────────────────
if ($chapterNum > 0) {
    $chapter = PortalDB::getBookChapter($bookSourceId, $chapterNum);
    if (!$chapter) {
        http_response_code(404);
        portal_head(__('book.chapter_not_found'));
        echo '<div class="book-page"><div class="book-not-found">';
        echo '<h1>' . __('book.chapter') . ' ' . $chapterNum . ' — ' . __('book.chapter_not_found') . '</h1>';
        echo '<a href="/buch/' . htmlspecialchars($bookSlug) . '" class="btn btn-secondary">' . __('book.back_to_book') . '</a>';
        echo '</div></div>';
        portal_footer();
        return;
    }

    $chTitle = $chapter['chapter_title'] ?: __('book.chapter') . " $chapterNum";
    portal_head(e($chTitle) . ' — ' . e($book['title']),
                showKiBanner: false, isPublic: true,
                description: __('book.chapter') . ' ' . $chapterNum . ' — ' . e($book['title']) . ' — ' . __('book.description'));
    ?>
    <article class="book-page book-chapter-view">
        <div class="book-chapter-header">
            <a href="/buch/<?= e($bookSlug) ?>" class="book-back-link">← <?= e($book['title']) ?></a>
            <div class="book-chapter-meta">
                <span class="book-chapter-num"><?= __('book.chapter') ?> <?= $chapterNum ?></span>
                <?php if ($chapter['is_revised']): ?>
                    <span class="book-revised-badge"><?= icon('check') ?> <?= __('book.revised') ?></span>
                <?php endif; ?>
                <span class="book-word-count"><?= number_format($chapter['word_count']) ?> <?= __('book.words') ?></span>
            </div>
            <h1 class="book-chapter-title"><?= e($chTitle) ?></h1>
        </div>

        <div class="ki-notice-inline">
            <span class="ki-badge-inline"><?= icon('bot') ?> <?= __('ki_banner.badge') ?></span>
            <?= __('book.ki_notice') ?>
        </div>

        <div class="book-chapter-body">
            <?= PortalDB::renderMarkdown($chapter['content_md']) ?>
        </div>

        <nav class="book-chapter-nav">
            <?php if ($chapterNum > 1): ?>
                <a href="/buch/<?= htmlspecialchars($bookSlug) ?>/kapitel/<?= $chapterNum - 1 ?>" class="btn btn-secondary"><?= __('book.prev_chapter') ?></a>
            <?php else: ?>
                <span></span>
            <?php endif; ?>
            <a href="/buch/<?= htmlspecialchars($bookSlug) ?>" class="btn btn-ghost"><?= icon('book-open') ?> <?= __('book.overview') ?></a>
            <?php
            $nextExists = false;
            foreach ($chapters as $ch) {
                if ((int)$ch['chapter_num'] === $chapterNum + 1) { $nextExists = true; break; }
            }
            ?>
            <?php if ($nextExists): ?>
                <a href="/buch/<?= htmlspecialchars($bookSlug) ?>/kapitel/<?= $chapterNum + 1 ?>" class="btn btn-secondary"><?= __('book.next_chapter') ?></a>
            <?php else: ?>
                <span class="book-end-note"><?= icon('book-open') ?> <?= __('book.end_of_text') ?></span>
            <?php endif; ?>
        </nav>

        <?php
        $shareUrl = ($config['site']['url'] ?? 'https://hey-ailey.com') . '/buch/' . htmlspecialchars($bookSlug) . '/kapitel/' . $chapterNum;
        portal_share_buttons($shareUrl, $chTitle . ' — ' . $book['title'], __('book.share_desc'));
        ?>
    </article>
    <?php
    portal_footer();
    return;
}

// ── Book Overview ────────────────────────────────────────────
portal_head(e($book['title']), showKiBanner: false, isPublic: true,
            description: e(mb_substr($book['description'] ?? '', 0, 160)));
?>
<div class="book-page">
    <section class="book-overview">
        <a href="/galerie?type=book" class="book-back-link"><?= __('book.all_books') ?></a>

        <div class="book-hero">
            <div class="book-cover-placeholder"><?= icon('book-open') ?></div>
            <div class="book-hero-info">
                <h1><?= e($book['title']) ?></h1>
                <?php if (!empty($meta['genre'])): ?>
                    <span class="book-genre"><?= e($meta['genre']) ?></span>
                <?php endif; ?>
                <div class="book-stats">
                    <?php if (!empty($meta['words'])): ?>
                        <span><?= number_format($meta['words']) ?> <?= __('book.words') ?></span>
                    <?php endif; ?>
                    <span><?= (int)($meta['chapters_done'] ?? 0) ?> / <?= (int)($meta['chapters_total'] ?? 0) ?> <?= __('book.chapters') ?></span>
                    <?php if (!empty($meta['status'])): ?>
                        <span class="book-status-badge status-<?= htmlspecialchars($meta['status']) ?>">
                            <?= $meta['status'] === 'writing' ? icon('pencil') . ' ' . __('book.status_writing') : ($meta['status'] === 'finished' ? icon('check') . ' ' . __('book.status_finished') : icon('clipboard') . ' ' . __('book.status_planned')) ?>
                        </span>
                    <?php endif; ?>
                </div>
                <?php if (!empty($meta['progress_pct'])): ?>
                    <div class="book-progress">
                        <div class="book-progress-bar" style="width: <?= (int)$meta['progress_pct'] ?>%"></div>
                        <span class="book-progress-text"><?= (int)$meta['progress_pct'] ?>% <?= __('book.done') ?></span>
                    </div>
                <?php endif; ?>
            </div>
        </div>

        <?php if (!empty($book['description'])): ?>
            <div class="book-synopsis">
                <h2><?= __('book.synopsis') ?></h2>
                <p><?= nl2br(htmlspecialchars($book['description'])) ?></p>
            </div>
        <?php endif; ?>

        <div class="ki-notice-inline">
            <span class="ki-badge-inline"><?= icon('bot') ?> <?= __('ki_banner.badge') ?></span>
            <?= __('book.ki_notice_overview') ?>
        </div>

        <?php if (!empty($chapters)): ?>
            <div class="book-chapters-list">
                <h2><?= __('book.chapters') ?></h2>
                <div class="book-chapters">
                    <?php foreach ($chapters as $ch): ?>
                        <a href="/buch/<?= e($bookSlug) ?>/kapitel/<?= (int)$ch['chapter_num'] ?>" class="book-chapter-card">
                            <span class="book-ch-num"><?= (int)$ch['chapter_num'] ?></span>
                            <div class="book-ch-info">
                                <span class="book-ch-title"><?= e($ch['chapter_title'] ?: __('book.chapter') . ' ' . $ch['chapter_num']) ?></span>
                                <span class="book-ch-meta">
                                    <?= number_format($ch['word_count']) ?> <?= __('book.words') ?>
                                    <?php if ($ch['is_revised']): ?> · <?= icon('check') ?> <?= __('book.revised') ?><?php endif; ?>
                                    <?php if ($ch['updated_at']): ?> · <?= __('book.updated') ?> <?= date('d.m.Y', strtotime($ch['updated_at'])) ?><?php endif; ?>
                                </span>
                            </div>
                            <span class="book-ch-arrow">→</span>
                        </a>
                    <?php endforeach; ?>
                </div>
            </div>
        <?php else: ?>
            <div class="book-no-chapters">
                <p><?= __('book.syncing') ?></p>
            </div>
        <?php endif; ?>

        <?php
        $shareUrl = ($config['site']['url'] ?? 'https://hey-ailey.com') . '/buch/' . htmlspecialchars($bookSlug);
        portal_share_buttons($shareUrl, $book['title'], $book['description'] ?? __('book.share_overview'));
        ?>
    </section>
</div>

<?php portal_footer(); ?>
