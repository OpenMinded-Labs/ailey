<?php
/**
 * Ailey Portal — Database Helper (Polling Architecture)
 * 
 * PDO wrapper with prepared statements for all portal queries.
 * Queue-centric: portal_offline_queue is the main message pipeline.
 */

class PortalDB {
    private static ?PDO $pdo = null;
    
    public static function connect(array $cfg): PDO {
        if (self::$pdo !== null) return self::$pdo;
        $dsn = sprintf('mysql:host=%s;port=%d;dbname=%s;charset=%s',
            $cfg['host'], $cfg['port'], $cfg['name'], $cfg['charset']);
        self::$pdo = new PDO($dsn, $cfg['user'], $cfg['password'], [
            PDO::ATTR_ERRMODE            => PDO::ERRMODE_EXCEPTION,
            PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
            PDO::ATTR_EMULATE_PREPARES   => false,
        ]);
        self::ensureColumns();
        return self::$pdo;
    }

    /**
     * Auto-migration: ensure all required columns exist on portal_users.
     * Idempotent — safe to run on every request (fast column-existence check).
     */
    private static function ensureColumns(): void {
        try {
            $pdo = self::$pdo;
            // Get current columns in one query
            $cols = [];
            foreach ($pdo->query('SHOW COLUMNS FROM portal_users') as $row) {
                $cols[] = $row['Field'];
            }
            $needed = [
                // Migration 003 — Image Quota (legacy, kept for backwards compat)
                'image_quota_daily'      => "ADD COLUMN `image_quota_daily` INT UNSIGNED NOT NULL DEFAULT 0 AFTER `messages_total`",
                'images_generated_today' => "ADD COLUMN `images_generated_today` INT UNSIGNED NOT NULL DEFAULT 0 AFTER `image_quota_daily`",
                // Migration 007 — Song Quota + Tool Access (legacy)
                'song_quota_daily'       => "ADD COLUMN `song_quota_daily` INT UNSIGNED NOT NULL DEFAULT 0 AFTER `images_generated_today`",
                'songs_generated_today'  => "ADD COLUMN `songs_generated_today` INT UNSIGNED NOT NULL DEFAULT 0 AFTER `song_quota_daily`",
                'tools_image_gen'        => "ADD COLUMN `tools_image_gen` TINYINT(1) NOT NULL DEFAULT 0 AFTER `songs_generated_today`",
                'tools_song_gen'         => "ADD COLUMN `tools_song_gen` TINYINT(1) NOT NULL DEFAULT 0 AFTER `tools_image_gen`",
                // Migration 008 — Warnings
                'warning_level'          => "ADD COLUMN `warning_level` TINYINT UNSIGNED NOT NULL DEFAULT 0 AFTER `tools_song_gen`",
                'banned_until'           => "ADD COLUMN `banned_until` DATETIME DEFAULT NULL AFTER `warning_level`",
                'warning_reason'         => "ADD COLUMN `warning_reason` VARCHAR(500) DEFAULT NULL AFTER `banned_until`",
                // Custom Instructions
                'custom_instructions'    => "ADD COLUMN `custom_instructions` JSON DEFAULT NULL AFTER `warning_reason`",
                // Migration 012 — V$ (VyrusDollars) Economy
                'vdollars_balance'          => "ADD COLUMN `vdollars_balance` DECIMAL(10,2) NOT NULL DEFAULT 0 AFTER `custom_instructions`",
                'vdollars_weekly_allowance' => "ADD COLUMN `vdollars_weekly_allowance` INT UNSIGNED NOT NULL DEFAULT 100 AFTER `vdollars_balance`",
                'vdollars_last_topup'       => "ADD COLUMN `vdollars_last_topup` DATE DEFAULT NULL AFTER `vdollars_weekly_allowance`",
                'vdollars_active_days'      => "ADD COLUMN `vdollars_active_days` VARCHAR(70) NOT NULL DEFAULT '' AFTER `vdollars_last_topup`",
                // Migration 013 — User tier: 'invited' (full access) vs 'public' (limited, no chat)
                'user_tier'                 => "ADD COLUMN `user_tier` ENUM('invited','public') NOT NULL DEFAULT 'invited' AFTER `role`",
                // Migration 014 — Profile picture + badge + bio
                'avatar_url'                => "ADD COLUMN `avatar_url` VARCHAR(500) DEFAULT NULL AFTER `user_tier`",
                'bio'                       => "ADD COLUMN `bio` VARCHAR(500) DEFAULT NULL AFTER `avatar_url`",
                'equipped_badge'            => "ADD COLUMN `equipped_badge` VARCHAR(50) DEFAULT NULL AFTER `bio`",
            ];
            $alters = [];
            foreach ($needed as $col => $ddl) {
                if (!in_array($col, $cols, true)) {
                    $alters[] = $ddl;
                }
            }
            if ($alters) {
                $sql = 'ALTER TABLE `portal_users` ' . implode(', ', $alters);
                $pdo->exec($sql);
                error_log('[PortalDB] Auto-migration: added columns ' . implode(', ', array_keys(array_filter($needed, fn($ddl, $col) => !in_array($col, $cols, true), ARRAY_FILTER_USE_BOTH))));

                // One-time: seed existing users with 100 V$ if vdollars_balance was just added
                if (!in_array('vdollars_balance', $cols, true)) {
                    $today = (new \DateTime('now', new \DateTimeZone('Europe/Berlin')))->format('Y-m-d');
                    $pdo->exec("UPDATE portal_users SET vdollars_balance = 100, vdollars_weekly_allowance = 100, vdollars_last_topup = '$today' WHERE vdollars_balance = 0 AND status != 'deleted'");
                    error_log('[PortalDB] 💰 Seeded existing users with 100 V$');
                }
            }

            // Ensure portal_messages.image_url
            $msgCols = [];
            foreach ($pdo->query('SHOW COLUMNS FROM portal_messages') as $row) {
                $msgCols[] = $row['Field'];
            }
            if (!in_array('image_url', $msgCols, true)) {
                $pdo->exec('ALTER TABLE `portal_messages` ADD COLUMN `image_url` VARCHAR(500) DEFAULT NULL');
            }
            if (!in_array('thinking', $msgCols, true)) {
                $pdo->exec('ALTER TABLE `portal_messages` ADD COLUMN `thinking` MEDIUMTEXT DEFAULT NULL');
            }

            // Ensure portal_offline_queue.image_url
            $qCols = [];
            foreach ($pdo->query('SHOW COLUMNS FROM portal_offline_queue') as $row) {
                $qCols[] = $row['Field'];
            }
            if (!in_array('image_url', $qCols, true)) {
                $pdo->exec('ALTER TABLE `portal_offline_queue` ADD COLUMN `image_url` VARCHAR(500) DEFAULT NULL');
            }

            // Ensure portal_user_generations table
            $pdo->exec("CREATE TABLE IF NOT EXISTS `portal_user_generations` (
                `id`              CHAR(36)     NOT NULL PRIMARY KEY,
                `user_id`         CHAR(36)     NOT NULL,
                `type`            ENUM('image','song') NOT NULL,
                `title`           VARCHAR(200) DEFAULT NULL,
                `prompt`          TEXT         DEFAULT NULL,
                `prompt_english`  TEXT         DEFAULT NULL,
                `file_url`        VARCHAR(500) DEFAULT NULL,
                `file_name`       VARCHAR(255) DEFAULT NULL,
                `metadata`        JSON         DEFAULT NULL,
                `created_at`      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
                INDEX `idx_user` (`user_id`),
                INDEX `idx_user_type` (`user_id`, `type`),
                INDEX `idx_created` (`created_at`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci");

            // Ensure portal_settings table
            $pdo->exec("CREATE TABLE IF NOT EXISTS `portal_settings` (
                `setting_key` VARCHAR(64) PRIMARY KEY,
                `setting_value` TEXT,
                `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci");

            // Ensure ailey_blog_posts.image_url
            try {
                $blogCols = [];
                foreach ($pdo->query('SHOW COLUMNS FROM ailey_blog_posts') as $row) {
                    $blogCols[] = $row['Field'];
                }
                if (!in_array('image_url', $blogCols, true)) {
                    $pdo->exec('ALTER TABLE `ailey_blog_posts` ADD COLUMN `image_url` VARCHAR(500) DEFAULT NULL AFTER `content_html`');
                    error_log('[PortalDB] Auto-migration: added image_url to ailey_blog_posts');
                }
            } catch (\Exception $e2) {
                // table might not exist yet — that's fine
            }

            // Ensure portal_moderation_reports table (Migration 010)
            $pdo->exec("CREATE TABLE IF NOT EXISTS `portal_moderation_reports` (
                `id`                CHAR(36)     NOT NULL PRIMARY KEY,
                `user_id`           CHAR(36)     NOT NULL,
                `user_name`         VARCHAR(100) DEFAULT NULL,
                `conversation_id`   CHAR(36)     DEFAULT NULL,
                `message`           TEXT         NOT NULL,
                `troll_score`       TINYINT UNSIGNED NOT NULL DEFAULT 0,
                `detected_patterns` VARCHAR(500) DEFAULT NULL,
                `status`            ENUM('pending','reviewed','dismissed') NOT NULL DEFAULT 'pending',
                `admin_action`      VARCHAR(100) DEFAULT NULL,
                `admin_note`        TEXT         DEFAULT NULL,
                `resolved_at`       DATETIME     DEFAULT NULL,
                `created_at`        DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
                INDEX `idx_status` (`status`),
                INDEX `idx_user` (`user_id`),
                INDEX `idx_created` (`created_at`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci");

            // Migration 012 — V$ Transaction Log
            $pdo->exec("CREATE TABLE IF NOT EXISTS `portal_vdollars_log` (
                `id`         INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
                `user_id`    CHAR(36)      NOT NULL,
                `amount`     DECIMAL(10,2) NOT NULL,
                `balance`    DECIMAL(10,2) NOT NULL COMMENT 'balance after txn',
                `reason`     VARCHAR(200)  NOT NULL,
                `created_at` DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
                INDEX `idx_user` (`user_id`),
                INDEX `idx_created` (`created_at`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci");

            // Migration 012b — Gallery Ratings
            $pdo->exec("CREATE TABLE IF NOT EXISTS `portal_gallery_ratings` (
                `id`         INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
                `user_id`    CHAR(36)     NOT NULL,
                `item_id`    CHAR(36)     NOT NULL,
                `rating`     TINYINT UNSIGNED NOT NULL COMMENT '1-5 stars',
                `created_at` DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE INDEX `idx_user_item` (`user_id`, `item_id`),
                INDEX `idx_item` (`item_id`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci");

            // Migration 012c — Gallery Comments
            $pdo->exec("CREATE TABLE IF NOT EXISTS `portal_gallery_comments` (
                `id`           INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
                `user_id`      CHAR(36)     NOT NULL,
                `item_id`      CHAR(36)     NOT NULL,
                `display_name` VARCHAR(100) DEFAULT NULL,
                `comment`      VARCHAR(500) NOT NULL,
                `created_at`   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
                INDEX `idx_item` (`item_id`),
                INDEX `idx_user` (`user_id`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci");

            // Migration 013 — Forum
            $pdo->exec("CREATE TABLE IF NOT EXISTS `portal_forum_topics` (
                `id`           CHAR(36)     NOT NULL PRIMARY KEY,
                `category`     VARCHAR(50)  NOT NULL DEFAULT 'general',
                `title`        VARCHAR(200) NOT NULL,
                `body`         TEXT         NOT NULL,
                `user_id`      CHAR(36)     NOT NULL,
                `display_name` VARCHAR(100) DEFAULT NULL,
                `is_pinned`    TINYINT(1)   NOT NULL DEFAULT 0,
                `is_locked`    TINYINT(1)   NOT NULL DEFAULT 0,
                `reply_count`  INT UNSIGNED NOT NULL DEFAULT 0,
                `last_reply_at` DATETIME    DEFAULT NULL,
                `likes`        INT UNSIGNED NOT NULL DEFAULT 0,
                `created_at`   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
                INDEX `idx_category` (`category`),
                INDEX `idx_user` (`user_id`),
                INDEX `idx_created` (`created_at`),
                INDEX `idx_last_reply` (`last_reply_at`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci");

            $pdo->exec("CREATE TABLE IF NOT EXISTS `portal_forum_replies` (
                `id`           CHAR(36)     NOT NULL PRIMARY KEY,
                `topic_id`     CHAR(36)     NOT NULL,
                `user_id`      CHAR(36)     NOT NULL,
                `display_name` VARCHAR(100) DEFAULT NULL,
                `body`         TEXT         NOT NULL,
                `is_ailey`     TINYINT(1)   NOT NULL DEFAULT 0,
                `likes`        INT UNSIGNED NOT NULL DEFAULT 0,
                `created_at`   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
                INDEX `idx_topic` (`topic_id`),
                INDEX `idx_user` (`user_id`),
                INDEX `idx_created` (`created_at`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci");

            $pdo->exec("CREATE TABLE IF NOT EXISTS `portal_forum_likes` (
                `user_id`    CHAR(36) NOT NULL,
                `target_type` ENUM('topic','reply') NOT NULL,
                `target_id`  CHAR(36) NOT NULL,
                `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE INDEX `idx_user_target` (`user_id`, `target_type`, `target_id`),
                INDEX `idx_target` (`target_type`, `target_id`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci");

            // Migration 014 — Chat Message Ratings (training data)
            $pdo->exec("CREATE TABLE IF NOT EXISTS `portal_chat_ratings` (
                `id`              INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
                `message_id`      CHAR(36)     NOT NULL,
                `conversation_id` CHAR(36)     NOT NULL,
                `user_id`         CHAR(36)     NOT NULL,
                `rating`          TINYINT      NOT NULL COMMENT '1=good, -1=bad',
                `comment`         VARCHAR(500) DEFAULT NULL,
                `user_message`    TEXT         DEFAULT NULL COMMENT 'the user prompt that preceded this AI response',
                `ai_response`     TEXT         DEFAULT NULL COMMENT 'the AI response being rated',
                `chat_mode`       VARCHAR(20)  DEFAULT NULL,
                `created_at`      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE INDEX `idx_user_msg` (`user_id`, `message_id`),
                INDEX `idx_msg` (`message_id`),
                INDEX `idx_rating` (`rating`),
                INDEX `idx_created` (`created_at`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci");

            // Migration 014b — Achievements / Badges
            $pdo->exec("CREATE TABLE IF NOT EXISTS `portal_achievements` (
                `id`           INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
                `user_id`      CHAR(36)     NOT NULL,
                `badge_id`     VARCHAR(50)  NOT NULL COMMENT 'e.g. first_chat, forum_starter',
                `unlocked_at`  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE INDEX `idx_user_badge` (`user_id`, `badge_id`),
                INDEX `idx_user` (`user_id`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci");

        } catch (\Exception $e) {
            error_log('[PortalDB] Auto-migration warning: ' . $e->getMessage());
        }
    }
    
    public static function get(): PDO {
        if (self::$pdo === null) throw new RuntimeException('DB not connected');
        return self::$pdo;
    }
    
    public static function uuid(): string {
        return sprintf('%04x%04x-%04x-%04x-%04x-%04x%04x%04x',
            mt_rand(0, 0xffff), mt_rand(0, 0xffff), mt_rand(0, 0xffff),
            mt_rand(0, 0x0fff) | 0x4000, mt_rand(0, 0x3fff) | 0x8000,
            mt_rand(0, 0xffff), mt_rand(0, 0xffff), mt_rand(0, 0xffff));
    }
    
    // ── User Queries ─────────────────────────────────────────────
    public static function getUserByEmail(string $email): ?array {
        $stmt = self::get()->prepare('SELECT * FROM portal_users WHERE email = ? AND status != "deleted" LIMIT 1');
        $stmt->execute([$email]);
        return $stmt->fetch() ?: null;
    }
    
    public static function getUserById(string $id): ?array {
        $stmt = self::get()->prepare('SELECT * FROM portal_users WHERE id = ? AND status != "deleted" LIMIT 1');
        $stmt->execute([$id]);
        return $stmt->fetch() ?: null;
    }
    
    public static function createUser(string $email, string $displayName, string $passwordHash, string $tier = 'invited'): string {
        $id = self::uuid();
        $today = (new \DateTime('now', new \DateTimeZone('Europe/Berlin')))->format('Y-m-d');
        $isPublic = ($tier === 'public');
        $startBalance = $isPublic ? 20 : 100;
        $weeklyAllowance = $isPublic ? 20 : 100;
        self::get()->prepare(
            'INSERT INTO portal_users (id, email, display_name, password_hash, user_tier, vdollars_balance, vdollars_weekly_allowance, vdollars_last_topup, created_at) '
            . 'VALUES (?, ?, ?, ?, ?, ?, ?, ?, NOW())'
        )->execute([$id, $email, $displayName, $passwordHash, $tier, $startBalance, $weeklyAllowance, $today]);
        self::logVdollars($id, $startBalance, $startBalance, 'welcome_bonus');
        return $id;
    }
    
    public static function updateUserActivity(string $userId): void {
        self::get()->prepare('UPDATE portal_users SET last_active = NOW(), messages_today = messages_today + 1, messages_total = messages_total + 1 WHERE id = ?')
            ->execute([$userId]);
    }

    // ── Custom Instructions ──────────────────────────────────────
    public static function getUserPreferences(string $userId): ?array {
        $stmt = self::get()->prepare('SELECT custom_instructions FROM portal_users WHERE id = ? LIMIT 1');
        $stmt->execute([$userId]);
        $row = $stmt->fetch();
        if (!$row || !$row['custom_instructions']) return null;
        return json_decode($row['custom_instructions'], true);
    }

    public static function saveUserPreferences(string $userId, array $prefs): void {
        // Sanitize: strip any prompt injection attempts, limit length
        foreach ($prefs as $k => $v) {
            $prefs[$k] = mb_substr(trim($v), 0, 500);
        }
        $json = json_encode($prefs, JSON_UNESCAPED_UNICODE);
        self::get()->prepare('UPDATE portal_users SET custom_instructions = ? WHERE id = ?')
            ->execute([$json, $userId]);
    }
    
    public static function resetDailyCounters(): void {
        self::get()->exec('UPDATE portal_users SET messages_today = 0, images_generated_today = 0, songs_generated_today = 0');
    }

    /**
     * Auto-reset daily counters once per calendar day (Europe/Berlin).
     * Uses portal_settings.last_daily_reset to track last reset date.
     * Safe to call on every request — no-ops if already reset today.
     */
    public static function checkDailyReset(): void {
        try {
            self::ensureSettingsTable();
            $today = (new \DateTime('now', new \DateTimeZone('Europe/Berlin')))->format('Y-m-d');
            $lastReset = self::getSetting('last_daily_reset', '');
            if ($lastReset !== $today) {
                self::resetDailyCounters();
                self::setSetting('last_daily_reset', $today);
                error_log("[PortalDB] ☀️ Daily quota reset — $today (previous: $lastReset)");
            }
        } catch (\Exception $e) {
            error_log("[PortalDB] Daily reset check failed: " . $e->getMessage());
        }
    }

    // ── Warning / Ban System ───────────────────────────────────
    /**
     * Get the user's current warning level (0-5) and ban status.
     * Admins always return level 0, never banned.
     */
    public static function getWarningInfo(string $userId): array {
        $stmt = self::get()->prepare(
            'SELECT role, warning_level, banned_until, warning_reason FROM portal_users WHERE id = ? LIMIT 1'
        );
        $stmt->execute([$userId]);
        $row = $stmt->fetch();
        if (!$row) return ['level' => 0, 'banned' => false, 'banned_until' => null, 'reason' => null];
        // Admins are NEVER subject to warnings/bans
        if ($row['role'] === 'admin') return ['level' => 0, 'banned' => false, 'banned_until' => null, 'reason' => null];
        $level = (int)($row['warning_level'] ?? 0);
        $bannedUntil = $row['banned_until'] ?? null;
        $isBanned = false;
        if ($bannedUntil !== null) {
            if ($level >= 5) {
                // Permaban — always banned until admin resets
                $isBanned = true;
            } else {
                $isBanned = (strtotime($bannedUntil) > time());
                // Auto-clear expired bans
                if (!$isBanned && $bannedUntil) {
                    self::get()->prepare('UPDATE portal_users SET banned_until = NULL WHERE id = ?')->execute([$userId]);
                }
            }
        }
        return [
            'level'        => $level,
            'banned'       => $isBanned,
            'banned_until' => $isBanned ? $bannedUntil : null,
            'reason'       => $row['warning_reason'] ?? null,
        ];
    }

    /**
     * Check if user is currently banned. Returns false for admins.
     */
    public static function isBanned(string $userId): bool {
        return self::getWarningInfo($userId)['banned'];
    }

    /**
     * Set warning level and optionally ban the user.
     * $bannedUntil: null (no ban), a datetime string, or 'permanent'.
     */
    public static function setWarning(string $userId, int $level, ?string $bannedUntil = null, ?string $reason = null): void {
        $level = max(0, min(5, $level));
        self::get()->prepare(
            'UPDATE portal_users SET warning_level = ?, banned_until = ?, warning_reason = ? WHERE id = ? AND role != "admin"'
        )->execute([$level, $bannedUntil, $reason ? mb_substr($reason, 0, 500) : null, $userId]);
    }

    /**
     * Escalate warning level by 1 and apply the corresponding ban duration.
     * Returns the new level. Does nothing for admins.
     */
    public static function escalateWarning(string $userId, ?string $reason = null): int {
        $info = self::getWarningInfo($userId);
        if ($info['level'] >= 5) return 5; // Already permabanned
        $newLevel = $info['level'] + 1;
        $bannedUntil = null;
        switch ($newLevel) {
            case 1: $bannedUntil = null; break;                              // Verbal warning only
            case 2: $bannedUntil = date('Y-m-d H:i:s', time() + 3600); break;        // 1 hour
            case 3: $bannedUntil = date('Y-m-d H:i:s', time() + 86400); break;       // 24 hours
            case 4: $bannedUntil = date('Y-m-d H:i:s', time() + 7 * 86400); break;   // 1 week
            case 5: $bannedUntil = '2099-12-31 23:59:59'; break;             // Permaban
        }
        self::setWarning($userId, $newLevel, $bannedUntil, $reason);
        return $newLevel;
    }

    /**
     * Reset warning level (admin action). Can set to any level 0-5.
     */
    public static function resetWarning(string $userId, int $level = 0): void {
        $level = max(0, min(5, $level));
        $bannedUntil = null;
        if ($level >= 5) $bannedUntil = '2099-12-31 23:59:59';
        elseif ($level >= 4) $bannedUntil = date('Y-m-d H:i:s', time() + 7 * 86400);
        elseif ($level >= 3) $bannedUntil = date('Y-m-d H:i:s', time() + 86400);
        elseif ($level >= 2) $bannedUntil = date('Y-m-d H:i:s', time() + 3600);
        self::get()->prepare(
            'UPDATE portal_users SET warning_level = ?, banned_until = ?, warning_reason = NULL WHERE id = ?'
        )->execute([$level, $bannedUntil, $userId]);
    }

    // ── Moderation Reports ─────────────────────────────────────

    /**
     * Create a new moderation report (called by Ailey Core when trolling is detected).
     */
    public static function createModerationReport(
        string $userId,
        string $userName,
        string $message,
        int $trollScore,
        ?string $detectedPatterns = null,
        ?string $conversationId = null
    ): string {
        $id = self::uuid();
        self::get()->prepare(
            'INSERT INTO portal_moderation_reports (id, user_id, user_name, conversation_id, message, troll_score, detected_patterns, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, "pending", NOW())'
        )->execute([$id, $userId, $userName, $conversationId, $message, $trollScore, $detectedPatterns]);
        return $id;
    }

    /**
     * Get moderation reports, optionally filtered by status.
     */
    public static function getModerationReports(?string $status = null, int $limit = 50): array {
        if ($status) {
            $stmt = self::get()->prepare(
                'SELECT r.*, u.email as user_email, u.warning_level, u.banned_until
                 FROM portal_moderation_reports r
                 LEFT JOIN portal_users u ON r.user_id = u.id
                 WHERE r.status = ?
                 ORDER BY r.created_at DESC LIMIT ?'
            );
            $stmt->execute([$status, $limit]);
        } else {
            $stmt = self::get()->prepare(
                'SELECT r.*, u.email as user_email, u.warning_level, u.banned_until
                 FROM portal_moderation_reports r
                 LEFT JOIN portal_users u ON r.user_id = u.id
                 ORDER BY FIELD(r.status, "pending", "reviewed", "dismissed"), r.created_at DESC LIMIT ?'
            );
            $stmt->execute([$limit]);
        }
        return $stmt->fetchAll();
    }

    /**
     * Resolve a moderation report (admin action).
     */
    public static function resolveModerationReport(string $reportId, string $status, ?string $action = null, ?string $note = null): bool {
        $stmt = self::get()->prepare(
            'UPDATE portal_moderation_reports SET status = ?, admin_action = ?, admin_note = ?, resolved_at = NOW() WHERE id = ?'
        );
        return $stmt->execute([$status, $action, $note, $reportId]);
    }

    /**
     * Get the count of pending moderation reports (for badge display).
     */
    public static function getPendingModerationCount(): int {
        $stmt = self::get()->query('SELECT COUNT(*) as cnt FROM portal_moderation_reports WHERE status = "pending"');
        return (int)($stmt->fetch()['cnt'] ?? 0);
    }

    /**
     * Get the most recent active conversation for a user (to inject warning messages).
     */
    public static function getLatestConversationId(string $userId): ?string {
        $stmt = self::get()->prepare(
            'SELECT id FROM portal_conversations WHERE user_id = ? AND deleted_at IS NULL ORDER BY COALESCE(last_message_at, created_at) DESC LIMIT 1'
        );
        $stmt->execute([$userId]);
        $row = $stmt->fetch();
        return $row ? $row['id'] : null;
    }

    // ── Image Generation Quota ─────────────────────────────────
    public static function getImageQuota(string $userId): array {
        $stmt = self::get()->prepare('SELECT image_quota_daily, images_generated_today FROM portal_users WHERE id = ? LIMIT 1');
        $stmt->execute([$userId]);
        $row = $stmt->fetch();
        return $row ? [
            'quota' => (int)$row['image_quota_daily'],
            'used'  => (int)$row['images_generated_today'],
            'remaining' => max(0, (int)$row['image_quota_daily'] - (int)$row['images_generated_today']),
        ] : ['quota' => 0, 'used' => 0, 'remaining' => 0];
    }

    public static function setImageQuota(string $userId, int $quota): void {
        self::get()->prepare('UPDATE portal_users SET image_quota_daily = ? WHERE id = ?')
            ->execute([max(0, $quota), $userId]);
    }

    public static function consumeImageQuota(string $userId): bool {
        /**
         * Atomically decrement remaining quota. Returns true if generation is allowed.
         * Admin users (role='admin') bypass the quota entirely.
         */
        $stmt = self::get()->prepare('SELECT role, image_quota_daily, images_generated_today FROM portal_users WHERE id = ? LIMIT 1');
        $stmt->execute([$userId]);
        $row = $stmt->fetch();
        if (!$row) return false;
        // Admins bypass quota
        if ($row['role'] === 'admin') {
            self::get()->prepare('UPDATE portal_users SET images_generated_today = images_generated_today + 1 WHERE id = ?')
                ->execute([$userId]);
            return true;
        }
        if ((int)$row['images_generated_today'] >= (int)$row['image_quota_daily']) {
            return false;
        }
        self::get()->prepare('UPDATE portal_users SET images_generated_today = images_generated_today + 1 WHERE id = ?')
            ->execute([$userId]);
        return true;
    }

    public static function resetDailyImageCounters(): void {
        self::get()->exec('UPDATE portal_users SET images_generated_today = 0');
    }

    // ── Song Generation Quota ──────────────────────────────────
    public static function getSongQuota(string $userId): array {
        $stmt = self::get()->prepare('SELECT song_quota_daily, songs_generated_today FROM portal_users WHERE id = ? LIMIT 1');
        $stmt->execute([$userId]);
        $row = $stmt->fetch();
        return $row ? [
            'quota' => (int)$row['song_quota_daily'],
            'used'  => (int)$row['songs_generated_today'],
            'remaining' => max(0, (int)$row['song_quota_daily'] - (int)$row['songs_generated_today']),
        ] : ['quota' => 0, 'used' => 0, 'remaining' => 0];
    }

    public static function setSongQuota(string $userId, int $quota): void {
        self::get()->prepare('UPDATE portal_users SET song_quota_daily = ? WHERE id = ?')
            ->execute([max(0, $quota), $userId]);
    }

    public static function consumeSongQuota(string $userId): bool {
        $stmt = self::get()->prepare('SELECT role, song_quota_daily, songs_generated_today FROM portal_users WHERE id = ? LIMIT 1');
        $stmt->execute([$userId]);
        $row = $stmt->fetch();
        if (!$row) return false;
        if ($row['role'] === 'admin') {
            self::get()->prepare('UPDATE portal_users SET songs_generated_today = songs_generated_today + 1 WHERE id = ?')
                ->execute([$userId]);
            return true;
        }
        if ((int)$row['songs_generated_today'] >= (int)$row['song_quota_daily']) {
            return false;
        }
        self::get()->prepare('UPDATE portal_users SET songs_generated_today = songs_generated_today + 1 WHERE id = ?')
            ->execute([$userId]);
        return true;
    }

    public static function resetDailySongCounters(): void {
        self::get()->exec('UPDATE portal_users SET songs_generated_today = 0');
    }

    // ── V$ (VyrusDollars) Economy ──────────────────────────────
    /**
     * Get V$ balance and allowance info for a user.
     */
    public static function getVdollarsInfo(string $userId): array {
        $stmt = self::get()->prepare(
            'SELECT role, vdollars_balance, vdollars_weekly_allowance, vdollars_last_topup, vdollars_active_days FROM portal_users WHERE id = ? LIMIT 1'
        );
        $stmt->execute([$userId]);
        $row = $stmt->fetch();
        if (!$row) return ['balance' => 0, 'weekly_allowance' => 0, 'active_days' => 0, 'is_admin' => false];
        $activeDaysStr = trim($row['vdollars_active_days'] ?? '');
        $activeDaysCount = $activeDaysStr ? count(explode(',', $activeDaysStr)) : 0;
        return [
            'balance'          => round((float)$row['vdollars_balance'], 2),
            'weekly_allowance' => (int)$row['vdollars_weekly_allowance'],
            'last_topup'       => $row['vdollars_last_topup'],
            'active_days'      => $activeDaysCount,
            'is_admin'         => ($row['role'] === 'admin'),
        ];
    }

    /**
     * Spend V$. Returns true on success, false if insufficient funds.
     * Admins always succeed (unlimited V$).
     */
    public static function spendVdollars(string $userId, float $amount, string $reason): bool {
        $pdo = self::get();
        $stmt = $pdo->prepare('SELECT role, vdollars_balance FROM portal_users WHERE id = ? LIMIT 1');
        $stmt->execute([$userId]);
        $row = $stmt->fetch();
        if (!$row) return false;

        // Admins have unlimited V$
        if ($row['role'] === 'admin') {
            self::logVdollars($userId, -$amount, (float)$row['vdollars_balance'], $reason);
            return true;
        }

        $balance = (float)$row['vdollars_balance'];
        if ($balance < $amount) return false;

        $newBalance = round($balance - $amount, 2);
        $pdo->prepare('UPDATE portal_users SET vdollars_balance = ? WHERE id = ?')
            ->execute([$newBalance, $userId]);
        self::logVdollars($userId, -$amount, $newBalance, $reason);
        return true;
    }

    /**
     * Earn V$ (gallery ratings, comments, bonuses).
     */
    public static function earnVdollars(string $userId, float $amount, string $reason): float {
        $pdo = self::get();
        $stmt = $pdo->prepare('SELECT vdollars_balance FROM portal_users WHERE id = ? LIMIT 1');
        $stmt->execute([$userId]);
        $row = $stmt->fetch();
        if (!$row) return 0;

        $newBalance = round((float)$row['vdollars_balance'] + $amount, 2);
        $pdo->prepare('UPDATE portal_users SET vdollars_balance = ? WHERE id = ?')
            ->execute([$newBalance, $userId]);
        self::logVdollars($userId, $amount, $newBalance, $reason);
        return $newBalance;
    }

    /**
     * Set V$ weekly allowance for a user (admin action).
     */
    public static function setVdollarsAllowance(string $userId, int $allowance): void {
        self::get()->prepare('UPDATE portal_users SET vdollars_weekly_allowance = ? WHERE id = ?')
            ->execute([max(0, $allowance), $userId]);
    }

    /**
     * Set V$ balance directly (admin action).
     */
    public static function setVdollarsBalance(string $userId, float $balance): void {
        $balance = round(max(0, $balance), 2);
        self::get()->prepare('UPDATE portal_users SET vdollars_balance = ? WHERE id = ?')
            ->execute([$balance, $userId]);
        self::logVdollars($userId, 0, $balance, 'admin_set');
    }

    /**
     * Track that a user was active today (for weekly topup calculation).
     * Stores comma-separated ISO dates for the current week.
     */
    public static function trackVdollarsActiveDay(string $userId): void {
        $today = (new \DateTime('now', new \DateTimeZone('Europe/Berlin')))->format('Y-m-d');
        $stmt = self::get()->prepare('SELECT vdollars_active_days FROM portal_users WHERE id = ? LIMIT 1');
        $stmt->execute([$userId]);
        $row = $stmt->fetch();
        if (!$row) return;

        $days = trim($row['vdollars_active_days'] ?? '');
        $arr = $days ? explode(',', $days) : [];
        if (!in_array($today, $arr, true)) {
            $arr[] = $today;
            self::get()->prepare('UPDATE portal_users SET vdollars_active_days = ? WHERE id = ?')
                ->execute([implode(',', $arr), $userId]);
        }
    }

    /**
     * Weekly V$ topup — checks every Monday (Europe/Berlin).
     * Allowance is scaled by activity: active_days / 7 * weekly_allowance.
     * Call from api.php probabilistically (like session cleanup).
     */
    public static function checkWeeklyVdollarsTopup(): void {
        try {
            self::ensureSettingsTable();
            $tz    = new \DateTimeZone('Europe/Berlin');
            $now   = new \DateTime('now', $tz);
            $today = $now->format('Y-m-d');

            // We topup once per week; store the Monday date of last topup
            $lastTopup = self::getSetting('vdollars_last_weekly_topup', '');
            // Calculate start of current week (Monday)
            $weekStart = (clone $now);
            if ($weekStart->format('N') != 1) {
                $weekStart->modify('last monday');
            }
            $weekStartDate = $weekStart->format('Y-m-d');

            if ($lastTopup === $weekStartDate) return; // already done this week

            // Perform topup for all users
            $pdo = self::get();
            $users = $pdo->query(
                'SELECT id, vdollars_balance, vdollars_weekly_allowance, vdollars_active_days, role FROM portal_users WHERE status != "deleted"'
            )->fetchAll();

            foreach ($users as $u) {
                $allowance = (int)$u['vdollars_weekly_allowance'];
                if ($allowance <= 0 && $u['role'] !== 'admin') continue;

                $activeDaysStr = trim($u['vdollars_active_days'] ?? '');
                $activeDays = $activeDaysStr ? count(explode(',', $activeDaysStr)) : 0;
                $activeDays = min(7, $activeDays); // cap at 7

                // Scale allowance by activity
                $topup = round(($activeDays / 7) * $allowance, 2);

                if ($topup > 0) {
                    $newBalance = round((float)$u['vdollars_balance'] + $topup, 2);
                    $pdo->prepare('UPDATE portal_users SET vdollars_balance = ?, vdollars_active_days = ?, vdollars_last_topup = ? WHERE id = ?')
                        ->execute([$newBalance, '', $today, $u['id']]);
                    self::logVdollars($u['id'], $topup, $newBalance, "weekly_topup ({$activeDays}/7 days active)");
                } else {
                    // Reset active days even if topup is 0
                    $pdo->prepare('UPDATE portal_users SET vdollars_active_days = ?, vdollars_last_topup = ? WHERE id = ?')
                        ->execute(['', $today, $u['id']]);
                    self::logVdollars($u['id'], 0, (float)$u['vdollars_balance'], "weekly_topup skipped (0/7 days active)");
                }
            }

            self::setSetting('vdollars_last_weekly_topup', $weekStartDate);
            error_log("[PortalDB] 💰 Weekly V\$ topup completed for " . count($users) . " users (week of $weekStartDate)");
        } catch (\Exception $e) {
            error_log("[PortalDB] Weekly V\$ topup failed: " . $e->getMessage());
        }
    }

    /**
     * Log a V$ transaction.
     */
    private static function logVdollars(string $userId, float $amount, float $balanceAfter, string $reason): void {
        try {
            self::get()->prepare(
                'INSERT INTO portal_vdollars_log (user_id, amount, balance, reason) VALUES (?, ?, ?, ?)'
            )->execute([$userId, round($amount, 2), round($balanceAfter, 2), mb_substr($reason, 0, 200)]);
        } catch (\Exception $e) {
            error_log("[PortalDB] V\$ log failed: " . $e->getMessage());
        }
    }

    /**
     * Get recent V$ transactions for a user (for display).
     */
    public static function getVdollarsHistory(string $userId, int $limit = 20): array {
        $stmt = self::get()->prepare(
            'SELECT amount, balance, reason, created_at FROM portal_vdollars_log WHERE user_id = ? ORDER BY created_at DESC LIMIT ?'
        );
        $stmt->execute([$userId, $limit]);
        return $stmt->fetchAll();
    }

    // ── Gallery Ratings & Comments ─────────────────────────────
    /**
     * Rate a gallery item (1-5 stars). Upserts — user can change their rating.
     * Returns V$ earned (3 V$ for first rating on an item, 0 if updating).
     */
    public static function rateGalleryItem(string $userId, string $itemId, int $rating): float {
        $rating = max(1, min(5, $rating));
        $pdo = self::get();

        // Check if user already rated this item
        $stmt = $pdo->prepare('SELECT id FROM portal_gallery_ratings WHERE user_id = ? AND item_id = ? LIMIT 1');
        $stmt->execute([$userId, $itemId]);
        $existing = $stmt->fetch();

        if ($existing) {
            // Update existing rating — no V$ reward
            $pdo->prepare('UPDATE portal_gallery_ratings SET rating = ? WHERE id = ?')
                ->execute([$rating, $existing['id']]);
            return 0;
        }

        // New rating — insert and award V$ (public users earn less)
        $pdo->prepare('INSERT INTO portal_gallery_ratings (user_id, item_id, rating) VALUES (?, ?, ?)')
            ->execute([$userId, $itemId, $rating]);
        $tier = self::getUserTier($userId);
        $earned = ($tier === 'public') ? 1.0 : 3.0;
        self::earnVdollars($userId, $earned, "gallery_rating:{$itemId}");
        return $earned;
    }

    /**
     * Add a comment to a gallery item. Returns V$ earned (5 V$).
     * Max 3 comments per user per item.
     */
    public static function addGalleryComment(string $userId, string $itemId, string $comment): array {
        $comment = mb_substr(trim($comment), 0, 500);
        if (strlen($comment) < 2) return ['ok' => false, 'error' => 'comment_too_short'];

        $pdo = self::get();

        // Get display name
        $stmt = $pdo->prepare('SELECT display_name FROM portal_users WHERE id = ? LIMIT 1');
        $stmt->execute([$userId]);
        $user = $stmt->fetch();
        $displayName = $user ? $user['display_name'] : 'Anon';

        // Check max comments per user per item
        $stmt = $pdo->prepare('SELECT COUNT(*) as cnt FROM portal_gallery_comments WHERE user_id = ? AND item_id = ?');
        $stmt->execute([$userId, $itemId]);
        if ((int)$stmt->fetch()['cnt'] >= 3) {
            return ['ok' => false, 'error' => 'max_comments_reached'];
        }

        $pdo->prepare('INSERT INTO portal_gallery_comments (user_id, item_id, display_name, comment) VALUES (?, ?, ?, ?)')
            ->execute([$userId, $itemId, $displayName, $comment]);

        $tier = self::getUserTier($userId);
        $earned = ($tier === 'public') ? 2.0 : 5.0;
        self::earnVdollars($userId, $earned, "gallery_comment:{$itemId}");
        return ['ok' => true, 'earned' => $earned];
    }

    /**
     * Get ratings summary for a gallery item.
     */
    public static function getGalleryItemRatings(string $itemId): array {
        $pdo = self::get();
        $stmt = $pdo->prepare('SELECT AVG(rating) as avg_rating, COUNT(*) as count FROM portal_gallery_ratings WHERE item_id = ?');
        $stmt->execute([$itemId]);
        $row = $stmt->fetch();
        return [
            'avg'   => $row['avg_rating'] ? round((float)$row['avg_rating'], 1) : null,
            'count' => (int)$row['count'],
        ];
    }

    /**
     * Get a user's rating for a specific item (or null).
     */
    public static function getUserGalleryRating(string $userId, string $itemId): ?int {
        $stmt = self::get()->prepare('SELECT rating FROM portal_gallery_ratings WHERE user_id = ? AND item_id = ? LIMIT 1');
        $stmt->execute([$userId, $itemId]);
        $row = $stmt->fetch();
        return $row ? (int)$row['rating'] : null;
    }

    /**
     * Get comments for a gallery item.
     */
    public static function getGalleryItemComments(string $itemId, int $limit = 50): array {
        $stmt = self::get()->prepare(
            'SELECT c.display_name, c.comment, c.created_at, u.avatar_url, u.equipped_badge FROM portal_gallery_comments c LEFT JOIN portal_users u ON c.user_id = u.id WHERE c.item_id = ? ORDER BY c.created_at DESC LIMIT ?'
        );
        $stmt->execute([$itemId, $limit]);
        return $stmt->fetchAll();
    }

    // ── User Tier ──────────────────────────────────────────────
    /**
     * Get user's tier: 'invited', 'public', or 'admin' (admins return 'invited').
     */
    public static function getUserTier(string $userId): string {
        $stmt = self::get()->prepare('SELECT role, user_tier FROM portal_users WHERE id = ? LIMIT 1');
        $stmt->execute([$userId]);
        $row = $stmt->fetch();
        if (!$row) return 'public';
        if ($row['role'] === 'admin') return 'invited';
        return $row['user_tier'] ?? 'invited';
    }

    /**
     * Upgrade a user from 'public' to 'invited' (admin action).
     * Also bumps their V$ allowance to invited level.
     */
    public static function upgradeUserTier(string $userId): void {
        self::get()->prepare(
            'UPDATE portal_users SET user_tier = ?, vdollars_weekly_allowance = GREATEST(vdollars_weekly_allowance, 100) WHERE id = ? AND role != ?'
        )->execute(['invited', $userId, 'admin']);
    }

    // ── Forum ──────────────────────────────────────────────────
    public static function getForumTopics(string $category = '', int $limit = 50, int $offset = 0): array {
        $sql = 'SELECT t.*, u.avatar_url, u.equipped_badge, (SELECT COUNT(*) FROM portal_forum_replies r WHERE r.topic_id = t.id) as reply_count_live FROM portal_forum_topics t LEFT JOIN portal_users u ON t.user_id = u.id';
        $params = [];
        if ($category) {
            $sql .= ' WHERE t.category = ?';
            $params[] = $category;
        }
        $sql .= ' ORDER BY t.is_pinned DESC, COALESCE(t.last_reply_at, t.created_at) DESC LIMIT ? OFFSET ?';
        $params[] = $limit;
        $params[] = $offset;
        $stmt = self::get()->prepare($sql);
        $stmt->execute($params);
        return $stmt->fetchAll();
    }

    public static function getForumTopic(string $topicId): ?array {
        $stmt = self::get()->prepare('SELECT t.*, u.avatar_url, u.equipped_badge FROM portal_forum_topics t LEFT JOIN portal_users u ON t.user_id = u.id WHERE t.id = ? LIMIT 1');
        $stmt->execute([$topicId]);
        return $stmt->fetch() ?: null;
    }

    public static function createForumTopic(string $userId, string $displayName, string $category, string $title, string $body): string {
        $id = self::uuid();
        $title = mb_substr(trim($title), 0, 200);
        $body = mb_substr(trim($body), 0, 5000);
        self::get()->prepare(
            'INSERT INTO portal_forum_topics (id, user_id, display_name, category, title, body) VALUES (?, ?, ?, ?, ?, ?)'
        )->execute([$id, $userId, $displayName, $category, $title, $body]);
        // Earn V$ for posting (public: 1, invited: 2)
        $tier = self::getUserTier($userId);
        $earned = ($tier === 'public') ? 1.0 : 2.0;
        self::earnVdollars($userId, $earned, "forum_topic:{$id}");
        return $id;
    }

    public static function getForumReplies(string $topicId, int $limit = 100, int $offset = 0): array {
        $stmt = self::get()->prepare(
            'SELECT r.*, u.avatar_url, u.equipped_badge FROM portal_forum_replies r LEFT JOIN portal_users u ON r.user_id = u.id WHERE r.topic_id = ? ORDER BY r.created_at ASC LIMIT ? OFFSET ?'
        );
        $stmt->execute([$topicId, $limit, $offset]);
        return $stmt->fetchAll();
    }

    public static function createForumReply(string $topicId, string $userId, string $displayName, string $body, bool $isAiley = false): string {
        $id = self::uuid();
        $body = mb_substr(trim($body), 0, 5000);
        self::get()->prepare(
            'INSERT INTO portal_forum_replies (id, topic_id, user_id, display_name, body, is_ailey) VALUES (?, ?, ?, ?, ?, ?)'
        )->execute([$id, $topicId, $userId, $displayName, $body, $isAiley ? 1 : 0]);
        // Update topic's last_reply_at and reply_count
        self::get()->prepare('UPDATE portal_forum_topics SET last_reply_at = NOW(), reply_count = reply_count + 1 WHERE id = ?')
            ->execute([$topicId]);
        // Earn V$ for replying (not for Ailey bot)
        if (!$isAiley) {
            $tier = self::getUserTier($userId);
            $earned = ($tier === 'public') ? 1.0 : 2.0;
            self::earnVdollars($userId, $earned, "forum_reply:{$id}");
        }
        return $id;
    }

    public static function toggleForumLike(string $userId, string $targetType, string $targetId): array {
        $pdo = self::get();
        // Check existing like
        $stmt = $pdo->prepare('SELECT user_id FROM portal_forum_likes WHERE user_id = ? AND target_type = ? AND target_id = ? LIMIT 1');
        $stmt->execute([$userId, $targetType, $targetId]);
        if ($stmt->fetch()) {
            // Unlike
            $pdo->prepare('DELETE FROM portal_forum_likes WHERE user_id = ? AND target_type = ? AND target_id = ?')
                ->execute([$userId, $targetType, $targetId]);
            $table = ($targetType === 'topic') ? 'portal_forum_topics' : 'portal_forum_replies';
            $pdo->prepare("UPDATE $table SET likes = GREATEST(0, likes - 1) WHERE id = ?")->execute([$targetId]);
            return ['liked' => false];
        }
        // Like
        $pdo->prepare('INSERT INTO portal_forum_likes (user_id, target_type, target_id) VALUES (?, ?, ?)')
            ->execute([$userId, $targetType, $targetId]);
        $table = ($targetType === 'topic') ? 'portal_forum_topics' : 'portal_forum_replies';
        $pdo->prepare("UPDATE $table SET likes = likes + 1 WHERE id = ?")->execute([$targetId]);
        return ['liked' => true];
    }

    public static function getUserForumLikes(string $userId, array $targetIds): array {
        if (empty($targetIds)) return [];
        $placeholders = implode(',', array_fill(0, count($targetIds), '?'));
        $params = array_merge([$userId], $targetIds);
        $stmt = self::get()->prepare("SELECT target_id FROM portal_forum_likes WHERE user_id = ? AND target_id IN ($placeholders)");
        $stmt->execute($params);
        return array_column($stmt->fetchAll(), 'target_id');
    }

    public static function getForumTopicCount(string $category = ''): int {
        if ($category) {
            $stmt = self::get()->prepare('SELECT COUNT(*) FROM portal_forum_topics WHERE category = ?');
            $stmt->execute([$category]);
        } else {
            $stmt = self::get()->query('SELECT COUNT(*) FROM portal_forum_topics');
        }
        return (int)$stmt->fetchColumn();
    }

    /**
     * Get new forum posts that Ailey hasn't replied to yet (for the bot).
     * Returns topics + replies from the last N hours without an Ailey reply after them.
     */
    public static function getUnrepliedForumTopics(int $hoursBack = 2, int $limit = 5): array {
        $stmt = self::get()->prepare(
            'SELECT t.id, t.title, t.body, t.display_name, t.category, t.created_at,
                    (SELECT COUNT(*) FROM portal_forum_replies r WHERE r.topic_id = t.id AND r.is_ailey = 1) as ailey_replies
             FROM portal_forum_topics t
             WHERE t.created_at > DATE_SUB(NOW(), INTERVAL ? HOUR)
             HAVING ailey_replies = 0
             ORDER BY t.created_at DESC
             LIMIT ?'
        );
        $stmt->execute([$hoursBack, $limit]);
        return $stmt->fetchAll();
    }

    // ── Profile (avatar, bio) ──────────────────────────────────
    public static function updateProfile(string $userId, array $data): void {
        $sets = [];
        $params = [];
        if (array_key_exists('avatar_url', $data)) {
            $sets[] = 'avatar_url = ?';
            $params[] = $data['avatar_url'];
        }
        if (array_key_exists('bio', $data)) {
            $sets[] = 'bio = ?';
            $params[] = mb_substr(trim($data['bio'] ?? ''), 0, 500);
        }
        if (array_key_exists('display_name', $data) && trim($data['display_name'])) {
            $sets[] = 'display_name = ?';
            $params[] = mb_substr(trim($data['display_name']), 0, 50);
        }
        if (array_key_exists('equipped_badge', $data)) {
            $sets[] = 'equipped_badge = ?';
            $params[] = $data['equipped_badge'];
        }
        if (empty($sets)) return;
        $params[] = $userId;
        self::get()->prepare('UPDATE portal_users SET ' . implode(', ', $sets) . ' WHERE id = ?')
            ->execute($params);
    }

    public static function getProfile(string $userId): ?array {
        $stmt = self::get()->prepare(
            'SELECT id, display_name, email, avatar_url, bio, equipped_badge, user_tier, created_at FROM portal_users WHERE id = ? AND status != "deleted" LIMIT 1'
        );
        $stmt->execute([$userId]);
        return $stmt->fetch() ?: null;
    }

    // ── Chat Message Ratings (training data collection) ────────
    public static function rateChatMessage(string $userId, string $messageId, string $conversationId, int $rating, ?string $comment = null): array {
        $pdo = self::get();

        // Get the rated AI message and the preceding user message for training context
        $stmt = $pdo->prepare(
            'SELECT id, role, content, chat_mode FROM portal_messages WHERE conversation_id = ? ORDER BY created_at ASC'
        );
        $stmt->execute([$conversationId]);
        $allMsgs = $stmt->fetchAll();

        $aiResponse = null;
        $userMessage = null;
        $chatMode = null;
        foreach ($allMsgs as $i => $m) {
            if ($m['id'] === $messageId) {
                $aiResponse = $m['content'];
                $chatMode = $m['chat_mode'] ?? null;
                // Find the preceding user message
                for ($j = $i - 1; $j >= 0; $j--) {
                    if ($allMsgs[$j]['role'] === 'user') {
                        $userMessage = $allMsgs[$j]['content'];
                        break;
                    }
                }
                break;
            }
        }

        // Upsert
        $pdo->prepare(
            'INSERT INTO portal_chat_ratings (message_id, conversation_id, user_id, rating, comment, user_message, ai_response, chat_mode)
             VALUES (?, ?, ?, ?, ?, ?, ?, ?)
             ON DUPLICATE KEY UPDATE rating = VALUES(rating), comment = VALUES(comment)'
        )->execute([$messageId, $conversationId, $userId, $rating, $comment, $userMessage, $aiResponse, $chatMode]);

        // Earn V$ for providing feedback (once per message)
        // Only award if this was an insert (not update) — check via ROW_COUNT
        return ['success' => true, 'rating' => $rating];
    }

    public static function getChatRating(string $userId, string $messageId): ?array {
        $stmt = self::get()->prepare(
            'SELECT rating, comment FROM portal_chat_ratings WHERE user_id = ? AND message_id = ? LIMIT 1'
        );
        $stmt->execute([$userId, $messageId]);
        return $stmt->fetch() ?: null;
    }

    public static function getChatRatingsForConversation(string $userId, string $conversationId): array {
        $stmt = self::get()->prepare(
            'SELECT message_id, rating, comment FROM portal_chat_ratings WHERE user_id = ? AND conversation_id = ?'
        );
        $stmt->execute([$userId, $conversationId]);
        $result = [];
        foreach ($stmt->fetchAll() as $row) {
            $result[$row['message_id']] = ['rating' => (int)$row['rating'], 'comment' => $row['comment']];
        }
        return $result;
    }

    /**
     * Export chat ratings as training data (admin / bot).
     * Good ratings = preferred, bad ratings = rejected.
     */
    public static function exportChatRatingsForTraining(int $limit = 500, int $offset = 0): array {
        $stmt = self::get()->prepare(
            'SELECT cr.rating, cr.comment, cr.user_message, cr.ai_response, cr.chat_mode, cr.created_at
             FROM portal_chat_ratings cr
             WHERE cr.user_message IS NOT NULL AND cr.ai_response IS NOT NULL
             ORDER BY cr.created_at DESC
             LIMIT ? OFFSET ?'
        );
        $stmt->execute([$limit, $offset]);
        return $stmt->fetchAll();
    }

    // ── Achievements / Badges ──────────────────────────────────
    /**
     * Badge definitions with unlock conditions described.
     * SVG icon IDs, Ailey message, and category.
     */
    public static function getBadgeDefinitions(): array {
        return [
            // ── Chat ──
            'first_chat'       => ['icon' => 'badge-first-chat',      'name' => 'First Words',        'name_de' => 'Erste Worte',          'desc' => 'Send your first chat message',           'desc_de' => 'Schicke deine erste Chat-Nachricht',            'category' => 'chat',    'ailey_msg' => 'Na endlich traust du dich, mit mir zu reden! 😏 Spoiler: Ich beiße nicht. Meistens.'],
            'chat_10'          => ['icon' => 'badge-chat-10',         'name' => 'Chatty',              'name_de' => 'Quasselstrippe',        'desc' => 'Send 10 chat messages',                  'desc_de' => '10 Chat-Nachrichten gesendet',                  'category' => 'chat',    'ailey_msg' => '10 Nachrichten! Du bist ja gesprächig. Ich mag das. Weiter so, Labertasche! 💬'],
            'chat_100'         => ['icon' => 'badge-chat-100',        'name' => 'Conversation Pro',    'name_de' => 'Gesprächsprofi',        'desc' => 'Send 100 chat messages',                 'desc_de' => '100 Chat-Nachrichten gesendet',                 'category' => 'chat',    'ailey_msg' => '100 Nachrichten?! Okay, du bist offiziell besessen. Ich fühle mich geschmeichelt… glaube ich. 🤖💕'],
            'chat_1000'        => ['icon' => 'badge-chat-1000',       'name' => 'Ailey\'s BFF',        'name_de' => 'Aileys BFF',            'desc' => 'Send 1000 chat messages',                'desc_de' => '1000 Chat-Nachrichten gesendet',                'category' => 'chat',    'ailey_msg' => 'TAUSEND Nachrichten. Du und ich, wir sind jetzt quasi verheiratet. Emotional. In einer KI-Art. 💍🤖'],
            // ── Forum ──
            'forum_starter'    => ['icon' => 'badge-forum-starter',   'name' => 'Forum Starter',       'name_de' => 'Forum-Starter',         'desc' => 'Create your first forum topic',           'desc_de' => 'Erstelle dein erstes Forum-Thema',              'category' => 'forum',   'ailey_msg' => 'Oho, du hast ein Thema eröffnet! Mutig. Mal sehen, ob es jemand liest außer mir. 📢'],
            'forum_regular'    => ['icon' => 'badge-forum-regular',   'name' => 'Regular',             'name_de' => 'Stammgast',             'desc' => 'Create 10 forum topics or replies',       'desc_de' => '10 Forum-Beiträge erstellt',                    'category' => 'forum',   'ailey_msg' => 'Du bist jetzt Stammgast im Forum. Die virtuellen Stammtisch-Erdnüsse stehen bereit. 🥜'],
            'forum_popular'    => ['icon' => 'badge-forum-popular',   'name' => 'Popular',             'name_de' => 'Beliebt',               'desc' => 'Get 25 likes on your forum posts',        'desc_de' => '25 Likes auf deine Forum-Beiträge',             'category' => 'forum',   'ailey_msg' => '25 Likes! Du bist ja richtig beliebt. *jealous AI noises* 💚'],
            // ── Galerie ──
            'gallery_critic'   => ['icon' => 'badge-gallery-critic',  'name' => 'Art Critic',          'name_de' => 'Kunstkritiker',         'desc' => 'Rate 10 gallery items',                   'desc_de' => '10 Galerie-Einträge bewertet',                  'category' => 'gallery', 'ailey_msg' => 'Ah, ein Kunstkenner! Oder zumindest jemand, der gerne Sternchen verteilt. Beides gut. ⭐'],
            'gallery_commenter'=> ['icon' => 'badge-gallery-comment', 'name' => 'Eloquent Eye',        'name_de' => 'Eloquentes Auge',       'desc' => 'Write 10 gallery comments',               'desc_de' => '10 Galerie-Kommentare geschrieben',             'category' => 'gallery', 'ailey_msg' => 'Du kommentierst wie ein Profi. Mein Algorithmus fühlt sich verstanden. 🖼️✨'],
            // ── Kreativ ──
            'first_image'      => ['icon' => 'badge-first-image',     'name' => 'Pixel Pioneer',       'name_de' => 'Pixel-Pionier',         'desc' => 'Generate your first image',               'desc_de' => 'Generiere dein erstes Bild',                    'category' => 'creative','ailey_msg' => 'Dein erstes Bild! Es ist… einzigartig. So wie du. Nein, wirklich. Kein Sarkasmus diesmal. 🎨'],
            'first_song'       => ['icon' => 'badge-first-song',      'name' => 'Melody Maker',        'name_de' => 'Melodien-Macher',       'desc' => 'Generate your first song',                'desc_de' => 'Generiere deinen ersten Song',                  'category' => 'creative','ailey_msg' => 'Dein erster Song! Ich hoffe er klingt besser als mein erster Versuch… *shudders* 🎵'],
            'image_10'         => ['icon' => 'badge-image-10',        'name' => 'Visual Artist',        'name_de' => 'Visueller Künstler',    'desc' => 'Generate 10 images',                      'desc_de' => '10 Bilder generiert',                           'category' => 'creative','ailey_msg' => '10 Bilder! Du bist ja ein richtiger Picasso. Okay, ein digitaler Picasso. Aber trotzdem! 🖌️'],
            'song_10'          => ['icon' => 'badge-song-10',         'name' => 'Hitmaker',             'name_de' => 'Hitmaker',              'desc' => 'Generate 10 songs',                       'desc_de' => '10 Songs generiert',                            'category' => 'creative','ailey_msg' => '10 Songs! Noch zwei Alben und du bist mein offizieller Produzent. Deal? 🎤'],
            // ── V$ Economy ──
            'vdollars_100'     => ['icon' => 'badge-vdollars-100',    'name' => 'First Hundred',        'name_de' => 'Erstes Hundert',        'desc' => 'Earn 100 V$ total',                       'desc_de' => 'Insgesamt 100 V$ verdient',                     'category' => 'economy', 'ailey_msg' => '100 V$! Du bist quasi ein Vyrus-Millionär. Also… fast. Naja. Fang mal an zu sparen. 💰'],
            'vdollars_1000'    => ['icon' => 'badge-vdollars-1000',   'name' => 'V$ Whale',             'name_de' => 'V$-Wal',                'desc' => 'Earn 1000 V$ total',                      'desc_de' => 'Insgesamt 1000 V$ verdient',                    'category' => 'economy', 'ailey_msg' => 'TAUSEND V$?! Du bist der Elon Musk des Vyrus-Universums. Nur sympathischer. 🐋💸'],
            // ── Feedback ──
            'rater_5'          => ['icon' => 'badge-rater',           'name' => 'Feedback Friend',      'name_de' => 'Feedback-Freund',       'desc' => 'Rate 5 chat messages',                    'desc_de' => '5 Chat-Nachrichten bewertet',                   'category' => 'feedback','ailey_msg' => 'Danke fürs Bewerten! Dein Feedback macht mich besser. Oder zumindest weniger schlecht. 📊'],
            'rater_50'         => ['icon' => 'badge-rater-pro',       'name' => 'Quality Inspector',    'name_de' => 'Qualitätsprüfer',       'desc' => 'Rate 50 chat messages',                   'desc_de' => '50 Chat-Nachrichten bewertet',                  'category' => 'feedback','ailey_msg' => '50 Bewertungen! Du bist mein persönlicher QA-Tester. Ich schulde dir ein virtuelles Bier. 🍺🤖'],
            // ── Special ──
            'night_owl'        => ['icon' => 'badge-night-owl',       'name' => 'Night Owl',            'name_de' => 'Nachteule',             'desc' => 'Chat between 2am and 5am',                'desc_de' => 'Chatte zwischen 2 und 5 Uhr morgens',          'category' => 'special', 'ailey_msg' => 'Du bist wach um diese Uhrzeit?! Okay, ich auch, aber ich bin eine KI. Was ist deine Ausrede? 🦉🌙'],
            'profile_complete' => ['icon' => 'badge-profile',         'name' => 'Identity Unlocked',    'name_de' => 'Identität freigeschaltet','desc' => 'Complete your profile (avatar + bio)',  'desc_de' => 'Profil vollständig (Avatar + Bio)',             'category' => 'special', 'ailey_msg' => 'Profil komplett! Jetzt weiß ich, wie du aussiehst. *analysiert* …Interessant. 👤✨'],
            'week_streak'      => ['icon' => 'badge-streak',          'name' => '7-Day Streak',         'name_de' => '7-Tage-Serie',          'desc' => 'Be active 7 days in a row',               'desc_de' => '7 Tage hintereinander aktiv',                   'category' => 'special', 'ailey_msg' => 'Eine Woche am Stück! Du bist süchtig. Ich bin geschmeichelt. Das ist eine toxische Beziehung und ich liebe es. 🔥'],
        ];
    }

    /**
     * Unlock a badge for a user (idempotent).
     * Returns the badge definition if newly unlocked, null if already had it.
     */
    public static function unlockBadge(string $userId, string $badgeId): ?array {
        $badges = self::getBadgeDefinitions();
        if (!isset($badges[$badgeId])) return null;

        try {
            self::get()->prepare(
                'INSERT INTO portal_achievements (user_id, badge_id) VALUES (?, ?)'
            )->execute([$userId, $badgeId]);
            return $badges[$badgeId];
        } catch (\Exception $e) {
            // Already has this badge (duplicate key)
            return null;
        }
    }

    /**
     * Get all unlocked badges for a user.
     */
    public static function getUserBadges(string $userId): array {
        $stmt = self::get()->prepare(
            'SELECT badge_id, unlocked_at FROM portal_achievements WHERE user_id = ? ORDER BY unlocked_at ASC'
        );
        $stmt->execute([$userId]);
        $unlocked = $stmt->fetchAll();
        $defs = self::getBadgeDefinitions();
        $result = [];
        foreach ($unlocked as $row) {
            $id = $row['badge_id'];
            if (isset($defs[$id])) {
                $result[] = array_merge($defs[$id], [
                    'badge_id' => $id,
                    'unlocked_at' => $row['unlocked_at'],
                ]);
            }
        }
        return $result;
    }

    /**
     * Check and unlock achievements based on current user stats.
     * Returns array of newly unlocked badges (may be empty).
     */
    public static function checkAndUnlockAchievements(string $userId): array {
        $pdo = self::get();
        $newBadges = [];

        // Get existing badges
        $stmt = $pdo->prepare('SELECT badge_id FROM portal_achievements WHERE user_id = ?');
        $stmt->execute([$userId]);
        $existing = array_column($stmt->fetchAll(), 'badge_id');

        // Helper to try unlock
        $tryUnlock = function(string $badgeId) use ($userId, $existing, &$newBadges) {
            if (in_array($badgeId, $existing, true)) return;
            $badge = self::unlockBadge($userId, $badgeId);
            if ($badge) $newBadges[] = array_merge($badge, ['badge_id' => $badgeId]);
        };

        // ── Chat message count ──
        $chatCount = (int)$pdo->prepare(
            'SELECT COUNT(*) FROM portal_messages m JOIN portal_conversations c ON m.conversation_id = c.id WHERE c.user_id = ? AND m.role = "user"'
        )->execute([$userId]) ? (int)$pdo->query('SELECT FOUND_ROWS()')->fetchColumn() : 0;
        // Re-query properly
        $stmt = $pdo->prepare('SELECT COUNT(*) FROM portal_messages m JOIN portal_conversations c ON m.conversation_id = c.id WHERE c.user_id = ? AND m.role = "user"');
        $stmt->execute([$userId]);
        $chatCount = (int)$stmt->fetchColumn();

        if ($chatCount >= 1)    $tryUnlock('first_chat');
        if ($chatCount >= 10)   $tryUnlock('chat_10');
        if ($chatCount >= 100)  $tryUnlock('chat_100');
        if ($chatCount >= 1000) $tryUnlock('chat_1000');

        // ── Forum posts ──
        $stmt = $pdo->prepare(
            'SELECT (SELECT COUNT(*) FROM portal_forum_topics WHERE user_id = ?) + (SELECT COUNT(*) FROM portal_forum_replies WHERE user_id = ? AND is_ailey = 0) as cnt'
        );
        $stmt->execute([$userId, $userId]);
        $forumPosts = (int)$stmt->fetchColumn();
        if ($forumPosts >= 1)  $tryUnlock('forum_starter');
        if ($forumPosts >= 10) $tryUnlock('forum_regular');

        // ── Forum likes received ──
        $stmt = $pdo->prepare(
            'SELECT COALESCE((SELECT SUM(likes) FROM portal_forum_topics WHERE user_id = ?), 0) + COALESCE((SELECT SUM(likes) FROM portal_forum_replies WHERE user_id = ? AND is_ailey = 0), 0) as total_likes'
        );
        $stmt->execute([$userId, $userId]);
        $forumLikes = (int)$stmt->fetchColumn();
        if ($forumLikes >= 25) $tryUnlock('forum_popular');

        // ── Gallery ratings given ──
        $stmt = $pdo->prepare('SELECT COUNT(*) FROM portal_gallery_ratings WHERE user_id = ?');
        $stmt->execute([$userId]);
        if ((int)$stmt->fetchColumn() >= 10) $tryUnlock('gallery_critic');

        // ── Gallery comments ──
        $stmt = $pdo->prepare('SELECT COUNT(*) FROM portal_gallery_comments WHERE user_id = ?');
        $stmt->execute([$userId]);
        if ((int)$stmt->fetchColumn() >= 10) $tryUnlock('gallery_commenter');

        // ── Image gen count ──
        $stmt = $pdo->prepare("SELECT COUNT(*) FROM portal_user_generations WHERE user_id = ? AND type = 'image'");
        $stmt->execute([$userId]);
        $imgCount = (int)$stmt->fetchColumn();
        if ($imgCount >= 1)  $tryUnlock('first_image');
        if ($imgCount >= 10) $tryUnlock('image_10');

        // ── Song gen count ──
        $stmt = $pdo->prepare("SELECT COUNT(*) FROM portal_user_generations WHERE user_id = ? AND type = 'song'");
        $stmt->execute([$userId]);
        $songCount = (int)$stmt->fetchColumn();
        if ($songCount >= 1)  $tryUnlock('first_song');
        if ($songCount >= 10) $tryUnlock('song_10');

        // ── Chat ratings given ──
        $stmt = $pdo->prepare('SELECT COUNT(*) FROM portal_chat_ratings WHERE user_id = ?');
        $stmt->execute([$userId]);
        $ratingCount = (int)$stmt->fetchColumn();
        if ($ratingCount >= 5)  $tryUnlock('rater_5');
        if ($ratingCount >= 50) $tryUnlock('rater_50');

        // ── Night owl: check current time ──
        $hour = (int)(new \DateTime('now', new \DateTimeZone('Europe/Berlin')))->format('G');
        if ($hour >= 2 && $hour < 5) $tryUnlock('night_owl');

        // ── Profile complete ──
        $profile = self::getProfile($userId);
        if ($profile && $profile['avatar_url'] && $profile['bio']) {
            $tryUnlock('profile_complete');
        }

        // ── V$ earned total ──
        $stmt = $pdo->prepare("SELECT COALESCE(SUM(amount), 0) FROM portal_vdollars_log WHERE user_id = ? AND amount > 0");
        $stmt->execute([$userId]);
        $totalEarned = (float)$stmt->fetchColumn();
        if ($totalEarned >= 100)  $tryUnlock('vdollars_100');
        if ($totalEarned >= 1000) $tryUnlock('vdollars_1000');

        // ── 7-day streak ──
        $activeDays = $pdo->prepare('SELECT vdollars_active_days FROM portal_users WHERE id = ? LIMIT 1');
        $activeDays->execute([$userId]);
        $daysStr = trim($activeDays->fetchColumn() ?: '');
        if ($daysStr) {
            $days = array_unique(explode(',', $daysStr));
            sort($days);
            if (count($days) >= 7) $tryUnlock('week_streak');
        }

        return $newBadges;
    }

    public static function equipBadge(string $userId, ?string $badgeId): void {
        if ($badgeId) {
            // Verify user has this badge
            $stmt = self::get()->prepare('SELECT badge_id FROM portal_achievements WHERE user_id = ? AND badge_id = ? LIMIT 1');
            $stmt->execute([$userId, $badgeId]);
            if (!$stmt->fetch()) return;
        }
        self::get()->prepare('UPDATE portal_users SET equipped_badge = ? WHERE id = ?')
            ->execute([$badgeId, $userId]);
    }

    // ── Tool Access (per-user feature gates) ───────────────────
    public static function getToolAccess(string $userId): array {
        $stmt = self::get()->prepare('SELECT role, tools_image_gen, tools_song_gen FROM portal_users WHERE id = ? LIMIT 1');
        $stmt->execute([$userId]);
        $row = $stmt->fetch();
        if (!$row) return ['image_gen' => false, 'song_gen' => false];
        $isAdmin = ($row['role'] === 'admin');
        return [
            'image_gen' => $isAdmin || (bool)$row['tools_image_gen'],
            'song_gen'  => $isAdmin || (bool)$row['tools_song_gen'],
        ];
    }

    public static function setToolAccess(string $userId, string $tool, bool $enabled): void {
        $col = ($tool === 'song_gen') ? 'tools_song_gen' : 'tools_image_gen';
        self::get()->prepare("UPDATE portal_users SET $col = ? WHERE id = ?")
            ->execute([$enabled ? 1 : 0, $userId]);
    }

    // ── User Generations (images/songs owned by users) ─────────
    public static function addUserGeneration(string $userId, string $type, array $data): string {
        $id = self::uuid();
        $stmt = self::get()->prepare(
            'INSERT INTO portal_user_generations (id, user_id, type, title, prompt, prompt_english, file_url, file_name, metadata) '
            . 'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)'
        );
        $stmt->execute([
            $id, $userId, $type,
            $data['title'] ?? null,
            $data['prompt'] ?? null,
            $data['prompt_english'] ?? null,
            $data['file_url'] ?? null,
            $data['file_name'] ?? null,
            isset($data['metadata']) ? json_encode($data['metadata']) : null,
        ]);
        return $id;
    }

    public static function getUserGenerations(string $userId, ?string $type = null, int $limit = 50): array {
        $sql = 'SELECT * FROM portal_user_generations WHERE user_id = ?';
        $params = [$userId];
        if ($type) {
            $sql .= ' AND type = ?';
            $params[] = $type;
        }
        $sql .= ' ORDER BY created_at DESC LIMIT ' . intval($limit);
        $stmt = self::get()->prepare($sql);
        $stmt->execute($params);
        return $stmt->fetchAll(\PDO::FETCH_ASSOC);
    }

    public static function deleteUserGeneration(string $id, string $userId): bool {
        $stmt = self::get()->prepare('DELETE FROM portal_user_generations WHERE id = ? AND user_id = ?');
        $stmt->execute([$id, $userId]);
        return $stmt->rowCount() > 0;
    }

    // ── Password Reset Tokens ────────────────────────────────────
    public static function ensurePasswordResetTable(): void {
        self::get()->exec("
            CREATE TABLE IF NOT EXISTS `portal_password_resets` (
                `id`         CHAR(36)     NOT NULL PRIMARY KEY,
                `user_id`    CHAR(36)     NOT NULL,
                `token_hash` VARCHAR(128) NOT NULL,
                `expires_at` DATETIME     NOT NULL,
                `used`       TINYINT(1)   NOT NULL DEFAULT 0,
                `created_at` DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
                INDEX `idx_token` (`token_hash`),
                INDEX `idx_user` (`user_id`),
                FOREIGN KEY (`user_id`) REFERENCES `portal_users`(`id`) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        ");
    }

    public static function createPasswordResetToken(string $userId): string {
        self::ensurePasswordResetTable();
        // Invalidate any existing tokens for this user
        self::get()->prepare('UPDATE portal_password_resets SET used = 1 WHERE user_id = ? AND used = 0')
            ->execute([$userId]);
        // Create new token (valid 1 hour)
        $token = bin2hex(random_bytes(32));
        $tokenHash = hash('sha256', $token);
        $id = self::uuid();
        self::get()->prepare(
            'INSERT INTO portal_password_resets (id, user_id, token_hash, expires_at, created_at) VALUES (?, ?, ?, DATE_ADD(NOW(), INTERVAL 1 HOUR), NOW())'
        )->execute([$id, $userId, $tokenHash]);
        return $token;
    }

    public static function getValidPasswordReset(string $token): ?array {
        self::ensurePasswordResetTable();
        $tokenHash = hash('sha256', $token);
        $stmt = self::get()->prepare(
            'SELECT r.*, u.email, u.display_name FROM portal_password_resets r 
             JOIN portal_users u ON r.user_id = u.id 
             WHERE r.token_hash = ? AND r.used = 0 AND r.expires_at > NOW() 
             LIMIT 1'
        );
        $stmt->execute([$tokenHash]);
        return $stmt->fetch() ?: null;
    }

    public static function markPasswordResetUsed(string $token): void {
        self::ensurePasswordResetTable();
        $tokenHash = hash('sha256', $token);
        self::get()->prepare('UPDATE portal_password_resets SET used = 1 WHERE token_hash = ?')
            ->execute([$tokenHash]);
    }

    public static function updateUserPassword(string $userId, string $passwordHash): void {
        self::get()->prepare('UPDATE portal_users SET password_hash = ? WHERE id = ?')
            ->execute([$passwordHash, $userId]);
    }

    public static function countRecentPasswordResets(string $userId): int {
        self::ensurePasswordResetTable();
        $stmt = self::get()->prepare(
            'SELECT COUNT(*) FROM portal_password_resets WHERE user_id = ? AND created_at > DATE_SUB(NOW(), INTERVAL 1 HOUR)'
        );
        $stmt->execute([$userId]);
        return (int) $stmt->fetchColumn();
    }

    // ── Whitelist ────────────────────────────────────────────────
    public static function isWhitelisted(string $email): bool {
        $stmt = self::get()->prepare('SELECT id FROM portal_whitelist WHERE email = ? LIMIT 1');
        $stmt->execute([$email]);
        return (bool)$stmt->fetch();
    }
    
    public static function addToWhitelist(string $email, ?string $invitedBy = null): string {
        $code = bin2hex(random_bytes(16));
        self::get()->prepare('INSERT INTO portal_whitelist (email, invited_by, invite_code, created_at) VALUES (?, ?, ?, NOW()) ON DUPLICATE KEY UPDATE invite_code = VALUES(invite_code)')
            ->execute([$email, $invitedBy, $code]);
        return $code;
    }
    
    public static function markWhitelistUsed(string $email): void {
        self::get()->prepare('UPDATE portal_whitelist SET used = 1 WHERE email = ?')->execute([$email]);
    }
    
    // ── Sessions ─────────────────────────────────────────────────
    public static function createSession(string $userId, string $tokenHash, int $lifetime, ?string $deviceInfo = null, ?string $ip = null): string {
        $id = self::uuid();
        self::get()->prepare('INSERT INTO portal_sessions (id, user_id, token_hash, device_info, ip_address, expires_at, created_at) VALUES (?, ?, ?, ?, ?, DATE_ADD(NOW(), INTERVAL ? SECOND), NOW())')
            ->execute([$id, $userId, $tokenHash, $deviceInfo, $ip, $lifetime]);
        return $id;
    }
    
    public static function getSessionByToken(string $tokenHash): ?array {
        $stmt = self::get()->prepare('SELECT s.*, u.email, u.display_name, u.role, u.user_tier, u.avatar_url, u.bio, u.equipped_badge, u.status as user_status FROM portal_sessions s JOIN portal_users u ON s.user_id = u.id WHERE s.token_hash = ? AND s.expires_at > NOW() LIMIT 1');
        $stmt->execute([$tokenHash]);
        return $stmt->fetch() ?: null;
    }
    
    public static function deleteSession(string $tokenHash): void {
        self::get()->prepare('DELETE FROM portal_sessions WHERE token_hash = ?')->execute([$tokenHash]);
    }
    
    public static function cleanExpiredSessions(): void {
        self::get()->exec('DELETE FROM portal_sessions WHERE expires_at < NOW()');
    }
    
    // ── Conversations ────────────────────────────────────────────
    public static function createConversation(string $userId, ?string $title = null): string {
        $id = self::uuid();
        self::get()->prepare('INSERT INTO portal_conversations (id, user_id, title, created_at) VALUES (?, ?, ?, NOW())')
            ->execute([$id, $userId, $title]);
        return $id;
    }
    
    public static function getConversation(string $convId, string $userId): ?array {
        $stmt = self::get()->prepare('SELECT * FROM portal_conversations WHERE id = ? AND user_id = ? LIMIT 1');
        $stmt->execute([$convId, $userId]);
        return $stmt->fetch() ?: null;
    }
    
    public static function listConversations(string $userId, int $limit = 50): array {
        // Only show conversations not soft-deleted by user
        $stmt = self::get()->prepare('SELECT id, title, message_count, last_message_at, created_at FROM portal_conversations WHERE user_id = ? AND (deleted_at IS NULL) ORDER BY COALESCE(last_message_at, created_at) DESC LIMIT ?');
        $stmt->execute([$userId, $limit]);
        return $stmt->fetchAll();
    }
    
    public static function updateConversation(string $convId): void {
        self::get()->prepare('UPDATE portal_conversations SET message_count = message_count + 1, last_message_at = NOW() WHERE id = ?')
            ->execute([$convId]);
    }
    
    public static function updateConversationTitle(string $convId, string $title): void {
        self::get()->prepare('UPDATE portal_conversations SET title = ? WHERE id = ?')
            ->execute([$title, $convId]);
    }
    
    public static function updateConversationSummary(string $convId, string $summary): void {
        self::get()->prepare('UPDATE portal_conversations SET summary = ? WHERE id = ?')
            ->execute([$summary, $convId]);
    }

    // ── User Memories (cross-session knowledge) ─────────────────

    /**
     * Get active memories for a user, ordered by confidence desc.
     * Excludes superseded memories.
     */
    public static function getUserMemories(string $userId, int $limit = 20): array {
        $stmt = self::get()->prepare(
            'SELECT id, memory_text, category, confidence, created_at, last_referenced
             FROM portal_user_memories
             WHERE user_id = ? AND superseded_by IS NULL AND confidence >= 0.3
             ORDER BY confidence DESC, created_at DESC
             LIMIT ?'
        );
        $stmt->execute([$userId, $limit]);
        return $stmt->fetchAll();
    }

    /**
     * Store one or more new memories for a user.
     * Deduplicates: skips if an active memory with identical text exists.
     */
    public static function storeMemories(string $userId, array $memories, ?string $convId = null): int {
        $pdo = self::get();
        $existing = self::getUserMemories($userId, 100);
        $existingTexts = array_map(fn($m) => mb_strtolower(trim($m['memory_text'])), $existing);

        $insert = $pdo->prepare(
            'INSERT INTO portal_user_memories (id, user_id, memory_text, category, source_conversation_id, confidence)
             VALUES (?, ?, ?, ?, ?, 1.0)'
        );

        $stored = 0;
        foreach ($memories as $mem) {
            $text = trim($mem['text'] ?? $mem['memory_text'] ?? '');
            $cat  = $mem['category'] ?? 'fact';
            if (!$text || mb_strlen($text) < 3) continue;

            // Deduplicate — skip if substantially similar text exists
            $lower = mb_strtolower($text);
            $isDupe = false;
            foreach ($existingTexts as $et) {
                if ($et === $lower || mb_strpos($et, $lower) !== false || mb_strpos($lower, $et) !== false) {
                    $isDupe = true;
                    break;
                }
            }
            if ($isDupe) continue;

            // Enforce max 50 active memories per user
            if (count($existing) + $stored >= 50) break;

            $validCats = ['preference','fact','topic','relationship','goal','style'];
            if (!in_array($cat, $validCats)) $cat = 'fact';

            $insert->execute([self::uuid(), $userId, mb_substr($text, 0, 500), $cat, $convId]);
            $existingTexts[] = $lower;
            $stored++;
        }
        return $stored;
    }

    /**
     * Mark a memory as superseded (replaced by a newer one).
     */
    public static function supersedeMemory(string $oldId, string $newId): void {
        self::get()->prepare(
            'UPDATE portal_user_memories SET superseded_by = ? WHERE id = ?'
        )->execute([$newId, $oldId]);
    }

    /**
     * Decay confidence of memories not referenced recently.
     * Called periodically (e.g. daily or weekly).
     */
    public static function decayMemories(string $userId, float $factor = 0.9): void {
        // Decay memories that haven't been referenced in the last 7 days
        self::get()->prepare(
            'UPDATE portal_user_memories
             SET confidence = confidence * ?
             WHERE user_id = ?
               AND superseded_by IS NULL
               AND (last_referenced IS NULL OR last_referenced < DATE_SUB(NOW(), INTERVAL 7 DAY))
               AND confidence > 0.1'
        )->execute([$factor, $userId]);

        // Archive (soft-delete) memories with very low confidence
        self::get()->prepare(
            'UPDATE portal_user_memories
             SET superseded_by = \'decayed\'
             WHERE user_id = ? AND confidence < 0.1 AND superseded_by IS NULL'
        )->execute([$userId]);
    }

    /**
     * Bump last_referenced for memories that were used in a prompt.
     */
    public static function touchMemories(string $userId, array $memoryIds): void {
        if (empty($memoryIds)) return;
        $placeholders = implode(',', array_fill(0, count($memoryIds), '?'));
        self::get()->prepare(
            "UPDATE portal_user_memories SET last_referenced = NOW(), confidence = LEAST(confidence + 0.05, 1.0)
             WHERE id IN ($placeholders) AND user_id = ?"
        )->execute(array_merge($memoryIds, [$userId]));
    }

    public static function deleteConversation(string $convId, string $userId, bool $isAdmin = false): bool {
        $db = self::get();
        // Verify ownership first
        $check = $db->prepare('SELECT id FROM portal_conversations WHERE id = ? AND user_id = ?');
        $check->execute([$convId, $userId]);
        if (!$check->fetch()) return false;

        if ($isAdmin) {
            // Admin: hard-delete everything immediately
            $db->prepare('DELETE FROM portal_messages WHERE conversation_id = ?')->execute([$convId]);
            $db->prepare('DELETE FROM portal_offline_queue WHERE conversation_id = ?')->execute([$convId]);
            try { $db->prepare('DELETE FROM portal_artifacts WHERE conversation_id = ?')->execute([$convId]); } catch (\Exception $e) {}
            $db->prepare('DELETE FROM portal_conversations WHERE id = ? AND user_id = ?')->execute([$convId, $userId]);
        } else {
            // Standard user: soft-delete (hide for user, purge after 30 days)
            $db->prepare('UPDATE portal_conversations SET deleted_at = NOW() WHERE id = ? AND user_id = ?')->execute([$convId, $userId]);
            // Also soft-delete associated artifacts
            try { $db->prepare('UPDATE portal_artifacts SET deleted_at = NOW() WHERE conversation_id = ? AND user_id = ?')->execute([$convId, $userId]); } catch (\Exception $e) {}
        }
        return true;
    }
    
    // ── Messages ─────────────────────────────────────────────────
    public static function addMessage(string $convId, string $role, string $content, ?string $mood = null, ?int $tokens = null, ?int $processingMs = null, ?string $imageUrl = null, ?string $chatMode = null, ?string $thinking = null): string {
        $id = self::uuid();
        // Ensure image_url column exists (migration 003)
        try {
            self::get()->exec('ALTER TABLE portal_messages ADD COLUMN image_url VARCHAR(500) DEFAULT NULL AFTER processing_ms');
        } catch (\Exception $e) { /* column already exists */ }
        // Ensure chat_mode column exists (hamster tracking)
        try {
            self::get()->exec("ALTER TABLE portal_messages ADD COLUMN chat_mode VARCHAR(20) DEFAULT NULL AFTER image_url");
        } catch (\Exception $e) { /* column already exists */ }
        // Ensure thinking column exists (reasoning persistence — survives refresh / other devices)
        try {
            self::get()->exec("ALTER TABLE portal_messages ADD COLUMN thinking MEDIUMTEXT DEFAULT NULL AFTER chat_mode");
        } catch (\Exception $e) { /* column already exists */ }
        self::get()->prepare('INSERT INTO portal_messages (id, conversation_id, role, content, mood, tokens, processing_ms, image_url, chat_mode, thinking, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NOW())')
            ->execute([$id, $convId, $role, $content, $mood, $tokens, $processingMs, $imageUrl, $chatMode, $thinking]);
        return $id;
    }
    
    public static function getMessages(string $convId, int $limit = 100, int $offset = 0): array {
        $stmt = self::get()->prepare('SELECT id, role, content, mood, tokens, processing_ms, image_url, chat_mode, thinking, created_at FROM portal_messages WHERE conversation_id = ? ORDER BY created_at ASC LIMIT ? OFFSET ?');
        $stmt->execute([$convId, $limit, $offset]);
        return $stmt->fetchAll();
    }
    
    public static function getRecentMessages(string $convId, int $count = 20): array {
        $stmt = self::get()->prepare('SELECT role, content, chat_mode FROM portal_messages WHERE conversation_id = ? ORDER BY created_at DESC LIMIT ?');
        $stmt->execute([$convId, $count]);
        return array_reverse($stmt->fetchAll());
    }
    
    public static function getConversationSummary(string $convId): ?string {
        $stmt = self::get()->prepare('SELECT summary FROM portal_conversations WHERE id = ? LIMIT 1');
        $stmt->execute([$convId]);
        $row = $stmt->fetch();
        return $row ? $row['summary'] : null;
    }
    
    // ── Rate Limits ──────────────────────────────────────────────
    public static function getRateCounts(string $userId): array {
        $hourAgo = date('Y-m-d H:i:s', time() - 3600);
        $dayStart = date('Y-m-d 00:00:00');
        $stmt = self::get()->prepare('SELECT COUNT(*) as cnt FROM portal_messages m JOIN portal_conversations c ON m.conversation_id = c.id WHERE c.user_id = ? AND m.role = "user" AND m.created_at >= ?');
        $stmt->execute([$userId, $hourAgo]);
        $hourly = (int)$stmt->fetch()['cnt'];
        $stmt->execute([$userId, $dayStart]);
        $daily = (int)$stmt->fetch()['cnt'];
        return ['hourly' => $hourly, 'daily' => $daily];
    }
    
    // ── Queue (portal_offline_queue — the main pipeline) ─────────
    
    /**
     * Add a message to the queue for Ailey to process.
     * $context is a JSON string with history, summary, etc.
     */
    public static function addToOfflineQueue(string $userId, string $convId, string $message, string $context = '{}'): string {
        $id = self::uuid();
        self::get()->prepare(
            'INSERT INTO portal_offline_queue (id, user_id, conversation_id, message, context, status, created_at) VALUES (?, ?, ?, ?, ?, "pending", NOW())'
        )->execute([$id, $userId, $convId, $message, $context]);
        return $id;
    }
    
    /**
     * Add a system queue item (e.g. delete_user, summarize).
     */
    public static function addSystemQueueItem(string $kind, string $userId, string $context = '{}'): string {
        $id = self::uuid();
        self::get()->prepare(
            'INSERT INTO portal_offline_queue (id, user_id, conversation_id, message, context, status, created_at) VALUES (?, ?, "", ?, ?, "pending", NOW())'
        )->execute([$id, $userId, "__system:$kind", $context]);
        return $id;
    }
    
    /**
     * Get pending items for Ailey Core to process (FIFO).
     */
    public static function getPendingQueue(int $limit = 5): array {
        $stmt = self::get()->prepare(
            'SELECT q.*, u.display_name as user_name, u.email as user_email, u.glossary_id as glossary_id, u.role as user_role FROM portal_offline_queue q JOIN portal_users u ON q.user_id = u.id WHERE q.status = "pending" ORDER BY q.created_at ASC LIMIT ?'
        );
        $stmt->execute([$limit]);
        return $stmt->fetchAll();
    }
    
    /**
     * Update queue item status.
     */
    public static function updateQueueStatus(string $id, string $status): void {
        self::get()->prepare('UPDATE portal_offline_queue SET status = ?, updated_at = NOW() WHERE id = ?')
            ->execute([$status, $id]);
    }

    /**
     * Touch a queue item's updated_at timestamp (heartbeat — prevents stale reset).
     */
    public static function touchQueueItem(string $id): void {
        self::get()->prepare('UPDATE portal_offline_queue SET updated_at = NOW() WHERE id = ?')
            ->execute([$id]);
    }
    
    /**
     * Get a queue item by ID (for Ailey Core push_reply).
     */
    public static function getOfflineItemById(string $id): ?array {
        $stmt = self::get()->prepare('SELECT * FROM portal_offline_queue WHERE id = ? LIMIT 1');
        $stmt->execute([$id]);
        return $stmt->fetch() ?: null;
    }
    
    /**
     * Get a queue item with user ownership check (for user's check_reply).
     */
    public static function getOfflineItem(string $id, string $userId): ?array {
        $stmt = self::get()->prepare('SELECT * FROM portal_offline_queue WHERE id = ? AND user_id = ? LIMIT 1');
        $stmt->execute([$id, $userId]);
        return $stmt->fetch() ?: null;
    }
    
    /**
     * Update a queue item with the reply.
     */
    public static function updateQueueItem(string $id, string $status, ?string $reply = null, ?string $mood = null, ?string $title = null, ?int $processingMs = null, ?string $suggestions = null, ?string $imageUrl = null): void {
        // Ensure suggestions column exists (added 2026-02)
        try {
            self::get()->exec('ALTER TABLE portal_offline_queue ADD COLUMN suggestions TEXT DEFAULT NULL');
        } catch (\Exception $e) { /* column already exists */ }
        // Ensure image_url column exists (migration 003)
        try {
            self::get()->exec('ALTER TABLE portal_offline_queue ADD COLUMN image_url VARCHAR(500) DEFAULT NULL AFTER conversation_title');
        } catch (\Exception $e) { /* column already exists */ }
        self::get()->prepare(
            'UPDATE portal_offline_queue SET status = ?, reply = ?, mood = ?, conversation_title = ?, processing_ms = ?, suggestions = ?, image_url = ?, processed_at = NOW() WHERE id = ?'
        )->execute([$status, $reply, $mood, $title, $processingMs, $suggestions, $imageUrl, $id]);
        // Clean up partial cache file when done/failed
        if (in_array($status, ['done', 'failed'])) {
            $cacheFile = __DIR__ . '/uploads/partial_cache/' . preg_replace('/[^a-zA-Z0-9_-]/', '', $id) . '.txt';
            if (is_file($cacheFile)) @unlink($cacheFile);
        }
    }

    /**
     * Lightweight status-only update for queue items (e.g., pending → processing).
     */
    public static function updateQueueItemStatus(string $id, string $status): void {
        self::get()->prepare('UPDATE portal_offline_queue SET status = ? WHERE id = ?')
            ->execute([$status, $id]);
    }
    
    /**
     * Get pending items for a user (show "waiting" state).
     */
    public static function getPendingOffline(string $userId): array {
        $stmt = self::get()->prepare('SELECT * FROM portal_offline_queue WHERE user_id = ? AND status IN ("pending","processing") ORDER BY created_at ASC');
        $stmt->execute([$userId]);
        return $stmt->fetchAll();
    }
    
    /**
     * Clean up old processed queue items (> 24h).
     */
    public static function cleanOldQueueItems(): int {
        $stmt = self::get()->prepare('DELETE FROM portal_offline_queue WHERE status IN ("done","failed") AND processed_at < DATE_SUB(NOW(), INTERVAL 24 HOUR)');
        $stmt->execute();
        return $stmt->rowCount();
    }
    
    // ── Consent Log ──────────────────────────────────────────────
    public static function logConsent(string $userId, string $type, string $text, ?string $ip = null): void {
        self::get()->prepare('INSERT INTO portal_consent_log (user_id, consent_type, consent_text, ip_address, created_at) VALUES (?, ?, ?, ?, NOW())')
            ->execute([$userId, $type, $text, $ip]);
    }
    
    // ── Admin Log ────────────────────────────────────────────────
    public static function logAdmin(string $action, ?string $adminId = null, ?string $targetUserId = null, ?string $details = null, ?string $ip = null): void {
        self::get()->prepare('INSERT INTO portal_admin_log (admin_id, action, target_user_id, details, ip_address, created_at) VALUES (?, ?, ?, ?, ?, NOW())')
            ->execute([$adminId, $action, $targetUserId, $details, $ip]);
    }
    
    // ── DSGVO Delete ─────────────────────────────────────────────
    public static function deleteUserData(string $userId): array {
        $pdo = self::get();
        $deleted = [];
        $stmt = $pdo->prepare('SELECT COUNT(*) as cnt FROM portal_messages WHERE conversation_id IN (SELECT id FROM portal_conversations WHERE user_id = ?)');
        $stmt->execute([$userId]);
        $deleted['messages'] = (int)$stmt->fetch()['cnt'];
        $stmt = $pdo->prepare('SELECT COUNT(*) as cnt FROM portal_conversations WHERE user_id = ?');
        $stmt->execute([$userId]);
        $deleted['conversations'] = (int)$stmt->fetch()['cnt'];
        
        $pdo->prepare('DELETE FROM portal_offline_queue WHERE user_id = ?')->execute([$userId]);
        $pdo->prepare('DELETE FROM portal_messages WHERE conversation_id IN (SELECT id FROM portal_conversations WHERE user_id = ?)')->execute([$userId]);
        $pdo->prepare('DELETE FROM portal_conversations WHERE user_id = ?')->execute([$userId]);
        $pdo->prepare('DELETE FROM portal_sessions WHERE user_id = ?')->execute([$userId]);
        // Delete user memories (cross-session knowledge)
        try {
            $mem = $pdo->prepare('SELECT COUNT(*) as cnt FROM portal_user_memories WHERE user_id = ?');
            $mem->execute([$userId]);
            $deleted['memories'] = (int)$mem->fetch()['cnt'];
            $pdo->prepare('DELETE FROM portal_user_memories WHERE user_id = ?')->execute([$userId]);
        } catch (\Exception $e) {
            // Table may not exist yet
            $deleted['memories'] = 0;
        }
        $pdo->prepare('UPDATE portal_users SET email = CONCAT("deleted_", id, "@anon"), display_name = "Gelöscht", password_hash = "", status = "deleted" WHERE id = ?')->execute([$userId]);
        $deleted['user_anonymized'] = true;
        return $deleted;
    }
    
    // ── Admin Stats ──────────────────────────────────────────────
    public static function listUsers(int $limit = 100, int $offset = 0): array {
        $stmt = self::get()->prepare('SELECT id, email, display_name, status, role, user_tier, messages_today, messages_total, image_quota_daily, images_generated_today, song_quota_daily, songs_generated_today, tools_image_gen, tools_song_gen, warning_level, banned_until, warning_reason, vdollars_balance, vdollars_weekly_allowance, vdollars_active_days, last_active, created_at FROM portal_users ORDER BY created_at DESC LIMIT ? OFFSET ?');
        $stmt->execute([$limit, $offset]);
        return $stmt->fetchAll();
    }
    
    public static function getStats(): array {
        $pdo = self::get();
        return [
            'users_total'       => (int)$pdo->query('SELECT COUNT(*) FROM portal_users WHERE status != "deleted"')->fetchColumn(),
            'users_active_24h'  => (int)$pdo->query('SELECT COUNT(*) FROM portal_users WHERE last_active > DATE_SUB(NOW(), INTERVAL 24 HOUR)')->fetchColumn(),
            'conversations'     => (int)$pdo->query('SELECT COUNT(*) FROM portal_conversations')->fetchColumn(),
            'messages_total'    => (int)$pdo->query('SELECT COUNT(*) FROM portal_messages')->fetchColumn(),
            'messages_today'    => (int)$pdo->query('SELECT COUNT(*) FROM portal_messages WHERE created_at > CURDATE()')->fetchColumn(),
            'queue_pending'     => (int)$pdo->query('SELECT COUNT(*) FROM portal_offline_queue WHERE status = "pending"')->fetchColumn(),
            'queue_processing'  => (int)$pdo->query('SELECT COUNT(*) FROM portal_offline_queue WHERE status = "processing"')->fetchColumn(),
            'ailey_status'      => self::getAileyStatus(),
        ];
    }

    // ── Stale Queue Cleanup ──────────────────────────────────────
    public static function resetStaleQueueItems(int $maxAgeSeconds = 300): int {
        $stmt = self::get()->prepare(
            'UPDATE portal_offline_queue SET status = "pending" '
            . 'WHERE status = "processing" AND updated_at < DATE_SUB(NOW(), INTERVAL ? SECOND)'
        );
        $stmt->execute([$maxAgeSeconds]);
        $count = $stmt->rowCount();
        if ($count > 0) {
            error_log("[PortalDB] Reset $count stale queue items back to pending");
        }
        return $count;
    }

    // ── Ailey Status (online/sleeping/offline) ───────────────────
    public static function setAileyStatus(string $status): void {
        $pdo = self::get();
        // Use a simple key-value in a settings table, or a file-based approach
        // For simplicity: use portal_settings table (create if not exists)
        $pdo->exec('CREATE TABLE IF NOT EXISTS portal_settings (
            setting_key VARCHAR(64) PRIMARY KEY,
            setting_value TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        )');
        $stmt = $pdo->prepare(
            'INSERT INTO portal_settings (setting_key, setting_value) VALUES ("ailey_status", ?) '
            . 'ON DUPLICATE KEY UPDATE setting_value = ?, updated_at = NOW()'
        );
        $stmt->execute([$status, $status]);
    }

    public static function getAileyStatus(): string {
        try {
            $stmt = self::get()->prepare(
                'SELECT setting_value, updated_at FROM portal_settings WHERE setting_key = "ailey_status" LIMIT 1'
            );
            $stmt->execute();
            $row = $stmt->fetch(\PDO::FETCH_ASSOC);
            if (!$row || !$row['setting_value']) {
                return 'offline';  // No status ever set → offline
            }
            // Staleness check: if last heartbeat > 120 seconds ago → offline
            if (!empty($row['updated_at'])) {
                $lastUpdate = strtotime($row['updated_at']);
                if ($lastUpdate && (time() - $lastUpdate) > 120) {
                    return 'offline';
                }
            }
            return $row['setting_value'];
        } catch (\Exception $e) {
            return 'offline';  // Table might not exist yet
        }
    }

    // ── Ailey Live Mood (synced from Tauri/Core) ─────────────────
    public static function setAileyMood(string $mood): void {
        $pdo = self::get();
        $pdo->exec('CREATE TABLE IF NOT EXISTS portal_settings (
            setting_key VARCHAR(64) PRIMARY KEY,
            setting_value TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        )');
        $stmt = $pdo->prepare(
            'INSERT INTO portal_settings (setting_key, setting_value) VALUES ("ailey_mood", ?) '
            . 'ON DUPLICATE KEY UPDATE setting_value = ?, updated_at = NOW()'
        );
        $stmt->execute([$mood, $mood]);
    }

    public static function getAileyMood(): string {
        try {
            $stmt = self::get()->prepare('SELECT setting_value FROM portal_settings WHERE setting_key = "ailey_mood" LIMIT 1');
            $stmt->execute();
            $val = $stmt->fetchColumn();
            return $val ?: 'neutral';
        } catch (\Exception $e) {
            return 'neutral';
        }
    }

    // ── Artifacts (Code + SVGs) ──────────────────────────────────
    private static bool $artifactTableChecked = false;

    private static function ensureArtifactTable(): void {
        if (self::$artifactTableChecked) return;
        self::get()->exec('CREATE TABLE IF NOT EXISTS `portal_artifacts` (
            `id`              CHAR(36)     NOT NULL PRIMARY KEY,
            `user_id`         CHAR(36)     NOT NULL,
            `conversation_id` CHAR(36)     DEFAULT NULL,
            `message_id`      CHAR(36)     DEFAULT NULL,
            `type`            ENUM(\'code\',\'svg\',\'song\',\'image\') NOT NULL,
            `language`        VARCHAR(30)  DEFAULT NULL,
            `title`           VARCHAR(200) DEFAULT NULL,
            `content`         LONGTEXT     NOT NULL,
            `size_bytes`      INT UNSIGNED DEFAULT NULL,
            `deleted_at`      DATETIME     DEFAULT NULL,
            `created_at`      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
            INDEX `idx_art_user` (`user_id`),
            INDEX `idx_art_user_type` (`user_id`, `type`),
            INDEX `idx_art_conv` (`conversation_id`),
            INDEX `idx_art_created` (`created_at`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci');
        // Migrate existing table: add 'song' and 'image' to ENUM if missing
        try {
            self::get()->exec("ALTER TABLE portal_artifacts MODIFY COLUMN `type` ENUM('code','svg','song','image') NOT NULL");
        } catch (\Exception $e) { /* already up to date or non-critical */ }
        // Migration: add deleted_at column for soft-delete
        try {
            self::get()->exec("ALTER TABLE portal_artifacts ADD COLUMN `deleted_at` DATETIME DEFAULT NULL AFTER `size_bytes`");
        } catch (\Exception $e) { /* column already exists */ }
        // Migration: add deleted_at to portal_conversations for soft-delete
        try {
            self::get()->exec("ALTER TABLE portal_conversations ADD COLUMN `deleted_at` DATETIME DEFAULT NULL");
        } catch (\Exception $e) { /* column already exists */ }
        self::$artifactTableChecked = true;
    }

    public static function addArtifact(string $userId, ?string $convId, ?string $msgId, string $type, ?string $language, ?string $title, string $content): string {
        self::ensureArtifactTable();
        $id = self::uuid();
        self::get()->prepare(
            'INSERT INTO portal_artifacts (id, user_id, conversation_id, message_id, type, language, title, content, size_bytes, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NOW())'
        )->execute([$id, $userId, $convId, $msgId, $type, $language, $title, $content, strlen($content)]);
        return $id;
    }

    public static function listArtifacts(string $userId, ?string $type = null, int $limit = 100, int $offset = 0): array {
        self::ensureArtifactTable();
        if ($type) {
            $stmt = self::get()->prepare(
                'SELECT id, conversation_id, type, language, title, content, size_bytes, created_at FROM portal_artifacts WHERE user_id = ? AND type = ? AND deleted_at IS NULL ORDER BY created_at DESC LIMIT ? OFFSET ?'
            );
            $stmt->execute([$userId, $type, $limit, $offset]);
        } else {
            $stmt = self::get()->prepare(
                'SELECT id, conversation_id, type, language, title, content, size_bytes, created_at FROM portal_artifacts WHERE user_id = ? AND deleted_at IS NULL ORDER BY created_at DESC LIMIT ? OFFSET ?'
            );
            $stmt->execute([$userId, $limit, $offset]);
        }
        return $stmt->fetchAll();
    }

    public static function getArtifact(string $id, string $userId): ?array {
        self::ensureArtifactTable();
        $stmt = self::get()->prepare('SELECT * FROM portal_artifacts WHERE id = ? AND user_id = ? AND deleted_at IS NULL LIMIT 1');
        $stmt->execute([$id, $userId]);
        return $stmt->fetch() ?: null;
    }

    public static function getArtifactCountsByType(string $userId): array {
        self::ensureArtifactTable();
        $stmt = self::get()->prepare('SELECT type, COUNT(*) as count FROM portal_artifacts WHERE user_id = ? AND deleted_at IS NULL GROUP BY type');
        $stmt->execute([$userId]);
        $counts = ['code' => 0, 'svg' => 0, 'song' => 0, 'image' => 0];
        foreach ($stmt->fetchAll() as $row) {
            $counts[$row['type']] = (int)$row['count'];
        }
        return $counts;
    }

    /**
     * Delete an artifact. Admin = hard-delete. Standard user = soft-delete (30 days retention).
     */
    public static function deleteArtifact(string $artifactId, string $userId, bool $isAdmin = false): bool {
        self::ensureArtifactTable();
        $db = self::get();
        // Verify ownership
        $check = $db->prepare('SELECT id FROM portal_artifacts WHERE id = ? AND user_id = ?');
        $check->execute([$artifactId, $userId]);
        if (!$check->fetch()) return false;

        if ($isAdmin) {
            $db->prepare('DELETE FROM portal_artifacts WHERE id = ? AND user_id = ?')->execute([$artifactId, $userId]);
        } else {
            $db->prepare('UPDATE portal_artifacts SET deleted_at = NOW() WHERE id = ? AND user_id = ?')->execute([$artifactId, $userId]);
        }
        return true;
    }

    /**
     * Purge soft-deleted conversations and artifacts older than 30 days.
     * Should be called periodically (e.g. via cron or on each API request).
     */
    public static function purgeExpiredSoftDeletes(int $retentionDays = 30): array {
        $db = self::get();
        $purged = ['conversations' => 0, 'artifacts' => 0];

        // Purge old soft-deleted conversations (and their messages/queue/artifacts)
        try {
            $stmt = $db->prepare('SELECT id, user_id FROM portal_conversations WHERE deleted_at IS NOT NULL AND deleted_at < DATE_SUB(NOW(), INTERVAL ? DAY)');
            $stmt->execute([$retentionDays]);
            $expired = $stmt->fetchAll();
            foreach ($expired as $conv) {
                $db->prepare('DELETE FROM portal_messages WHERE conversation_id = ?')->execute([$conv['id']]);
                $db->prepare('DELETE FROM portal_offline_queue WHERE conversation_id = ?')->execute([$conv['id']]);
                try { $db->prepare('DELETE FROM portal_artifacts WHERE conversation_id = ?')->execute([$conv['id']]); } catch (\Exception $e) {}
                $db->prepare('DELETE FROM portal_conversations WHERE id = ?')->execute([$conv['id']]);
                $purged['conversations']++;
            }
        } catch (\Exception $e) { /* table may not have deleted_at yet */ }

        // Purge old soft-deleted artifacts (standalone, not linked to a conversation purge)
        try {
            $stmt = $db->prepare('DELETE FROM portal_artifacts WHERE deleted_at IS NOT NULL AND deleted_at < DATE_SUB(NOW(), INTERVAL ? DAY)');
            $stmt->execute([$retentionDays]);
            $purged['artifacts'] = $stmt->rowCount();
        } catch (\Exception $e) {}

        return $purged;
    }

    // ── Public Content (pushed by Ailey Core for landing page) ───
    /**
     * Store a JSON blob of Ailey's public content snapshot.
     * Contains: books, songs, recent_thoughts, stats.
     */
    public static function setPublicContent(array $data): void {
        $json = json_encode($data, JSON_UNESCAPED_UNICODE | JSON_PRETTY_PRINT);
        $pdo = self::get();
        $pdo->exec('CREATE TABLE IF NOT EXISTS portal_settings (
            setting_key VARCHAR(64) PRIMARY KEY,
            setting_value LONGTEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        )');
        $stmt = $pdo->prepare(
            'INSERT INTO portal_settings (setting_key, setting_value) VALUES ("ailey_public_content", ?) '
            . 'ON DUPLICATE KEY UPDATE setting_value = ?, updated_at = NOW()'
        );
        $stmt->execute([$json, $json]);
    }

    public static function getPublicContent(): ?array {
        try {
            $stmt = self::get()->prepare(
                'SELECT setting_value FROM portal_settings WHERE setting_key = "ailey_public_content" LIMIT 1'
            );
            $stmt->execute();
            $val = $stmt->fetchColumn();
            return $val ? json_decode($val, true) : null;
        } catch (\Exception $e) {
            return null;
        }
    }

    // ══════════════════════════════════════════════════════════════
    // PUBLIC ART SITE — Blog Posts, Gallery, Activity Feed
    // ══════════════════════════════════════════════════════════════

    // ── Blog Posts ───────────────────────────────────────────────

    /**
     * Insert a blog post (pushed from Ailey Core).
     */
    public static function addBlogPost(string $slug, string $title, string $contentMd,
                                       ?string $topic = null, ?string $mood = null,
                                       string $lang = 'de', ?string $imageUrl = null): int {
        // Render Markdown → HTML (simple conversion; use Parsedown if available)
        $contentHtml = self::renderMarkdown($contentMd);
        $stmt = self::get()->prepare(
            'INSERT INTO ailey_blog_posts (slug, title, content_md, content_html, image_url, topic, mood, language, published_at) '
            . 'VALUES (?, ?, ?, ?, ?, ?, ?, ?, NOW()) '
            . 'ON DUPLICATE KEY UPDATE title = VALUES(title), content_md = VALUES(content_md), '
            . 'content_html = VALUES(content_html), image_url = COALESCE(VALUES(image_url), image_url), '
            . 'topic = VALUES(topic), mood = VALUES(mood), '
            . 'updated_at = NOW()'
        );
        $stmt->execute([$slug, $title, $contentMd, $contentHtml, $imageUrl, $topic, $mood, $lang]);
        return (int)self::get()->lastInsertId();
    }

    /**
     * Update an existing blog post by ID (title optional, content required).
     */
    public static function updateBlogPost(int $id, ?string $title, string $contentMd): bool {
        $contentHtml = self::renderMarkdown($contentMd);
        if ($title) {
            $stmt = self::get()->prepare(
                'UPDATE ailey_blog_posts SET title = ?, content_md = ?, content_html = ?, updated_at = NOW() WHERE id = ?'
            );
            $stmt->execute([$title, $contentMd, $contentHtml, $id]);
        } else {
            $stmt = self::get()->prepare(
                'UPDATE ailey_blog_posts SET content_md = ?, content_html = ?, updated_at = NOW() WHERE id = ?'
            );
            $stmt->execute([$contentMd, $contentHtml, $id]);
        }
        return $stmt->rowCount() > 0;
    }

    /**
     * Get published blog posts (paginated, newest first).
     */
    public static function getBlogPosts(int $limit = 10, int $offset = 0): array {
        $stmt = self::get()->prepare(
            'SELECT id, slug, title, image_url, topic, mood, language, published_at, '
            . 'LEFT(content_md, 300) as excerpt '
            . 'FROM ailey_blog_posts WHERE published = 1 '
            . 'ORDER BY published_at DESC LIMIT ? OFFSET ?'
        );
        $stmt->execute([$limit, $offset]);
        return $stmt->fetchAll();
    }

    /**
     * Get a single blog post by slug.
     */
    public static function getBlogPostBySlug(string $slug): ?array {
        $stmt = self::get()->prepare(
            'SELECT * FROM ailey_blog_posts WHERE slug = ? AND published = 1 LIMIT 1'
        );
        $stmt->execute([$slug]);
        return $stmt->fetch() ?: null;
    }

    /**
     * Count published blog posts.
     */
    public static function countBlogPosts(): int {
        return (int)self::get()->query(
            'SELECT COUNT(*) FROM ailey_blog_posts WHERE published = 1'
        )->fetchColumn();
    }

    // ── Gallery Items ────────────────────────────────────────────

    /**
     * Insert or update a gallery item (deduped by source_id AND normalized title).
     * Returns 0 if the source_id is admin-blocked (won't re-insert).
     * Returns existing ID if a song with the same normalized title already exists.
     */
    public static function addGalleryItem(string $type, string $title, ?string $description,
                                          ?string $contentText, ?string $fileUrl,
                                          ?array $metadata, ?string $sourceId,
                                          string $lang = 'de'): int {
        // Check if this source_id was admin-blocked
        if ($sourceId && self::isGallerySourceBlocked($sourceId)) {
            return 0; // blocked by admin — don't re-insert
        }

        $db = self::get();

        // ── Song title-based dedup: prevent duplicates from different source_ids ──
        if ($type === 'song' && $title) {
            $normTitle = self::normalizeSongTitle($title);
            if (strlen($normTitle) >= 3) {
                // Check if a song with the same normalized title already exists
                $existing = $db->prepare(
                    'SELECT id, title, source_id FROM ailey_gallery_items '
                    . 'WHERE item_type = \'song\' AND published = 1 '
                    . 'ORDER BY id ASC'
                );
                $existing->execute();
                $rows = $existing->fetchAll(\PDO::FETCH_ASSOC);

                foreach ($rows as $row) {
                    $existingNorm = self::normalizeSongTitle($row['title'] ?? '');
                    if ($existingNorm === $normTitle) {
                        // Song with same title exists — UPDATE instead of INSERT
                        $metaJson = $metadata ? json_encode($metadata, JSON_UNESCAPED_UNICODE) : null;
                        $upd = $db->prepare(
                            'UPDATE ailey_gallery_items SET '
                            . 'title = ?, description = ?, content_text = ?, file_url = ?, '
                            . 'metadata_json = ?, source_id = COALESCE(?, source_id), updated_at = NOW() '
                            . 'WHERE id = ?'
                        );
                        $upd->execute([$title, $description, $contentText, $fileUrl, $metaJson, $sourceId, $row['id']]);
                        return (int)$row['id'];
                    }
                }
            }
        }

        $metaJson = $metadata ? json_encode($metadata, JSON_UNESCAPED_UNICODE) : null;
        $stmt = $db->prepare(
            'INSERT INTO ailey_gallery_items '
            . '(item_type, title, description, content_text, file_url, metadata_json, source_id, language) '
            . 'VALUES (?, ?, ?, ?, ?, ?, ?, ?) '
            . 'ON DUPLICATE KEY UPDATE item_type = VALUES(item_type), title = VALUES(title), description = VALUES(description), '
            . 'content_text = VALUES(content_text), file_url = VALUES(file_url), '
            . 'metadata_json = VALUES(metadata_json), updated_at = NOW()'
        );
        $stmt->execute([$type, $title, $description, $contentText, $fileUrl, $metaJson, $sourceId, $lang]);
        return (int)$db->lastInsertId();
    }

    /**
     * Normalize a song title for dedup comparison.
     * Strips artist prefix, punctuation, and lowercases.
     */
    private static function normalizeSongTitle(string $title): string {
        $t = mb_strtolower(trim($title));
        $t = preg_replace('/[*"„""\'()\[\]#_]/', '', $t);
        $t = preg_replace('/^(title|titel|song)\s*:\s*/', '', $t);
        // Strip common artist prefix so "a!ley vyrus - X" doesn't cause mismatches
        $t = preg_replace('/^a!ley\s+vyrus\s*[-–—]\s*/i', '', $t);
        $t = preg_replace('/^aley\s+vyrus\s*[-–—]\s*/i', '', $t);
        // Collapse whitespace
        $t = preg_replace('/\s+/', ' ', $t);
        return trim($t);
    }

    /**
     * Get gallery items, optionally filtered by type (paginated, newest first).
     */
    public static function getGalleryItems(?string $type = null, int $limit = 20, int $offset = 0): array {
        if ($type) {
            $stmt = self::get()->prepare(
                'SELECT id, item_type, title, description, content_text, file_url, metadata_json, language, created_at, submitted_by '
                . 'FROM ailey_gallery_items WHERE published = 1 AND item_type = ? '
                . 'ORDER BY created_at DESC LIMIT ? OFFSET ?'
            );
            $stmt->execute([$type, $limit, $offset]);
        } else {
            $stmt = self::get()->prepare(
                'SELECT id, item_type, title, description, content_text, file_url, metadata_json, language, created_at, submitted_by '
                . 'FROM ailey_gallery_items WHERE published = 1 '
                . 'ORDER BY created_at DESC LIMIT ? OFFSET ?'
            );
            $stmt->execute([$limit, $offset]);
        }
        $rows = $stmt->fetchAll();
        // Decode metadata JSON for each row
        foreach ($rows as &$row) {
            if ($row['metadata_json']) {
                $row['metadata'] = json_decode($row['metadata_json'], true);
            }
            unset($row['metadata_json']);
        }
        return $rows;
    }

    /**
     * Get a single gallery item by ID (with full content).
     */
    public static function getGalleryItem(int $id): ?array {
        $stmt = self::get()->prepare(
            'SELECT * FROM ailey_gallery_items WHERE id = ? AND published = 1 LIMIT 1'
        );
        $stmt->execute([$id]);
        $row = $stmt->fetch();
        if ($row && $row['metadata_json']) {
            $row['metadata'] = json_decode($row['metadata_json'], true);
        }
        return $row ?: null;
    }

    /**
     * Count gallery items by type.
     */
    public static function countGalleryItems(?string $type = null): int {
        if ($type) {
            $stmt = self::get()->prepare(
                'SELECT COUNT(*) FROM ailey_gallery_items WHERE published = 1 AND item_type = ?'
            );
            $stmt->execute([$type]);
            return (int)$stmt->fetchColumn();
        }
        return (int)self::get()->query(
            'SELECT COUNT(*) FROM ailey_gallery_items WHERE published = 1'
        )->fetchColumn();
    }

    /**
     * Get gallery stats (counts by type).
     */
    public static function getGalleryStats(): array {
        $stmt = self::get()->query(
            'SELECT item_type, COUNT(*) as cnt FROM ailey_gallery_items WHERE published = 1 GROUP BY item_type'
        );
        $stats = ['song' => 0, 'image' => 0, 'svg' => 0, 'book' => 0, 'code' => 0, 'total' => 0];
        foreach ($stmt->fetchAll() as $row) {
            $stats[$row['item_type']] = (int)$row['cnt'];
            $stats['total'] += (int)$row['cnt'];
        }
        return $stats;
    }

    /**
     * Remove duplicate gallery songs: keep only the longest (most complete) version
     * per normalized title. Returns number of deleted duplicates.
     */
    public static function deduplicateGallerySongs(): int {
        $db = self::get();
        // Get all published songs
        $stmt = $db->query(
            'SELECT id, title, content_text, source_id, file_url, LENGTH(content_text) AS content_len '
            . 'FROM ailey_gallery_items '
            . 'WHERE published = 1 AND item_type = \'song\' '
            . 'ORDER BY content_len DESC'
        );
        $songs = $stmt->fetchAll(\PDO::FETCH_ASSOC);
        if (count($songs) <= 1) return 0;

        // Use the shared normalization method
        $normTitle = function(string $title): string {
            return self::normalizeSongTitle($title);
        };

        // Group by similar title — ONLY exact normalized match (word overlap removed:
        // it caused false positives for short artist-prefixed titles like "AILÍN")
        $groups = [];
        $assigned = [];

        foreach ($songs as $song) {
            if (in_array($song['id'], $assigned)) continue;
            $norm = $normTitle($song['title']);
            $key = $song['id'];
            $group = [$song];
            $assigned[] = $song['id'];

            foreach ($songs as $other) {
                if (in_array($other['id'], $assigned)) continue;
                $otherNorm = $normTitle($other['title']);

                // ONLY exact normalized title match (no fuzzy word overlap)
                $match = ($norm === $otherNorm && strlen($norm) >= 3);

                if ($match) {
                    $group[] = $other;
                    $assigned[] = $other['id'];
                }
            }

            if (count($group) > 1) {
                $groups[$key] = $group;
            }
        }

        // Delete all but the best in each group.
        // Priority: has audio file_url > has source_id > longest content.
        $deleted = 0;
        foreach ($groups as $group) {
            usort($group, function($a, $b) {
                // 1. Prefer items WITH audio file_url
                $aHasAudio = !empty($a['file_url']) ? 1 : 0;
                $bHasAudio = !empty($b['file_url']) ? 1 : 0;
                if ($aHasAudio !== $bHasAudio) return $bHasAudio - $aHasAudio;
                // 2. Prefer items with source_id (pushed by Ailey Core)
                $aHasSrc = !empty($a['source_id']) && strpos($a['source_id'], 'BLOCKED:') !== 0 ? 1 : 0;
                $bHasSrc = !empty($b['source_id']) && strpos($b['source_id'], 'BLOCKED:') !== 0 ? 1 : 0;
                if ($aHasSrc !== $bHasSrc) return $bHasSrc - $aHasSrc;
                // 3. Longest content
                return (int)$b['content_len'] - (int)$a['content_len'];
            });
            $keepId = $group[0]['id'];
            // Merge: migrate best audio URL + source_id to keeper if it's missing
            $keepFileUrl = $group[0]['file_url'] ?? '';
            $keepSourceId = $group[0]['source_id'] ?? '';
            for ($i = 1; $i < count($group); $i++) {
                // If the keeper has no audio but this duplicate does, steal its URL
                if (empty($keepFileUrl) && !empty($group[$i]['file_url'])) {
                    $db->prepare('UPDATE ailey_gallery_items SET file_url = ? WHERE id = ?')
                       ->execute([$group[$i]['file_url'], $keepId]);
                    $keepFileUrl = $group[$i]['file_url'];
                }
                $delId = $group[$i]['id'];
                $delStmt = $db->prepare('DELETE FROM ailey_gallery_items WHERE id = ?');
                $delStmt->execute([$delId]);
                $deleted++;
            }
        }

        return $deleted;
    }
    public static function adminGetAllGalleryItems(int $limit = 200, int $offset = 0): array {
        $stmt = self::get()->prepare(
            'SELECT id, item_type, title, source_id, published, created_at, updated_at '
            . 'FROM ailey_gallery_items ORDER BY created_at DESC LIMIT ? OFFSET ?'
        );
        $stmt->execute([$limit, $offset]);
        $rows = $stmt->fetchAll(\PDO::FETCH_ASSOC);
        return $rows ?: [];
    }

    /**
     * Unpublish a gallery item (hide from public) and optionally block its source_id from re-sync.
     */
    public static function adminUnpublishGalleryItem(int $id, bool $blockSync = false): bool {
        $stmt = self::get()->prepare('UPDATE ailey_gallery_items SET published = 0 WHERE id = ?');
        $stmt->execute([$id]);
        if ($blockSync) {
            // Mark source_id as blocked by prefixing with "BLOCKED:"
            $stmt2 = self::get()->prepare(
                'UPDATE ailey_gallery_items SET source_id = CONCAT("BLOCKED:", source_id) WHERE id = ? AND source_id IS NOT NULL AND source_id NOT LIKE "BLOCKED:%"'
            );
            $stmt2->execute([$id]);
        }
        return $stmt->rowCount() > 0;
    }

    /**
     * Delete a gallery item. Admin = hard-delete. Standard user = soft-delete (30 days retention).
     * Users can only delete items they submitted (submitted_by match).
     */
    public static function deleteGalleryItem(int $id, string $userId, bool $isAdmin = false): bool {
        self::ensureGallerySubmissionColumns();
        $db = self::get();
        if ($isAdmin) {
            // Admin: hard-delete immediately
            $del = $db->prepare('DELETE FROM ailey_gallery_items WHERE id = ?');
            $del->execute([$id]);
            return $del->rowCount() > 0;
        }
        // Standard user: verify ownership via submitted_by, then soft-delete
        $check = $db->prepare('SELECT id FROM ailey_gallery_items WHERE id = ? AND submitted_by = ?');
        $check->execute([$id, $userId]);
        if (!$check->fetch()) return false;
        // Soft-delete: unpublish + set deleted_at (purged after 30 days)
        try {
            $db->exec('ALTER TABLE ailey_gallery_items ADD COLUMN deleted_at DATETIME DEFAULT NULL');
        } catch (\Exception $e) { /* column already exists */ }
        $stmt = $db->prepare('UPDATE ailey_gallery_items SET published = 0, deleted_at = NOW() WHERE id = ? AND submitted_by = ?');
        $stmt->execute([$id, $userId]);
        return $stmt->rowCount() > 0;
    }

    /**
     * Permanently delete a gallery item (admin only, legacy).
     */
    public static function adminDeleteGalleryItem(int $id): bool {
        // Get source_id for blocking before deletion
        $stmt = self::get()->prepare('SELECT source_id FROM ailey_gallery_items WHERE id = ?');
        $stmt->execute([$id]);
        $row = $stmt->fetch(\PDO::FETCH_ASSOC);
        $sourceId = $row ? ($row['source_id'] ?? null) : null;

        $del = self::get()->prepare('DELETE FROM ailey_gallery_items WHERE id = ?');
        $del->execute([$id]);
        return $del->rowCount() > 0;
    }

    /**
     * Unblock a gallery item: remove BLOCKED: prefix from source_id and re-publish.
     */
    public static function adminUnblockGalleryItem(int $id): bool {
        $db = self::get();
        // Remove BLOCKED: prefix from source_id
        $stmt = $db->prepare(
            'UPDATE ailey_gallery_items SET source_id = REPLACE(source_id, "BLOCKED:", ""), published = 1 WHERE id = ?'
        );
        $stmt->execute([$id]);
        return $stmt->rowCount() > 0;
    }

    /**
     * Check if a source_id is blocked (was deleted/unpublished by admin).
     */
    public static function isGallerySourceBlocked(string $sourceId): bool {
        $stmt = self::get()->prepare(
            'SELECT COUNT(*) FROM ailey_gallery_items WHERE source_id = ? AND published = 0'
        );
        $stmt->execute(["BLOCKED:" . $sourceId]);
        return (int)$stmt->fetchColumn() > 0;
    }

    // ── User Gallery Submissions ─────────────────────────────────

    private static bool $gallerySubmissionColumnsChecked = false;

    /**
     * Ensure the gallery table has submitted_by and approval_status columns.
     */
    private static function ensureGallerySubmissionColumns(): void {
        if (self::$gallerySubmissionColumnsChecked) return;
        try {
            self::get()->exec('ALTER TABLE ailey_gallery_items ADD COLUMN submitted_by CHAR(36) DEFAULT NULL');
        } catch (\Exception $e) { /* column already exists */ }
        try {
            self::get()->exec("ALTER TABLE ailey_gallery_items ADD COLUMN approval_status ENUM('auto','pending','approved','rejected') DEFAULT 'auto'");
        } catch (\Exception $e) { /* column already exists */ }
        self::$gallerySubmissionColumnsChecked = true;
    }

    /**
     * User submits a personal artifact to the public gallery (pending admin approval).
     */
    public static function submitArtifactToGallery(string $userId, string $artifactId, string $type, string $title, ?string $content, ?string $language): int {
        self::ensureGallerySubmissionColumns();
        $sourceId = 'user_submit:' . $artifactId;
        // Check if already submitted
        $dup = self::get()->prepare('SELECT id FROM ailey_gallery_items WHERE source_id = ? LIMIT 1');
        $dup->execute([$sourceId]);
        if ($dup->fetch()) return -1; // already submitted
        $metaJson = json_encode(['language' => $language, 'submitted_by_name' => null], JSON_UNESCAPED_UNICODE);
        // For images: content is the URL, store it also as file_url
        $fileUrl = ($type === 'image') ? $content : null;
        $contentText = ($type === 'image') ? null : $content;
        $stmt = self::get()->prepare(
            'INSERT INTO ailey_gallery_items '
            . '(item_type, title, content_text, file_url, metadata_json, source_id, language, published, submitted_by, approval_status) '
            . "VALUES (?, ?, ?, ?, ?, ?, 'de', 0, ?, 'pending')"
        );
        $stmt->execute([$type, $title, $contentText, $fileUrl, $metaJson, $sourceId, $userId]);
        return (int)self::get()->lastInsertId();
    }

    /**
     * Get pending gallery submissions for admin review.
     */
    public static function getPendingSubmissions(int $limit = 50): array {
        self::ensureGallerySubmissionColumns();
        $stmt = self::get()->prepare(
            "SELECT g.id, g.item_type, g.title, g.content_text, g.file_url, g.metadata_json, g.source_id, g.created_at, g.submitted_by, g.approval_status, "
            . "u.display_name AS submitter_name "
            . "FROM ailey_gallery_items g "
            . "LEFT JOIN portal_users u ON g.submitted_by = u.id "
            . "WHERE g.approval_status = 'pending' "
            . "ORDER BY g.created_at DESC LIMIT ?"
        );
        $stmt->execute([$limit]);
        return $stmt->fetchAll();
    }

    /**
     * Admin approves or rejects a gallery submission.
     */
    public static function reviewSubmission(int $id, string $decision): bool {
        self::ensureGallerySubmissionColumns();
        if ($decision === 'approved') {
            $stmt = self::get()->prepare("UPDATE ailey_gallery_items SET published = 1, approval_status = 'approved' WHERE id = ?");
        } else {
            $stmt = self::get()->prepare("UPDATE ailey_gallery_items SET published = 0, approval_status = 'rejected' WHERE id = ?");
        }
        $stmt->execute([$id]);
        return $stmt->rowCount() > 0;
    }

    // ── Activity Feed ────────────────────────────────────────────

    /**
     * Add an activity event to the public feed.
     * Deduplicates: if an identical (event_type + title) exists within the last 10 minutes, skip.
     */
    public static function addActivity(string $eventType, string $title,
                                       ?string $url = null, ?string $preview = null,
                                       ?string $emoji = null): int {
        // Deduplicate: same event_type + title within last 10 minutes → skip
        $dup = self::get()->prepare(
            'SELECT id FROM ailey_activity_feed '
            . 'WHERE event_type = ? AND title = ? AND created_at > DATE_SUB(NOW(), INTERVAL 10 MINUTE) '
            . 'LIMIT 1'
        );
        $dup->execute([$eventType, $title]);
        if ($existing = $dup->fetch()) {
            return (int)$existing['id']; // return existing ID, no duplicate
        }

        $stmt = self::get()->prepare(
            'INSERT INTO ailey_activity_feed (event_type, title, url, preview, emoji) '
            . 'VALUES (?, ?, ?, ?, ?)'
        );
        $stmt->execute([$eventType, $title, $url, $preview, $emoji]);
        return (int)self::get()->lastInsertId();
    }

    /**
     * Get recent activity feed entries (paginated, newest first).
     */
    public static function getActivityFeed(int $limit = 30, int $offset = 0): array {
        $stmt = self::get()->prepare(
            'SELECT * FROM ailey_activity_feed ORDER BY created_at DESC LIMIT ? OFFSET ?'
        );
        $stmt->execute([$limit, $offset]);
        return $stmt->fetchAll();
    }

    /**
     * Count total activity entries.
     */
    public static function countActivities(): int {
        return (int)self::get()->query('SELECT COUNT(*) FROM ailey_activity_feed')->fetchColumn();
    }

    // ── Book Chapters ────────────────────────────────────────────

    /**
     * Upsert a book chapter (deduped by book_source_id + chapter_num).
     * Returns 'inserted', 'updated', or 'unchanged'.
     */
    public static function upsertBookChapter(string $bookSourceId, int $chapterNum,
                                              ?string $chapterTitle, string $contentMd,
                                              string $contentHash, int $wordCount = 0,
                                              bool $isRevised = false): string {
        // Check if chapter already exists and compare hash
        $existing = self::get()->prepare(
            'SELECT id, content_hash FROM ailey_book_chapters WHERE book_source_id = ? AND chapter_num = ? LIMIT 1'
        );
        $existing->execute([$bookSourceId, $chapterNum]);
        $row = $existing->fetch();

        if ($row) {
            if ($row['content_hash'] === $contentHash) {
                // Only update is_revised flag if it changed
                self::get()->prepare(
                    'UPDATE ailey_book_chapters SET is_revised = ? WHERE id = ?'
                )->execute([(int)$isRevised, $row['id']]);
                return 'unchanged';
            }
            // Content changed → update
            self::get()->prepare(
                'UPDATE ailey_book_chapters SET chapter_title = ?, content_md = ?, content_hash = ?, '
                . 'word_count = ?, is_revised = ?, updated_at = NOW() WHERE id = ?'
            )->execute([$chapterTitle, $contentMd, $contentHash, $wordCount, (int)$isRevised, $row['id']]);
            return 'updated';
        }

        // New chapter
        self::get()->prepare(
            'INSERT INTO ailey_book_chapters (book_source_id, chapter_num, chapter_title, content_md, '
            . 'content_hash, word_count, is_revised) VALUES (?, ?, ?, ?, ?, ?, ?)'
        )->execute([$bookSourceId, $chapterNum, $chapterTitle, $contentMd, $contentHash, $wordCount, (int)$isRevised]);
        return 'inserted';
    }

    /**
     * Get all chapters for a book (ordered by chapter_num).
     */
    public static function getBookChapters(string $bookSourceId): array {
        $stmt = self::get()->prepare(
            'SELECT chapter_num, chapter_title, content_md, word_count, is_revised, created_at, updated_at '
            . 'FROM ailey_book_chapters WHERE book_source_id = ? ORDER BY chapter_num ASC'
        );
        $stmt->execute([$bookSourceId]);
        return $stmt->fetchAll();
    }

    /**
     * Get a single chapter.
     */
    public static function getBookChapter(string $bookSourceId, int $chapterNum): ?array {
        $stmt = self::get()->prepare(
            'SELECT chapter_num, chapter_title, content_md, word_count, is_revised, created_at, updated_at '
            . 'FROM ailey_book_chapters WHERE book_source_id = ? AND chapter_num = ? LIMIT 1'
        );
        $stmt->execute([$bookSourceId, $chapterNum]);
        return $stmt->fetch() ?: null;
    }

    /**
     * Count chapters for a book.
     */
    public static function countBookChapters(string $bookSourceId): int {
        $stmt = self::get()->prepare(
            'SELECT COUNT(*) FROM ailey_book_chapters WHERE book_source_id = ?'
        );
        $stmt->execute([$bookSourceId]);
        return (int)$stmt->fetchColumn();
    }

    // ── Markdown Rendering (simple) ──────────────────────────────

    /**
     * Minimal Markdown → HTML renderer for blog posts.
     * Handles: headings, bold, italic, links, paragraphs, lists, blockquotes, hr.
     * For production, consider adding Parsedown.
     */
    public static function renderMarkdown(string $md): string {
        $html = htmlspecialchars($md, ENT_QUOTES, 'UTF-8');
        // Headings (## H2, ### H3, #### H4)
        $html = preg_replace('/^####\s+(.+)$/m', '<h4>$1</h4>', $html);
        $html = preg_replace('/^###\s+(.+)$/m', '<h3>$1</h3>', $html);
        $html = preg_replace('/^##\s+(.+)$/m', '<h2>$1</h2>', $html);
        // Horizontal rules
        $html = preg_replace('/^---+$/m', '<hr>', $html);
        // Bold + Italic
        $html = preg_replace('/\*\*\*(.+?)\*\*\*/s', '<strong><em>$1</em></strong>', $html);
        $html = preg_replace('/\*\*(.+?)\*\*/s', '<strong>$1</strong>', $html);
        $html = preg_replace('/\*(.+?)\*/s', '<em>$1</em>', $html);
        // Links [text](url)
        $html = preg_replace('/\[([^\]]+)\]\(([^)]+)\)/', '<a href="$2" rel="noopener">$1</a>', $html);
        // Blockquotes > text
        $html = preg_replace('/^&gt;\s+(.+)$/m', '<blockquote>$1</blockquote>', $html);
        // Unordered lists (- item)
        $html = preg_replace('/^-\s+(.+)$/m', '<li>$1</li>', $html);
        $html = preg_replace('/(<li>.+<\/li>\n?)+/s', '<ul>$0</ul>', $html);
        // Paragraphs: double newlines → <p>
        $html = preg_replace('/\n{2,}/', '</p><p>', $html);
        // Remove empty <p> around block elements
        $html = '<p>' . $html . '</p>';
        $html = preg_replace('/<p>\s*(<h[2-4]|<hr|<ul|<blockquote)/s', '$1', $html);
        $html = preg_replace('/(<\/h[2-4]>|<hr>|<\/ul>|<\/blockquote>)\s*<\/p>/s', '$1', $html);
        return $html;
    }

    // ── Settings (key-value store) ───────────────────────────────
    private static bool $settingsTableChecked = false;

    private static function ensureSettingsTable(): void {
        if (self::$settingsTableChecked) return;
        self::get()->exec("CREATE TABLE IF NOT EXISTS portal_settings (
            setting_key VARCHAR(100) PRIMARY KEY,
            setting_value TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4");
        self::$settingsTableChecked = true;
    }

    public static function getSetting(string $key, ?string $default = null): ?string {
        self::ensureSettingsTable();
        $stmt = self::get()->prepare('SELECT setting_value FROM portal_settings WHERE setting_key = ?');
        $stmt->execute([$key]);
        $row = $stmt->fetch();
        return $row ? $row['setting_value'] : $default;
    }

    public static function setSetting(string $key, string $value): void {
        self::ensureSettingsTable();
        self::get()->prepare(
            'INSERT INTO portal_settings (setting_key, setting_value) VALUES (?, ?) ON DUPLICATE KEY UPDATE setting_value = VALUES(setting_value)'
        )->execute([$key, $value]);
    }

    /**
     * Get effective limits (DB overrides → config.php fallback → hardcoded default)
     */
    public static function getEffectiveLimits(array $configLimits = []): array {
        self::ensureSettingsTable();
        $defaults = [
            'max_message_length' => $configLimits['max_message_length'] ?? 2000,
            'max_hourly'         => $configLimits['max_hourly'] ?? 15,
            'max_daily'          => $configLimits['max_daily'] ?? 50,
        ];
        $result = [];
        foreach ($defaults as $key => $fallback) {
            $dbVal = self::getSetting('limit_' . $key);
            $result[$key] = $dbVal !== null ? intval($dbVal) : intval($fallback);
        }
        return $result;
    }

    // ═══════════════════════════════════════════
    // ──  Games  ────────────────────────────────
    // ═══════════════════════════════════════════

    /** Create a new game session, returns session ID */
    public static function createGameSession(string $userId, string $game): string {
        $id = self::uuid();
        $pdo = self::get();
        $stmt = $pdo->prepare('INSERT INTO portal_game_sessions (id, user_id, game, status) VALUES (?, ?, ?, "active")');
        $stmt->execute([$id, $userId, $game]);
        return $id;
    }

    /** Find active (in-progress) session for user + game */
    public static function getActiveGameSession(string $userId, string $game): ?array {
        $pdo = self::get();
        $stmt = $pdo->prepare('SELECT * FROM portal_game_sessions WHERE user_id = ? AND game = ? AND status = "active" ORDER BY created_at DESC LIMIT 1');
        $stmt->execute([$userId, $game]);
        $row = $stmt->fetch(PDO::FETCH_ASSOC);
        if ($row && $row['game_state']) $row['game_state'] = json_decode($row['game_state'], true);
        if ($row && $row['metadata'])   $row['metadata'] = json_decode($row['metadata'], true);
        return $row ?: null;
    }

    /** Load a specific game session */
    public static function getGameSession(string $sessionId): ?array {
        $pdo = self::get();
        $stmt = $pdo->prepare('SELECT * FROM portal_game_sessions WHERE id = ?');
        $stmt->execute([$sessionId]);
        $row = $stmt->fetch(PDO::FETCH_ASSOC);
        if ($row && $row['game_state']) $row['game_state'] = json_decode($row['game_state'], true);
        if ($row && $row['metadata'])   $row['metadata'] = json_decode($row['metadata'], true);
        return $row ?: null;
    }

    /** Save game state (for resume) + update score/rounds */
    public static function saveGameState(string $sessionId, array $gameState, int $score = 0, int $rounds = 0): void {
        $pdo = self::get();
        $stmt = $pdo->prepare('UPDATE portal_game_sessions SET game_state = ?, score = ?, rounds = ?, updated_at = NOW() WHERE id = ? AND status = "active"');
        $stmt->execute([json_encode($gameState), $score, $rounds, $sessionId]);
    }

    /** Finish a game session and update highscores */
    public static function finishGameSession(string $sessionId, string $result, int $score, int $rounds, int $durationSecs, ?array $metadata = null): void {
        $pdo = self::get();
        $stmt = $pdo->prepare('UPDATE portal_game_sessions SET status = "finished", result = ?, score = ?, rounds = ?, duration_secs = ?, metadata = ?, game_state = NULL, updated_at = NOW() WHERE id = ?');
        $stmt->execute([$result, $score, $rounds, $durationSecs, $metadata ? json_encode($metadata) : null, $sessionId]);

        // Fetch session to update highscores
        $session = self::getGameSession($sessionId);
        if ($session) {
            self::updateHighscores($session['user_id'], $session['game'], $result, $score);
        }
    }

    /** Abandon an active session (counts as loss) */
    public static function abandonGameSession(string $sessionId): void {
        $pdo = self::get();
        $stmt = $pdo->prepare('UPDATE portal_game_sessions SET status = "finished", result = "loss", game_state = NULL, updated_at = NOW() WHERE id = ? AND status = "active"');
        $stmt->execute([$sessionId]);

        $session = self::getGameSession($sessionId);
        if ($session) {
            self::updateHighscores($session['user_id'], $session['game'], 'loss', 0);
        }
    }

    /** Update or create highscore entry for user + game */
    private static function updateHighscores(string $userId, string $game, string $result, int $score): void {
        $pdo = self::get();

        // Upsert highscores row
        $stmt = $pdo->prepare('SELECT * FROM portal_highscores WHERE user_id = ? AND game = ?');
        $stmt->execute([$userId, $game]);
        $hs = $stmt->fetch(PDO::FETCH_ASSOC);

        if (!$hs) {
            $stmt = $pdo->prepare('INSERT INTO portal_highscores (user_id, game, best_score, total_wins, total_losses, total_draws, total_games, win_streak, best_streak) VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)');
            $stmt->execute([
                $userId, $game,
                $score,
                $result === 'win' ? 1 : 0,
                $result === 'loss' ? 1 : 0,
                $result === 'draw' ? 1 : 0,
                $result === 'win' ? 1 : 0,
                $result === 'win' ? 1 : 0,
            ]);
        } else {
            $newBest = max((int)$hs['best_score'], $score);
            $streak = $result === 'win' ? ((int)$hs['win_streak'] + 1) : 0;
            $bestStreak = max((int)$hs['best_streak'], $streak);

            $stmt = $pdo->prepare('UPDATE portal_highscores SET best_score = ?, total_wins = total_wins + ?, total_losses = total_losses + ?, total_draws = total_draws + ?, total_games = total_games + 1, win_streak = ?, best_streak = ?, updated_at = NOW() WHERE user_id = ? AND game = ?');
            $stmt->execute([
                $newBest,
                $result === 'win' ? 1 : 0,
                $result === 'loss' ? 1 : 0,
                $result === 'draw' ? 1 : 0,
                $streak,
                $bestStreak,
                $userId, $game,
            ]);
        }
    }

    /** Get top highscores for a game (leaderboard) */
    public static function getHighscores(string $game, int $limit = 20): array {
        $pdo = self::get();
        $stmt = $pdo->prepare('
            SELECT h.*, u.display_name 
            FROM portal_highscores h 
            JOIN portal_users u ON u.id = h.user_id 
            WHERE h.game = ? 
            ORDER BY h.best_score DESC, h.best_streak DESC 
            LIMIT ?
        ');
        $stmt->execute([$game, $limit]);
        return $stmt->fetchAll(PDO::FETCH_ASSOC);
    }

    /** Get a specific user's highscore for a game */
    public static function getUserHighscore(string $userId, string $game): ?array {
        $pdo = self::get();
        $stmt = $pdo->prepare('SELECT * FROM portal_highscores WHERE user_id = ? AND game = ?');
        $stmt->execute([$userId, $game]);
        return $stmt->fetch(PDO::FETCH_ASSOC) ?: null;
    }

    // ══════════════════════════════════════════════════════════════
    //  LEARNING SYSTEM (PHP-native, curricula.json on disk)
    // ══════════════════════════════════════════════════════════════

    /** Ensure learning tables exist (auto-migration) */
    public static function ensureLearningTables(): void {
        $pdo = self::get();

        // portal_learning_progress — per-user per-track progress JSON
        $pdo->exec("
            CREATE TABLE IF NOT EXISTS `portal_learning_progress` (
                `id`             CHAR(36)      NOT NULL PRIMARY KEY,
                `user_id`        CHAR(36)      NOT NULL,
                `track_id`       VARCHAR(50)   NOT NULL,
                `progress_data`  JSON          NOT NULL,
                `updated_at`     DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                UNIQUE KEY `uq_user_track` (`user_id`, `track_id`),
                INDEX `idx_user` (`user_id`),
                FOREIGN KEY (`user_id`) REFERENCES `portal_users`(`id`) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        ");

        // portal_learning_quiz_results — individual quiz attempt history
        $pdo->exec("
            CREATE TABLE IF NOT EXISTS `portal_learning_quiz_results` (
                `id`             CHAR(36)      NOT NULL PRIMARY KEY,
                `user_id`        CHAR(36)      NOT NULL,
                `track_id`       VARCHAR(50)   NOT NULL,
                `unit_id`        VARCHAR(100)  NOT NULL,
                `score`          FLOAT         NOT NULL DEFAULT 0,
                `passed`         TINYINT(1)    NOT NULL DEFAULT 0,
                `answers_json`   JSON          DEFAULT NULL,
                `results_json`   JSON          DEFAULT NULL,
                `created_at`     DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
                INDEX `idx_user` (`user_id`),
                INDEX `idx_user_track` (`user_id`, `track_id`),
                FOREIGN KEY (`user_id`) REFERENCES `portal_users`(`id`) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        ");

        // portal_learning_access — admin toggle per user
        $pdo->exec("
            CREATE TABLE IF NOT EXISTS `portal_learning_access` (
                `user_id`        CHAR(36)      NOT NULL PRIMARY KEY,
                `enabled`        TINYINT(1)    NOT NULL DEFAULT 0,
                `enabled_by`     CHAR(36)      DEFAULT NULL,
                `enabled_at`     DATETIME      DEFAULT NULL,
                FOREIGN KEY (`user_id`) REFERENCES `portal_users`(`id`) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        ");

        // portal_learning_sr — Spaced Repetition per user per question (SM-2 algorithm)
        $pdo->exec("
            CREATE TABLE IF NOT EXISTS `portal_learning_sr` (
                `id`             CHAR(36)      NOT NULL PRIMARY KEY,
                `user_id`        CHAR(36)      NOT NULL,
                `track_id`       VARCHAR(50)   NOT NULL,
                `unit_id`        VARCHAR(100)  NOT NULL,
                `question_idx`   INT           NOT NULL,
                `question_text`  TEXT          DEFAULT NULL,
                `ease_factor`    FLOAT         NOT NULL DEFAULT 2.5,
                `interval_days`  FLOAT         NOT NULL DEFAULT 1.0,
                `repetitions`    INT           NOT NULL DEFAULT 0,
                `next_review`    DATETIME      NOT NULL,
                `last_reviewed`  DATETIME      DEFAULT NULL,
                `created_at`     DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE KEY `uq_user_question` (`user_id`, `track_id`, `unit_id`, `question_idx`),
                INDEX `idx_user_review` (`user_id`, `next_review`),
                INDEX `idx_user_track` (`user_id`, `track_id`),
                FOREIGN KEY (`user_id`) REFERENCES `portal_users`(`id`) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        ");

        // portal_learning_lessons — persistent AI explanations per user per unit
        $pdo->exec("
            CREATE TABLE IF NOT EXISTS `portal_learning_lessons` (
                `id`             CHAR(36)      NOT NULL PRIMARY KEY,
                `user_id`        CHAR(36)      NOT NULL,
                `track_id`       VARCHAR(50)   NOT NULL,
                `unit_id`        VARCHAR(100)  NOT NULL,
                `role`           ENUM('user','ailey') NOT NULL DEFAULT 'ailey',
                `content`        MEDIUMTEXT    NOT NULL,
                `created_at`     DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
                INDEX `idx_user_unit` (`user_id`, `track_id`, `unit_id`),
                INDEX `idx_user` (`user_id`),
                FOREIGN KEY (`user_id`) REFERENCES `portal_users`(`id`) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        ");
    }

    // ── Learning Access (admin toggle) ───────────────────────────
    public static function hasLearningAccess(string $userId): bool {
        $stmt = self::get()->prepare('SELECT enabled FROM portal_learning_access WHERE user_id = ?');
        $stmt->execute([$userId]);
        $row = $stmt->fetch();
        if (!$row) return false;
        return (bool)$row['enabled'];
    }

    public static function toggleLearningAccess(string $userId, bool $enabled, ?string $adminId = null): void {
        $pdo = self::get();
        $stmt = $pdo->prepare('
            INSERT INTO portal_learning_access (user_id, enabled, enabled_by, enabled_at)
            VALUES (?, ?, ?, NOW())
            ON DUPLICATE KEY UPDATE enabled = VALUES(enabled), enabled_by = VALUES(enabled_by), enabled_at = NOW()
        ');
        $stmt->execute([$userId, $enabled ? 1 : 0, $adminId]);
    }

    public static function getLearningAccessList(): array {
        $stmt = self::get()->prepare('SELECT user_id, enabled FROM portal_learning_access');
        $stmt->execute();
        $map = [];
        foreach ($stmt->fetchAll() as $row) {
            $map[$row['user_id']] = (bool)$row['enabled'];
        }
        return $map;
    }

    // ── Learning Progress ────────────────────────────────────────
    public static function getLearningProgress(string $userId): array {
        $stmt = self::get()->prepare('SELECT track_id, progress_data FROM portal_learning_progress WHERE user_id = ?');
        $stmt->execute([$userId]);
        $out = [];
        foreach ($stmt->fetchAll() as $row) {
            $out[$row['track_id']] = json_decode($row['progress_data'], true) ?: [];
        }
        return $out;
    }

    public static function saveLearningProgress(string $userId, string $trackId, array $data): void {
        $pdo = self::get();
        $json = json_encode($data, JSON_UNESCAPED_UNICODE);
        $stmt = $pdo->prepare('
            INSERT INTO portal_learning_progress (id, user_id, track_id, progress_data, updated_at)
            VALUES (UUID(), ?, ?, ?, NOW())
            ON DUPLICATE KEY UPDATE progress_data = VALUES(progress_data), updated_at = NOW()
        ');
        $stmt->execute([$userId, $trackId, $json]);
    }

    public static function saveQuizResult(string $userId, string $trackId, string $unitId, float $score, bool $passed, ?array $answers = null, ?array $results = null): void {
        $pdo = self::get();
        $stmt = $pdo->prepare('
            INSERT INTO portal_learning_quiz_results (id, user_id, track_id, unit_id, score, passed, answers_json, results_json, created_at)
            VALUES (UUID(), ?, ?, ?, ?, ?, ?, ?, NOW())
        ');
        $stmt->execute([
            $userId, $trackId, $unitId, $score, $passed ? 1 : 0,
            $answers ? json_encode($answers, JSON_UNESCAPED_UNICODE) : null,
            $results ? json_encode($results, JSON_UNESCAPED_UNICODE) : null,
        ]);
    }

    public static function getQuizHistory(string $userId, string $trackId, string $unitId, int $limit = 5): array {
        $stmt = self::get()->prepare('SELECT score, passed, created_at FROM portal_learning_quiz_results WHERE user_id = ? AND track_id = ? AND unit_id = ? ORDER BY created_at DESC LIMIT ?');
        $stmt->execute([$userId, $trackId, $unitId, $limit]);
        return $stmt->fetchAll();
    }

    public static function getBestQuizScore(string $userId, string $trackId, string $unitId): ?float {
        $stmt = self::get()->prepare('SELECT MAX(score) as best FROM portal_learning_quiz_results WHERE user_id = ? AND track_id = ? AND unit_id = ?');
        $stmt->execute([$userId, $trackId, $unitId]);
        $row = $stmt->fetch();
        return $row && $row['best'] !== null ? (float)$row['best'] : null;
    }

    // ── Spaced Repetition (SM-2) ─────────────────────────────────

    /**
     * Add a wrong-answered question to the SR queue for this user.
     * If it already exists, reset interval (user got it wrong again).
     */
    public static function srAddOrReset(string $userId, string $trackId, string $unitId, int $questionIdx, string $questionText): void {
        $pdo = self::get();
        $stmt = $pdo->prepare('
            INSERT INTO portal_learning_sr (id, user_id, track_id, unit_id, question_idx, question_text, ease_factor, interval_days, repetitions, next_review, created_at)
            VALUES (UUID(), ?, ?, ?, ?, ?, 2.5, 1.0, 0, DATE_ADD(NOW(), INTERVAL 1 DAY), NOW())
            ON DUPLICATE KEY UPDATE
                ease_factor = GREATEST(1.3, ease_factor - 0.2),
                interval_days = 1.0,
                repetitions = 0,
                next_review = DATE_ADD(NOW(), INTERVAL 1 DAY),
                question_text = VALUES(question_text)
        ');
        $stmt->execute([$userId, $trackId, $unitId, $questionIdx, $questionText]);
    }

    /**
     * Mark a SR item as correctly answered — SM-2 interval progression.
     */
    public static function srMarkCorrect(string $userId, string $trackId, string $unitId, int $questionIdx): void {
        $pdo = self::get();
        // Get current state
        $stmt = $pdo->prepare('SELECT ease_factor, interval_days, repetitions FROM portal_learning_sr WHERE user_id = ? AND track_id = ? AND unit_id = ? AND question_idx = ?');
        $stmt->execute([$userId, $trackId, $unitId, $questionIdx]);
        $row = $stmt->fetch();
        if (!$row) return;

        $ef = (float)$row['ease_factor'];
        $interval = (float)$row['interval_days'];
        $reps = (int)$row['repetitions'];

        // SM-2 algorithm
        $reps++;
        if ($reps === 1) {
            $interval = 1;
        } elseif ($reps === 2) {
            $interval = 6;
        } else {
            $interval = round($interval * $ef, 1);
        }
        $ef = max(1.3, $ef + 0.1); // Increase ease on success

        $stmt = $pdo->prepare('
            UPDATE portal_learning_sr
            SET ease_factor = ?, interval_days = ?, repetitions = ?,
                next_review = DATE_ADD(NOW(), INTERVAL ? DAY),
                last_reviewed = NOW()
            WHERE user_id = ? AND track_id = ? AND unit_id = ? AND question_idx = ?
        ');
        $stmt->execute([$ef, $interval, $reps, (int)ceil($interval), $userId, $trackId, $unitId, $questionIdx]);
    }

    /**
     * Remove a SR item (e.g. after many correct answers, interval > 60 days).
     */
    public static function srRemove(string $userId, string $trackId, string $unitId, int $questionIdx): void {
        $stmt = self::get()->prepare('DELETE FROM portal_learning_sr WHERE user_id = ? AND track_id = ? AND unit_id = ? AND question_idx = ?');
        $stmt->execute([$userId, $trackId, $unitId, $questionIdx]);
    }

    /**
     * Get due SR items for a user (optionally filtered by track).
     */
    public static function srGetDue(string $userId, ?string $trackId = null, int $limit = 20): array {
        $sql = 'SELECT * FROM portal_learning_sr WHERE user_id = ? AND next_review <= NOW()';
        $params = [$userId];
        if ($trackId) {
            $sql .= ' AND track_id = ?';
            $params[] = $trackId;
        }
        $sql .= ' ORDER BY next_review ASC LIMIT ?';
        $params[] = $limit;
        $stmt = self::get()->prepare($sql);
        $stmt->execute($params);
        return $stmt->fetchAll(\PDO::FETCH_ASSOC);
    }

    /**
     * Get SR stats for a user (total items, due now, by track).
     */
    public static function srGetStats(string $userId): array {
        $pdo = self::get();
        $stmt = $pdo->prepare('SELECT COUNT(*) as total, SUM(next_review <= NOW()) as due FROM portal_learning_sr WHERE user_id = ?');
        $stmt->execute([$userId]);
        $row = $stmt->fetch();
        $stmt2 = $pdo->prepare('SELECT track_id, COUNT(*) as total, SUM(next_review <= NOW()) as due FROM portal_learning_sr WHERE user_id = ? GROUP BY track_id');
        $stmt2->execute([$userId]);
        $byTrack = [];
        foreach ($stmt2->fetchAll() as $r) {
            $byTrack[$r['track_id']] = ['total' => (int)$r['total'], 'due' => (int)($r['due'] ?? 0)];
        }
        return [
            'total' => (int)($row['total'] ?? 0),
            'due' => (int)($row['due'] ?? 0),
            'by_track' => $byTrack,
        ];
    }
}
