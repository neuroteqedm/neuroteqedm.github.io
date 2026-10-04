import concurrent.futures
import json
import mimetypes
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SITE = Path.cwd() / "_site"
RELEASES_FILE = ROOT / "releases.json"


def save_artwork(release):
    url = release.get("cover", "")
    if not url.startswith("https://"):
        return url
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "NeuroteqSite/1.0"})
        with urllib.request.urlopen(request, timeout=20) as response:
            content_type = response.headers.get_content_type()
            if not content_type.startswith("image/"):
                return url
            suffix = mimetypes.guess_extension(content_type) or ".jpg"
            if suffix == ".jpe":
                suffix = ".jpg"
            target = SITE / "images" / "releases" / f"{release['id']}{suffix}"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(response.read(12_000_001))
            if target.stat().st_size > 12_000_000:
                target.unlink(missing_ok=True)
                return url
            return f"/images/releases/{target.name}"
    except Exception:
        return url


def normalize_track(track, release, index):
    if isinstance(track, str):
        return {
            "id": f"{release['id']}-{index}",
            "title": track,
            "artists": [{"name": name} for name in release.get("artists", [])],
            "durationMs": 0,
            "number": index,
            "disc": 1,
            "url": release.get("url", ""),
        }
    return {
        "id": track.get("id") or f"{release['id']}-{index}",
        "title": track.get("title") or track.get("name", ""),
        "artists": track.get("artists", []),
        "durationMs": track.get("durationMs", track.get("duration_ms", 0)),
        "number": track.get("number", track.get("track_number", index)),
        "disc": track.get("disc", track.get("disc_number", 1)),
        "url": track.get("url") or track.get("external_urls", {}).get("spotify", release.get("url", "")),
    }


def main():
    releases = json.loads(RELEASES_FILE.read_text(encoding="utf-8"))
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        artwork_urls = list(pool.map(save_artwork, releases))

    fetched_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    catalogue = {
        "artistId": "0bAOna6xN6OaEK7vRtmS1r",
        "fetchedAt": fetched_at,
        "releases": [],
    }
    for release, artwork in zip(releases, artwork_urls):
        date = release.get("date", "")
        precision = "day" if len(date) >= 10 else "month" if len(date) >= 7 else "year"
        tracks = [normalize_track(track, release, index) for index, track in enumerate(release.get("tracks", []), 1)]
        catalogue["releases"].append({
            "id": release["id"],
            "title": release["title"],
            "type": release.get("type", "single"),
            "date": date,
            "datePrecision": precision,
            "tracks": len(tracks),
            "artwork": artwork,
            "url": release.get("url", ""),
            "artists": [{"name": name} for name in release.get("artists", [])],
            "tracklist": tracks,
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
