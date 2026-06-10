<?php
/**
 * A!ley Portal — Activity Feed / Newsfeed (Public)
 *
 * Timeline of A!ley's creative events:
 * - New songs, book chapters, finished books
 * - New images, blog posts
 * - Mood updates (optional)
 *
 * Data from ailey_activity_feed table (pushed by A!ley Core).
 */
require_once __DIR__ . '/layout.php';

$page = max(1, (int)($_GET['page'] ?? 1));
$perPage = 40;
$offset = ($page - 1) * $perPage;

$feed = PortalDB::getActivityFeed($perPage, $offset);
$totalItems = PortalDB::countActivities();
$totalPages = max(1, (int)ceil($totalItems / $perPage));

portal_head(__('feed.title'), showKiBanner: false, isPublic: true, description: __('feed.description'));
?>

<div class="feed-page">
    <section class="feed-header">
        <h1><?= icon('satellite') ?> <?= __('feed.header') ?></h1>
        <p class="feed-subtitle">
            <?= __('feed.subtitle') ?>
        </p>
    </section>

    <?php if (empty($feed)): ?>
        <div class="feed-empty">
            <p><?= __('feed.empty') ?></p>
            <a href="/" class="btn btn-secondary"><?= __('feed.back_home') ?></a>
        </div>
    <?php else: ?>
        <div class="feed-timeline">
            <?php
            $currentDate = '';
            foreach ($feed as $event):
                $eventDate = date('d. F Y', strtotime($event['created_at']));
                if ($eventDate !== $currentDate):
                    $currentDate = $eventDate;
            ?>
                <div class="feed-date-separator">
                    <span><?= htmlspecialchars($eventDate) ?></span>
                </div>
            <?php endif; ?>

                <div class="feed-event feed-event-<?= htmlspecialchars($event['event_type']) ?>">
                    <div class="feed-event-icon">
                        <?= htmlspecialchars($event['emoji'] ?? '📌') ?>
                    </div>
                    <div class="feed-event-content">
                        <h3 class="feed-event-title">
                            <?php if (!empty($event['url'])): ?>
                                <a href="<?= e($event['url']) ?>"><?= e($event['title']) ?></a>
                            <?php else: ?>
                                <?= e($event['title']) ?>
                            <?php endif; ?>
                        </h3>
                        <?php if (!empty($event['preview'])): ?>
                            <p class="feed-event-preview"><?= e(mb_substr($event['preview'], 0, 300)) ?></p>
                        <?php endif; ?>
                        <time class="feed-event-time" datetime="<?= htmlspecialchars($event['created_at']) ?>">
                            <?= date('H:i', strtotime($event['created_at'])) ?> <?= __('feed.time_suffix') ?>
                        </time>
                    </div>
                </div>
            <?php endforeach; ?>
        </div>

        <!-- ── Pagination ────────────────────────────────────── -->
        <?php if ($totalPages > 1): ?>
            <nav class="feed-pagination">
                <?php if ($page > 1): ?>
                    <a href="/feed?page=<?= $page - 1 ?>" class="btn btn-secondary"><?= __('feed.newer') ?></a>
                <?php endif; ?>
                <span class="pagination-info"><?= __('page') ?> <?= $page ?> / <?= $totalPages ?></span>
                <?php if ($page < $totalPages): ?>
                    <a href="/feed?page=<?= $page + 1 ?>" class="btn btn-secondary"><?= __('feed.older') ?></a>
                <?php endif; ?>
            </nav>
        <?php endif; ?>
    <?php endif; ?>
</div>

<?php portal_footer(); ?>
