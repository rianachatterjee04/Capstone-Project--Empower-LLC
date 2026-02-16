
cycles={}
reviews={}

def start_cycle(name):
    cycles[name]=[]

def submit(employee,score):
    reviews.setdefault(employee,[]).append(score)
