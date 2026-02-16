
def required_approvers(role):
    graph={
        "hire":["manager","hr"],
        "promotion":["hr","finance","exec"],
        "termination":["hr","legal"]
    }
    return graph.get(role,["hr"])
