SEEN = set()

async def remember(finding):
    key = str(finding)
    if key in SEEN:
        return False
    SEEN.add(key)
    return True

