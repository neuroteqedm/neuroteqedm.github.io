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

PLATFORM_LOGOS = {
    "spotify": ("spotify", "000000"),
    "apple-music": ("applemusic", "ffffff"),
    "soundcloud": ("soundcloud", "ff5500"),
    "youtube-music": ("youtubemusic", "ffffff"),
    "tidal": ("tidal", "ffffff"),
    "deezer": ("deezer", "b26bff"),
    "amazon-music": ("amazonmusic", "25d1da"),
    "newgrounds": ("newgrounds", "ff9900"),
    "youtube": ("youtube", "ff0033"),
    "instagram": ("instagram", "e4405f"),
    "tiktok": ("tiktok", "ffffff"),
    "twitch": ("twitch", "a970ff"),
    "musixmatch": ("musixmatch", "ffffff"),
}


def download_platform_logos():
    logo_dir = SITE / "images" / "platform-logos"
    logo_dir.mkdir(parents=True, exist_ok=True)

    def download(item):
        name, (icon, color) = item
        domain = {"spotify": "spotify.com", "apple-music": "music.apple.com", "soundcloud": "soundcloud.com", "youtube-music": "music.youtube.com", "tidal": "tidal.com", "deezer": "deezer.com", "amazon-music": "music.amazon.com", "newgrounds": "newgrounds.com", "youtube": "youtube.com", "instagram": "instagram.com", "tiktok": "tiktok.com", "twitch": "twitch.tv", "musixmatch": "musixmatch.com"}[name]
        url = "https://www.google.com/s2/favicons?domain={}&sz=128".format(domain)
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "NeuroteqSite/1.0", "Accept": "image/png"})
            with urllib.request.urlopen(request, timeout=20) as response:
                content = response.read(500_001)
                if response.headers.get_content_type() != "image/png" or not content.startswith(b"\x89PNG\r\n\x1a\n") or len(content) > 500_000:
                    return name, False
            (logo_dir / (name + ".png")).write_bytes(content)
            return name, True
        except Exception as exc:
            print("Could not download {} logo: {}".format(name, exc))
            return name, False

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        results = dict(pool.map(download, PLATFORM_LOGOS.items()))
    print("Downloaded {}/{} platform PNG logos.".format(sum(results.values()), len(PLATFORM_LOGOS)))
    return {name for name, ok in results.items() if ok}


def inject_platform_logos(html, downloaded):
    def key_for_href(href):
        if "music.youtube.com" in href:
            return "youtube-music"
        if "open.spotify.com" in href:
            return "spotify"
        if "music.apple.com" in href:
            return "apple-music"
        for host, name in (
            ("soundcloud.com", "soundcloud"), ("tidal.com", "tidal"),
            ("deezer.com", "deezer"), ("amazon.com", "amazon-music"),
            ("newgrounds.com", "newgrounds"), ("youtube.com", "youtube"),
            ("instagram.com", "instagram"), ("tiktok.com", "tiktok"),
            ("twitch.tv", "twitch"), ("musixmatch.com", "musixmatch"),
        ):
            if host in href:
                return name
        return None

    for list_class in ("music-links", "social-links"):
        pattern = r'(<ul[^>]*class="[^"]*\b' + list_class + r'\b[^"]*"[^>]*>)(.*?)(</ul>)'
        match = re.search(pattern, html, flags=re.S)
        if not match:
            continue

        def add_image(anchor):
            href = re.search(r'\bhref="([^"]+)"', anchor.group(0))
            if not href:
                return anchor.group(0)
            name = key_for_href(href.group(1))
            if not name or name not in downloaded:
                return anchor.group(0)
            img = '<img class="platform-logo" src="/images/platform-logos/{}.png" width="22" height="22" alt="" aria-hidden="true">'.format(name)
            return anchor.group(0) + img

        links = re.sub(r'<a\b[^>]*>', add_image, match.group(2))
        html = html[:match.start(2)] + links + html[match.end(2):]
    return html


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
        'onMouseEnter:()=>n(!0)': 'onMouseEnter:e=>{let t=e.currentTarget;clearTimeout(t._tracklistCloseTimer);let r=t.querySelector(".tracklist-popover");r&&r.classList.remove("tracklist-closing");n(!0)}',
        'onMouseLeave:()=>n(!1)': 'onMouseLeave:e=>{if(e.currentTarget.contains(e.relatedTarget))return;let t=e.currentTarget.querySelector(".tracklist-popover");t&&t.classList.add("tracklist-closing");clearTimeout(e.currentTarget._tracklistCloseTimer);e.currentTarget._tracklistCloseTimer=setTimeout(()=>n(!1),150)}',
        'className:"tracklist-popover",id:g,children:': 'className:"tracklist-popover",id:g,onMouseEnter:e=>{let t=e.currentTarget.closest(".release-tracks");t&&clearTimeout(t._tracklistCloseTimer);e.currentTarget.classList.remove("tracklist-closing")},onMouseLeave:e=>{let t=e.currentTarget.closest(".release-tracks");if(t&&!t.contains(e.relatedTarget)){e.currentTarget.classList.add("tracklist-closing");clearTimeout(t._tracklistCloseTimer);t._tracklistCloseTimer=setTimeout(()=>n(!1),150)}},children:',
        'onClick:()=>n(!1)': 'onClick:e=>{let t=e.currentTarget.closest(".release-tracks"),r=t?.querySelector(".tracklist-popover");r&&r.classList.add("tracklist-closing");t&&(clearTimeout(t._tracklistCloseTimer),t._tracklistCloseTimer=setTimeout(()=>n(!1),150))}',
        'onClick:()=>n(!t)': 'onClick:e=>{let r=e.currentTarget.closest(".release-tracks"),i=r?.querySelector(".tracklist-popover");if(!t){clearTimeout(r?._tracklistCloseTimer);n(!0);return}i&&i.classList.add("tracklist-closing");r&&(clearTimeout(r._tracklistCloseTimer),r._tracklistCloseTimer=setTimeout(()=>n(!1),150))}',
        'onBlur:t=>{t.currentTarget.parentElement?.contains(t.relatedTarget)||n(!1)}': 'onBlur:e=>{let t=e.currentTarget.parentElement;if(t?.contains(e.relatedTarget))return;let r=t?.querySelector(".tracklist-popover");r&&r.classList.add("tracklist-closing");t&&(clearTimeout(t._tracklistCloseTimer),t._tracklistCloseTimer=setTimeout(()=>n(!1),150))}',
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
        logos_downloaded = download_platform_logos()
        html = inject_platform_logos(html, logos_downloaded)
        html = re.sub(
            r'(<footer\b[^>]*>.*?</footer>)',
            lambda match: re.sub(
                r'Query Records\.?</p>',
                'Query Records</p>',
                re.sub(r'<a\b[^>]*>Query Records</a>', 'Query Records', match.group(1)),
                count=1,
            ),
            html,
            count=1,
            flags=re.S,
        )

        tracklist_css = """
<style id="neuroteq-tracklist-layout">.release:has(.tracklist-popover){position:relative;z-index:9999}
.release-tracks{position:relative}
.release-tracks:has(.tracklist-popover){padding-bottom:8px!important;margin-bottom:-8px!important}
a[href="#label-heading"].text-link{display:none!important}
footer a[href="#label-heading"]{pointer-events:none;text-decoration:none;color:inherit}.tracklist-popover{position:absolute!important;top:calc(100% - 3px)!important;bottom:auto!important;left:-9px!important;right:auto!important;width:calc(100% + 18px)!important;max-height:min(520px,calc(100vh - 24px))!important;overflow:auto!important;z-index:10000!important}
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
.release { border: 0 !important; border-radius: 0 !important; background: transparent !important; padding: 0 !important; }
.release-art { border-radius: 14px; transition: filter .28s ease, transform .32s cubic-bezier(.2,.7,.2,1); }
.release:hover .release-art { filter: brightness(1.045); transform: scale(1.012); }
.release-meta { margin-top: 14px; }
.tracklist-head h4 { font-size: 1.2rem; }
.tracklist-songs a { min-height: 64px; padding: 15px 16px; }
.track-title { font-size: 1.0625rem; }
.tracklist-popover { border-radius: 18px; overflow: hidden; animation: tracklist-window-in .24s cubic-bezier(.2,.7,.2,1) both; transform-origin: top left; }
.tracklist-head { border-radius: 17px 17px 0 0; }
.tracklist-popover.tracklist-closing { animation: tracklist-window-out .15s ease both !important; pointer-events: none !important; }
@keyframes tracklist-window-in { from { opacity: 0; transform: translateY(9px) scale(.985); } to { opacity: 1; transform: translateY(0) scale(1); } }
@keyframes tracklist-window-out { from { opacity: 1; transform: translateY(0) scale(1); } to { opacity: 0; transform: translateY(3px) scale(.99); } }
.tracklist-head { border-radius: 13px 13px 0 0; }
.tracklist-close { border-radius: 50%; transition: color .18s ease, background-color .18s ease; }
.tracklist-close:hover { background: #2b1d31; }
.release-tabs .release-tab-list { border: 0; gap: 8px; margin-bottom: 22px; }
.release-tabs .release-tab { min-height: 40px; border: 1px solid transparent; border-radius: 8px; padding: 7px 14px; transition: color .18s ease, background-color .18s ease, border-color .18s ease; }
.release-tabs .release-tab[data-state=active] { background: #1a151e; border-color: #49394f; }
.release-tabs .release-tab:after { display: none; }
.show-releases { border-radius: 8px; }
a, button { transition: color .18s ease, background-color .18s ease, border-color .18s ease, box-shadow .18s ease, opacity .18s ease, transform .2s cubic-bezier(.2,.7,.2,1); }
.tracklist-songs a { transition: color .18s ease, background-color .18s ease, transform .18s ease; }
.tracklist-songs a:hover { background: #1a151e; }
.release-link svg, .tracklist-spotify svg, .show-releases svg { transition: transform .2s ease; }
.release-link:hover svg, .tracklist-spotify:hover svg, .show-releases:hover svg { transform: translate(2px,-2px); }
.music-links { border: 0; gap: 10px 22px; }
.music-links li, .music-links li:hover { border: 0; border-radius: 0; background: transparent; overflow: visible; }
.music-links a { grid-template-columns: 24px minmax(0,1fr) 18px; align-items: center; column-gap: 10px; min-height: 60px; padding: 8px 0; border-radius: 0; }
.music-links a::before { content: ""; display: block; width: 22px; height: 22px; grid-column: 1; grid-row: 1 / span 2; align-self: center; background-position: center; background-repeat: no-repeat; background-size: contain; }
.music-links a .platform-name { grid-column: 2; grid-row: 1; }
.music-links a .platform-detail { grid-column: 2; grid-row: 2; }
.music-links a > svg { grid-column: 3; grid-row: 1 / span 2; }
.music-links a::before { background-repeat: no-repeat; background-position: center; background-size: contain; transition: transform .22s cubic-bezier(.2,.7,.2,1), filter .2s ease; }
.music-links a[href*="spotify.com"]::before { background-image: url("https://cdn.simpleicons.org/spotify/000000"), radial-gradient(circle, #1ed760 61%, transparent 63%); background-size: 75% 75%, 100% 100%; background-position: center, center; border-radius: 50%; }
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
.music-links a[href*="amazon.com"]::before { background-image: url("https://api.iconify.design/simple-icons/amazonmusic.svg?color=%2325d1da"); }
.music-links a:hover::before { transform: scale(1.12); }
.social-links { gap: 10px 22px; }
.social-links li, .social-links li:hover { border: 0 !important; border-radius: 0 !important; background: transparent !important; padding: 0 !important; }
.social-links a { display: grid; grid-template-columns: 24px minmax(0,1fr) 16px; align-items: center; gap: 1px 10px; min-height: 56px; padding: 8px 0; border-radius: 0; transition: color .2s ease, opacity .2s ease; }
.social-links a::before { content: ""; display: block; width: 20px; height: 20px; grid-column: 1; grid-row: 1 / span 2; align-self: center; background-position: center; background-repeat: no-repeat; background-size: contain; transition: transform .22s cubic-bezier(.2,.7,.2,1), opacity .2s ease; }
.social-links a > span:first-child { grid-column: 2; grid-row: 1; }
.social-links a .social-handle { grid-column: 2; grid-row: 2; }
.social-links a > svg { grid-column: 3; grid-row: 1 / span 2; transition: transform .2s ease, color .2s ease; }
.social-links a:hover::before { transform: scale(1.12); }
.social-links a:hover > svg { transform: translate(2px,-2px); }
.social-links a[href*="youtube.com"]::before { background-image: url("https://cdn.simpleicons.org/youtube/FF0033"); }
.social-links a[href*="instagram.com"]::before { background-image: url("https://cdn.simpleicons.org/instagram/E4405F"); }
.social-links a[href*="tiktok.com"]::before { background-image: url("https://cdn.simpleicons.org/tiktok/FFFFFF"); }
.social-links a[href*="twitch.tv"]::before { background-image: url("https://cdn.simpleicons.org/twitch/A970FF"); }
.social-links a[href*="musixmatch.com"]::before { background-image: url("https://upload.wikimedia.org/wikipedia/commons/0/0f/Musixmatch_Icon.svg"); }
.label-note { border: 1px solid #49394f; border-left: 2px solid var(--accent); border-radius: 16px; background: #100e12; padding: 22px; }
.timeline li:before { border-radius: 50%; }
.site-footer a { border-radius: 6px; padding-inline: 11px; transition: color .18s ease, background-color .18s ease; }
.site-footer a:hover { background: #1a151e; }
@media (max-width:760px) {
  .release { border: 0 !important; border-radius: 0 !important; background: transparent !important; padding: 0 !important; }
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

/* Noticeable, lightweight feedback for controls across the page */
a, button { transform-origin: center; }
a:hover { text-decoration-color: currentColor; text-shadow: 0 0 12px rgba(220,48,247,.32); }
button:hover { filter: brightness(1.12); }
a:active, button:active { transform: translateY(0) scale(.97); }
a:focus-visible, button:focus-visible { outline: 2px solid #df35fa; outline-offset: 4px; }
.music-links a, .social-links a, .site-footer a, .release-link, .show-releases, .tracklist-spotify, .release-tabs .release-tab, .tracklist-close { transform: translateY(0); transition: transform .2s cubic-bezier(.2,.7,.2,1), color .2s ease, background-color .2s ease, border-color .2s ease, box-shadow .2s ease; }
.music-links a:hover, .social-links a:hover, .site-footer a:hover, .release-link:hover, .show-releases:hover, .tracklist-spotify:hover { transform: translateY(-3px); }
.music-links a:active, .social-links a:active, .site-footer a:active, .release-link:active, .show-releases:active, .tracklist-spotify:active { transform: translateY(0) scale(.98); }
.release-art { transition: transform .28s cubic-bezier(.2,.7,.2,1), filter .24s ease, box-shadow .24s ease; }
.release:hover .release-art, .release-tracks:hover .release-art { transform: translateY(-4px) scale(1.035); filter: brightness(1.1); box-shadow: 0 12px 34px rgba(222,35,255,.18); }
.tracklist-songs a { border-radius: 9px; transition: background-color .18s ease, color .18s ease, transform .18s cubic-bezier(.2,.7,.2,1); }
.tracklist-songs a:hover { background: rgba(220,48,247,.12)!important; transform: translateX(5px); }
.tracklist-songs a:active { transform: translateX(2px) scale(.99); }
.release-tabs .release-tab:hover { transform: translateY(-2px); background: rgba(218,47,245,.12); }
.release-tabs .release-tab:active { transform: scale(.97); }
.tracklist-close:hover { transform: rotate(90deg); background: rgba(220,48,247,.16); }
.tracklist-popover { border-radius: 20px!important; }
.music-links a:hover::before, .social-links a:hover::before { filter: drop-shadow(0 0 7px currentColor); }
@media (prefers-reduced-motion: reduce) { a, button, .release-art, .tracklist-songs a, .music-links a, .social-links a { transition-duration: .01ms!important; } .release:hover .release-art, .release-tracks:hover .release-art, .music-links a:hover, .social-links a:hover, .tracklist-songs a:hover { transform: none!important; } }

@media (prefers-reduced-motion: reduce) {
  a, button, .tracklist-songs a, .release-link, .tracklist-spotify, .show-releases, .music-links a, .music-links a::before, .music-links a > svg, .social-links li, .social-links a, .social-links a::before, .social-links a > svg, .release-tabs .release-tab, .tracklist-close, .site-footer a { transition: none !important; }
  .release-art, .release:hover .release-art { transition: none !important; transform: none; }
  .tracklist-popover, .tracklist-popover.tracklist-closing { animation: none !important; }
}
</style>
"""
        if 'id="neuroteq-tracklist-layout"' not in html:
            html = html.replace("</head>", tracklist_css + "</head>", 1)
        logo_css = """<style id="neuroteq-platform-logo-images">
.music-links a::before, .social-links a::before { content: none !important; display: none !important; background: none !important; }
.platform-logo { width: 22px; height: 22px; display: block; grid-column: 1; grid-row: 1 / span 2; align-self: center; object-fit: contain; transition: transform .22s cubic-bezier(.2,.7,.2,1), filter .2s ease; }
.social-links .platform-logo { width: 20px; height: 20px; }
.platform-logo[src*="spotify.png"] { box-sizing: border-box; padding: 3px; border-radius: 50%; background: #1ed760; }
.music-links a:hover .platform-logo, .social-links a:hover .platform-logo { transform: scale(1.08); }
</style>"""
        html = html.replace("</head>", logo_css + "</head>", 1)

        index_file.write_text(html, encoding="utf-8")

    patch_exported_site()

if __name__ == "__main__":
    main()


# React renders the platform links after loading this HTML shell. Insert their
# image assets after the links exist, then keep them if React redraws that block.
if __name__ == "__main__":
    rendered_index = SITE / "index.html"
    rendered_html = rendered_index.read_text(encoding="utf-8")
    logo_assets = {
        name: "/images/platform-logos/{}.png".format(name)
        for name in PLATFORM_LOGOS
        if (SITE / "images" / "platform-logos" / (name + ".png")).is_file()
    }
    logo_assets.setdefault("newgrounds", "https://cdn.simpleicons.org/newgrounds/ff9900")
    logo_script = """<script id="neuroteq-platform-logo-injector">
(() => {
  const assets = __ASSETS__;
  const platform = (host) => {
    if (host === "music.youtube.com") return "youtube-music";
    if (host === "music.apple.com") return "apple-music";
    if (host === "open.spotify.com") return "spotify";
    if (host.endsWith("soundcloud.com")) return "soundcloud";
    if (host.endsWith("tidal.com")) return "tidal";
    if (host.endsWith("deezer.com")) return "deezer";
    if (host.endsWith("amazon.com")) return "amazon-music";
    if (host.endsWith("newgrounds.com")) return "newgrounds";
    if (host.endsWith("youtube.com")) return "youtube";
    if (host.endsWith("instagram.com")) return "instagram";
    if (host.endsWith("tiktok.com")) return "tiktok";
    if (host.endsWith("twitch.tv")) return "twitch";
    if (host.endsWith("musixmatch.com")) return "musixmatch";
    return null;
  };
  const addLogos = () => document.querySelectorAll(".music-links a[href], .social-links a[href]").forEach((link) => {
    if (link.querySelector("img.platform-logo")) return;
    let name;
    try { name = platform(new URL(link.href, location.href).hostname); } catch (_) { return; }
    if (!name || !assets[name]) return;
    const image = document.createElement("img");
    image.className = "platform-logo";
    image.src = assets[name];
    image.width = 22;
    image.height = 22;
    image.alt = "";
    image.setAttribute("aria-hidden", "true");
    link.insertBefore(image, link.firstChild);
  });
  addLogos();
  new MutationObserver(addLogos).observe(document.body, { childList: true, subtree: true });
})();
</script>""".replace("__ASSETS__", json.dumps(logo_assets, separators=(",", ":")))
    if "neuroteq-platform-logo-injector" not in rendered_html:
        rendered_html = rendered_html.replace("</body>", logo_script + "</body>", 1)
        rendered_index.write_text(rendered_html, encoding="utf-8")


# Replace site favicons with platform brand marks and keep the PNGs local.
if __name__ == "__main__":
    import cairosvg

    def download_official_png(item):
        name, (icon, color) = item
        url = "https://cdn.simpleicons.org/{}/{}".format(icon, color)
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "NeuroteqSite/1.0", "Accept": "image/svg+xml"})
            with urllib.request.urlopen(request, timeout=20) as response:
                svg = response.read(250_001)
            if len(svg) > 250_000 or b"<svg" not in svg[:1000].lower():
                return name, False
            png = cairosvg.svg2png(bytestring=svg, output_width=128, output_height=128)
            if not png.startswith(b"\x89PNG\r\n\x1a\n"):
                return name, False
            (SITE / "images" / "platform-logos" / (name + ".png")).write_bytes(png)
            return name, True
        except Exception as exc:
            print("Could not create official {} PNG: {}".format(name, exc))
            return name, False

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        official_results = dict(pool.map(download_official_png, PLATFORM_LOGOS.items()))
    missing_official = sorted(name for name, ok in official_results.items() if not ok)
    print("Built {}/{} official brand PNGs.".format(sum(official_results.values()), len(PLATFORM_LOGOS)))
    if missing_official:
        print("Could not build: {}".format(", ".join(missing_official)))
    logo_index = SITE / "index.html"
    if logo_index.exists():
        page = logo_index.read_text(encoding="utf-8")
        page = page.replace("https://cdn.simpleicons.org/newgrounds/ff9900", "/images/platform-logos/newgrounds.png")
        logo_index.write_text(page, encoding="utf-8")


# Use recognizable platform marks for the two brands missing from Simple Icons.
if __name__ == "__main__":
    import cairosvg

    fallback_logos = {
        "amazon-music": "https://api.iconify.design/simple-icons/amazonmusic.svg?color=%2325d1da",
        "musixmatch": "https://upload.wikimedia.org/wikipedia/commons/0/0f/Musixmatch_Icon.svg",
    }

    def download_fallback_png(item):
        name, url = item
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "NeuroteqSite/1.0", "Accept": "image/svg+xml"})
            with urllib.request.urlopen(request, timeout=20) as response:
                svg = response.read(250_001)
            if len(svg) > 250_000 or b"<svg" not in svg[:1000].lower():
                return name, False
            png = cairosvg.svg2png(bytestring=svg, output_width=128, output_height=128)
            if not png.startswith(b"\x89PNG\r\n\x1a\n"):
                return name, False
            (SITE / "images" / "platform-logos" / (name + ".png")).write_bytes(png)
            return name, True
        except Exception as exc:
            print("Could not create {} fallback PNG: {}".format(name, exc))
            return name, False

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        fallback_results = dict(pool.map(download_fallback_png, fallback_logos.items()))
    print("Built {}/2 fallback platform PNGs.".format(sum(fallback_results.values())))


# Correct the Spotify mark and keep all platform logos legible at link size.
if __name__ == "__main__":
    try:
        spotify_url = "https://cdn.simpleicons.org/spotify/1ed760"
        request = urllib.request.Request(spotify_url, headers={"User-Agent": "NeuroteqSite/1.0", "Accept": "image/svg+xml"})
        with urllib.request.urlopen(request, timeout=20) as response:
            spotify_svg = response.read(250_001)
        if len(spotify_svg) <= 250_000 and b"<svg" in spotify_svg[:1000].lower():
            spotify_png = cairosvg.svg2png(bytestring=spotify_svg, output_width=128, output_height=128)
            if spotify_png.startswith(b"\x89PNG\r\n\x1a\n"):
                (SITE / "images" / "platform-logos" / "spotify.png").write_bytes(spotify_png)
    except Exception as exc:
        print("Could not update Spotify brand mark: {}".format(exc))

    logo_index = SITE / "index.html"
    if logo_index.exists():
        page = logo_index.read_text(encoding="utf-8")
        logo_css = """<style id="neuroteq-platform-logo-refinements">
.platform-logo { width: 26px; height: 26px; }
.social-links .platform-logo { width: 24px; height: 24px; }
.music-links a { grid-template-columns: 30px minmax(0,1fr) 18px; }
.social-links a { grid-template-columns: 28px minmax(0,1fr) 16px; }
.platform-logo[src*="spotify.png"] { padding: 0 !important; border-radius: 0 !important; background: transparent !important; }
</style>"""
        if 'id="neuroteq-platform-logo-refinements"' not in page:
            page = page.replace("</head>", logo_css + "</head>", 1)
            logo_index.write_text(page, encoding="utf-8")


# Keep Spotify's black mark on its green disc. The music service glyphs are white
# on this dark page; invert their one-color PNGs so the negative cutouts read white.
if __name__ == "__main__":
    spotify_url = "https://upload.wikimedia.org/wikipedia/commons/a/a7/Spotify-icon.png"
    try:
        request = urllib.request.Request(spotify_url, headers={"User-Agent": "NeuroteqSite/1.0", "Accept": "image/png"})
        with urllib.request.urlopen(request, timeout=20) as response:
            spotify_png = response.read(1_000_001)
        if len(spotify_png) <= 1_000_000 and spotify_png.startswith(b"\x89PNG\r\n\x1a\n"):
            (SITE / "images" / "platform-logos" / "spotify.png").write_bytes(spotify_png)
    except Exception as exc:
        print("Could not update Spotify PNG: {}".format(exc))

    logo_index = SITE / "index.html"
    if logo_index.exists():
        page = logo_index.read_text(encoding="utf-8")
        logo_css = """<style id="neuroteq-platform-logo-contrast">
.platform-logo[src*="apple-music.png"], .platform-logo[src*="youtube-music.png"] { filter: invert(1); }
.platform-logo[src*="amazon-music.png"] { width: 36px; height: 30px; }
</style>"""
        if 'id="neuroteq-platform-logo-contrast"' not in page:
            page = page.replace("</head>", logo_css + "</head>", 1)
            logo_index.write_text(page, encoding="utf-8")


# Keep the Apple Music and YouTube Music marks visible on the dark background.
if __name__ == "__main__":
    logo_index = SITE / "index.html"
    if logo_index.exists():
        page = logo_index.read_text(encoding="utf-8")
        logo_css = """<style id="neuroteq-platform-logo-visible">
.platform-logo[src*="apple-music.png"], .platform-logo[src*="youtube-music.png"] { filter: none !important; }
</style>"""
        if 'id="neuroteq-platform-logo-visible"' not in page:
            page = page.replace("</head>", logo_css + "</head>", 1)
            logo_index.write_text(page, encoding="utf-8")


# Render the Spotify mark in its familiar black-on-green treatment.
if __name__ == "__main__":
    try:
        spotify_url = "https://cdn.simpleicons.org/spotify/000000"
        request = urllib.request.Request(spotify_url, headers={"User-Agent": "NeuroteqSite/1.0", "Accept": "image/svg+xml"})
        with urllib.request.urlopen(request, timeout=20) as response:
            spotify_svg = response.read(250_001)
        if len(spotify_svg) <= 250_000 and b"<svg" in spotify_svg[:1000].lower():
            spotify_png = cairosvg.svg2png(bytestring=spotify_svg, output_width=128, output_height=128)
            if spotify_png.startswith(b"\x89PNG\r\n\x1a\n"):
                (SITE / "images" / "platform-logos" / "spotify.png").write_bytes(spotify_png)
    except Exception as exc:
        print("Could not update Spotify brand mark: {}".format(exc))

    logo_index = SITE / "index.html"
    if logo_index.exists():
        page = logo_index.read_text(encoding="utf-8")
        logo_css = """<style id="neuroteq-spotify-final-mark">
.platform-logo[src*=\"spotify.png\"] { box-sizing:border-box; width:26px!important; height:26px!important; padding:3px!important; border-radius:50%!important; background:#1ed760!important; object-fit:contain; filter:none!important; }
</style>"""
        if 'id="neuroteq-spotify-final-mark"' not in page:
            page = page.replace("</head>", logo_css + "</head>", 1)
            logo_index.write_text(page, encoding="utf-8")


# Apple Music's favicon is the current full-colour platform mark.
if __name__ == "__main__":
    try:
        apple_url = "https://www.google.com/s2/favicons?domain=music.apple.com&sz=128"
        request = urllib.request.Request(apple_url, headers={"User-Agent": "NeuroteqSite/1.0", "Accept": "image/png"})
        with urllib.request.urlopen(request, timeout=20) as response:
            apple_png = response.read(500_001)
        if len(apple_png) <= 500_000 and apple_png.startswith(b"\x89PNG\r\n\x1a\n"):
            (SITE / "images" / "platform-logos" / "apple-music.png").write_bytes(apple_png)
    except Exception as exc:
        print("Could not update Apple Music logo: {}".format(exc))
