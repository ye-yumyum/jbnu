from flask import Flask, request, jsonify
import urllib.request
import ssl
from datetime import datetime, timedelta
import re
import json
import os
import time
from bs4 import BeautifulSoup

app = Flask(__name__)

@app.route("/health", methods=["GET"])
def health():
    return "OK", 200

MENU_CACHE = {}
MENU_CACHE_TTL_SECONDS = 300
MENU_ERROR_CACHE_TTL_SECONDS = 30

def _cache_get(key: str):
    item = MENU_CACHE.get(key)
    if not item or item["expires_at"] < time.time():
        MENU_CACHE.pop(key, None)
        return None
    return item["value"]

def _cache_set(key: str, value: str, ttl_seconds: int):
    MENU_CACHE[key] = {"expires_at": time.time() + ttl_seconds, "value": value}

def get_jbnu_menu(target_date):
    korea_now = datetime.utcnow() + timedelta(hours=9)
    today_str = korea_now.strftime("%Y-%m-%d")

    if not target_date or any(x in str(target_date).lower() for x in ["{{", "sys", "none"]):
        target_date = today_str

    target_date = str(target_date).split("T")[0]
    try:
        date_obj = datetime.strptime(target_date, "%Y-%m-%d")
    except:
        target_date = today_str
        date_obj = datetime.strptime(target_date, "%Y-%m-%d")

    cached = _cache_get(target_date)
    if cached is not None:
        return cached

    url = f"https://likehome.jbnu.ac.kr/home/main/inner.php?sMenu=B7300&date={target_date}"
    context = ssl._create_unverified_context()
    context.set_ciphers("DEFAULT@SECURITY=1")

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        # 카카오 스킬 타임아웃 내 응답을 위해 짧게 유지
        with urllib.request.urlopen(req, context=context, timeout=2) as response:
            html = response.read().decode("utf-8", errors="ignore")

        soup = BeautifulSoup(html, "html.parser")
        tables = soup.find_all("table")
        if not tables:
            result = f"📅 {target_date}\n식단표를 찾을 수 없습니다."
            _cache_set(target_date, result, MENU_ERROR_CACHE_TTL_SECONDS)
            return result

        rows = tables[0].find_all("tr")
        weekday = date_obj.weekday()
        if weekday > 4:
            result = f"📅 {target_date}\n주말은 식단을 운영하지 않습니다."
            _cache_set(target_date, result, MENU_CACHE_TTL_SECONDS)
            return result

        col_idx = weekday + 1
        def extract_menu(row_idx, target_col):
            try:
                tds = rows[row_idx].find_all("td")
                if len(tds) > target_col:
                    menu_text = tds[target_col].get_text(strip=True, separator=" ")
                    return menu_text if len(menu_text) >= 2 else "미운영"
                return "미운영"
            except: return "미운영"

        breakfast = extract_menu(1, col_idx)
        lunch = extract_menu(2, col_idx)
        dinner = extract_menu(3, col_idx)

        result = f"📅 날짜: {target_date}\n\n🍳 [아침]\n{breakfast}\n\n🍱 [점심]\n{lunch}\n\n🌙 [저녁]\n{dinner}"
        _cache_set(target_date, result, MENU_CACHE_TTL_SECONDS)
        return result
    except:
        result = "서버 연결 오류: 잠시 후 다시 시도해 주세요."
        _cache_set(target_date, result, MENU_ERROR_CACHE_TTL_SECONDS)
        return result

@app.route("/keyboard", methods=["POST"])
def chat_response():
    try:
        data = request.get_json(silent=True) or {}
        utterance = data.get("userRequest", {}).get("utterance", "")
        text = str(utterance).replace(" ", "")
        now = datetime.utcnow() + timedelta(hours=9)
        user_date = None

        # 1) 카카오 파라미터에서 날짜
        params = data.get("action", {}).get("params", {}) or {}
        raw_date = params.get("date") or params.get("sys.date")
        if raw_date and "{{" not in str(raw_date):
            try:
                if isinstance(raw_date, str) and raw_date.strip().startswith("{"):
                    raw_date = json.loads(raw_date).get("date")
                if isinstance(raw_date, str):
                    raw_date = raw_date.split("T")[0]
                user_date = datetime.strptime(str(raw_date), "%Y-%m-%d").strftime("%Y-%m-%d")
            except Exception:
                pass

        # 2) 문장에서 날짜 추출
        if not user_date:
            if "내일" in text:
                user_date = (now + timedelta(days=1)).strftime("%Y-%m-%d")
            elif "모레" in text:
                user_date = (now + timedelta(days=2)).strftime("%Y-%m-%d")
            elif "어제" in text:
                user_date = (now - timedelta(days=1)).strftime("%Y-%m-%d")

        if not user_date:
            weekdays = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"]
            add_week = 7 if ("다음주" in text or "다음 주" in text) else 0
            for i, w in enumerate(weekdays):
                if w in text:
                    diff = i - now.weekday() + add_week
                    if diff < 0:
                        diff += 7
                    user_date = (now + timedelta(days=diff)).strftime("%Y-%m-%d")
                    break

        if not user_date:
            m = re.search(r"(\d{4})년(\d{1,2})월(\d{1,2})일", text)
            if m:
                try:
                    user_date = datetime(*map(int, m.groups())).strftime("%Y-%m-%d")
                except Exception:
                    pass
        if not user_date:
            m = re.search(r"(\d{1,2})월(\d{1,2})일", text)
            if m:
                try:
                    user_date = datetime(now.year, *map(int, m.groups())).strftime("%Y-%m-%d")
                except Exception:
                    pass
        if not user_date:
            m = re.search(r"(\d{1,2})일", text)
            if m:
                try:
                    user_date = datetime(now.year, now.month, int(m.group(1))).strftime("%Y-%m-%d")
                except Exception:
                    pass

        if not user_date or "{{" in str(user_date):
            user_date = now.strftime("%Y-%m-%d")

        menu_text = get_jbnu_menu(user_date)
        return jsonify({
            "version": "2.0",
            "template": {"outputs": [{"simpleText": {"text": f"🍴 전북대 식단 안내\n\n{menu_text}"}}]}
        })
    except Exception:
        return jsonify({
            "version": "2.0",
            "template": {"outputs": [{"simpleText": {"text": "처리 중 오류가 발생했습니다."}}]}
        })

if __name__ == "__main__":
    # Render에서 부여하는 PORT(예: 10000)를 우선 사용
    port = int(os.environ.get("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
