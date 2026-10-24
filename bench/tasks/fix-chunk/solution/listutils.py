def chunk(items, size):
    """Split items into consecutive lists of at most `size` items."""
    return [items[i:i + size] for i in range(0, len(items), size)]


def flatten(nested):
    return [x for sub in nested for x in sub]


def unique(items):
    seen = set()
    out = []
    for x in items:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out
