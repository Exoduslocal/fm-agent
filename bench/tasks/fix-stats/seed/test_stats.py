from stats import mean, clamp, is_even

assert mean([2, 4, 6]) == 4, f"mean([2,4,6]) gave {mean([2,4,6])}, expected 4"
assert clamp(15, 0, 10) == 10, f"clamp(15,0,10) gave {clamp(15,0,10)}, expected 10"
assert clamp(-5, 0, 10) == 0, f"clamp(-5,0,10) gave {clamp(-5,0,10)}, expected 0"
assert is_even(4) is True, "is_even(4) should be True"
assert is_even(7) is False, "is_even(7) should be False"
print("all tests passed")
