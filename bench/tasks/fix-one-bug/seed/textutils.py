def title_case(s):
    return " ".join(w.capitalize() for w in s.split())


def word_count(text):
    return len(text.split(" "))


def reverse_words(s):
    return " ".join(reversed(s.split()))
