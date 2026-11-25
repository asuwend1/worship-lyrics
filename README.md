# Worship Lyrics

A single-page app for small-group worship at home: lyrics on the living-room TV, highlighted line by line, with worship sessions (Welcome, songs, Prayer, Sharing, Prayer Requests).

**Open it:** https://asuwend1.github.io/worship-lyrics/ (Chrome or Edge recommended)

## Where your data lives
Nothing is stored in this repository. Songs and sessions are saved either in your browser, or (recommended) in a folder you choose, such as a Google Drive folder:

- `Song Title - Artist.txt`: one plain-text lyrics file per song
- `sessions/2026-11-28 - Home Family Caregroup.txt`: one run-sheet per meeting
- `_worship-app.json`: timing, song order and background settings
- `audio/`: backing tracks you add
- `_trash/`: deleted songs and sessions, so you can restore them

## Quick start
1. Open the app, click **Choose songs folder…** in the sidebar, and pick a folder in Google Drive.
2. **+ New song**: paste lyrics (Verse/Chorus or Bait/Reff labels are detected).
3. Build a session in the sidebar, connect the laptop to the TV, and press **Open TV window** (or **F** for full screen).
4. Press **?** in the app for all keyboard shortcuts.

## Development
The whole app is `index.html`: plain HTML, CSS and JavaScript with no build step. To work on it, open the file in Chrome, or serve the folder with `python3 -m http.server`.
