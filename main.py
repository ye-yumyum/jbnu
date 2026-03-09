from flask import Flask, request, jsonify
import urllib.request
import ssl
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import re
import json

app = Flask(__name__)

# 1. 이스터 에그 정의
EASTER_EGGS = {
    "지유림": "퀸.",
    "구민영": "제주도좋다",
    "강지은": "260312 국가시험 합격",
    "임예린": "감히 입에 올릴 존합이 아니다!",
    "박지영": "바퀴벌레. 이젠 무섭지않아.",
}

# [주의] 함수를 하나로 합쳤습니다. 중복된 @app.route('/keyboard')는 삭제하세요!
@app.route('/keyboard', methods=['POST'])
def chat_response():
    try:
        data = request.get_json()
        utterance = data.get('userRequest', {}).get('utterance', '')
        utterance_stripped = utterance.replace(" ", "")

        # [1순위] 이스터 에그 검사: 문장에 이름이 '포함'되어 있는지 확인
        for name, message in EASTER_EGGS.items():
            if name in utterance_stripped:  # '지유림'이 '지유림이누구야'에 들어있는지 확인
                return jsonify({
                    "version": "2.0",
                    "template": {
                        "outputs": [{"simpleText": {"text": message}}]
                    }
                })

        # [2순위] 이스터 에그가 아닐 때만 식단 로직 실행
        user_date = None
        now = datetime.utcnow() + timedelta(hours=9)

        # 카카오 파라미터 확인
        params = data.get('action', {}).get('params', {})
        raw_date = params.get('date') or params.get('sys.date')
        
        if raw_date and '{{' not in str(raw_date):
            if isinstance(raw_date, str) and '{' in raw_date:
                user_date = json.loads(raw_date).get('date')
            else:
                user_date = raw_date

        # 요일 및 숫자 강제 판독기 (기존 로직 유지)
        if not user_date or '{{' in str(user_date):
            match_full = re.search(r'(\d{4})년(\d{1,2})월(\d{1,2})일', utterance_stripped)
            if match_full:
                year, month, day = map(int, match_full.groups())
                try: user_date = datetime(year, month, day).strftime("%Y-%m-%d")
                except: user_date = now.strftime("%Y-%m-%d")

            if not user_date:
                match_md = re.search(r'(\d{1,2})월(\d{1,2})일', utterance_stripped)
                if match_md:
                    month, day = map(int, match_md.groups())
                    try: user_date = datetime(now.year, month, day).strftime("%Y-%m-%d")
                    except: user_date = now.strftime("%Y-%m-%d")

            if not user_date:
                match_d = re.search(r'(\d{1,2})일', utterance_stripped)
                if match_d:
                    day = int(match_d.group(1))
                    try: user_date = datetime(now.year, now.month, day).strftime("%Y-%m-%d")
                    except: user_date = now.strftime("%Y-%m-%d")

            if not user_date:
                weekday_match = re.search(r'(월|화|수|목|금)요일', utterance_stripped)
                if weekday_match:
                    days_map = {"월": 0, "화": 1, "수": 2, "목": 3, "금": 4}
                    idx = days_map
