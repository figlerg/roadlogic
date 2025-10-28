"""
In some parts of the code we need a number as an ID. 
I figured, I might as well use a bijection to encode and decode the string names. 
This encoding can easily be reversed and is persistent, so we can just remember the ids for our usual actor names:
ego     ...     6645615
car1    ...     1667330609
"""


def encode(s: str) -> int:
    if s == 'obstacle':
        return 161867879 # forgive me
    return int.from_bytes(s.encode("utf-8"), "big")

def decode(n: int) -> str:
    if n == 161867879:
        return 'obstacle'
    return n.to_bytes((n.bit_length() + 7) // 8, "big").decode("utf-8")

# print(encode("ego"))
# print(encode("car1"))


# test = "ego"

# encoded = encode(test)
# decoded = decode(encoded)

# print(test, encoded, decoded)