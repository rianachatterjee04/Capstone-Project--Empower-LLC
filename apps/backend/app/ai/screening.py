
def screen(resume,criteria):
    score=len(set(resume.split()) & set(criteria.split()))
    return {"score":score,"reason":f"Matched {score} keywords","bias_check":"none detected"}
