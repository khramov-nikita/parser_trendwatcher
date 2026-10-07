-- Sitemap-источник из карты (blog.youtube).
-- Безопасно для повторного запуска.

INSERT INTO sources (label, url, kind, enabled)
SELECT
  'YouTube Blog sitemap',
  'https://blog.youtube/sitemap.xml',
  'sitemap',
  true
WHERE NOT EXISTS (
  SELECT 1
  FROM sources
  WHERE url = 'https://blog.youtube/sitemap.xml'
);
