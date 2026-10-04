import base64
import json
import os
import urllib.parse
import urllib.request
from pathlib import Path

ARTIST_ID = "0bAOna6xN6OaEK7vRtmS1r"
API = "https://api.spotify.com/v1"


def request(url, headers=None, data=None):
    req = urllib.request.Request(url, headers=headers or {}, data=data)
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.load(response)


def main():
    client_id = os.environ["SPOTIFY_CLIENT_ID"]
    client_secret = os.environ["SPOTIFY_CLIENT_SECRET"]
    credentials = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    token = request(
        "https://accounts.spotify.com/api/token",
        headers={"Authorization": f"Basic {credentials}", "Content-Type": "application/x-www-form-urlencoded"},
        data=urllib.parse.urlencode({"grant_type": "client_credentials"}).encode(),
    )["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    albums = []
    url = f"{API}/artists/{ARTIST_ID}/albums?include_groups=album,single,compilation&market=US&limit=10"
    while url:
        page = request(url, headers)
        albums.extend(page["items"])
        url = page["next"]

    releases = []
    seen = set()
    for album in albums:
        if album["id"] in seen:
            continue
        seen.add(album["id"])
        tracks = request(f"{API}/albums/{album['id']}/tracks?limit=50", headers)["items"]
        artists = [artist["name"] for artist in album["artists"]]
        for track in tracks:
            for artist in track["artists"]:
                if artist["name"] not in artists:
                    artists.append(artist["name"])

        releases.append({
            "id": album["id"],
            "type": album.get("album_type", "single"),
            "title": album["name"],
            "date": album["release_date"],
            "artists": artists,
            "url": album["external_urls"]["spotify"],
            "cover": album["images"][0]["url"] if album["images"] else "",
            "tracks": [track["name"] for track in tracks],
        })

    releases.sort(key=lambda item: item["date"], reverse=True)
    Path("releases.json").write_text(json.dumps(releases, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
