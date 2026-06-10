<?php
/**
 * Ailey Portal — Configuration
 * 
 * Copy this file to config.php and fill in your values.
 * NEVER commit config.php to git!
 */

return [
    // ─── Database (allinkl MySQL) ────────────────────────────────
    'db' => [
        'host'     => 'localhost',
        'port'     => 3306,
        'name'     => 'YOUR_DB_NAME',
        'user'     => 'YOUR_DB_USER',
        'password' => 'YOUR_DB_PASSWORD',
        'charset'  => 'utf8mb4',
    ],

    // ─── Ailey Core Connection ───────────────────────────────────
    // Note: Ailey Core POLLS this server — no tunnel needed!
    // The portal_key must match AILEY_PORTAL_KEY env var on the Mac.
    'ailey' => [
        'portal_key' => 'YOUR_PORTAL_KEY_HERE',
    ],

    // ─── Session ─────────────────────────────────────────────────
    'session' => [
        'lifetime'    => 86400 * 7,  // 7 days
        'cookie_name' => 'ailey_portal_session',
        'secure'      => true,       // HTTPS only
        'httponly'     => true,
        'samesite'    => 'Lax',
    ],

    // ─── Rate Limits ─────────────────────────────────────────────
    'limits' => [
        'max_daily'    => 50,
        'max_hourly'   => 15,
        'max_message_length' => 2000,  // characters
    ],

    // ─── Site Info (Legal) ───────────────────────────────────────
    'site' => [
        'name'       => 'Ailey Portal',
        'url'        => 'https://hey-ailey.com',  // Base URL for OG tags & canonical (primary domain)
        'domain'     => 'hey-ailey.com',  // TODO: fill in
        'impressum'  => [
            'name'    => 'Simon van de Loo',
            'address' => 'Musterstraße 1, 12345 Musterstadt',  // TODO: fill in
            'email'   => 'simon@example.de',  // TODO: fill in
            'phone'   => '',
        ],
        'ki_disclosure' => 'Ailey ist ein KI-System (Large Language Model), entwickelt von Simon van de Loo. Ailey generiert Texte auf Basis statistischer Muster und hat kein echtes Bewusstsein. Alle Aussagen sind KI-generiert und keine professionelle Beratung.',
    ],

    // ─── Label / Dachmarke (OpenM!nded) ──────────────────────────
    // Tech-Label/Lab, unter dem A!ley entsteht. 'active' => false blendet es
    // überall aus, bis es offiziell geführt wird.
    'label' => [
        'active'     => true,
        'name'       => 'OpenM!nded',
        'tagline'    => 'Tech Lab',
        'url'        => '',
        'is_company' => false,
    ],

    // ─── Admin Dev-Link (Next.js Mainapp @ Mac) ──────────────────
    // Password-protected link in Admin Panel that opens the Next.js
    // mainapp running on the Mac. Port 5502 = Flask API which also
    // serves the Next.js frontend at /app/ (same port already used).
    'admin_devlink' => [
        'password' => 'CHANGE_ME_LOCAL_ONLY',
        'port'     => 5502,
    ],

    // ─── Debug ───────────────────────────────────────────────────
    'debug' => false,
];
