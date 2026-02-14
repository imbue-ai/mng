from imbue.imbue_common.pure import pure


@pure
def compute_default_url(url_by_type: dict[str, str]) -> str | None:
    """Extract the default URL from a dict of URLs keyed by type.

    Returns the "default" key if present, or the only value if exactly one URL
    exists, or None otherwise.
    """
    default_url = url_by_type.get("default")
    if default_url is not None:
        return default_url
    if len(url_by_type) == 1:
        return next(iter(url_by_type.values()))
    return None
