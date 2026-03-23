from flask import Flask, jsonify
from flask_cors import CORS
from scraper import scrape_all
import time

app = Flask(__name__)
CORS(app)

# Cache scraped data for 30 minutes
# This avoids re-scraping on every app request
_cache = {
    "data":      None,
    "timestamp": 0,
}
CACHE_TTL = 60 * 30  # 30 minutes


def get_cached_issues():
    now = time.time()
    if _cache["data"] is None or (now - _cache["timestamp"]) > CACHE_TTL:
        print("[cache] Refreshing data from ShareSansar...")
        _cache["data"]      = scrape_all()
        _cache["timestamp"] = now
    else:
        print("[cache] Serving cached data")
    return _cache["data"]


@app.route("/issues", methods=["GET"])
def get_issues():
    try:
        data = get_cached_issues()
        return jsonify(data), 200
    except Exception as e:
        print(f"[app] Error in /issues: {e}")
        return jsonify({"error": str(e), "issues": [], "count": 0}), 500


@app.route("/ping", methods=["GET"])
def ping():
    return jsonify({"status": "ok"}), 200


if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=5000)