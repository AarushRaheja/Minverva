def find_duplicates(items):
    seen = []
    dups = []
    for x in items:
        if x in seen and x not in dups:
            dups.append(x)
        seen.append(x)
    return dups
