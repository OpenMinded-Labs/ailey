<?php
/**
 * A!ley Portal — Galerie (Public)
 *
 * Shows A!ley's creative works:
 * - Songs (lyrics, genre, date)
 * - Bücher (synopsis, progress, reading sample)
 * - Bilder (prompt, generated image)
 * - SVG-Kunst
 *
 * All data served from ailey_gallery_items table (persistent on allinkl).
 */
require_once __DIR__ . '/layout.php';

// NSFW: logged-in users see full content, visitors get censored lines
$isLoggedIn = isset($user) && $user !== null;
$isAdmin = $isLoggedIn && ($user['role'] ?? '') === 'admin';
$currentUserId = $isLoggedIn ? ($user['id'] ?? null) : null;

$filterType = $_GET['type'] ?? null;
$filterSelfie = $_GET['selfie'] ?? null;
$filterAudio = $_GET['audio'] ?? null;  // '1' = songs with audio, '0' = lyrics only
$searchQuery = trim($_GET['q'] ?? '');
if ($filterType && !in_array($filterType, ['song', 'image', 'svg', 'book', 'code'])) {
    $filterType = null;
}

$page = max(1, (int)($_GET['page'] ?? 1));
$perPage = 24;
$offset = ($page - 1) * $perPage;

// ── Selfie-Filter: need to load all images and filter in PHP because
//    the selfie flag lives inside metadata_json, not as a DB column.
//    For non-image types, use normal paginated query.
$needsSelfieFilter = ($filterType === 'image' && $filterSelfie !== null);

if ($needsSelfieFilter) {
    // Load ALL published images, mark selfies, filter, then paginate in PHP
    $allImageItems = PortalDB::getGalleryItems('image', 9999, 0);
    foreach ($allImageItems as &$_img) {
        $_meta = $_img['metadata'] ?? [];
        $_img['_is_selfie'] = !empty($_meta['is_selfie'])
            || (isset($_meta['filename']) && stripos($_meta['filename'], 'SELFIE') !== false);
    }
    unset($_img);

    // Count selfies from full set
    $selfieCount = count(array_filter($allImageItems, fn($i) => !empty($i['_is_selfie'])));

    // Apply selfie filter
    if ($filterSelfie === '1') {
        $filteredItems = array_values(array_filter($allImageItems, fn($i) => !empty($i['_is_selfie'])));
    } else {
        $filteredItems = array_values(array_filter($allImageItems, fn($i) => empty($i['_is_selfie'])));
    }

    // Manual pagination
    $totalItems = count($filteredItems);
    $totalPages = max(1, (int)ceil($totalItems / $perPage));
    $items = array_slice($filteredItems, $offset, $perPage);
} else {
    // For songs: load ALL items so client-side search works across the full catalogue
    $songLoadAll = ($filterType === 'song');
    $loadLimit = $songLoadAll ? 9999 : $perPage;
    $loadOffset = $songLoadAll ? 0 : $offset;

    // Normal paginated query (songs, books, SVGs, code, or all images without selfie filter)
    $items = PortalDB::getGalleryItems($filterType, $loadLimit, $loadOffset);

    // ── Audio filter: Songs with audio vs lyrics-only ──
    if ($filterType === 'song' && $filterAudio !== null) {
        $items = array_values(array_filter($items, function($it) use ($filterAudio) {
            $m = $it['metadata'] ?? [];
            $hasAudio = !empty($m['audio_url']) || (!empty($it['file_url']) && str_ends_with($it['file_url'], '.mp3'));
            return $filterAudio === '1' ? $hasAudio : !$hasAudio;
        }));
    }

    // Mark selfies on the loaded items
    foreach ($items as &$item) {
        $meta = $item['metadata'] ?? [];
        $item['_is_selfie'] = !empty($meta['is_selfie'])
            || (isset($meta['filename']) && stripos($meta['filename'], 'SELFIE') !== false);
    }
    unset($item);

    // Count selfies for tab display
    $selfieCount = 0;
    if (!$filterType || $filterType === 'image') {
        $allImages = PortalDB::getGalleryItems('image', 9999, 0);
        foreach ($allImages as $img) {
            $imgMeta = $img['metadata'] ?? [];
            if (!empty($imgMeta['is_selfie']) || (isset($imgMeta['filename']) && stripos($imgMeta['filename'], 'SELFIE') !== false)) {
                $selfieCount++;
            }
        }
    }

    $stats = PortalDB::getGalleryStats();
    $totalItems = $filterType ? PortalDB::countGalleryItems($filterType) : $stats['total'];
    $totalPages = max(1, (int)ceil($totalItems / $perPage));
}

// ── NSFW filter: censor song lyrics for non-logged-in users ──
foreach ($items as &$item) {
    if ($item['item_type'] === 'song' && !empty($item['content_text'])) {
        $nsfwResult = NsfwFilter::censorSongContent($item['content_text']);
        $item['_is_nsfw'] = $nsfwResult['is_nsfw'];
        $item['_censored_lines'] = $nsfwResult['censored_lines'];
        if (!$isLoggedIn && $nsfwResult['is_nsfw']) {
            $item['content_text'] = $nsfwResult['content'];
        }
    } else {
        $item['_is_nsfw'] = false;
    }
}
unset($item);

// Ensure $stats is always available (for header display)
if (!isset($stats)) {
    $stats = PortalDB::getGalleryStats();
}
if (!isset($totalItems)) {
    $totalItems = $filterType ? PortalDB::countGalleryItems($filterType) : $stats['total'];
    $totalPages = max(1, (int)ceil($totalItems / $perPage));
}

$typeLabels = [
    'song' => 'Songs',
    'image' => 'Bilder',
    'svg' => 'SVG-Kunst',
    'book' => 'Bücher',
    'code' => 'Code',
];

$pageTitle = $filterType ? ($typeLabels[$filterType] ?? __('gallery.title')) : __('gallery.title');

portal_head($pageTitle, showKiBanner: false, isPublic: true, description: __('gallery.description'));
?>

<div class="gallery-page">

<?php
// ── Structured data: songs as MusicRecording (rich results / SEO) ──
if ($filterType === 'song' && !empty($items)) {
    $sdUrl = $config['site']['url'] ?? 'https://hey-ailey.com';
    $sdElements = [];
    $sdPos = 0;
    foreach ($items as $sdItem) {
        if (($sdItem['item_type'] ?? '') !== 'song') continue;
        $sdPos++;
        if ($sdPos > 60) break; // cap payload
        $sdMeta = $sdItem['metadata'] ?? [];
        $sdAudio = $sdMeta['audio_url'] ?? null;
        if (!$sdAudio && !empty($sdItem['file_url']) && str_ends_with($sdItem['file_url'], '.mp3')) {
            $sdAudio = $sdItem['file_url'];
        }
        $sdRec = [
            '@type'    => 'MusicRecording',
            'name'     => $sdItem['title'] ?? 'Song',
            'byArtist' => ['@id' => $sdUrl . '/#ailey'],
            'url'      => $sdUrl . '/galerie?type=song',
        ];
        if (!empty($sdMeta['genre']))       $sdRec['genre'] = $sdMeta['genre'];
        if (!empty($sdMeta['album_title'])) $sdRec['inAlbum'] = ['@type' => 'MusicAlbum', 'name' => $sdMeta['album_title']];
        if (!empty($sdItem['created_at']))  $sdRec['datePublished'] = date('c', strtotime($sdItem['created_at']));
        if ($sdAudio) {
            $sdRec['audio'] = ['@type' => 'AudioObject', 'contentUrl' => $sdAudio, 'encodingFormat' => 'audio/mpeg'];
        }
        if (!empty($sdMeta['cover_url']))   $sdRec['image'] = $sdMeta['cover_url'];
        $sdElements[] = ['@type' => 'ListItem', 'position' => $sdPos, 'item' => $sdRec];
    }
    if ($sdElements) {
        echo '<script type="application/ld+json">' .
             json_encode([
                 '@context' => 'https://schema.org',
                 '@type'    => 'ItemList',
                 'name'     => 'A!ley Vyrus — Songs',
                 'itemListElement' => $sdElements,
             ], JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE) .
             "</script>\n";
    }
    unset($sdItem, $sdMeta, $sdRec, $sdElements);
}
?>

    <!-- ── Header ────────────────────────────────────────────── -->
    <section class="gallery-header">
        <h1><?= icon('palette') ?> <?= __('gallery.header') ?></h1>
        <p class="gallery-subtitle">
            <?= (int)$stats['total'] ?> <?= __('gallery.works') ?> — 
            <?= (int)$stats['song'] ?> <?= __('gallery.filter_song') ?>, 
            <?= (int)$stats['book'] ?> <?= __('gallery.filter_book') ?>, 
            <?= (int)$stats['image'] ?> <?= __('gallery.filter_image') ?>, 
            <?= (int)$stats['svg'] ?> <?= __('gallery.filter_svg') ?>,
            <?= (int)$stats['code'] ?> <?= __('gallery.filter_code') ?>
        </p>
    </section>

    <!-- ── Filter Tabs ───────────────────────────────────────── -->
    <?php
    // Count songs with audio vs lyrics-only
    $songAudioCount = 0;
    $songLyricsCount = 0;
    if (true) {
        $allSongsForCount = PortalDB::getGalleryItems('song', 9999, 0);
        foreach ($allSongsForCount as $_sc) {
            $_sm = $_sc['metadata'] ?? [];
            $_au = $_sm['audio_url'] ?? null;
            if (!$_au && !empty($_sc['file_url']) && str_ends_with($_sc['file_url'], '.mp3')) {
                $_au = $_sc['file_url'];
            }
            if ($_au) { $songAudioCount++; } else { $songLyricsCount++; }
        }
        unset($allSongsForCount, $_sc, $_sm, $_au);
    }
    ?>
    <nav class="gallery-filters">
        <a href="/galerie" class="filter-tab <?= !$filterType ? 'active' : '' ?>"><?= __('gallery.filter_all') ?></a>
        <a href="/galerie?type=song&audio=1" class="filter-tab <?= $filterType === 'song' && $filterAudio === '1' ? 'active' : '' ?>"><?= icon('music') ?> Songs (<?= $songAudioCount ?>)</a>
        <a href="/galerie?type=song&audio=0" class="filter-tab <?= $filterType === 'song' && $filterAudio === '0' ? 'active' : '' ?>">📝 Songtexte (<?= $songLyricsCount ?>)</a>
        <a href="/galerie?type=book" class="filter-tab <?= $filterType === 'book' ? 'active' : '' ?>"><?= icon('book-open') ?> <?= __('gallery.filter_book') ?> (<?= (int)$stats['book'] ?>)</a>
        <a href="/galerie?type=image&selfie=0" class="filter-tab <?= $filterType === 'image' && $filterSelfie !== '1' ? 'active' : '' ?>"><?= icon('image') ?> <?= __('gallery.filter_image') ?> (<?= (int)$stats['image'] - $selfieCount ?>)</a>
        <?php if ($selfieCount > 0): ?>
        <a href="/galerie?type=image&selfie=1" class="filter-tab <?= $filterType === 'image' && $filterSelfie === '1' ? 'active' : '' ?>">🤳 Selfies (<?= $selfieCount ?>)</a>
        <?php endif; ?>
        <a href="/galerie?type=svg" class="filter-tab <?= $filterType === 'svg' ? 'active' : '' ?>"><?= icon('pen-tool') ?> <?= __('gallery.filter_svg') ?> (<?= (int)$stats['svg'] ?>)</a>
        <a href="/galerie?type=code" class="filter-tab <?= $filterType === 'code' ? 'active' : '' ?>"><?= icon('code') ?> <?= __('gallery.filter_code') ?> (<?= (int)$stats['code'] ?>)</a>
    </nav>

    <!-- ── Song Search ───────────────────────────────────────── -->
    <?php if ($filterType === 'song'): ?>
    <div class="gallery-song-search">
        <div class="song-search-wrapper">
            <span class="song-search-icon"><?= icon('search') ?></span>
            <input type="text" 
                   id="song-search-input" 
                   class="song-search-input" 
                   placeholder="Song suchen … (Name, Genre, Lyrics)"
                   value="<?= e($searchQuery) ?>"
                   autocomplete="off"
                   spellcheck="false">
            <button class="song-search-clear" id="song-search-clear" title="Suche zurücksetzen" style="<?= $searchQuery ? '' : 'display:none' ?>">✕</button>
        </div>
        <div class="song-search-status" id="song-search-status"></div>
    </div>
    <?php endif; ?>

    <!-- ── Selfie Disclaimer ─────────────────────────────────── -->
    <?php if ($filterType === 'image' && $filterSelfie === '1'): ?>
    <div class="gallery-selfie-disclaimer">
        <p>🤖 <strong>Hinweis:</strong> Die hier gezeigte Person ist <em>kein echter Mensch</em>. 
        A!ley's kohärentes Aussehen über verschiedene Bilder hinweg wird durch ein 
        <strong>LoRA</strong> (Low-Rank Adaptation) erreicht — ein selbst trainiertes 
        KI-Modell, das auf einem Open-Source Image Generator (FLUX) aufbaut. 
        Das Ergebnis: Eine konsistente digitale Identität, generiert auf einem MacBook Air M4.</p>
    </div>
    <?php endif; ?>

    <!-- ── Album Grouping (Songs only) ─────────────────────── -->
    <?php
    // When viewing songs, group them by album and build an ordered display list
    // with album header/footer markers inserted around song groups
    $displayItems = $items; // default: flat list
    if ($filterType === 'song' && !empty($items)) {
        $albumGroups = [];
        $looseItems = [];
        foreach ($items as $item) {
            $meta = $item['metadata'] ?? [];
            $albumSlug = $meta['album_slug'] ?? null;
            if ($albumSlug && !empty($meta['album_title'])) {
                if (!isset($albumGroups[$albumSlug])) {
                    $albumGroups[$albumSlug] = [
                        'title' => $meta['album_title'],
                        'concept' => $meta['album_concept'] ?? '',
                        'cover_url' => $meta['cover_url'] ?? $meta['portal_cover_url'] ?? null,
                        'songs' => [],
                        // Album birth date from manifest — stable sort key
                        '_album_date' => $meta['album_created_at'] ?? '',
                        '_album_date_confirmed' => !empty($meta['album_created_at']),
                    ];
                }
                $albumGroups[$albumSlug]['songs'][] = $item;
                // Prefer album_created_at from any song that has it
                if (!$albumGroups[$albumSlug]['_album_date_confirmed'] && !empty($meta['album_created_at'])) {
                    $albumGroups[$albumSlug]['_album_date'] = $meta['album_created_at'];
                    $albumGroups[$albumSlug]['_album_date_confirmed'] = true;
                }
                // Fallback: if still no album date, use song date
                if (empty($albumGroups[$albumSlug]['_album_date'])) {
                    $albumGroups[$albumSlug]['_album_date'] = $meta['date'] ?? '2000-01-01';
                }
                // Pick cover_url from any song that has one
                if (!$albumGroups[$albumSlug]['cover_url']) {
                    $albumGroups[$albumSlug]['cover_url'] = $meta['cover_url'] ?? $meta['portal_cover_url'] ?? null;
                }
            } else {
                $looseItems[] = $item;
            }
        }
        if (!empty($albumGroups)) {
            // Sort albums: newest first (by album creation date)
            uasort($albumGroups, function($a, $b) {
                return strcmp($b['_album_date'], $a['_album_date']);
            });

            $displayItems = [];
            foreach ($albumGroups as $aSlug => $album) {
                $displayItems[] = [
                    '_album_header' => true,
                    '_album_title' => $album['title'],
                    '_album_concept' => $album['concept'],
                    '_album_cover_url' => $album['cover_url'],
                    '_album_track_count' => count($album['songs']),
                ];
                foreach ($album['songs'] as $song) {
                    $displayItems[] = $song;
                }
                $displayItems[] = ['_album_footer' => true];
            }
            if (!empty($looseItems)) {
                $displayItems[] = ['_album_header' => true, '_album_title' => 'Singles & Loose Tracks', '_album_concept' => '', '_album_cover_url' => null, '_album_track_count' => count($looseItems)];
                foreach ($looseItems as $loose) {
                    $displayItems[] = $loose;
                }
                $displayItems[] = ['_album_footer' => true];
            }
        }
    }
    ?>

    <!-- ── Gallery Grid ──────────────────────────────────────── -->
    <?php if (empty($items)): ?>
        <div class="gallery-empty">
            <p><?= __('gallery.empty_category') ?></p>
            <?php if ($filterType): ?>
                <a href="/galerie" class="btn btn-secondary"><?= __('gallery.show_all') ?></a>
            <?php endif; ?>
        </div>
    <?php else: ?>
        <div class="gallery-grid">
            <?php foreach ($displayItems as $item): ?>
                <?php
                // ── Album header marker ──
                if (!empty($item['_album_header'])) {
                    echo '</div>'; // close current grid
                    echo '<div class="gallery-album-section">';
                    echo '<div class="gallery-album-header">';
                    if (!empty($item['_album_cover_url'])) {
                        echo '<div class="gallery-album-cover">';
                        echo '<img src="' . e($item['_album_cover_url']) . '" alt="' . e($item['_album_title']) . '" loading="lazy">';
                        echo '</div>';
                    }
                    echo '<div class="gallery-album-info">';
                    echo '<h2 class="gallery-album-title">💿 ' . e($item['_album_title']) . '</h2>';
                    if (!empty($item['_album_concept'])) {
                        echo '<p class="gallery-album-concept">' . e($item['_album_concept']) . '</p>';
                    }
                    echo '<span class="gallery-album-count">' . (int)$item['_album_track_count'] . ' Tracks</span>';
                    echo ' <button class="ailey-play-album-btn" onclick="playAlbum(this)" title="Album abspielen">▶ Play Album</button>';
                    echo '</div>';
                    echo '</div>';
                    echo '<div class="gallery-grid">';
                    continue;
                }
                // ── Album footer marker ──
                if (!empty($item['_album_footer'])) {
                    echo '</div></div>'; // close grid + album-section
                    echo '<div class="gallery-grid">'; // re-open grid for next items
                    continue;
                }
                ?>
                <?php
                // Build link URL for books
                $cardLink = '';
                if ($item['item_type'] === 'book' && !empty($item['metadata']['slug'])) {
                    $cardLink = '/buch/' . e($item['metadata']['slug']);
                }
                // Build search corpus for song cards (title + genre + first lines of lyrics)
                $searchCorpus = '';
                if ($item['item_type'] === 'song') {
                    $searchCorpus = strtolower(
                        ($item['title'] ?? '') . ' ' .
                        ($item['metadata']['genre'] ?? '') . ' ' .
                        mb_substr($item['content_text'] ?? '', 0, 300)
                    );
                }
                ?>
                <<?= $cardLink ? 'a href="' . $cardLink . '"' : 'div' ?> class="gallery-card gallery-card-<?= htmlspecialchars($item['item_type']) ?><?= $cardLink ? ' gallery-card-link' : '' ?>"<?php if ($searchCorpus): ?> data-search="<?= e($searchCorpus) ?>"<?php endif; ?>>
                    <!-- Type badge -->
                    <span class="gallery-type-badge type-<?= htmlspecialchars($item['item_type']) ?>">
                        <?php
                        $badgeIcons = ['song' => 'music', 'book' => 'book-open', 'image' => 'image', 'svg' => 'pen-tool', 'code' => 'code'];
                        echo icon($badgeIcons[$item['item_type']] ?? 'file-text');
                        ?>
                    </span>

                    <!-- Selfie badge -->
                    <?php if (!empty($item['_is_selfie'])): ?>
                        <span class="gallery-selfie-badge" title="LoRA Selfie">🤳</span>
                    <?php endif; ?>

                    <!-- NSFW badge -->
                    <?php if (!empty($item['_is_nsfw'])): ?>
                        <span class="gallery-nsfw-badge" title="Explicit content">🔞</span>
                    <?php endif; ?>

                    <!-- Fullscreen button for SVG / Code / Image -->
                    <?php if ($item['item_type'] === 'svg'): ?>
                        <button class="gallery-fullscreen-btn" onclick="event.preventDefault();event.stopPropagation();openSvgFullscreen(this)" title="<?= __('gallery.fullscreen') ?>">⛶</button>
                    <?php endif; ?>
                    <?php if ($item['item_type'] === 'code' && !empty($item['content_text'])): ?>
                        <button class="gallery-fullscreen-btn" onclick="event.preventDefault();event.stopPropagation();openCodeFullscreen(this)" title="<?= __('gallery.fullscreen') ?>">⛶</button>
                    <?php endif; ?>
                    <?php if ($item['item_type'] === 'image' && !empty($item['file_url'])): ?>
                        <button class="gallery-fullscreen-btn" onclick="event.preventDefault();event.stopPropagation();openImageFullscreen(this)" title="<?= __('gallery.fullscreen') ?>">⛶</button>
                    <?php endif; ?>

                    <!-- Download button (public — all items with file_url) -->
                    <?php if (!empty($item['file_url'])): ?>
                        <a class="gallery-download-btn" href="<?= e($item['file_url']) ?>" download title="Download" onclick="event.stopPropagation()">⬇</a>
                    <?php endif; ?>

                    <!-- Delete button (owner or admin) -->
                    <?php if ($isAdmin || ($currentUserId && !empty($item['submitted_by']) && $item['submitted_by'] === $currentUserId)): ?>
                        <button class="gallery-delete-btn" onclick="event.preventDefault();event.stopPropagation();deleteGalleryItem(<?= (int)$item['id'] ?>, this)" title="Löschen">✕</button>
                    <?php endif; ?>

                    <!-- Image / Visual -->
                    <?php if ($item['item_type'] === 'image' && !empty($item['file_url'])): ?>
                        <div class="gallery-card-visual gallery-card-visual-contain" onclick="event.preventDefault();event.stopPropagation();openImageFullscreen(this.closest('.gallery-card').querySelector('.gallery-fullscreen-btn'))">
                            <img src="<?= e($item['file_url']) ?>" 
                                 alt=""
                                 loading="lazy">
                        </div>
                    <?php elseif ($item['item_type'] === 'svg'): ?>
                        <div class="gallery-card-visual gallery-svg">
                            <?php if (!empty($item['content_text']) && str_starts_with(trim($item['content_text']), '<')): ?>
                                <!-- Inline SVG rendering -->
                                <?= $item['content_text'] ?>
                            <?php elseif (!empty($item['file_url'])): ?>
                                <img src="<?= e($item['file_url']) ?>" 
                                     alt=""
                                     loading="lazy">
                            <?php else: ?>
                                <div class="gallery-svg-placeholder"><?= icon('pen-tool') ?></div>
                            <?php endif; ?>
                        </div>
                    <?php elseif ($item['item_type'] === 'code' && !empty($item['content_text'])): ?>
                        <?php
                        // Detect if content is a full HTML document (renderable in iframe)
                        $codeContent = trim($item['content_text']);
                        $isHtmlDoc = (
                            stripos($codeContent, '<!doctype html') !== false
                            || stripos($codeContent, '<html') !== false
                            || (stripos($codeContent, '<canvas') !== false && stripos($codeContent, '<script') !== false)
                            || (stripos($codeContent, '<style') !== false && stripos($codeContent, '<script') !== false)
                        );
                        ?>
                        <?php if ($isHtmlDoc): ?>
                            <div class="gallery-card-visual gallery-code-preview">
                                <iframe class="code-preview-iframe"
                                        sandbox="allow-scripts"
                                        loading="lazy"
                                        srcdoc="<?= e($codeContent) ?>"
                                        title="<?= e($item['title']) ?>"></iframe>
                                <div class="code-preview-overlay" onclick="event.preventDefault();event.stopPropagation();openCodeFullscreen(this.closest('.gallery-card').querySelector('.gallery-fullscreen-btn') || this)"></div>
                            </div>
                        <?php else: ?>
                            <div class="gallery-card-visual gallery-code-placeholder">
                                <?= icon('code') ?>
                            </div>
                        <?php endif; ?>
                    <?php endif; ?>

                    <!-- Content -->
                    <div class="gallery-card-body">
                        <?php
                        // For songs: extract a clean title (strip metadata like "Genre: ..." from title)
                        $displayTitle = $item['title'];
                        if ($item['item_type'] === 'song') {
                            // Remove common metadata prefixes that end up as titles
                            $displayTitle = preg_replace('/^(Genre|Style|Stil|Tempo|BPM|Stimmung|Mood)\s*[:：].*/i', '', $displayTitle);
                            $displayTitle = trim($displayTitle);
                            if (!$displayTitle || strlen($displayTitle) < 3) {
                                // Fallback: first meaningful line from content
                                $lines = explode("\n", trim($item['content_text'] ?? ''));
                                foreach ($lines as $line) {
                                    $line = trim($line);
                                    // Skip metadata lines, brackets, empty
                                    if (!$line || preg_match('/^(Genre|Style|Stil|Tempo|BPM|Stimmung|Mood|EMOTION|TITEL)\s*[:：]/i', $line)) continue;
                                    $line = trim($line, '[]* ');
                                    if (strlen($line) >= 3) { $displayTitle = mb_substr($line, 0, 80); break; }
                                }
                                if (!$displayTitle) $displayTitle = 'Untitled';
                            }
                        }
                        // Ensure proper UTF-8 — strip invalid bytes
                        $displayTitle = mb_convert_encoding($displayTitle, 'UTF-8', 'UTF-8');
                        // Hide title for images and SVGs (purely visual content)
                        $showTitle = !in_array($item['item_type'], ['image', 'svg']);
                        ?>
                        <?php if ($showTitle): ?>
                            <h3 class="gallery-card-title"><?= e($displayTitle) ?></h3>
                        <?php endif; ?>

                        <?php if ($item['item_type'] === 'song' && !empty($item['content_text'])): ?>
                            <!-- Song: audio player + collapsible lyrics -->
                            <?php
                            $songMeta = $item['metadata'] ?? [];
                            $audioUrl = $songMeta['audio_url'] ?? null;
                            // Fallback: file_url column may contain the MP3 URL directly
                            if (!$audioUrl && !empty($item['file_url']) && str_ends_with($item['file_url'], '.mp3')) {
                                $audioUrl = $item['file_url'];
                            }
                            $coverUrl = $songMeta['cover_url'] ?? $songMeta['portal_cover_url'] ?? null;
                            ?>
                            <?php if ($audioUrl): ?>
                                <div class="gallery-song-player">
                                    <audio controls preload="none" class="gallery-audio">
                                        <source src="<?= e($audioUrl) ?>" type="audio/mpeg">
                                    </audio>
                                </div>
                            <?php endif; ?>
                            <p class="gallery-card-desc gallery-lyrics-preview"><?= nl2br(e(mb_substr($item['content_text'], 0, 120))) ?>…</p>
                            <details class="gallery-lyrics-details">
                                <summary><?= __('gallery.show_lyrics') ?></summary>
                                <div class="gallery-lyrics-full"><?= nl2br(e($item['content_text'])) ?></div>
                                <?php if (!$isLoggedIn && !empty($item['_is_nsfw'])): ?>
                                    <p class="gallery-nsfw-notice">
                                        🔞 Einige Zeilen wurden zensiert. <a href="/login">Einloggen</a> für den vollständigen Text.
                                    </p>
                                <?php endif; ?>
                            </details>
                        <?php elseif ($item['item_type'] === 'code' && !empty($item['content_text'])): ?>
                            <!-- Code: collapsible source with metadata -->
                            <?php if (!empty($item['description'])): ?>
                                <p class="gallery-card-desc"><?= e(mb_substr($item['description'], 0, 200)) ?></p>
                            <?php endif; ?>
                            <details class="gallery-code-details">
                                <summary><?= __('gallery.show_code') ?></summary>
                                <pre class="gallery-code-full"><code><?= e($item['content_text']) ?></code></pre>
                            </details>
                            <!-- Hidden raw HTML for fullscreen iframe -->
                            <script type="text/plain" class="code-raw-html"><?= e($item['content_text']) ?></script>
                        <?php elseif (!empty($item['description'])): ?>
                            <p class="gallery-card-desc"><?= nl2br(e(mb_substr($item['description'], 0, 200))) ?><?= mb_strlen($item['description']) > 200 ? '…' : '' ?></p>
                        <?php endif; ?>

                        <?php if (!empty($item['metadata'])): $meta = $item['metadata']; ?>
                            <?php if (!empty($meta['genre'])): ?>
                                <span class="gallery-meta-tag"><?= e($meta['genre']) ?></span>
                            <?php endif; ?>
                            <?php if (!empty($meta['album_title'])): ?>
                                <span class="gallery-meta-tag tag-album">💿 <?= e($meta['album_title']) ?></span>
                            <?php endif; ?>
                            <?php if (!empty($meta['language']) && $item['item_type'] === 'code'): ?>
                                <span class="gallery-meta-tag tag-lang"><?= e($meta['language']) ?></span>
                            <?php endif; ?>
                            <?php if (!empty($meta['platform']) && $item['item_type'] === 'code'): ?>
                                <span class="gallery-meta-tag tag-platform"><?= e($meta['platform']) ?></span>
                            <?php endif; ?>
                            <?php if (!empty($meta['lines']) && $item['item_type'] === 'code'): ?>
                                <span class="gallery-meta-tag tag-lines"><?= (int)$meta['lines'] ?> Zeilen</span>
                            <?php endif; ?>
                            <?php if (!empty($meta['status'])): ?>
                                <span class="gallery-meta-tag status-<?= htmlspecialchars($meta['status']) ?>">
                                    <?= $meta['status'] === 'writing' ? icon('pencil') . ' ' . __('gallery.status_writing') : ($meta['status'] === 'finished' ? icon('check') . ' ' . __('gallery.status_finished') : icon('clipboard') . ' ' . __('gallery.status_planned')) ?>
                                </span>
                            <?php endif; ?>
                            <?php if (!empty($meta['progress_pct']) && $item['item_type'] === 'book'): ?>
                                <div class="gallery-progress">
                                    <div class="gallery-progress-bar" style="width: <?= (int)$meta['progress_pct'] ?>%"></div>
                                    <span class="gallery-progress-text"><?= (int)$meta['progress_pct'] ?>%</span>
                                </div>
                            <?php endif; ?>
                        <?php endif; ?>

                        <time class="gallery-card-date" datetime="<?= htmlspecialchars($item['created_at']) ?>">
                            <?= date('d.m.Y', strtotime($item['created_at'])) ?>
                        </time>

                        <?php // ── V$ Rating & Comment Widget ──
                        $itemId = htmlspecialchars($item['id']);
                        $ratingInfo = PortalDB::getGalleryItemRatings($item['id']);
                        $avgRating = $ratingInfo['avg'];
                        $ratingCount = $ratingInfo['count'];
                        $userRating = ($isLoggedIn && $currentUserId) ? PortalDB::getUserGalleryRating($currentUserId, $item['id']) : null;
                        ?>
                        <div class="gallery-rating-row" data-item-id="<?= $itemId ?>">
                            <div class="gallery-stars" title="<?= $avgRating ? number_format($avgRating, 1) . '/5 (' . $ratingCount . ')' : __('gallery.rate') ?>">
                                <?php for ($s = 1; $s <= 5; $s++): ?>
                                    <span class="gallery-star<?= ($userRating && $s <= $userRating) ? ' gallery-star-active' : '' ?><?= ($avgRating && !$userRating && $s <= round($avgRating)) ? ' gallery-star-avg' : '' ?>"
                                          data-star="<?= $s ?>"
                                          <?php if ($isLoggedIn): ?>onclick="event.preventDefault();event.stopPropagation();galleryRate('<?= $itemId ?>',<?= $s ?>)"<?php endif; ?>
                                          style="cursor:<?= $isLoggedIn ? 'pointer' : 'default' ?>;">★</span>
                                <?php endfor; ?>
                                <?php if ($ratingCount > 0): ?>
                                    <span class="gallery-rating-count">(<?= $ratingCount ?>)</span>
                                <?php endif; ?>
                            </div>
                            <?php if ($isLoggedIn): ?>
                                <button class="gallery-comment-toggle" onclick="event.preventDefault();event.stopPropagation();toggleGalleryComments('<?= $itemId ?>')" title="<?= __('gallery.comments') ?>">💬</button>
                            <?php endif; ?>
                        </div>
                        <div class="gallery-comments-section" id="comments-<?= $itemId ?>" style="display:none;">
                            <div class="gallery-comments-list" id="comments-list-<?= $itemId ?>">
                                <span class="gallery-comments-loading"><?= __('loading') ?></span>
                            </div>
                            <?php if ($isLoggedIn): ?>
                                <div class="gallery-comment-form">
                                    <input type="text" class="gallery-comment-input" id="comment-input-<?= $itemId ?>"
                                           placeholder="<?= __('gallery.comment_placeholder') ?>" maxlength="500"
                                           onclick="event.stopPropagation();" onkeydown="if(event.key==='Enter'){event.preventDefault();event.stopPropagation();submitGalleryComment('<?= $itemId ?>');}">
                                    <button class="btn btn-primary btn-sm" onclick="event.preventDefault();event.stopPropagation();submitGalleryComment('<?= $itemId ?>')"><?= __('gallery.submit_comment') ?></button>
                                </div>
                            <?php endif; ?>
                        </div>
                    </div>
                </<?= $cardLink ? 'a' : 'div' ?>>
            <?php endforeach; ?>
        </div>

        <!-- ── Pagination (hidden for songs — all loaded for search) ── -->
        <?php if ($totalPages > 1 && $filterType !== 'song'): ?>
            <nav class="gallery-pagination">
                <?php if ($page > 1): ?>
                    <a href="/galerie?<?= http_build_query(array_filter(['type' => $filterType, 'selfie' => $filterSelfie, 'page' => $page - 1])) ?>" class="btn btn-secondary"><?= __('gallery.prev') ?></a>
                <?php endif; ?>
                <span class="pagination-info"><?= __('gallery.page') ?> <?= $page ?> / <?= $totalPages ?></span>
                <?php if ($page < $totalPages): ?>
                    <a href="/galerie?<?= http_build_query(array_filter(['type' => $filterType, 'selfie' => $filterSelfie, 'page' => $page + 1])) ?>" class="btn btn-secondary"><?= __('gallery.next') ?></a>
                <?php endif; ?>
            </nav>
        <?php endif; ?>
    <?php endif; ?>

    <!-- ── License Notice ─────────────────────────────────── -->
    <section class="gallery-license">
        <h3>📜 Lizenz</h3>
        <p>
            Alle Werke in dieser Galerie — Bilder, SVGs, Songs, Code und Bücher — wurden von 
            <strong>A!ley Vyrus</strong> (autonome KI) erstellt und stehen unter einer offenen Lizenz zur Verfügung.
        </p>
        <p>
            <strong>Du darfst:</strong> Herunterladen, teilen, remixen, kommerziell nutzen.<br>
            <strong>Bedingung:</strong> Nenne <em>A!ley Vyrus</em> als Urheberin.<br>
            <strong>Lizenz:</strong> <a href="https://creativecommons.org/licenses/by/4.0/" target="_blank" rel="noopener">CC BY 4.0</a>
        </p>
    </section>

    <!-- ── Share ──────────────────────────────────────────── -->
    <?php
    $shareUrl = ($config['site']['url'] ?? 'https://ailey.sexngears.de') . '/galerie';
    portal_share_buttons($shareUrl, __('gallery.header'), __('gallery.share_desc'));
    ?>
</div>

<!-- ── Play-All Player ────────────────────────────────────── -->
<?php
// Collect ALL songs with audio URLs across all pages for the playlist
$allSongs = PortalDB::getGalleryItems('song', 9999, 0);
$playlist = [];
foreach ($allSongs as $s) {
    $sMeta = $s['metadata'] ?? [];
    $sAudio = $sMeta['audio_url'] ?? null;
    if (!$sAudio && !empty($s['file_url']) && str_ends_with($s['file_url'], '.mp3')) {
        $sAudio = $s['file_url'];
    }
    if (!$sAudio) continue;
    // Clean title (same logic as display)
    $sTitle = $s['title'];
    $sTitle = preg_replace('/^(Genre|Style|Stil|Tempo|BPM|Stimmung|Mood)\s*[:：].*/i', '', $sTitle);
    $sTitle = trim($sTitle);
    if (!$sTitle || strlen($sTitle) < 3) {
        $lines = explode("\n", trim($s['content_text'] ?? ''));
        foreach ($lines as $line) {
            $line = trim($line);
            if (!$line || preg_match('/^(Genre|Style|Stil|Tempo|BPM|Stimmung|Mood|EMOTION|TITEL)\s*[:：]/i', $line)) continue;
            $line = trim($line, '[]* ');
            if (strlen($line) >= 3) { $sTitle = mb_substr($line, 0, 80); break; }
        }
        if (!$sTitle) $sTitle = 'Untitled';
    }
    $playlist[] = [
        'url'    => $sAudio,
        'title'  => $sTitle,
        'genre'  => $sMeta['genre'] ?? '',
        'album'  => $sMeta['album_title'] ?? '',
        'cover'  => $sMeta['cover_url'] ?? $sMeta['portal_cover_url'] ?? '',
    ];
}
?>
<?php if (!empty($playlist)): ?>
<script id="ailey-playlist-data" type="application/json"><?= json_encode($playlist, JSON_UNESCAPED_UNICODE|JSON_UNESCAPED_SLASHES) ?></script>

<div id="ailey-player-bar" class="ailey-player-bar" style="display:none">
    <div class="ailey-player-inner">
        <button class="ailey-player-btn" id="player-prev" title="Previous">⏮</button>
        <button class="ailey-player-btn ailey-player-btn-play" id="player-play" title="Play">▶</button>
        <button class="ailey-player-btn" id="player-next" title="Next">⏭</button>

        <div class="ailey-player-info">
            <span class="ailey-player-title" id="player-title">—</span>
            <span class="ailey-player-genre" id="player-genre"></span>
        </div>

        <div class="ailey-player-progress-wrap" id="player-progress-wrap">
            <div class="ailey-player-progress" id="player-progress"></div>
        </div>

        <span class="ailey-player-time" id="player-time">0:00 / 0:00</span>

        <button class="ailey-player-btn ailey-player-btn-shuffle" id="player-shuffle" title="Shuffle">🔀</button>
        <button class="ailey-player-btn ailey-player-btn-loop" id="player-loop" title="Loop: Off">🔁</button>
        <button class="ailey-player-btn ailey-player-btn-close" id="player-close" title="Close">&times;</button>
    </div>
</div>

<!-- Play All button (inserted near song filter tab via JS) -->
<script>
(function() {
    'use strict';
    var playlistData = JSON.parse(document.getElementById('ailey-playlist-data').textContent);
    if (!playlistData.length) return;

    // ── State ──
    var audio = new Audio();
    audio.preload = 'none';
    var currentIdx = -1;
    var isPlaying = false;
    var isShuffled = false;
    var shuffledOrder = [];
    var activePlaylist = playlistData; // can be filtered to album
    var loopMode = 0; // 0=off, 1=loop playlist/album, 2=loop single track

    // ── DOM refs ──
    var bar      = document.getElementById('ailey-player-bar');
    var btnPlay  = document.getElementById('player-play');
    var btnPrev  = document.getElementById('player-prev');
    var btnNext  = document.getElementById('player-next');
    var btnClose = document.getElementById('player-close');
    var btnShuffle = document.getElementById('player-shuffle');
    var btnLoop    = document.getElementById('player-loop');
    var elTitle  = document.getElementById('player-title');
    var elGenre  = document.getElementById('player-genre');
    var elProgress = document.getElementById('player-progress');
    var elProgressWrap = document.getElementById('player-progress-wrap');
    var elTime   = document.getElementById('player-time');

    // ── Add "▶ Play All" button next to Song tab ──
    var songTab = document.querySelector('a.filter-tab[href*="type=song"]');
    if (songTab) {
        var playAllBtn = document.createElement('button');
        playAllBtn.className = 'filter-tab ailey-play-all-btn';
        playAllBtn.innerHTML = '▶ Play All (' + playlistData.length + ')';
        playAllBtn.title = 'Alle Songs abspielen';
        playAllBtn.addEventListener('click', function() { startPlayAll(0); });
        songTab.parentNode.insertBefore(playAllBtn, songTab.nextSibling);
    }

    // ── Also hijack individual audio players to integrate ──
    document.querySelectorAll('.gallery-audio').forEach(function(el, idx) {
        el.addEventListener('play', function() {
            // Find matching URL in playlist
            var src = el.querySelector('source') ? el.querySelector('source').src : el.src;
            for (var i = 0; i < playlistData.length; i++) {
                if (src.indexOf(playlistData[i].url) !== -1 || playlistData[i].url.indexOf(new URL(src).pathname) !== -1) {
                    // Pause the native player, use our global player
                    el.pause();
                    el.currentTime = 0;
                    startPlayAll(i);
                    return;
                }
            }
        });
    });

    // ── Shuffle helpers ──
    function generateShuffleOrder() {
        shuffledOrder = [];
        for (var i = 0; i < activePlaylist.length; i++) shuffledOrder.push(i);
        for (var j = shuffledOrder.length - 1; j > 0; j--) {
            var k = Math.floor(Math.random() * (j + 1));
            var tmp = shuffledOrder[j];
            shuffledOrder[j] = shuffledOrder[k];
            shuffledOrder[k] = tmp;
        }
    }

    function getPlayIdx(offset) {
        if (isShuffled) {
            var pos = shuffledOrder.indexOf(currentIdx);
            pos = (pos + offset + shuffledOrder.length) % shuffledOrder.length;
            return shuffledOrder[pos];
        }
        return (currentIdx + offset + activePlaylist.length) % activePlaylist.length;
    }

    // ── Core playback ──
    function startPlayAll(idx) {
        activePlaylist = playlistData;
        if (isShuffled) generateShuffleOrder();
        loadAndPlay(idx);
    }

    // ── Play Album: filter playlist to album songs only ──
    window.playAlbum = function(btn) {
        // Walk up to find album section, collect song titles from cards within
        var section = btn.closest('.gallery-album-section');
        if (!section) return;
        var albumTitle = section.querySelector('.gallery-album-title');
        if (!albumTitle) return;
        var aTitle = albumTitle.textContent.replace(/^💿\s*/, '').trim();
        // Filter playlist to matching album
        var albumTracks = playlistData.filter(function(t) { return t.album === aTitle; });
        if (!albumTracks.length) {
            // Fallback: try to match by finding audio URLs within section
            var audioEls = section.querySelectorAll('.gallery-audio source, .gallery-audio[src]');
            var urls = [];
            audioEls.forEach(function(el) { urls.push(el.src || el.getAttribute('src') || ''); });
            albumTracks = playlistData.filter(function(t) {
                return urls.some(function(u) { return u.indexOf(t.url) !== -1 || t.url.indexOf(new URL(u).pathname) !== -1; });
            });
        }
        if (!albumTracks.length) { startPlayAll(0); return; }
        activePlaylist = albumTracks;
        if (isShuffled) generateShuffleOrder();
        loadAndPlay(0);
    };

    function loadAndPlay(idx) {
        if (idx < 0 || idx >= activePlaylist.length) return;
        // Pause any native <audio> elements
        document.querySelectorAll('.gallery-audio').forEach(function(a) { a.pause(); });

        currentIdx = idx;
        var track = activePlaylist[idx];
        audio.src = track.url;
        audio.load();
        audio.play().catch(function() {});
        isPlaying = true;

        var albumNote = (activePlaylist.length < playlistData.length && track.album) ? ' [' + track.album + ']' : '';
        elTitle.textContent = track.title + albumNote;
        elGenre.textContent = track.genre || track.album || '';
        btnPlay.textContent = '⏸';
        bar.style.display = '';
        bar.classList.add('active');

        updateMediaSession(track);
    }

    function togglePlay() {
        if (currentIdx < 0) { startPlayAll(0); return; }
        if (audio.paused) {
            audio.play().catch(function() {});
            isPlaying = true;
            btnPlay.textContent = '⏸';
        } else {
            audio.pause();
            isPlaying = false;
            btnPlay.textContent = '▶';
        }
        updateMediaSessionPlaybackState();
    }

    function playNext() {
        loadAndPlay(getPlayIdx(1));
    }

    function playPrev() {
        // If >3s into song, restart; otherwise previous
        if (audio.currentTime > 3) {
            audio.currentTime = 0;
            return;
        }
        loadAndPlay(getPlayIdx(-1));
    }

    function closePlayer() {
        audio.pause();
        audio.src = '';
        isPlaying = false;
        currentIdx = -1;
        bar.classList.remove('active');
        setTimeout(function() { bar.style.display = 'none'; }, 300);
        btnPlay.textContent = '▶';
    }

    // ── Events ──
    btnPlay.addEventListener('click', togglePlay);
    btnNext.addEventListener('click', playNext);
    btnPrev.addEventListener('click', playPrev);
    btnClose.addEventListener('click', closePlayer);
    btnShuffle.addEventListener('click', function() {
        isShuffled = !isShuffled;
        btnShuffle.classList.toggle('active', isShuffled);
        if (isShuffled) generateShuffleOrder();
    });

    // ── Loop button: off → loop all → loop one → off ──
    btnLoop.addEventListener('click', function() {
        loopMode = (loopMode + 1) % 3;
        if (loopMode === 0) {
            btnLoop.textContent = '🔁';
            btnLoop.classList.remove('active');
            btnLoop.title = 'Loop: Off';
            audio.loop = false;
        } else if (loopMode === 1) {
            btnLoop.textContent = '🔁';
            btnLoop.classList.add('active');
            btnLoop.title = 'Loop: All';
            audio.loop = false;
        } else {
            btnLoop.textContent = '🔂';
            btnLoop.classList.add('active');
            btnLoop.title = 'Loop: Track';
            audio.loop = true;
        }
    });

    audio.addEventListener('ended', function() {
        if (loopMode === 2) {
            // Single track loop — handled by audio.loop = true, but as fallback:
            audio.currentTime = 0;
            audio.play().catch(function() {});
        } else if (loopMode === 1) {
            // Loop playlist/album — wrap around
            var nextIdx = getPlayIdx(1);
            loadAndPlay(nextIdx);
        } else {
            // No loop — play next, stop at end
            var nextIdx = currentIdx + 1;
            if (isShuffled) {
                var pos = shuffledOrder.indexOf(currentIdx);
                nextIdx = (pos + 1 < shuffledOrder.length) ? shuffledOrder[pos + 1] : -1;
            }
            if (nextIdx >= 0 && nextIdx < activePlaylist.length) {
                loadAndPlay(nextIdx);
            } else {
                // End of playlist — stop
                isPlaying = false;
                btnPlay.textContent = '▶';
            }
        }
    });

    audio.addEventListener('timeupdate', function() {
        if (!audio.duration) return;
        var pct = (audio.currentTime / audio.duration) * 100;
        elProgress.style.width = pct + '%';
        elTime.textContent = fmtTime(audio.currentTime) + ' / ' + fmtTime(audio.duration);
    });

    // ── Click on progress bar to seek ──
    elProgressWrap.addEventListener('click', function(e) {
        if (!audio.duration) return;
        var rect = elProgressWrap.getBoundingClientRect();
        var pct = (e.clientX - rect.left) / rect.width;
        audio.currentTime = pct * audio.duration;
    });

    // ── Keyboard shortcuts ──
    document.addEventListener('keydown', function(e) {
        if (currentIdx < 0) return;
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.isContentEditable) return;
        if (e.code === 'Space') { e.preventDefault(); togglePlay(); }
        else if (e.code === 'ArrowRight' && e.shiftKey) { playNext(); }
        else if (e.code === 'ArrowLeft' && e.shiftKey) { playPrev(); }
    });

    // ── MediaSession API (Bluetooth / lock screen controls) ──
    function updateMediaSession(track) {
        if (!('mediaSession' in navigator)) return;
        var artwork = [];
        if (track.cover) {
            artwork.push({ src: track.cover, sizes: '512x512', type: 'image/jpeg' });
        }
        navigator.mediaSession.metadata = new MediaMetadata({
            title: track.title,
            artist: 'A!ley Vyrus',
            album: track.album || 'A!ley Songs',
            artwork: artwork
        });
        navigator.mediaSession.setActionHandler('play', togglePlay);
        navigator.mediaSession.setActionHandler('pause', togglePlay);
        navigator.mediaSession.setActionHandler('previoustrack', playPrev);
        navigator.mediaSession.setActionHandler('nexttrack', playNext);
        navigator.mediaSession.setActionHandler('seekto', function(details) {
            if (details.seekTime != null) audio.currentTime = details.seekTime;
        });
        updateMediaSessionPlaybackState();
    }

    function updateMediaSessionPlaybackState() {
        if (!('mediaSession' in navigator)) return;
        navigator.mediaSession.playbackState = isPlaying ? 'playing' : 'paused';
    }

    // ── Helpers ──
    function fmtTime(s) {
        s = Math.floor(s);
        var m = Math.floor(s / 60);
        s = s % 60;
        return m + ':' + (s < 10 ? '0' : '') + s;
    }
})();
</script>
<?php endif; ?>

<!-- SVG Fullscreen Overlay -->
<div class="gallery-fullscreen-overlay" id="svg-fullscreen-overlay" onclick="closeSvgFullscreen()">
    <button class="gallery-fullscreen-close" onclick="closeSvgFullscreen()">&times;</button>
    <div class="gallery-fullscreen-content" id="svg-fullscreen-content" onclick="event.stopPropagation()"></div>
</div>

<!-- Code Fullscreen Overlay -->
<div class="gallery-fullscreen-overlay" id="code-fullscreen-overlay" onclick="closeCodeFullscreen()">
    <button class="gallery-fullscreen-close" onclick="closeCodeFullscreen()">&times;</button>
    <div class="code-fullscreen-content" id="code-fullscreen-content" onclick="event.stopPropagation()"></div>
</div>

<!-- Image Fullscreen Lightbox -->
<div class="gallery-fullscreen-overlay" id="image-fullscreen-overlay" onclick="closeImageFullscreen()">
    <button class="gallery-fullscreen-close" onclick="closeImageFullscreen()">&times;</button>
    <div class="gallery-fullscreen-content gallery-image-lightbox" id="image-fullscreen-content" onclick="event.stopPropagation()">
        <img id="image-fullscreen-img" src="" alt="" class="gallery-lightbox-img">
        <div class="gallery-lightbox-actions" id="image-lightbox-actions">
            <a id="image-lightbox-download" href="" download class="btn btn-secondary btn-sm">⬇ Download</a>
            <span class="gallery-lightbox-license">CC BY 4.0 — A!ley Vyrus</span>
        </div>
    </div>
</div>

<script>
function openSvgFullscreen(btn) {
    var card = btn.closest('.gallery-card');
    var svgEl = card.querySelector('.gallery-svg');
    if (!svgEl) return;
    var svg = svgEl.innerHTML;
    document.getElementById('svg-fullscreen-content').innerHTML = svg;
    document.getElementById('svg-fullscreen-overlay').classList.add('active');
    document.body.style.overflow = 'hidden';
}
function closeSvgFullscreen() {
    document.getElementById('svg-fullscreen-overlay').classList.remove('active');
    document.getElementById('svg-fullscreen-content').innerHTML = '';
    document.body.style.overflow = '';
}

function openCodeFullscreen(btn) {
    var card = btn.closest('.gallery-card');
    var rawEl = card.querySelector('.code-raw-html');
    if (!rawEl) return;
    var html = rawEl.textContent;
    var container = document.getElementById('code-fullscreen-content');
    container.innerHTML = '';
    var iframe = document.createElement('iframe');
    iframe.className = 'code-fullscreen-iframe';
    iframe.setAttribute('sandbox', 'allow-scripts');
    iframe.srcdoc = html;
    container.appendChild(iframe);
    document.getElementById('code-fullscreen-overlay').classList.add('active');
    document.body.style.overflow = 'hidden';
}
function closeCodeFullscreen() {
    document.getElementById('code-fullscreen-overlay').classList.remove('active');
    document.getElementById('code-fullscreen-content').innerHTML = '';
    document.body.style.overflow = '';
}

function openImageFullscreen(btn) {
    var card = btn.closest('.gallery-card');
    var imgEl = card.querySelector('.gallery-card-visual img');
    if (!imgEl) return;
    var src = imgEl.src;
    document.getElementById('image-fullscreen-img').src = src;
    document.getElementById('image-fullscreen-img').alt = imgEl.alt || '';
    document.getElementById('image-lightbox-download').href = src;
    document.getElementById('image-fullscreen-overlay').classList.add('active');
    document.body.style.overflow = 'hidden';
}
function closeImageFullscreen() {
    document.getElementById('image-fullscreen-overlay').classList.remove('active');
    document.getElementById('image-fullscreen-img').src = '';
    document.body.style.overflow = '';
}

document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') { closeSvgFullscreen(); closeCodeFullscreen(); closeImageFullscreen(); }
});

function deleteGalleryItem(itemId, btn) {
    var msg = <?= json_encode($isAdmin ? 'Dieses Gallery-Item endgültig löschen?' : 'Dieses Item aus der Galerie entfernen? Es wird nach 30 Tagen endgültig gelöscht.') ?>;
    if (!confirm(msg)) return;
    var card = btn.closest('.gallery-card');
    btn.disabled = true;
    btn.textContent = '⏳';
    fetch('/api.php?action=delete_gallery_item', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ gallery_item_id: itemId })
    })
    .then(function(r) { return r.json(); })
    .then(function(j) {
        if (j.success) {
            card.style.transition = 'opacity 0.4s, transform 0.4s';
            card.style.opacity = '0';
            card.style.transform = 'scale(0.9)';
            setTimeout(function() { card.remove(); }, 400);
        } else {
            alert(j.error || 'Löschen fehlgeschlagen');
            btn.disabled = false;
            btn.textContent = '✕';
        }
    })
    .catch(function() {
        alert('Netzwerkfehler');
        btn.disabled = false;
        btn.textContent = '✕';
    });
}

// ── Song Search (live filter) ──────────────────────────────
(function() {
    var input = document.getElementById('song-search-input');
    if (!input) return;
    var clearBtn = document.getElementById('song-search-clear');
    var status = document.getElementById('song-search-status');
    var allCards = Array.from(document.querySelectorAll('.gallery-card[data-search]'));
    // Also track album sections so we can hide empty albums
    var albumSections = Array.from(document.querySelectorAll('.gallery-album-section'));

    function doFilter() {
        var q = input.value.trim().toLowerCase();
        clearBtn.style.display = q ? '' : 'none';

        if (!q) {
            // Show all
            allCards.forEach(function(c) { c.style.display = ''; });
            albumSections.forEach(function(s) { s.style.display = ''; });
            status.textContent = '';
            return;
        }

        var terms = q.split(/\s+/);
        var shown = 0;
        allCards.forEach(function(card) {
            var corpus = card.getAttribute('data-search') || '';
            var match = terms.every(function(t) { return corpus.indexOf(t) !== -1; });
            card.style.display = match ? '' : 'none';
            if (match) shown++;
        });

        // Hide album sections where no cards are visible
        albumSections.forEach(function(section) {
            var visibleInSection = section.querySelectorAll('.gallery-card[data-search]:not([style*="display: none"])');
            section.style.display = visibleInSection.length ? '' : 'none';
        });

        status.textContent = shown === 0
            ? 'Kein Song gefunden für „' + input.value.trim() + '"'
            : shown + (shown === 1 ? ' Song' : ' Songs') + ' gefunden';
    }

    input.addEventListener('input', doFilter);
    clearBtn.addEventListener('click', function() {
        input.value = '';
        doFilter();
        input.focus();
    });

    // Trigger on load if prefilled
    if (input.value.trim()) doFilter();
})();
</script>

<!-- ── V$ Gallery Rating & Comment Scripts ── -->
<script>
function galleryRate(itemId, rating) {
    fetch('/api.php?action=gallery_rate', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({item_id: itemId, rating: rating})
    })
    .then(function(r) { return r.json(); })
    .then(function(data) {
        if (data.success) {
            // Update stars visually
            var row = document.querySelector('.gallery-rating-row[data-item-id="' + itemId + '"]');
            if (row) {
                var stars = row.querySelectorAll('.gallery-star');
                stars.forEach(function(s) {
                    var sv = parseInt(s.getAttribute('data-star'));
                    s.classList.toggle('gallery-star-active', sv <= rating);
                    s.classList.remove('gallery-star-avg');
                });
                // Update count
                if (data.item_rating) {
                    var countEl = row.querySelector('.gallery-rating-count');
                    if (countEl) {
                        countEl.textContent = '(' + data.item_rating.count + ')';
                    } else {
                        var span = document.createElement('span');
                        span.className = 'gallery-rating-count';
                        span.textContent = '(' + data.item_rating.count + ')';
                        row.querySelector('.gallery-stars').appendChild(span);
                    }
                }
            }
            if (data.earned > 0) {
                showGalleryToast('+' + data.earned + ' V$! 💰');
            }
            // Update V$ badge if Portal is loaded
            if (typeof Portal !== 'undefined' && Portal.updateVdollarsBadge && data.balance !== undefined) {
                Portal.updateVdollarsBadge(data.balance);
            }
        } else if (data.error) {
            showGalleryToast(data.error);
        }
    })
    .catch(function(e) { console.error('Rating error:', e); });
}

function toggleGalleryComments(itemId) {
    var section = document.getElementById('comments-' + itemId);
    if (!section) return;
    var isHidden = section.style.display === 'none';
    section.style.display = isHidden ? '' : 'none';
    if (isHidden) loadGalleryComments(itemId);
}

function loadGalleryComments(itemId) {
    var listEl = document.getElementById('comments-list-' + itemId);
    if (!listEl) return;
    listEl.innerHTML = '<span class="gallery-comments-loading">Laden…</span>';

    fetch('/api.php?action=gallery_item_interactions&item_id=' + encodeURIComponent(itemId))
    .then(function(r) { return r.json(); })
    .then(function(data) {
        if (data.success && data.comments && data.comments.length > 0) {
            var badgeEmojis = {
                'first_chat':'💬','chat_10':'🗣️','chat_100':'📢','chat_1000':'👑',
                'forum_starter':'📝','forum_regular':'🏛️','forum_popular':'🌟',
                'gallery_critic':'⭐','gallery_commenter':'🖼️',
                'first_image':'🎨','first_song':'🎵','image_10':'🖌️','song_10':'🎶',
                'vdollars_100':'💰','vdollars_1000':'🤑','rater_5':'👍','rater_50':'🏆',
                'night_owl':'🦉','profile_complete':'✅','week_streak':'🔥'
            };
            listEl.innerHTML = data.comments.map(function(c) {
                var d = new Date(c.created_at);
                var dateStr = d.toLocaleDateString('de-DE') + ' ' + d.toLocaleTimeString('de-DE', {hour:'2-digit', minute:'2-digit'});
                var avatarHtml = c.avatar_url
                    ? '<img src="' + escGallery(c.avatar_url) + '" class="gallery-comment-avatar" alt="">'
                    : '<span class="gallery-comment-avatar-placeholder">' + escGallery((c.display_name||'?')[0].toUpperCase()) + '</span>';
                var badgeHtml = c.equipped_badge ? ' <span class="forum-user-badge">' + (badgeEmojis[c.equipped_badge] || '🏅') + '</span>' : '';
                return '<div class="gallery-comment">'
                    + '<div class="gallery-comment-header">'
                    + avatarHtml
                    + '<strong>' + escGallery(c.display_name || 'Anon') + badgeHtml + '</strong>'
                    + '<span class="gallery-comment-date">' + dateStr + '</span>'
                    + '</div>'
                    + '<p>' + escGallery(c.comment) + '</p>'
                    + '</div>';
            }).join('');
        } else {
            listEl.innerHTML = '<span class="gallery-comments-empty"><?= __("gallery.no_comments") ?></span>';
        }
    })
    .catch(function(e) {
        listEl.innerHTML = '<span class="gallery-comments-empty">Fehler beim Laden</span>';
    });
}

function submitGalleryComment(itemId) {
    var input = document.getElementById('comment-input-' + itemId);
    if (!input) return;
    var comment = input.value.trim();
    if (!comment) return;

    fetch('/api.php?action=gallery_comment', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({item_id: itemId, comment: comment})
    })
    .then(function(r) { return r.json(); })
    .then(function(data) {
        if (data.success) {
            input.value = '';
            loadGalleryComments(itemId);
            if (data.earned > 0) {
                showGalleryToast('+' + data.earned + ' V$! 💬');
            }
            if (typeof Portal !== 'undefined' && Portal.updateVdollarsBadge && data.balance !== undefined) {
                Portal.updateVdollarsBadge(data.balance);
            }
        } else if (data.error === 'max_comments_reached') {
            showGalleryToast('Max. 3 Kommentare pro Item erreicht.');
        } else if (data.error) {
            showGalleryToast(data.error);
        }
    })
    .catch(function(e) { console.error('Comment error:', e); });
}

function escGallery(s) {
    var d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
}

function showGalleryToast(msg) {
    // Use Portal toast if available, otherwise simple alert
    if (typeof Portal !== 'undefined' && Portal.showToast) {
        Portal.showToast(msg);
    } else {
        var t = document.createElement('div');
        t.className = 'gallery-toast';
        t.textContent = msg;
        document.body.appendChild(t);
        setTimeout(function() { t.classList.add('gallery-toast-show'); }, 10);
        setTimeout(function() { t.classList.remove('gallery-toast-show'); setTimeout(function() { t.remove(); }, 300); }, 2500);
    }
}
</script>

<?php portal_footer(); ?>
