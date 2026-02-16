
# Total Compensation View + Performance Hooks + Benchmarking (LLM)

class TotalCompensation:
    def __init__(self, salary, bonus, equity_value, benefits_value):
        self.salary = salary
        self.bonus = bonus
        self.equity_value = equity_value
        self.benefits_value = benefits_value

    def total_comp(self):
        return self.salary + self.bonus + self.equity_value + self.benefits_value

    def comp_summary(self):
        return {
            "Salary": self.salary,
            "Bonus": self.bonus,
            "Equity": self.equity_value,
            "Benefits": self.benefits_value,
            "Total": self.total_comp()
        }
