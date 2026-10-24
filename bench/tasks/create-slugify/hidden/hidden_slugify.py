from slugify import slugify

assert slugify("") == ""
assert slugify("---") == ""
assert slugify("x") == "x"
assert slugify("A_B") == "a-b"
assert slugify("a&b") == "a-b"
assert slugify("Hello,   World!!") == "hello-world"
assert slugify("2024-01-05") == "2024-01-05"
assert slugify("-lead and trail-") == "lead-and-trail"
print("hidden tests passed")
