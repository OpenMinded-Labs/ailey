-- ============================================================================
-- Migration 008: User Warning System (Ailey Self-Moderation)
-- ============================================================================
-- Ailey can autonomously escalate trolling users through warning levels:
--   Level 0: Clean — no warnings
--   Level 1: Verbal warning (Ailey tells user to stop)
--   Level 2: 1 hour ban
--   Level 3: 24 hour ban
--   Level 4: 1 week ban
--   Level 5: Permaban (until admin resets or user sends apology email)
--
-- Admins (role='admin') are NEVER subject to warnings/bans.
-- Admin can reset/reduce warning levels via admin panel.
-- ============================================================================

ALTER TABLE `portal_users`
    ADD COLUMN `warning_level` TINYINT UNSIGNED NOT NULL DEFAULT 0 AFTER `tools_song_gen`,
    ADD COLUMN `banned_until`  DATETIME DEFAULT NULL AFTER `warning_level`,
    ADD COLUMN `warning_reason` VARCHAR(500) DEFAULT NULL AFTER `banned_until`;
