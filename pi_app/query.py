ALIASES = {
    "phone": {"phone", "iphone", "cellphone"},
    "wallet": {"wallet"},
    "airpods": {"airpods", "airpod", "airport", "airports", "earbuds", "earbud"},
}


def extract_target_object(transcript: str) -> str:
    tokens = set(transcript.lower().replace("?", " ").replace(".", " ").split())
    for object_name, aliases in ALIASES.items():
        if tokens & aliases:
            return object_name
    return "unknown"
