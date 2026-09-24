from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentUser, current_user
from app.db import get_session
from app.models import PLANS, Category, Product
from app.runtime import get_runtime
from app.schemas.api import CategoryIn, CategoryOut, ImportOut, ProductIn, ProductOut
from app.services.catalog import load_product, save_product
from app.services.catalog_import import import_catalog, template_xlsx
from app.services.text import normalize

router = APIRouter(prefix="/api", tags=["catalog"])
MAX_IMPORT_BYTES = 5 * 1024 * 1024


async def _enqueue_enrich(product_ids: list[int]) -> None:
    arq = get_runtime().arq
    if arq is not None:
        for pid in product_ids:
            await arq.enqueue_job("enrich_product", pid)


async def _check_product_limit(session: AsyncSession, user: CurrentUser, adding: int = 1) -> None:
    limit = PLANS.get(user.shop.plan, PLANS["start"])["max_products"]
    if limit is None:
        return
    count = await session.scalar(select(func.count()).select_from(Product).where(Product.shop_id == user.shop.id))
    if (count or 0) + adding > limit:
        raise HTTPException(402, f"Tarif bo'yicha mahsulotlar limiti: {limit}")


@router.get("/categories", response_model=list[CategoryOut])
async def list_categories(user: CurrentUser = Depends(current_user), session: AsyncSession = Depends(get_session)):
    rows = await session.scalars(select(Category).where(Category.shop_id == user.shop.id).order_by(Category.name))
    return [CategoryOut.model_validate(c) for c in rows]


@router.post("/categories", response_model=CategoryOut, status_code=201)
async def create_category(
    body: CategoryIn, user: CurrentUser = Depends(current_user), session: AsyncSession = Depends(get_session)
):
    cat = Category(shop_id=user.shop.id, name=body.name, parent_id=body.parent_id)
    session.add(cat)
    await session.commit()
    return CategoryOut.model_validate(cat)


@router.delete("/categories/{category_id}", status_code=204)
async def delete_category(
    category_id: int, user: CurrentUser = Depends(current_user), session: AsyncSession = Depends(get_session)
):
    cat = await session.scalar(select(Category).where(Category.shop_id == user.shop.id, Category.id == category_id))
    if cat is None:
        raise HTTPException(404)
    await session.delete(cat)
    await session.commit()


@router.get("/products", response_model=list[ProductOut])
async def list_products(
    q: str | None = None,
    limit: int = 50,
    offset: int = 0,
    user: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    stmt = (
        select(Product)
        .where(Product.shop_id == user.shop.id)
        .options(selectinload(Product.variants), selectinload(Product.images))
        .order_by(Product.id.desc())
        .limit(min(limit, 200))
        .offset(offset)
    )
    if q:
        stmt = stmt.where(Product.search_text.ilike(f"%{normalize(q)}%"))
    return [ProductOut.model_validate(p) for p in await session.scalars(stmt)]


async def _save(session: AsyncSession, user: CurrentUser, body: ProductIn, product: Product | None) -> Product:
    return await save_product(
        session,
        user.shop.id,
        product=product,
        name=body.name,
        price=body.price,
        description=body.description,
        category_id=body.category_id,
        category_name=body.category_name,
        is_active=body.is_active,
        variants=[v.model_dump(exclude={"id"}) for v in body.variants],
        images=[str(u) for u in body.images] if body.images is not None else None,
    )


@router.post("/products", response_model=ProductOut, status_code=201)
async def create_product(
    body: ProductIn, user: CurrentUser = Depends(current_user), session: AsyncSession = Depends(get_session)
):
    await _check_product_limit(session, user)
    product = await _save(session, user, body, None)
    await session.commit()
    await _enqueue_enrich([product.id])
    return ProductOut.model_validate(await load_product(session, user.shop.id, product.id))


@router.get("/products/{product_id}", response_model=ProductOut)
async def get_product(
    product_id: int, user: CurrentUser = Depends(current_user), session: AsyncSession = Depends(get_session)
):
    product = await load_product(session, user.shop.id, product_id)
    if product is None:
        raise HTTPException(404)
    return ProductOut.model_validate(product)


@router.put("/products/{product_id}", response_model=ProductOut)
async def update_product(
    product_id: int,
    body: ProductIn,
    user: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    product = await load_product(session, user.shop.id, product_id)
    if product is None:
        raise HTTPException(404)
    await _save(session, user, body, product)
    await session.commit()
    await _enqueue_enrich([product_id])
    session.expire_all()
    return ProductOut.model_validate(await load_product(session, user.shop.id, product_id))


@router.delete("/products/{product_id}", status_code=204)
async def delete_product(
    product_id: int, user: CurrentUser = Depends(current_user), session: AsyncSession = Depends(get_session)
):
    product = await load_product(session, user.shop.id, product_id)
    if product is None:
        raise HTTPException(404)
    await session.delete(product)  # buyurtmalarda snapshot saqlanadi
    await session.commit()


@router.post("/products/import", response_model=ImportOut)
async def import_products(
    file: UploadFile = File(...),
    user: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    content = await file.read(MAX_IMPORT_BYTES + 1)
    if len(content) > MAX_IMPORT_BYTES:
        raise HTTPException(413, "Fayl 5 MB dan katta")
    result = await import_catalog(session, user.shop.id, content, file.filename or "catalog.xlsx")
    try:
        await _check_product_limit(session, user, adding=0)
    except HTTPException:
        await session.rollback()
        raise
    await session.commit()
    await _enqueue_enrich(result.product_ids)
    return ImportOut(created=result.created, updated=result.updated, errors=result.errors)


@router.get("/products-import-template")
async def import_template(user: CurrentUser = Depends(current_user)) -> Response:
    return Response(
        template_xlsx(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="katalog_shablon.xlsx"'},
    )
