import concurrent.futures
import json
import mimetypes
import re
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
            target = SITE / "images" / "releases" / "{}{}".format(release["id"], suffix)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(response.read(12_000_001))
            if target.stat().st_size > 12_000_000:
                target.unlink(missing_ok=True)
                return url
            return "/images/releases/{}".format(target.name)
    except Exception:
        return url








def normalize_track(track, release, index):
    if isinstance(track, str):
        return {
            "id": "{}-{}".format(release["id"], index),
            "title": track,
            "artists": [{"name": name} for name in release.get("artists", [])],
            "durationMs": 0,
            "number": index,
            "disc": 1,
            "url": release.get("url", ""),
        }
    return {
        "id": track.get("id") or "{}-{}".format(release["id"], index),
        "title": track.get("title") or track.get("name", ""),
        "artists": track.get("artists", []),
        "durationMs": track.get("durationMs", track.get("duration_ms", 0)),
        "number": track.get("number", track.get("track_number", index)),
        "disc": track.get("disc", track.get("disc_number", 1)),
        "url": track.get("url") or track.get("external_urls", {}).get("spotify", release.get("url", "")),
    }








def patch_exported_site():
    chunks = SITE / "_next" / "static" / "chunks"
    old_name = "layout-segment-context-D-I1VA2F.js"
    new_name = "layout-context-D-I1VA2F.js"
    old_chunk = chunks / old_name
    new_chunk = chunks / new_name




    if old_chunk.exists():
        chunk_text = old_chunk.read_text(encoding="utf-8")
        chunk_text = chunk_text.replace(
            'import{i as n}from"./index-Neuroteq2.js";',
            "var n=()=>null;",
        )
        new_chunk.write_text(chunk_text, encoding="utf-8")
        old_chunk.unlink()
    elif new_chunk.exists():
        chunk_text = new_chunk.read_text(encoding="utf-8")
        chunk_text = chunk_text.replace(
            'import{i as n}from"./index-Neuroteq2.js";',
            "var n=()=>null;",
        )
        new_chunk.write_text(chunk_text, encoding="utf-8")




    replacements = {
        old_name: new_name,
        "https://neuroteq.xyz/": "https://backzone99.tb.ru/",
        "https://music.apple.com/ru/artist/backzone99/1715799081": "https://music.apple.com/us/artist/neuroteq/6811395218",
        "https://query-records.backzone99.chatgpt.site": "#label-heading",
        r'\"className\":\"social-handle\",\"children\":\"backzone99\"': r'\"className\":\"social-handle\",\"children\":\"neuroteq\"',
        "https://musixmatch.com/artist/backzone99": "https://musixmatch.com/artist/neuroteq",
    }
    for path in SITE.rglob("*"):
        if not path.is_file() or path.suffix not in {".html", ".js", ".json", ".css"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        updated = text
        for old, new in replacements.items():
            updated = updated.replace(old, new)
        if updated != text:
            path.write_text(updated, encoding="utf-8")








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
    index_file = SITE / "index.html"
    if index_file.exists():
        html = index_file.read_text(encoding="utf-8")
        html = re.sub(
            r'<a class="text-link" href="https://query-records\.backzone99\.chatgpt\.site"[^>]*>Visit Query Records .*?</a>',
            "",
            html,
            count=1,
            flags=re.S,
        )
        html = re.sub(
            r'<a href="https://query-records\.backzone99\.chatgpt\.site">Query Records</a>',
            "Query Records",
            html,
            count=1,
        )
        html = html.replace(
            '<span>Musixmatch</span><span class="social-handle">backzone99</span>',
            '<span>Musixmatch</span><span class="social-handle">neuroteq</span>',
        )
        html = re.sub(
            r'<style id="neuroteq-tracklist-layout">.*?</style>',
            "",
            html,
            count=1,
            flags=re.S,
        )
        site_links_css = """
<style id="neuroteq-site-links">.release:has(.tracklist-popover){position:relative;z-index:30}
.release-tracks{position:relative}
.tracklist-popover{position:absolute!important;top:100%!important;left:0!important;right:auto!important;bottom:auto!important;width:100%!important;max-height:min(480px,calc(100vh - 24px))!important;overflow:auto!important;z-index:50!important}
a[href="#label-heading"].text-link{display:none!important}
footer a[href="#label-heading"]{pointer-events:none;text-decoration:none;color:inherit}
</style>
"""
        if 'id="neuroteq-site-links"' not in html:
            html = html.replace("</head>", site_links_css + "</head>", 1)
        index_file.write_text(html, encoding="utf-8")




    patch_exported_site()








if __name__ == "__main__":
    main()
