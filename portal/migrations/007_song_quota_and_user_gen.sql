-- ============================================================================
-- Migration 007: Song Quota + User-Generated Content Storage
-- ============================================================================
-- Adds song generation quota (analogous to image_quota_daily) and
-- a table for user-generated content (images/songs belong to users,
-- NOT to Ailey's public gallery).
-- ============================================================================

-- ─── Song Quota columns on portal_users ─────────────────────────────────────
ALTER TABLE `portal_users`
    ADD COLUMN `song_quota_daily` INT UNSIGNED NOT NULL DEFAULT 0 AFTER `images_generated_today`,
    ADD COLUMN `songs_generated_today` INT UNSIGNED NOT NULL DEFAULT 0 AFTER `song_quota_daily`,
    ADD COLUMN `tools_image_gen` TINYINT(1) NOT NULL DEFAULT 0 AFTER `songs_generated_today`,
    ADD COLUMN `tools_song_gen` TINYINT(1) NOT NULL DEFAULT 0 AFTER `tools_image_gen`;

-- ─── User-Generated Content Table ───────────────────────────────────────────
-- User-created images and songs are stored HERE, not in ailey_gallery_items.
-- They belong to the user and are NOT auto-pushed to the public gallery.
CREATE TABLE IF NOT EXISTS `portal_user_generations` (
    `id`              CHAR(36)     NOT NULL PRIMARY KEY,
    `user_id`         CHAR(36)     NOT NULL,
    `type`            ENUM('image','song') NOT NULL,
    `title`           VARCHAR(200) DEFAULT NULL,
    `prompt`          TEXT         DEFAULT NULL,          -- user's original prompt
    `prompt_english`  TEXT         DEFAULT NULL,          -- LLM-translated English prompt
    `file_url`        VARCHAR(500) DEFAULT NULL,          -- URL on allinkl (uploaded file)
    `file_name`       VARCHAR(255) DEFAULT NULL,          -- original filename
    `metadata`        JSON         DEFAULT NULL,          -- aspect_ratio, steps, duration, tags, etc.
    `created_at`      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX `idx_user` (`user_id`),
    INDEX `idx_user_type` (`user_id`, `type`),
    INDEX `idx_created` (`created_at`),
    FOREIGN KEY (`user_id`) REFERENCES `portal_users`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
