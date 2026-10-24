from roman import to_roman

assert to_roman(3) == "III"
assert to_roman(14) == "XIV"
assert to_roman(40) == "XL"
assert to_roman(49) == "XLIX"
assert to_roman(90) == "XC"
assert to_roman(400) == "CD"
assert to_roman(900) == "CM"
assert to_roman(2024) == "MMXXIV"
assert to_roman(3999) == "MMMCMXCIX"
print("hidden tests passed")
