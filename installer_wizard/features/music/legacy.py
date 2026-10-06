from features.music import catalog, naming
from features.music.db import db


def migrate() -> int:
    rows = db.rows("SELECT id, artist, album_artist, album FROM tracks WHERE lower(album)='album sconosciuto' OR lower(artist)='artista sconosciuto' "
                   "OR lower(album_artist)='artista sconosciuto'")
    for row in rows:
        artist = naming.UNKNOWN_ARTIST if naming.no_artist(row["artist"]) else row["artist"]
        album_artist = naming.UNKNOWN_ARTIST if naming.no_artist(row["album_artist"]) else row["album_artist"]
        album = naming.SINGLES if row["album"].lower() == "album sconosciuto" else row["album"]
        db.run("UPDATE tracks SET artist=?, album_artist=?, album=?, album_key=?, artist_key=? WHERE id=?",
               (artist, album_artist, album, catalog.key(album_artist, album), catalog.key(artist), row["id"]))
    return len(rows)
