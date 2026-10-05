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
footer a[href="#label-heading"]{pointer-events:none;text-decoration:none;color:inherit}.tracklist-popover{position:relative!important;top:auto!important;bottom:auto!important;left:auto!important;right:auto!important;width:100%!important;max-height:min(480px,calc(100vh - 24px))!important;z-index:50!important}
</style>
"""
        if 'id="neuroteq-tracklist-layout"' not in html:
            html = html.replace("</head>", tracklist_css + "</head>", 1)
        marks_css = """<style id="neuroteq-platform-marks">
.music-links a>.platform-name,.social-links a>span:first-child{display:inline-flex;align-items:center;gap:9px}.platform-mark{width:19px;height:19px;flex:0 0 19px;display:inline-block;color:currentColor;transition:color .2s cubic-bezier(.22,.61,.36,1)}
.music-links a:hover .platform-mark--spotify,.social-links a:hover .platform-mark--spotify{color:#1ed760}.music-links a:hover .platform-mark--apple,.social-links a:hover .platform-mark--apple{color:#fa243c}.music-links a:hover .platform-mark--soundcloud,.social-links a:hover .platform-mark--soundcloud{color:#ff5500}.music-links a:hover .platform-mark--youtube,.social-links a:hover .platform-mark--youtube,.music-links a:hover .platform-mark--youtube-music,.social-links a:hover .platform-mark--youtube-music{color:#ff0033}.music-links a:hover .platform-mark--tidal,.social-links a:hover .platform-mark--tidal{color:#7de8ff}.music-links a:hover .platform-mark--deezer,.social-links a:hover .platform-mark--deezer{color:#b26bff}.music-links a:hover .platform-mark--amazon,.social-links a:hover .platform-mark--amazon{color:#25d1da}.music-links a:hover .platform-mark--newgrounds,.social-links a:hover .platform-mark--newgrounds{color:#f90}.music-links a:hover .platform-mark--instagram,.social-links a:hover .platform-mark--instagram{color:#e4405f}.music-links a:hover .platform-mark--tiktok,.social-links a:hover .platform-mark--tiktok{color:#25f4ee}.music-links a:hover .platform-mark--twitch,.social-links a:hover .platform-mark--twitch{color:#a970ff}.music-links a:hover .platform-mark--musixmatch,.social-links a:hover .platform-mark--musixmatch{color:#ff5b5b}
@media(prefers-reduced-motion:reduce){.platform-mark{transition:none}}</style>
"""
        if 'id="neuroteq-platform-marks"' not in html:
            html = html.replace("</head>", marks_css + "</head>", 1)
        marks_script = """<script id="neuroteq-platform-marks-script">
(()=>{const n="http://www.w3.org/2000/svg",m={
"Spotify":["spotify",'<path d="M4 9c4-1.5 11-1 16 1.5M5 12.5c3.5-1.2 9-.8 13 1.2M6 16c3-1 7-.5 10 1"/>'],
"Apple Music":["apple",'<path d="M15 4v12M15 5l5-1v11M14 18c0 2-6 3-6 0s6-4 6-1M20 16c0 2-6 3-6 0s6-4 6-1"/>'],
"SoundCloud":["soundcloud",'<path d="M3 14v4m3-7v7m3-9v9m3-12v12m3-8v8M15 17h4a3 3 0 0 0 0-6 5 5 0 0 0-9-1"/>'],
"YouTube Music":["youtube-music",'<circle cx="12" cy="12" r="9"/><path d="m10 9 5 3-5 3z"/>'],"YouTube":["youtube",'<rect x="3" y="6" width="18" height="12" rx="4"/><path d="m10 9 5 3-5 3z"/>'],
"TIDAL":["tidal",'<path d="m4 8 2-2 2 2-2 2zm6 0 2-2 2 2-2 2zm6 0 2-2 2 2-2 2zm-3 6 2-2 2 2-2 2zm-6 0 2-2 2 2-2 2z"/>'],
"Deezer":["deezer",'<path d="M3 15h3v4H3zm5-3h3v7H8zm5-3h3v10h-3zm5-3h3v13h-3z"/>'],"Amazon Music":["amazon",'<path d="M5 19c4 2 10 2 14-1M7 16a3 3 0 1 1 6 0v2H9a2 2 0 0 1 0-4h4m1 4v-9h5v9"/>'],
"Newgrounds":["newgrounds",'<path d="M5 19V5h4l6 8V5h4v14h-4l-6-8v8z"/>'],"Instagram":["instagram",'<rect x="3.5" y="3.5" width="17" height="17" rx="5"/><circle cx="12" cy="12" r="4"/><circle cx="17.5" cy="6.5" r=".8"/>'],
"TikTok":["tiktok",'<path d="M14 4v10a4 4 0 1 1-3-4m3-6c1 3 2 4 5 5"/>'],"Twitch":["twitch",'<path d="M5 4h16v12l-4 4h-4l-3 3v-3H5zM10 8v5m6-5v5"/>'],"Musixmatch":["musixmatch",'<path d="M4 8h3v8H4zm5-3h3v14H9zm5 3h3v8h-3zm5 2h2v4h-2z"/>']};
function add(){document.querySelectorAll(".music-links a,.social-links a").forEach(a=>{let s=a.querySelector(":scope>.platform-name")||a.querySelector(":scope>span:first-child");if(!s||s.querySelector(".platform-mark"))return;let x=m[s.textContent.trim()];if(!x)return;let i=document.createElementNS(n,"svg");i.setAttribute("viewBox","0 0 24 24");i.setAttribute("class","platform-mark platform-mark--"+x[0]);i.setAttribute("aria-hidden","true");i.setAttribute("focusable","false");i.innerHTML=x[1];i.querySelectorAll("path,circle,rect").forEach(p=>{if(!p.hasAttribute("fill"))p.setAttribute("fill","none");p.setAttribute("stroke","currentColor");p.setAttribute("stroke-width","1.8");p.setAttribute("stroke-linecap","round");p.setAttribute("stroke-linejoin","round")});s.prepend(i)})}add();new MutationObserver(add).observe(document.body,{childList:true,subtree:true})})();
</script>"""
        if 'id="neuroteq-platform-marks-script"' not in html:
            html = html.replace("</body>", marks_script + "</body>", 1)
        index_file.write_text(html, encoding="utf-8")


    patch_exported_site()




if __name__ == "__main__":
    main()
