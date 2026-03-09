from flask import Flask, request, jsonify
import urllib.request
import ssl
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import re
import json

app = Flask(__name__)

# 이스터 에그: 친구 이름 입력 시 정해진 답
EASTER_EGGS = {
    "지유림": "자유림",
    "구민영": "제주도좋다",
    "강지은": "멍뭉이",
    "박지영": "바퀴벌레 이젠 무섭지않아.",
}

def get_jbnu_menu(target_date):
    # 한국 시간(KST) 기준 오늘 날짜 설정
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

    # 전북대 익산캠퍼스(후생관) 식단표 URL
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
        weekday = date_obj.weekday()  # 0:월, 1:화, 2:수, 3:목, 4:금

        # 주말 처리 (토, 일)
        if weekday > 4:
            return f"📅 {target_date}\n주말은 식단을 운영하지 않습니다."

        # 표 구조: 0=일, 1=월, 2=화, 3=수, 4=목, 5=금
        col_idx = weekday + 1

        def extract_menu(row_idx, target_col):
            try:
                tds = rows[row_idx].find_all('td')
                if len(tds) > target_col:
                    menu_text = tds[target_col].get_text(strip=True, separator=' ')
                    if not menu_text or len(menu_text) < 2:
                        return "미운영"
                    return menu_text
                return "미운영"
            except:
                return "미운영"

        breakfast = extract_menu(1, col_idx)
        lunch = extract_menu(2, col_idx)
        dinner = extract_menu(3, col_idx)

        return (f"📅 날짜: {target_date}\n\n🍳 [아침]\n{breakfast}\n\n"
                f"🍱 [점심]\n{lunch}\n\n🌙 [저녁]\n{dinner}")
    except Exception as e:
        return f"서버 연결 오류: 잠시 후 다시 시도해 주세요."
@app.route('/health', methods=['GET'])
def health():
    return "OK", 200
@app.route('/keyboard', methods=['POST'])
def chat_response():
    try:
        data = request.get_json()
        utterance = data.get('userRequest', {}).get('utterance', '')
        utterance_stripped = utterance.replace(" ", "")

        # 이스터 에그: 친구 이름이면 정해진 답만 반환
        if utterance_stripped in EASTER_EGGS:
            return jsonify({
                "version": "2.0",
                "template": {
                    "outputs": [{
                        "simpleText": {"text": EASTER_EGGS[utterance_stripped]}
                    }]
                }
            })

        utterance = utterance_stripped
        user_date = None
        now = datetime.utcnow() + timedelta(hours=9)

        # 1. 카카오 파라미터 확인
        params = data.get('action', {}).get('params', {})
        raw_date = params.get('date') or params.get('sys.date')
        if raw_date and '{{' not in str(raw_date):
            if isinstance(raw_date, str) and '{' in raw_date:
                user_date = json.loads(raw_date).get('date')
            else:
                user_date = raw_date

        # 2. [요일 및 숫자 강제 판독기]
        if not user_date or '{{' in str(user_date):
            # (1) "2025년 3월 13일" 형태
            match_full = re.search(r'(\d{4})년(\d{1,2})월(\d{1,2})일', utterance)
            if match_full:
                year = int(match_full.group(1))
                month = int(match_full.group(2))
                day = int(match_full.group(3))
                try:
                    user_date = datetime(year, month, day).strftime("%Y-%m-%d")
                except ValueError:
                    user_date = now.strftime("%Y-%m-%d")

            # (2) "3월 13일" 형태 (년도는 현재 연도)
            if not user_date:
                match_md = re.search(r'(\d{1,2})월(\d{1,2})일', utterance)
                if match_md:
                    year = now.year
                    month = int(match_md.group(1))
                    day = int(match_md.group(2))
                    try:
                        user_date = datetime(year, month, day).strftime("%Y-%m-%d")
                    except ValueError:
                        user_date = now.strftime("%Y-%m-%d")

            # (3) "13일" 형태 (현재 연/월에 일만 교체)
            if not user_date:
                match_d = re.search(r'(\d{1,2})일', utterance)
                if match_d:
                    day = int(match_d.group(1))
                    year = now.year
                    month = now.month
                    try:
                        user_date = datetime(year, month, day).strftime("%Y-%m-%d")
                    except ValueError:
                        user_date = now.strftime("%Y-%m-%d")

            # (4) "월요일/화요일/수요일/목요일/금요일" 요일 판독
            if not user_date:
                weekday_match = re.search(r'(월|화|수|목|금)요일', utterance)
                if weekday_match:
                    days_map = {"월": 0, "화": 1, "수": 2, "목": 3, "금": 4}
                    idx = days_map[weekday_match.group(1)]
                    diff = idx - now.weekday()
                    if diff < 0:
                        diff += 7
                    user_date = (now + timedelta(days=diff)).strftime("%Y-%m-%d")

            # (5) 내일 / 모레
            if not user_date and "내일" in utterance:
                user_date = (now + timedelta(days=1)).strftime("%Y-%m-%d")
            elif not user_date and "모레" in utterance:
                user_date = (now + timedelta(days=2)).strftime("%Y-%m-%d")

        menu = get_jbnu_menu(user_date)
        return jsonify({
            "version": "2.0",
            "template": {
                "outputs": [{
                    "simpleText": {
                        "text": f"🍴 전북대 식단 안내\n\n{menu}"
                    }
                }]
            }
        })
    except:
        return jsonify({
            "version": "2.0",
            "template": {
                "outputs": [{
                    "simpleText": {
                        "text": "처리 중 오류가 발생했습니다."
                    }
                }]
            }
        })

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8080)
    