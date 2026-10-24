from textutils import title_case, word_count, reverse_words

assert title_case("hello big world") == "Hello Big World"
assert reverse_words("a b c") == "c b a"
assert word_count("hello world") == 2
assert word_count("a  b") == 2, f"word_count('a  b') gave {word_count('a  b')}, expected 2"
print("all tests passed")
