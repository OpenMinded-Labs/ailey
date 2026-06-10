<?php
/**
 * Ailey Portal — Main Entry / Router
 * 
 * Simple PHP router. Serves the SPA-style portal pages.
 * Requires config.php (copy from config.example.php).
 */

$configPath = __DIR__ . '/config.php';
if (!file_exists($configPath)) {
    die('config.php not found. Copy config.example.php to config.php and fill in your values.');
}

$config = require $configPath;
require_once __DIR__ . '/db.php';
require_once __DIR__ . '/auth.php';
require_once __DIR__ . '/i18n.php';
require_once __DIR__ . '/icons.php';

require_once __DIR__ . '/nsfw_filter.php';

PortalDB::connect($config['db']);
$auth = new PortalAuth($config);
$auth->initSession();

// Simple routing
$path = parse_url($_SERVER['REQUEST_URI'], PHP_URL_PATH);
$path = rtrim($path, '/') ?: '/';

// Fallback: support ?page=login style routing (if mod_rewrite fails)
if ($path === '/' || basename($path) === 'index.php') {
    $pageParam = $_GET['page'] ?? '';
    if ($pageParam) {
        $path = '/' . $pageParam;
    }
}

// Static asset passthrough (let web server handle)
if (preg_match('/\.(css|js|png|jpg|jpeg|webp|gif|ico|svg|woff2?)$/', $path)) {
    return false; // Let PHP built-in or Apache handle static files
}

$user = $auth->getCurrentUser();

switch ($path) {
    case '/':
        // Cookie-gated intro: show morph intro once, then landing
        if (isset($_COOKIE['ailey_intro_seen'])) {
            require __DIR__ . '/pages/landing.php';
        } else {
            require __DIR__ . '/pages/intro.php';
        }
        break;
    case '/chat':
        if (!$user) { header('Location: /login'); exit; }
        // Public-tier users cannot access chat — redirect to forum
        if (PortalDB::getUserTier($user['id']) === 'public') { header('Location: /forum'); exit; }
        require __DIR__ . '/pages/chat.php';
        break;
    case '/login':
        if ($user) { header('Location: /chat'); exit; }
        require __DIR__ . '/pages/login.php';
        break;
    case '/forgot-password':
        if ($user) { header('Location: /chat'); exit; }
        require __DIR__ . '/pages/forgot-password.php';
        break;
    case '/reset-password':
        if ($user) { header('Location: /chat'); exit; }
        require __DIR__ . '/pages/reset-password.php';
        break;
    case '/register':
        if ($user) { header('Location: /chat'); exit; }
        require __DIR__ . '/pages/register.php';
        break;
    case '/impressum':
        require __DIR__ . '/pages/impressum.php';
        break;
    case '/datenschutz':
        require __DIR__ . '/pages/datenschutz.php';
        break;
    case '/settings':
        if (!$user) { header('Location: /login'); exit; }
        require __DIR__ . '/pages/settings.php';
        break;
    case '/play':
    case '/games':
        if (!$user) { header('Location: /login'); exit; }
        require __DIR__ . '/pages/games.php';
        break;
    case '/learning':
    case '/lernen':
        if (!$user) { header('Location: /login'); exit; }
        require __DIR__ . '/pages/learning.php';
        break;
    case '/admin':
        if (!$user || $user['role'] !== 'admin') { header('Location: /'); exit; }
        require __DIR__ . '/pages/admin.php';
        break;

    // ── Generierungs-Tools (eigene Unterseiten) ───────────────
    case '/bildgen':
    case '/bild-gen':
        if (!$user) { header('Location: /login'); exit; }
        require __DIR__ . '/pages/bildgen.php';
        break;
    case '/songgen':
    case '/song-gen':
        if (!$user) { header('Location: /login'); exit; }
        require __DIR__ . '/pages/songgen.php';
        break;

    // ── Public Art Site Pages ──────────────────────────────────
    case '/galerie':
    case '/gallery':
        require __DIR__ . '/pages/gallery.php';
        break;
    case '/blog':
        require __DIR__ . '/pages/blog.php';
        break;
    case '/feed':
        require __DIR__ . '/pages/feed.php';
        break;
    case '/ueber-ailey':
    case '/about':
        require __DIR__ . '/pages/about.php';
        break;
    case '/faq':
        require __DIR__ . '/pages/faq.php';
        break;
    case '/forum':
        require __DIR__ . '/pages/forum.php';
        break;
    case '/agb':
    case '/nutzungsbedingungen':
        require __DIR__ . '/pages/agb.php';
        break;
    case '/sitemap.xml':
        require __DIR__ . '/pages/sitemap.php';
        break;

    default:
        // Dynamic blog post route: /blog/slug-name
        if (preg_match('#^/blog/([a-z0-9-]+)$#', $path, $m)) {
            $_GET['slug'] = $m[1];
            require __DIR__ . '/pages/blog.php';
            break;
        }
        // Book chapter route: /buch/SLUG/kapitel/NUM
        if (preg_match('#^/buch/([a-z0-9_-]+)/kapitel/(\d+)$#', $path, $m)) {
            $_GET['book_slug'] = $m[1];
            $_GET['chapter'] = (int)$m[2];
            require __DIR__ . '/pages/book.php';
            break;
        }
        // Book overview route: /buch/SLUG
        if (preg_match('#^/buch/([a-z0-9_-]+)$#', $path, $m)) {
            $_GET['book_slug'] = $m[1];
            require __DIR__ . '/pages/book.php';
            break;
        }
        http_response_code(404);
        require __DIR__ . '/pages/404.php';
}
