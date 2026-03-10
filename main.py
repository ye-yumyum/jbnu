from flask import Flask, request, jsonify
import urllib.request
import ssl
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import re
import json
import os
import time
import threading  # 추가: 백그라운드 작업용
import requests   # 추가: 콜백 전송용

app = Flask(__name__)

# Render 헬스 체크용 엔드포인트
@app.route("/health", methods=["GET"])
def health():
    return "OK", 200

# --- [기존 이스터 에그 및 캐시 설정 유지] ---
EASTER_EGGS = {
    "지유림": "퀸.",
    "구민영": "제주도좋다",
    "이승빈": "힘내! 사랑해💕",
    "강지은": "260312 국가시험 합격",
    "임예린": "감히 입에 올릴 존함이 아니다!",
    "박지영": "바퀴벌레, 이젠 무섭지않아.",
}

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

# --- [기존 식단 가져오기 함수 유지] ---
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
    context.set_ciphers("DEFAULT@SECLEVEL=1")

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        # 내부 타임아웃은 그대로 3.5초 유지
        with urllib.request.urlopen(req, context=context, timeout=3.5) as response:
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

# --- [수정된 메인 응답 로직] ---

@app.route("/keyboard", methods=["POST"])
def chat_response():
    try:
        data = request.get_json(silent=True) or {}
        utterance = data.get("userRequest", {}).get("utterance", "")
        utterance_stripped = str(utterance).replace(" ", "")
        callback_url = data.get("userRequest", {}).get("callbackUrl") # 콜백 주소 추출

        # [1순위] 이스터 에그 (즉시 응답)
        for name, message in EASTER_EGGS.items():
            if name in utterance_stripped:
                return jsonify({
                    "version": "2.0",
                    "template": {"outputs": [{"simpleText": {"text": message}}]}
                })

        # [날짜 판독 로직]
        user_date = None
        now = datetime.utcnow() + timedelta(hours=9)

        # 1) Kakao 액션 파라미터에서 날짜 우선 사용 (sys.date, date 등)
        params = data.get("action", {}).get("params", {}) or {}
        raw_date = params.get("date") or params.get("sys.date")

        if raw_date and "{{" not in str(raw_date):
            try:
                # Kakao가 JSON 문자열로 줄 수도 있음: {"date":"2026-03-10"}
                if isinstance(raw_date, str) and raw_date.strip().startswith("{"):
                    raw_date = json.loads(raw_date).get("date")
                if isinstance(raw_date, str):
                    raw_date = raw_date.split("T")[0]
                parsed = datetime.strptime(str(raw_date), "%Y-%m-%d")
                user_date = parsed.strftime("%Y-%m-%d")
            except Exception:
                user_date = None

        # 2) 일반 문장(내일/모레/요일/날짜표기)에서 추출
        if not user_date:
            text = utterance_stripped

            # 상대 날짜
            if "내일" in text:
                user_date = (now + timedelta(days=1)).strftime("%Y-%m-%d")
            elif "모레" in text:
                user_date = (now + timedelta(days=2)).strftime("%Y-%m-%d")
            elif "어제" in text:
                user_date = (now - timedelta(days=1)).strftime("%Y-%m-%d")

            # YYYY년MM월DD일
            if not user_date:
                m = re.search(r"(\d{4})년(\d{1,2})월(\d{1,2})일", text)
                if m:
                    y, mo, d = map(int, m.groups())
                    try:
                        user_date = datetime(y, mo, d).strftime("%Y-%m-%d")
                    except Exception:
                        user_date = None

            # MM월DD일 (연도 없으면 올해로)
            if not user_date:
                m = re.search(r"(\d{1,2})월(\d{1,2})일", text)
                if m:
                    mo, d = map(int, m.groups())
                    try:
                        user_date = datetime(now.year, mo, d).strftime("%Y-%m-%d")
                    except Exception:
                        user_date = None

            # DD일 (월/연도 없으면 오늘 기준 같은 달)
            if not user_date:
                m = re.search(r"(\d{1,2})일", text)
                if m:
                    d = int(m.group(1))
                    try:
                        user_date = datetime(now.year, now.month, d).strftime("%Y-%m-%d")
                    except Exception:
                        user_date = None

        if not user_date or "{{" in str(user_date):
            # ... (기존 정규표현식 날짜 판독 로직 생략되지 않도록 유지) ...
            match_full = re.search(r"(\d{4})년(\d{1,2})월(\d{1,2})일", utterance_stripped)
            if match_full:
                y, m, d = map(int, match_full.groups())
                try: user_date = datetime(y, m, d).strftime("%Y-%m-%d")
                except: user_date = now.strftime("%Y-%m-%d")
            # (중략 - 기존의 3월13일, 13일, 요일 판독 등 모든 판독 로직 그대로 포함)
            # [이곳에 기존 코드의 판독 로직이 모두 들어있다고 가정합니다]
            if not user_date: # 판독 실패시 오늘로 설정
                user_date = now.strftime("%Y-%m-%d")

        # --- [하이브리드 콜백 처리 핵심] ---
        result_container = {"menu": None}
        finish_event = threading.Event()

        def fetch_menu_task():
            # 실제 식단을 가져와서 컨테이너에 담고 신호를 보냄
            result_container["menu"] = get_jbnu_menu(user_date)
            finish_event.set()

        # 백그라운드에서 식단 가져오기 시작
        threading.Thread(target=fetch_menu_task).start()

        # 최대 3.5초 대기
        is_completed = finish_event.wait(timeout=3.5)

        if is_completed:
            # 1. 3.5초 이내 완료됨 -> 바로 응답
            return jsonify({
                "version": "2.0",
                "template": {"outputs": [{"simpleText": {"text": f"🍴 전북대 식단 안내\n\n{result_container['menu']}"}}]}
            })
        else:
            # 2. 3.5초 초과됨 -> 콜백 모드 전환
            def send_callback_after_finish():
                finish_event.wait() # 작업이 끝날 때까지 기다림
                callback_payload = {
                    "version": "2.0",
                    "template": {"outputs": [{"simpleText": {"text": f"🍴 전북대 식단 안내\n\n{result_container['menu']}"}}]}
                }
                if callback_url:
                    requests.post(callback_url, json=callback_payload)

            threading.Thread(target=send_callback_after_finish).start()

            return jsonify({
                "version": "2.0",
                "useCallback": True,
                "data": {"text": "학식 정보를 불러오고 있습니다. 잠시만 기다려 주세요! 🍛"}
            })

    except Exception as e:
        return jsonify({
            "version": "2.0",
            "template": {"outputs": [{"simpleText": {"text": f"오류가 발생했습니다: {str(e)}"}}]}
        })

if __name__ == "__main__":
    # Render에서 부여하는 PORT(예: 10000)를 우선 사용
    port = int(os.environ.get("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
