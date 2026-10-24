from slugify import slugify

assert slugify("Hello World") == "hello-world"
assert slugify("  Foo -- Bar!  ") == "foo-bar"
assert slugify("Python 3.12") == "python-3-12"
print("all tests passed")
