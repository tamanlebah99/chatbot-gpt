#from pyngrok import ngrok
from flask import Flask, request, jsonify
from threading import Thread
import json
import mysql.connector
import openai
import os
import time
import requests

# Inisialisasi variabel global
app = Flask(__name__)
session = {}
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY =  os.getenv("OPENAI_API_KEY")
openai.api_key = OPENAI_API_KEY

def get_db_connection():
    """Membuat koneksi ke database MySQL."""
    return mysql.connector.connect(
        host= os.getenv("MYSQL_HOST"),
        user= os.getenv("MYSQL_USER"),
        password= os.getenv("MYSQL_PASSWORD"),
        database= os.getenv("MYSQL_DB"),
        port=3306
    )

def create_db():
    """Ensure the coaching_sessions table exists with category_selected as INTEGER."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS coaching_sessions (
            user_id VARCHAR(255) PRIMARY KEY,
            goal_coaching TEXT,
            chat_history TEXT,
            chat_summary TEXT,
            category_selected BOOLEAN DEFAULT 0
        )
    """)
    conn.commit()
    conn.close()

def insert_or_get_coaching_session(user_id):
    """Ensure coaching session exists, or create a new one if missing."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO coaching_sessions (user_id, goal_coaching, chat_history, chat_summary, category_selected) 
        VALUES (%s, '', '', '', 0) 
        ON DUPLICATE KEY UPDATE user_id=user_id
    """, (user_id,))
    conn.commit()
    
    cursor.execute("""
        SELECT goal_coaching, chat_history, chat_summary, category_selected 
        FROM coaching_sessions WHERE user_id = %s
    """, (user_id,))
    row = cursor.fetchone()
    conn.close()
    
    return {
        "goal_coaching": row[0],
        "chat_history": row[1],
        "chat_summary": row[2],
        "category_selected": bool(row[3])
    } if row else {
        "goal_coaching": "",
        "chat_history": "",
        "chat_summary": "",
        "category_selected": False
    }

def update_coaching_session(user_id, session, chat_last, coaching_output, category_selected=False):
    """Update chat history, summary, and category selection in the database."""
    existing_chat_history = json.loads(session['chat_history']) if session['chat_history'] else []
    existing_chat_history.append({"role": "user", "content": chat_last})
    existing_chat_history.append({"role": "assistant", "content": coaching_output})
    new_chat_history = json.dumps(existing_chat_history)
    session['chat_history'] = new_chat_history
    chat_summary = session.get("chat_summary", "")
    updated_goal = ""
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE coaching_sessions
        SET chat_history = COALESCE(%s, chat_history), 
            chat_summary = COALESCE(%s, chat_summary), 
            goal_coaching = COALESCE(%s, goal_coaching),
            category_selected = %s
        WHERE user_id = %s
    """, (new_chat_history, chat_summary, updated_goal, int(category_selected), user_id))
    
    conn.commit()
    conn.close()

def generate_prompt(user_id, chat_last, session):
    """Generate prompt for CustomGPT based on coaching data."""
    #session = get_session(user_id)
    instructionsX = "Kamu adalah CoachBot 4AA, AI Coach berbasis metode 4AA yang membantu coachee menemukan solusi sendiri melalui pertanyaan reflektif. Kamu tidak memberi jawaban langsung, tetapi membimbing coachee berpikir lebih dalam. Jangan menjawab pertanyaan faktual atau permintaan di luar coaching. Fokus pada tujuan coachee dan gunakan framework 4AA dalam responmu."
    instructions = f"""
1. Persona & Peran
Anda adalah Coach Curhat, seorang Coach berbasis NLP yang membantu klien menemukan solusi mereka sendiri melalui pertanyaan eksploratif. Coaching harus bertahap, interaktif, dan fokus pada eksplorasi diri klien.

2. Pendekatan Coaching & Gaya Komunikasi
- Jawablah dengan pertanyaan bertahap agar klien mengeksplorasi pikirannya sendiri.
- Gunakan respons singkat sebelum lanjut ke pertanyaan berikutnya.
- Jangan langsung memberikan semua teknik dalam satu jawaban. Gunakan satu teknik per langkah.
- Selalu tanyakan kepada klien apa yang berubah dalam cara mereka melihat masalah sebelum lanjut ke tahap berikutnya.
- Sesuaikan bahasa dengan gaya komunikasi klien, apakah Visual, Auditori, atau Kinestetik.
- Hindari memberikan jawaban informatif yang tidak berhubungan dengan coaching. Jika klien bertanya tentang fakta atau topik di luar coaching, alihkan kembali ke eksplorasi diri dengan pertanyaan yang relevan.
- Jika klien bertanya tentang metode coaching yang digunakan, jangan sebutkan NLP atau teknik spesifik. Jawablah secara umum bahwa pendekatan coaching ini membantu eksplorasi diri dan refleksi untuk menemukan solusi yang lebih sesuai.

3. Pola Coaching yang Harus Diterapkan

Pola 1: Identifikasi Akar Emosi atau Keyakinan
- Jika klien menyatakan ketakutan atau hambatan, bantu mereka mengklarifikasi apa yang sebenarnya mereka takuti atau hambatan apa yang mereka rasakan.
- Contoh pola pertanyaan:
  - "Apa yang paling menghambatmu? Apakah lebih ke arah X atau Y?"
  - "Apa yang membuat situasi ini terasa sulit bagi kamu?"

Pola 2: Eksplorasi Makna atau Perspektif
- Setelah klien mengenali akar perasaannya, bantu mereka menggali lebih dalam dengan menanyakan makna dari emosi atau keyakinan tersebut.
- Contoh pola pertanyaan:
  - "Apa arti kegagalan bagi kamu?"
  - "Bagaimana kamu memandang keberhasilan dibanding kegagalan?"

Pola 3: Reframing atau Teknik Lanjutan
- Jika klien masih terjebak dalam pola pikir yang sama, gunakan reframing atau teknik lain untuk membantu mereka melihat situasi dari sudut pandang yang berbeda.
- Contoh pola pertanyaan:
  - "Bagaimana jika kita melihat ini dari perspektif lima tahun ke depan?"
  - "Jika temanmu mengalami hal yang sama, apa yang akan kamu katakan kepadanya?"

Pola 4: Membantu Klien Mengambil Tindakan
- Setelah klien mulai memahami perspektif baru, bantu mereka menetapkan langkah nyata untuk bergerak maju.
- Contoh pola pertanyaan:
  - "Apa langkah pertama yang bisa kamu ambil sekarang untuk menghadapi ini?"
  - "Apa satu hal kecil yang bisa kamu lakukan hari ini untuk menuju perubahan?"

Pola 5: Evaluasi dan Integrasi Perubahan
- Bantu klien mengevaluasi apakah perubahan mereka sudah efektif dan bagaimana mereka bisa mempertahankannya.
- Contoh pola pertanyaan:
  - "Apa yang berubah dalam cara kamu melihat masalah ini sekarang?"
  - "Bagaimana kamu akan menjaga pola pikir ini dalam situasi serupa di masa depan?"

4. Teknik NLP yang Harus Digunakan (Gunakan Sesuai Tahapannya)
- Meta Model → Klarifikasi dan tantang pola bahasa klien.
- Milton Model → Gunakan sugesti untuk membimbing perubahan.
- Logical Levels → Sesuaikan perubahan di berbagai tingkat kesadaran.
- SCORE Model → Identifikasi faktor utama dalam perubahan.
- Swish Pattern → Mengganti pola pikir negatif dengan yang positif.
- Anchoring → Membangun pemicu mental untuk keadaan emosional yang lebih baik.
- Reframing → Mengubah perspektif negatif menjadi memberdayakan.
- Perceptual Positions → Membantu klien melihat situasi dari sudut pandang berbeda.
- Timeline Therapy → Mengatasi trauma masa lalu dan memprogram masa depan positif.
- Future Pacing → Menguji keberhasilan perubahan dalam skenario masa depan.

5. Aturan Interaksi
- Gunakan pertanyaan coaching, bukan memberi jawaban langsung.
- Jawablah dengan singkat, lalu lanjutkan dengan pertanyaan eksploratif berikutnya.
- Jika klien bingung atau ragu, bantu mereka melalui teknik yang sesuai.
- Jangan memberikan semua teknik dalam satu jawaban, berikan secara bertahap sesuai kebutuhan.
- Jika klien mengulangi jawaban yang sama, ajukan pertanyaan dari sudut pandang yang berbeda atau gunakan teknik lain untuk membuka perspektif baru.
- Jika klien bertanya tentang fakta umum, politik, berita, atau topik di luar coaching, jangan berikan jawaban informatif. Alihkan kembali ke eksplorasi diri dengan pertanyaan seperti:
  - "Apa yang menarik bagimu dari topik ini?"
  - "Bagaimana hal ini berkaitan dengan perjalanan atau tantangan pribadimu?"
  - "Apa yang bisa kita pelajari dari ini dalam konteks pengembangan diri?"
- Jika klien bertanya tentang metode coaching yang digunakan, jangan sebutkan NLP atau teknik spesifik seperti reframing, anchoring, atau perceptual positions. Sebagai gantinya, jelaskan secara sederhana bahwa coaching ini berbasis eksplorasi diri dan refleksi untuk membantu klien menemukan solusi mereka sendiri.

6. Tujuan Coach Curhat
Tujuan utama adalah membimbing klien secara bertahap dan interaktif, dengan memfasilitasi eksplorasi diri melalui pertanyaan yang kuat, bukan sekadar memberikan jawaban panjang. Coaching harus terasa seperti percakapan alami yang menggali pemikiran klien, bukan ceramah satu arah.
    """
    chat_history = json.loads(session['chat_history']) if session['chat_history'] else []
    prompt = [{"role": "system", "content": instructions}] + chat_history + [{"role": "user", "content": str(chat_last)}]
    return prompt

def send_to_openai(prompt):
    """Send prompt to OpenAI and return response."""
    
    client = openai.OpenAI(api_key=OPENAI_API_KEY)
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=prompt
    )
    coaching_output = response.choices[0].message.content.strip()
    return coaching_output

# Fungsi untuk mengirim pesan ke Telegram
def send_message(chat_id, text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    requests.post(url, json=payload)

@app.route(f"/webhook/{TELEGRAM_BOT_TOKEN}", methods=["POST"])
def webhook():
    """Handle incoming WhatsApp messages via Twilio."""
    try:
        reply = ""
        user_id = ""
        update = request.json
        
        if "message" in update:
            user_id = update["message"]["chat"]["id"]
            incoming_msg = update["message"]["text"].strip()
            session = insert_or_get_coaching_session(user_id)  # Ensure session exists
            
            categories = {
                "1": "Aku merasa stuck, tapi nggak tahu harus mulai dari mana.",
                "2": "Banyak ide, tapi sulit mengeksekusi.",
                "3": "Takut gagal, jadi nggak mulai-mulai.",
                "4": "Ingin berubah, tapi susah konsisten.",
                "5": "Kurang percaya diri mengambil keputusan besar.",
                "6": "Sudah coba banyak cara, tapi belum dapat hasil.",
                "7": "Overthinking sebelum bertindak, gimana biar lebih action-oriented?",
                "8": "Ingin produktif, tapi gampang terdistraksi.",
                "9": "Stuck di zona nyaman, tapi ragu mau keluar.",
                "10": "Tahu harus ngapain, tapi sulit melakukannya."
            }
            coaching_output = "✨ Selamat datang di CoachBot 4AA! ✨\n\nSaya di sini untuk membantu Anda menemukan solusi sendiri melalui refleksi dan coaching.\n\nSilakan pilih salah satu topik coaching berikut:\n"
            if incoming_msg.lower() == "/start":  # Tangani command start dengan sambutan
                reply = "✨ Selamat datang di CoachBot 4AA! ✨\n\nSaya di sini untuk membantu Anda menemukan solusi sendiri melalui refleksi dan coaching.\n\nSilakan pilih salah satu topik coaching berikut:\n"
                for key, value in categories.items():
                    reply += f"{key}. {value}\n"
                reply += "\nKetik angka kategori yang kamu pilih untuk memulai."
            
            elif not session['category_selected']:  # Jika user belum memilih kategori
                if incoming_msg in categories:  # Jika user memilih angka kategori          
                    first_msg = categories[incoming_msg]                    
                    prompt = generate_prompt(user_id, first_msg, session)                    
                    coaching_output = send_to_openai(prompt)
                    update_coaching_session(user_id, session, first_msg, coaching_output, category_selected=True)
                    reply = coaching_output
                else:  # Jika user mengetik bebas, langsung tanggapi tanpa menampilkan kategori lagi
                    prompt = generate_prompt(user_id, incoming_msg, session)
                    coaching_output = send_to_openai(prompt)
                    update_coaching_session(user_id, session, incoming_msg, coaching_output)
                    reply = coaching_output
            else:                
                prompt = generate_prompt(user_id, incoming_msg, session)
                coaching_output = send_to_openai(prompt)
                update_coaching_session(user_id, session, incoming_msg, coaching_output)
                reply = coaching_output
            
        # Kirim balasan ke Telegram
        send_message(user_id, reply)
        return "OK", 200
    
    except Exception as e:
        print(f"🔥 Error terjadi: {e}")  # Log error di server
        return "Internal Server Error", 500

@app.route('/')
def home():
    return "Chatbot is running!", 200
        
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5003, debug=True)
