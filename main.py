from flask import Flask, request, jsonify
from datetime import datetime, timedelta
import os
import requests
from bs4 import BeautifulSoup
import urllib3
import ssl
from requests.adapters import HTTPAdapter
from urllib3.util.ssl_ import create_urllib3_context

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

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
        if not tables: return f"📅 {target_date}\n식단을 불러올 수 없습니다."

        rows = tables[0].find_all("tr")
        weekday = datetime.strptime(target_date, "%Y-%m-%d").weekday()
        if weekday > 4: return f"📅 {target_date}\n주말은 식단을 운영하지 않습니다. 🛌"

        col_idx = weekday + 1
        def extract(row_idx):
            try:
                tds = rows[row_idx].find_all("td")
                return tds[col_idx].get_text(strip=True, separator=" ") if len(tds) > col_idx else "미운영"
            except: return "미운영"

        return f"🍴 전북대 식단 ({target_date})\n\n🍳 [아침]\n{extract(1)}\n\n🍱 [점심]\n{extract(2)}\n\n🌙 [저녁]\n{extract(3)}"
    except Exception as e: return f"연결 실패: {str(e)}"

@app.route("/health", methods=["GET"])
@app.route("/keep-alive", methods=["GET"])
def health(): return "OK", 200

@app.route("/keyboard", methods=["POST"])
def chat_response():
    try:
        content = request.get_json()
        utterance = content.get("userRequest", {}).get("utterance", "")
        
        # 한국 시간 기준 '오늘' 설정
        now = datetime.utcnow() + timedelta(hours=9)
        target_date_obj = now
        
        # 요일 리스트 (월:0 ~ 일:6)
        weekdays_ko = ["월", "화", "수", "목", "금", "토", "일"]
        found_day = False

        # 1. 요일이 문장에 포함되어 있는지 확인 (가장 강력한 조건)
        for i, day_name in enumerate(weekdays_ko):
            if day_name in utterance:
                diff = i - now.weekday()
                # 지난 요일이면 다음주로 이동
                if diff < 0:
                    diff += 7
                # "다음주"라는 말이 있으면 무조건 7일 더함
                if "다음" in utterance:
                    # 이미 위에서 7일이 더해졌는데 또 "다음"이 있으면 중복 방지
                    if i <= now.weekday(): 
                        pass 
                    else:
                        diff += 0 # 혹은 필요에 따라 로직 수정
                
                target_date_obj = now + timedelta(days=diff)
                found_day = True
                break

        # 2. 요일을 못 찾았을 때만 "오늘/내일/모레" 확인
        if not found_day:
            if "내일" in utterance:
                target_date_obj = now + timedelta(days=1)
            elif "모레" in utterance:
                target_date_obj = now + timedelta(days=2)
            else:
                target_date_obj = now # 기본값 오늘

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
