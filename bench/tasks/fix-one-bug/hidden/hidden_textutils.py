from textutils import title_case, word_count, reverse_words

assert word_count("") == 0
assert word_count("one") == 1
assert word_count(" a b ") == 2
assert word_count("a\tb\nc") == 3
assert word_count("the quick  brown   fox") == 4
assert title_case("hello world") == "Hello World"
assert title_case("") == ""
assert reverse_words("a b c") == "c b a"
assert reverse_words("one") == "one"
print("hidden tests passed")
