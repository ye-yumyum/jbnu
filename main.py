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

# 2. 보안 어댑터 설정
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
            return f"📅 {target_date}\n식단을 불러올 수 없습니다."

        rows = tables[0].find_all("tr")
        weekday = datetime.strptime(target_date, "%Y-%m-%d").weekday()
        
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
        
        # 한국 시간 오늘 날짜
        now = datetime.utcnow() + timedelta(hours=9)
        target_date_obj = now
        
        weekdays_ko = ["월", "화", "수", "목", "금", "토", "일"]
        day_found = False

        # 요일 찾기 루프
        for i, day_name in enumerate(weekdays_ko):
            if day_name in utterance:
                diff = i - now.weekday()
                # 이미 지난 요일이면 다음주로 계산
                if diff < 0:
                    diff += 7
                # "다음"이라는 단어가 있으면 한 주 더함 (이미 다음주일 경우 중복 방지)
                if "다음" in utterance and diff < 7:
                    diff += 7
                
                target_date_obj = now + timedelta(days=diff)
                day_found = True
                break

        # 요일이 없을 때만 오늘/내일/모레 판별
        if not day_found:
            if "내일" in utterance:
                target_date_obj = now + timedelta(days=1)
            elif "모레" in utterance:
                target_date_obj = now + timedelta(days=2)
            # "오늘"이거나 아무것도 없으면 기본값(now) 유지

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

# 5. 실행부 (Render 포트 바인딩 최적화)
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
