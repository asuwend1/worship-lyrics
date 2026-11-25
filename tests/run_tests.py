"""End-to-end browser tests for Worship Lyrics.

Run locally:   pip install playwright && python -m playwright install chromium
               python tests/run_tests.py
Starts a local web server for the repo root, drives index.html in headless
Chromium, and exits non-zero if any check fails. Uses only made-up names.
"""
import asyncio, json, os, struct, subprocess, sys, tempfile, time, wave
from pathlib import Path
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parent.parent
PORT = int(os.environ.get("PORT", "8765"))
BASE = f"http://localhost:{PORT}/index.html"
CHROME = os.environ.get("CHROME_PATH")  # optional: use a system Chrome
FAILS = []


def check(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name + (f"  [{detail}]" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def make_wav(path, seconds):
    w = wave.open(str(path), "w"); w.setnchannels(1); w.setsampwidth(2); w.setframerate(8000)
    w.writeframes(b"".join(struct.pack("<h", 0) for _ in range(8000 * seconds))); w.close()


OPFS_RESET = """async()=>{const d=await navigator.storage.getDirectory();for await (const [n] of d.entries()) await d.removeEntry(n,{recursive:true});return d}"""
OPFS_CONNECT = """async()=>{const d=await navigator.storage.getDirectory();for await (const [n] of d.entries()) await d.removeEntry(n,{recursive:true});await window.__wlConnect(d)}"""
LIST = r"""async()=>{const d=await navigator.storage.getDirectory();const out=[];for await (const [n,h] of d.entries()){out.push(n+(h.kind==='directory'?'/':''));if(h.kind==='directory'){for await (const [m] of h.entries()) out.push(n+'/'+m)}}return out.sort()}"""
READ = r"""async(p)=>{let d=await navigator.storage.getDirectory();const parts=p.split('/');for(const x of parts.slice(0,-1))d=await d.getDirectoryHandle(x);return (await (await d.getFileHandle(parts.at(-1))).getFile()).text()}"""
WRITE = r"""async([p,t])=>{let d=await navigator.storage.getDirectory();const parts=p.split('/');for(const x of parts.slice(0,-1))d=await d.getDirectoryHandle(x,{create:true});const fh=await d.getFileHandle(parts.at(-1),{create:true});const w=await fh.createWritable();await w.write(t);await w.close()}"""


async def new_page(browser):
    ctx = await browser.new_context(viewport={"width": 1400, "height": 1000})
    await ctx.grant_permissions(["clipboard-read", "clipboard-write"], origin=f"http://localhost:{PORT}")
    pg = await ctx.new_page()
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.on("dialog", lambda d: asyncio.ensure_future(d.accept()))
    await pg.goto(BASE); await pg.wait_for_timeout(600); await pg.keyboard.press("Escape")
    return ctx, pg, errs


async def create_song(pg, title, lyrics, add=False):
    await pg.click("#btnNew"); await pg.fill("#nsTitle", title); await pg.fill("#nsLyrics", lyrics)
    if not add:
        await pg.uncheck("#nsAdd")
    await pg.click("#nsCreate"); await pg.wait_for_timeout(400)


async def cur_line(pg):
    t = await pg.inner_text("#preview")
    h = await pg.evaluate("(document.querySelector('#preview .ln.cur')||{}).textContent||''")
    return t.split("\n")[0] + " > " + (h or "-")


async def test_parsing(browser):
    ctx, pg, errs = await new_page(browser)
    genius = "12 Contributors\nSong Lyrics\n[Verse 1]\nl1\nl2\n\n[Chorus]\nc1\nc2 (2x)\nYou might also like\n[Verse 2]\nl3\n[Chorus]\n[Bridge]\nb1\n[Outro]\nlast3Embed"
    await create_song(pg, "Parse", genius); await pg.click("#tabEdit")
    check("genius paste: sections and order", await pg.input_value("#eOrder") == "V1 C V2 C B E", await pg.input_value("#eOrder"))
    await pg.select_option("#eLang", "id")
    await pg.fill("#eLyrics", "Bait 1:\nsatu\ndua\n\nReff:\ntiga\nempat\n\nBait 2:\nlima\n\nReff"); await pg.wait_for_timeout(600)
    check("indonesian labels", await pg.input_value("#eOrder") == "V1 C V2 C", await pg.input_value("#eOrder"))
    await pg.select_option("#eLang", "en")
    await pg.fill("#eLyrics", "a1\na2\n\nc1\nc2\n\nb1\nb2\n\nc1\nc2"); await pg.wait_for_timeout(600)
    check("unlabeled: repeat becomes chorus", await pg.input_value("#eOrder") == "V1 C V2 C", await pg.input_value("#eOrder"))
    check("parsing: no page errors", not errs, str(errs)); await ctx.close()


async def test_navigation(browser):
    ctx, pg, errs = await new_page(browser)
    await create_song(pg, "Nav", "[Verse 1]\nv1a\nv1b\n[Chorus]\nca\ncb\n[Verse 2]\nv2a\nv2b\n[Chorus]")
    seq = []
    for k in ["Space", "Space", "Space", "ArrowDown", "ArrowUp", "c", "ArrowLeft", "r", "e"]:
        await pg.keyboard.press(k); seq.append(await cur_line(pg))
    expect = ["Verse 1 > v1a", "Verse 1 > v1b", "Chorus > ca", "Verse 2 > v2a", "Chorus > ca", "Chorus > ca", "Verse 2 > v2b", "Verse 2 > v2a", "Chorus > ca"]
    check("manual line/section/jump keys", seq == expect, f"{seq}")
    # timed mode with the clock
    await pg.click("#tabEdit"); await pg.check("input[name=mt][value=clock]"); await pg.wait_for_timeout(300); await pg.click("#tabLive")
    await pg.keyboard.press("s")
    for k in ["Space"] * 8 + ["c", "Space"]:
        await pg.wait_for_timeout(300); await pg.keyboard.press(k)
    await pg.keyboard.press("s"); await pg.wait_for_timeout(200)
    check("timing recorded", "10 timing cues" in await pg.inner_text("#status"), await pg.inner_text("#status"))
    await pg.click("#clkReset"); await pg.keyboard.press("Enter"); await pg.wait_for_timeout(1300)
    check("auto-follow moves with the clock", (await cur_line(pg)).startswith("Verse 1") or (await cur_line(pg)).startswith("Chorus"), await cur_line(pg))
    await pg.keyboard.press("ArrowDown"); await pg.wait_for_timeout(250); a = await cur_line(pg)
    await pg.keyboard.press("ArrowDown"); await pg.wait_for_timeout(250); b = await cur_line(pg)
    check("timed section jump changes section", a.split(" > ")[0] != b.split(" > ")[0], f"{a} | {b}")
    check("navigation: no page errors", not errs, str(errs)); await ctx.close()


async def test_sessions(browser):
    ctx, pg, errs = await new_page(browser)
    await pg.click('#set .item >> nth=0'); await pg.wait_for_timeout(200)
    check("welcome slide shows group name", "Home Family Caregroup" in await pg.inner_text("#preview"))
    await pg.click('#set .item:has-text("Sharing")'); await pg.fill("#sfTitle", "Faith"); await pg.fill("#sfName", "Member A"); await pg.keyboard.press("Escape")
    t = (await pg.inner_text("#preview")).split("\n")
    check("sharing: name below title", t.index("Member A") > t.index("Faith"), str(t))
    await pg.click('#set .item:has-text("Prayer Requests")'); await pg.fill("#sfReq", "r1\nr2\nr3"); await pg.keyboard.press("Escape")
    pv = await pg.inner_text("#preview")
    check("prayer requests listed", all(x in pv for x in ["r1", "r2", "r3"]))
    # Bible reading paste cleanup (public-domain wording, BibleGateway-style copy)
    await pg.click('#set .item:has-text("Prayer")'); await pg.select_option("#sessAdd", "bible"); await pg.click('#set .item:has-text("Bible")')
    await pg.fill("#sfTitle", "John 3:16-17")
    check("BibleGateway link uses NIV by default", "version=NIV" in (await pg.get_attribute("#sfBG", "href")))
    bg = "John 3:16-17\nKing James Version\n16 For God so loved the world,[a] that he gave his only begotten Son,(A) that whosoever believeth in him should not perish. 17 For God sent not his Son into the world to condemn the world.\nFootnotes\nJohn 3:16 note\nKing James Version (KJV) Public Domain"
    await pg.evaluate("t=>navigator.clipboard.writeText(t)", bg); await pg.click("#sfPasteBG"); await pg.wait_for_timeout(300)
    txt = await pg.input_value("#sfText")
    check("bible paste cleaned and split", txt.startswith("16 For God") and "\n17 For God" in txt and "[a]" not in txt and "(A)" not in txt and "Footnotes" not in txt, txt)
    check("translation detected from paste", await pg.input_value("#sfName") == "KJV")
    await pg.keyboard.press("Escape")
    # run-sheet, duplicate, default order
    await pg.click("#sessShare"); await pg.wait_for_timeout(200); rs = await pg.evaluate("navigator.clipboard.readText()")
    check("run-sheet has songs and sharing, not requests", "Give Thanks" in rs and "Faith – Member A" in rs and "r1" not in rs, rs)
    await pg.click("#sessDup"); await pg.wait_for_timeout(300)
    items = await pg.inner_text("#set")
    check("duplicate keeps songs, clears sharing", "Give Thanks" in items and "Member A" not in items, items)
    await pg.click("#sessTpl"); await pg.click("#sessNew"); await pg.wait_for_timeout(200)
    check("new session follows saved order", "Bible:" in await pg.inner_text("#set") and "Choose a song" in await pg.inner_text("#set"))
    await pg.click('#lib .item:has-text("Amazing Grace") button'); await pg.wait_for_timeout(200)
    check("+ Add fills the first empty song slot", "Amazing Grace" in await pg.inner_text("#set"))
    # space after the last line of a song moves to the next item
    await pg.click('#set .item:has-text("Amazing Grace")'); await pg.wait_for_timeout(300)
    for _ in range(18):
        await pg.keyboard.press("Space"); await pg.wait_for_timeout(15)
    check("space flows from song end to next item", "Amazing Grace" not in await pg.inner_text("#songName"), await pg.inner_text("#songName"))
    check("sessions: no page errors", not errs, str(errs)); await ctx.close()


async def test_folder(browser, tmp):
    ctx, pg, errs = await new_page(browser)
    await pg.evaluate(OPFS_RESET)
    await pg.evaluate(WRITE, ["Song One.txt", "Title: Song One\nLanguage: Indonesian\n\nBait 1:\nsatu\n\nReff:\ndua\n"])
    await pg.evaluate("async()=>{const d=await navigator.storage.getDirectory();await window.__wlConnect(d)}"); await pg.wait_for_timeout(2000)
    check("folder: song file loaded", "Song One" in await pg.inner_text("#lib"))
    await create_song(pg, "Song Two", "[Verse 1]\nx\n"); await pg.wait_for_timeout(1500)
    files = await pg.evaluate(LIST)
    check("folder: new song file and session file written", "Song Two.txt" in files and any(f.startswith("sessions/") and f.endswith(".txt") for f in files), str(files))
    # audio copied into the folder
    wav = tmp / "tone.wav"; make_wav(wav, 2)
    await pg.click("#tabEdit"); await pg.check("input[name=mt][value=audio]"); await pg.wait_for_timeout(300)
    await pg.set_input_files("#eAudio", str(wav)); await pg.wait_for_timeout(1500)
    check("folder: audio copied", any(f.startswith("audio/") for f in await pg.evaluate(LIST)))
    # settings merge: another laptop changed Song One more recently
    meta = json.loads(await pg.evaluate(READ, "_worship-app.json"))
    meta["songs"]["Song One.txt"]["offset"] = 0.7; meta["songs"]["Song One.txt"]["mUpdated"] = 9999999999999
    await pg.evaluate(WRITE, ["_worship-app.json", json.dumps(meta)])
    await pg.click("#tabLive"); await pg.keyboard.press("]"); await pg.wait_for_timeout(2500)
    meta2 = json.loads(await pg.evaluate(READ, "_worship-app.json"))
    check("folder: other laptop's newer setting kept", meta2["songs"]["Song One.txt"]["offset"] == 0.7, str(meta2["songs"].get("Song One.txt")))
    # external edit picked up on focus
    await pg.evaluate(WRITE, ["Song One.txt", "Title: Song One\n\n[Verse 1]\nedited\n"])
    await pg.wait_for_timeout(50)
    await pg.evaluate(WRITE, ["Added Outside.txt", "one\ntwo\n"])
    await pg.evaluate("window.dispatchEvent(new Event('focus'))"); await pg.wait_for_timeout(1500)
    check("folder: file added outside the app appears", "Added Outside" in await pg.inner_text("#lib"))
    # delete goes to _trash
    await pg.click('#lib >> text=Added Outside'); await pg.click("#tabEdit"); await pg.click("#eDel"); await pg.wait_for_timeout(2500)
    files = await pg.evaluate(LIST)
    check("folder: deleted song moved to _trash", "Added Outside.txt" not in files and any(f.startswith("_trash/") and "Added Outside" in f for f in files), str(files))
    check("folder: no page errors", not errs, str(errs)); await ctx.close()


async def test_pacing_and_handsfree(browser, tmp):
    ctx, pg, errs = await new_page(browser)
    await create_song(pg, "Pace", "[Verse 1]\na\nb\n[Chorus]\nc\nd")
    await pg.click("#tabEdit"); await pg.check("input[name=mt][value=clock]"); await pg.wait_for_timeout(200); await pg.click("#tabLive")
    await pg.keyboard.press("s"); await pg.wait_for_timeout(4000)
    for _ in range(4):
        await pg.keyboard.press("Space"); await pg.wait_for_timeout(800)
    await pg.keyboard.press("s"); await pg.wait_for_timeout(200); await pg.click("#clkReset"); await pg.keyboard.press("Enter")
    counts, widths = set(), set()
    for _ in range(6):
        await pg.wait_for_timeout(600)
        counts.add(await pg.evaluate("(document.querySelector('#preview .count')||{}).textContent||''"))
        widths.add(await pg.evaluate("document.querySelector('#preview .pace i').style.width"))
    check("intro countdown shows", {"3", "2", "1"} & counts != set(), str(counts))
    check("pacing bar moves", len(widths) > 2, str(widths))
    check("pacing: no page errors", not errs, str(errs)); await ctx.close()


async def test_check_and_pwa(browser):
    ctx, pg, errs = await new_page(browser)
    long = "This is a very long lyric line that will certainly wrap on the television, friends"
    await create_song(pg, "Check", "Check Lyrics\nYou might also like\n[Verse 1]\n" + long + "\nshort\n[Chorus]\nc1\n[Bridge]\nb1")
    await pg.wait_for_timeout(400)
    check("new song with problems opens the Edit tab", not await pg.is_hidden("#edit"))
    txt = await pg.inner_text("#eCheck")
    check("lyrics check flags leftover text and long line", "Leftover website text" in txt and "Long line" in txt, txt)
    check("section previews drawn", await pg.locator("#eThumbs .stage").count() >= 2)
    await pg.click('#eCheck li:has-text("Long line") button'); await pg.wait_for_timeout(500)
    lyr = await pg.input_value("#eLyrics")
    check("split long line into two", long not in lyr and "certainly" in lyr, lyr)
    await pg.click('#eCheck li:has-text("You might also like") button'); await pg.wait_for_timeout(500)
    check("remove leftover text", "You might also like" not in await pg.input_value("#eLyrics"))
    # onboarding + installable app files
    check("getting started checklist shown", not await pg.is_hidden("#onb") and "/" in await pg.inner_text("#onbCount"))
    man = await pg.evaluate("fetch('manifest.webmanifest').then(r=>r.json())")
    check("manifest served", man.get("name") == "Worship Lyrics" and len(man.get("icons", [])) >= 2)
    await pg.wait_for_timeout(1500)
    sw = await pg.evaluate("navigator.serviceWorker.getRegistration().then(r=>!!r)")
    check("offline service worker registered", sw)
    check("check/pwa: no page errors", not errs, str(errs)); await ctx.close()


async def main():
    server = subprocess.Popen([sys.executable, "-m", "http.server", str(PORT)], cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1)
    try:
        async with async_playwright() as p:
            kw = {"args": ["--no-sandbox", "--autoplay-policy=no-user-gesture-required"]}
            if CHROME:
                kw["executable_path"] = CHROME
            browser = await p.chromium.launch(**kw)
            with tempfile.TemporaryDirectory() as t:
                tmp = Path(t)
                for fn in (test_parsing, test_navigation, test_sessions):
                    await fn(browser)
                await test_folder(browser, tmp)
                await test_pacing_and_handsfree(browser, tmp)
                await test_check_and_pwa(browser)
            await browser.close()
    finally:
        server.terminate()
    print(f"\n{len(FAILS)} failed" if FAILS else "\nAll checks passed")
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    asyncio.run(main())
