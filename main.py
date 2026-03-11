from flask import Flask, request, jsonify
from datetime import datetime, timedelta
import os
import requests
from bs4 import BeautifulSoup
import urllib3
import ssl
from requests.adapters import HTTPAdapter
from urllib3.util.ssl_ import create_urllib3_context

# 1. SSL 경고 무시
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 2. 보안 어댑터 설정 (학교 서버 전용)
class LegacyAdapter(HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        context = create_urllib3_context(ciphers='DEFAULT@SECLEVEL=1')
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        legacy_flag = getattr(ssl, 'OP_LEGACY_SERVER_CONNECT', 0x4)
        context.options |= legacy_flag
        kwargs['ssl_context'] = context
        return super(LegacyAdapter, self).init_poolmanager(*args, **kwargs)

app = Flask(__name__)

# 3. 식단 가져오기 함수
def get_jbnu_menu(target_date):
    try:
        url = f"https://likehome.jbnu.ac.kr/home/main/inner.php?sMenu=B7300&date={target_date}"
        headers = {"User-Agent": "Mozilla/5.0"}
        session = requests.Session()
        session.mount("https://", LegacyAdapter())
        
        response = session.get(url, headers=headers, verify=False, timeout=4.5)
        response.encoding = 'utf-8'
        soup = BeautifulSoup(response.text, "html.parser")
        tables = soup.find_all("table")
        
        if not tables:
            return f"📅 {target_date}\n식단을 불러올 수 없습니다. (학교 서버 확인 필요)"

        rows = tables[0].find_all("tr")
        # 날짜 문자열에서 요일 숫자 추출 (0:월 ~ 6:일)
        weekday = datetime.strptime(target_date, "%Y-%m-%d").weekday()
        
        # 주말(토, 일) 처리
        if weekday > 4:
            return f"📅 {target_date}\n주말은 식단을 운영하지 않습니다. 🛌"

        col_idx = weekday + 1
        
        def extract(row_idx):
            try:
                tds = rows[row_idx].find_all("td")
                if len(tds) > col_idx:
                    menu = tds[col_idx].get_text(strip=True, separator=" ")
                    return menu if len(menu) > 1 else "미운영"
                return "미운영"
            except:
                return "미운영"

        return f"🍴 전북대 식단 ({target_date})\n\n🍳 [아침]\n{extract(1)}\n\n🍱 [점심]\n{extract(2)}\n\n🌙 [저녁]\n{extract(3)}"
    except Exception as e:
        return f"연결 실패: {str(e)}"

# 4. 엔드포인트
@app.route("/health", methods=["GET"])
@app.route("/keep-alive", methods=["GET"])
def health():
    return "OK", 200

@app.route("/keyboard", methods=["POST"])
def chat_response():
    try:
        content = request.get_json()
        utterance = content.get("userRequest", {}).get("utterance", "")
        
        # 한국 시간 기준 오늘 날짜 설정
        now = datetime.utcnow() + timedelta(hours=9)
        target_date_obj = now

        # --- 날짜 인식 로직 (버그 수정 버전) ---
        
        # A. 우선순위 1: '모레', '내일', '오늘'을 먼저 체크 (순서 중요!)
        if "모레" in utterance:
            target_date_obj = now + timedelta(days=2)
        elif "내일" in utterance:
            target_date_obj = now + timedelta(days=1)
        elif "오늘" in utterance:
            target_date_obj = now
        else:
            # B. 우선순위 2: 특정 요일이 포함되어 있는지 확인
            weekdays_ko = ["월", "화", "수", "목", "금", "토", "일"]
            for i, day_name in enumerate(weekdays_ko):
                # '일' 글자 하나만 있는 경우 '내일'과 겹치지 않게 '요일'까지 확인하거나 '일' 제외 로직 적용
                if (day_name + "요일") in utterance or (day_name in utterance and len(utterance) < 5):
                    diff = i - now.weekday()
                    if diff < 0: # 이미 지난 요일이면 다음 주로
                        diff += 7
                    if "다음" in utterance and diff < 7:
                        diff += 7
                    target_date_obj = now + timedelta(days=diff)
                    break

        target_date = target_date_obj.strftime("%Y-%m-%d")
        menu_text = get_jbnu_menu(target_date)
        
        return jsonify({
            "version": "2.0",
            "template": {"outputs": [{"simpleText": {"text": menu_text}}]}
        })
    except Exception as e:
        return jsonify({
            "version": "2.0",
            "template": {"outputs": [{"simpleText": {"text": f"오류 발생: {str(e)}"}}]}
        })

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
