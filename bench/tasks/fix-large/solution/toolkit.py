"""Small general-purpose helpers."""


def clamp(x, lo, hi):
    """Return x limited to the range [lo, hi].

    If x is below lo the result is lo; if x is above hi the result is hi.
    """
    if x < lo:
        return lo
    if x > hi:
        return hi
    return x


def lerp(a, b, t):
    """Linear interpolation between a and b.

    t = 0 gives a, t = 1 gives b, and values in between blend the two.
    """
    return a + (b - a) * t


def mean(values):
    """Arithmetic mean of a non-empty sequence of numbers.

    Raises ZeroDivisionError for an empty sequence.
    """
    total = 0
    for v in values:
        total += v
    return total / len(values)


def variance(values):
    """Population variance of a non-empty sequence of numbers.

    This is the mean of the squared differences from the mean.
    """
    m = mean(values)
    return sum((v - m) ** 2 for v in values) / len(values)


def is_prime(n):
    """Return True if n is a prime number.

    Numbers below 2 are not prime. Uses trial division up to the square root.
    """
    if n < 2:
        return False
    i = 2
    while i * i <= n:
        if n % i == 0:
            return False
        i += 1
    return True


def gcd(a, b):
    """Greatest common divisor of two non-negative integers.

    Uses the Euclidean algorithm. gcd(a, 0) is a.
    """
    while b:
        a, b = b, a % b
    return a


def lcm(a, b):
    """Least common multiple of two positive integers.

    Computed from the greatest common divisor.
    """
    return a // gcd(a, b) * b


def fib(n):
    """Return the n-th Fibonacci number, with fib(0) = 0 and fib(1) = 1.

    Computed iteratively so large n does not hit the recursion limit.
    """
    a, b = 0, 1
    for _ in range(n):
        a, b = b, a + b
    return a


def factorial(n):
    """Return n! for a non-negative integer n.

    factorial(0) is 1.
    """
    result = 1
    for i in range(2, n + 1):
        result *= i
    return result


def digit_sum(n):
    """Sum of the decimal digits of a non-negative integer.

    For example digit_sum(123) is 6.
    """
    total = 0
    while n:
        total += n % 10
        n //= 10
    return total


def reverse_string(s):
    """Return s reversed.

    Works for any string, including the empty string.
    """
    return s[::-1]


def is_palindrome(s):
    """Return True if s reads the same forwards and backwards.

    The comparison is case-sensitive and does not ignore spaces.
    """
    return s == s[::-1]


def capitalize_words(s):
    """Capitalize the first letter of every space-separated word.

    Runs of spaces are collapsed to a single space.
    """
    return " ".join(w.capitalize() for w in s.split())


def count_vowels(s):
    """Count the vowels a, e, i, o, u in s, ignoring case.

    The letter y is not treated as a vowel.
    """
    return sum(1 for ch in s.lower() if ch in "aeiou")


def truncate(s, width):
    """Shorten s to at most width characters.

    If s is longer than width, the result ends with three dots and is
    exactly width characters long. width is at least 3.
    """
    if len(s) <= width:
        return s
    return s[: width - 3] + "..."


def pad_left(s, width, fill=" "):
    """Pad s on the left with the fill character until it is width long.

    If s is already width or longer it is returned unchanged.
    """
    return fill * (width - len(s)) + s


def repeat_join(s, n, sep=""):
    """Repeat s n times, separated by sep.

    repeat_join("ab", 3, "-") is "ab-ab-ab". n = 0 gives an empty string.
    """
    return sep.join([s] * n)


def flatten(nested):
    """Flatten one level of nesting in a list of lists.

    flatten([[1, 2], [3]]) is [1, 2, 3].
    """
    return [x for sub in nested for x in sub]


def chunk(items, size):
    """Split items into consecutive lists of at most size items.

    The last chunk may be shorter.
    """
    return [items[i : i + size] for i in range(0, len(items), size)]


def rotate_list(items, k):
    """Rotate items to the right by k positions and return a new list.

    k is between 0 and len(items). rotate_list([1, 2, 3, 4, 5], 2) is
    [4, 5, 1, 2, 3]. The input list is not modified.
    """
    return items[len(items) - k :] + items[: len(items) - k]


def dedupe(items):
    """Remove duplicates from items, keeping the first occurrence of each.

    The relative order of the remaining items is preserved.
    """
    seen = set()
    out = []
    for x in items:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def running_sum(values):
    """Return the running totals of values.

    running_sum([1, 2, 3]) is [1, 3, 6].
    """
    out = []
    total = 0
    for v in values:
        total += v
        out.append(total)
    return out


def transpose(matrix):
    """Transpose a rectangular list of lists.

    Rows become columns. An empty matrix gives an empty list.
    """
    if not matrix:
        return []
    return [list(col) for col in zip(*matrix)]


def invert_dict(d):
    """Swap keys and values of a dict with unique, hashable values.

    invert_dict({"a": 1}) is {1: "a"}.
    """
    return {v: k for k, v in d.items()}


def merge_dicts(a, b):
    """Return a new dict with the items of a, updated with the items of b.

    Where both have a key, the value from b wins. Neither input is changed.
    """
    out = dict(a)
    out.update(b)
    return out


def median_of_three(a, b, c):
    """Return the middle value of three numbers.

    The result is the number that is neither the smallest nor the largest.
    """
    return sorted([a, b, c])[1]


def sign(x):
    """Return -1 for negative numbers, 1 for positive numbers and 0 for zero.

    The result is always an int.
    """
    if x < 0:
        return -1
    if x > 0:
        return 1
    return 0


def is_even(n):
    """Return True if the integer n is even.

    Zero counts as even and negative numbers are handled the same way.
    """
    return n % 2 == 0


def is_odd(n):
    """Return True if the integer n is odd.

    This is the opposite of is_even for every integer.
    """
    return n % 2 != 0


def square(x):
    """Return x multiplied by itself.

    Works for ints and floats.
    """
    return x * x


def cube(x):
    """Return x multiplied by itself twice.

    Works for ints and floats.
    """
    return x * x * x


def power_of_two(n):
    """Return True if the positive integer n is a power of two.

    One counts as a power of two (2 to the power 0). Zero and negatives are not.
    """
    return n > 0 and n & (n - 1) == 0


def count_digits(n):
    """Return the number of decimal digits in a non-negative integer.

    Zero has one digit.
    """
    return len(str(n))


def to_binary(n):
    """Return the binary representation of a non-negative integer as a string.

    to_binary(5) is "101" and to_binary(0) is "0".
    """
    return format(n, "b")


def from_binary(s):
    """Parse a string of 0s and 1s into an integer.

    from_binary("101") is 5.
    """
    return int(s, 2)


def swap_case(s):
    """Return s with upper case letters made lower case and the reverse.

    Characters that are not letters are unchanged.
    """
    return s.swapcase()


def remove_spaces(s):
    """Return s with every space character removed.

    Tabs and newlines are kept.
    """
    return s.replace(" ", "")


def first_word(s):
    """Return the first whitespace-separated word of s.

    An empty or all-whitespace string gives an empty string.
    """
    parts = s.split()
    return parts[0] if parts else ""


def last_word(s):
    """Return the last whitespace-separated word of s.

    An empty or all-whitespace string gives an empty string.
    """
    parts = s.split()
    return parts[-1] if parts else ""


def count_words(s):
    """Return the number of whitespace-separated words in s.

    Runs of whitespace count as a single separator.
    """
    return len(s.split())


def is_anagram(a, b):
    """Return True if a and b contain the same letters, ignoring case and spaces.

    Other characters are compared as they are.
    """
    clean_a = sorted(a.replace(" ", "").lower())
    clean_b = sorted(b.replace(" ", "").lower())
    return clean_a == clean_b


def char_frequency(s):
    """Return a dict mapping each character in s to how many times it occurs.

    The dict keeps the order in which characters first appear.
    """
    out = {}
    for ch in s:
        out[ch] = out.get(ch, 0) + 1
    return out


def most_common(items):
    """Return the item that occurs most often in a non-empty list.

    If several items tie, the one that appears first in the list wins.
    """
    counts = {}
    for x in items:
        counts[x] = counts.get(x, 0) + 1
    best = items[0]
    for x in items:
        if counts[x] > counts[best]:
            best = x
    return best


def take(items, n):
    """Return the first n items as a new list.

    If there are fewer than n items, all of them are returned.
    """
    return list(items[:n])


def drop(items, n):
    """Return all items after the first n as a new list.

    If there are fewer than n items, the result is empty.
    """
    return list(items[n:])


def zip_dict(keys, values):
    """Build a dict from two equal-length lists.

    zip_dict(["a", "b"], [1, 2]) is {"a": 1, "b": 2}.
    """
    return dict(zip(keys, values))


def partition(items, predicate):
    """Split items into those that satisfy predicate and those that do not.

    Returns a tuple of two lists and keeps the original order in each.
    """
    yes, no = [], []
    for x in items:
        (yes if predicate(x) else no).append(x)
    return yes, no


def interleave(a, b):
    """Interleave two lists, starting with the first item of a.

    Once the shorter list runs out, the rest of the longer one is appended.
    """
    out = []
    for i in range(max(len(a), len(b))):
        if i < len(a):
            out.append(a[i])
        if i < len(b):
            out.append(b[i])
    return out


def moving_average(values, window):
    """Return the simple moving average of values over a window.

    The result has len(values) - window + 1 items. window must be at least 1.
    """
    out = []
    for i in range(len(values) - window + 1):
        out.append(sum(values[i : i + window]) / window)
    return out


def normalize(values):
    """Scale values linearly so the smallest becomes 0 and the largest becomes 1.

    If all values are equal, every result is 0.
    """
    lo, hi = min(values), max(values)
    if hi == lo:
        return [0 for _ in values]
    return [(v - lo) / (hi - lo) for v in values]


def percent(part, whole):
    """Return part as a percentage of whole.

    A whole of zero gives 0.
    """
    if whole == 0:
        return 0
    return part * 100 / whole


def round_to(x, step):
    """Round x to the nearest multiple of step.

    step must be positive.
    """
    return round(x / step) * step
