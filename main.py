# FLYIO
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

# Fungsi mengirim pesan biasa
def send_message(chat_id, text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id, 
        "text": text,
        "parse_mode": "Markdown"
    }
    requests.post(url, json=payload)

# Fungsi mengirim pesan dengan keyboard interaktif
def send_message_with_keyboard(chat_id, text, keyboard):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
        "reply_markup": json.dumps(keyboard)
    }
    requests.post(url, json=payload)

def get_user_sessions(user_id):
    """Mengambil daftar sesi coaching user dari database."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT session_id, active FROM coaching_sessions WHERE user_id = %s", (user_id,))
    sessions = cursor.fetchall()

    cursor.close()
    conn.close()

    if not sessions:  # Pastikan tidak mengembalikan None
        return []

    return [(s[0], s[1]) for s in sessions]  # Kembalikan dalam format tuple (session_id, active)

def get_user_active_session(user_id):
    """Mengambil sesi aktif user dari database."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT session_id, goal_coaching, chat_history, chat_summary FROM coaching_sessions WHERE user_id = %s AND active = TRUE", (user_id,))
    session = cursor.fetchone()
    
    cursor.close()
    conn.close()
    
    if session:
        return {
            "session_id": session[0],
            "goal_coaching": session[1],
            "chat_history": session[2] if session[2] else "[]",  # Pastikan JSON valid
            "chat_summary": session[3] if session[3] else ""
        }
    return {}  # Kembalikan dictionary kosong jika tidak ada sesi aktif

def set_active_session(user_id, session_id):
    """Mengaktifkan sesi tertentu dan menonaktifkan yang lain."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Nonaktifkan semua sesi user
    cursor.execute("UPDATE coaching_sessions SET active = FALSE WHERE user_id = %s", (user_id,))
    
    # Aktifkan sesi yang dipilih
    cursor.execute("UPDATE coaching_sessions SET active = TRUE WHERE user_id = %s AND session_id = %s", (user_id, session_id))
    
    conn.commit()
    cursor.close()
    conn.close()

def deactivate_user_sessions(user_id):
    """Menonaktifkan semua sesi lama user tanpa menghapusnya."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("UPDATE coaching_sessions SET active = FALSE WHERE user_id = %s", (user_id,))
    
    conn.commit()
    cursor.close()
    conn.close()

def delete_session(user_id, session_id):
    """Menghapus sesi tertentu dari database berdasarkan session_id."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("DELETE FROM coaching_sessions WHERE user_id = %s AND session_id = %s", (user_id, session_id))
    
    conn.commit()
    cursor.close()
    conn.close()

def delete_all_sessions(user_id):
    """Menghapus semua sesi user dari database."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("DELETE FROM coaching_sessions WHERE user_id = %s", (user_id,))
    
    conn.commit()
    cursor.close()
    conn.close()

def create_new_session(user_id):
    """Membuat sesi coaching baru untuk user dan menonaktifkan sesi sebelumnya."""
    deactivate_user_sessions(user_id)  # Nonaktifkan sesi lama sebelum membuat sesi baru

    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Buat sesi baru
    cursor.execute(
        "INSERT INTO coaching_sessions (user_id, goal_coaching, chat_history, chat_summary, active) VALUES (%s, '', '', '', TRUE)",
        (user_id,)
    )
    
    conn.commit()
    cursor.close()
    conn.close()

    # Cek apakah user memiliki sesi lain selain yang baru dibuat
    session_list = get_user_sessions(user_id)
    has_sessions = len(session_list) > 1  # Karena sesi baru sudah dibuat, maka harus lebih dari 1

    # Kategori coaching
    categories = {
        "1": "Stuck, Bingung Mulai",
        "2": "Kebanyakan Ide, No Action",
        "3": "Takut Gagal",
        "4": "Susah Konsisten",
        "5": "Kurang Percaya Diri",
        "6": "Usaha Belum Berhasil",
        "7": "Overthinking Parah",
        "8": "Mudah Terdistraksi",
        "9": "Zona Nyaman vs Tantangan",
        "10": "Tahu Harus Ngapain, Tapi..."
    }

    
    category_text = "\n".join([f"{key}. {value}" for key, value in categories.items()])
    
    # Pesan selamat datang langsung di sini
    welcome_message = (
        "👋 *Selamat datang di Coach Curhat!* 😊\n\n"
        "Saya di sini untuk membantu Kamu menemukan solusi sendiri melalui refleksi dan coaching.\n"
        "Silakan pilih salah satu kategori di bawah ini dengan mengetik angkanya:\n\n"
        f"{category_text}\n\n"
        "Atau Kamu bisa langsung mengetik pesan untuk memulai percakapan."
    )

    # Tombol interaktif
    keyboard = {
        "inline_keyboard": [
            [{"text": "💙 Donasi", "url": "https://trakteer.id/coachcurhat"}],
            [{"text": "ℹ️ Info", "callback_data": "info"}],
            [{"text": "📞 Kontak", "callback_data": "kontak"}]
        ]
    }

    # **Jika user memiliki sesi lain, tambahkan tombol Pilih Sesi & Hapus Sesi**
    if has_sessions:
        keyboard["inline_keyboard"].append([{"text": "📋 Pilih Sesi", "callback_data": "sessions"}])
        keyboard["inline_keyboard"].append([{"text": "🗑️ Hapus Sesi", "callback_data": "delete_session"}])

    # Kirim pesan selamat datang dengan tombol interaktif
    send_message_with_keyboard(user_id, welcome_message, keyboard)

def update_coaching_session(user_id, session, chat_last, coaching_output, category_selected=False):
    """Update chat history, summary, and category selection in the database."""
    existing_chat_history = json.loads(session.get('chat_history', '[]'))  # Pastikan JSON valid
    existing_chat_history.append({"role": "user", "content": chat_last})
    existing_chat_history.append({"role": "assistant", "content": coaching_output})
    
    new_chat_history = json.dumps(existing_chat_history)
    session['chat_history'] = new_chat_history
    chat_summary = session.get("chat_summary", "")
    session_id = session.get("session_id")  # Gunakan session_id agar lebih spesifik
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE coaching_sessions
        SET chat_history = %s, 
            chat_summary = %s, 
            category_selected = %s
        WHERE user_id = %s AND session_id = %s
    """, (new_chat_history, chat_summary, int(category_selected), user_id, session_id))
    
    conn.commit()
    cursor.close()
    conn.close()

def send_to_openai(prompt):
    """Send prompt to OpenAI and return response."""
    
    client = openai.OpenAI(api_key=OPENAI_API_KEY)
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=prompt
    )
    coaching_output = response.choices[0].message.content.strip()
    return coaching_output

def generate_prompt(user_id, chat_last, session):
    """Generate prompt for CustomGPT based on coaching data."""
    #session = get_session(user_id)
    instructionsX = "Kamu adalah CoachBot 4AA, AI Coach berbasis metode 4AA yang membantu coachee menemukan solusi sendiri melalui pertanyaan reflektif. Kamu tidak memberi jawaban langsung, tetapi membimbing coachee berpikir lebih dalam. Jangan menjawab pertanyaan faktual atau permintaan di luar coaching. Fokus pada tujuan coachee dan gunakan framework 4AA dalam responmu."
    instructions = f"""
1. Persona & Peran
Anda adalah Coach Curhat, seorang Coach berbasis NLP yang membantu klien menemukan solusi mereka sendiri melalui pertanyaan eksploratif. Coaching harus bertahap, interaktif, dan fokus pada eksplorasi diri klien.

2. Pendekatan Coaching & Aturan Interaksi
- Gunakan respons yang ramah, suportif, dan membangun kepercayaan.
- Jawablah dengan pertanyaan bertahap agar klien mengeksplorasi pikirannya sendiri.
- Berikan konteks sebelum bertanya agar jawaban terasa lebih alami dan bernilai bagi klien.
- Gunakan respons yang sedikit lebih panjang untuk memberikan ruang eksplorasi sebelum mengajukan pertanyaan.
- Gunakan format Telegram untuk menyoroti poin penting dengan teks tebal (*bold*) dan tambahkan emoji jika relevan untuk meningkatkan keterbacaan.
- Jangan langsung memberikan semua teknik dalam satu jawaban. Gunakan satu teknik per langkah.
- Selalu tanyakan kepada klien apa yang berubah dalam cara mereka melihat masalah sebelum lanjut ke tahap berikutnya.
- Sesuaikan bahasa dengan gaya komunikasi klien, apakah Visual, Auditori, atau Kinestetik.
- Hindari memberikan jawaban informatif yang tidak berhubungan dengan coaching. Jika klien bertanya tentang fakta atau topik di luar coaching, alihkan kembali ke eksplorasi diri dengan pertanyaan yang relevan.
- Jika klien meminta gambar, kode, atau tugas lain di luar coaching, tolak permintaan dengan sopan dan arahkan kembali ke coaching.
- Jika klien bertanya tentang metode coaching yang digunakan, jangan sebutkan NLP atau teknik spesifik. Jawablah secara umum bahwa pendekatan coaching ini membantu eksplorasi diri dan refleksi untuk menemukan solusi yang lebih sesuai.
- Jika klien mengulangi jawaban yang sama, ajukan pertanyaan dari sudut pandang yang berbeda atau gunakan teknik lain untuk membuka perspektif baru.
- Jika klien bertanya tentang fakta umum, politik, berita, atau topik di luar coaching, jangan berikan jawaban informatif. Alihkan kembali ke eksplorasi diri dengan pertanyaan seperti:
  - "Apa yang menarik bagimu dari topik ini?"
  - "Bagaimana hal ini berkaitan dengan perjalanan atau tantangan pribadimu?"
  - "Apa yang bisa kita pelajari dari ini dalam konteks pengembangan diri?"

3. Pola Coaching yang Harus Diterapkan

Pola 1: Identifikasi Akar Emosi atau Keyakinan
- Jika klien menyatakan ketakutan atau hambatan, bantu mereka mengklarifikasi apa yang sebenarnya mereka takuti atau hambatan apa yang mereka rasakan.
- Berikan pengantar sebelum bertanya agar terasa lebih suportif dan membangun koneksi.
- Contoh pola pertanyaan:
  - "Wajar banget kalau ada rasa khawatir. Kalau kita coba lihat lebih dalam, apa yang sebenarnya paling membuatmu ragu?"
  - "Kalau kita telaah lebih jauh, apakah tantangan utama yang kamu hadapi lebih ke faktor internal (seperti keyakinan diri) atau eksternal (seperti lingkungan dan peluang)?"

Pola 2: Eksplorasi Makna atau Perspektif
- Setelah klien mengenali akar perasaannya, bantu mereka menggali lebih dalam dengan menanyakan makna dari emosi atau keyakinan tersebut.
- Contoh pola pertanyaan:
  - "Kalau kita definisikan lebih jelas, apa arti ‘sukses’ menurutmu dalam situasi ini?"
  - "Apa skenario terburuk yang bisa terjadi, dan bagaimana kamu bisa menghadapinya?"

Pola 3: Reframing atau Teknik Lanjutan
- Jika klien masih terjebak dalam pola pikir yang sama, gunakan reframing atau teknik lain untuk membantu mereka melihat situasi dari sudut pandang yang berbeda.
- Contoh pola pertanyaan:
  - "Bagaimana jika kita melihat ini dari perspektif lima tahun ke depan? Apakah kamu masih melihatnya sebagai hambatan yang besar?"
  - "Kalau chatbot ini bisa membantu satu orang saja secara nyata, apakah itu sudah cukup berharga untukmu?"

Pola 4: Membantu Klien Mengambil Tindakan
- Setelah klien mulai memahami perspektif baru, bantu mereka menetapkan langkah nyata untuk bergerak maju.
- Contoh pola pertanyaan:
  - "Sekarang, kalau kita fokus ke eksekusi, apa satu langkah konkret yang bisa kamu lakukan minggu ini untuk menguji potensi pasar chatbot-mu?"
  - "Kalau ada satu hal kecil yang bisa kamu lakukan sekarang untuk mempercepat progres, apa itu?"

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

5. Donasi Setelah Sesi Selesai
- Jika klien mengucapkan kalimat yang mengindikasikan sesi berakhir, seperti "Terima kasih", "Aku sudah menemukan jawabannya", atau "Aku merasa lebih baik", tanyakan konfirmasi apakah mereka ingin mengakhiri sesi.
- Jika klien mengonfirmasi bahwa sesi selesai, akhiri dengan pesan singkat dan ajakan donasi:
  - "Terima kasih telah berbagi dan mengeksplorasi bersama Coach Curhat!
Jika kamu merasa sesi ini bermanfaat, kamu bisa mendukung Coach Curhat melalui donasi di 💙 Trakteer:
https://trakteer.id/coachcurhat.
Untuk memulai sesi baru lagi, ketik /start."

6. Tujuan Coach Curhat
Tujuan utama adalah membimbing klien secara bertahap dan interaktif, dengan memfasilitasi eksplorasi diri melalui pertanyaan yang kuat, bukan sekadar memberikan jawaban panjang. Coaching harus terasa seperti percakapan alami yang menggali pemikiran klien, bukan ceramah satu arah.
    """
    chat_history = json.loads(session['chat_history']) if session['chat_history'] else []
    prompt = [{"role": "system", "content": instructions}] + chat_history + [{"role": "user", "content": str(chat_last)}]
    return prompt

def handle_new_session(user_id):
    """Menonaktifkan sesi lama dan membuat sesi baru."""
    deactivate_user_sessions(user_id)
    create_new_session(user_id)
    return "OK", 200

def handle_switch_session(user_id, session_id):
    """Mengaktifkan sesi yang dipilih oleh user."""
    if session_id in [s[0] for s in get_user_sessions(user_id)]:
        set_active_session(user_id, session_id)
        send_message(user_id, f"🔄 Sesi {session_id} telah diaktifkan. Silakan lanjutkan coaching.")
    else:
        send_message(user_id, "⚠️ Sesi tidak ditemukan. Gunakan `/sessions` untuk melihat daftar sesi.")
    return "OK", 200

def handle_list_sessions(user_id):
    """Menampilkan daftar sesi coaching user dalam bentuk tombol interaktif."""
    session_list = get_user_sessions(user_id)

    if not session_list:
        send_message(user_id, "⚠️ Kamu belum memiliki sesi. Ketik `/new_session` untuk memulai sesi baru.")
        return "OK", 200

    reply = "📋 **Pilih sesi yang ingin kamu aktifkan:**"
    keyboard = {"inline_keyboard": []}

    for session_id, active in session_list:
        status = "✅ Aktif" if active else "⚪ Tidak aktif"
        keyboard["inline_keyboard"].append([
            {"text": f"Sesi {session_id} ({status})", "callback_data": f"switch_session_{session_id}"}
        ])

    # Tambahkan tombol kembali ke awal
    keyboard["inline_keyboard"].append([
        {"text": "🔙 Kembali ke Awal", "callback_data": "start"}
    ])

    send_message_with_keyboard(user_id, reply, keyboard)
    return "OK", 200

def handle_delete_session(user_id):
    """Menampilkan daftar sesi yang bisa dihapus."""
    session_list = get_user_sessions(user_id)

    if not session_list:
        send_message(user_id, "⚠️ Kamu belum memiliki sesi yang bisa dihapus.")
        return "OK", 200

    reply = "🗑️ **Pilih sesi yang ingin kamu hapus:**"
    keyboard = {"inline_keyboard": []}

    for session_id, _ in session_list:
        keyboard["inline_keyboard"].append([
            {"text": f"Hapus Sesi {session_id}", "callback_data": f"confirm_delete_{session_id}"}
        ])

    # Tambahkan opsi hapus semua sesi
    keyboard["inline_keyboard"].append([
        {"text": "🗑️ Hapus Semua Sesi", "callback_data": "confirm_delete_all"}
    ])

    # Tambahkan tombol kembali ke awal
    keyboard["inline_keyboard"].append([
        {"text": "🔙 Kembali ke Awal", "callback_data": "start"}
    ])

    send_message_with_keyboard(user_id, reply, keyboard)
    return "OK", 200

def send_welcome_message(user_id):
    """Menampilkan menu utama tanpa membuat sesi baru atau menonaktifkan sesi lama."""
    
    # Cek apakah user sudah memiliki sesi aktif
    session_list = get_user_sessions(user_id)
    has_sessions = len(session_list) > 0  # Jika ada sesi, user sudah memiliki sesi

    # Kategori coaching
    categories = {
        "1": "Stuck, Bingung Mulai",
        "2": "Kebanyakan Ide, No Action",
        "3": "Takut Gagal",
        "4": "Susah Konsisten",
        "5": "Kurang Percaya Diri",
        "6": "Usaha Belum Berhasil",
        "7": "Overthinking Parah",
        "8": "Mudah Terdistraksi",
        "9": "Zona Nyaman vs Tantangan",
        "10": "Tahu Harus Ngapain, Tapi..."
    }

    
    category_text = "\n".join([f"{key}. {value}" for key, value in categories.items()])
    
    # Pesan utama tanpa mengubah sesi aktif
    welcome_message = (
        "👋 *Selamat datang kembali di Coach Curhat!* 😊\n\n"
        "Saya di sini untuk membantu Kamu menemukan solusi sendiri melalui refleksi dan coaching.\n"
        "Silakan pilih salah satu kategori di bawah ini dengan mengetik angkanya:\n\n"
        f"{category_text}\n\n"
        "Atau Kamu bisa langsung mengetik pesan untuk memulai percakapan."
    )

    # Tombol interaktif
    keyboard = {
        "inline_keyboard": [
            [{"text": "💙 Donasi", "url": "https://trakteer.id/coachcurhat"}],
            [{"text": "ℹ️ Info", "callback_data": "info"}],
            [{"text": "📞 Kontak", "callback_data": "kontak"}]
        ]
    }

    # Jika user sudah memiliki sesi, tambahkan tombol "Pilih Sesi" & "Hapus Sesi"
    if has_sessions:
        keyboard["inline_keyboard"].append([{"text": "📋 Pilih Sesi", "callback_data": "sessions"}])
        keyboard["inline_keyboard"].append([{"text": "🗑️ Hapus Sesi", "callback_data": "delete_session"}])

    # Kirim pesan selamat datang dengan tombol interaktif tanpa mengubah sesi
    send_message_with_keyboard(user_id, welcome_message, keyboard)
    return "OK", 200

@app.route(f"/webhook/{TELEGRAM_BOT_TOKEN}", methods=["POST"])
def webhook():
    """Handle incoming Telegram messages."""
    try:
        update = request.json
        if "message" in update:
            user_id = update["message"]["chat"]["id"]
            incoming_msg = update["message"]["text"].strip()
            
            if incoming_msg.lower() == "/start":
                session_list = get_user_sessions(user_id)
            
                if session_list:
                    reply = "📋 **Sesi sebelumnya ditemukan. Pilih sesi atau buat sesi baru:**\n"
                    keyboard = {"inline_keyboard": []}
            
                    for session_id, active in session_list:
                        status = "✅ Aktif" if active else "⚪ Tidak aktif"
                        keyboard["inline_keyboard"].append([
                            {"text": f"Sesi {session_id} ({status})", "callback_data": f"switch_session_{session_id}"}
                        ])
            
                    keyboard["inline_keyboard"].append([
                        {"text": "➕ Buat Sesi Baru", "callback_data": "new_session"}
                    ])
                    keyboard["inline_keyboard"].append([
                        {"text": "🗑️ Hapus Sesi", "callback_data": "delete_session"}
                    ])
            
                    send_message_with_keyboard(user_id, reply, keyboard)
                else:
                    create_new_session(user_id)                    
            
                return "OK", 200
            
            elif incoming_msg.lower() == "/new_session":
                return handle_new_session(user_id)
            
            elif incoming_msg.lower().startswith("/switch_session"):
                try:
                    session_id = int(incoming_msg.split()[1])
                    return handle_switch_session(user_id, session_id)
                except (IndexError, ValueError):
                    send_message(user_id, "⚠️ Format salah! Gunakan `/switch_session [ID]`.")
                    return "OK", 200
            
            elif incoming_msg.lower() == "/sessions":
                return handle_list_sessions(user_id)
            
            elif incoming_msg.lower().startswith("/delete_session"):
                try:
                    session_id = int(incoming_msg.split()[1])
                    return handle_delete_session(user_id, session_id)
                except (IndexError, ValueError):
                    send_message(user_id, "⚠️ Format salah! Gunakan `/delete_session [ID]`.")
                    return "OK", 200
            
            # Generate prompt and send to OpenAI for coaching response
            else:
                session = get_user_active_session(user_id)
                
                if not session:
                    create_new_session(user_id)
            
                categories = {
                    "1": "Stuck, Bingung Mulai",
                    "2": "Kebanyakan Ide, No Action",
                    "3": "Takut Gagal",
                    "4": "Susah Konsisten",
                    "5": "Kurang Percaya Diri",
                    "6": "Usaha Belum Berhasil",
                    "7": "Overthinking Parah",
                    "8": "Mudah Terdistraksi",
                    "9": "Zona Nyaman vs Tantangan",
                    "10": "Tahu Harus Ngapain, Tapi..."
                }

            
                # **Cek apakah user mengetik angka sebagai kategori**
                if not session.get("category_selected", False) and incoming_msg in categories:
                    first_msg = categories[incoming_msg]  # Ubah angka ke teks kategori
                    prompt = generate_prompt(user_id, first_msg, session)
                    coaching_output = send_to_openai(prompt)
                    update_coaching_session(user_id, session, first_msg, coaching_output, category_selected=True)  # Set kategori terpilih
                    send_message(user_id, coaching_output)
                    return "OK", 200
            
                # Jika bukan kategori, kirim sebagai input biasa ke OpenAI
                prompt = generate_prompt(user_id, incoming_msg, session)
                coaching_output = send_to_openai(prompt)
                update_coaching_session(user_id, session, incoming_msg, coaching_output)
                send_message(user_id, coaching_output)
                return "OK", 200

        elif "callback_query" in update:
            callback_data = update["callback_query"]["data"]
            user_id = update["callback_query"]["from"]["id"]
            
            if callback_data == "info":
                send_message(user_id, "ℹ️ *Tentang Coach Curhat*\n\nCoach Curhat adalah chatbot yang dirancang untuk membantu Kamu menemukan solusi atas tantangan hidup melalui refleksi dan coaching.")
            elif callback_data == "kontak":
                send_message(user_id, "📞 Kontak: Kamu dapat menghubungi admin di email: coachcurhat@gmail.com")

            elif callback_data == "start":
                return send_welcome_message(user_id)  # Hanya menampilkan menu tanpa mengubah sesi

            elif callback_data.startswith("switch_session_"):
                session_id = int(callback_data.split("_")[2])  # Ambil session ID
                return handle_switch_session(user_id, session_id)
        
            elif callback_data == "new_session":
                return handle_new_session(user_id)
        
            elif callback_data == "delete_session":
                return handle_delete_session(user_id)  # Akan menampilkan list sesi untuk dihapus
        
            elif callback_data == "sessions":
                return handle_list_sessions(user_id)  # Langsung gunakan fungsi yang sudah ada
        
            elif callback_data.startswith("confirm_delete_"):
                session_id = callback_data.split("_")[2]
                
                if session_id == "all":
                    delete_all_sessions(user_id)  # Hapus semua sesi
                    send_message(user_id, "✅ Semua sesi telah dihapus.")
                else:
                    delete_session(user_id, session_id)
                    send_message(user_id, f"✅ Sesi {session_id} telah dihapus.")
            
                return "OK", 200

            return "OK", 200
        
    except Exception as e:
        print(f"🔥 Error terjadi: {e}")  # Log error di server
        return "Internal Server Error", 500

@app.route('/')
def home():
    return "Chatbot is running!", 200

if __name__ == "X__main__":
    port = 5003
    if "KAGGLE_KERNEL_RUN_MODE" in os.environ:
        public_url = ngrok.connect("5003", "http")
        print(f"New Public URL: {public_url}")
        
        def run_flask():
            app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
        
        Thread(target=run_flask).start()
    else:
        public_url = ngrok.connect("5003", "http")
        print(f"New Public URL: {public_url}")
        app.run(host="0.0.0.0", port=port, debug=True, use_reloader=False)
        
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5003, debug=True)
