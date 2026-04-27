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
    # PRIORITÉ 1 : variables d'environnement Railway
    li_at      = os.environ.get("LI_AT", "").strip()
    jsessionid = os.environ.get("JSESSIONID", "").strip()

    # PRIORITÉ 2 : fichier cookies (fallback)
    if not li_at and os.path.exists(COOKIE_PATH):
        with open(COOKIE_PATH) as f:
            raw = f.read().strip()
        if raw:
            try:
                data = json.loads(raw)
                if isinstance(data, str):
                    data = json.loads(data)
                if isinstance(data, dict):
                    data = data.get("cookies", [])
                if isinstance(data, str):
                    data = json.loads(data)
                if isinstance(data, list):
                    li_at      = next((c["value"] for c in data if isinstance(c, dict) and c.get("name") == "li_at"), "")
                    jsessionid = next((c["value"] for c in data if isinstance(c, dict) and c.get("name") == "JSESSIONID"), "")
            except Exception as e:
                raise Exception(f"Erreur parsing cookies fichier : {e}")

    if not li_at:
        raise Exception("li_at introuvable. Vérifie la variable LI_AT dans Railway.")

    session = requests.Session()
    session.cookies.set("li_at",      li_at,      domain=".linkedin.com")
    session.cookies.set("JSESSIONID", jsessionid, domain=".linkedin.com")
    session.headers.update({
        **HEADERS,
        "csrf-token": jsessionid.strip('"'),
    })
    return session

@app.route("/env")
def env():
    li_at      = os.environ.get("LI_AT", "NON_DEFINI")
    jsessionid = os.environ.get("JSESSIONID", "NON_DEFINI")
    return jsonify({
        "LI_AT_length":      len(li_at),
        "LI_AT_start":       li_at[:10] if li_at != "NON_DEFINI" else "NON_DEFINI",
        "JSESSIONID_length": len(jsessionid),
        "JSESSIONID_start":  jsessionid[:10] if jsessionid != "NON_DEFINI" else "NON_DEFINI",
    })

@app.route("/search", methods=["POST"])
def search():
    data      = request.json or {}
    keyword   = data.get("keyword", "")
    job_title = data.get("job_title", "")
    limit     = int(data.get("limit", 20))
    try:
        session = get_session()
        query   = f"{keyword} {job_title}".strip()
        url     = "https://www.linkedin.com/voyager/api/search/blended"
        params  = {
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
        url     = "https://www.linkedin.com/voyager/api/search/blended"
        params  = {
            "count":    2,
            "filters":  "List(resultType->PEOPLE)",
            "keywords": keyword,
            "origin":   "GLOBAL_SEARCH_HEADER",
            "q":        "all",
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
    if isinstance(cookies, str):
        try:
            cookies = json.loads(cookies)
        except Exception:
            pass
    with open(COOKIE_PATH, "w") as f:
        json.dump(cookies, f)
    return jsonify({"status": "cookies saved", "count": len(cookies) if isinstance(cookies, list) else 0})

@app.route("/health")
def health():
    return jsonify({"status": "ok"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
