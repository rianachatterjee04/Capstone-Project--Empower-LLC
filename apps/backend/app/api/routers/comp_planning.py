
from fastapi import APIRouter
from app.core.json_utils import json_safe
router = APIRouter(prefix="/comp", tags=["comp"])
raises={}
@router.post("/propose/{eid}")
def propose(eid:str, percent:float):
    raises[eid]=percent
    return {"proposed":percent}
