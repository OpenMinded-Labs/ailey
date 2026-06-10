-- ============================================================================
-- Migration 003: Image Generation Quota + Image URLs in messages
-- ============================================================================
-- Run this on existing portal databases to add image generation support.
-- Safe to run multiple times (IF NOT EXISTS / ADD COLUMN with error suppression).
-- ============================================================================

-- Add image quota fields to portal_users
ALTER TABLE `portal_users` ADD COLUMN `image_quota_daily` INT UNSIGNED NOT NULL DEFAULT 0 AFTER `messages_total`;
ALTER TABLE `portal_users` ADD COLUMN `images_generated_today` INT UNSIGNED NOT NULL DEFAULT 0 AFTER `image_quota_daily`;

-- Add image_url to portal_messages (for inline image display in chat)
ALTER TABLE `portal_messages` ADD COLUMN `image_url` VARCHAR(500) DEFAULT NULL AFTER `processing_ms`;

-- Add image_url to portal_offline_queue (so check_reply can return it)
ALTER TABLE `portal_offline_queue` ADD COLUMN `image_url` VARCHAR(500) DEFAULT NULL AFTER `conversation_title`;

-- ============================================================================
-- Notes:
-- • image_quota_daily: How many images a user can generate per day (0 = none)
-- • images_generated_today: Counter, reset daily by resetDailyCounters()
-- • Admin users (role='admin') bypass the quota entirely
-- • image_url: Public URL of generated image on allinkl (/uploads/gallery/...)
-- ============================================================================
