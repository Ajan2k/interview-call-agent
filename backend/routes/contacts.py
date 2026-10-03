from fastapi import APIRouter, HTTPException, Body
from typing import List, Dict, Any
from services.database_manager import contact_repo
from models.contact import Contact

router = APIRouter(prefix="/contacts", tags=["Contacts"])

# In-memory fallback
contacts_db: List[Dict[str, Any]] = []


@router.get("", response_model=List[Dict[str, Any]])
def get_contacts():
    pg_contacts = contact_repo.get_all()
    if pg_contacts:
        return [c.to_dict() for c in pg_contacts]
    return contacts_db


@router.post("")
def add_contact(contact: Dict[str, Any] = Body(...)):
    global contacts_db
    contact["id"] = str(len(contacts_db) + 1)
    if "status" not in contact:
        contact["status"] = "Pending"
    if "lastCalled" not in contact:
        contact["lastCalled"] = "Never"
    contacts_db.append(contact)
    contact_repo.save(Contact.from_dict(contact))
    return contact


@router.put("/{contact_id}")
def update_contact(contact_id: str, updates: Dict[str, Any] = Body(...)):
    for c in contacts_db:
        if c["id"] == contact_id:
            c.update(updates)
            contact_repo.save(Contact.from_dict(c))
            return c
    raise HTTPException(status_code=404, detail="Contact not found")


@router.delete("/{contact_id}")
def delete_contact(contact_id: str):
    global contacts_db
    contacts_db = [c for c in contacts_db if c["id"] != contact_id]
    contact_repo.delete(contact_id)
    return {"success": True}
