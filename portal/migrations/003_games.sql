-- ============================================================================
-- Ailey Portal — Games & Highscores Schema
-- ============================================================================
-- Run on the portal MySQL database.
-- Tracks game sessions and highscores for "Play with Ailey" feature.
-- ============================================================================

-- ─── Game Sessions (individual game results + in-progress state) ─────────────
CREATE TABLE IF NOT EXISTS `portal_game_sessions` (
    `id`              CHAR(36)     NOT NULL PRIMARY KEY,
    `user_id`         CHAR(36)     NOT NULL,
    `game`            ENUM('quartett','duchess','server_ddos') NOT NULL,
    `status`          ENUM('active','finished') NOT NULL DEFAULT 'active',
    `result`          ENUM('win','loss','draw') DEFAULT NULL,   -- NULL while active
    `score`           INT          NOT NULL DEFAULT 0,
    `rounds`          INT UNSIGNED NOT NULL DEFAULT 0,
    `duration_secs`   INT UNSIGNED DEFAULT NULL,
    `game_state`      JSON         DEFAULT NULL,               -- full saveable state for resume
    `metadata`        JSON         DEFAULT NULL,               -- game-specific stats (final)
    `created_at`      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at`      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX `idx_user` (`user_id`),
    INDEX `idx_game` (`game`),
    INDEX `idx_active` (`user_id`, `game`, `status`),
    INDEX `idx_game_score` (`game`, `score` DESC),
    INDEX `idx_created` (`created_at`),
    FOREIGN KEY (`user_id`) REFERENCES `portal_users`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ─── Highscores (aggregated per user per game) ──────────────────────────────
CREATE TABLE IF NOT EXISTS `portal_highscores` (
    `user_id`         CHAR(36)     NOT NULL,
    `game`            ENUM('quartett','duchess','server_ddos') NOT NULL,
    `best_score`      INT          NOT NULL DEFAULT 0,
    `total_wins`      INT UNSIGNED NOT NULL DEFAULT 0,
    `total_losses`    INT UNSIGNED NOT NULL DEFAULT 0,
    `total_draws`     INT UNSIGNED NOT NULL DEFAULT 0,
    `total_games`     INT UNSIGNED NOT NULL DEFAULT 0,
    `win_streak`      INT UNSIGNED NOT NULL DEFAULT 0,         -- current streak
    `best_streak`     INT UNSIGNED NOT NULL DEFAULT 0,         -- all-time best streak
    `updated_at`      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`user_id`, `game`),
    INDEX `idx_game_score` (`game`, `best_score` DESC),
    INDEX `idx_game_wins` (`game`, `total_wins` DESC),
    FOREIGN KEY (`user_id`) REFERENCES `portal_users`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
