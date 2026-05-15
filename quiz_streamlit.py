"""
세계 지식 마스터 퀴즈 — Streamlit 버전
=======================================
실행:
    pip install streamlit requests
    streamlit run quiz_streamlit.py

배포 (무료):
    https://share.streamlit.io 에 GitHub 업로드 후 연결
"""

from __future__ import annotations

import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import unquote

import streamlit as st

try:
    import requests as req_lib
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

# ==============================================================================
# 설정
# ==============================================================================
QUESTIONS_PER_COUNTRY = 5
QUIZ_TIMER_SECONDS    = 20

COUNTRY_META: dict[str, dict] = {
    "대한민국": {"flag": "🇰🇷", "keywords": ["korea", "korean", "seoul"]},
    "미국":     {"flag": "🇺🇸", "keywords": ["united states", "america", "american", "usa",
                                               "washington", "new york", "hollywood", "nasa"]},
    "영국":     {"flag": "🇬🇧", "keywords": ["united kingdom", "england", "british", "london",
                                               "uk", "scotland", "wales"]},
    "일본":     {"flag": "🇯🇵", "keywords": ["japan", "japanese", "tokyo"]},
    "독일":     {"flag": "🇩🇪", "keywords": ["germany", "german", "berlin"]},
}

# ==============================================================================
# 폴백 퀴즈 데이터
# ==============================================================================
FALLBACK_POOL: dict[str, list[dict]] = {
    "대한민국": [
        {"question": "대한민국의 수도는 어디입니까?",
         "choices": ["서울", "부산", "인천", "대구"], "answer": "서울",
         "fact": "서울은 대한민국의 수도이자 최대 도시입니다."},
        {"question": "한국의 국화는 무엇입니까?",
         "choices": ["무궁화", "장미", "진달래", "국화"], "answer": "무궁화",
         "fact": "무궁화는 대한민국의 국화입니다."},
        {"question": "한국의 전통 발효 음식은?",
         "choices": ["김치", "스시", "라멘", "딤섬"], "answer": "김치",
         "fact": "김치는 한국의 대표적인 발효 음식입니다."},
        {"question": "한국의 전통 의상은?",
         "choices": ["한복", "기모노", "치파오", "사리"], "answer": "한복",
         "fact": "한복은 한국의 전통 의상입니다."},
        {"question": "서울의 대표적인 궁궐은?",
         "choices": ["경복궁", "황궁", "자금성", "버킹엄궁"], "answer": "경복궁",
         "fact": "경복궁은 조선 왕조의 정궁입니다."},
        {"question": "한글을 창제한 왕은?",
         "choices": ["세종대왕", "태조", "광개토대왕", "정조"], "answer": "세종대왕",
         "fact": "세종대왕은 1443년 훈민정음(한글)을 창제했습니다."},
        {"question": "한국의 국기 이름은?",
         "choices": ["태극기", "일장기", "성조기", "유니언잭"], "answer": "태극기",
         "fact": "태극기는 대한민국의 국기로, 태극 문양과 사괘로 구성됩니다."},
        {"question": "제주도에 있는 한국 최고봉은?",
         "choices": ["한라산", "설악산", "지리산", "백두산"], "answer": "한라산",
         "fact": "한라산(1,950m)은 제주도에 위치한 한국의 최고봉입니다."},
        {"question": "한국의 전통 씨름 경기는?",
         "choices": ["씨름", "유도", "스모", "레슬링"], "answer": "씨름",
         "fact": "씨름은 유네스코 인류무형문화유산으로 등재된 한국 전통 스포츠입니다."},
        {"question": "불국사가 위치한 도시는?",
         "choices": ["경주", "부산", "전주", "수원"], "answer": "경주",
         "fact": "불국사는 경주에 위치한 유네스코 세계문화유산입니다."},
    ],
    "미국": [
        {"question": "미국의 수도는 어디입니까?",
         "choices": ["워싱턴 D.C.", "뉴욕", "로스앤젤레스", "시카고"],
         "answer": "워싱턴 D.C.", "fact": "워싱턴 D.C.는 미국의 수도입니다."},
        {"question": "미국의 초대 대통령은?",
         "choices": ["조지 워싱턴", "에이브러햄 링컨", "토머스 제퍼슨", "존 애덤스"],
         "answer": "조지 워싱턴", "fact": "조지 워싱턴은 미국의 초대 대통령입니다."},
        {"question": "미국의 독립 기념일은?",
         "choices": ["7월 4일", "7월 14일", "6월 4일", "8월 4일"],
         "answer": "7월 4일", "fact": "미국은 1776년 7월 4일 독립을 선언했습니다."},
        {"question": "자유의 여신상이 위치한 곳은?",
         "choices": ["뉴욕", "워싱턴 D.C.", "보스턴", "필라델피아"],
         "answer": "뉴욕", "fact": "자유의 여신상은 뉴욕항의 리버티섬에 위치합니다."},
        {"question": "그랜드 캐니언이 위치한 주는?",
         "choices": ["애리조나", "텍사스", "캘리포니아", "콜로라도"],
         "answer": "애리조나", "fact": "그랜드 캐니언은 애리조나 주에 위치합니다."},
        {"question": "미국의 50번째 주는?",
         "choices": ["하와이", "알래스카", "아리조나", "뉴멕시코"],
         "answer": "하와이", "fact": "하와이는 1959년 미국의 50번째 주로 편입되었습니다."},
        {"question": "미국의 국조(나라 새)는?",
         "choices": ["흰머리수리", "독수리", "콘도르", "매"],
         "answer": "흰머리수리", "fact": "흰머리수리(대머리독수리)는 미국의 국조입니다."},
        {"question": "미국 최초의 국립공원은?",
         "choices": ["옐로스톤", "그랜드 캐니언", "요세미티", "에버글레이즈"],
         "answer": "옐로스톤", "fact": "옐로스톤은 1872년 세계 최초의 국립공원으로 지정되었습니다."},
        {"question": "미국의 실리콘밸리는 어느 주에 있습니까?",
         "choices": ["캘리포니아", "텍사스", "플로리다", "뉴욕"],
         "answer": "캘리포니아", "fact": "실리콘밸리는 캘리포니아 주 샌프란시스코 만 지역에 위치합니다."},
        {"question": "나사(NASA)의 본부가 있는 곳은?",
         "choices": ["워싱턴 D.C.", "휴스턴", "플로리다", "캘리포니아"],
         "answer": "워싱턴 D.C.", "fact": "NASA 본부는 워싱턴 D.C.에 있으며, 존슨 우주센터는 텍사스 휴스턴에 있습니다."},
    ],
    "영국": [
        {"question": "영국의 수도는 어디입니까?",
         "choices": ["런던", "맨체스터", "버밍엄", "에든버러"],
         "answer": "런던", "fact": "런던은 영국의 수도이자 최대 도시입니다."},
        {"question": "영국 왕실의 공식 거주지는?",
         "choices": ["버킹엄 궁전", "윈저 성", "켄싱턴 궁전", "세인트제임스 궁전"],
         "answer": "버킹엄 궁전", "fact": "버킹엄 궁전은 영국 왕실의 공식 런던 거주지입니다."},
        {"question": "영국의 유명한 시계탑은?",
         "choices": ["빅벤", "에펠탑", "자유의 여신상", "시계탑"],
         "answer": "빅벤", "fact": "빅벤은 런던 의회 의사당의 시계탑입니다."},
        {"question": "셰익스피어의 출생지는?",
         "choices": ["스트랫퍼드어폰에이번", "런던", "옥스퍼드", "에든버러"],
         "answer": "스트랫퍼드어폰에이번",
         "fact": "윌리엄 셰익스피어는 1564년 스트랫퍼드어폰에이번에서 태어났습니다."},
        {"question": "비틀즈의 출신 도시는?",
         "choices": ["리버풀", "런던", "맨체스터", "버밍엄"],
         "answer": "리버풀", "fact": "비틀즈는 1960년대 영국 리버풀에서 결성된 전설적인 록 밴드입니다."},
        {"question": "해리포터의 원작자는?",
         "choices": ["J.K. 롤링", "J.R.R. 톨킨", "C.S. 루이스", "로알드 달"],
         "answer": "J.K. 롤링", "fact": "J.K. 롤링은 영국 작가로, 해리포터 시리즈의 원작자입니다."},
        {"question": "영국의 화폐 단위는?",
         "choices": ["파운드", "유로", "달러", "프랑"],
         "answer": "파운드", "fact": "영국 파운드(£)는 세계에서 가장 오래된 통화 중 하나입니다."},
        {"question": "영국의 유명한 선사시대 유적지는?",
         "choices": ["스톤헨지", "콜로세움", "아크로폴리스", "앙코르와트"],
         "answer": "스톤헨지", "fact": "스톤헨지는 잉글랜드 윌트셔에 위치한 유네스코 세계문화유산입니다."},
        {"question": "템스강이 흐르는 도시는?",
         "choices": ["런던", "맨체스터", "리버풀", "브리스틀"],
         "answer": "런던", "fact": "템스강은 영국 잉글랜드 남부를 흐르며 런던을 관통합니다."},
        {"question": "영국 최고봉은?",
         "choices": ["벤네비스산", "스노든산", "스캐펠파이크", "펠트베르크"],
         "answer": "벤네비스산", "fact": "벤네비스산(1,345m)은 스코틀랜드에 위치한 영국의 최고봉입니다."},
    ],
    "일본": [
        {"question": "일본의 수도는 어디입니까?",
         "choices": ["도쿄", "오사카", "교토", "나고야"],
         "answer": "도쿄", "fact": "도쿄는 일본의 수도이자 세계 최대 도시 중 하나입니다."},
        {"question": "일본의 최고봉은?",
         "choices": ["후지산", "아소산", "사쿠라지마", "온타케산"],
         "answer": "후지산", "fact": "후지산은 일본의 최고봉(3776m)으로 세계문화유산입니다."},
        {"question": "일본의 공식 통화는?",
         "choices": ["엔(円)", "위안", "달러", "원"],
         "answer": "엔(円)", "fact": "엔(円, ¥)은 일본의 공식 통화입니다."},
        {"question": "일본의 대표적인 전통 공연 예술은?",
         "choices": ["가부키", "노", "분라쿠", "교겐"],
         "answer": "가부키", "fact": "가부키는 일본의 대표적인 전통 공연 예술입니다."},
        {"question": "일본의 국화는?",
         "choices": ["국화", "벚꽃", "매화", "연꽃"],
         "answer": "국화", "fact": "국화는 일본 황실의 문장으로 사용되는 일본의 국화입니다."},
        {"question": "일본의 전통 시 형식은?",
         "choices": ["하이쿠", "소네트", "시조", "한시"],
         "answer": "하이쿠", "fact": "하이쿠는 5-7-5 음절로 구성된 일본의 전통 단시 형식입니다."},
        {"question": "일본에서 가장 큰 섬은?",
         "choices": ["혼슈", "홋카이도", "규슈", "시코쿠"],
         "answer": "혼슈", "fact": "혼슈는 일본 최대의 섬으로 도쿄, 오사카 등 주요 도시가 위치합니다."},
        {"question": "일본의 전통 다도 의식을 무엇이라 합니까?",
         "choices": ["차노유", "다례", "다도", "다회"],
         "answer": "차노유", "fact": "차노유(茶の湯)는 일본의 전통 차 의식으로 선(禅) 정신을 담고 있습니다."},
        {"question": "일본의 국기 명칭은?",
         "choices": ["히노마루", "태극기", "성조기", "유니언잭"],
         "answer": "히노마루", "fact": "히노마루(日の丸)는 흰 바탕에 붉은 원이 그려진 일본의 국기입니다."},
        {"question": "일본의 대표적인 만화·애니메이션 거리가 있는 도쿄의 지역은?",
         "choices": ["아키하바라", "시부야", "신주쿠", "아사쿠사"],
         "answer": "아키하바라", "fact": "아키하바라는 전자제품과 애니메이션·만화 문화의 중심지입니다."},
    ],
    "독일": [
        {"question": "독일의 수도는 어디입니까?",
         "choices": ["베를린", "뮌헨", "함부르크", "프랑크푸르트"],
         "answer": "베를린", "fact": "베를린은 독일의 수도이자 최대 도시입니다."},
        {"question": "베를린 장벽이 붕괴된 연도는?",
         "choices": ["1989년", "1991년", "1985년", "1993년"],
         "answer": "1989년", "fact": "베를린 장벽은 1989년 11월 9일 붕괴되었습니다."},
        {"question": "독일의 대표적인 맥주 축제는?",
         "choices": ["옥토버페스트", "카니발", "크리스마스 마켓", "라인강 축제"],
         "answer": "옥토버페스트", "fact": "옥토버페스트는 매년 뮌헨에서 열리는 세계 최대 맥주 축제입니다."},
        {"question": "베토벤의 출생지는?",
         "choices": ["본", "베를린", "뮌헨", "함부르크"],
         "answer": "본", "fact": "루트비히 판 베토벤은 1770년 독일 본에서 태어났습니다."},
        {"question": "독일의 화폐는 무엇입니까?",
         "choices": ["유로", "마르크", "파운드", "프랑"],
         "answer": "유로", "fact": "독일은 2002년부터 유로화를 공식 통화로 사용합니다."},
        {"question": "독일의 유명한 동화 수집가는?",
         "choices": ["그림 형제", "안데르센", "페로", "오스카 와일드"],
         "answer": "그림 형제", "fact": "그림 형제(야코프·빌헬름)는 신데렐라, 백설공주 등 유명 동화를 수집·출판했습니다."},
        {"question": "독일 통일은 몇 년에 이루어졌습니까?",
         "choices": ["1990년", "1989년", "1991년", "1992년"],
         "answer": "1990년", "fact": "동독과 서독은 1990년 10월 3일 공식 통일되었습니다."},
        {"question": "독일의 인쇄술을 발명한 사람은?",
         "choices": ["구텐베르크", "에디슨", "다빈치", "파라데이"],
         "answer": "구텐베르크", "fact": "요하네스 구텐베르크는 15세기 활판 인쇄술을 발명해 지식 혁명을 이끌었습니다."},
        {"question": "독일 최고봉은?",
         "choices": ["추크슈피체", "바츠만", "베르히테스가덴", "펠트베르크"],
         "answer": "추크슈피체", "fact": "추크슈피체(2,962m)는 바이에른 알프스에 위치한 독일의 최고봉입니다."},
        {"question": "독일의 최대 항구 도시는?",
         "choices": ["함부르크", "브레멘", "킬", "뤼베크"],
         "answer": "함부르크", "fact": "함부르크는 독일 최대의 항구 도시이자 두 번째로 큰 도시입니다."},
    ],
}

# ==============================================================================
# 번역 유틸리티
# ==============================================================================
_translation_cache: dict[str, str] = {}
_GT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://translate.google.com/",
}

def _translate_google(text: str) -> str | None:
    try:
        resp = req_lib.get(
            "https://translate.googleapis.com/translate_a/single",
            params={"client": "gtx", "sl": "en", "tl": "ko", "dt": "t", "q": text},
            headers=_GT_HEADERS, timeout=8,
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        parts = data[0] if data and isinstance(data, list) else []
        result = "".join(
            seg[0] for seg in parts
            if isinstance(seg, list) and seg and isinstance(seg[0], str)
        ).strip()
        return result if result else None
    except Exception:
        return None

def _translate_mymemory(text: str) -> str | None:
    try:
        resp = req_lib.get(
            "https://api.mymemory.translated.net/get",
            params={"q": text, "langpair": "en|ko"}, timeout=8,
        )
        translated = resp.json().get("responseData", {}).get("translatedText", "")
        if translated and not translated.lower().startswith(("invalid", "mymemory")):
            return translated.strip()
    except Exception:
        pass
    return None

def translate_to_korean(text: str) -> str:
    if not text or not REQUESTS_AVAILABLE:
        return text
    if text in _translation_cache:
        return _translation_cache[text]
    result = _translate_google(text) or _translate_mymemory(text) or text
    _translation_cache[text] = result
    return result

def _is_korean(text: str) -> bool:
    return any("\uAC00" <= ch <= "\uD7A3" for ch in text)

def translate_question(q: dict) -> dict:
    texts = [q["question"], q["answer"]] + q["choices"] + [q.get("fact", "")]
    uncached = [t for t in texts if t and t not in _translation_cache]
    def _one(t):
        r = _translate_google(t) or _translate_mymemory(t) or t
        _translation_cache[t] = r
        return t, r
    with ThreadPoolExecutor(max_workers=8) as ex:
        for orig, tr in ex.map(_one, uncached):
            _translation_cache[orig] = tr
    get = lambda t: _translation_cache.get(t, t)
    return {
        "question": get(q["question"]),
        "choices":  [get(c) for c in q["choices"]],
        "answer":   get(q["answer"]),
        "fact":     get(q.get("fact", "")),
    }

# ==============================================================================
# Open Trivia DB 가져오기
# ==============================================================================
def _best_country_for(text: str) -> str | None:
    qt = text.lower()
    best, best_len = None, 0
    for country, meta in COUNTRY_META.items():
        for kw in meta["keywords"]:
            if kw in qt and len(kw) > best_len:
                best, best_len = country, len(kw)
    return best

def fetch_quiz_from_api() -> dict[str, list[dict]]:
    buckets: dict[str, list[dict]] = {c: [] for c in COUNTRY_META}
    if not REQUESTS_AVAILABLE:
        return buckets
    seen: set[str] = set()
    raw: list[dict] = []
    try:
        resp = req_lib.get(
            "https://opentdb.com/api.php",
            params={"amount": 50, "category": 22, "type": "multiple", "encode": "url3986"},
            timeout=10,
        )
        if resp.status_code == 200 and resp.json().get("response_code") == 0:
            for item in resp.json().get("results", []):
                dq = unquote(item["question"])
                if dq.strip().lower() in seen:
                    continue
                seen.add(dq.strip().lower())
                country = _best_country_for(dq)
                if country is None or len(buckets[country]) >= QUESTIONS_PER_COUNTRY:
                    continue
                correct = unquote(item["correct_answer"])
                choices = [unquote(w) for w in item["incorrect_answers"]] + [correct]
                random.shuffle(choices)
                raw.append({
                    "country": country,
                    "question": dq, "choices": choices,
                    "answer": correct, "fact": "출처: Open Trivia DB",
                })
    except Exception:
        pass

    if raw:
        def _tr(r):
            t = translate_question(r)
            t["_c"] = r["country"]
            return t
        with ThreadPoolExecutor(max_workers=10) as ex:
            for t in ex.map(_tr, raw):
                c = t.pop("_c")
                if len(buckets[c]) < QUESTIONS_PER_COUNTRY:
                    buckets[c].append(t)
    return buckets

def build_quiz() -> dict[str, list[dict]]:
    """API + 폴백으로 각 나라당 5문제 구성"""
    api_data = fetch_quiz_from_api()
    quiz: dict[str, list[dict]] = {}
    for country in COUNTRY_META:
        pool = list(api_data.get(country, []))
        needed = QUESTIONS_PER_COUNTRY - len(pool)
        if needed > 0:
            fb = random.sample(FALLBACK_POOL[country],
                               min(needed, len(FALLBACK_POOL[country])))
            pool += fb
        random.shuffle(pool)
        quiz[country] = pool[:QUESTIONS_PER_COUNTRY]
    return quiz

# ==============================================================================
# Streamlit 세션 초기화
# ==============================================================================
def init_state():
    defaults = {
        "page": "login",          # login | country_select | quiz | result
        "user_id": "",
        "quiz_data": None,
        "country_list": list(COUNTRY_META.keys()),
        "completed": [],          # 완료한 나라들
        "total_score": 0,
        "current_country": None,
        "quiz_pool": [],
        "step": 0,                # 현재 문제 번호
        "answered": False,        # 현재 문제 답변 여부
        "selected": None,         # 선택한 답
        "score_this_round": 0,
        "ranking": [],
        "timer_start": None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

# ==============================================================================
# 페이지: 로그인
# ==============================================================================
def page_login():
    st.markdown("""
    <div style='text-align:center; padding: 40px 0 20px'>
        <div style='font-size:3rem'>🌍</div>
        <h1 style='font-size:2rem; margin:8px 0'>세계 지식 마스터 퀴즈</h1>
        <p style='color:gray'>5개 나라 × 5문제 — 얼마나 알고 있나요?</p>
    </div>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        name = st.text_input("닉네임을 입력하세요", placeholder="예: 퀴즈왕", max_chars=20)
        if st.button("🚀 시작하기", use_container_width=True, type="primary"):
            if not name.strip():
                st.warning("닉네임을 입력해 주세요!")
            else:
                st.session_state.user_id = name.strip()
                with st.spinner("퀴즈 문제를 불러오는 중..."):
                    st.session_state.quiz_data = build_quiz()
                st.session_state.page = "country_select"
                st.rerun()

# ==============================================================================
# 페이지: 나라 선택
# ==============================================================================
def page_country_select():
    completed = st.session_state.completed
    total     = st.session_state.total_score
    max_score = len(completed) * QUESTIONS_PER_COUNTRY

    st.markdown(f"### 👋 {st.session_state.user_id}님, 나라를 선택하세요!")
    st.progress(len(completed) / len(COUNTRY_META),
                text=f"진행: {len(completed)}/{len(COUNTRY_META)} 나라 완료 | 점수: {total}/{max_score}")
    st.markdown("---")

    cols = st.columns(len(COUNTRY_META))
    for i, (country, meta) in enumerate(COUNTRY_META.items()):
        with cols[i]:
            done = country in completed
            label = f"{meta['flag']}\n\n**{country}**\n\n{'✅ 완료' if done else '도전!'}"
            if st.button(label, key=f"country_{country}",
                         use_container_width=True,
                         disabled=done):
                pool = list(st.session_state.quiz_data.get(country, []))
                if not pool:
                    pool = random.sample(FALLBACK_POOL[country], QUESTIONS_PER_COUNTRY)
                random.shuffle(pool)
                st.session_state.current_country  = country
                st.session_state.quiz_pool        = pool
                st.session_state.step             = 0
                st.session_state.answered         = False
                st.session_state.selected         = None
                st.session_state.score_this_round = 0
                st.session_state.page             = "quiz"
                st.rerun()

    if len(completed) == len(COUNTRY_META):
        st.markdown("---")
        if st.button("🏆 최종 결과 보기", type="primary", use_container_width=True):
            st.session_state.page = "result"
            st.rerun()

# ==============================================================================
# 페이지: 퀴즈
# ==============================================================================
def page_quiz():
    country = st.session_state.current_country
    pool    = st.session_state.quiz_pool
    step    = st.session_state.step
    meta    = COUNTRY_META[country]

    # 나라 다 풀었으면 완료 처리
    if step >= len(pool):
        if country not in st.session_state.completed:
            st.session_state.completed.append(country)
            st.session_state.total_score += st.session_state.score_this_round
        st.session_state.page = "country_select"
        st.rerun()
        return

    q = pool[step]

    # 헤더
    st.markdown(f"## {meta['flag']} {country} 퀴즈")
    progress_val = step / QUESTIONS_PER_COUNTRY
    st.progress(progress_val, text=f"문제 {step + 1} / {QUESTIONS_PER_COUNTRY}")
    st.markdown(f"**이번 라운드 점수: {st.session_state.score_this_round} / {step}**")
    st.markdown("---")

    # 문제
    st.markdown(f"### ❓ {q['question']}")
    st.markdown("")

    answered = st.session_state.answered
    selected = st.session_state.selected
    correct  = q["answer"]

    # 보기 버튼
    choices = q["choices"]
    for choice in choices:
        if answered:
            if choice == correct:
                st.success(f"✅ {choice}")
            elif choice == selected:
                st.error(f"❌ {choice}")
            else:
                st.markdown(f"- {choice}")
        else:
            if st.button(choice, key=f"choice_{step}_{choice}", use_container_width=True):
                st.session_state.selected = choice
                st.session_state.answered = True
                if choice == correct:
                    st.session_state.score_this_round += 1
                st.rerun()

    # 정답 확인 후
    if answered:
        if selected == correct:
            st.markdown("### 🎉 정답입니다!")
        else:
            st.markdown(f"### 😢 틀렸습니다! 정답: **{correct}**")

        if q.get("fact"):
            st.info(f"💡 {q['fact']}")

        st.markdown("")
        if st.button("➡️ 다음 문제", type="primary", use_container_width=True):
            st.session_state.step    += 1
            st.session_state.answered = False
            st.session_state.selected = None
            st.rerun()

    # 퀴즈 나가기
    st.markdown("---")
    if st.button("🏠 나라 선택으로 돌아가기"):
        st.session_state.page = "country_select"
        st.rerun()

# ==============================================================================
# 페이지: 최종 결과
# ==============================================================================
def page_result():
    total    = st.session_state.total_score
    max_q    = len(COUNTRY_META) * QUESTIONS_PER_COUNTRY
    user     = st.session_state.user_id
    pct      = int(total / max_q * 100)

    if pct >= 90:
        grade, emoji = "🏆 세계 지식 마스터!", "🌟"
    elif pct >= 70:
        grade, emoji = "🥈 글로벌 탐험가", "🗺️"
    elif pct >= 50:
        grade, emoji = "🥉 세계 여행자", "✈️"
    else:
        grade, emoji = "📚 지식 탐구자", "🔍"

    st.markdown(f"""
    <div style='text-align:center; padding:30px 0'>
        <div style='font-size:4rem'>{emoji}</div>
        <h1>🎉 퀴즈 완료!</h1>
        <h2>{user}님의 결과</h2>
        <div style='font-size:3rem; font-weight:bold; color:#3b82f6'>{total}</div>
        <div style='font-size:1.2rem; color:gray'>/ {max_q} 점 ({pct}%)</div>
        <h3 style='margin-top:16px'>{grade}</h3>
    </div>
    """, unsafe_allow_html=True)

    # 랭킹 업데이트
    ranking = st.session_state.ranking
    ranking = [r for r in ranking if r["name"] != user]
    ranking.append({"name": user, "score": total})
    ranking.sort(key=lambda x: x["score"], reverse=True)
    st.session_state.ranking = ranking

    st.markdown("### 🏅 랭킹")
    medals = ["🥇", "🥈", "🥉"]
    for i, r in enumerate(ranking[:10]):
        medal = medals[i] if i < 3 else f"{i+1}."
        highlight = "**" if r["name"] == user else ""
        st.markdown(f"{medal} {highlight}{r['name']}{highlight} — {r['score']}점")

    st.markdown("---")
    if st.button("🔄 새로운 도전 시작", type="primary", use_container_width=True):
        for key in list(st.session_state.keys()):
            if key != "ranking":
                del st.session_state[key]
        st.rerun()

# ==============================================================================
# 메인
# ==============================================================================
st.set_page_config(
    page_title="🌍 세계 지식 마스터 퀴즈",
    page_icon="🌍",
    layout="centered",
)

init_state()

page = st.session_state.page
if page == "login":
    page_login()
elif page == "country_select":
    page_country_select()
elif page == "quiz":
    page_quiz()
elif page == "result":
    page_result()
