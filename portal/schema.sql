-- ============================================================================
-- Ailey Portal — MySQL Schema for allinkl hosting
-- ============================================================================
-- Run this once on your MySQL database.
-- PHP 8.x / MySQL 8.x compatible.
-- ============================================================================

SET NAMES utf8mb4;
SET CHARACTER SET utf8mb4;

-- ─── Users ──────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS `portal_users` (
    `id`              CHAR(36)     NOT NULL PRIMARY KEY,   -- UUID
    `email`           VARCHAR(255) NOT NULL UNIQUE,
    `display_name`    VARCHAR(100) NOT NULL DEFAULT '',
    `password_hash`   VARCHAR(255) NOT NULL,
    `status`          ENUM('active','suspended','deleted') NOT NULL DEFAULT 'active',
    `role`            ENUM('user','admin')                 NOT NULL DEFAULT 'user',
    `glossary_id`     VARCHAR(100) DEFAULT NULL,            -- link to Ailey people_glossary
    `language`        VARCHAR(5)   NOT NULL DEFAULT 'de',
    `messages_today`  INT UNSIGNED NOT NULL DEFAULT 0,
    `messages_total`  INT UNSIGNED NOT NULL DEFAULT 0,
    `image_quota_daily` INT UNSIGNED NOT NULL DEFAULT 0,
    `images_generated_today` INT UNSIGNED NOT NULL DEFAULT 0,
    `last_active`     DATETIME     DEFAULT NULL,
    `consent_dsgvo`   DATETIME     DEFAULT NULL,            -- when DSGVO consent was given
    `consent_ki`      DATETIME     DEFAULT NULL,            -- when KI-Kennzeichnung was acknowledged
    `custom_instructions` TEXT       DEFAULT NULL,            -- JSON: {about_me, response_style, other}
    `created_at`      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at`      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX `idx_email` (`email`),
    INDEX `idx_status` (`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ─── Whitelist (invite-only) ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS `portal_whitelist` (
    `id`              INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    `email`           VARCHAR(255) NOT NULL UNIQUE,
    `invited_by`      CHAR(36)     DEFAULT NULL,            -- user ID of inviter (or NULL for admin)
    `invite_code`     VARCHAR(64)  DEFAULT NULL,
    `used`            TINYINT(1)   NOT NULL DEFAULT 0,
    `created_at`      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX `idx_invite_code` (`invite_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ─── Auth Sessions ──────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS `portal_sessions` (
    `id`              CHAR(36)     NOT NULL PRIMARY KEY,    -- session UUID
    `user_id`         CHAR(36)     NOT NULL,
    `token_hash`      VARCHAR(255) NOT NULL,                 -- SHA-256 of session token
    `device_info`     VARCHAR(500) DEFAULT NULL,              -- User-Agent etc.
    `ip_address`      VARCHAR(45)  DEFAULT NULL,
    `expires_at`      DATETIME     NOT NULL,
    `created_at`      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX `idx_user` (`user_id`),
    INDEX `idx_expires` (`expires_at`),
    FOREIGN KEY (`user_id`) REFERENCES `portal_users`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ─── Conversations ──────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS `portal_conversations` (
    `id`              CHAR(36)     NOT NULL PRIMARY KEY,
    `user_id`         CHAR(36)     NOT NULL,
    `title`           VARCHAR(200) DEFAULT NULL,
    `summary`         TEXT         DEFAULT NULL,              -- rolling summary for context
    `message_count`   INT UNSIGNED NOT NULL DEFAULT 0,
    `last_message_at` DATETIME     DEFAULT NULL,
    `created_at`      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at`      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX `idx_user` (`user_id`),
    INDEX `idx_last_msg` (`last_message_at`),
    FOREIGN KEY (`user_id`) REFERENCES `portal_users`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ─── Messages ───────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS `portal_messages` (
    `id`              CHAR(36)     NOT NULL PRIMARY KEY,
    `conversation_id` CHAR(36)     NOT NULL,
    `role`            ENUM('user','assistant') NOT NULL,
    `content`         TEXT         NOT NULL,
    `mood`            VARCHAR(30)  DEFAULT NULL,
    `tokens`          INT UNSIGNED DEFAULT NULL,
    `processing_ms`   INT UNSIGNED DEFAULT NULL,              -- how long Ailey took
    `image_url`       VARCHAR(500) DEFAULT NULL,              -- generated image URL (if any)
    `thinking`        MEDIUMTEXT   DEFAULT NULL,              -- reasoning/thinking content (persistent, survives refresh & other devices)
    `created_at`      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX `idx_conv` (`conversation_id`),
    INDEX `idx_created` (`created_at`),
    FOREIGN KEY (`conversation_id`) REFERENCES `portal_conversations`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ─── Queue (main message pipeline — Ailey Core polls this) ──────────────────
CREATE TABLE IF NOT EXISTS `portal_offline_queue` (
    `id`                 CHAR(36)     NOT NULL PRIMARY KEY,
    `user_id`            CHAR(36)     NOT NULL,
    `conversation_id`    CHAR(36)     NOT NULL DEFAULT '',
    `message`            TEXT         NOT NULL,                    -- user message or "__system:delete_user" etc.
    `context`            LONGTEXT     DEFAULT NULL,                -- JSON: history, summary, user_name, language, etc.
    `status`             ENUM('pending','processing','done','failed') NOT NULL DEFAULT 'pending',
    `reply`              TEXT         DEFAULT NULL,                -- Ailey's response
    `mood`               VARCHAR(30)  DEFAULT NULL,                -- detected mood
    `conversation_title` VARCHAR(200) DEFAULT NULL,                -- auto-generated title
    `image_url`          VARCHAR(500) DEFAULT NULL,                -- generated image URL
    `processing_ms`      INT UNSIGNED DEFAULT NULL,
    `created_at`         DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `processed_at`       DATETIME     DEFAULT NULL,
    INDEX `idx_user` (`user_id`),
    INDEX `idx_status` (`status`),
    INDEX `idx_status_created` (`status`, `created_at`),
    FOREIGN KEY (`user_id`) REFERENCES `portal_users`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ─── Admin Log ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS `portal_admin_log` (
    `id`              INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    `admin_id`        CHAR(36)     DEFAULT NULL,
    `action`          VARCHAR(100) NOT NULL,
    `target_user_id`  CHAR(36)     DEFAULT NULL,
    `details`         TEXT         DEFAULT NULL,
    `ip_address`      VARCHAR(45)  DEFAULT NULL,
    `created_at`      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX `idx_admin` (`admin_id`),
    INDEX `idx_action` (`action`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ─── Consent Log (DSGVO) ───────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS `portal_consent_log` (
    `id`              INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    `user_id`         CHAR(36)     NOT NULL,
    `consent_type`    ENUM('dsgvo','ki_disclosure','data_processing') NOT NULL,
    `consent_given`   TINYINT(1)   NOT NULL DEFAULT 1,
    `consent_text`    TEXT         DEFAULT NULL,               -- the text the user agreed to
    `ip_address`      VARCHAR(45)  DEFAULT NULL,
    `created_at`      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX `idx_user` (`user_id`),
    FOREIGN KEY (`user_id`) REFERENCES `portal_users`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ─── Rate Limit Tracking ────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS `portal_rate_limits` (
    `user_id`         CHAR(36)     NOT NULL,
    `window_start`    DATETIME     NOT NULL,
    `window_type`     ENUM('hourly','daily') NOT NULL,
    `count`           INT UNSIGNED NOT NULL DEFAULT 0,
    PRIMARY KEY (`user_id`, `window_start`, `window_type`),
    INDEX `idx_window` (`window_start`),
    FOREIGN KEY (`user_id`) REFERENCES `portal_users`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ─── Artifacts (Code + SVGs extracted from Ailey's replies) ─────────────────
CREATE TABLE IF NOT EXISTS `portal_artifacts` (
    `id`              CHAR(36)     NOT NULL PRIMARY KEY,
    `user_id`         CHAR(36)     NOT NULL,
    `conversation_id` CHAR(36)     DEFAULT NULL,
    `message_id`      CHAR(36)     DEFAULT NULL,
    `type`            ENUM('code','svg') NOT NULL,
    `language`        VARCHAR(30)  DEFAULT NULL,              -- e.g. 'python', 'javascript', 'svg'
    `title`           VARCHAR(200) DEFAULT NULL,              -- auto-generated or first line
    `content`         LONGTEXT     NOT NULL,                  -- the actual code/SVG
    `size_bytes`      INT UNSIGNED DEFAULT NULL,
    `created_at`      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX `idx_user` (`user_id`),
    INDEX `idx_user_type` (`user_id`, `type`),
    INDEX `idx_conv` (`conversation_id`),
    INDEX `idx_created` (`created_at`),
    FOREIGN KEY (`user_id`) REFERENCES `portal_users`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ─── Initial Admin (Simon) ──────────────────────────────────────────────────
-- Run this separately after creating the schema.
-- Replace the password_hash with the actual bcrypt hash.
-- INSERT INTO portal_users (id, email, display_name, password_hash, role, status)
-- VALUES (UUID(), 'simon@example.de', 'Simon', '$2y$10$YOUR_HASH_HERE', 'admin', 'active');
