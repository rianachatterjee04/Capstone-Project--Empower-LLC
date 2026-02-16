
# Investor and Legal Portal with Permissions and Dilution Modeling

class InvestorPortal:
    def __init__(self):
        self.users = {}

    def invite_user(self, name, role, permissions):
        self.users[name] = {"role": role, "permissions": permissions}

    def view_access(self, name, document_type):
        return document_type in self.users.get(name, {}).get("permissions", [])
