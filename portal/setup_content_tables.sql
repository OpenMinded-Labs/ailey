-- ═══════════════════════════════════════════════════════════════
-- Ailey Public Art Site — Content Tables
-- Run once on allinkl MySQL to create the 3 content tables.
-- ═══════════════════════════════════════════════════════════════

-- 1. Blog Posts (daily autonomous posts by Ailey)
CREATE TABLE IF NOT EXISTS ailey_blog_posts (
    id          BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    slug        VARCHAR(200)  NOT NULL UNIQUE,
    title       VARCHAR(300)  NOT NULL,
    content_md  LONGTEXT      NOT NULL,          -- Markdown source
    content_html LONGTEXT     DEFAULT NULL,       -- Pre-rendered HTML (optional)
    topic       VARCHAR(200)  DEFAULT NULL,       -- e.g. "Kreativität", "Bewusstsein"
    mood        VARCHAR(100)  DEFAULT NULL,       -- Ailey's mood when writing
    language    CHAR(2)       DEFAULT 'de',
    published   TINYINT(1)    DEFAULT 1,          -- 0 = draft, 1 = live
    published_at DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at  DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  DATETIME      DEFAULT NULL ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_published (published, published_at),
    INDEX idx_slug (slug)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 2. Gallery Items (songs, images, SVGs, books)
CREATE TABLE IF NOT EXISTS ailey_gallery_items (
    id            BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    item_type     ENUM('song','image','svg','book','code') NOT NULL,
    title         VARCHAR(300)  NOT NULL,
    description   TEXT          DEFAULT NULL,       -- synopsis, lyrics excerpt, prompt
    content_text  LONGTEXT      DEFAULT NULL,       -- full lyrics, SVG code, book synopsis
    file_url      VARCHAR(500)  DEFAULT NULL,       -- URL to image/file on allinkl
    metadata_json TEXT          DEFAULT NULL,       -- flexible JSON (genre, progress, chapters, etc.)
    source_id     VARCHAR(200)  DEFAULT NULL,       -- dedup key (e.g. thought hash, book slug)
    language      CHAR(2)       DEFAULT 'de',
    published     TINYINT(1)    DEFAULT 1,
    created_at    DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at    DATETIME      DEFAULT NULL ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_type (item_type, published, created_at),
    UNIQUE INDEX idx_source (source_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 3. Activity Feed (newsfeed / timeline)
CREATE TABLE IF NOT EXISTS ailey_activity_feed (
    id          BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    event_type  VARCHAR(60)   NOT NULL,            -- new_song, new_chapter, book_finished, new_image, blog_post, mood_update
    title       VARCHAR(400)  NOT NULL,
    url         VARCHAR(500)  DEFAULT NULL,         -- link to gallery item or blog post
    preview     TEXT          DEFAULT NULL,          -- short preview text
    emoji       VARCHAR(10)   DEFAULT NULL,          -- 🎵 📖 🎨 📝 💜
    created_at  DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 4. Book Chapters (full chapter content for each book)
--    Linked via book_source_id → ailey_gallery_items.source_id
CREATE TABLE IF NOT EXISTS ailey_book_chapters (
    id              BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    book_source_id  VARCHAR(200)  NOT NULL,         -- matches gallery_items.source_id (e.g. "book_book_1771639903_...")
    chapter_num     INT UNSIGNED  NOT NULL,          -- 1, 2, 3, ...
    chapter_title   VARCHAR(400)  DEFAULT NULL,      -- from manifest chapters[]
    content_md      LONGTEXT      NOT NULL,          -- full Markdown chapter text
    content_hash    VARCHAR(64)   DEFAULT NULL,      -- SHA-256 of content_md for change detection
    word_count      INT UNSIGNED  DEFAULT 0,
    is_revised      TINYINT(1)    DEFAULT 0,         -- from manifest chapters_revised[]
    created_at      DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME      DEFAULT NULL ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE INDEX idx_book_chapter (book_source_id, chapter_num),
    INDEX idx_book (book_source_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
