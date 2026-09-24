from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, current_user
from app.db import get_session
from app.models import Lead
from app.schemas.api import LeadOut, LeadStatusIn

router = APIRouter(prefix="/api/leads", tags=["leads"])


@router.get("", response_model=list[LeadOut])
async def list_leads(
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
    user: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    stmt = select(Lead).where(Lead.shop_id == user.shop.id).order_by(Lead.id.desc())
    if status:
        stmt = stmt.where(Lead.status == status)
    return [LeadOut.model_validate(x) for x in await session.scalars(stmt.limit(min(limit, 200)).offset(offset))]


@router.post("/{lead_id}/status", response_model=LeadOut)
async def set_lead_status(
    lead_id: int,
    body: LeadStatusIn,
    user: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    lead = await session.scalar(select(Lead).where(Lead.shop_id == user.shop.id, Lead.id == lead_id))
    if lead is None:
        raise HTTPException(404)
    lead.status = body.status
    await session.commit()
    return LeadOut.model_validate(lead)
