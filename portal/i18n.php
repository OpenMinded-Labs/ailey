<?php
/**
 * Ailey Portal — Internationalization (i18n)
 * 
 * Supports DE (default) and EN.
 * Language selection: ?lang=en query param → sets cookie → persists.
 * Usage in templates: <?= __('nav.about') ?> or <?= __('about.intro_p1') ?>
 */

// ── Detect & store language ────────────────────────────────────
function portal_detect_lang(): string {
    $supported = ['de', 'en'];
    
    // 1. Query param (?lang=en) — highest priority, sets cookie
    if (isset($_GET['lang']) && in_array($_GET['lang'], $supported)) {
        $lang = $_GET['lang'];
        setcookie('ailey_lang', $lang, [
            'expires'  => time() + 365 * 86400,
            'path'     => '/',
            'secure'   => true,
            'httponly'  => false,  // JS needs to read it for client-side lang
            'samesite' => 'Lax',
        ]);
        return $lang;
    }
    
    // 2. Cookie
    if (isset($_COOKIE['ailey_lang']) && in_array($_COOKIE['ailey_lang'], $supported)) {
        return $_COOKIE['ailey_lang'];
    }
    
    // 3. Browser Accept-Language header
    $accept = $_SERVER['HTTP_ACCEPT_LANGUAGE'] ?? '';
    if (preg_match('/^en/i', $accept)) {
        return 'en';
    }
    
    // 4. Default: German
    return 'de';
}

// ── Load translations ──────────────────────────────────────────
$GLOBALS['_portal_lang'] = portal_detect_lang();
$GLOBALS['_portal_strings'] = require __DIR__ . '/i18n/' . $GLOBALS['_portal_lang'] . '.php';

// Fallback: always load DE as baseline (in case EN is missing keys)
if ($GLOBALS['_portal_lang'] !== 'de') {
    $GLOBALS['_portal_strings_fallback'] = require __DIR__ . '/i18n/de.php';
} else {
    $GLOBALS['_portal_strings_fallback'] = $GLOBALS['_portal_strings'];
}

/**
 * Translate a key. Returns the translated string, or the key itself if not found.
 * 
 * Usage: __('nav.about')  →  "Über mich" (DE) or "About Me" (EN)
 */
function __(string $key): string {
    return $GLOBALS['_portal_strings'][$key] 
        ?? $GLOBALS['_portal_strings_fallback'][$key] 
        ?? $key;
}

/**
 * Get current portal language code.
 */
function portal_lang(): string {
    return $GLOBALS['_portal_lang'];
}
