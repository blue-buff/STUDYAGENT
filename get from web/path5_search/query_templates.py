"""
Search query template engine.
Generates optimized search queries from structured requirements.

Key insight: Searching for actual question text patterns (like "已知函数",
"设函数f(x)") returns much better results than topic descriptions alone.
"""

from models import SearchRequest
import config


# Question text patterns by subject — these match how questions actually start
SUBJECT_PATTERNS = {
    "数学": [
        '"已知函数f(x)"',
        '"设函数f(x)"',
        '"若函数f(x)"',
        '"函数f(x)"',
    ],
    "物理": [
        '"如图所示"',
        '"一物体"',
        '"一个质量"',
        '"在光滑"',
    ],
    "化学": [
        '"下列反应的离子方程式"',
        '"某温度下"',
        '"将一定量"',
        '"下列物质中"',
    ],
}


class QueryTemplates:
    """Generates search queries for Chinese high school questions."""

    TEMPLATES = {
        # General topic search
        "general": "{subject} {knowledge_point} {question_type} {difficulty} 题目 解析 答案",

        # Direct question search with topic
        "direct": "{knowledge_point} {question_type} {difficulty} {subject} 试题",

        # Exam-oriented
        "exam": "{knowledge_point} 高考{subject} {question_type} {difficulty}",

        # Question text pattern search (most effective)
        "pattern": "{pattern} {knowledge_point} {question_type} {difficulty} {subject}",
    }

    @classmethod
    def generate_queries(cls, request: SearchRequest, strategy: str = "all") -> list[str]:
        """
        Generate search queries from a SearchRequest.

        Args:
            request: The search requirements
            strategy: "all" (full set), or a specific template name

        Returns:
            List of search query strings
        """
        params = {
            "subject": f"高中{request.subject}" if "高中" not in request.subject else request.subject,
            "knowledge_point": request.knowledge_point,
            "question_type": request.question_type,
            "difficulty": request.difficulty,
        }

        if strategy == "all":
            queries = []

            # Strategy 1: Question-text-pattern searches (most effective for finding actual questions)
            patterns = SUBJECT_PATTERNS.get(request.subject, SUBJECT_PATTERNS["数学"])
            for pattern in patterns[:2]:  # Use top 2 patterns
                params["pattern"] = pattern
                queries.append(cls.TEMPLATES["pattern"].format(**params))

            # Strategy 2: General topic search
            queries.append(cls.TEMPLATES["general"].format(**params))

            # Strategy 3: Exam-oriented search
            queries.append(cls.TEMPLATES["exam"].format(**params))

            return queries

        elif strategy in cls.TEMPLATES:
            template = cls.TEMPLATES[strategy]
            if "{pattern}" in template:
                queries = []
                patterns = SUBJECT_PATTERNS.get(request.subject, SUBJECT_PATTERNS["数学"])
                for pattern in patterns[:2]:
                    params["pattern"] = pattern
                    queries.append(template.format(**params))
                return queries
            return [template.format(**params)]
        else:
            raise ValueError(f"Unknown strategy: {strategy}")

    @classmethod
    def generate_single_query(cls, request: SearchRequest) -> str:
        """Generate the single best search query for a request."""
        params = {
            "subject": f"高中{request.subject}" if "高中" not in request.subject else request.subject,
            "knowledge_point": request.knowledge_point,
            "question_type": request.question_type,
            "difficulty": request.difficulty,
        }
        return cls.TEMPLATES["general"].format(**params)


# ── Pre-defined test cases for validation ──────────────────────────────────

TEST_CASES = [
    SearchRequest(subject="数学", knowledge_point="导数单调性", question_type="选择题", difficulty="中等"),
    SearchRequest(subject="数学", knowledge_point="三角函数图像", question_type="填空题", difficulty="基础"),
    SearchRequest(subject="数学", knowledge_point="数列通项公式", question_type="解答题", difficulty="较难"),
    SearchRequest(subject="物理", knowledge_point="牛顿第二定律", question_type="选择题", difficulty="中等"),
    SearchRequest(subject="物理", knowledge_point="动能定理", question_type="计算题", difficulty="中等"),
    SearchRequest(subject="化学", knowledge_point="离子方程式", question_type="选择题", difficulty="基础"),
    SearchRequest(subject="化学", knowledge_point="化学平衡", question_type="填空题", difficulty="较难"),
    SearchRequest(subject="数学", knowledge_point="立体几何体积", question_type="解答题", difficulty="中等"),
    SearchRequest(subject="数学", knowledge_point="概率统计", question_type="选择题", difficulty="基础"),
    SearchRequest(subject="物理", knowledge_point="带电粒子在磁场中的运动", question_type="解答题", difficulty="压轴"),
    SearchRequest(subject="数学", knowledge_point="解析几何椭圆", question_type="解答题", difficulty="压轴"),
    SearchRequest(subject="化学", knowledge_point="有机推断", question_type="解答题", difficulty="中等"),
]
