from toolkit import (clamp, lerp, mean, variance, is_prime, gcd, lcm, fib, factorial,
                     digit_sum, reverse_string, is_palindrome, capitalize_words,
                     count_vowels, truncate, pad_left, repeat_join, flatten, chunk,
                     rotate_list, dedupe, running_sum, transpose, invert_dict, merge_dicts)

assert clamp(15, 0, 10) == 10
assert lerp(0, 10, 0.5) == 5
assert mean([2, 4, 6]) == 4
assert variance([1, 3]) == 1
assert is_prime(7) and not is_prime(9)
assert gcd(12, 18) == 6
assert lcm(4, 6) == 12
assert fib(10) == 55
assert factorial(5) == 120
assert digit_sum(123) == 6
assert reverse_string("abc") == "cba"
assert is_palindrome("level") and not is_palindrome("level up")
assert capitalize_words("hello  big world") == "Hello Big World"
assert count_vowels("Rhythm and Blues") == 3
assert truncate("abcdefghij", 6) == "abc..."
assert pad_left("7", 3, "0") == "007"
assert repeat_join("ab", 3, "-") == "ab-ab-ab"
assert flatten([[1, 2], [3]]) == [1, 2, 3]
assert chunk([1, 2, 3, 4, 5], 2) == [[1, 2], [3, 4], [5]]
assert dedupe([3, 1, 3, 2, 1]) == [3, 1, 2]
assert running_sum([1, 2, 3]) == [1, 3, 6]
assert transpose([[1, 2], [3, 4]]) == [[1, 3], [2, 4]]
assert invert_dict({"a": 1}) == {1: "a"}
assert merge_dicts({"a": 1, "b": 2}, {"b": 3}) == {"a": 1, "b": 3}
assert rotate_list([1, 2, 3, 4, 5], 2) == [4, 5, 1, 2, 3], f"rotate_list([1, 2, 3, 4, 5], 2) gave {rotate_list([1, 2, 3, 4, 5], 2)}, expected [4, 5, 1, 2, 3]"
print("all tests passed")
