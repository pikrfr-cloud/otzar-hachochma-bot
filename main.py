import telebot
import requests
import os
import io
import time
import base64
from playwright.sync_api import sync_playwright

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
OTZAR_USERNAME = os.environ.get("OTZAR_USERNAME", "")
OTZAR_PASSWORD = os.environ.get("OTZAR_PASSWORD", "")

BASE_URL = "https://tablet.otzar.org"

bot = telebot.TeleBot(TELEGRAM_TOKEN)

_pw = None
_browser = None
_page = None

def get_page():
    global _pw, _browser, _page
    if _page is None:
        _pw = sync_playwright().start()
        _browser = _pw.chromium.launch(headless=True)
        ctx = _browser.new_context()
        _page = ctx.new_page()
        _page.goto(f"{BASE_URL}/#/login")
        _page.wait_for_load_state("networkidle", timeout=15000)
        time.sleep(2)
        inputs = _page.query_selector_all("input")
        if len(inputs) >= 2:
            inputs[0].fill(OTZAR_USERNAME)
            inputs[1].fill(OTZAR_PASSWORD)
        btns = _page.query_selector_all("button")
        if btns:
            btns[0].click()
        time.sleep(4)
        print("Logged in to Otzar HaChochma")
    return _page


def search_book(book_name):
    session = requests.Session()
    resp = session.post(f"{BASE_URL}/api/user/connectUser", json={
        "username": OTZAR_USERNAME,
        "password": OTZAR_PASSWORD
    })
    if resp.status_code != 200:
        return None, "Login failed"
    resp = session.get(f"{BASE_URL}/api/search/searchBooks", params={
        "searchStr": book_name,
        "start": 0,
        "rows": 10
    })
    if resp.status_code != 200:
        return None, f"Search failed: {resp.status_code}"
    data = resp.json()
    books = data.get("books", data.get("results", data.get("docs", [])))
    if not books:
        return None, f"No books found for '{book_name}'"
    book = books[0]
    book_id = book.get("id", book.get("bookId", book.get("ID")))
    title = book.get("title", book.get("bookTitle", book_name))
    return book_id, title


def parse_siman(siman_str):
    hebrew_map = {
        'א': 1, 'ב': 2, 'ג': 3, 'ד': 4, 'ה': 5,
        'ו': 6, 'ז': 7, 'ח': 8, 'ט': 9, 'י': 10,
        'יא': 11, 'יב': 12, 'יג': 13, 'יד': 14, 'טו': 15,
        'טז': 16, 'יז': 17, 'יח': 18, 'יט': 19, 'כ': 20
    }
    s = siman_str.strip()
    if s in hebrew_map:
        return hebrew_map[s]
    try:
        return int(s)
    except:
        return 1


def find_siman_pages(book_id, siman_str):
    session = requests.Session()
    session.post(f"{BASE_URL}/api/user/connectUser", json={
        "username": OTZAR_USERNAME,
        "password": OTZAR_PASSWORD
    })
    resp = session.get(f"{BASE_URL}/api/books/getIndex", params={"bookId": book_id})
    if resp.status_code == 200:
        try:
            toc = resp.json()
            entries = toc.get("index", toc.get("toc", []))
            if entries:
                for entry in entries:
                    label = str(entry.get("label", entry.get("title", "")))
                    if siman_str in label or str(parse_siman(siman_str)) in label:
                        sp = entry.get("page", entry.get("pageNum", 1))
                        return list(range(sp, sp + 3))
        except:
            pass
    siman_num = parse_siman(siman_str)
    estimated = max(1, siman_num * 2 + 15)
    return list(range(estimated, estimated + 3))


def capture_page(book_id, page_num):
    page = get_page()
    url = f"{BASE_URL}/#/b/{book_id}/p/{page_num}/t/0/fs/0/start/0/end/0/c"
    print(f"Loading: {url}")
    page.goto(url)
    try:
        page.wait_for_selector(".img-canvas, canvas", timeout=20000)
        time.sleep(3)
    except:
        time.sleep(6)
    canvas_data = page.evaluate("""() => {
        const canvas = document.querySelector('.img-canvas') || document.querySelector('canvas');
        if (canvas && canvas.width > 10) {
            return canvas.toDataURL('image/jpeg', 0.85);
        }
        return null;
    }""")
    if canvas_data and "data:image" in str(canvas_data):
        b64 = canvas_data.split(",")[1]
        return base64.b64decode(b64)
    # Fallback: screenshot
    return page.screenshot()


@bot.message_handler(commands=['start'])
def start(message):
    bot.reply_to(message, "שלום! אני בוט אוצר החכמה.\n\nפקודות:\n/get <שם ספר> <ציון>\n/download <book_id> <עמוד_התחלה>-<עמוד_סוף>\n/search <מילה>")


@bot.message_handler(commands=['get'])
def get_siman(message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        bot.reply_to(message, "שימוש: /get <שם ספר> <ציון>\nדוגמה: /get תשובות הרמבם ז")
        return
    args = parts[1].strip()
    tokens = args.split()
    siman = tokens[-1]
    book_name = " ".join(tokens[:-1])
    bot.reply_to(message, f"מחפש '{book_name}'...")
    book_id, title = search_book(book_name)
    if book_id is None:
        bot.reply_to(message, f"לא נמצא: {title}")
        return
    bot.reply_to(message, f"נמצא: {title} (ID: {book_id})\nמחפש ציון {siman}...")
    pages = find_siman_pages(book_id, siman)
    bot.reply_to(message, f"מוריד עמודים {pages[0]}-{pages[-1]}...")
    sent = 0
    for p in pages:
        try:
            data = capture_page(book_id, p)
            if data and len(data) > 500:
                buf = io.BytesIO(data)
                buf.name = f"page_{p}.jpg"
                bot.send_document(message.chat.id, buf, caption=f"עמוד {p}")
                sent += 1
            else:
                bot.send_message(message.chat.id, f"עמוד {p}: תמונה ריקה")
        except Exception as e:
            bot.send_message(message.chat.id, f"שגיאה עמוד {p}: {str(e)[:120]}")
    bot.send_message(message.chat.id, f"הסתיים - {sent} עמודים נשלחו")


@bot.message_handler(commands=['download'])
def download_pages(message):
    parts = message.text.split()
    if len(parts) < 3:
        bot.reply_to(message, "שימוש: /download <book_id> <start>-<end>")
        return
    book_id = parts[1]
    rng = parts[2]
    if '-' in rng:
        s, e = rng.split('-')
        pages = list(range(int(s), int(e) + 1))
    else:
        pages = [int(rng)]
    bot.reply_to(message, f"מוריד עמודים {pages[0]}-{pages[-1]} מספר {book_id}...")
    for p in pages:
        try:
            data = capture_page(book_id, p)
            if data and len(data) > 500:
                buf = io.BytesIO(data)
                buf.name = f"page_{p}.jpg"
                bot.send_document(message.chat.id, buf, caption=f"עמוד {p}")
            else:
                bot.send_message(message.chat.id, f"עמוד {p}: לא ניתן להוריד")
        except Exception as e:
            bot.send_message(message.chat.id, f"שגיאה עמוד {p}: {str(e)[:120]}")


@bot.message_handler(commands=['search'])
def search_cmd(message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        bot.reply_to(message, "שימוש: /search <מילה>")
        return
    query = parts[1]
    book_id, title = search_book(query)
    if book_id:
        bot.reply_to(message, f"נמצא: {title}\nID: {book_id}\nלהורדה: /download {book_id} 1-3")
    else:
        bot.reply_to(message, f"לא נמצא: {query}")


print("Bot starting with Playwright support...")
bot.polling(none_stop=True)
