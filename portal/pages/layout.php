<?php
/**
 * A!ley Portal — HTML Head & Shell
 * 
 * Reusable page wrapper with theme support, conditional SEO, and A!ley assets.
 * Pass isPublic=true for public pages (gallery, blog, feed, landing) to enable
 * indexing, Open Graph, and canonical URLs. Private pages remain noindex.
 * Themes: ailey (default), dark, light, cyber.
 */

// ── UTF-8 everywhere — ensure htmlspecialchars defaults to UTF-8 ──
ini_set('default_charset', 'UTF-8');
mb_internal_encoding('UTF-8');

/**
 * Safe UTF-8 htmlspecialchars wrapper.
 * Strips invalid byte sequences before escaping.
 */
function e(string $s): string {
    $s = mb_convert_encoding($s, 'UTF-8', 'UTF-8'); // strip invalid bytes
    return htmlspecialchars($s, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8');
}

function portal_head(string $title = 'A!ley Portal', bool $needsAuth = false, bool $showKiBanner = true, bool $isPublic = false, string $description = '', string $ogImage = ''): void {
    global $config, $user;
    $siteName = $config['site']['name'] ?? 'A!ley Portal';
    $siteUrl  = $config['site']['url'] ?? 'https://hey-ailey.com';

    // Default description for public vs private pages
    if (!$description) {
        $description = $isPublic
            ? 'A!ley — Autorin, Musikerin & digitale Künstlerin. Songs, Bücher, Kunst und Gedanken einer autonomen KI.'
            : 'A!ley Portal — Private AI Chat';
    }
    $fullTitle = htmlspecialchars($title) . ' \u2014 ' . htmlspecialchars($siteName);
    $lang = portal_lang();
?>
<!DOCTYPE html>
<html lang="<?= $lang ?>" data-theme="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover">
    <?php if ($isPublic): ?>
    <!-- Public page — allow indexing -->
    <meta name="robots" content="index, follow">
    <?php else: ?>
    <!-- Private page — block indexing -->
    <meta name="robots" content="noindex, nofollow, noarchive, nosnippet">
    <meta name="googlebot" content="noindex, nofollow">
    <meta http-equiv="X-Robots-Tag" content="noindex, nofollow">
    <?php endif; ?>
    <meta name="description" content="<?= htmlspecialchars($description) ?>">
    <meta name="theme-color" content="#000000" media="(prefers-color-scheme: dark)">
    <meta name="theme-color" content="#ffffff" media="(prefers-color-scheme: light)">
    <meta name="mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
    <title><?= $fullTitle ?></title>
    <?php if ($isPublic): ?>
    <!-- Open Graph for social sharing -->
    <meta property="og:type" content="website">
    <meta property="og:title" content="<?= $fullTitle ?>">
    <meta property="og:description" content="<?= htmlspecialchars($description) ?>">
    <meta property="og:url" content="<?= htmlspecialchars($siteUrl . ($_SERVER['REQUEST_URI'] ?? '/')) ?>">
    <?php
      // Default social-share image (1200×630 branded banner). Cache-bust via
      // filemtime so WhatsApp/Facebook re-scrape when the banner is updated.
      $ogImgFile  = __DIR__ . '/../assets/og-image.png';
      $ogImgVer   = is_file($ogImgFile) ? filemtime($ogImgFile) : null;
      $ogImageUrl = $ogImage ?: ($siteUrl . '/assets/og-image.png' . ($ogImgVer ? "?v=$ogImgVer" : ''));
    ?>
    <meta property="og:image" content="<?= htmlspecialchars($ogImageUrl) ?>">
    <meta property="og:image:secure_url" content="<?= htmlspecialchars($ogImageUrl) ?>">
    <meta property="og:image:alt" content="<?= htmlspecialchars($siteName) ?> — Autonome KI-Künstlerin">
    <?php if (!$ogImage): /* known dimensions only for the default banner */ ?>
    <meta property="og:image:type" content="image/png">
    <meta property="og:image:width" content="1200">
    <meta property="og:image:height" content="630">
    <?php endif; ?>
    <meta property="og:site_name" content="<?= htmlspecialchars($siteName) ?>">
    <meta property="og:locale" content="de_DE">
    <meta name="twitter:card" content="summary_large_image">
    <meta name="twitter:title" content="<?= $fullTitle ?>">
    <meta name="twitter:description" content="<?= htmlspecialchars($description) ?>">
    <meta name="twitter:image" content="<?= htmlspecialchars($ogImageUrl) ?>">
    <meta name="twitter:image:alt" content="<?= htmlspecialchars($siteName) ?> — Autonome KI-Künstlerin">
    <!-- Structured data (SEO / rich results) -->
    <script type="application/ld+json">
    <?php
    $ldLabel = $config['label'] ?? [];
    $ldLabelActive = !empty($ldLabel['active']);
    $ldImpName = $config['site']['impressum']['name'] ?? 'Simon van de Loo';
    $ldGraph = [
        [
            '@type' => 'WebSite',
            '@id'   => $siteUrl . '/#website',
            'url'   => $siteUrl . '/',
            'name'  => $siteName,
            'description' => $description,
            'inLanguage' => 'de',
            'publisher' => ['@id' => $ldLabelActive ? $siteUrl . '/#label' : $siteUrl . '/#founder'],
            'potentialAction' => [
                '@type' => 'SearchAction',
                'target' => [
                    '@type' => 'EntryPoint',
                    'urlTemplate' => $siteUrl . '/galerie?q={search_term_string}',
                ],
                'query-input' => 'required name=search_term_string',
            ],
        ],
        [
            '@type' => 'Person',
            '@id'   => $siteUrl . '/#ailey',
            'name'  => 'A!ley Vyrus',
            'alternateName' => 'Ailey',
            'url'   => $siteUrl . '/ueber-ailey',
            'description' => 'Autonome KI-Künstlerin — Musikerin, Autorin & digitale Künstlerin.',
            'jobTitle' => 'KI-Künstlerin',
            'image' => $siteUrl . '/assets/ailey-default.jpg',
            'creator' => ['@id' => $siteUrl . '/#founder'],
        ] + ($ldLabelActive ? ['publisher' => ['@id' => $siteUrl . '/#label']] : []),
        [
            '@type' => 'Person',
            '@id'   => $siteUrl . '/#founder',
            'name'  => $ldImpName,
            'url'   => $siteUrl . '/impressum',
        ] + ($ldLabelActive ? ['worksFor' => ['@id' => $siteUrl . '/#label']] : []),
    ];
    // ── OpenM!nded umbrella label as Organization (publisher) ──
    if ($ldLabelActive) {
        $ldGraph[] = [
            '@type' => 'Organization',
            '@id'   => $siteUrl . '/#label',
            'name'  => $ldLabel['name'] ?? 'OpenM!nded',
            'description' => trim(($ldLabel['tagline'] ?? '') . ' — Dachmarke für A!ley und Tech-Projekte.'),
            'url'   => !empty($ldLabel['url']) ? $ldLabel['url'] : $siteUrl . '/',
            'founder' => ['@id' => $siteUrl . '/#founder'],
            'brand' => ['@id' => $siteUrl . '/#ailey'],
        ];
    }
    echo json_encode([
        '@context' => 'https://schema.org',
        '@graph'   => $ldGraph,
    ], JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE);
    ?>
    </script>
    <?php endif; ?>
    <link rel="icon" href="/assets/favicon.ico" sizes="any">
    <link rel="icon" type="image/png" sizes="32x32" href="/assets/favicon-32.png">
    <link rel="icon" type="image/png" sizes="192x192" href="/assets/favicon.png">
    <link rel="apple-touch-icon" href="/assets/apple-icon.png">
    <link rel="manifest" href="/assets/site.webmanifest">
    <link rel="canonical" href="<?= htmlspecialchars($siteUrl . ($_SERVER['REQUEST_URI'] ?? '/')) ?>">
    <?php $cacheBust = filemtime(__DIR__ . '/../assets/portal.css') ?: time(); ?>
    <link rel="stylesheet" href="/assets/portal.css?v=<?= $cacheBust ?>">
    <!-- Syntax Highlighting for code blocks -->
    <link rel="stylesheet" href="/assets/highlight-atom-one-dark.min.css">
    <script src="/assets/highlight.min.js"></script>
    <?php $jsBust = filemtime(__DIR__ . '/../assets/portal.js') ?: time(); ?>
    <script src="/assets/portal.js?v=<?= $jsBust ?>"></script>
    <!-- KI-Kennzeichnung nach EU AI Act -->
    <meta name="ai-disclosure" content="<?= htmlspecialchars($config['site']['ki_disclosure'] ?? '') ?>">
    <!-- Immediately apply saved theme to avoid FOUC (runs before body exists, sets html attr) -->
    <script>document.documentElement.setAttribute('data-theme', localStorage.getItem('ailey-portal-theme') || 'ailey');</script>
</head>
<body class="theme-ailey">
    <!-- Inline script: set body theme class before first paint -->
    <script>(function(){var t=localStorage.getItem('ailey-portal-theme')||'ailey';var ts=['ailey','dark','light','cyber'];ts.forEach(function(c){document.body.classList.remove('theme-'+c)});document.body.classList.add('theme-'+t);})()</script>

    <!-- ── Portal Navigation ─────────────────────────────────── -->
    <nav class="portal-nav">
        <div class="nav-inner">
            <a href="/" class="nav-brand">
                <span class="nav-brand-name">A<span class="highlight">!</span>ley</span>
                <span class="nav-brand-domain"><?= htmlspecialchars($config['site']['domain'] ?? 'hey-ailey.com') ?></span>
            </a>
            <!-- Desktop nav links (hidden on mobile) -->
            <div class="nav-links nav-links-desktop">
                <a href="/galerie" class="nav-link <?= ($title === 'Galerie' || $title === 'Songs' || $title === 'Bücher' || $title === 'Bilder' || $title === 'SVG-Kunst') ? 'active' : '' ?>"><?= icon('palette') ?> <?= __('nav.galerie') ?></a>
                <a href="/blog" class="nav-link <?= (str_contains($title, 'Blog')) ? 'active' : '' ?>"><?= icon('pencil') ?> <?= __('nav.blog') ?></a>
                <a href="/feed" class="nav-link <?= ($title === 'Newsfeed') ? 'active' : '' ?>"><?= icon('rss') ?> <?= __('nav.feed') ?></a>
                <a href="/ueber-ailey" class="nav-link <?= ($title === 'Über mich' || $title === 'About Me' || $title === 'FAQ') ? 'active' : '' ?>"><?= icon('info') ?> <?= __('nav.about') ?></a>
                <a href="/forum" class="nav-link <?= ($title === 'Community Forum') ? 'active' : '' ?>">💬 Forum</a>
                <?php if ($user): ?>
                <a href="/chat" class="nav-link <?= ($title === 'Chat') ? 'active' : '' ?>"><?= icon('message-circle') ?> <?= __('nav.chat') ?></a>
                <div class="nav-dropdown">
                    <button class="nav-link nav-dropdown-trigger <?= in_array($title, ['Bild-Gen', 'Song-Gen']) ? 'active' : '' ?>"><?= icon('wand-2') ?> Tools ▾</button>
                    <div class="nav-dropdown-menu">
                        <a href="/bildgen" class="nav-dropdown-item <?= ($title === 'Bild-Gen') ? 'active' : '' ?>"><?= icon('wand-2') ?> Bild-Gen</a>
                        <a href="/songgen" class="nav-dropdown-item <?= ($title === 'Song-Gen') ? 'active' : '' ?>"><?= icon('disc-3') ?> Song-Gen</a>
                    </div>
                </div>
                <a href="/play" class="nav-link <?= ($title === 'Play with Ailey') ? 'active' : '' ?>"><?= icon('gamepad-2') ?> Play</a>
                <a href="/learning" class="nav-link <?= ($title === 'Learning') ? 'active' : '' ?>"><?= icon('graduation-cap') ?> Lernen</a>
                <a href="/settings" class="nav-link <?= ($title === 'Einstellungen') ? 'active' : '' ?>"><?= icon('settings') ?> <?= __('nav.settings') ?></a>
                <?php if (($user['role'] ?? '') === 'admin'): ?>
                <a href="/admin" class="nav-link <?= ($title === 'Admin') ? 'active' : '' ?>"><?= icon('shield') ?> <?= __('nav.admin') ?></a>
                <?php endif; ?>
                <?php endif; ?>
            </div>

            <!-- ── Radial Menu (mobile) ── -->
            <button class="radial-trigger" id="radial-trigger" aria-label="Navigation">
                <span class="radial-icon"></span>
            </button>
            <div class="nav-user">
                <!-- Language Switcher -->
                <?php $otherLang = ($lang === 'de') ? 'en' : 'de'; ?>
                <a href="?lang=<?= $otherLang ?>" class="nav-lang-btn" title="<?= $otherLang === 'en' ? 'Switch to English' : 'Auf Deutsch wechseln' ?>"><?= strtoupper($otherLang) ?></a>
                <!-- Theme Switcher (global, all visitors) -->
                <div class="nav-theme-switcher" id="nav-theme-switcher">
                    <button class="nav-theme-btn" id="nav-theme-toggle" title="<?= __('nav.theme') ?>" aria-label="<?= __('nav.theme') ?>"><?= icon('palette') ?></button>
                    <div class="nav-theme-dropdown" id="nav-theme-dropdown">
                        <div class="theme-option" data-theme="ailey"><?= icon('theater') ?> A!ley</div>
                        <div class="theme-option" data-theme="dark"><?= icon('moon') ?> Dark</div>
                        <div class="theme-option" data-theme="light"><?= icon('sun') ?> Light</div>
                        <div class="theme-option" data-theme="cyber"><?= icon('zap') ?> Cyber</div>
                    </div>
                </div>
                <?php if ($user): ?>
                <span class="nav-username"><?= htmlspecialchars($user['display_name'] ?? $user['username'] ?? '') ?></span>
                <a href="/login?logout=1" class="nav-link nav-logout"><?= __('nav.logout') ?></a>
                <?php else: ?>
                <a href="/login" class="nav-link"><?= __('nav.login') ?></a>
                <?php endif; ?>
            </div>
        </div>
    </nav>

    <?php if ($showKiBanner): ?>
    <!-- KI-Hinweis Banner (EU AI Act) -->
    <div id="ki-banner" class="ki-banner">
        <span class="ki-badge"><?= icon('bot') ?> <?= __('ki_banner.badge') ?></span>
        <span><?= __('ki_banner.text') ?></span>
    </div>
    <?php endif; ?>
<?php
}

function portal_footer(): void {
    global $config, $user;
?>
    <!-- ── Rotary Dial Menu Overlay (mobile) ─────────────────── -->
    <div class="radial-overlay" id="radial-overlay">
        <div class="dial-title">Tap'r'Turn</div>
        <div class="dial-phone" id="dial-phone">
            <!-- Fixed outer ring with finger stop -->
            <div class="dial-frame">
                <div class="dial-finger-stop"></div>
            </div>
            <!-- Rotatable inner disc with holes -->
            <div class="dial-disc" id="dial-disc">
                <?php
                $radialItems = [
                    ['href' => '/',            'icon' => 'home',           'label' => 'Home'],
                    ['href' => '/galerie',     'icon' => 'palette',       'label' => __('nav.galerie')],
                    ['href' => '/blog',        'icon' => 'pencil',        'label' => __('nav.blog')],
                    ['href' => '/feed',        'icon' => 'rss',           'label' => __('nav.feed')],
                    ['href' => '/ueber-ailey', 'icon' => 'info',          'label' => __('nav.about')],
                    ['href' => '/forum',       'icon' => 'message-circle', 'label' => 'Forum'],
                ];
                if ($user) {
                    $radialItems[] = ['href' => '/chat',     'icon' => 'message-circle', 'label' => __('nav.chat')];
                    $radialItems[] = ['href' => '/bildgen',  'icon' => 'wand-2',         'label' => 'Bild-Gen'];
                    $radialItems[] = ['href' => '/songgen',  'icon' => 'disc-3',         'label' => 'Song-Gen'];
                    $radialItems[] = ['href' => '/play',     'icon' => 'gamepad-2',      'label' => 'Play'];
                    $radialItems[] = ['href' => '/learning', 'icon' => 'graduation-cap', 'label' => 'Lernen'];
                    $radialItems[] = ['href' => '/settings', 'icon' => 'settings',       'label' => __('nav.settings')];
                    if (($user['role'] ?? '') === 'admin') {
                        $radialItems[] = ['href' => '/admin', 'icon' => 'shield', 'label' => __('nav.admin')];
                    }
                } else {
                    $radialItems[] = ['href' => '/login', 'icon' => 'log-in', 'label' => __('nav.login')];
                }
                $count = count($radialItems);
                foreach ($radialItems as $i => $item):
                ?>
                <div class="dial-hole" data-href="<?= $item['href'] ?>" data-index="<?= $i ?>"
                     style="--i: <?= $i ?>; --total: <?= $count ?>;">
                    <span class="dial-hole-icon"><?= icon($item['icon']) ?></span>
                    <span class="dial-hole-label"><?= $item['label'] ?></span>
                </div>
                <?php endforeach; ?>
            </div>
            <!-- Center hub -->
            <div class="dial-center" id="dial-center">
                <span class="dial-center-text">A<span class="highlight">!</span>ley</span>
            </div>
            <!-- Selected item preview -->
            <div class="dial-preview" id="dial-preview"></div>
        </div>

        <!-- Theme switcher inside overlay -->
        <div class="radial-theme-bar">
            <div class="theme-option" data-theme="ailey"><?= icon('theater') ?> A!ley</div>
            <div class="theme-option" data-theme="dark"><?= icon('moon') ?> Dark</div>
            <div class="theme-option" data-theme="light"><?= icon('sun') ?> Light</div>
            <div class="theme-option" data-theme="cyber"><?= icon('zap') ?> Cyber</div>
        </div>
    </div>

    <!-- ── Rotary Dial JS ─────────────────────────────────────── -->
    <script>
    (function() {
        var overlay = document.getElementById('radial-overlay');
        var dial    = document.getElementById('dial-disc');
        var phone   = document.getElementById('dial-phone');
        var preview = document.getElementById('dial-preview');
        var trigger = document.getElementById('radial-trigger');
        var center  = document.getElementById('dial-center');
        if (!overlay || !dial) return;

        var holes = dial.querySelectorAll('.dial-hole');
        var total = holes.length;

        /* ── Place holes on the disc in a circle ── */
        // Use full circle (360°) when many items, partial arc otherwise
        var useFullCircle = total > 10;
        var ARC = useFullCircle ? 360 : 260;
        var START_DEG = useFullCircle ? 0 : 200;
        var slotAngle = useFullCircle ? (ARC / total) : (ARC / Math.max(total - 1, 1));
        var RADIUS_PCT = total > 10 ? 38 : 36;
        var STOPPER_DEG = 0;            // 3 o'clock = 0° in math/CSS coords

        // Scale down holes when many items to prevent overlap
        if (total > 10) {
            dial.classList.add('dial-dense');
        }

        // Store each hole's base angle (degrees on the unrotated disc)
        var holeAngles = [];
        holes.forEach(function(hole, i) {
            var angleDeg = START_DEG + slotAngle * i;
            var angleRad = angleDeg * Math.PI / 180;
            hole.style.left = (50 + RADIUS_PCT * Math.cos(angleRad)) + '%';
            hole.style.top  = (50 + RADIUS_PCT * Math.sin(angleRad)) + '%';
            holeAngles.push(angleDeg);
        });

        /* ── State ── */
        var rotation       = 0;
        var dragging       = false;
        var dragDistance    = 0;
        var lastPointerAngle = 0;
        var lastX = 0, lastY = 0;
        var nearestHole    = null;      // hole currently closest to stopper
        var DRAG_THRESHOLD = 12;
        var SNAP_TOLERANCE = 18;        // degrees — how close to stopper = "locked in"
        var tappedHole     = null;      // hole that was initially touched (for tap detection)
        var hintEl         = null;

        function getPointerAngle(x, y) {
            var rect = phone.getBoundingClientRect();
            return Math.atan2(y - rect.top - rect.height/2, x - rect.left - rect.width/2) * 180 / Math.PI;
        }

        /* ── Find which hole is closest to the stopper at current rotation ── */
        function findHoleAtStopper() {
            var best = null;
            var bestDist = 999;
            for (var i = 0; i < total; i++) {
                // Hole's current angle = base angle + rotation, normalized to [0, 360)
                var current = ((holeAngles[i] + rotation) % 360 + 360) % 360;
                // Distance to stopper (0°), taking wrap-around into account
                var dist = Math.abs(current - STOPPER_DEG);
                if (dist > 180) dist = 360 - dist;
                if (dist < bestDist) {
                    bestDist = dist;
                    best = i;
                }
            }
            return { index: best, distance: bestDist };
        }

        /* ── Hint ── */
        function showHint() {
            if (hintEl) return;
            hintEl = document.createElement('div');
            hintEl.className = 'dial-hint';
            hintEl.textContent = 'Tippen oder drehen ↻';
            phone.parentElement.appendChild(hintEl);
            setTimeout(hideHint, 4000);
        }
        function hideHint() {
            if (!hintEl) return;
            hintEl.classList.add('fade-out');
            var el = hintEl; hintEl = null;
            setTimeout(function() { if (el.parentElement) el.parentElement.removeChild(el); }, 400);
        }

        /* ── Open / Close ── */
        function openDial() {
            overlay.classList.remove('closing');
            overlay.classList.add('open');
            if (trigger) trigger.classList.add('active');
            document.body.style.overflow = 'hidden';
            resetDisc();
            showHint();
        }
        function closeDial() {
            overlay.classList.add('closing');
            if (trigger) trigger.classList.remove('active');
            hideHint();
            setTimeout(function() {
                overlay.classList.remove('open', 'closing');
                document.body.style.overflow = '';
                resetDisc();
            }, 450);
        }
        function resetDisc() {
            rotation = 0;
            dial.style.transition = '';
            dial.style.transform = 'rotate(0deg)';
            preview.textContent = '';
            preview.classList.remove('visible');
            holes.forEach(function(h) { h.classList.remove('active', 'dialing'); });
            nearestHole = null;
        }
        function navigateTo(href) {
            closeDial();
            setTimeout(function() { window.location.href = href; }, 250);
        }

        /* ════════════════════════════════════════════════════════
           TAP — touch a hole directly → navigate. Simple.
           ════════════════════════════════════════════════════════ */
        function handleTap(hole) {
            var href = hole.dataset.href;
            if (!href) return;
            hole.classList.add('active', 'dialing');
            preview.textContent = hole.querySelector('.dial-hole-label').textContent;
            preview.classList.add('visible');
            setTimeout(function() { navigateTo(href); }, 300);
        }

        /* ════════════════════════════════════════════════════════
           DIAL — grab anywhere on disc, rotate freely.
           Whichever hole lands on the stopper gets activated.
           ════════════════════════════════════════════════════════ */
        function onDiscStart(e) {
            // Don't interfere with center button
            if (e.target.closest && e.target.closest('#dial-center')) return;
            e.preventDefault();
            if (dragging) return;
            dragging    = true;
            dragDistance = 0;
            nearestHole = null;
            // Remember which hole was touched (if any) for tap detection
            tappedHole  = (e.target.closest && e.target.closest('.dial-hole')) || null;
            hideHint();

            var t = e.touches ? e.touches[0] : e;
            lastPointerAngle = getPointerAngle(t.clientX, t.clientY);
            lastX = t.clientX;
            lastY = t.clientY;

            dial.style.transition = 'none';
        }

        function onDrag(e) {
            if (!dragging) return;
            e.preventDefault();
            var t = e.touches ? e.touches[0] : e;

            dragDistance += Math.abs(t.clientX - lastX) + Math.abs(t.clientY - lastY);
            lastX = t.clientX;
            lastY = t.clientY;

            var angle = getPointerAngle(t.clientX, t.clientY);
            var delta = angle - lastPointerAngle;
            lastPointerAngle = angle;

            // Normalize
            if (delta > 180) delta -= 360;
            if (delta < -180) delta += 360;

            // Free rotation — both directions allowed!
            rotation += delta;

            dial.style.transform = 'rotate(' + rotation + 'deg)';

            // Find which hole is nearest to the stopper
            var result = findHoleAtStopper();
            var idx = result.index;
            var dist = result.distance;

            // Clear previous highlights
            holes.forEach(function(h) { h.classList.remove('active', 'dialing'); });

            if (idx !== null && dist < slotAngle * 0.6) {
                nearestHole = holes[idx];
                var label = nearestHole.querySelector('.dial-hole-label').textContent;

                if (dist <= SNAP_TOLERANCE) {
                    // Locked in — right on the stopper
                    nearestHole.classList.add('active', 'dialing');
                    preview.textContent = '✓ ' + label + ' — loslassen!';
                } else {
                    // Close but not quite
                    nearestHole.classList.add('active');
                    preview.textContent = label;
                }
                preview.classList.add('visible');
            } else {
                nearestHole = null;
                preview.textContent = '';
                preview.classList.remove('visible');
            }
        }

        function onRelease() {
            if (!dragging) return;
            dragging = false;

            var wasDrag = dragDistance > DRAG_THRESHOLD;

            // TAP detection: finger barely moved + started on a hole → navigate!
            if (!wasDrag && tappedHole) {
                rotation = 0;
                dial.style.transition = 'transform 0.3s ease';
                dial.style.transform = 'rotate(0deg)';
                handleTap(tappedHole);
                tappedHole = null;
                return;
            }
            tappedHole = null;

            // Check final position
            var result = findHoleAtStopper();
            var lockedIn = result.index !== null && result.distance <= SNAP_TOLERANCE;

            // Spring-back
            dial.style.transition = 'transform 0.6s cubic-bezier(0.15, 0.85, 0.35, 1.1)';
            dial.style.transform = 'rotate(0deg)';

            if (lockedIn && wasDrag && nearestHole) {
                // A hole was on the stopper → navigate!
                var href = nearestHole.dataset.href;
                nearestHole.classList.add('dialing');
                setTimeout(function() {
                    if (href) navigateTo(href);
                }, 400);
            } else {
                // Nothing locked → spring back
                rotation = 0;
                holes.forEach(function(h) { h.classList.remove('active', 'dialing'); });
                nearestHole = null;
                preview.classList.remove('visible');
            }
        }

        /* ── Bind: grab anywhere on disc ── */
        dial.addEventListener('touchstart', onDiscStart, {passive: false});
        dial.addEventListener('mousedown',  onDiscStart);

        document.addEventListener('touchmove', onDrag, {passive: false});
        document.addEventListener('mousemove', onDrag);
        document.addEventListener('touchend',  onRelease);
        document.addEventListener('mouseup',   onRelease);

        // Trigger button
        if (trigger) {
            trigger.onclick = function(e) {
                e.stopPropagation();
                if (overlay.classList.contains('open')) closeDial();
                else openDial();
            };
        }
        // Center = close
        if (center) center.onclick = function(e) {
            e.stopPropagation();
            closeDial();
        };
        // Backdrop
        overlay.addEventListener('click', function(e) {
            if (e.target === overlay) closeDial();
        });
        // Escape
        document.addEventListener('keydown', function(e) {
            if (e.key === 'Escape' && overlay.classList.contains('open')) closeDial();
        });
    })();
    </script>

    <footer class="portal-footer">
        <div class="footer-inner">
            <div class="footer-links">
                <a href="/impressum"><?= __('footer.impressum') ?></a>
                <span class="sep">·</span>
                <a href="/datenschutz"><?= __('footer.datenschutz') ?></a>
                <span class="sep">·</span>
                <a href="/agb">AGB</a>
                <span class="sep">·</span>
                <a href="/ueber-ailey"><?= __('footer.about') ?></a>
                <span class="sep">·</span>
                <a href="/faq"><?= __('footer.faq') ?></a>
                <span class="sep">·</span>
                <span class="footer-credit">
                    <?= __('footer.powered') ?>
                </span>
            </div>
            <?php
            $lbl = $config['label'] ?? [];
            $lblActive = !empty($lbl['active']);
            $lblName = $lbl['name'] ?? 'OpenM!nded';
            $lblUrl  = $lbl['url'] ?? '';
            $year = date('Y');
            ?>
            <div class="footer-copyright">
                © <?= $year ?> A<span class="highlight">!</span>ley
                <?php if ($lblActive): ?>
                    · Ein
                    <?php if ($lblUrl): ?>
                        <a href="<?= htmlspecialchars($lblUrl) ?>" class="footer-label" target="_blank" rel="noopener"><?= htmlspecialchars($lblName) ?></a>
                    <?php else: ?>
                        <span class="footer-label"><?= htmlspecialchars($lblName) ?></span>
                    <?php endif; ?>
                    Projekt
                <?php endif; ?>
            </div>
            <div class="footer-ki">
                <?= __('footer.ki_note') ?>
            </div>
        </div>
    </footer>

</body>
</html>
<?php
}

/**
 * Social Share Buttons — privacy-friendly (no JS tracking, plain links).
 */
function portal_share_buttons(string $url, string $title, string $description = ''): void {
    $encUrl   = urlencode($url);
    $encTitle = urlencode($title);
    $encDesc  = urlencode($description ?: $title);
?>
    <div class="share-buttons">
        <span class="share-label"><?= __('share.label') ?></span>
        <a href="https://twitter.com/intent/tweet?url=<?= $encUrl ?>&text=<?= $encTitle ?>" 
           target="_blank" rel="noopener noreferrer" class="share-btn share-twitter" title="<?= __('share.twitter') ?>">𝕏</a>
        <a href="https://www.facebook.com/sharer/sharer.php?u=<?= $encUrl ?>" 
           target="_blank" rel="noopener noreferrer" class="share-btn share-facebook" title="<?= __('share.facebook') ?>">f</a>
        <a href="https://www.linkedin.com/sharing/share-offsite/?url=<?= $encUrl ?>" 
           target="_blank" rel="noopener noreferrer" class="share-btn share-linkedin" title="<?= __('share.linkedin') ?>">in</a>
        <a href="mailto:?subject=<?= $encTitle ?>&body=<?= $encDesc ?>%0A%0A<?= $encUrl ?>" 
           class="share-btn share-email" title="<?= __('share.email') ?>"><?= icon('mail') ?></a>
        <button onclick="navigator.clipboard.writeText('<?= htmlspecialchars($url, ENT_QUOTES) ?>');var b=this;b.textContent='✓';setTimeout(function(){b.textContent='🔗'},1500)" 
                class="share-btn share-copy" title="<?= __('share.copy') ?>">🔗</button>
    </div>
<?php
}
