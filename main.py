from flask import Flask, request, jsonify
import requests, os, json

app = Flask(__name__)
COOKIE_PATH = "/app/cookies.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/vnd.linkedin.normalized+json+2.1",
    "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
    "x-li-lang": "fr_FR",
    "x-li-track": '{"clientVersion":"1.13.1665"}',
    "x-restli-protocol-version": "2.0.0",
}

def get_session():
    if not os.path.exists(COOKIE_PATH):
        raise Exception("Cookies non chargés. Appelle /cookies d'abord.")
    
    with open(COOKIE_PATH) as f:
        raw = json.load(f)

    # Supporte 2 formats : liste directe OU {"cookies": [...]}
    if isinstance(raw, dict):
        cookies_list = raw.get("cookies", [])
    elif isinstance(raw, list):
        cookies_list = raw
    else:
        raise Exception(f"Format cookies invalide : {type(raw)}")

    if not cookies_list:
        raise Exception("Liste de cookies vide.")

    session = requests.Session()
    for c in cookies_list:
        if isinstance(c, dict) and "name" in c and "value" in c:
            session.cookies.set(c["name"], c["value"], domain=".linkedin.com")

    jsessionid = session.cookies.get("JSESSIONID", "")
    session.headers.update({
        **HEADERS,
        "csrf-token": jsessionid.strip('"'),
    })
    return session

@app.route("/search", methods=["POST"])
def search():
    data      = request.json or {}
    keyword   = data.get("keyword", "")
    job_title = data.get("job_title", "")
    limit     = int(data.get("limit", 20))

    try:
        session = get_session()
        query   = f"{keyword} {job_title}".strip()

        url = "https://www.linkedin.com/voyager/api/search/blended"
        params = {
            "count":    limit,
            "filters":  "List(resultType->PEOPLE)",
            "keywords": query,
            "origin":   "GLOBAL_SEARCH_HEADER",
            "q":        "all",
        }
        resp = session.get(url, params=params, timeout=15)

        if resp.status_code != 200:
            return jsonify({"error": f"LinkedIn {resp.status_code}", "body": resp.text[:500]}), 500

        data_json = resp.json()
        prospects = []
        elements  = data_json.get("data", {}).get("elements", [])

        for element in elements:
            for item in element.get("elements", []):
                name   = item.get("title", {}).get("text", "")
                sub    = item.get("primarySubtitle", {}).get("text", "")
                loc    = item.get("secondarySubtitle", {}).get("text", "")
                nav    = item.get("navigationUrl", "")
                pub_id = nav.split("/in/")[-1].split("?")[0] if "/in/" in nav else ""
                parts  = name.split(" ", 1)
                prospects.append({
                    "firstname":   parts[0] if parts else "",
                    "lastname":    parts[1] if len(parts) > 1 else "",
                    "occupation":  sub,
                    "location":    loc,
                    "profile_url": f"https://linkedin.com/in/{pub_id}" if pub_id else "",
                    "summary":     "",
                    "source":      "linkedin"
                })

        return jsonify({"prospects": prospects, "count": len(prospects)})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/debug", methods=["POST"])
def debug():
    data    = request.json or {}
    keyword = data.get("keyword", "renovation")
    try:
        session = get_session()
        url = "https://www.linkedin.com/voyager/api/search/blended"
        params = {
            "count":   2,
            "filters": "List(resultType->PEOPLE)",
            "keywords": keyword,
            "origin":  "GLOBAL_SEARCH_HEADER",
            "q":       "all",
        }
        resp = session.get(url, params=params, timeout=15)
        try:
            body = resp.json()
        except Exception:
            body = resp.text[:2000]
        return jsonify({"status_code": resp.status_code, "raw": body})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/cookies", methods=["POST"])
def upload_cookies():
    data    = request.json or {}
    cookies = data.get("cookies", [])
    with open(COOKIE_PATH, "w") as f:
        json.dump(cookies, f)
    return jsonify({"status": "cookies saved", "count": len(cookies)})

@app.route("/health")
def health():
    return jsonify({"status": "ok"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
