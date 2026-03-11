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

# 2. 보안 수준 조정 어댑터
class LegacyAdapter(HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        context = create_urllib3_context(ciphers='DEFAULT@SECLEVEL=1')
        legacy_flag = getattr(ssl, 'OP_LEGACY_SERVER_CONNECT', 0x4)
        context.options |= legacy_flag
        kwargs['ssl_context'] = context
        return super(LegacyAdapter, self).init_poolmanager(*args, **kwargs)

app = Flask(__name__)

# 3. 식단 추출 보조 함수 (가독성을 위해 분리)
def extract_row_data(rows, row_idx, col_idx):
    try:
        tds = rows[row_idx].find_all("td")
        if len(tds) > col_idx:
            menu = tds[col_idx].get_text(strip=True, separator=" ")
            return menu if len(menu) > 1 else "미운영"
        return "미운영"
    except:
        return "미운영"

def get_jbnu_menu(target_date):
    try:
        url = f"https://likehome.jbnu.ac.kr/home/main/inner.php?sMenu=B7300&date={target_date}"
        headers = {"User-Agent": "Mozilla/5.0"}
        
        session = requests.Session()
        session.mount("https://", LegacyAdapter())
        
        response = session.get(url, headers=headers, verify=False, timeout=4)
        response.encoding = 'utf-8'
        
        soup = BeautifulSoup(response.text, "html.parser")
        tables = soup.find_all("table")
        
        if not tables:
            return f"📅 {target_date}\n식단 정보를 찾을 수 없습니다."

        rows = tables[0].find_all("tr")
        weekday = datetime.strptime(target_date, "%Y-%m-%d").weekday()
        
        if weekday > 4:
            return f"📅 {target_date}\n주말은 식단을 운영하지 않습니다."

        col_idx = weekday + 1
        breakfast = extract_row_data(rows, 1, col_idx)
        lunch = extract_row_data(rows, 2, col_idx)
        dinner = extract_row_data(rows, 3, col_idx)

        return f"🍴 전북대 식단 ({target_date})\n\n🍳 [아침]\n{breakfast}\n\n🍱 [점심]\n{lunch}\n\n🌙 [저녁]\n{dinner}"

    except Exception as e:
        return f"연결 실패: {str(e)}"

# 4. 엔드포인트 설정
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
            "template": {"outputs": [{"simpleText": {"text": f"오류: {str(e)}"}}]}
        })

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
