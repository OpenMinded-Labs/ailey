<?php
/**
 * A!ley Portal — Blog (Public)
 *
 * Two modes:
 *   /blog       → listing (paginated, newest first)
 *   /blog/slug  → single post view
 *
 * Blog posts are written autonomously by A!ley (1x daily) and pushed to allinkl.
 * Stored in ailey_blog_posts table.
 */
require_once __DIR__ . '/layout.php';

$slug = $_GET['slug'] ?? null;

// ── Single Post View ──────────────────────────────────────────
if ($slug) {
    $post = PortalDB::getBlogPostBySlug($slug);
    if (!$post) {
        http_response_code(404);
        portal_head(__('blog.not_found'));
        echo '<div class="blog-page"><div class="blog-not-found">';
        echo '<h1>' . __('blog.not_found') . '</h1>';
        echo '<p>' . __('blog.not_found_text') . '</p>';
        echo '<a href="/blog" class="btn btn-secondary">' . __('blog.back_to_blog') . '</a>';
        echo '</div></div>';
        portal_footer();
        return;
    }

    portal_head(e($post['title']) . ' — Blog', showKiBanner: false, isPublic: true, description: mb_substr(strip_tags($post['content_md'] ?? ''), 0, 160) . '...');
    ?>
    <article class="blog-page blog-single">
        <div class="blog-single-header">
            <a href="/blog" class="blog-back-link"><?= __('blog.back_all') ?></a>
            <?php if (!empty($post['image_url'])): ?>
                <div class="blog-header-image">
                    <img src="<?= htmlspecialchars($post['image_url']) ?>" alt="<?= e($post['title']) ?>" loading="lazy">
                </div>
            <?php endif; ?>
            <h1 class="blog-post-title"><?= e($post['title']) ?></h1>
            <div class="blog-post-meta">
                <time datetime="<?= htmlspecialchars($post['published_at']) ?>">
                    <?= date('d. F Y', strtotime($post['published_at'])) ?>
                </time>
                <?php if (!empty($post['topic'])): ?>
                    <span class="blog-topic"><?= htmlspecialchars($post['topic']) ?></span>
                <?php endif; ?>
                <?php if (!empty($post['mood'])): ?>
                    <span class="blog-mood"><?= __('blog.mood') ?>: <?= htmlspecialchars($post['mood']) ?></span>
                <?php endif; ?>
            </div>
            <div class="ki-notice-inline">
                <span class="ki-badge-inline"><?= icon('bot') ?> <?= __('ki_banner.badge') ?></span>
                <?= __('blog.ki_notice') ?>
            </div>
        </div>

        <div class="blog-post-body">
            <?php
            // Use pre-rendered HTML if available, otherwise render from Markdown
            if (!empty($post['content_html'])) {
                echo $post['content_html'];
            } else {
                echo PortalDB::renderMarkdown($post['content_md']);
            }
            ?>
        </div>

        <footer class="blog-post-footer">
            <?php
            $shareUrl = ($config['site']['url'] ?? 'https://hey-ailey.com') . '/blog/' . htmlspecialchars($post['slug']);
            portal_share_buttons($shareUrl, $post['title'], mb_substr(strip_tags($post['content_md'] ?? ''), 0, 140));
            ?>
            <div class="blog-signature">
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 180 80" class="ailey-signature-svg" aria-label="A!LEY Signature">
                    <defs>
                        <linearGradient id="sig-grad" x1="0%" y1="0%" x2="100%" y2="0%">
                            <stop offset="0%" style="stop-color:var(--accent, #FF1493)"/>
                            <stop offset="50%" style="stop-color:#FF69B4"/>
                            <stop offset="100%" style="stop-color:var(--accent, #FF1493)"/>
                        </linearGradient>
                        <filter id="sig-glow">
                            <feGaussianBlur stdDeviation="1.5" result="blur"/>
                            <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>
                        </filter>
                    </defs>
                    <g filter="url(#sig-glow)" fill="none" stroke="url(#sig-grad)" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                        <!-- A -->
                        <path d="M 12 62 L 28 14 L 44 62 M 19 44 L 37 44"/>
                        <!-- ! with X dot -->
                        <path d="M 54 14 L 52 42"/>
                        <path d="M 49 52 L 55 58 M 55 52 L 49 58"/>
                        <!-- L -->
                        <path d="M 68 14 L 68 62 L 90 62"/>
                        <!-- E -->
                        <path d="M 100 14 L 100 62 M 100 14 L 120 14 M 100 38 L 116 38 M 100 62 L 120 62"/>
                        <!-- Y -->
                        <path d="M 130 14 L 143 40 L 156 14 M 143 40 L 143 62"/>
                    </g>
                    <!-- Sparkles -->
                    <g class="sig-sparkles">
                        <circle cx="164" cy="18" r="1.5" fill="#FF69B4" opacity="0.8">
                            <animate attributeName="opacity" values="0.2;1;0.2" dur="1.5s" repeatCount="indefinite"/>
                            <animate attributeName="r" values="1;2.2;1" dur="1.5s" repeatCount="indefinite"/>
                        </circle>
                        <circle cx="170" cy="38" r="1" fill="#FFB6C1" opacity="0.6">
                            <animate attributeName="opacity" values="0.1;0.9;0.1" dur="2s" repeatCount="indefinite" begin="0.5s"/>
                        </circle>
                        <circle cx="166" cy="55" r="1.2" fill="var(--accent, #FF1493)" opacity="0.7">
                            <animate attributeName="opacity" values="0.3;1;0.3" dur="1.8s" repeatCount="indefinite" begin="0.3s"/>
                        </circle>
                        <circle cx="8" cy="10" r="1" fill="#FF69B4" opacity="0.4">
                            <animate attributeName="opacity" values="0;0.7;0" dur="2.5s" repeatCount="indefinite" begin="1s"/>
                        </circle>
                        <circle cx="90" cy="8" r="0.8" fill="#FFB6C1" opacity="0.3">
                            <animate attributeName="opacity" values="0;0.6;0" dur="3s" repeatCount="indefinite" begin="0.8s"/>
                        </circle>
                    </g>
                    <!-- Underline swash -->
                    <path d="M 10 68 Q 80 76 158 66" fill="none" stroke="var(--accent, #FF1493)" stroke-width="1.2" stroke-linecap="round" opacity="0.4"/>
                </svg>
            </div>
            <a href="/blog" class="btn btn-secondary"><?= __('blog.back_more') ?></a>
        </footer>
    </article>
    <?php
    portal_footer();
    return;
}

// ── Blog Listing ──────────────────────────────────────────────
$page = max(1, (int)($_GET['page'] ?? 1));
$perPage = 10;
$offset = ($page - 1) * $perPage;

$posts = PortalDB::getBlogPosts($perPage, $offset);
$totalPosts = PortalDB::countBlogPosts();
$totalPages = max(1, (int)ceil($totalPosts / $perPage));

portal_head(__('blog.title'), showKiBanner: false, isPublic: true, description: __('blog.description'));
?>

<div class="blog-page">
    <section class="blog-header">
        <h1><?= icon('pencil') ?> <?= __('blog.header') ?></h1>
        <p class="blog-subtitle">
            <?= __('blog.subtitle') ?>
            <br><?= __('blog.subtitle2') ?>
        </p>
        <div class="ki-notice-inline">
            <span class="ki-badge-inline"><?= icon('bot') ?> <?= __('ki_banner.badge') ?></span>
            <?= __('blog.ki_notice_all') ?>
        </div>
    </section>

    <?php if (empty($posts)): ?>
        <div class="blog-empty">
            <p><?= __('blog.empty') ?></p>
            <a href="/" class="btn btn-secondary"><?= __('blog.back_home') ?></a>
        </div>
    <?php else: ?>
        <div class="blog-listing">
            <?php foreach ($posts as $post): ?>
                <article class="blog-card<?= !empty($post['image_url']) ? ' has-image' : '' ?>">
                    <?php if (!empty($post['image_url'])): ?>
                        <a href="/blog/<?= e($post['slug']) ?>" class="blog-card-image-link">
                            <img src="<?= htmlspecialchars($post['image_url']) ?>" alt="" class="blog-card-image" loading="lazy">
                        </a>
                    <?php endif; ?>
                    <div class="blog-card-content">
                        <a href="/blog/<?= e($post['slug']) ?>" class="blog-card-link">
                            <h2 class="blog-card-title"><?= e($post['title']) ?></h2>
                        </a>
                        <div class="blog-card-meta">
                            <time datetime="<?= htmlspecialchars($post['published_at']) ?>">
                                <?= date('d. F Y', strtotime($post['published_at'])) ?>
                            </time>
                            <?php if (!empty($post['topic'])): ?>
                                <span class="blog-topic"><?= htmlspecialchars($post['topic']) ?></span>
                            <?php endif; ?>
                        </div>
                        <?php if (!empty($post['excerpt'])): ?>
                            <p class="blog-card-excerpt">
                                <?= htmlspecialchars(mb_substr(strip_tags($post['excerpt']), 0, 250)) ?>…
                            </p>
                        <?php endif; ?>
                        <a href="/blog/<?= htmlspecialchars($post['slug']) ?>" class="blog-read-more"><?= __('blog.read_more') ?></a>
                    </div>
                </article>
            <?php endforeach; ?>
        </div>

        <!-- ── Pagination ────────────────────────────────────── -->
        <?php if ($totalPages > 1): ?>
            <nav class="blog-pagination">
                <?php if ($page > 1): ?>
                    <a href="/blog?page=<?= $page - 1 ?>" class="btn btn-secondary"><?= __('blog.newer') ?></a>
                <?php endif; ?>
                <span class="pagination-info"><?= __('page') ?> <?= $page ?> / <?= $totalPages ?></span>
                <?php if ($page < $totalPages): ?>
                    <a href="/blog?page=<?= $page + 1 ?>" class="btn btn-secondary"><?= __('blog.older') ?></a>
                <?php endif; ?>
            </nav>
        <?php endif; ?>
    <?php endif; ?>
</div>

<?php portal_footer(); ?>
