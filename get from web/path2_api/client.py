"""
HTTP API client for zujuan.xkw.com (组卷网)

Provides:
- Search questions by knowledge point + filters
- Parse question data from server-rendered HTML
- Get answer images from imzujuan.xkw.com/getAnswerAndParse
- Knowledge tree navigation

Architecture:
- Question LIST: server-rendered HTML (no separate API)
- Answer images: imzujuan.xkw.com/getAnswerAndParse (requires login)
- Formula images: staticzujuan.xkw.com/quesimg/Upload/formula/
- Anti-bot: alicfw cookie challenge on zujuan.xkw.com
"""

import json
import os
import re
import time
from urllib.parse import urljoin

import bs4
import requests

from challenge import ensure_challenge_cookies
from login import login_interactive, load_cookies, save_cookies, check_login_status

# -------- Constants --------
BASE_URL = 'https://zujuan.xkw.com'

# Grade prefixes
GRADE_PREFIX = {'high': 'gzsx', 'middle': 'czsx'}

# Question type codes (high school)
HIGH_TYPE_CODES = {
    't1': '2701',   # 单选题
    't2': '2704',   # 多选题
    't3': '2702',   # 填空题
    't4': '2703',   # 解答题
}

# Question type codes (middle school)
MIDDLE_TYPE_CODES = {
    't1': '1101',
    't2': '1104',
    't3': '1102',
    't4': '1103',
}

# Difficulty levels
DIFFICULTY_MAP = {
    'd1': '容易', 'd2': '较易', 'd3': '适中', 'd4': '较难', 'd5': '困难',
}

# Sort order
ORDER_MAP = {
    'latest': 'o2', 'hot': 'o1', 'comprehensive': 'o0',
}

# Answer image API
ANSWER_API = 'https://imzujuan.xkw.com/getAnswerAndParse'

# Default config paths
CONFIG_DIR = os.path.join(os.path.dirname(__file__), 'config')
COOKIE_FILE = os.path.join(CONFIG_DIR, 'cookies.pkl')
KNOWLEDGE_TREE_FILE = os.path.join(CONFIG_DIR, 'knowledge_tree_high.json')


class ZuJuanClient:
    """HTTP API client for zujuan.xkw.com question bank."""

    def __init__(self, grade='high', cookie_path=None, cookies=None):
        self.grade = grade
        self.cookie_path = cookie_path or COOKIE_FILE
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        })
        self.session.verify = False

        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

        self._logged_in = None
        self._username = None

        # Inject cookies if provided
        if cookies:
            self.set_cookies(cookies)

    def set_cookies(self, cookies: dict):
        """Inject cookies from browser (userId, user_token, zujuan-core, etc.)."""
        for name, value in cookies.items():
            self.session.cookies.set(name, value)

    # ==================== Login ====================

    def login(self, interactive=True):
        """
        Log in to zujuan. If interactive=True, shows QR code and waits for scan.
        Returns True if logged in.
        """
        # First try saved cookies
        saved = load_cookies(self.cookie_path)
        if saved:
            self.session.cookies = saved
            ok, user = check_login_status(self.session)
            if ok:
                self._logged_in = True
                self._username = user
                print(f"[Client] Using saved login: {user}")
                return True

        if interactive:
            self.session, ok = login_interactive(
                self.session, cookie_path=self.cookie_path
            )
            if ok:
                self._logged_in = True
                _, self._username = check_login_status(self.session)
            return ok
        else:
            print("[Client] Not logged in and interactive=False")
            return False

    def is_logged_in(self):
        """Check if client is logged in."""
        if self._logged_in is None:
            self._logged_in, self._username = check_login_status(self.session)
        return self._logged_in

    @property
    def username(self):
        if self._username is None:
            self.is_logged_in()
        return self._username

    # ==================== Anti-bot ====================

    def _ensure_challenge(self):
        """Ensure we have valid anti-bot challenge cookies."""
        return ensure_challenge_cookies(self.session)

    # ==================== URL Building ====================

    def _get_type_code(self, qtype, multi_count=None, fill_count=None):
        """Get question type code for URL."""
        codes = HIGH_TYPE_CODES if self.grade == 'high' else MIDDLE_TYPE_CODES
        base = codes.get(qtype, '')
        if not base:
            return ''

        if qtype == 't2' and multi_count is not None:
            suffix = '03' if multi_count >= 4 else f'0{multi_count}'
            return f'{base}{suffix}'
        elif qtype == 't3' and fill_count is not None:
            suffix = '03' if fill_count >= 3 else f'0{fill_count}'
            return f'{base}{suffix}'
        return base

    def build_url(self, knowledge_id, qtype=None, difficulty=None, year=None,
                  order='latest', page=1, multi_count=None, fill_count=None):
        """
        Build a zujuan search URL.

        Args:
            knowledge_id: Knowledge point ID (e.g., 'zsd27942')
            qtype: 't1'=单选, 't2'=多选, 't3'=填空, 't4'=解答
            difficulty: 'd1'~'d5'
            year: e.g., 2025
            order: 'latest', 'hot', 'comprehensive'
            page: page number (1-based)
            multi_count: for t2, number of correct options (2,3,4+)
            fill_count: for t3, number of blanks (1,2,3+)
        """
        prefix = GRADE_PREFIX[self.grade]
        kid = knowledge_id.replace('zsd', '')

        parts = []
        if qtype:
            tc = self._get_type_code(qtype, multi_count, fill_count)
            if tc:
                parts.append(f'qt{tc}')
        if difficulty:
            parts.append(f'd{difficulty[1]}')
        if year:
            parts.append(f'y{year}')

        order_code = ORDER_MAP.get(order, 'o2')
        if page > 1:
            parts.append(f'{order_code}p{page}')
        else:
            parts.append(order_code)

        url = f'{BASE_URL}/{prefix}/zsd{kid}/'
        if parts:
            url += ''.join(parts) + '/'
        return url

    # ==================== Question Search ====================

    def search(self, knowledge_id, qtype=None, difficulty=None, year=None,
               order='latest', page=1, limit=None, multi_count=None,
               fill_count=None):
        """
        Search for questions by knowledge point and filters.

        Returns a dict with metadata and list of question dicts.
        """
        url = self.build_url(knowledge_id, qtype, difficulty, year, order,
                             page, multi_count, fill_count)

        # Get past anti-bot
        self._ensure_challenge()

        print(f"[Search] Fetching: {url}")
        resp = self.session.get(url, timeout=30)

        if resp.status_code != 200:
            return {'error': f'HTTP {resp.status_code}', 'results': []}

        questions = self._parse_question_list(resp.text)

        # Extract total count
        total_match = re.search(r'id="questioncount">(\d+)', resp.text)
        total = int(total_match.group(1)) if total_match else len(questions)

        # Apply limit
        if limit and limit < len(questions):
            questions = questions[:limit]

        return {
            'url': url,
            'knowledge_id': knowledge_id,
            'qtype': qtype,
            'difficulty': difficulty,
            'year': year,
            'order': order,
            'page': page,
            'total': total,
            'count': len(questions),
            'results': questions,
        }

    def _parse_question_list(self, html):
        """Parse questions from server-rendered HTML."""
        soup = bs4.BeautifulSoup(html, 'html.parser')
        results = []

        for item in soup.find_all('div', class_='tk-quest-item'):
            qid = item.get('questionid', '')
            if not qid:
                continue

            question = {'id': qid}

            # Source info
            source_a = item.select_one('span.addi-msg > a.addi-msg.ques-src')
            if source_a:
                question['source'] = source_a.get('title', '').replace('原始出处：', '')
                question['source_text'] = source_a.text.strip()

            # Additional info (type, difficulty, score rate)
            info_spans = item.select('div.left-msg > span.addi-info > span.info-cnt')
            for span in info_spans:
                text = span.text.strip()
                # Check if it's difficulty with score rate
                diff_match = re.match(r'(.+?)\(([0-9.]+)\)', text)
                if diff_match:
                    question['difficulty'] = diff_match.group(1)
                    question['score_rate'] = float(diff_match.group(2))
                elif '题' in text:
                    question['question_type'] = text

            # Knowledge keywords
            kw_links = item.select('div.knowledge-list > a.knowledge-item')
            question['knowledge_keywords'] = [a.get('title', '') for a in kw_links]

            # Tags (名校, etc.)
            tags = item.select('span.tag')
            question['tags'] = [t.text.strip() for t in tags]

            # Question content
            cnt_div = item.select_one('div.exam-item__cnt')
            if cnt_div:
                question['content_html'] = str(cnt_div)
                question['content_text'] = cnt_div.get_text(separator=' ', strip=True)

                # Extract formula image URLs
                formula_imgs = cnt_div.find_all('img')
                question['formula_images'] = [
                    img.get('src', '') for img in formula_imgs
                ]

            # Detail page URL
            question['detail_url'] = f'{BASE_URL}/11q{qid}.html'

            # Control buttons
            add_btn = item.select_one('a.add-exam-btn')
            if add_btn:
                question['categories'] = add_btn.get('categories', '')
                question['category_name'] = add_btn.get('categoryname', '')
                question['qyid'] = add_btn.get('qyid', '')
                question['qyname'] = add_btn.get('qyname', '')

            results.append(question)

        return results

    # ==================== Answer Images ====================

    def get_answer(self, question_id, bank_id='11'):
        """
        Download the answer/analysis image for a question.

        Flow:
        1. Fetch question detail page to get __RequestVerificationToken (CSRF)
        2. POST /zujuan-api/check_ques_parse to get a one-time key
        3. GET the answer JPEG from imzujuan.xkw.com/getAnswerAndParse

        Requires login cookies (userId, user_token, zujuan-core).
        Critical headers: Referer (detail page) + Origin (zujuan.xkw.com).

        Returns (image_bytes, content_type) or (None, None).
        """
        detail_url = f'{BASE_URL}/11q{question_id}.html'

        # Step 1: Get CSRF token from detail page
        try:
            resp = self.session.get(detail_url, timeout=15)
            match = re.search(
                r'name="__RequestVerificationToken"[^>]*value="([^"]+)"',
                resp.text
            )
            csrf_token = match.group(1) if match else ''
            if not csrf_token:
                print(f"[Answer] Failed to get CSRF token for question {question_id}")
                return None, None
        except Exception as e:
            print(f"[Answer] Error fetching detail page: {e}")
            return None, None

        # Step 2: Get answer key via checkQuesParse
        try:
            resp2 = self.session.post(
                f'{BASE_URL}/zujuan-api/check_ques_parse',
                data={'quesId': question_id, 'bankId': bank_id},
                headers={
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'RequestVerification': csrf_token,
                    'Referer': detail_url,
                    'Origin': BASE_URL,
                },
                timeout=15,
            )
            result = resp2.json()
            key = result.get('key', '')
            if not key:
                print(f"[Answer] No key returned for question {question_id} "
                      f"(daily limit reached or not logged in)")
                return None, None
        except Exception as e:
            print(f"[Answer] Error getting parse key: {e}")
            return None, None

        # Step 3: Download answer image
        user_token = self.session.cookies.get('user_token', '')
        if not user_token:
            print("[Answer] user_token cookie not found")
            return None, None

        img_url = (
            f'{ANSWER_API}/{question_id}/{bank_id}/{key}'
            f'?enVqdWFu={user_token}&width=766'
        )

        try:
            resp3 = self.session.get(img_url, headers={
                'Referer': detail_url,
                'Origin': BASE_URL,
            }, timeout=30)

            if resp3.status_code == 200 and len(resp3.content) > 10000:
                return resp3.content, resp3.headers.get('content-type', 'image/jpeg')
            else:
                # May be an error image (403x19 PNG)
                print(f"[Answer] Image too small ({len(resp3.content)} bytes), "
                      f"likely permission error")
                return None, None
        except Exception as e:
            print(f"[Answer] Error downloading image: {e}")
            return None, None

    # ==================== Knowledge Tree ====================

    def load_knowledge_tree(self, tree_file=None):
        """Load the knowledge tree JSON."""
        tree_file = tree_file or KNOWLEDGE_TREE_FILE
        if os.path.exists(tree_file):
            with open(tree_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return None

    def search_knowledge(self, keyword, tree=None):
        """Search knowledge tree for matching nodes."""
        if tree is None:
            tree = self.load_knowledge_tree()

        if not tree:
            return []

        results = []

        def _search(node, path=''):
            name = node.get('name', '')
            kid = node.get('id', '')
            current_path = f'{path} > {name}' if path else name

            if keyword.lower() in name.lower():
                results.append({
                    'id': kid,
                    'name': name,
                    'path': current_path,
                })

            for child in node.get('children', []):
                _search(child, current_path)

        for root_node in tree if isinstance(tree, list) else [tree]:
            _search(root_node)

        return results


# ==================== Convenience Functions ====================


def create_client(grade='high', login=True):
    """Create a pre-configured ZuJuanClient."""
    client = ZuJuanClient(grade=grade)
    if login:
        client.login(interactive=True)
    return client


def quick_search(knowledge_id, qtype='t1', difficulty=None, limit=5,
                 grade='high', login_required=False):
    """
    Quick search without login (for public question data).
    Answer images require login.
    """
    client = ZuJuanClient(grade=grade)
    if login_required:
        client.login(interactive=True)

    result = client.search(knowledge_id, qtype=qtype, difficulty=difficulty,
                           limit=limit)
    return result


if __name__ == '__main__':
    # Quick test
    client = ZuJuanClient(grade='high')
    # No login needed for question list
    result = client.search('zsd27942', qtype='t1', difficulty='d3', limit=3)
    print(json.dumps(result, ensure_ascii=False, indent=2))
