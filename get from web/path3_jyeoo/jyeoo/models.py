from dataclasses import dataclass, field, asdict
from typing import Optional
import json


@dataclass
class Subject:
    name: str
    name_cn: str
    junior_path: str
    senior_path: str = ""
    primary_path: str = ""


@dataclass
class KnowledgePoint:
    id: str
    name: str
    parent_id: Optional[str] = None
    level: int = 0
    children: list["KnowledgePoint"] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "parent_id": self.parent_id,
            "level": self.level,
            "children": [c.to_dict() for c in self.children],
        }


@dataclass
class Question:
    subject: str
    grade: str
    knowledge_points: list[str] = field(default_factory=list)
    question_type: str = ""
    difficulty: str = ""
    year: str = ""
    question_text: str = ""
    question_images: list[str] = field(default_factory=list)
    answer_text: str = ""
    answer_images: list[str] = field(default_factory=list)
    analysis: str = ""
    source: str = ""
    source_url: str = ""
    source_id: str = ""
    options: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["knowledge_points"] = self.knowledge_points
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


@dataclass
class SiteStructure:
    base_url: str
    subjects: list[dict] = field(default_factory=list)
    url_patterns: dict = field(default_factory=dict)
    filters: dict = field(default_factory=dict)
    login_required_for: list[str] = field(default_factory=list)
    anti_bot_observations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)
