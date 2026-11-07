def find_duplicates(items):
    seen = set()
    reported = set()
    dups = []
    for x in items:
        if x in seen and x not in reported:
            reported.add(x)
            dups.append(x)
        seen.add(x)
    return dups
