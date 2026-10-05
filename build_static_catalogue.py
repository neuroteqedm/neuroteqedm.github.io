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
        updated = re.sub(r"[‐‑‒–—―]", "-", updated)
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
        tracklist_css = """
<style id="neuroteq-tracklist-layout">.release:has(.tracklist-popover){position:relative;z-index:9999}
.release-tracks{position:relative}
a[href="#label-heading"].text-link{display:none!important}
footer a[href="#label-heading"]{pointer-events:none;text-decoration:none;color:inherit}.tracklist-popover{position:absolute!important;top:calc(100% + 5px)!important;bottom:auto!important;left:-9px!important;right:auto!important;width:calc(100% + 18px)!important;max-height:min(520px,calc(100vh - 24px))!important;overflow:auto!important;z-index:10000!important}
.music-links a[href*="open.spotify.com"]:hover,.social-links a[href*="open.spotify.com"]:hover{color:#1ed760!important}
.music-links a[href*="music.apple.com"]:hover,.social-links a[href*="music.apple.com"]:hover{color:#fa243c!important}
.music-links a[href*="soundcloud.com"]:hover,.social-links a[href*="soundcloud.com"]:hover{color:#ff5500!important}
.music-links a[href*="youtube.com"]:hover,.social-links a[href*="youtube.com"]:hover{color:#ff0033!important}
.music-links a[href*="tidal.com"]:hover,.social-links a[href*="tidal.com"]:hover{color:#7de8ff!important}
.music-links a[href*="deezer.com"]:hover,.social-links a[href*="deezer.com"]:hover{color:#b26bff!important}
.music-links a[href*="amazon.com"]:hover,.social-links a[href*="amazon.com"]:hover{color:#25d1da!important}
.music-links a[href*="newgrounds.com"]:hover,.social-links a[href*="newgrounds.com"]:hover{color:#ff9900!important}
.music-links a[href*="instagram.com"]:hover,.social-links a[href*="instagram.com"]:hover{color:#e4405f!important}
.music-links a[href*="tiktok.com"]:hover,.social-links a[href*="tiktok.com"]:hover{color:#25f4ee!important}
.music-links a[href*="twitch.tv"]:hover,.social-links a[href*="twitch.tv"]:hover{color:#a970ff!important}
.music-links a[href*="musixmatch.com"]:hover,.social-links a[href*="musixmatch.com"]:hover{color:#ff5b5b!important}

/* Softer corners across the site */
:root { --radius: 14px; }
.hero-avatar-frame { border-radius: 16px; }
.hero-avatar-frame img { border-radius: inherit; }
.genres li { border: 1px solid #49394f; border-radius: 10px; padding: 3px 11px; }
.genres ul { gap: 7px; }
.release { border: 1px solid #302a35; border-radius: 12px; background: #100e12; padding: 12px; }
.release-art { border-radius: 8px; }
.release-meta { margin-top: 14px; }
.tracklist-head h4 { font-size: 1.2rem; }
.tracklist-songs a { min-height: 64px; padding: 15px 16px; }
.track-title { font-size: 1.0625rem; }
.tracklist-popover { border-radius: 14px; overflow: hidden; }
.tracklist-head { border-radius: 13px 13px 0 0; }
.tracklist-close { border-radius: 50%; transition: color .18s ease, background-color .18s ease; }
.tracklist-close:hover { background: #2b1d31; }
.release-tabs .release-tab-list { border: 0; gap: 8px; margin-bottom: 22px; }
.release-tabs .release-tab { min-height: 40px; border: 1px solid transparent; border-radius: 8px; padding: 7px 14px; transition: color .18s ease, background-color .18s ease, border-color .18s ease; }
.release-tabs .release-tab[data-state=active] { background: #1a151e; border-color: #49394f; }
.release-tabs .release-tab:after { display: none; }
.show-releases { border-radius: 8px; }
.music-links { border: 0; gap: 10px 22px; }
.music-links li, .music-links li:hover { border: 0; border-radius: 0; background: transparent; overflow: visible; }
.music-links a { grid-template-columns: 24px minmax(0,1fr) 18px; align-items: center; column-gap: 10px; min-height: 60px; padding: 8px 0; border-radius: 0; }
.music-links a::before { content: ""; display: block; width: 22px; height: 22px; grid-column: 1; grid-row: 1 / span 2; align-self: center; background-position: center; background-repeat: no-repeat; background-size: contain; }
.music-links a .platform-name { grid-column: 2; grid-row: 1; }
.music-links a .platform-detail { grid-column: 2; grid-row: 2; }
.music-links a > svg { grid-column: 3; grid-row: 1 / span 2; }
.music-links a::before { background-repeat: no-repeat; background-position: center; background-size: contain; transition: transform .22s cubic-bezier(.2,.7,.2,1), filter .2s ease; }
.music-links a[href*="spotify.com"]::before { background-image: radial-gradient(circle, #1ed760 61%, transparent 63%), url("https://cdn.simpleicons.org/spotify/000000"); background-size: 100% 100%, 75% 75%; border-radius: 50%; }
.music-links a[href*="music.apple.com"]::before { background-image: url("https://cdn.simpleicons.org/applemusic/ffffff"); }
.music-links a[href*="soundcloud.com"]::before { background-image: url("https://cdn.simpleicons.org/soundcloud/ff5500"); }
.music-links a[href*="soundcloud.com"]:hover .platform-name { color: #ff5500; }
.music-links a[href*="music.youtube.com"]::before { background-image: url("https://cdn.simpleicons.org/youtubemusic/ffffff"); }
.music-links a[href*="tidal.com"]::before { background-image: url("https://cdn.simpleicons.org/tidal/ffffff"); }
.music-links a[href*="tidal.com"]:hover .platform-name { color: #ffffff; }
.music-links a[href*="deezer.com"]::before { background-image: url("https://cdn.simpleicons.org/deezer/b26bff"); }
.music-links a[href*="deezer.com"]:hover .platform-name { color: #b26bff; }
.music-links a[href*="newgrounds.com"]::before { background-image: url("https://cdn.simpleicons.org/newgrounds/ff9900"); }
.music-links a[href*="newgrounds.com"]:hover .platform-name { color: #ff9900; }
.music-links a[href*="music.apple.com"]:hover .platform-name { color: #fa243c; }
.music-links a[href*="music.youtube.com"]:hover .platform-name { color: #ff0033; }
.music-links a[href*="amazon.com"]::before { background-image: url("https://cdn.simpleicons.org/amazonmusic/25D1DA"); }
.music-links a:hover::before { transform: scale(1.12); }
.social-links { gap: 10px 22px; }
.social-links li, .social-links li:hover { border: 0 !important; border-radius: 0 !important; background: transparent !important; padding: 0 !important; }
.social-links a { display: grid; grid-template-columns: minmax(0,1fr) 16px; align-items: center; gap: 1px 10px; min-height: 56px; padding: 8px 0; border-radius: 0; transition: color .2s ease, opacity .2s ease; }
.social-links a > span:first-child { grid-column: 1; grid-row: 1; }
.social-links a .social-handle { grid-column: 1; grid-row: 2; }
.social-links a > svg { grid-column: 2; grid-row: 1 / span 2; transition: transform .2s ease, color .2s ease; }
.social-links a:hover > svg { transform: translate(2px,-2px); }
.label-note { border: 1px solid #49394f; border-left: 2px solid var(--accent); border-radius: 16px; background: #100e12; padding: 22px; }
.timeline li:before { border-radius: 50%; }
.site-footer a { border-radius: 6px; padding-inline: 11px; transition: color .18s ease, background-color .18s ease; }
.site-footer a:hover { background: #1a151e; }
@media (max-width:760px) {
  .release { border-radius: 10px; padding: 9px; }
  .music-links { gap: 8px 14px; }
  .music-links a { min-height: 54px; padding: 7px 0; }
  .social-links { gap: 8px; }
  .social-links li { padding-inline: 11px; }
  .label-note { padding: 18px; }
}
.music-links a, .music-links a .platform-name, .music-links a .platform-detail, .music-links a > svg { transition: color .2s ease, opacity .2s ease, transform .2s ease; }
.music-links a::before { transition: transform .22s cubic-bezier(.2,.7,.2,1), opacity .2s ease; }
.music-links a:hover::before { transform: scale(1.12); }
.music-links a:hover > svg { transform: translate(2px,-2px); }
.music-links a[href*="spotify.com"]:hover .platform-name { color: #1ed760; }
.music-links a[href*="music.apple.com"]:hover .platform-name { color: #fa243c; }
.music-links a[href*="soundcloud.com"]:hover .platform-name { color: #ff5500; }
.music-links a[href*="youtube.com"]:hover .platform-name { color: #ff0033; }
.music-links a[href*="tidal.com"]:hover .platform-name { color: #7de8ff; }
.music-links a[href*="deezer.com"]:hover .platform-name { color: #b26bff; }
.music-links a[href*="amazon.com"]:hover .platform-name { color: #25d1da; }
.music-links a[href*="newgrounds.com"]:hover .platform-name { color: #ff9900; }
@media (prefers-reduced-motion: reduce) {
  .music-links a, .music-links a::before, .music-links a > svg, .social-links li, .social-links a, .social-links a::before, .social-links a > svg, .release-tabs .release-tab, .tracklist-close, .site-footer a { transition: none; }
}
</style>
"""
        if 'id="neuroteq-tracklist-layout"' not in html:
            html = html.replace("</head>", tracklist_css + "</head>", 1)
        index_file.write_text(html, encoding="utf-8")

    patch_exported_site()

if __name__ == "__main__":
    main()
