import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SITE = Path.cwd() / "_site"
RELEASES_FILE = ROOT / "releases.json"


def main():
    releases = json.loads(RELEASES_FILE.read_text(encoding="utf-8"))
    fetched_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    catalogue = {
        "artistId": "0bAOna6xN6OaEK7vRtmS1r",
        "fetchedAt": fetched_at,
        "releases": [],
    }
    for release in releases:
        date = release.get("date", "")
        precision = "day" if len(date) >= 10 else "month" if len(date) >= 7 else "year"
        tracks = release.get("tracks", [])
        catalogue["releases"].append({
            "id": release["id"],
            "title": release["title"],
            "type": release.get("type", "single"),
            "date": date,
            "datePrecision": precision,
            "tracks": len(tracks),
            "artwork": release.get("cover", ""),
            "url": release.get("url", ""),
            "artists": [{"name": name} for name in release.get("artists", [])],
        })
        track_dir = SITE / "api" / "releases" / release["id"]
        track_dir.mkdir(parents=True, exist_ok=True)
        (track_dir / "tracks.json").write_text(json.dumps({
            "releaseId": release["id"],
            "tracks": tracks,
        }, ensure_ascii=False), encoding="utf-8")

    api_file = SITE / "api" / "releases.json"
    api_file.parent.mkdir(parents=True, exist_ok=True)
    api_file.write_text(json.dumps(catalogue, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
