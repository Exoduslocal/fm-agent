from mathutils import mean, clamp, median

assert mean([2, 4, 6]) == 4
assert clamp(15, 0, 10) == 10
assert median([3, 1, 2]) == 2
assert median([4, 1, 3, 2]) == 2.5
print("all tests passed")
