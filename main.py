from flask import Flask, request, jsonify
from datetime import datetime, timedelta
import os
import requests
from bs4 import BeautifulSoup
import urllib3
from requests.adapters import HTTPAdapter
from urllib3.util.ssl_ import create_urllib3_context

# SSL 경고 제거
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- 보안 수준을 강제로 낮추는 설정 (핵심) ---
class LegacyAdapter(HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        context = create_urllib3_context()
        # 최근 서버에서 금지된 오래된 보안 방식(TLS 1.0 등)을 허용합니다.
        context.set_ciphers('DEFAULT@SECURITY=1')
        kwargs['ssl_context'] = context
        return super(LegacyAdapter, self).init_poolmanager(*args, **kwargs)

app = Flask(__name__)

@app.route("/health", methods=["GET"])
@app.route("/keep-alive", methods=["GET"])
def health():
    return "OK", 200

def get_jbnu_menu(target_date):
    try:
        url = f"https://likehome.jbnu.ac.kr/home/main/inner.php?sMenu=B7300&date={target_date}"
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        
        # 세션을 만들고 보안을 낮춘 어댑터 연결
        session = requests.Session()
        session.mount("https://", LegacyAdapter())
        
        response = session.get(url, headers=headers, verify=False, timeout=10)
        response.encoding = 'utf-8'
        html = response.text

        soup = BeautifulSoup(html, "html.parser")
        tables = soup.find_all("table")
        
        if not tables:
            return f"📅 {target_date}\n식단표를 찾을 수 없습니다."

        rows = tables[0].find_all("tr")
        date_obj = datetime.strptime(target_date, "%Y-%m-%d")
        weekday = date_obj.weekday()
        
        if weekday > 4:
            return f"📅 {target_date}\n주말은 식단을 운영하지 않습니다."

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

        breakfast = extract(1)
        lunch = extract(2)
        dinner = extract(3)

        return f"🍴 전북대 식단 ({target_date})\n\n🍳 [아침]\n{breakfast}\n\n🍱 [점심]\n{lunch}\n\n🌙 [저녁]\n{dinner}"

    except Exception as e:
        return f"학교 서버 보안 문제로 접속 실패: {str(e)}"

@app.route("/keyboard", methods=["POST"])
def chat_response():
    try:
        content = request.get_json()
        utterance = content.get("userRequest", {}).get("utterance", "")
        
        now = datetime.utcnow() + timedelta(hours=9)
        target_date = now.strftime("%Y-%m-%d")

        if "내일" in utterance:
            target_date = (now + timedelta(days=1)).strftime("%Y-%m-%d")
        elif "모레" in utterance:
            target_date = (now + timedelta(days=2)).strftime("%Y-%m-%d")

        result_text = get_jbnu_menu(target_date)

        return jsonify({
            "version": "2.0",
            "template": {"outputs": [{"simpleText": {"text": result_text}}]}
        })
    except Exception as e:
        return jsonify({
            "version": "2.0",
            "template": {"outputs": [{"simpleText": {"text": f"오류 발생: {str(e)}"}}] }
        })

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
