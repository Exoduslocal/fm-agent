# Held-out tests: the agent never sees these. They catch fixes that hard-code the
# bounds from the visible test, or that fix one case and break another.
from stats import mean, clamp, is_even

assert mean([1, 2, 3, 4]) == 2.5
assert mean([10]) == 10
assert clamp(5, 0, 10) == 5
assert clamp(0, 0, 10) == 0
assert clamp(10, 0, 10) == 10
assert clamp(11, 0, 10) == 10
assert clamp(15, 0, 5) == 5
assert clamp(-3, -2, 2) == -2
assert clamp(-1, 0, 10) == 0
assert is_even(0) is True
assert is_even(3) is False
assert is_even(-2) is True
assert is_even(-3) is False
print("hidden tests passed")
