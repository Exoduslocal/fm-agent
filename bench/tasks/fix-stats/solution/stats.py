def mean(values):
    total = 0
    for v in values:
        total += v
    return total / len(values)


def clamp(x, lo, hi):
    if x < lo:
        return lo
    if x > hi:
        return hi
    return x


def is_even(n):
    return n % 2 == 0
