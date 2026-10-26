from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.base import get_db
from app.services.parties import (
    list_open_parties,
    create_party,
    get_party_detail,
    close_party
)
from app.api.deps import get_current_employee
from app.schemas.party import PartyIn, PartyDetail

router = APIRouter()


@router.get("/parties")
def get_parties(
    db: Session = Depends(get_db),
    user=Depends(get_current_employee),
    open: bool = True
):
    """List open parties that the user can view."""
    return list_open_parties(db, user)


@router.post("/parties", status_code=201)
def create_new_party(
    party_data: PartyIn,
    db: Session = Depends(get_db),
    user=Depends(get_current_employee)
):
    """Create a new party."""
    try:
        return create_party(db, user, party_data)
    except Exception as e:
        if hasattr(e, 'status') and hasattr(e, 'detail'):
            raise HTTPException(status_code=e.status, detail=e.detail)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/parties/{party_id}")
def get_party(
    party_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_employee)
):
    """Get details of a specific party."""
    try:
        return get_party_detail(db, user, party_id)
    except Exception as e:
        if hasattr(e, 'status') and hasattr(e, 'detail'):
            raise HTTPException(status_code=e.status, detail=e.detail)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/parties/{party_id}/close")
def close_existing_party(
    party_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_employee)
):
    """Close an existing party."""
    try:
        return close_party(db, user, party_id)
    except Exception as e:
        if hasattr(e, 'status') and hasattr(e, 'detail'):
            raise HTTPException(status_code=e.status, detail=e.detail)
        raise HTTPException(status_code=500, detail="Internal server error")