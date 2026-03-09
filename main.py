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
                    idx = days_map[weekday_match.group(1)]
                    diff = idx - now.weekday()
                    if diff < 0: diff += 7
                    user_date = (now + timedelta(days=diff)).strftime("%Y-%m-%d")

            if not user_date and "내일" in utterance_stripped:
                user_date = (now + timedelta(days=1)).strftime("%Y-%m-%d")
            elif not user_date and "모레" in utterance_stripped:
                user_date = (now + timedelta(days=2)).strftime("%Y-%m-%d")

        # 식단 가져오기 실행
        menu = get_jbnu_menu(user_date)
        return jsonify({
            "version": "2.0",
            "template": {
                "outputs": [{
                    "simpleText": {"text": f"🍴 전북대 식단 안내\n\n{menu}"}
                }]
            }
        })
        
    except Exception as e:
        return jsonify({
            "version": "2.0",
            "template": {"outputs": [{"simpleText": {"text": "처리 중 오류가 발생했습니다."}}]}
        })

def get_jbnu_menu(target_date):
    korea_now = datetime.utcnow() + timedelta(hours=9)
    today_str = korea_now.strftime("%Y-%m-%d")

    if not target_date or any(x in str(target_date) for x in ['{{', 'sys', 'none']):
        target_date = today_str

    target_date = str(target_date).split('T')[0]
    try:
        date_obj = datetime.strptime(target_date, "%Y-%m-%d")
    except:
        target_date = today_str
        date_obj = datetime.strptime(target_date, "%Y-%m-%d")

    url = f"https://likehome.jbnu.ac.kr/home/main/inner.php?sMenu=B7300&date={target_date}"
    context = ssl._create_unverified_context()
    context.set_ciphers('DEFAULT@SECLEVEL=1')

    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, context=context, timeout=10) as response:
            html = response.read().decode('utf-8')
        soup = BeautifulSoup(html, 'html.parser')
        tables = soup.find_all('table')
        if not tables:
            return f"📅 {target_date}\n식단표를 찾을 수 없습니다."

        rows = tables[0].find_all('tr')
        weekday = date_obj.weekday()
        if weekday > 4:
            return f"📅 {target_date}\n주말은 식단을 운영하지 않습니다."

        col_idx = weekday + 1

        def extract_menu(row_idx, target_col):
            try:
                tds = rows[row_idx].find_all('td')
                if len(tds) > target_col:
                    menu_text = tds[target_col].get_text(strip=True, separator=' ')
                    if not menu_text or len(menu_text) < 2: return "미운영"
                    return menu_text
                return "미운영"
            except: return "미운영"

        breakfast = extract_menu(1, col_idx)
        lunch = extract_menu(2, col_idx)
        dinner = extract_menu(3, col_idx)

        return (f"📅 날짜: {target_date}\n\n🍳 [아침]\n{breakfast}\n\n"
                f"🍱 [점심]\n{lunch}\n\n🌙 [저녁]\n{dinner}")
    except:
        return f"서버 연결 오류: 잠시 후 다시 시도해 주세요."

@app.route('/health', methods=['GET'])
@app.route('/', methods=['GET']) # 렌더의 Health Check를 위한 경로 추가
def health():
    return "OK", 200

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8080)
