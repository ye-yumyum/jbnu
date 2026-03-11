from flask import Flask, request, jsonify
import urllib.request
import ssl
from datetime import datetime, timedelta
import os
from bs4 import BeautifulSoup

app = Flask(__name__)

# --- 깨우기 경로 ---
@app.route("/health", methods=["GET"])
@app.route("/keep-alive", methods=["GET"])
def health():
    return "OK", 200

# --- 식단 크롤링 함수 ---
def get_jbnu_menu(target_date):
    try:
        # SSL 설정
        context = ssl._create_unverified_context()
        url = f"https://likehome.jbnu.ac.kr/home/main/inner.php?sMenu=B7300&date={target_date}"
        
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, context=context, timeout=5) as response:
            html = response.read().decode("utf-8", errors="ignore")

        soup = BeautifulSoup(html, "html.parser")
        tables = soup.find_all("table")
        
        if not tables:
            return f"📅 {target_date}\n해당 날짜의 식단표 테이블을 찾을 수 없습니다."

        rows = tables[0].find_all("tr")
        
        # 요일 계산 (0:월, 1:화, ..., 4:금, 5:토, 6:일)
        date_obj = datetime.strptime(target_date, "%Y-%m-%d")
        weekday = date_obj.weekday()
        
        if weekday > 4:
            return f"📅 {target_date}\n주말은 식단을 운영하지 않습니다."

        col_idx = weekday + 1 # 월요일이 1번 열
        
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

        return f"📅 날짜: {target_date}\n\n🍳 [아침]\n{breakfast}\n\n🍱 [점심]\n{lunch}\n\n🌙 [저녁]\n{dinner}"

    except Exception as e:
        return f"식단 정보를 가져오는 중 오류 발생: {str(e)}"

# --- 카카오톡 응답 로직 ---
@app.route("/keyboard", methods=["POST"])
def chat_response():
    try:
        content = request.get_json()
        # 카카오톡에서 보낸 발화(말) 추출
        utterance = content.get("userRequest", {}).get("utterance", "")
        
        # 기본 날짜 설정 (한국 시간 오늘)
        now = datetime.utcnow() + timedelta(hours=9)
        target_date = now.strftime("%Y-%m-%d")

        # 간단한 날짜 판별
        if "내일" in utterance:
            target_date = (now + timedelta(days=1)).strftime("%Y-%m-%d")
        elif "모레" in utterance:
            target_date = (now + timedelta(days=2)).strftime("%Y-%m-%d")

        result_text = get_jbnu_menu(target_date)

        return jsonify({
            "version": "2.0",
            "template": {
                "outputs": [{"simpleText": {"text": result_text}}]
            }
        })
    except Exception as e:
        return jsonify({
            "version": "2.0",
            "template": {
                "outputs": [{"simpleText": {"text": f"서버 내부 오류가 발생했습니다: {str(e)}"}}]
            }
        })

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
