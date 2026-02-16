
def build_payroll_export(employees):
    return [{"employee_id":e["id"],"salary":e.get("salary",0)} for e in employees]
