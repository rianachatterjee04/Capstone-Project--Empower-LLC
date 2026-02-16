
# Employee Equity Education Chatbot

class EquityBot:
    def answer(self, question):
        # Simple simulation of educational answers
        q = question.lower()
        if "vesting" in q:
            return "Vesting means your right to earn equity over time or milestones."
        elif "leave" in q:
            return "If you leave, vested shares are yours, but unvested typically go back."
        else:
            return "I'm your equity helper! Ask me about grants, taxes, or vesting."
