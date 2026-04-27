from flask import Flask, request, jsonify
from linkedin_api import Linkedin
import os

app = Flask(__name__)

@app.route("/search", methods=["POST"])
def search():
    data = request.json or {}
    keyword    = data.get("keyword", "")
    job_title  = data.get("job_title", "")
    location   = data.get("location", "")
    limit      = int(data.get("limit", 20))

    api = Linkedin(
        os.environ["LINKEDIN_EMAIL"],
        os.environ["LINKEDIN_PASSWORD"]
    )

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

@app.route("/health")
def health():
    return jsonify({"status": "ok"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
