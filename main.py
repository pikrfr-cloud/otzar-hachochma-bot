import telebot
import requests
import os
import io

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
OTZAR_USERNAME = os.environ.get("OTZAR_USERNAME", "")
OTZAR_PASSWORD = os.environ.get("OTZAR_PASSWORD", "")

BASE_URL = "https://tablet.otzar.org"

bot = telebot.TeleBot(TELEGRAM_TOKEN)
session = requests.Session()

def login_to_otzar():
    resp = session.post(f"{BASE_URL}/api/user/connectUser", json={
        "username": OTZAR_USERNAME,
        "password": OTZAR_PASSWORD
    })
    return resp.status_code == 200

def get_page_image(book_id, page_num):
    url = f"{BASE_URL}/api/images/{book_id}/P{page_num:04d}?&resize=1000"
    resp = session.get(url)
    if resp.status_code == 200:
        return resp.content
    return None

print("Connecting to Otzar HaChochma...")
if login_to_otzar():
    print("Login successful!")
else:
    print("Login failed - check credentials")

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    bot.reply_to(message,
        "📚 ברוך הבא לבוט אוצר החכמה!\n\n"
        "פקודות זמינות:\n"
        "/download <ספר_מספר> <עמוד_התחלה>-<עמוד_סוף>\n"
        "דוגמה: /download 169125 1-5\n\n"
        "/search <מילה>\n"
        "דוגמה: /search שבת")

@bot.message_handler(commands=['download'])
def download_pages(message):
    try:
        parts = message.text.split()
        if len(parts) < 3:
            bot.reply_to(message, "שימוש: /download <מספר_ספר> <עמוד_התחלה>-<עמוד_סוף>")
            return
        book_id = parts[1]
        pages_range = parts[2].split('-')
        start_page = int(pages_range[0])
        end_page = int(pages_range[1]) if len(pages_range) > 1 else start_page
        if end_page - start_page > 20:
            bot.reply_to(message, "ניתן להוריד עד 20 עמודים בכל פעם")
            return
        bot.reply_to(message, f"מוריד עמודים {start_page}-{end_page} מספר {book_id}...")
        for page_num in range(start_page, end_page + 1):
            img_data = get_page_image(book_id, page_num)
            if img_data:
                img_file = io.BytesIO(img_data)
                img_file.name = f"page_{page_num}.jpg"
                try:
                    bot.send_photo(message.chat.id, img_file, caption=f"עמוד {page_num}")
                except Exception:
                    img_file = io.BytesIO(img_data)
                    img_file.name = f"page_{page_num}.jpg"
                    bot.send_document(message.chat.id, img_file, caption=f"עמוד {page_num}")
            else:
                bot.send_message(message.chat.id, f"לא נמצא עמוד {page_num}")
    except Exception as e:
        bot.reply_to(message, f"שגיאה: {str(e)}")

@bot.message_handler(commands=['search'])
def search_otzar(message):
    try:
        query = message.text.replace('/search', '').strip()
        if not query:
            bot.reply_to(message, "שימוש: /search <מילה>")
            return
        bot.reply_to(message, f"מחפש: {query}...")
        resp = session.post(f"{BASE_URL}/api/freesearch/coords", json={
            "words": query,
            "books": [],
            "start": 0,
            "rows": 10
        })
        if resp.status_code == 200:
            data = resp.json()
            results = data.get('docs', [])
            if results:
                reply = f"נמצאו {len(results)} תוצאות עבור '{query}':\n\n"
                for i, r in enumerate(results[:5], 1):
                    title = r.get('title', 'ללא שם')
                    book_id = r.get('bookId', '')
                    page = r.get('page', '')
                    reply += f"{i}. {title}\n   ספר: {book_id}, עמוד: {page}\n\n"
                bot.reply_to(message, reply)
            else:
                bot.reply_to(message, f"לא נמצאו תוצאות עבור '{query}'")
        else:
            bot.reply_to(message, "שגיאה בחיפוש")
    except Exception as e:
        bot.reply_to(message, f"שגיאה: {str(e)}")

print("Bot is running...")
bot.polling(none_stop=True)
