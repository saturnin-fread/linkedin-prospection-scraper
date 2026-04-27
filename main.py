from flask import Flask, request, jsonify
from linkedin_api import Linkedin
import os, json

app = Flask(__name__)
COOKIE_PATH = "/app/cookies.json"

def get_api():
    if os.path.exists(COOKIE_PATH):
        with open(COOKIE_PATH) as f:
            cookies = json.load(f)
        li_at = next((c["value"] for c in cookies if c["name"] == "li_at"), None)
        JSESSIONID = next((c["value"] for c in cookies if c["name"] == "JSESSIONID"), None)
        if li_at:
            return Linkedin("", "", cookies={"li_at": li_at, "JSESSIONID": JSESSIONID})
    return Linkedin(os.environ["LINKEDIN_EMAIL"], os.environ["LINKEDIN_PASSWORD"])

@app.route("/debug", methods=["POST"])
def debug():
    """Retourne les données brutes de search_people pour diagnostic"""
    data    = request.json or {}
    keyword = data.get("keyword", "renovation")
    limit   = int(data.get("limit", 2))
    try:
        api     = get_api()
        results = api.search_people(keywords=keyword, limit=limit)
        # Retourne les 2 premiers résultats bruts pour voir la structure exacte
        sample  = results[:2] if results else []
        return jsonify({
            "total":   len(results),
            "type":    str(type(results)),
            "sample":  sample
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

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
            elif urn_id:
                try:
                    profile = api.get_profile(urn_id)
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
