from flask import Flask, request, jsonify
import urllib.request
import ssl
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import re
import json
import os
import time

app = Flask(__name__)

# 이스터 에그 정의
EASTER_EGGS = {
    "지유림": "퀸.",
    "구민영": "제주도좋다",
    "이승빈": "힘내! 사랑해",
    "강지은": "260312 국가시험 합격",
    "임예린": "감히 입에 올릴 존함이 아니다!",
    "박지영": "바퀴벌레, 이젠 무섭지않아.",
}

# 식단 캐시 (메모리 캐시)
MENU_CACHE = {}  # key: "YYYY-MM-DD" -> {"expires_at": float, "value": str}
MENU_CACHE_TTL_SECONDS = 300  # 5분
MENU_ERROR_CACHE_TTL_SECONDS = 30  # 실패/오류는 30초만 캐시


def _cache_get(key: str):
    item = MENU_CACHE.get(key)
    if not item:
        return None
    if item["expires_at"] < time.time():
        MENU_CACHE.pop(key, None)
        return None
    return item["value"]


def _cache_set(key: str, value: str, ttl_seconds: int):
    MENU_CACHE[key] = {"expires_at": time.time() + ttl_seconds, "value": value}


def get_jbnu_menu(target_date):
    # 한국 시간(KST) 기준 오늘 날짜
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

    # 전북대 생활관(특성화캠퍼스) 주간식단표 URL
    url = f"https://likehome.jbnu.ac.kr/home/main/inner.php?sMenu=B7300&date={target_date}"

    context = ssl._create_unverified_context()
    context.set_ciphers("DEFAULT@SECLEVEL=1")

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})

        # 카카오 스킬 timeout 대비: 외부요청 timeout 짧게
        with urllib.request.urlopen(req, context=context, timeout=3.5) as response:
            html = response.read().decode("utf-8", errors="ignore")

        soup = BeautifulSoup(html, "html.parser")
        tables = soup.find_all("table")
        if not tables:
            result = f"📅 {target_date}\n식단표를 찾을 수 없습니다."
            _cache_set(target_date, result, MENU_ERROR_CACHE_TTL_SECONDS)
            return result

        rows = tables[0].find_all("tr")
        if len(rows) < 4:
            result = f"📅 {target_date}\n식단표 형식이 예상과 다릅니다."
            _cache_set(target_date, result, MENU_ERROR_CACHE_TTL_SECONDS)
            return result

        weekday = date_obj.weekday()  # 0:월 ... 4:금

        # 주말(토/일)
        if weekday > 4:
            result = f"📅 {target_date}\n주말은 식단을 운영하지 않습니다."
            _cache_set(target_date, result, MENU_CACHE_TTL_SECONDS)
            return result

        # 표 구조: td 기준 0=일, 1=월, 2=화, 3=수, 4=목, 5=금
        col_idx = weekday + 1

        def extract_menu(row_idx, target_col):
            try:
                tds = rows[row_idx].find_all("td")
                if len(tds) > target_col:
                    menu_text = tds[target_col].get_text(strip=True, separator=" ")
                    if not menu_text or len(menu_text) < 2:
                        return "미운영"
                    return menu_text
                return "미운영"
            except:
                return "미운영"

        breakfast = extract_menu(1, col_idx)
        lunch = extract_menu(2, col_idx)
        dinner = extract_menu(3, col_idx)

        result = (
            f"📅 날짜: {target_date}\n\n"
            f"🍳 [아침]\n{breakfast}\n\n"
            f"🍱 [점심]\n{lunch}\n\n"
            f"🌙 [저녁]\n{dinner}"
        )

        _cache_set(target_date, result, MENU_CACHE_TTL_SECONDS)
        return result

    except:
        result = "서버 연결 오류: 잠시 후 다시 시도해 주세요."
        _cache_set(target_date, result, MENU_ERROR_CACHE_TTL_SECONDS)
        return result


@app.route("/health", methods=["GET"])
def health():
    return "OK", 200


@app.route("/keyboard", methods=["POST"])
def chat_response():
    try:
        data = request.get_json(silent=True) or {}
        utterance = data.get("userRequest", {}).get("utterance", "")
        utterance_stripped = str(utterance).replace(" ", "")

        # [1순위] 이스터 에그: 문장에 이름이 포함되면 즉시 응답
        for name, message in EASTER_EGGS.items():
            if name in utterance_stripped:
                return jsonify({
                    "version": "2.0",
                    "template": {"outputs": [{"simpleText": {"text": message}}]}
                })

        user_date = None
        now = datetime.utcnow() + timedelta(hours=9)

        # 1) 카카오 파라미터 확인
        params = data.get("action", {}).get("params", {})
        raw_date = params.get("date") or params.get("sys.date")

        if raw_date and "{{" not in str(raw_date):
            if isinstance(raw_date, str) and raw_date.strip().startswith("{"):
                try:
                    user_date = json.loads(raw_date).get("date")
                except:
                    user_date = None
            else:
                user_date = raw_date

        # 2) 요일/날짜 판독기
        if not user_date or "{{" in str(user_date):
            # (1) "2026년3월13일"
            match_full = re.search(r"(\d{4})년(\d{1,2})월(\d{1,2})일", utterance_stripped)
            if match_full:
                year, month, day = map(int, match_full.groups())
                try:
                    user_date = datetime(year, month, day).strftime("%Y-%m-%d")
                except:
                    user_date = now.strftime("%Y-%m-%d")

            # (2) "3월13일" (연도는 현재)
            if not user_date:
                match_md = re.search(r"(\d{1,2})월(\d{1,2})일", utterance_stripped)
                if match_md:
                    month, day = map(int, match_md.groups())
                    try:
                        user_date = datetime(now.year, month, day).strftime("%Y-%m-%d")
                    except:
                        user_date = now.strftime("%Y-%m-%d")

            # (3) "13일" (현재 연/월)
            if not user_date:
                match_d = re.search(r"(\d{1,2})일", utterance_stripped)
                if match_d:
                    day = int(match_d.group(1))
                    try:
                        user_date = datetime(now.year, now.month, day).strftime("%Y-%m-%d")
                    except:
                        user_date = now.strftime("%Y-%m-%d")

            # (4) "월요일/화요일/수요일/목요일/금요일"
            if not user_date:
                weekday_match = re.search(r"(월|화|수|목|금)요일", utterance_stripped)
                if weekday_match:
                    days_map = {"월": 0, "화": 1, "수": 2, "목": 3, "금": 4}
                    idx = days_map[weekday_match.group(1)]
                    diff = idx - now.weekday()
                    if diff < 0:
                        diff += 7
                    user_date = (now + timedelta(days=diff)).strftime("%Y-%m-%d")

            # (5) 내일 / 모레
            if not user_date and "내일" in utterance_stripped:
                user_date = (now + timedelta(days=1)).strftime("%Y-%m-%d")
            elif not user_date and "모레" in utterance_stripped:
                user_date = (now + timedelta(days=2)).strftime("%Y-%m-%d")

        menu = get_jbnu_menu(user_date)
        return jsonify({
            "version": "2.0",
            "template": {"outputs": [{"simpleText": {"text": f"🍴 전북대 식단 안내\n\n{menu}"}}]}
        })
    except:
        return jsonify({
            "version": "2.0",
            "template": {"outputs": [{"simpleText": {"text": "처리 중 오류가 발생했습니다."}}]}
        })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    app.run(host="0.0.0.0", port=port)
