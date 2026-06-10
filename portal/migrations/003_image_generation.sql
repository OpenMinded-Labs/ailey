-- ============================================================================
-- Migration 003: Image Generation Quota System
-- ============================================================================
-- Adds per-user daily image generation quota to portal_users
-- Adds image_url field to portal_messages + portal_offline_queue
-- ============================================================================

-- ─── portal_users: image quota fields ──────────────────────────────────────
ALTER TABLE `portal_users`
    ADD COLUMN `image_quota_daily` INT UNSIGNED NOT NULL DEFAULT 0 AFTER `messages_total`,
    ADD COLUMN `images_generated_today` INT UNSIGNED NOT NULL DEFAULT 0 AFTER `image_quota_daily`;

-- ─── portal_messages: image_url for generated images ───────────────────────
ALTER TABLE `portal_messages`
    ADD COLUMN `image_url` VARCHAR(500) DEFAULT NULL AFTER `processing_ms`;

-- ─── portal_offline_queue: image_url in reply ──────────────────────────────
ALTER TABLE `portal_offline_queue`
    ADD COLUMN `image_url` VARCHAR(500) DEFAULT NULL AFTER `conversation_title`;
