<?php
/**
 * Ailey Portal — Dynamic Sitemap (XML)
 *
 * Lists all public pages + blog post URLs for search engines.
 * Access via: /sitemap.xml
 */

header('Content-Type: application/xml; charset=UTF-8');

$baseUrl = $config['site']['url'] ?? 'https://hey-ailey.com';

echo '<?xml version="1.0" encoding="UTF-8"?>' . "\n";
?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
    <!-- Static public pages -->
    <url><loc><?= $baseUrl ?>/</loc><changefreq>daily</changefreq><priority>1.0</priority></url>
    <url><loc><?= $baseUrl ?>/galerie</loc><changefreq>daily</changefreq><priority>0.9</priority></url>
    <url><loc><?= $baseUrl ?>/blog</loc><changefreq>daily</changefreq><priority>0.9</priority></url>
    <url><loc><?= $baseUrl ?>/feed</loc><changefreq>hourly</changefreq><priority>0.7</priority></url>
    <url><loc><?= $baseUrl ?>/ueber-ailey</loc><changefreq>monthly</changefreq><priority>0.6</priority></url>
    <url><loc><?= $baseUrl ?>/faq</loc><changefreq>monthly</changefreq><priority>0.5</priority></url>
    <url><loc><?= $baseUrl ?>/impressum</loc><changefreq>monthly</changefreq><priority>0.3</priority></url>
    <url><loc><?= $baseUrl ?>/datenschutz</loc><changefreq>monthly</changefreq><priority>0.3</priority></url>

<?php
// Dynamic blog post URLs
try {
    $posts = PortalDB::getBlogPosts(100, 0);
    foreach ($posts as $post) {
        $slug = htmlspecialchars($post['slug']);
        $date = date('Y-m-d', strtotime($post['published_at'] ?? $post['created_at'] ?? 'now'));
?>
    <url><loc><?= $baseUrl ?>/blog/<?= $slug ?></loc><lastmod><?= $date ?></lastmod><changefreq>monthly</changefreq><priority>0.8</priority></url>
<?php
    }
} catch (Exception $e) {
    // Tables might not exist yet — silently skip
}

// Dynamic book URLs
try {
    $books = PortalDB::getGalleryItems('book', 50, 0);
    foreach ($books as $book) {
        $meta = $book['metadata'] ?? [];
        $slug = $meta['slug'] ?? '';
        if (!$slug) continue;
        $bookSlug = htmlspecialchars($slug);
?>
    <url><loc><?= $baseUrl ?>/buch/<?= $bookSlug ?></loc><changefreq>weekly</changefreq><priority>0.8</priority></url>
<?php
        // Include individual chapter URLs
        try {
            $chapters = PortalDB::getBookChapters('book_' . $slug);
            foreach ($chapters as $ch) {
                $chDate = date('Y-m-d', strtotime($ch['updated_at'] ?? $ch['created_at'] ?? 'now'));
?>
    <url><loc><?= $baseUrl ?>/buch/<?= $bookSlug ?>/kapitel/<?= (int)$ch['chapter_num'] ?></loc><lastmod><?= $chDate ?></lastmod><changefreq>weekly</changefreq><priority>0.7</priority></url>
<?php
            }
        } catch (Exception $e) { }
    }
} catch (Exception $e) { }
?>
</urlset>
