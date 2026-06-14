from typing import List, Dict, Any, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, and_, distinct

from app.database import AsyncSessionLocal
from app.models import Company, User, GlafiraSettings, Candidate
from app.provision_company import provision_company, ProvisionError
from app.services.settings.glafira import get_glafira_settings
from app.services.settings.crypto import encrypt_text, decrypt_text
from app.services.glafira.models import ALLOWED_MODEL_VALUES


class CompanyInfo:
    """DTO for company information in dashboard"""

    def __init__(
        self,
        id: UUID,
        name: str,
        admin_email: str,
        created_at: str,
        has_openrouter_key: bool,
        users_count: int,
        candidates_count: int
    ):
        self.id = id
        self.name = name
        self.admin_email = admin_email
        self.created_at = created_at
        self.has_openrouter_key = has_openrouter_key
        self.users_count = users_count
        self.candidates_count = candidates_count


class CompanyService:
    """Service layer for company management"""

    async def list_companies(self) -> List[CompanyInfo]:
        """List all companies with basic statistics"""
        async with AsyncSessionLocal() as session:
            # Query companies with admin email and counts
            query = (
                select(
                    Company.id,
                    Company.name,
                    Company.created_at,
                    # distinct: иначе тройной outerjoin (User×Candidate×GlafiraSettings)
                    # даёт декартово произведение и счётчики перемножаются
                    func.count(distinct(User.id)).label("users_count"),
                    func.count(distinct(Candidate.id)).label("candidates_count"),
                    # Get first admin email
                    func.min(User.email).filter(User.role == "admin").label("admin_email"),
                    # Check if has openrouter key
                    func.bool_or(GlafiraSettings.openrouter_api_key.isnot(None)).label("has_openrouter_key")
                )
                .outerjoin(User, User.company_id == Company.id)
                .outerjoin(Candidate, and_(
                    Candidate.company_id == Company.id,
                    Candidate.deleted_at.is_(None)
                ))
                .outerjoin(GlafiraSettings, GlafiraSettings.company_id == Company.id)
                .group_by(Company.id, Company.name, Company.created_at)
                .order_by(Company.created_at.desc())
            )

            result = await session.execute(query)
            rows = result.fetchall()

            companies = []
            for row in rows:
                companies.append(CompanyInfo(
                    id=row.id,
                    name=row.name,
                    admin_email=row.admin_email or "No admin",
                    created_at=row.created_at.strftime("%Y-%m-%d %H:%M"),
                    has_openrouter_key=bool(row.has_openrouter_key),
                    users_count=row.users_count,
                    candidates_count=row.candidates_count
                ))

            return companies

    async def create_company(
        self,
        name: str,
        admin_email: str,
        admin_password: str,
        admin_full_name: str,
        openrouter_api_key: Optional[str] = None
    ) -> CompanyInfo:
        """Create new company with admin user and settings"""
        async with AsyncSessionLocal() as session:
            try:
                # Use existing provision_company function
                company, admin = await provision_company(
                    session,
                    name=name,
                    admin_email=admin_email,
                    admin_password=admin_password,
                    admin_full_name=admin_full_name
                )

                # Set OpenRouter API key if provided
                if openrouter_api_key and openrouter_api_key.strip():
                    gs = await get_glafira_settings(session, company.id)
                    gs.openrouter_api_key = encrypt_text(openrouter_api_key.strip())

                await session.commit()

                return CompanyInfo(
                    id=company.id,
                    name=company.name,
                    admin_email=admin_email,
                    created_at=company.created_at.strftime("%Y-%m-%d %H:%M"),
                    has_openrouter_key=bool(openrouter_api_key and openrouter_api_key.strip()),
                    users_count=1,
                    candidates_count=0
                )

            except Exception:
                await session.rollback()
                raise

    async def get_company(self, company_id: UUID) -> Optional[CompanyInfo]:
        """Get company by ID with statistics"""
        companies = await self.list_companies()
        for company in companies:
            if company.id == company_id:
                return company
        return None

    async def update_company(
        self,
        company_id: UUID,
        name: Optional[str] = None,
        openrouter_api_key: Optional[str] = None,
        llm_model: Optional[str] = None
    ) -> bool:
        """Update company information"""
        async with AsyncSessionLocal() as session:
            try:
                # Get company
                result = await session.execute(
                    select(Company).where(Company.id == company_id)
                )
                company = result.scalar_one_or_none()
                if not company:
                    return False

                # Update company name if provided
                if name is not None:
                    company.name = name

                # Update Glafira settings if needed
                if openrouter_api_key is not None or llm_model is not None:
                    gs = await get_glafira_settings(session, company_id)

                    if openrouter_api_key is not None and openrouter_api_key.strip():
                        gs.openrouter_api_key = encrypt_text(openrouter_api_key.strip())

                    if llm_model is not None:
                        # Validate model if whitelist exists
                        if ALLOWED_MODEL_VALUES and llm_model not in ALLOWED_MODEL_VALUES:
                            raise ValueError(f"Invalid LLM model: {llm_model}")
                        gs.llm_model = llm_model if llm_model else None

                await session.commit()
                return True

            except Exception:
                await session.rollback()
                raise

    async def get_company_settings(self, company_id: UUID) -> Dict[str, Any]:
        """Get company settings for editing form"""
        async with AsyncSessionLocal() as session:
            # Get company
            result = await session.execute(
                select(Company).where(Company.id == company_id)
            )
            company = result.scalar_one_or_none()
            if not company:
                return {}

            # Get Glafira settings
            gs = await get_glafira_settings(session, company_id)

            # Mask OpenRouter key for display
            openrouter_key_display = ""
            if gs.openrouter_api_key:
                try:
                    decrypted = decrypt_text(gs.openrouter_api_key)
                    if len(decrypted) >= 4:
                        openrouter_key_display = f"••••{decrypted[-4:]}"
                    else:
                        openrouter_key_display = "••••"
                except Exception:
                    openrouter_key_display = "••••"

            return {
                "id": company.id,
                "name": company.name,
                "openrouter_key_display": openrouter_key_display,
                "llm_model": gs.llm_model or "",
                "available_models": ALLOWED_MODEL_VALUES if ALLOWED_MODEL_VALUES else []
            }


company_service = CompanyService()