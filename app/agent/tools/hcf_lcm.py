import math

def hcf(a: int, b: int) -> int:
    return math.gcd(int(a), int(b))

def lcm(a: int, b: int) -> int:
    a, b = int(a), int(b)
    return abs(a * b) // math.gcd(a, b)