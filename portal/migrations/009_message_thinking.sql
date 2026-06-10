-- ─── Migration 009: Persistent Reasoning/Thinking on Messages ───────────────
-- Stores Ailey's reasoning ("thinking") content directly on the assistant
-- message row so it survives page refreshes and is visible across devices.
-- Previously thinking was only kept in a transient cache file
-- (uploads/thinking_cache/{queue_id}.txt) that was read once during live
-- polling (check_reply) and then lost from the conversation history.
--
-- Safe to run multiple times: db.php also ensures this column on connect
-- (lazy ADD COLUMN guard), but this file documents the canonical change.

ALTER TABLE `portal_messages`
    ADD COLUMN IF NOT EXISTS `thinking` MEDIUMTEXT DEFAULT NULL AFTER `image_url`;
