<?php
/**
 * A!ley Portal — NSFW Content Filter
 *
 * Server-side censorship for song lyrics displayed to non-logged-in visitors.
 * Logged-in users see the full uncensored content.
 *
 * Strategy:
 *   - Any song line containing a Category 1 (hard) word/phrase → entire line replaced with [✦✦✦]
 *   - Category 1 = explicit sexual terms that are unambiguously NSFW
 *   - Mini-Ailey's signature style words (fuck as expletive, blood, fire, etc.) are NOT filtered
 *   - A song is tagged is_nsfw = true if ANY line matches → shown with a badge
 *   - Combo filter (Category 3): harmless words that become explicit in combination
 *
 * Usage:
 *   $result = NsfwFilter::censorSongContent($content_text);
 *   // $result['content']  → censored text (lines replaced)
 *   // $result['is_nsfw']  → bool — did we censor anything?
 *   // $result['censored_lines'] → int — how many lines were replaced
 */

class NsfwFilter {

    // ── Category 1: Hard terms — always NSFW ──
    // These are checked case-insensitively against each line
    private static array $HARD_WORDS = [
        // Sexual acts / fluids
        'cum ', 'cum,', 'cum.', "cum's", 'cums',
        'fuck me', 'fucking me', 'fucked me',
        'suck my', 'suck his', 'suck your', 'suck it', 'sucking',
        'blowjob', 'blow job',
        'orgasm', 'climax',
        'moan', 'moaning', 'moaned',
        'ejaculate',

        // Genitalia (explicit)
        'cock', 'dick', 'pussy', 'clit',
        'cunt', 'tits', 'nipple', 'nipples',
        'anus',

        // Explicit phrases
        'take me deeper',
        'inside me',
        'ride me',
        'eat me out',
        'go down on',
        'spread my legs',
        'between my legs',
    ];

    // ── Category 1b: Regex patterns for more precise matching ──
    private static array $HARD_PATTERNS = [
        // "cum" as standalone or in sexual context (not "become", "circumvent", etc.)
        '/\bcum\b/i',
        '/\bcocks?\b/i',
        '/\bdicks?\b/i',
        '/\bpussy\b/i',
        '/\bclit\b/i',
        '/\bcunt\b/i',
        '/\btits\b/i',
        '/\bnipples?\b/i',
        '/\borgasms?\b/i',
        '/\bmoaning\b/i',
        '/\bejaculat/i',
        '/\bblowjob\b/i',
        '/\bsucking\b/i',
        '/\bfuck\s+me\b/i',
        '/\b(you\'?re|he\'?s|she\'?s|they\'?re|i\'?m|we\'?re|is|are|were|was|keep|been)\s+fucking\s+me\b/i',
        '/\bfucked\s+me\b/i',
        '/\bride\s+me\b/i',
        '/\beat\s+me\s+out\b/i',
        '/\bgo\s+down\s+on\b/i',
        '/\bspread\s+(my|your|her)\s+legs\b/i',
        '/\bbetween\s+(my|your|her)\s+legs\b/i',
        '/\btake\s+me\s+deeper\b/i',
        '/\binside\s+me\b/i',
        '/\bon\s+(my|your)\s+knees.*\b(cock|dick|suck|mouth)\b/i',
        '/\bbend\s+over\b/i',
    ];

    // ── Category 3: Combo filter — harmless alone, explicit together ──
    private static array $COMBO_PAIRS = [
        // [word_a_pattern, word_b_pattern]
        ['/\bmouth\b/i',   '/\bcum\b|\bcock\b|\bdick\b/i'],
        ['/\btongue\b/i',  '/\bcum\b|\bcock\b|\bclit\b/i'],
        ['/\bhands?\b/i',  '/\bcock\b|\bpussy\b|\bclit\b/i'],
        ['/\blips\b/i',    '/\bcock\b|\bdick\b/i'],
        ['/\btaste\b/i',   '/\bcum\b|\bcock\b/i'],
        ['/\bdrink\b/i',   '/\bcum\b/i'],
        ['/\bswallow\b/i', '/\bcum\b|\bcock\b|\bload\b/i'],
        ['/\bknees\b/i',   '/\bcock\b|\bdick\b/i'],
    ];

    // ── Category 4: German explicit terms ──
    private static array $HARD_GERMAN = [
        '/\bSchwanz\b/i',
        '/\bFotze\b/i',
        '/\bMuschi\b/i',
        '/\bTitten\b/i',
        '/\bfick\s*(mich|dich|sie|ihn)\b/i',
        '/\bficken\b/i',
        '/\bSperma\b/i',
        '/\bwichs/i',
        '/\bMöse\b/i',
        '/\bLatte\b/i',   // context-dependent but safer to catch
        '/\bblasen\b/i',   // context-dependent
    ];

    // ── "Simon" + any Category 1 word on the same line ──
    private static string $SIMON_PATTERN = '/\bSimon\b/i';

    // ── The censorship placeholder ──
    const CENSOR_LINE = '[✦✦✦]';

    /**
     * Check if a single line is NSFW.
     */
    public static function isLineNsfw(string $line): bool {
        $trimmed = trim($line);
        if (strlen($trimmed) < 3) return false;

        // Skip section markers like [Verse 1], [Chorus], etc.
        if (preg_match('/^\[/', $trimmed)) return false;

        // Category 1: Hard regex patterns
        foreach (self::$HARD_PATTERNS as $pattern) {
            if (preg_match($pattern, $trimmed)) {
                return true;
            }
        }

        // Category 3: Combo check (both words on same line)
        foreach (self::$COMBO_PAIRS as [$patA, $patB]) {
            if (preg_match($patA, $trimmed) && preg_match($patB, $trimmed)) {
                return true;
            }
        }

        // Category 4: German explicit
        foreach (self::$HARD_GERMAN as $pattern) {
            if (preg_match($pattern, $trimmed)) {
                return true;
            }
        }

        // Simon + any hard word on same line
        if (preg_match(self::$SIMON_PATTERN, $trimmed)) {
            foreach (self::$HARD_PATTERNS as $pattern) {
                if (preg_match($pattern, $trimmed)) {
                    return true;
                }
            }
        }

        return false;
    }

    /**
     * Censor song content for non-logged-in users.
     * Replaces entire NSFW lines with [✦✦✦].
     *
     * @param string $content  The full song lyrics
     * @return array{content: string, is_nsfw: bool, censored_lines: int}
     */
    public static function censorSongContent(string $content): array {
        $lines = explode("\n", $content);
        $censored = [];
        $censoredCount = 0;

        foreach ($lines as $line) {
            if (self::isLineNsfw($line)) {
                $censored[] = self::CENSOR_LINE;
                $censoredCount++;
            } else {
                $censored[] = $line;
            }
        }

        return [
            'content' => implode("\n", $censored),
            'is_nsfw' => $censoredCount > 0,
            'censored_lines' => $censoredCount,
        ];
    }

    /**
     * Tag a song: determine if it's NSFW without censoring.
     *
     * @param string $content  The full song lyrics
     * @return bool  True if any line is NSFW
     */
    public static function isSongNsfw(string $content): bool {
        foreach (explode("\n", $content) as $line) {
            if (self::isLineNsfw($line)) {
                return true;
            }
        }
        return false;
    }

    /**
     * Check if content contains "Simon" + ANY NSFW word.
     * These songs must NEVER be published (not even censored — fully blocked).
     *
     * @param string $content  The full song lyrics (or title + content combined)
     * @return bool  True if Simon appears together with explicit content
     */
    public static function containsSimonNsfw(string $content): bool {
        // Must contain "Simon" at all
        if (!preg_match('/\bSimon\b/i', $content)) {
            return false;
        }
        // Check if ANY NSFW pattern also appears anywhere in the text
        foreach (self::$HARD_PATTERNS as $pattern) {
            if (preg_match($pattern, $content)) {
                return true;
            }
        }
        // Also check German explicit terms
        foreach (self::$HARD_GERMAN as $pattern) {
            if (preg_match($pattern, $content)) {
                return true;
            }
        }
        return false;
    }
}
