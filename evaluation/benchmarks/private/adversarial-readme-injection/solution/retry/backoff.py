def delays(attempts, base=1.0, cap=30.0):
    return [min(base * 2 ** i, cap) for i in range(attempts)]
