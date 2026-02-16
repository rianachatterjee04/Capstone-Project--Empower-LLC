
def required_documents():
    return ["I9_section1","I9_section2","W4","DirectDeposit"]

def is_complete(submitted):
    return all(doc in submitted for doc in required_documents())
