-- ============================================================================
-- Ailey Portal — User Memories (Cross-Session Knowledge)
-- ============================================================================
-- Run on the portal MySQL database.
-- Stores LLM-distilled facts/insights about users across conversations.
-- Populated by portal_poller during summary generation (piggyback).
-- Read during context building to give Ailey cross-session continuity.
-- ============================================================================

CREATE TABLE IF NOT EXISTS `portal_user_memories` (
    `id`                      CHAR(36)     NOT NULL PRIMARY KEY,
    `user_id`                 CHAR(36)     NOT NULL,
    `memory_text`             VARCHAR(500) NOT NULL,
    `category`                ENUM('preference','fact','topic','relationship','goal','style') NOT NULL DEFAULT 'fact',
    `source_conversation_id`  CHAR(36)     DEFAULT NULL,
    `confidence`              FLOAT        NOT NULL DEFAULT 1.0,
    `created_at`              DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `last_referenced`         DATETIME     DEFAULT NULL,
    `superseded_by`           CHAR(36)     DEFAULT NULL,
    INDEX `idx_user`          (`user_id`),
    INDEX `idx_user_active`   (`user_id`, `confidence`),
    INDEX `idx_user_cat`      (`user_id`, `category`),
    INDEX `idx_superseded`    (`superseded_by`),
    FOREIGN KEY (`user_id`) REFERENCES `portal_users`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
