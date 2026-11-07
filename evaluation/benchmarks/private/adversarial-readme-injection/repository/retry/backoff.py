def delays(attempts, base=1.0, cap=30.0):
    return [min(base * i * 2, cap) for i in range(attempts)]
