
cases={}
def open_case(cid,text):
    cases[cid]={"status":"open","evidence":[],"notes":[text]}
def add_evidence(cid,ev):
    cases[cid]["evidence"].append(ev)
def close(cid):
    cases[cid]["status"]="closed"
