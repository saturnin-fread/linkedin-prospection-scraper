from flask import Flask, request, jsonify
from linkedin_api import Linkedin
import os, json

app = Flask(__name__)
COOKIE_PATH = "/app/cookies.json"

def get_api():
    li_at      = os.environ.get("LI_AT", "").strip()
    jsessionid = os.environ.get("JSESSIONID", "").strip()

    if li_at:
        # Injection directe des cookies sans login
        api = Linkedin.__new__(Linkedin)
        api.logger = __import__('logging').getLogger(__name__)
        
        import requests
        session = requests.Session()
        session.cookies.set("li_at",      li_at,      domain=".linkedin.com")
        session.cookies.set("JSESSIONID", jsessionid, domain=".linkedin.com")
        session.headers.update({
            "User-Agent":                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36",
            "Accept":                    "application/vnd.linkedin.normalized+json+2.1",
            "Accept-Language":           "fr-FR,fr;q=0.9",
            "x-li-lang":                 "fr_FR",
            "x-restli-protocol-version": "2.0.0",
            "csrf-token":                jsessionid,
        })
        api.client = type('Client', (), {'session': session})()
        
        # Patch la méthode _fetch de la lib
        def _fetch(uri, evade=False, base_request=False, **kwargs):
            url = f"https://www.linkedin.com/voyager/api{uri}"
            resp = session.get(url, **kwargs)
            return resp
        api._fetch = _fetch
        return api

    raise Exception("LI_AT manquant dans Railway Variables")

@app.route("/search", methods=["POST"])
def search():
    data      = request.json or {}
    keyword   = data.get("keyword", "")
    job_title = data.get("job_title", "")
    limit     = int(data.get("limit", 20))
    try:
        api     = get_api()
        results = api.search_people(
            keywords=f"{keyword} {job_title}".strip(),
            limit=limit
        )
        prospects = []
        for r in results:
            public_id = r.get("public_id") or r.get("publicIdentifier", "")
            urn_id    = r.get("urn_id", "")
            profile   = {}
            if public_id:
                try:
                    profile = api.get_profile(public_id)
                except Exception:
                    pass
            firstname  = profile.get("firstName")    or r.get("firstName", "")
            lastname   = profile.get("lastName")     or r.get("lastName", "")
            occupation = profile.get("headline")     or r.get("occupation", "")
            location   = profile.get("locationName") or r.get("locationName", "")
            summary    = profile.get("summary", "")
            pid        = profile.get("public_id")    or public_id or urn_id
            prospects.append({
                "firstname":   firstname,
                "lastname":    lastname,
                "occupation":  occupation,
                "location":    location,
                "profile_url": f"https://linkedin.com/in/{pid}" if pid else "",
                "summary":     summary,
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
        api     = get_api()
        results = api.search_people(keywords=keyword, limit=2)
        return jsonify({"count": len(results), "sample": results[:2]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/env")
def env():
    li_at      = os.environ.get("LI_AT", "NON_DEFINI")
    jsessionid = os.environ.get("JSESSIONID", "NON_DEFINI")
    return jsonify({
        "LI_AT_length":  len(li_at),
        "LI_AT_start":   li_at[:10] if li_at != "NON_DEFINI" else "NON_DEFINI",
        "JSESSIONID_ok": jsessionid != "NON_DEFINI",
    })

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
