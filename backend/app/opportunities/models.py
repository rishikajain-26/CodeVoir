import json
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, Text

from .database import Base


class Opportunity(Base):
    __tablename__ = "opportunities"

    id = Column(String, primary_key=True)
    title = Column(String, nullable=False)
    type = Column(String, nullable=False)  # hackathon | job | internship | competition
    source = Column(String, nullable=False)  # unstop | devfolio
    url = Column(String, nullable=False)
    description = Column(Text)
    organization = Column(String)
    deadline = Column(String)
    prize_pool = Column(String)
    stipend = Column(String)
    skills_required = Column(Text, default="[]")   # JSON list
    min_cgpa = Column(Float, default=0.0)
    eligible_years = Column(Text, default="[1,2,3,4]")  # JSON list of ints
    tags = Column(Text, default="[]")              # JSON list
    location = Column(String, default="Online")
    is_remote = Column(Boolean, default=True)
    team_size = Column(String)
    cover_image = Column(String)
    crawled_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)
    is_platform_company = Column(Boolean, default=False)   # org is in Codevoir interview dataset

    # ── helpers ────────────────────────────────────────────────────────────────

    def skills_list(self) -> list[str]:
        try:
            return json.loads(self.skills_required or "[]")
        except Exception:
            return []

    def tags_list(self) -> list[str]:
        try:
            return json.loads(self.tags or "[]")
        except Exception:
            return []

    def years_list(self) -> list[int]:
        try:
            return json.loads(self.eligible_years or "[1,2,3,4]")
        except Exception:
            return [1, 2, 3, 4]

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "type": self.type,
            "source": self.source,
            "url": self.url,
            "description": (self.description or "")[:500],
            "organization": self.organization,
            "deadline": self.deadline,
            "prize_pool": self.prize_pool,
            "stipend": self.stipend,
            "skills_required": self.skills_list(),
            "min_cgpa": self.min_cgpa,
            "eligible_years": self.years_list(),
            "tags": self.tags_list(),
            "location": self.location,
            "is_remote": self.is_remote,
            "team_size": self.team_size,
            "cover_image": self.cover_image,
            "crawled_at": self.crawled_at.isoformat() if self.crawled_at else None,
            "is_platform_company": bool(self.is_platform_company),
        }


class CrawlLog(Base):
    __tablename__ = "crawl_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source = Column(String)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    items_crawled = Column(Integer, default=0)
    status = Column(String)   # running | success | partial | error
    error_message = Column(Text)
