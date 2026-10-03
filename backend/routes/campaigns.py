from fastapi import APIRouter, Body
from typing import List, Dict, Any
from services.database_manager import campaign_repo
from models.campaign import Campaign

router = APIRouter(prefix="/campaigns", tags=["Campaigns"])

# In-memory fallback
campaigns_db: List[Dict[str, Any]] = []


@router.get("", response_model=List[Dict[str, Any]])
def get_campaigns():
    pg_campaigns = campaign_repo.get_all()
    if pg_campaigns:
        return pg_campaigns
    return campaigns_db


@router.post("")
def create_campaign(campaign: Dict[str, Any] = Body(...)):
    global campaigns_db
    if "id" not in campaign:
        campaign["id"] = f"camp-{len(campaigns_db) + 1}"
    campaigns_db.append(campaign)
    campaign_repo.save(Campaign.from_dict(campaign))
    return campaign
