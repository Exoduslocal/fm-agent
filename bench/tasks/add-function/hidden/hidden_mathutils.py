from mathutils import mean, clamp, median

# the existing functions must still work
assert mean([1, 2, 3, 4]) == 2.5
assert clamp(-1, 0, 10) == 0
assert clamp(5, 0, 10) == 5

assert median([5]) == 5
assert median([1, 2]) == 1.5
assert median([-1, -5, -3]) == -3
assert median([9, 1, 5, 3, 7]) == 5
values = [3, 1, 2]
median(values)
assert values == [3, 1, 2], "median must not modify its input"
print("hidden tests passed")
