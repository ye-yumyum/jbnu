from flask import Flask, request, jsonify
from datetime import datetime, timedelta
import os
import requests
from bs4 import BeautifulSoup
import urllib3
import ssl
from requests.adapters import HTTPAdapter
from urllib3.util.ssl_ import create_urllib3_context

# 1. SSL 경고 끄기
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 2. 보안 충돌을 해결한 레거시 어댑터
class LegacyAdapter(HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        # 보안 수준을 낮춘 컨텍스트 생성
        context = create_urllib3_context(ciphers='DEFAULT@SECLEVEL=1')
        
        # [핵심] 에러 원인 해결: 보안을 끌 때는 아래 두 설정을 모두 꺼야 합니다.
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        
        # 레거시 서버 연결 허용 옵션
        legacy_flag = getattr(ssl, 'OP_LEGACY_SERVER_CONNECT', 0x4)
        context.options |= legacy_flag
        
        kwargs['ssl_context'] = context
        return super(LegacyAdapter, self).init_poolmanager(*args, **kwargs)

app = Flask(__name__)

def get_jbnu_menu(target_date):
    try:
        # 학교 서버 주소 (https 유지)
        url = f"https://likehome.jbnu.ac.kr/home/main/inner.php?sMenu=B7300&date={target_date}"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        
        # 세션 생성 및 어댑터 장착
        session = requests.Session()
        session.mount("https://", LegacyAdapter())
        
        # 타임아웃을 4.5초로 설정 (카톡 5초 컷 방지)
        response = session.get(url, headers=headers, verify=False, timeout=4.5)
        response.encoding = 'utf-8'
        
        soup = BeautifulSoup(response.text, "html.parser")
        tables = soup.find_all("table")
        
        if not tables:
            return f"📅 {target_date}\n식단을 불러올 수 없습니다. (학교 사이트 반응 없음)"

        rows = tables[0].find_all("tr")
        weekday = datetime.strptime(target_date, "%Y-%m-%d").weekday()
        
        if weekday > 4:
            return f"📅 {target_date}\n주말은 식단을 운영하지 않습니다."

        col_idx = weekday + 1
        
        def extract(row_idx):
            try:
                tds = rows[row_idx].find_all("td")
                return tds[col_idx].get_text(strip=True, separator=" ") if len(tds) > col_idx else "미운영"
            except: return "미운영"

        breakfast = extract(1)
        lunch = extract(2)
        dinner = extract(3)

        return f"🍴 전북대 식단 ({target_date})\n\n🍳 [아침]\n{breakfast}\n\n🍱 [점심]\n{lunch}\n\n🌙 [저녁]\n{dinner}"

    except Exception as e:
        # 에러 발생 시 카톡에 에러 메시지 출력
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
        target_date = now.strftime("%Y-%m-%d")

        if "내일" in utterance:
            target_date = (now + timedelta(days=1)).strftime("%Y-%m-%d")
        elif "모레" in utterance:
            target_date = (now + timedelta(days=2)).strftime("%Y-%m-%d")

        menu_text = get_jbnu_menu(target_date)
        return jsonify({
            "version": "2.0",
            "template": {"outputs": [{"simpleText": {"text": menu_text}}]}
        })
    except:
        return jsonify({
            "version": "2.0",
            "template": {"outputs": [{"simpleText": {"text": "잠시 후 다시 시도해 주세요."}}]}
        })

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
