from flask import Flask, request, jsonify
import requests, os, json, re

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
    li_at      = os.environ.get("LI_AT", "").strip()
    jsessionid = os.environ.get("JSESSIONID", "").strip()

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
                raise Exception(f"Erreur parsing cookies : {e}")

    if not li_at:
        raise Exception("li_at introuvable. Vérifie LI_AT dans Railway Variables.")

    session = requests.Session()
    session.cookies.set("li_at",      li_at,      domain=".linkedin.com")
    session.cookies.set("JSESSIONID", jsessionid, domain=".linkedin.com")
    session.headers.update({
        **HEADERS,
        "csrf-token": jsessionid.strip('"'),
    })
    return session

def safe_query(text):
    """Nettoie le texte pour l'insérer dans le paramètre query LinkedIn"""
    return re.sub(r'[(),:]+', ' ', text).strip()

def build_params(query, limit):
    q = safe_query(query)
    return {
        "decorationId": "com.linkedin.voyager.dash.deco.search.SearchClusterCollection-175",
        "count":        min(int(limit), 49),  # LinkedIn limite à 49
        "q":            "all",
        "query":        f"(keywords:{q},flagshipSearchIntent:SEARCH_SRP,queryParameters:(resultType:List(PEOPLE)),includeFiltersInResponse:false)",
    }

def extract_prospects(data_json):
    """
    Tente d'extraire les prospects depuis plusieurs structures possibles
    de réponse LinkedIn (l'API change régulièrement).
    """
    prospects = []

    # Structure 1 : elements[].items[].item.entityResult
    for cluster in data_json.get("elements", []):
        for item in cluster.get("items", []):
            entity = item.get("item", {}).get("entityResult", {})
            if not entity:
                # Structure 2 : items directs sans entityResult
                entity = item.get("entityResult", {})
            if not entity:
                continue
            name   = entity.get("title", {}).get("text", "")
            sub    = entity.get("primarySubtitle", {}).get("text", "")
            loc    = entity.get("secondarySubtitle", {}).get("text", "")
            nav    = entity.get("navigationUrl", "")
            pub_id = nav.split("/in/")[-1].split("?")[0] if "/in/" in nav else ""
            if not name:
                continue
            parts = name.split(" ", 1)
            prospects.append({
                "firstname":   parts[0] if parts else "",
                "lastname":    parts[1] if len(parts) > 1 else "",
                "occupation":  sub,
                "location":    loc,
                "profile_url": f"https://linkedin.com/in/{pub_id}" if pub_id else "",
                "summary":     "",
                "source":      "linkedin"
            })

    # Structure 3 : included[] (format normalisé LinkedIn)
    if not prospects:
        for item in data_json.get("included", []):
            if item.get("$type", "") not in (
                "com.linkedin.voyager.dash.search.SearchProfile",
                "com.linkedin.voyager.search.SearchProfile",
            ):
                continue
            name   = item.get("title", {}).get("text", "") if isinstance(item.get("title"), dict) else item.get("title", "")
            sub    = item.get("primarySubtitle", {}).get("text", "") if isinstance(item.get("primarySubtitle"), dict) else item.get("primarySubtitle", "")
            loc    = item.get("secondarySubtitle", {}).get("text", "") if isinstance(item.get("secondarySubtitle"), dict) else item.get("secondarySubtitle", "")
            nav    = item.get("navigationUrl", "")
            pub_id = nav.split("/in/")[-1].split("?")[0] if "/in/" in nav else ""
            if not name:
                continue
            parts = name.split(" ", 1)
            prospects.append({
                "firstname":   parts[0] if parts else "",
                "lastname":    parts[1] if len(parts) > 1 else "",
                "occupation":  sub,
                "location":    loc,
                "profile_url": f"https://linkedin.com/in/{pub_id}" if pub_id else "",
                "summary":     "",
                "source":      "linkedin"
            })

    return prospects

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
    limit     = data.get("limit", 20)
    try:
        session   = get_session()
        query     = f"{keyword} {job_title}".strip()
        url       = "https://www.linkedin.com/voyager/api/voyagerSearchDashClusters"
        params    = build_params(query, limit)
        resp      = session.get(url, params=params, timeout=20)

        if resp.status_code == 401:
            return jsonify({"error": "Session expirée. Mets à jour LI_AT dans Railway Variables."}), 401
        if resp.status_code == 429:
            return jsonify({"error": "Rate limit LinkedIn. Attends quelques minutes."}), 429
        if resp.status_code != 200:
            return jsonify({"error": f"LinkedIn {resp.status_code}", "body": resp.text[:500]}), 500

        prospects = extract_prospects(resp.json())
        return jsonify({"prospects": prospects, "count": len(prospects)})

    except requests.Timeout:
        return jsonify({"error": "Timeout — LinkedIn met trop de temps à répondre."}), 504
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/debug", methods=["POST"])
def debug():
    data    = request.json or {}
    keyword = data.get("keyword", "renovation")
    try:
        session = get_session()
        url     = "https://www.linkedin.com/voyager/api/voyagerSearchDashClusters"
        params  = build_params(keyword, 2)
        resp    = session.get(url, params=params, timeout=20)
        try:
            body = resp.json()
        except Exception:
            body = resp.text[:3000]
        return jsonify({
            "status_code":    resp.status_code,
            "prospects_found": len(extract_prospects(body)) if isinstance(body, dict) else 0,
            "raw":            body
        })
    except requests.Timeout:
        return jsonify({"error": "Timeout"}), 504
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
    return jsonify({
        "status": "cookies saved",
        "count":  len(cookies) if isinstance(cookies, list) else 0
    })

@app.route("/health")
def health():
    return jsonify({"status": "ok"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
