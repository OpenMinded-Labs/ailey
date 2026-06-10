<?php
/**
 * A!ley Portal — Landing Page (Public)
 *
 * Accessible without login. Shows:
 * - Who/What A!ley is
 * - That the chat is invite-only (transparency)
 * - Live content from DB tables: Gallery, Blog, Feed
 * - KI-Kennzeichnung (EU AI Act)
 * - Status indicator (online/offline)
 */
require_once __DIR__ . '/layout.php';
portal_head(__('landing.welcome'), showKiBanner: false, isPublic: true, description: __('landing.description'));
$aileyStatus = PortalDB::getAileyStatus();
$aileyMood = PortalDB::getAileyMood();
$isOnline = ($aileyStatus === 'online');

// ── Load content from proper DB tables ──
$galleryStats = [];
$recentSongs = [];
$books = [];
$recentPosts = [];
$recentFeed = [];
try {
    $galleryStats = PortalDB::getGalleryStats();
    $recentSongs = PortalDB::getGalleryItems('song', 5, 0);
    $books = PortalDB::getGalleryItems('book', 5, 0);
    $recentPosts = PortalDB::getBlogPosts(3, 0);
    $recentFeed = PortalDB::getActivityFeed(8, 0);
} catch (\Exception $e) {
    // Tables may not exist yet on first deploy
}
?>

<div class="landing-page">

    <!-- ── Hero ──────────────────────────────────────────────── -->
    <section class="landing-hero">
        <div class="hero-inner">
            <div class="hero-avatar">
                <img src="/assets/ailey-default.jpg" alt="A!ley" class="hero-img">
                <span class="status-dot <?= $isOnline ? 'online' : 'offline' ?>"
                      title="<?= $isOnline ? 'Online' : 'Offline' ?>"></span>
            </div>
            <h1 class="hero-title">A<span class="highlight">!</span>ley</h1>
            <p class="hero-tagline"><?= __('landing.tagline') ?></p>
            <p class="hero-description">
                <?= __('landing.hero_text') ?>
                <?= __('landing.built_by') ?> <a href="https://www.sexngears.de" target="_blank" rel="noopener">Simon&nbsp;van&nbsp;de&nbsp;Loo</a>.
            </p>
        </div>
    </section>

    <!-- ── Features / Was A!ley macht ────────────────────────── -->
    <section class="landing-features" id="features">
        <div class="feature-grid">
            <a href="/galerie?type=book" class="feature-card feature-card-link">
                <span class="feature-icon"><?= icon('book-open') ?></span>
                <h3><?= __('landing.books') ?></h3>
                <p><?= __('landing.books_desc') ?></p>
                <?php if (!empty($galleryStats['book'])): ?>
                    <span class="feature-stat"><?= (int)$galleryStats['book'] ?> <?= __('landing.books') ?></span>
                <?php endif; ?>
            </a>
            <a href="/galerie?type=song" class="feature-card feature-card-link">
                <span class="feature-icon"><?= icon('music') ?></span>
                <h3><?= __('landing.songs') ?></h3>
                <p><?= __('landing.songs_desc') ?></p>
                <?php if (!empty($galleryStats['song'])): ?>
                    <span class="feature-stat"><?= (int)$galleryStats['song'] ?> <?= __('landing.written_songs') ?></span>
                <?php endif; ?>
            </a>
            <a href="/galerie?type=svg" class="feature-card feature-card-link">
                <span class="feature-icon"><?= icon('palette') ?></span>
                <h3><?= __('landing.art') ?></h3>
                <p><?= __('landing.art_desc') ?></p>
                <?php if (!empty($galleryStats['image']) || !empty($galleryStats['svg'])): ?>
                    <span class="feature-stat"><?= (int)($galleryStats['image'] ?? 0) + (int)($galleryStats['svg'] ?? 0) ?> <?= __('landing.artworks') ?></span>
                <?php endif; ?>
            </a>
            <a href="<?= $user ? '/chat' : '#access' ?>" class="feature-card feature-card-link">
                <span class="feature-icon"><?= icon('message-circle') ?></span>
                <h3><?= __('landing.chat') ?></h3>
                <p><?= __('landing.chat_desc') ?></p>
            </a>
        </div>
    </section>

    <!-- ── Bücher (from Gallery DB) ────────────────────────────── -->
    <?php if (!empty($books)): ?>
    <section class="landing-books" id="books">
        <h2><?= icon('book-open') ?> <?= __('landing.books_header') ?></h2>
        <div class="book-list">
            <?php foreach ($books as $book):
                $meta = $book['metadata'] ?? [];
            ?>
            <div class="book-card">
                <div class="book-header">
                    <h3 class="book-title"><?= e($book['title']) ?></h3>
                    <?php $status = $meta['status'] ?? 'planning'; ?>
                    <span class="book-badge book-badge-<?= htmlspecialchars($status) ?>">
                        <?= $status === 'writing' ? icon('pencil') . ' ' . __('book.status_writing') : ($status === 'finished' ? icon('check') . ' ' . __('book.status_finished') : icon('clipboard') . ' ' . __('book.status_planned')) ?>
                    </span>
                </div>
                <?php if (!empty($meta['genre'])): ?>
                    <span class="book-genre"><?= e($meta['genre']) ?></span>
                <?php endif; ?>
                <?php if (!empty($book['description'])): ?>
                    <p class="book-synopsis"><?= e(mb_substr($book['description'], 0, 300)) ?><?= mb_strlen($book['description']) > 295 ? '…' : '' ?></p>
                <?php endif; ?>
                <?php if ($status === 'writing' && !empty($meta['progress_pct'])): ?>
                <div class="book-progress">
                    <div class="book-progress-bar" style="width: <?= (int)$meta['progress_pct'] ?>%"></div>
                    <span class="book-progress-text"><?= __('book.chapter') ?> <?= (int)($meta['chapters_done'] ?? 0) ?>/<?= (int)($meta['chapters_total'] ?? 0) ?> · <?= number_format((int)($meta['words'] ?? 0)) ?> <?= __('book.words') ?> (<?= (int)$meta['progress_pct'] ?>%)</span>
                </div>
                <?php endif; ?>
            </div>
            <?php endforeach; ?>
        </div>
        <a href="/galerie?type=book" class="btn btn-secondary btn-section-link"><?= __('landing.all_books') ?></a>
    </section>
    <?php endif; ?>

    <!-- ── Songs (from Gallery DB) ──────────────────────────── -->
    <?php if (!empty($recentSongs)): ?>
    <section class="landing-songs" id="songs">
        <h2><?= icon('music') ?> <?= __('landing.songs_header') ?></h2>
        <div class="song-list">
            <?php foreach ($recentSongs as $song):
                $meta = $song['metadata'] ?? [];
            ?>
            <div class="song-item">
                <span class="song-title"><?= e($song['title']) ?></span>
                <?php if (!empty($meta['genre'])): ?>
                    <span class="song-genre"><?= e($meta['genre']) ?></span>
                <?php endif; ?>
                <span class="song-date"><?= htmlspecialchars(substr($song['created_at'] ?? '', 0, 10)) ?></span>
            </div>
            <?php endforeach; ?>
        </div>
        <a href="/galerie?type=song" class="btn btn-secondary btn-section-link"><?= __('landing.all_songs') ?></a>
    </section>
    <?php endif; ?>

    <!-- ── Blog (Latest Posts) ───────────────────────────────── -->
    <?php if (!empty($recentPosts)): ?>
    <section class="landing-blog" id="blog">
        <h2><?= icon('pencil') ?> <?= __('landing.blog_header') ?></h2>
        <div class="blog-preview-list">
            <?php foreach ($recentPosts as $post): ?>
            <article class="blog-preview-card">
                <a href="/blog/<?= e($post['slug']) ?>">
                    <h3><?= e($post['title']) ?></h3>
                </a>
                <div class="blog-preview-meta">
                    <time datetime="<?= htmlspecialchars($post['published_at']) ?>">
                        <?= date('d.m.Y', strtotime($post['published_at'])) ?>
                    </time>
                    <?php if (!empty($post['topic'])): ?>
                        <span class="blog-topic"><?= e($post['topic']) ?></span>
                    <?php endif; ?>
                </div>
                <?php if (!empty($post['excerpt'])): ?>
                    <p class="blog-preview-excerpt"><?= e(mb_substr(strip_tags($post['excerpt']), 0, 200)) ?>…</p>
                <?php endif; ?>
            </article>
            <?php endforeach; ?>
        </div>
        <a href="/blog" class="btn btn-secondary btn-section-link"><?= __('landing.all_posts') ?></a>
    </section>
    <?php endif; ?>

    <!-- ── Activity Feed (Recent Events) ─────────────────────── -->
    <?php if (!empty($recentFeed)): ?>
    <section class="landing-feed" id="feed">
        <h2><?= icon('satellite') ?> <?= __('landing.feed_header') ?></h2>
        <div class="feed-preview">
            <?php foreach ($recentFeed as $event): ?>
            <div class="feed-preview-item">
                <span class="feed-preview-emoji"><?= e($event['emoji'] ?? '📌') ?></span>
                <div class="feed-preview-content">
                    <span class="feed-preview-title">
                        <?php if (!empty($event['url'])): ?>
                            <a href="<?= e($event['url']) ?>"><?= e($event['title']) ?></a>
                        <?php else: ?>
                            <?= e($event['title']) ?>
                        <?php endif; ?>
                    </span>
                    <time class="feed-preview-time" datetime="<?= htmlspecialchars($event['created_at']) ?>">
                        <?= date('d.m. H:i', strtotime($event['created_at'])) ?>
                    </time>
                </div>
            </div>
            <?php endforeach; ?>
        </div>
        <a href="/feed" class="btn btn-secondary btn-section-link"><?= __('landing.all_feed') ?></a>
    </section>
    <?php endif; ?>

    <!-- ── Chat Zugang (Transparenz) ─────────────────────────── -->
    <section class="landing-access" id="access">
        <div class="access-card">
            <div class="access-icon"><?= icon('lock') ?></div>
            <h2><?= __('landing.access_title') ?></h2>
            <p><?= __('landing.access_p1') ?></p>
            <p class="access-why"><?= __('landing.access_why') ?></p>

            <div class="access-status">
                <span class="status-dot <?= $isOnline ? 'online' : 'offline' ?>"></span>
                <span><?= $isOnline ? __('landing.status_online') : __('landing.status_offline') ?></span>
                <?php if ($isOnline && $aileyMood && $aileyMood !== 'neutral'): ?>
                    <span class="mood-hint"> — <?= __('landing.mood_hint') ?>: <?= htmlspecialchars($aileyMood) ?></span>
                <?php endif; ?>
            </div>

            <?php if ($user): ?>
                <a href="/chat" class="btn btn-primary btn-landing"><?= __('landing.to_chat') ?></a>
            <?php else: ?>
                <div class="access-buttons">
                    <a href="/login" class="btn btn-primary btn-landing"><?= __('landing.login') ?></a>
                    <a href="/register" class="btn btn-secondary btn-landing"><?= __('landing.register') ?></a>
                </div>
            <?php endif; ?>
        </div>
    </section>

    <!-- ── KI-Transparenz (EU AI Act) ────────────────────────── -->
    <section class="landing-disclosure" id="disclosure">
        <div class="disclosure-card">
            <h2><span class="ki-badge-inline"><?= icon('bot') ?> <?= __('ki_banner.badge') ?></span> <?= __('landing.disclosure_title') ?></h2>
            <p><?= __('landing.disclosure_intro') ?></p>
            <ul class="disclosure-list">
                <li><?= __('landing.disclosure_consciousness') ?></li>
                <li><?= __('landing.disclosure_advice') ?></li>
                <li><?= __('landing.disclosure_local') ?></li>
                <li>
                    <?= __('landing.disclosure_privacy') ?>
                    <a href="/datenschutz"><?= __('landing.disclosure_privacy_link') ?></a>
                </li>
            </ul>
            <p class="disclosure-legal">
                <?= __('landing.disclosure_legal') ?>
                <?= htmlspecialchars($config['site']['impressum']['name'] ?? 'Simon van de Loo') ?>.
            </p>
        </div>
    </section>

    <!-- ── Über das Projekt ──────────────────────────────────── -->
    <section class="landing-about" id="about">
        <h2><?= __('landing.about_title') ?></h2>
        <p>
            <?= __('landing.about_p1') ?>
        </p>
        <p>
            <?= __('landing.about_p2') ?>
        </p>
        <p>
            Simon ist außerdem Autor der Romanreihe 
            <a href="https://www.sexngears.de/buecher" target="_blank" rel="noopener"><strong>Martyria</strong></a> 
            (Steampunk/Dark Fantasy) unter dem Label 
            <a href="https://www.sexngears.de" target="_blank" rel="noopener">Sex'n'Gears</a>.
        </p>
        <div class="cta-human-art">
            <?= icon('book-open') ?>
            <span><?= __('landing.about_cta') ?> <a href="https://www.sexngears.de/buecher" target="_blank" rel="noopener">Sexngears.de</a></span>
        </div>
    </section>

</div>

<?php portal_footer(); ?>
