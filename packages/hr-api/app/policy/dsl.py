
# Example DSL: "IF severity >= high THEN escalate WITHIN 48h"
def parse(policy_text: str) -> dict:
    return {"raw": policy_text}
