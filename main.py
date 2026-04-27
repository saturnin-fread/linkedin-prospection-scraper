from flask import Flask, request, jsonify
from linkedin_api import Linkedin
import os, json

app = Flask(__name__)

COOKIE_PATH = "/app/cookies.json"

def get_api():
    if os.path.exists(COOKIE_PATH):
        with open(COOKIE_PATH) as f:
            cookies = json.load(f)
        # Extrait li_at depuis les cookies
        li_at = next((c["value"] for c in cookies if c["name"] == "li_at"), None)
        JSESSIONID = next((c["value"] for c in cookies if c["name"] == "JSESSIONID"), None)
        if li_at:
            return Linkedin(
                "",
                "",
                cookies={"li_at": li_at, "JSESSIONID": JSESSIONID}
            )
    # Fallback email/password
    return Linkedin(
        os.environ["LINKEDIN_EMAIL"],
        os.environ["LINKEDIN_PASSWORD"]
    )

@app.route("/search", methods=["POST"])
def search():
    data      = request.json or {}
    keyword   = data.get("keyword", "")
    job_title = data.get("job_title", "")
    limit     = int(data.get("limit", 20))

    try:
        api = get_api()
        results = api.search_people(
            keywords=keyword,
            job_title=job_title if job_title else None,
            limit=limit
        )
        prospects = []
        for r in results:
            prospects.append({
                "firstname":   r.get("firstName", ""),
                "lastname":    r.get("lastName", ""),
                "occupation":  r.get("occupation", ""),
                "location":    r.get("locationName", ""),
                "profile_url": f"https://linkedin.com/in/{r.get('publicIdentifier','')}",
                "summary":     r.get("summary", ""),
                "source":      "linkedin"
            })
        return jsonify({"prospects": prospects, "count": len(prospects)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/cookies", methods=["POST"])
def upload_cookies():
    data = request.json or {}
    cookies = data.get("cookies", [])
    with open(COOKIE_PATH, "w") as f:
        json.dump(cookies, f)
    return jsonify({"status": "cookies saved", "count": len(cookies)})

@app.route("/health")
def health():
    return jsonify({"status": "ok"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
