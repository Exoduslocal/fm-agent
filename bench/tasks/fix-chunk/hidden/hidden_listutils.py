from listutils import chunk, flatten, unique

assert chunk([], 3) == []
assert chunk([1], 1) == [[1]]
assert chunk([1, 2, 3], 5) == [[1, 2, 3]]
assert chunk([1, 2, 3, 4, 5, 6, 7], 3) == [[1, 2, 3], [4, 5, 6], [7]]
assert chunk(list("abcde"), 1) == [["a"], ["b"], ["c"], ["d"], ["e"]]
assert flatten([]) == []
assert flatten([[1], [2, 3]]) == [1, 2, 3]
assert unique([]) == []
assert unique(["a", "a"]) == ["a"]
print("hidden tests passed")
