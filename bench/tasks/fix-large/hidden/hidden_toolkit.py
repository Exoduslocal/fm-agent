from toolkit import (clamp, mean, gcd, fib, chunk, rotate_list, dedupe, transpose,
                     truncate, merge_dicts)

# the function with the bug: edge cases
assert rotate_list([1, 2, 3, 4, 5], 1) == [5, 1, 2, 3, 4]
assert rotate_list([1, 2, 3, 4, 5], 0) == [1, 2, 3, 4, 5]
assert rotate_list([1, 2, 3, 4, 5], 5) == [1, 2, 3, 4, 5]
assert rotate_list([1, 2, 3, 4, 5], 4) == [2, 3, 4, 5, 1]
assert rotate_list([], 0) == []
assert rotate_list(["a", "b", "c"], 1) == ["c", "a", "b"]
original = [1, 2, 3]
rotate_list(original, 1)
assert original == [1, 2, 3], "input must not be modified"

# everything else must still work
assert clamp(-3, 0, 10) == 0
assert mean([1, 2, 3, 4]) == 2.5
assert gcd(7, 0) == 7
assert fib(0) == 0 and fib(1) == 1 and fib(20) == 6765
assert chunk([], 3) == []
assert dedupe([]) == []
assert transpose([]) == []
assert truncate("abc", 5) == "abc"
assert merge_dicts({}, {"x": 1}) == {"x": 1}
print("hidden tests passed")
