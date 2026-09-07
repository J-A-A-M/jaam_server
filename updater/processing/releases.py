"""Чиста логіка вибору файлів релізів (production/beta)."""


def select_release_files(releases_cache, predicate, get_file_names, logger, strip_pattern="JAAM_", limit=5):
    """Фільтрує релізи за `predicate` і повертає перші `limit` імен файлів."""
    filtered = [r for r in releases_cache if predicate(r)]
    return get_file_names(logger, filtered, strip_pattern=strip_pattern)[:limit]
