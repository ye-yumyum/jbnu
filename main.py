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
        
        if not tables:
            return f"📅 {target_date}\n식단표를 찾을 수 없습니다."

        rows = tables[0].find_all("tr")
        # 요일 숫자 (0:월 ~ 6:일)
        weekday = datetime.strptime(target_date, "%Y-%m-%d").weekday()
        col_idx = weekday + 1 # 식단표 테이블의 열 인덱스
        
        def extract(row_idx):
            try:
                tds = rows[row_idx].find_all("td")
                if len(tds) > col_idx:
                    menu = tds[col_idx].get_text(strip=True, separator=" ")
                    return menu if len(menu) > 1 else "미운영"
                return "미운영"
            except:
                return "미운영"

        # 주말 체크 로직 삭제 -> 그냥 긁어서 보여줌
        return f"🍴 전북대 식단 ({target_date})\n\n🍳 [아침]\n{extract(1)}\n\n🍱 [점심]\n{extract(2)}\n\n🌙 [저녁]\n{extract(3)}"
    except Exception as e:
        return f"연결 실패: {str(e)}"

@app.route("/health", methods=["GET"])
@app.route("/keep-alive", methods=["GET"])
def health():
    return "OK", 200

@app.route("/keyboard", methods=["POST"])
def chat_response():
    try:
        content = request.get_json()
        utterance = content.get("userRequest", {}).get("utterance", "")
        now = datetime.utcnow() + timedelta(hours=9)
        target_date_obj = now

        # 날짜 판별 로직 (순서: 오늘/내일/모레 -> 요일)
        if "모레" in utterance:
            target_date_obj = now + timedelta(days=2)
        elif "내일" in utterance:
            target_date_obj = now + timedelta(days=1)
        elif "오늘" in utterance:
            target_date_obj = now
        else:
            weekdays_ko = ["월", "화", "수", "목", "금", "토", "일"]
            for i, day_name in enumerate(weekdays_ko):
                if (day_name + "요일") in utterance or (day_name in utterance and len(utterance) < 5):
                    diff = i - now.weekday()
                    if diff < 0: diff += 7
                    if "다음" in utterance and diff < 7: diff += 7
                    target_date_obj = now + timedelta(days=diff)
                    break

        target_date = target_date_obj.strftime("%Y-%m-%d")
        return jsonify({
            "version": "2.0",
            "template": {"outputs": [{"simpleText": {"text": get_jbnu_menu(target_date)}}]}
        })
    except Exception as e:
        return jsonify({
            "version": "2.0",
            "template": {"outputs": [{"simpleText": {"text": f"오류 발생: {str(e)}"}}]}
        })

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
