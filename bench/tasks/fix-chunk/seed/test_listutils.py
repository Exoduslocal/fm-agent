from listutils import chunk, flatten, unique

assert flatten([[1, 2], [3], []]) == [1, 2, 3]
assert unique([3, 1, 3, 2, 1]) == [3, 1, 2]
assert chunk([1, 2, 3, 4], 2) == [[1, 2], [3, 4]]
assert chunk([1, 2, 3, 4, 5], 2) == [[1, 2], [3, 4], [5]], f"chunk([1,2,3,4,5], 2) gave {chunk([1,2,3,4,5], 2)}, expected [[1, 2], [3, 4], [5]]"
print("all tests passed")
