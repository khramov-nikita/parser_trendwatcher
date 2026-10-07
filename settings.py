"""Настройки сборщика (локальные константы, без секретов)."""

# Подстроки в path/query URL из sitemap — такие адреса не считаем событиями.
# Можно дополнять. Сравнение без учёта регистра.
SITEMAP_EXCLUDE_SUBSTRINGS: tuple[str, ...] = (
    # политика / оферта
    "privacy",
    "policy",
    "cookie",
    "terms",
    "tos",
    "legal",
    "offer",
    "оферт",
    "политик",
    "конфиденц",
    # поиск
    "/search",
    "search?",
    "?q=",
    "&q=",
    "/поиск",
    # теги
    "/tag/",
    "/tags/",
    "/label/",
    "/topic/",
    "/topics/",
    "/тег",
    # авторы
    "/author/",
    "/authors/",
    "/writer/",
    "/user/",
    "/users/",
    "/автор",
    # постраничная навигация
    "/page/",
    "/pages/",
    "page=",
    "/p/",
    # ленты
    "/feed",
    "/rss",
    "/atom",
    "sitemap",
)
