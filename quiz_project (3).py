"""
세계 지식 마스터 퀴즈 - 웹 애플리케이션
========================================
• Open Trivia DB에서 영어 퀴즈를 가져와 Google Translate로 자동 한국어 번역
  (API 키 불필요 — Google의 비공개 Ajax 엔드포인트 사용, 다중 폴백 지원)
• 세션 동안 출제된 문제를 추적해 중복 방지
• Flask 기반 단일 파일 웹 앱 (템플릿 내장)

실행 방법:
    pip install flask requests
    python quiz_web_app.py
    브라우저에서 http://127.0.0.1:5000 접속
"""

from __future__ import annotations

import json
import random
import threading
import time
import uuid
import webbrowser
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Any
from urllib.parse import unquote

from flask import Flask, jsonify, request, session, Response

try:
    import requests as req_lib
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

# ==============================================================================
# 설정 상수
# ==============================================================================
QUESTIONS_PER_COUNTRY = 5   # 나라당 문제 수
API_BATCH_SIZE        = 50  # Open Trivia DB 요청당 문제 수 (최대 50)
API_MAX_PAGES         = 5   # 최대 API 요청 횟수 (총 250문항)
QUIZ_TIMER_SECONDS    = 20  # 문제당 제한 시간(초)
AUTO_ADVANCE_SECONDS  = 5   # 정답 확인 후 자동 이동 대기(초)

# ==============================================================================
# 나라 메타데이터
# ==============================================================================
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
# 폴백 퀴즈 (오프라인 또는 API 부족 시 사용)
# ==============================================================================
# 폴백 풀 — 나라당 15문제, 로그인마다 5개 무작위 선택
FALLBACK_POOL: dict[str, list[dict]] = {
    "대한민국": [
        {"question": "대한민국의 수도는 어디입니까?",
         "choices": ["서울", "부산", "인천", "대구"], "answer": "서울",
         "fact": "서울은 대한민국의 수도이자 최대 도시입니다.", "translated": True},
        {"question": "한국의 국화는 무엇입니까?",
         "choices": ["무궁화", "장미", "진달래", "국화"], "answer": "무궁화",
         "fact": "무궁화는 대한민국의 국화입니다.", "translated": True},
        {"question": "한국의 전통 발효 음식은?",
         "choices": ["김치", "스시", "라멘", "딤섬"], "answer": "김치",
         "fact": "김치는 한국의 대표적인 발효 음식입니다.", "translated": True},
        {"question": "한국의 전통 의상은?",
         "choices": ["한복", "기모노", "치파오", "사리"], "answer": "한복",
         "fact": "한복은 한국의 전통 의상입니다.", "translated": True},
        {"question": "서울의 대표적인 궁궐은?",
         "choices": ["경복궁", "황궁", "자금성", "버킹엄궁"], "answer": "경복궁",
         "fact": "경복궁은 조선 왕조의 정궁입니다.", "translated": True},
        {"question": "한국의 전통 음악 장르 중 하나는?",
         "choices": ["판소리", "가부키", "경극", "플라멩코"], "answer": "판소리",
         "fact": "판소리는 유네스코 인류무형문화유산에 등재된 한국의 전통 음악입니다.", "translated": True},
        {"question": "한국에서 가장 긴 강은?",
         "choices": ["낙동강", "한강", "금강", "영산강"], "answer": "낙동강",
         "fact": "낙동강은 약 525km로 한국에서 가장 긴 강입니다.", "translated": True},
        {"question": "한글을 창제한 왕은?",
         "choices": ["세종대왕", "태조", "광개토대왕", "정조"], "answer": "세종대왕",
         "fact": "세종대왕은 1443년 훈민정음(한글)을 창제했습니다.", "translated": True},
        {"question": "한국의 전통 씨름 경기는?",
         "choices": ["씨름", "유도", "스모", "레슬링"], "answer": "씨름",
         "fact": "씨름은 유네스코 인류무형문화유산으로 등재된 한국 전통 스포츠입니다.", "translated": True},
        {"question": "불국사가 위치한 도시는?",
         "choices": ["경주", "부산", "전주", "수원"], "answer": "경주",
         "fact": "불국사는 경주에 위치한 유네스코 세계문화유산입니다.", "translated": True},
        {"question": "한국의 전통 혼례복 색깔 중 신부가 주로 입는 색은?",
         "choices": ["붉은색", "흰색", "파란색", "노란색"], "answer": "붉은색",
         "fact": "한국 전통 혼례에서 신부는 붉은색 한복을 주로 입습니다.", "translated": True},
        {"question": "한국의 국기 이름은?",
         "choices": ["태극기", "일장기", "성조기", "유니언잭"], "answer": "태극기",
         "fact": "태극기는 대한민국의 국기로, 태극 문양과 사괘로 구성됩니다.", "translated": True},
        {"question": "제주도에 있는 한국 최고봉은?",
         "choices": ["한라산", "설악산", "지리산", "백두산"], "answer": "한라산",
         "fact": "한라산(1,950m)은 제주도에 위치한 한국의 최고봉입니다.", "translated": True},
        {"question": "한국의 전통 가옥 형태는?",
         "choices": ["한옥", "다다미방", "후통", "리야드"], "answer": "한옥",
         "fact": "한옥은 자연 재료를 사용한 한국 전통 건축 양식입니다.", "translated": True},
        {"question": "한국의 전통 탈춤 중 가장 유명한 것은?",
         "choices": ["봉산탈춤", "사자춤", "부채춤", "강강술래"], "answer": "봉산탈춤",
         "fact": "봉산탈춤은 황해도 봉산 지역에서 유래한 한국의 대표적인 탈춤입니다.", "translated": True},
    ],
    "미국": [
        {"question": "미국의 수도는 어디입니까?",
         "choices": ["워싱턴 D.C.", "뉴욕", "로스앤젤레스", "시카고"],
         "answer": "워싱턴 D.C.", "fact": "워싱턴 D.C.는 미국의 수도입니다.", "translated": True},
        {"question": "미국의 초대 대통령은?",
         "choices": ["조지 워싱턴", "에이브러햄 링컨", "토머스 제퍼슨", "존 애덤스"],
         "answer": "조지 워싱턴", "fact": "조지 워싱턴은 미국의 초대 대통령입니다.", "translated": True},
        {"question": "미국의 독립 기념일은?",
         "choices": ["7월 4일", "7월 14일", "6월 4일", "8월 4일"],
         "answer": "7월 4일", "fact": "미국은 1776년 7월 4일 독립을 선언했습니다.", "translated": True},
        {"question": "미국의 국조(나라 새)는?",
         "choices": ["흰머리수리", "독수리", "콘도르", "매"],
         "answer": "흰머리수리", "fact": "흰머리수리(대머리독수리)는 미국의 국조입니다.", "translated": True},
        {"question": "그랜드 캐니언이 위치한 주는?",
         "choices": ["애리조나", "텍사스", "캘리포니아", "콜로라도"],
         "answer": "애리조나", "fact": "그랜드 캐니언은 애리조나 주에 위치합니다.", "translated": True},
        {"question": "미국에서 가장 긴 강은?",
         "choices": ["미시시피강", "미주리강", "콜로라도강", "허드슨강"],
         "answer": "미시시피강", "fact": "미시시피강은 미국에서 가장 긴 강 중 하나로 약 3,730km입니다.", "translated": True},
        {"question": "자유의 여신상이 위치한 곳은?",
         "choices": ["뉴욕", "워싱턴 D.C.", "보스턴", "필라델피아"],
         "answer": "뉴욕", "fact": "자유의 여신상은 뉴욕항의 리버티섬에 위치합니다.", "translated": True},
        {"question": "미국 헌법이 제정된 연도는?",
         "choices": ["1787년", "1776년", "1800년", "1865년"],
         "answer": "1787년", "fact": "미국 헌법은 1787년 필라델피아 제헌회의에서 제정되었습니다.", "translated": True},
        {"question": "미국의 국화는?",
         "choices": ["장미", "튤립", "국화", "해바라기"],
         "answer": "장미", "fact": "장미는 1986년 미국의 국화로 지정되었습니다.", "translated": True},
        {"question": "미국 최초의 국립공원은?",
         "choices": ["옐로스톤", "그랜드 캐니언", "요세미티", "에버글레이즈"],
         "answer": "옐로스톤", "fact": "옐로스톤은 1872년 세계 최초의 국립공원으로 지정되었습니다.", "translated": True},
        {"question": "미국 남북전쟁은 몇 년에 끝났습니까?",
         "choices": ["1865년", "1870년", "1860년", "1875년"],
         "answer": "1865년", "fact": "미국 남북전쟁은 1861년에 시작해 1865년에 북군의 승리로 끝났습니다.", "translated": True},
        {"question": "미국의 실리콘밸리는 어느 주에 있습니까?",
         "choices": ["캘리포니아", "텍사스", "플로리다", "뉴욕"],
         "answer": "캘리포니아", "fact": "실리콘밸리는 캘리포니아 주 샌프란시스코 만 지역에 위치합니다.", "translated": True},
        {"question": "미국 최고 법원의 이름은?",
         "choices": ["연방대법원", "항소법원", "지방법원", "헌법재판소"],
         "answer": "연방대법원", "fact": "연방대법원은 미국 사법부의 최고 기관입니다.", "translated": True},
        {"question": "나사(NASA)의 본부가 있는 곳은?",
         "choices": ["워싱턴 D.C.", "휴스턴", "플로리다", "캘리포니아"],
         "answer": "워싱턴 D.C.", "fact": "NASA 본부는 워싱턴 D.C.에 있으며, 존슨 우주센터는 텍사스 휴스턴에 있습니다.", "translated": True},
        {"question": "미국의 50번째 주는?",
         "choices": ["하와이", "알래스카", "아리조나", "뉴멕시코"],
         "answer": "하와이", "fact": "하와이는 1959년 미국의 50번째 주로 편입되었습니다.", "translated": True},
    ],
    "영국": [
        {"question": "영국의 수도는 어디입니까?",
         "choices": ["런던", "맨체스터", "버밍엄", "에든버러"],
         "answer": "런던", "fact": "런던은 영국의 수도이자 최대 도시입니다.", "translated": True},
        {"question": "영국 왕실의 공식 거주지는?",
         "choices": ["버킹엄 궁전", "윈저 성", "켄싱턴 궁전", "세인트제임스 궁전"],
         "answer": "버킹엄 궁전", "fact": "버킹엄 궁전은 영국 왕실의 공식 런던 거주지입니다.", "translated": True},
        {"question": "영국의 유명한 시계탑은?",
         "choices": ["빅벤", "에펠탑", "자유의 여신상", "시계탑"],
         "answer": "빅벤", "fact": "빅벤은 런던 의회 의사당의 시계탑입니다.", "translated": True},
        {"question": "셰익스피어의 출생지는?",
         "choices": ["스트랫퍼드어폰에이번", "런던", "옥스퍼드", "에든버러"],
         "answer": "스트랫퍼드어폰에이번",
         "fact": "윌리엄 셰익스피어는 1564년 스트랫퍼드어폰에이번에서 태어났습니다.", "translated": True},
        {"question": "영국의 국화는?",
         "choices": ["장미", "백합", "국화", "튤립"],
         "answer": "장미", "fact": "장미는 영국의 국화입니다.", "translated": True},
        {"question": "영국의 명문 대학교 두 곳은?",
         "choices": ["옥스퍼드·케임브리지", "하버드·MIT", "소르본·파리", "베를린·뮌헨"],
         "answer": "옥스퍼드·케임브리지", "fact": "옥스퍼드와 케임브리지는 영국을 대표하는 세계 최고의 명문 대학입니다.", "translated": True},
        {"question": "템스강이 흐르는 도시는?",
         "choices": ["런던", "맨체스터", "리버풀", "브리스틀"],
         "answer": "런던", "fact": "템스강은 영국 잉글랜드 남부를 흐르며 런던을 관통합니다.", "translated": True},
        {"question": "영국의 유명한 선사시대 유적지는?",
         "choices": ["스톤헨지", "콜로세움", "아크로폴리스", "앙코르와트"],
         "answer": "스톤헨지", "fact": "스톤헨지는 잉글랜드 윌트셔에 위치한 유네스코 세계문화유산입니다.", "translated": True},
        {"question": "영국의 화폐 단위는?",
         "choices": ["파운드", "유로", "달러", "프랑"],
         "answer": "파운드", "fact": "영국 파운드(£)는 세계에서 가장 오래된 통화 중 하나입니다.", "translated": True},
        {"question": "해리포터의 원작자는?",
         "choices": ["J.K. 롤링", "J.R.R. 톨킨", "C.S. 루이스", "로알드 달"],
         "answer": "J.K. 롤링", "fact": "J.K. 롤링은 영국 작가로, 해리포터 시리즈의 원작자입니다.", "translated": True},
        {"question": "비틀즈의 출신 도시는?",
         "choices": ["리버풀", "런던", "맨체스터", "버밍엄"],
         "answer": "리버풀", "fact": "비틀즈는 1960년대 영국 리버풀에서 결성된 전설적인 록 밴드입니다.", "translated": True},
        {"question": "영국의 국가 보건 서비스 약자는?",
         "choices": ["NHS", "CDC", "WHO", "IMF"],
         "answer": "NHS", "fact": "NHS(National Health Service)는 1948년 설립된 영국의 공공 의료 시스템입니다.", "translated": True},
        {"question": "영국 최고봉은?",
         "choices": ["벤네비스산", "스노든산", "스캐펠파이크", "펜-이-판"],
         "answer": "벤네비스산", "fact": "벤네비스산(1,345m)은 스코틀랜드에 위치한 영국의 최고봉입니다.", "translated": True},
        {"question": "영국의 국가 원수는 누구입니까?",
         "choices": ["국왕", "대통령", "수상", "총리"],
         "answer": "국왕", "fact": "영국은 입헌군주제 국가로 국왕이 국가 원수입니다.", "translated": True},
        {"question": "세계 최초의 공공 철도가 개통된 나라는?",
         "choices": ["영국", "미국", "프랑스", "독일"],
         "answer": "영국", "fact": "세계 최초의 공공 증기 철도는 1825년 영국에서 개통되었습니다.", "translated": True},
    ],
    "일본": [
        {"question": "일본의 수도는 어디입니까?",
         "choices": ["도쿄", "오사카", "교토", "나고야"],
         "answer": "도쿄", "fact": "도쿄는 일본의 수도이자 세계 최대 도시 중 하나입니다.", "translated": True},
        {"question": "일본의 국화는?",
         "choices": ["국화", "벚꽃", "매화", "연꽃"],
         "answer": "국화", "fact": "국화는 일본 황실의 문장으로 사용되는 일본의 국화입니다.", "translated": True},
        {"question": "일본의 대표적인 전통 공연 예술은?",
         "choices": ["가부키", "노", "분라쿠", "교겐"],
         "answer": "가부키", "fact": "가부키는 일본의 대표적인 전통 공연 예술입니다.", "translated": True},
        {"question": "일본의 최고봉은?",
         "choices": ["후지산", "아소산", "사쿠라지마", "온타케산"],
         "answer": "후지산", "fact": "후지산은 일본의 최고봉(3776m)으로 세계문화유산입니다.", "translated": True},
        {"question": "일본의 공식 통화는?",
         "choices": ["엔(円)", "위안", "달러", "원"],
         "answer": "엔(円)", "fact": "엔(円, ¥)은 일본의 공식 통화입니다.", "translated": True},
        {"question": "일본의 전통 시 형식은?",
         "choices": ["하이쿠", "소네트", "시조", "한시"],
         "answer": "하이쿠", "fact": "하이쿠는 5-7-5 음절로 구성된 일본의 전통 단시 형식입니다.", "translated": True},
        {"question": "일본의 대표적인 전통 무술은?",
         "choices": ["유도", "태권도", "쿵후", "무에타이"],
         "answer": "유도", "fact": "유도는 일본에서 시작된 무술로 1964년 도쿄 올림픽 정식 종목이 되었습니다.", "translated": True},
        {"question": "일본의 전통 3대 명원 중 하나인 곳은?",
         "choices": ["겐로쿠엔", "베르사유 궁전", "버킹엄 궁전 정원", "중국 이화원"],
         "answer": "겐로쿠엔", "fact": "겐로쿠엔은 가나자와에 위치한 일본 3대 명원 중 하나입니다.", "translated": True},
        {"question": "일본의 전통 인형극은?",
         "choices": ["분라쿠", "가부키", "노", "라쿠고"],
         "answer": "분라쿠", "fact": "분라쿠는 유네스코 인류무형문화유산에 등재된 일본 전통 인형극입니다.", "translated": True},
        {"question": "일본에서 가장 큰 섬은?",
         "choices": ["혼슈", "홋카이도", "규슈", "시코쿠"],
         "answer": "혼슈", "fact": "혼슈는 일본 최대의 섬으로 도쿄, 오사카 등 주요 도시가 위치합니다.", "translated": True},
        {"question": "일본의 전통 스모 경기장 이름은?",
         "choices": ["료고쿠 국기관", "도쿄 돔", "오사카 성", "닛코"],
         "answer": "료고쿠 국기관", "fact": "료고쿠 국기관은 도쿄에 위치한 일본 스모의 성지입니다.", "translated": True},
        {"question": "일본의 대표적인 만화·애니메이션 거리가 있는 도쿄의 지역은?",
         "choices": ["아키하바라", "시부야", "신주쿠", "아사쿠사"],
         "answer": "아키하바라", "fact": "아키하바라는 전자제품과 애니메이션·만화 문화의 중심지입니다.", "translated": True},
        {"question": "일본의 전통 다도 의식을 무엇이라 합니까?",
         "choices": ["차노유", "다례", "다도", "다회"],
         "answer": "차노유", "fact": "차노유(茶の湯)는 일본의 전통 차 의식으로 선(禅) 정신을 담고 있습니다.", "translated": True},
        {"question": "일본이 2차 세계대전 종전을 선언한 연도는?",
         "choices": ["1945년", "1943년", "1947년", "1950년"],
         "answer": "1945년", "fact": "일본은 1945년 8월 15일 연합군에 무조건 항복을 선언했습니다.", "translated": True},
        {"question": "일본의 국기 명칭은?",
         "choices": ["히노마루", "태극기", "성조기", "유니언잭"],
         "answer": "히노마루", "fact": "히노마루(日の丸)는 흰 바탕에 붉은 원이 그려진 일본의 국기입니다.", "translated": True},
    ],
    "독일": [
        {"question": "독일의 수도는 어디입니까?",
         "choices": ["베를린", "뮌헨", "함부르크", "프랑크푸르트"],
         "answer": "베를린", "fact": "베를린은 독일의 수도이자 최대 도시입니다.", "translated": True},
        {"question": "다음 중 독일 자동차 브랜드가 아닌 것은?",
         "choices": ["피아트", "BMW", "벤츠", "폭스바겐"],
         "answer": "피아트", "fact": "피아트는 이탈리아 자동차 브랜드입니다.", "translated": True},
        {"question": "베를린 장벽이 붕괴된 연도는?",
         "choices": ["1989년", "1991년", "1985년", "1993년"],
         "answer": "1989년", "fact": "베를린 장벽은 1989년 11월 9일 붕괴되었습니다.", "translated": True},
        {"question": "독일의 대표적인 맥주 축제는?",
         "choices": ["옥토버페스트", "카니발", "크리스마스 마켓", "라인강 축제"],
         "answer": "옥토버페스트", "fact": "옥토버페스트는 매년 뮌헨에서 열리는 세계 최대 맥주 축제입니다.", "translated": True},
        {"question": "독일 통일은 몇 년에 이루어졌습니까?",
         "choices": ["1990년", "1989년", "1991년", "1992년"],
         "answer": "1990년", "fact": "동독과 서독은 1990년 10월 3일 공식 통일되었습니다.", "translated": True},
        {"question": "베토벤의 출생지는?",
         "choices": ["본", "베를린", "뮌헨", "함부르크"],
         "answer": "본", "fact": "루트비히 판 베토벤은 1770년 독일 본에서 태어났습니다.", "translated": True},
        {"question": "독일의 유명한 동화 수집가는?",
         "choices": ["그림 형제", "안데르센", "페로", "오스카 와일드"],
         "answer": "그림 형제", "fact": "그림 형제(야코프·빌헬름)는 신데렐라, 백설공주 등 유명 동화를 수집·출판했습니다.", "translated": True},
        {"question": "독일의 화폐는 무엇입니까?",
         "choices": ["유로", "마르크", "파운드", "프랑"],
         "answer": "유로", "fact": "독일은 2002년부터 유로화를 공식 통화로 사용합니다.", "translated": True},
        {"question": "독일의 최대 항구 도시는?",
         "choices": ["함부르크", "브레멘", "킬", "뤼베크"],
         "answer": "함부르크", "fact": "함부르크는 독일 최대의 항구 도시이자 두 번째로 큰 도시입니다.", "translated": True},
        {"question": "마르틴 루터가 종교개혁 논제를 붙인 도시는?",
         "choices": ["비텐베르크", "베를린", "쾰른", "아우크스부르크"],
         "answer": "비텐베르크", "fact": "마르틴 루터는 1517년 비텐베르크 성당 문에 95개조 논제를 게시했습니다.", "translated": True},
        {"question": "독일의 대표적인 르네상스 화가는?",
         "choices": ["뒤러", "모네", "피카소", "렘브란트"],
         "answer": "뒤러", "fact": "알브레히트 뒤러는 독일 르네상스를 대표하는 화가·판화가입니다.", "translated": True},
        {"question": "독일 최고봉은?",
         "choices": ["추크슈피체", "바츠만", "베르히테스가덴", "펠트베르크"],
         "answer": "추크슈피체", "fact": "추크슈피체(2,962m)는 바이에른 알프스에 위치한 독일의 최고봉입니다.", "translated": True},
        {"question": "독일의 인쇄술을 발명한 사람은?",
         "choices": ["구텐베르크", "에디슨", "다빈치", "파라데이"],
         "answer": "구텐베르크", "fact": "요하네스 구텐베르크는 15세기 활판 인쇄술을 발명해 지식 혁명을 이끌었습니다.", "translated": True},
        {"question": "독일의 유명한 낭만주의 고성이 있는 지역은?",
         "choices": ["바이에른", "작센", "튀링겐", "헤센"],
         "answer": "바이에른", "fact": "노이슈반슈타인 성 등 독일의 대표적인 낭만주의 고성은 바이에른 주에 위치합니다.", "translated": True},
        {"question": "독일 연방의회(의회)가 위치한 건물은?",
         "choices": ["라이히스탁", "브란덴부르크 문", "벨뷔궁", "체크포인트 찰리"],
         "answer": "라이히스탁", "fact": "라이히스탁은 베를린에 위치한 독일 연방의회 건물로, 유리 돔이 특징입니다.", "translated": True},
    ],
}

# 글로벌 문제 풀 사용 추적 — 서버 재시작 전까지 누적
# {나라: [이미 출제된 문제 인덱스, ...]}
_GLOBAL_USED: dict[str, list[int]] = {c: [] for c in COUNTRY_META}

def _pick_fallback(country: str, n: int) -> list[dict]:
    """
    FALLBACK_POOL에서 n개를 선택합니다.
    가능한 한 전역적으로 이미 출제된 문제를 피하고,
    모두 소진되면 전체 풀을 리셋해 다시 순환합니다.
    """
    pool = FALLBACK_POOL[country]
    used = _GLOBAL_USED[country]

    # 미사용 인덱스
    unused_idx = [i for i in range(len(pool)) if i not in used]

    # 부족하면 리셋
    if len(unused_idx) < n:
        _GLOBAL_USED[country] = []
        unused_idx = list(range(len(pool)))

    chosen_idx = random.sample(unused_idx, min(n, len(unused_idx)))
    _GLOBAL_USED[country].extend(chosen_idx)
    return [pool[i] for i in chosen_idx]

# 하위 호환: 기존 코드가 FALLBACK_QUIZ를 참조하는 부분 지원
FALLBACK_QUIZ: dict[str, list[dict]] = {
    c: FALLBACK_POOL[c][:5] for c in FALLBACK_POOL
}

# 앱 전체에서 공유되는 랭킹 데이터 (메모리)
RANKING_DATA: list[dict] = []

# ==============================================================================
# 번역 유틸리티
# ── 전략: Google Translate 비공개 Ajax 엔드포인트(API 키 불필요)를 1순위로,
#          MyMemory API를 2순위 폴백으로 사용합니다.
#          두 방법 모두 실패하면 원문을 반환합니다.
# ==============================================================================
_translation_cache: dict[str, str] = {}

_GT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
    "Referer": "https://translate.google.com/",
}

def _translate_google(text: str) -> str | None:
    """
    Google Translate 비공개 Ajax 엔드포인트로 영→한 번역을 시도합니다.
    성공하면 번역 문자열을, 실패하면 None을 반환합니다.
    """
    try:
        resp = req_lib.get(
            "https://translate.googleapis.com/translate_a/single",
            params={
                "client": "gtx",
                "sl":     "en",
                "tl":     "ko",
                "dt":     "t",
                "q":      text,
            },
            headers=_GT_HEADERS,
            timeout=8,
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        # 응답 구조: [[[번역문, 원문, ...], ...], ...]
        parts = data[0] if data and isinstance(data, list) else []
        result = "".join(
            seg[0] for seg in parts
            if isinstance(seg, list) and seg and isinstance(seg[0], str)
        ).strip()
        return result if result else None
    except Exception:
        return None


def _translate_mymemory(text: str) -> str | None:
    """MyMemory 무료 API로 영→한 번역을 시도합니다 (폴백용)."""
    try:
        resp = req_lib.get(
            "https://api.mymemory.translated.net/get",
            params={"q": text, "langpair": "en|ko"},
            timeout=8,
        )
        data       = resp.json()
        translated = data.get("responseData", {}).get("translatedText", "")
        if (translated
                and not translated.lower().startswith("invalid")
                and not translated.lower().startswith("mymemory")):
            return translated.strip()
    except Exception:
        pass
    return None


def translate_to_korean(text: str) -> str:
    """
    영어 텍스트를 한국어로 번역합니다.
    1순위: Google Translate (비공개 gtx 엔드포인트, API 키 불필요)
    2순위: MyMemory API (폴백)
    실패 시: 원문 반환
    캐시를 사용해 동일 텍스트의 중복 요청을 방지합니다.
    """
    if not text or not REQUESTS_AVAILABLE:
        return text
    if text in _translation_cache:
        return _translation_cache[text]

    # 1순위: Google Translate
    result = _translate_google(text)

    # 2순위: MyMemory 폴백
    if not result:
        result = _translate_mymemory(text)

    final = result if result else text
    _translation_cache[text] = final
    return final


def _is_korean(text: str) -> bool:
    """텍스트에 한글 문자가 하나 이상 포함되어 있으면 True를 반환합니다."""
    return any("\uAC00" <= ch <= "\uD7A3" or "\u1100" <= ch <= "\u11FF" for ch in text)


def translate_question(q_en: dict) -> dict:
    """
    영어 퀴즈 딕셔너리를 받아 문제·선택지·정답·해설을 모두 한국어로 번역합니다.
    ★ 최적화: 모든 텍스트를 ThreadPoolExecutor로 병렬 번역합니다.
    """
    texts_to_translate = (
        [q_en["question"], q_en["answer"]]
        + q_en["choices"]
        + [q_en.get("fact", "")]
    )

    # 캐시 히트는 즉시 처리, 미스만 병렬 번역
    results: dict[str, str] = {}
    uncached = [t for t in texts_to_translate if t not in _translation_cache]

    def _safe_one(text: str) -> tuple[str, str]:
        if not text:
            return text, text
        result = _translate_google(text) or _translate_mymemory(text) or text
        if not _is_korean(result) and result != text:
            # 재시도
            result = _translate_google(text) or _translate_mymemory(text) or text
        _translation_cache[text] = result
        return text, result

    # 병렬 번역 (최대 8 스레드)
    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = {ex.submit(_safe_one, t): t for t in uncached}
        for fut in as_completed(futures):
            orig, translated = fut.result()
            results[orig] = translated

    # 캐시 히트 병합
    for t in texts_to_translate:
        if t not in results:
            results[t] = _translation_cache.get(t, t)

    translated_q       = results[q_en["question"]]
    translated_ans     = results[q_en["answer"]]
    translated_choices = [results[c] for c in q_en["choices"]]
    translated_fact    = results[q_en.get("fact", "")]
    is_translated      = _is_korean(translated_q) or _is_korean(translated_ans)

    if not is_translated:
        print(f"  [번역 경고] 한글 변환 실패 — 원문 사용: {q_en['question'][:60]}")

    return {
        "question":   translated_q,
        "choices":    translated_choices,
        "answer":     translated_ans,
        "fact":       translated_fact,
        "translated": is_translated,
        "source":     q_en.get("source", "Open Trivia DB"),
    }


# ==============================================================================
# Open Trivia DB 가져오기 + 번역
# ==============================================================================

def _best_country_for(question_text: str) -> str | None:
    qt = question_text.lower()
    best_country: str | None = None
    best_kw_len: int = 0
    for country, meta in COUNTRY_META.items():
        for kw in meta["keywords"]:
            if kw in qt and len(kw) > best_kw_len:
                best_country = country
                best_kw_len  = len(kw)
    return best_country


# ==============================================================================
# 서버 시작 시 미리 준비해 두는 퀴즈 캐시
# 로그인하면 캐시에서 즉시 반환하고, 백그라운드에서 다음 세트를 준비합니다.
# ==============================================================================
_prefetch_cache: list[dict] = []          # 준비된 퀴즈 세트 목록
_prefetch_lock  = threading.Lock()
_prefetch_event = threading.Event()       # 첫 번째 세트 준비 완료 신호

def _fetch_one_batch() -> tuple[dict[str, list[dict]], str, str | None]:
    """
    Open Trivia DB에서 문제를 1회 요청하고 병렬 번역합니다.
    ★ 최적화 포인트:
      - sleep(5) 완전 제거 (1번만 요청하므로 불필요)
      - 문제를 모아서 ThreadPoolExecutor로 한꺼번에 병렬 번역
      - 버킷이 다 차면 즉시 종료
    """
    if not REQUESTS_AVAILABLE:
        return {c: _pick_fallback(c, QUESTIONS_PER_COUNTRY) for c in COUNTRY_META}, "fallback", "requests 없음"

    buckets: dict[str, list[dict]] = {c: [] for c in COUNTRY_META}
    seen_questions: set[str] = set()
    any_network = False
    last_error: str | None = None
    raw_candidates: list[dict] = []   # 번역 전 후보 문제

    def _all_full() -> bool:
        return all(len(buckets[c]) >= QUESTIONS_PER_COUNTRY for c in COUNTRY_META)

    # Open Trivia DB: 최대 2페이지만 시도 (sleep 없음)
    for page in range(min(API_MAX_PAGES, 2)):
        if _all_full():
            break
        try:
            resp = req_lib.get(
                "https://opentdb.com/api.php",
                params={"amount": API_BATCH_SIZE, "category": 22,
                        "type": "multiple", "encode": "url3986"},
                timeout=8,
            )
            if resp.status_code == 429:
                time.sleep(3)   # 짧게만 대기
                continue
            resp.raise_for_status()
            data = resp.json()
            if data.get("response_code") != 0:
                break
            any_network = True

            for item in data.get("results", []):
                decoded_q = unquote(item["question"])
                q_key     = decoded_q.strip().lower()
                if q_key in seen_questions:
                    continue
                seen_questions.add(q_key)

                country = _best_country_for(decoded_q)
                if country is None or len(buckets[country]) >= QUESTIONS_PER_COUNTRY:
                    continue

                correct   = unquote(item["correct_answer"])
                incorrect = [unquote(w) for w in item["incorrect_answers"]]
                choices   = incorrect + [correct]
                random.shuffle(choices)
                raw_candidates.append({
                    "country":  country,
                    "question": decoded_q,
                    "choices":  choices,
                    "answer":   correct,
                    "fact":     f"출처: Open Trivia DB / {unquote(item.get('category', ''))}",
                    "source":   "Open Trivia DB",
                })

        except req_lib.exceptions.ConnectionError:
            last_error = "인터넷 연결 없음"
            break
        except req_lib.exceptions.Timeout:
            last_error = "서버 응답 시간 초과"
            break
        except Exception as e:
            last_error = str(e)
            break

    # ★ 후보 문제 전체를 ThreadPoolExecutor로 병렬 번역
    if raw_candidates:
        def _translate_one(raw: dict) -> dict:
            result = translate_question(raw)
            result["_country"] = raw["country"]
            return result

        with ThreadPoolExecutor(max_workers=10) as ex:
            translated_list = list(ex.map(_translate_one, raw_candidates))

        for tq in translated_list:
            c = tq.pop("_country")
            if len(buckets[c]) < QUESTIONS_PER_COUNTRY:
                buckets[c].append(tq)

    # 부족분은 폴백으로 채우기
    quiz: dict[str, list[dict]] = {}
    for country in COUNTRY_META:
        net_qs = list(buckets[country])
        needed = QUESTIONS_PER_COUNTRY - len(net_qs)
        fill   = _pick_fallback(country, needed) if needed > 0 else []
        random.shuffle(net_qs)
        quiz[country] = net_qs + fill

    source = "network" if any_network else "fallback"
    return quiz, source, last_error


def fetch_and_translate_quiz() -> tuple[dict[str, list[dict]], str, str | None]:
    """
    캐시에서 즉시 반환하고, 백그라운드에서 다음 세트를 미리 준비합니다.
    첫 로그인 전에 서버가 미리 준비해 두므로 대기 시간이 거의 없습니다.
    """
    # 첫 번째 준비 완료까지 최대 15초 대기 (폴백보다는 네트워크 우선)
    _prefetch_event.wait(timeout=15)

    with _prefetch_lock:
        if _prefetch_cache:
            entry = _prefetch_cache.pop(0)
            quiz, source, error = entry["quiz"], entry["source"], entry["error"]
        else:
            # 캐시가 비어 있으면 폴백 즉시 반환
            quiz   = {c: _pick_fallback(c, QUESTIONS_PER_COUNTRY) for c in COUNTRY_META}
            source = "fallback"
            error  = "캐시 준비 중 — 폴백 사용"

    # 백그라운드에서 다음 세트 준비
    threading.Thread(target=_prefetch_worker, daemon=True).start()
    return quiz, source, error


def _prefetch_worker() -> None:
    """백그라운드에서 퀴즈 세트를 미리 1개 준비해 캐시에 저장합니다."""
    with _prefetch_lock:
        if len(_prefetch_cache) >= 2:   # 이미 충분히 준비됨
            return

    try:
        quiz, source, error = _fetch_one_batch()
        with _prefetch_lock:
            _prefetch_cache.append({"quiz": quiz, "source": source, "error": error})
        _prefetch_event.set()
        print(f"  [프리패치] 퀴즈 세트 준비 완료 (출처: {source})")
    except Exception as e:
        print(f"  [프리패치 오류] {e}")
        _prefetch_event.set()   # 오류여도 대기 해제


# ==============================================================================
# 세션 관리 헬퍼
# ==============================================================================

def init_session_if_needed() -> None:
    """세션에 필요한 키가 없으면 초기화합니다."""
    if "user_id" not in session:
        session["user_id"]          = ""
    if "quiz_data" not in session:
        session["quiz_data"]        = None
    if "data_source" not in session:
        session["data_source"]      = None
    if "network_error" not in session:
        session["network_error"]    = None
    if "completed" not in session:
        session["completed"]        = []    # 완료된 나라 목록
    if "total_score" not in session:
        session["total_score"]      = 0
    if "current_country" not in session:
        session["current_country"]  = ""
    if "quiz_pool" not in session:
        session["quiz_pool"]        = []
    if "step" not in session:
        session["step"]             = 0
    # ★ 중복 방지: 세션 내 출제된 문제 키 집합
    if "seen_question_keys" not in session:
        session["seen_question_keys"] = {}   # {나라: [문제 키, ...]}


def get_seen_keys(country: str) -> list[str]:
    return session.get("seen_question_keys", {}).get(country, [])


def mark_question_seen(country: str, question: str) -> None:
    """출제된 문제를 세션에 기록합니다."""
    seen = session.setdefault("seen_question_keys", {})
    keys = seen.setdefault(country, [])
    key  = question.strip().lower()
    if key not in keys:
        keys.append(key)
    session["seen_question_keys"] = seen
    session.modified = True


def build_quiz_pool(country: str) -> list[dict]:
    """
    해당 나라의 퀴즈 풀을 구성합니다.
    ★ 이미 출제된 문제(seen_question_keys)는 제외하고,
      남은 문제가 부족하면 폴백에서 보충합니다.
    """
    quiz_data: dict = session.get("quiz_data") or FALLBACK_QUIZ
    all_questions    = list(quiz_data.get(country, FALLBACK_QUIZ[country]))
    seen             = set(get_seen_keys(country))

    # 미출제 문제 필터링
    unseen = [q for q in all_questions
              if q["question"].strip().lower() not in seen]

    # 부족하면 폴백에서 무작위 보충 (중복 체크)
    if len(unseen) < QUESTIONS_PER_COUNTRY:
        needed_extra = QUESTIONS_PER_COUNTRY - len(unseen)
        fb_candidates = _pick_fallback(country, needed_extra * 2)
        fb_unseen = [q for q in fb_candidates
                     if q["question"].strip().lower() not in seen
                     and q not in unseen]
        unseen.extend(fb_unseen)

    # 최대 QUESTIONS_PER_COUNTRY개 무작위 선택
    random.shuffle(unseen)
    pool = unseen[:QUESTIONS_PER_COUNTRY]
    return pool


# ==============================================================================
# Flask 앱
# ==============================================================================
app = Flask(__name__)
app.secret_key = uuid.uuid4().hex  # 세션 암호화 키

# 서버 시작 즉시 백그라운드에서 첫 번째 퀴즈 세트 준비 시작
threading.Thread(target=_prefetch_worker, daemon=True).start()


# ──────────────────────────────────────────────────────────────────────────────
# HTML 템플릿 (인라인 — 별도 파일 불필요)
# ──────────────────────────────────────────────────────────────────────────────
HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>🌍 세계 지식 마스터 퀴즈</title>
<style>
  /* ── Reset & Base ── */
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: 'Malgun Gothic', 'Apple SD Gothic Neo', 'Noto Sans KR', sans-serif;
    background: #0f172a;
    color: #e2e8f0;
    min-height: 100vh;
    display: flex;
    flex-direction: column;
  }

  /* ── Colours ── */
  :root {
    --bg:        #0f172a;
    --card:      #1e3a5f;
    --header:    #1e293b;
    --accent:    #3b82f6;
    --success:   #22c55e;
    --danger:    #ef4444;
    --warning:   #f59e0b;
    --text:      #e2e8f0;
    --text-sec:  #94a3b8;
    --border:    #2d4a7a;
  }

  /* ── Layout ── */
  header {
    background: var(--header);
    padding: 18px 32px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    border-bottom: 1px solid var(--border);
  }
  header h1 { font-size: 1.4rem; }
  header .meta { font-size: .85rem; color: var(--text-sec); text-align:right; }

  main {
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 40px 16px;
  }

  /* ── Cards ── */
  .card {
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 16px;
    padding: 40px 48px;
    width: 100%;
    max-width: 520px;
    box-shadow: 0 8px 32px rgba(0,0,0,.4);
  }
  .card h2 { margin-bottom: 6px; }
  .card p.sub { color: var(--text-sec); font-size:.9rem; margin-bottom:24px; }

  /* ── Form elements ── */
  label { display:block; font-size:.85rem; color:var(--text-sec); margin-bottom:6px; }
  input[type=text] {
    width: 100%;
    padding: 12px 16px;
    background: #0f172a;
    border: 2px solid var(--border);
    border-radius: 8px;
    color: var(--text);
    font-size: 1rem;
    outline: none;
    transition: border-color .2s;
  }
  input[type=text]:focus { border-color: var(--accent); }
  .err { color: var(--danger); font-size:.85rem; margin-top:8px; min-height:20px; }

  /* ── Buttons ── */
  .btn {
    display: inline-block;
    padding: 12px 32px;
    border-radius: 8px;
    border: none;
    font-size: 1rem;
    font-weight: 700;
    cursor: pointer;
    transition: background .15s, transform .1s;
  }
  .btn:active { transform: scale(.97); }
  .btn-primary   { background: var(--accent);   color: #fff; }
  .btn-primary:hover   { background: #2563eb; }
  .btn-success   { background: var(--success);  color: #fff; }
  .btn-success:hover   { background: #16a34a; }
  .btn-secondary { background: var(--header);   color: var(--text); border:1px solid var(--border); }
  .btn-secondary:hover { background: var(--border); }
  .btn-full { width:100%; margin-top:20px; }
  .btn-sm   { padding: 8px 20px; font-size:.9rem; }

  /* ── Status banner ── */
  .banner {
    padding: 8px 32px;
    font-size: .82rem;
    text-align: center;
  }
  .banner.online  { background: #052e16; color: #86efac; }
  .banner.offline { background: #431407; color: #fcd34d; }

  /* ── Country grid ── */
  .country-grid {
    display: grid;
    grid-template-columns: repeat(3, 220px);
    gap: 16px;
    max-width: 760px;
    width: 100%;
    justify-content: center;
  }
  /* Center the last 2 cards in the 3-column grid */
  .country-card:nth-child(4) { grid-column: 1; }
  .country-card:nth-child(5) { grid-column: 2; }
  .country-card {
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 28px 16px;
    text-align: center;
    cursor: pointer;
    transition: background .15s, transform .1s, border-color .15s;
    font-size: .95rem;
    font-weight: 700;
  }
  .country-card:hover:not(.done) {
    background: var(--accent);
    border-color: var(--accent);
    transform: translateY(-3px);
  }
  .country-card .flag { font-size: 2.4rem; display:block; margin-bottom:8px; }
  .country-card .badge {
    display:inline-block;
    margin-top:10px;
    padding: 3px 12px;
    border-radius:99px;
    font-size:.75rem;
    font-weight:700;
  }
  .country-card .badge.challenge { background:var(--accent);  color:#fff; }
  .country-card .badge.done      { background:var(--success); color:#fff; }
  .country-card.done { opacity:.55; cursor:default; }

  /* ── Quiz screen ── */
  .quiz-wrap { max-width: 720px; width:100%; }
  .quiz-header {
    background: var(--header);
    border-radius: 12px 12px 0 0;
    padding: 16px 28px;
    display:flex; align-items:center; justify-content:space-between;
    border: 1px solid var(--border);
    border-bottom: none;
  }
  .quiz-header .left { font-size:1rem; font-weight:700; }
  .quiz-header .right { font-size: 2rem; font-weight:900; }
  .timer-bar { height: 6px; background: var(--border); border-radius:0; overflow:hidden; }
  .timer-bar-inner { height:100%; width:100%; background:var(--success);
                     transition: width 1s linear, background .5s; }
  .quiz-body {
    background: var(--bg);
    border: 1px solid var(--border);
    border-top: none;
    padding: 36px 40px 28px;
    border-radius: 0 0 12px 12px;
  }
  .question-text {
    font-size: 1.25rem;
    font-weight: 700;
    line-height: 1.6;
    margin-bottom: 28px;
    text-align: center;
  }
  .translated-badge {
    display:inline-flex; align-items:center; gap:4px;
    background:#1e3a5f; border:1px solid #3b82f6;
    border-radius:99px; padding:3px 10px;
    font-size:.72rem; color:#818cf8;
    margin-bottom:16px;
  }
  .choices { display:flex; flex-direction:column; gap:10px; }
  .choice-btn {
    padding: 14px 24px;
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 8px;
    color: var(--text);
    font-size: 1rem;
    font-family: inherit;
    cursor: pointer;
    text-align: left;
    transition: background .12s, border-color .12s;
  }
  .choice-btn:hover:not(:disabled) {
    background: var(--accent);
    border-color: var(--accent);
  }
  .choice-btn.correct  { background: var(--success)!important; border-color: var(--success)!important; color:#fff!important; }
  .choice-btn.wrong    { background: var(--danger)!important;  border-color: var(--danger)!important;  color:#fff!important; }
  .choice-btn:disabled { cursor: default; }

  /* result area */
  .result-area { margin-top:20px; }
  .result-label { font-size:1.1rem; font-weight:700; margin-bottom:6px; }
  .fact-text    { font-size:.85rem; color:var(--text-sec); line-height:1.5; }
  .advance-row  { display:flex; align-items:center; gap:16px; margin-top:20px; }
  .advance-row .countdown { font-size:.9rem; color:var(--accent); }

  /* ── Final screen ── */
  .final-wrap { max-width: 640px; width:100%; text-align:center; }
  .score-big { font-size:3rem; font-weight:900; color:var(--warning); }
  .score-sub { color:var(--text-sec); margin-bottom:32px; }
  table { width:100%; border-collapse:collapse; }
  th, td { padding: 10px 14px; text-align:center; font-size:.9rem; }
  th { color:var(--accent); background:var(--header); }
  tr:nth-child(even) td { background: rgba(255,255,255,.03); }
  .me { color:var(--accent); font-weight:700; }

  /* ── Loading ── */
  .loading-wrap { text-align:center; }
  .dots { font-size:2rem; color:var(--accent); letter-spacing:8px; }
  .loading-note { color:var(--text-sec); font-size:.85rem; margin-top:12px; line-height:1.6; }

  /* ── Misc ── */
  .flex-center { display:flex; align-items:center; justify-content:center; gap:12px; }
  footer {
    padding: 12px;
    text-align:center;
    font-size:.75rem;
    color:var(--text-sec);
    border-top:1px solid var(--border);
  }
  @media (max-width: 600px) {
    .country-grid { grid-template-columns: repeat(2,1fr); }
    .card { padding: 28px 20px; }
    .quiz-body { padding:24px 16px 20px; }
  }
</style>
</head>
<body>

<header>
  <h1>🌍 세계 지식 마스터 퀴즈</h1>
  <div class="meta" id="clock"></div>
</header>

<div id="banner" style="display:none"></div>

<main id="main-content">
  <!-- screens injected here by JS -->
</main>

<footer>Open Trivia DB + MyMemory 번역 API · 세션 내 중복 문제 자동 필터링</footer>

<script>
/* ============================================================
   클라이언트 상태
   ============================================================ */
const STATE = {
  userId:         "",
  quizData:       null,
  dataSource:     null,
  networkError:   null,
  completed:      [],
  totalScore:     0,
  currentCountry: "",
  quizPool:       [],
  step:           0,
  currentQ:       null,
  answered:       false,
  quizTimerId:    null,
  autoAdvId:      null,
  quizSeconds:    20,   // will be overwritten by boot() once CONFIG loads
  autoSeconds:    5,    // will be overwritten by boot() once CONFIG loads
};

/* ── Clock ── */
function updateClock() {
  const now = new Date();
  const pad = n => String(n).padStart(2,'0');
  document.getElementById("clock").textContent =
    `${now.getFullYear()}년 ${pad(now.getMonth()+1)}월 ${pad(now.getDate())}일  ${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`;
}
setInterval(updateClock, 1000);
updateClock();

/* ── API helpers ── */
async function api(path, body=null) {
  const opts = { method: body ? "POST" : "GET",
                 headers: {"Content-Type":"application/json"} };
  if (body) opts.body = JSON.stringify(body);
  try {
    const r = await fetch(path, opts);
    if (!r.ok) throw new Error("HTTP " + r.status);
    return r.json();
  } catch(e) {
    console.error("API error [" + path + "]:", e);
    throw e;
  }
}

/* ── Render helpers ── */
function main() { return document.getElementById("main-content"); }

function clearTimers() {
  clearInterval(STATE.quizTimerId);
  clearInterval(STATE.autoAdvId);
  STATE.quizTimerId = null;
  STATE.autoAdvId   = null;
}

function showBanner(msg, cls) {
  const b = document.getElementById("banner");
  b.className = `banner ${cls}`;
  b.textContent = msg;
  b.style.display = "block";
}
function hideBanner() { document.getElementById("banner").style.display="none"; }

/* ============================================================
   1. 로그인 화면
   ============================================================ */
function showLogin() {
  clearTimers(); hideBanner();
  main().innerHTML = `
  <div class="card" style="text-align:center">
    <h2 style="font-size:2rem;margin-bottom:4px">🌍</h2>
    <h2>세계 지식 마스터 퀴즈</h2>
    <p class="sub">5개국에 대한 문제를 풀고 마스터가 되세요!</p>
    <label for="nameInput">닉네임을 입력해 주세요</label>
    <input id="nameInput" type="text" placeholder="닉네임 (2자 이상)"
           maxlength="20" autocomplete="off">
    <div class="err" id="loginErr"></div>
    <button class="btn btn-primary btn-full" onclick="submitLogin()">시작하기 🚀</button>
    <p style="margin-top:16px;font-size:.78rem;color:#475569">
      인터넷 연결 시 실시간 영어 퀴즈를 자동 번역하여 제공합니다</p>
  </div>`;
  const inp = document.getElementById("nameInput");
  inp.focus();
  inp.addEventListener("keydown", e => { if(e.key==="Enter") submitLogin(); });
}

async function submitLogin() {
  const name = document.getElementById("nameInput").value.trim();
  const err  = document.getElementById("loginErr");
  if (!name)         { err.textContent="닉네임을 입력해야 합니다!"; return; }
  if (name.length<2) { err.textContent="닉네임은 2자 이상이어야 합니다."; return; }
  err.textContent = "";
  STATE.userId = name;
  showLoading();
  const data = await api("/api/start", {user_id: name});
  STATE.quizData     = data.quiz_data;
  STATE.dataSource   = data.source;
  STATE.networkError = data.error;
  STATE.completed    = [];
  STATE.totalScore   = 0;
  showMain();
}

/* ============================================================
   2. 로딩 화면
   ============================================================ */
function showLoading() {
  clearTimers(); hideBanner();
  main().innerHTML = `
  <div class="loading-wrap">
    <h2 style="margin-bottom:16px">퀴즈 데이터 불러오는 중...</h2>
    <div class="dots" id="dots">● ○ ○</div>
    <p class="loading-note">
      서버가 미리 준비한 퀴즈를 가져오는 중입니다.<br>
      잠시만 기다려 주세요 (보통 5초 이내).
    </p>
  </div>`;
  let f = 0;
  const frames = ["● ○ ○","○ ● ○","○ ○ ●","○ ● ○"];
  STATE.quizTimerId = setInterval(()=>{
    const el = document.getElementById("dots");
    if(el) el.textContent = frames[f++ % frames.length];
  }, 400);
}

/* ============================================================
   3. 나라 선택 화면
   ============================================================ */
function showMain() {
  clearTimers();
  if (STATE.dataSource === "network") {
    let msg = "✅  인터넷에서 나라별 영어 퀴즈를 가져와 한국어로 자동 번역했습니다!";
    if (STATE.networkError) msg += `  (일부 오류: ${STATE.networkError})`;
    showBanner(msg, "online");
  } else {
    showBanner(`⚠️  네트워크 오류 — 오프라인 데이터를 사용합니다.  (${STATE.networkError})`, "offline");
  }

  const total = Object.keys(STATE.quizData).length;
  main().innerHTML = `
  <div style="width:100%;display:flex;flex-direction:column;align-items:center">
    <div style="text-align:center;margin-bottom:28px">
      <p style="font-size:1.05rem;font-weight:700">
        ${STATE.userId} 님, 도전할 나라를 선택하세요!</p>
      <p style="font-size:.85rem;color:var(--text-sec);margin-top:4px">
        진행 ${STATE.completed.length}/${total} &nbsp;|&nbsp; 점수 ${STATE.totalScore}점</p>
    </div>
    <div class="country-grid" id="countryGrid"></div>
  </div>`;

  /* Hardcoded flag emoji map — avoids encoding issues with CONFIG fallback */
  const FLAG_MAP = {
    "대한민국": "🇰🇷",
    "미국":     "🇺🇸",
    "영국":     "🇬🇧",
    "일본":     "🇯🇵",
    "독일":     "🇩🇪",
  };

  const grid = document.getElementById("countryGrid");
  Object.entries(STATE.quizData).forEach(([name, qs])=>{
    const done  = STATE.completed.includes(name);
    const flag  = FLAG_MAP[name] || (CONFIG.countryMeta[name]||{}).flag || "🌐";
    const card  = document.createElement("div");
    card.className = "country-card" + (done?" done":"");
    card.innerHTML = `
      <span class="flag">${flag}</span>
      ${name}
      <span class="badge ${done?"done":"challenge"}">${done?"✔ 완료!":"도전!"}</span>`;
    if (!done) card.addEventListener("click", ()=> startQuiz(name));
    grid.appendChild(card);
  });
}

/* ============================================================
   4. 퀴즈 플로우
   ============================================================ */
async function startQuiz(country) {
  hideBanner();
  const data = await api("/api/quiz/start", {country});
  STATE.currentCountry = country;
  STATE.quizPool       = data.pool;
  STATE.step           = 0;
  loadQuestion();
}

function loadQuestion() {
  if (STATE.step < STATE.quizPool.length) {
    STATE.currentQ  = STATE.quizPool[STATE.step];
    STATE.answered  = false;
    STATE.step     += 1;
    renderQuiz();
  } else {
    finishCountry();
  }
}

function renderQuiz() {
  clearTimers();
  const q        = STATE.currentQ;
  const country  = STATE.currentCountry;
  const meta     = CONFIG.countryMeta;
  const flag     = (meta[country]||{}).flag || "🌐";
  const total    = STATE.quizPool.length;

  main().innerHTML = `
  <div class="quiz-wrap">
    <div class="quiz-header">
      <div class="left">${flag} ${country} — 문제 ${STATE.step} / ${total}</div>
      <div class="right" id="timerNum">CONFIG.timerSecs</div>
    </div>
    <div class="timer-bar"><div class="timer-bar-inner" id="timerBar"></div></div>
    <div class="quiz-body">
      ${q.translated ? `<div class="translated-badge">🌐 인터넷 문제 (자동 번역)</div>` : ''}
      <div class="question-text">${escHtml(q.question)}</div>
      <div class="choices" id="choices">
        ${q.choices.map((c,i)=>`
          <button class="choice-btn" id="cb${i}" onclick="checkAnswer(${i},'${escAttr(c)}')">
            ${escHtml(c)}
          </button>`).join("")}
      </div>
      <div class="result-area" id="resultArea"></div>
    </div>
  </div>`;

  /* 퀴즈 타이머 */
  STATE.quizSeconds = CONFIG.timerSecs;
  tickQuizTimer();
}

function tickQuizTimer() {
  if (STATE.answered) return;
  const secs = STATE.quizSeconds;
  const numEl = document.getElementById("timerNum");
  const barEl = document.getElementById("timerBar");
  if (!numEl || !barEl) return;

  numEl.textContent = secs;
  const pct = (secs / CONFIG.timerSecs) * 100;
  barEl.style.width = pct + "%";
  if (secs > 10)      { numEl.style.color="var(--success)"; barEl.style.background="var(--success)"; }
  else if (secs > 5)  { numEl.style.color="var(--warning)"; barEl.style.background="var(--warning)"; }
  else                { numEl.style.color="var(--danger)";  barEl.style.background="var(--danger)"; }

  if (secs <= 0) { checkAnswer(-1, null); return; }
  STATE.quizSeconds--;
  STATE.quizTimerId = setTimeout(tickQuizTimer, 1000);
}

function checkAnswer(idx, choice) {
  if (STATE.answered) return;
  STATE.answered = true;
  clearTimers();

  const q       = STATE.currentQ;
  const correct = q.answer;
  const isOk    = (choice === correct);

  if (isOk) STATE.totalScore++;

  /* 버튼 채색 */
  q.choices.forEach((c, i) => {
    const btn = document.getElementById(`cb${i}`);
    if (!btn) return;
    btn.disabled = true;
    if (c === correct) btn.classList.add("correct");
    else if (c === choice) btn.classList.add("wrong");
  });

  /* 결과 표시 */
  let resText, resColor;
  if      (!choice || idx < 0) { resText="⏰ 시간 초과!";                      resColor="var(--warning)"; }
  else if (isOk)               { resText="✅ 정답입니다!";                     resColor="var(--success)"; }
  else                         { resText=`❌ 틀렸습니다! 정답: ${correct}`; resColor="var(--danger)";  }

  document.getElementById("resultArea").innerHTML = `
    <div class="result-area">
      <div class="result-label" style="color:${resColor}">${resText}</div>
      <div class="fact-text">${escHtml(q.fact || "")}</div>
      <div class="advance-row">
        <span class="countdown" id="advCountdown">
          ${CONFIG.autoSecs}초 후 자동으로 다음 문제로 이동합니다...
        </span>
        <button class="btn btn-primary btn-sm" onclick="advanceNow()">다음 문제 →</button>
      </div>
    </div>`;

  /* 서버에 정답 여부 기록 (seen_question_keys 업데이트) */
  api("/api/quiz/answer", {
    country:  STATE.currentCountry,
    question: q.question,
    correct:  isOk,
  });

  /* 자동 이동 카운트다운 */
  STATE.autoSeconds = CONFIG.autoSecs;
  tickAutoAdvance();
}

function tickAutoAdvance() {
  const secs = STATE.autoSeconds;
  const el   = document.getElementById("advCountdown");
  if (!el) return;
  if (secs <= 0) { advanceNow(); return; }
  el.textContent = `${secs}초 후 자동으로 다음 문제로 이동합니다...`;
  STATE.autoSeconds--;
  STATE.autoAdvId = setTimeout(tickAutoAdvance, 1000);
}

function advanceNow() {
  clearTimers();
  loadQuestion();
}

/* ============================================================
   5. 나라 완료
   ============================================================ */
function finishCountry() {
  STATE.completed.push(STATE.currentCountry);
  if (STATE.completed.length >= Object.keys(STATE.quizData).length) {
    api("/api/score", {user_id: STATE.userId, score: STATE.totalScore})
      .then(data => showFinal(data.ranking));
  } else {
    showMain();
  }
}

/* ============================================================
   6. 최종 결과 화면
   ============================================================ */
function showFinal(ranking) {
  clearTimers(); hideBanner();
  const maxQ = Object.keys(STATE.quizData).length * CONFIG.questionsPerCountry;
  const medals = ["🥇 1위","🥈 2위","🥉 3위"];

  let rows = "";
  ranking.forEach((entry, i) => {
    const isMe = (entry.name === STATE.userId);
    rows += `<tr>
      <td>${i < 3 ? medals[i] : (i+1)+"위"}</td>
      <td class="${isMe?"me":""}">${escHtml(entry.name)}${isMe?" ← 나":""}</td>
      <td>${entry.score} / ${maxQ}점</td>
    </tr>`;
  });

  main().innerHTML = `
  <div class="final-wrap">
    <div style="font-size:1.4rem;font-weight:700;margin-bottom:8px">🎉 퀴즈 완료!</div>
    <div class="score-big">${STATE.totalScore}</div>
    <div class="score-sub">/ ${maxQ} 점</div>
    <table>
      <thead><tr><th>순위</th><th>닉네임</th><th>점수</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>
    <button class="btn btn-primary btn-full" style="max-width:300px;margin:32px auto 0"
            onclick="resetGame()">🔄 새로운 도전자로 시작</button>
  </div>`;
}

function resetGame() {
  api("/api/reset").then(()=> showLogin());
}

/* ── Escape helpers ── */
function escHtml(s) {
  return String(s||"").replace(/&/g,"&amp;").replace(/</g,"&lt;")
                      .replace(/>/g,"&gt;").replace(/"/g,"&quot;");
}
function escAttr(s) {
  return String(s||"").replace(/'/g,"\\'");
}

/* ── Boot ── */
async function boot() {
  try {
    const cfg = await api("/api/config");
    window.CONFIG = cfg;
    STATE.quizSeconds = cfg.timerSecs  || 20;
    STATE.autoSeconds = cfg.autoSecs   || 5;
  } catch(e) {
    window.CONFIG = {
      timerSecs: 20,
      autoSecs: 5,
      questionsPerCountry: 5,
      countryMeta: {
        "\ub300\ud55c\ubbfc\uad6d": {"flag": "\ud83c\uddf0\ud83c\uddf7"},
        "\ubbf8\uad6d":     {"flag": "\ud83c\uddfa\ud83c\uddf8"},
        "\uc601\uad6d":     {"flag": "\ud83c\uddec\ud83c\udde7"},
        "\uc77c\ubcf8":     {"flag": "\ud83c\uddef\ud83c\uddf5"},
        "\ub3c5\uc77c":     {"flag": "\ud83c\udde9\ud83c\uddea"}
      }
    };
    STATE.quizSeconds = 20;
    STATE.autoSeconds = 5;
  }
  showLogin();
}
boot();
</script>
</body>
</html>
"""

# ==============================================================================
# Flask 라우트
# ==============================================================================

@app.route("/")
def index():
    """메인 페이지"""
    return Response(HTML_TEMPLATE, mimetype="text/html; charset=utf-8")


@app.route("/api/config")
def api_config():
    """JS CONFIG 객체에 필요한 서버 상수를 반환합니다."""
    return jsonify({
        "timerSecs":          QUIZ_TIMER_SECONDS,
        "autoSecs":           AUTO_ADVANCE_SECONDS,
        "questionsPerCountry": QUESTIONS_PER_COUNTRY,
        "countryMeta":        COUNTRY_META,
    })


@app.route("/api/start", methods=["POST"])
def api_start():
    """
    로그인 + 퀴즈 데이터 로드.
    Open Trivia DB에서 영어 문제를 가져와 한국어로 번역합니다.
    세션을 초기화합니다.
    """
    data    = request.get_json(force=True)
    user_id = data.get("user_id", "").strip()

    # 세션 초기화
    session.clear()
    session["user_id"]              = user_id
    session["completed"]            = []
    session["total_score"]          = 0
    session["seen_question_keys"]   = {}

    # 퀴즈 데이터 로드 (번역 포함)
    quiz, source, error = fetch_and_translate_quiz()
    session["quiz_data"]     = quiz
    session["data_source"]   = source
    session["network_error"] = error

    return jsonify({
        "quiz_data": quiz,
        "source":    source,
        "error":     error,
    })


@app.route("/api/quiz/start", methods=["POST"])
def api_quiz_start():
    """
    특정 나라 퀴즈 시작.
    ★ 세션 내 이미 출제된 문제를 제외하고 새로운 풀을 반환합니다.
    """
    data    = request.get_json(force=True)
    country = data.get("country", "")

    pool = build_quiz_pool(country)
    session["quiz_pool"]        = pool
    session["current_country"]  = country
    session["step"]             = 0

    return jsonify({"pool": pool, "country": country})


@app.route("/api/quiz/answer", methods=["POST"])
def api_quiz_answer():
    """
    문제에 답했을 때 호출.
    ★ 해당 문제를 seen_question_keys에 기록해 중복 출제를 방지합니다.
    """
    data     = request.get_json(force=True)
    country  = data.get("country", "")
    question = data.get("question", "")
    correct  = data.get("correct", False)

    # 출제된 문제 기록
    mark_question_seen(country, question)

    # 점수 반영
    if correct:
        session["total_score"] = session.get("total_score", 0) + 1

    return jsonify({"ok": True})


@app.route("/api/score", methods=["POST"])
def api_score():
    """
    모든 나라 완료 후 최종 점수 저장 및 랭킹 반환.
    """
    data    = request.get_json(force=True)
    user_id = data.get("user_id", "")
    score   = data.get("score", 0)

    # 기존 동일 닉네임 제거 후 추가 (최고 점수 갱신)
    global RANKING_DATA
    RANKING_DATA = [r for r in RANKING_DATA if r["name"] != user_id]
    RANKING_DATA.append({"name": user_id, "score": score,
                          "at": datetime.now().strftime("%H:%M")})
    RANKING_DATA.sort(key=lambda x: x["score"], reverse=True)

    return jsonify({"ranking": RANKING_DATA})


@app.route("/api/reset", methods=["GET"])
def api_reset():
    """세션 리셋."""
    session.clear()
    return jsonify({"ok": True})


# ==============================================================================
if __name__ == "__main__":
    print("=" * 60)
    print("  🌍 세계 지식 마스터 퀴즈 웹 앱 시작")
    print("=" * 60)
    print("  브라우저에서 접속하세요: http://<서버IP>:5000")
    print()
    print("  기능:")
    print("  • Open Trivia DB 영어 퀴즈 자동 수집")
    print("  • Google Translate로 한국어 자동 번역 (MyMemory 폴백)")
    print("  • 세션 내 중복 문제 자동 필터링")
    print("  • 오프라인 폴백 퀴즈 내장")
    print()
    print("  종료: Ctrl+C")
    print("=" * 60)

    # Open the browser automatically after a short delay so Flask is ready
    def open_browser():
        time.sleep(1.2)
        webbrowser.open("http://127.0.0.1:5000")

    threading.Thread(target=open_browser, daemon=True).start()
    app.run(debug=False, host="0.0.0.0", port=5000)