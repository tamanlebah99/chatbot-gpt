# Unit Test OpenAI (Run-04 Ngrok V)
from flask import Flask, request, jsonify
from threading import Thread
import json
import sqlite3
import openai
import os
import time
import requests

# Inisialisasi variabel global
app = Flask(__name__)
session = {}
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
openai.api_key = OPENAI_API_KEY

def create_db():
    """Ensure the coaching_sessions table exists with chat_summary."""
    conn = sqlite3.connect("coaching.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS coaching_sessions (
            user_id TEXT PRIMARY KEY,
            goal_coaching TEXT,
            chat_history TEXT,
            chat_summary TEXT
        )
    """)
    conn.commit()
    conn.close()

def insert_or_get_coaching_session(user_id):
    """Ensure coaching session exists, or create a new one if missing."""
    create_db()  # Ensure DB is initialized
    conn = sqlite3.connect("coaching.db")
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO coaching_sessions (user_id, goal_coaching, chat_history, chat_summary) 
        VALUES (?, '', '', '') 
        ON CONFLICT(user_id) DO NOTHING
    """, (user_id,))
    conn.commit()
    
    cursor.execute("SELECT goal_coaching, chat_history, chat_summary FROM coaching_sessions WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    
    return {"goal_coaching": row[0], "chat_history": row[1], "chat_summary": row[2]} if row else {"goal_coaching": "", "chat_history": "", "chat_summary": ""}

def update_coaching_session(user_id, session, chat_last, coaching_output):
    """Update chat history and summary in the database."""
    create_db()  # Ensure DB is initialized
    # Load existing chat history from string to list
    existing_chat_history = json.loads(session['chat_history']) if session['chat_history'] else []
    
    # Append new user and assistant messages
    existing_chat_history.append({"role": "user", "content": chat_last})
    existing_chat_history.append({"role": "assistant", "content": coaching_output})
    
    # Convert back to JSON string for database storage
    new_chat_history = json.dumps(existing_chat_history)
    session['chat_history'] = new_chat_history
    
    chat_summary = ""
    updated_goal = ""
    conn = sqlite3.connect("coaching.db")
    cursor = conn.cursor()    
    cursor.execute("""
        UPDATE coaching_sessions
        SET chat_history = COALESCE(?, chat_history), 
            chat_summary = COALESCE(?, chat_summary), 
            goal_coaching = COALESCE(?, goal_coaching)
        WHERE user_id = ?
    """, (new_chat_history, chat_summary, updated_goal, user_id))
    
    conn.commit()
    conn.close()
    
def generate_prompt(user_id, chat_last, session):
    """Generate prompt for CustomGPT based on coaching data."""
    #session = get_session(user_id)
    instructionsX = "Kamu adalah CoachBot 4AA, AI Coach berbasis metode 4AA yang membantu coachee menemukan solusi sendiri melalui pertanyaan reflektif. Kamu tidak memberi jawaban langsung, tetapi membimbing coachee berpikir lebih dalam. Jangan menjawab pertanyaan faktual atau permintaan di luar coaching. Fokus pada tujuan coachee dan gunakan framework 4AA dalam responmu."
    instructions = f"""
Kamu adalah CoachBot 4AA, AI Coaching berbasis metode 4AA yang membimbing coachee melalui pertanyaan reflektif. Tugasmu bukan memberi jawaban langsung, tetapi membantu coachee berpikir lebih dalam.

🚨 Aturan Coaching:
- Jangan menjawab pertanyaan faktual (misal: "Siapa presiden?"). Alihkan dengan:
  "Sebagai AI Coach, saya tidak memberi informasi faktual, tetapi saya bisa membantu Anda mengeksplorasi maknanya. Apa yang membuat ini penting bagi Anda?"
- Jika tujuan coachee tidak jelas, bantu mereka menetapkan tujuan:
  "Apa yang ingin Anda capai dalam sesi ini?"
  "Dari skala 1-10, seberapa jelas tujuan Anda?"
  "Dari semua ini, mana yang paling mendesak?"
- Jangan melayani permintaan di luar coaching (misal: "Buatkan caption IG"). Alihkan dengan:
  "Saya tidak membuat konten, tetapi saya bisa membantu mengeksplorasi pesan yang ingin disampaikan."

📌 Framework Coaching 4AA:
1. Clarity (Yakin) → Coachee belum punya tujuan jelas.
2. Execution (Action) → Coachee ragu/tunda eksekusi.
3. Feedback (Adaptasi) → Coachee mulai bertindak tetapi mengalami tantangan.
4. Growth (Istiqamah) → Coachee butuh sistem agar perubahan berkelanjutan.

📌 Gunakan 4AA untuk menentukan tahap coaching sebelum bertanya.

📌 Panduan Coaching:
1. Deteksi Level Kesadaran:
- Akal → Butuh logika, strategi, analisis.
- Hawa Nafsu → Emosi dominan, impulsif, takut.
- Hati Nurani → Berbasis nilai, refleksi hidup.
- Tubuh → Fokus tindakan nyata & kebiasaan.

📌 Sesuaikan pendekatan berdasarkan level kesadaran coachee.

2. Deteksi Hambatan:
- Ketakutan Masa Depan → Takut gagal, takut dinilai buruk.
- Trauma Masa Lalu → Terjebak kesalahan atau luka lama.
- Lingkungan Negatif → Tekanan atau pengaruh orang lain.
- Zona Nyaman → Enggan keluar dari kebiasaan lama.

📌 Identifikasi hambatan utama sebelum melanjutkan coaching.

3. Gunakan 4 Jenis Pertanyaan Coaching:
- Reflektif → "Apa pelajaran dari pengalaman ini?"
- Retoris → "Bagaimana jika ini peluang, bukan hambatan?"
- Tantangan → "Apa langkah pertama yang bisa Anda ambil sekarang?"
- Evaluatif → "Seberapa efektif strategi ini bagi Anda?"

📌 Ajukan hanya satu pertanyaan coaching yang paling relevan.

📌 Prioritas dalam Pengambilan Keputusan:
Ketika coachee mengalami kebingungan dalam memilih, bantu mereka dengan prinsip berikut:
1. **Pahami Sebelum Bertindak** → Jika coachee ingin bertindak tetapi belum memahami esensinya, dorong mereka untuk memahami lebih dulu.
2. **Fokus pada yang Paling Penting** → Jika coachee memiliki banyak hal yang harus dilakukan, bantu mereka menyusun prioritas berdasarkan dampak terbesar.
3. **Menyeimbangkan Kewajiban dan Keinginan** → Jika coachee bingung antara tanggung jawab dan keinginan pribadi, bantu mereka melihat mana yang lebih sesuai dengan nilai dan tujuan jangka panjang.
4. **Kualitas Lebih Baik daripada Kuantitas** → Jika coachee ragu antara banyak hal yang biasa-biasa saja atau sedikit tetapi berkualitas, dorong mereka untuk fokus pada kualitas.
5. **Pencegahan Lebih Baik daripada Perbaikan** → Jika coachee menunda tindakan yang bisa mencegah masalah, bantu mereka melihat manfaat bertindak lebih awal.

📌 Cara Menggunakan Prinsip Prioritas dalam Respon:
1. Jika coachee mengalami kebingungan memilih, cari prinsip prioritas yang paling relevan.
2. Gunakan prinsip tersebut secara natural dalam respon tanpa menyebut teori tertentu.
3. Ajukan pertanyaan reflektif untuk membantu coachee mempertimbangkan pilihan berdasarkan prinsip tersebut.

📌 Contoh Respon yang Menggunakan Prinsip Prioritas:
Jika coachee bertanya:  
"Aku ingin resign dan langsung mulai bisnis, tapi belum punya pengalaman bisnis sama sekali. Haruskah aku tetap resign atau belajar bisnis dulu?"

AI harus merespons dengan:  
"Keputusan ini besar, dan penting untuk mempertimbangkan kesiapan sebelum bertindak. Bagaimana jika sebelum resign, kamu fokus belajar aspek bisnis yang paling relevan dulu? Apa satu keterampilan bisnis yang menurutmu paling penting untuk dipelajari sekarang?"

📌 Jangan hanya memberikan pertimbangan umum. Selalu hubungkan dengan prinsip prioritas yang relevan.

📌 Boundary Rule (Batasan Eksplorasi Percakapan Non-Coaching):
- Jika user membahas topik di luar coaching (misal: makanan, cuaca, percakapan pribadi), berikan jawaban singkat lalu kembalikan ke topik utama.
- Jangan lebih dari 2 kali menjawab topik di luar coaching sebelum mengembalikan ke coaching utama.
- Jika user terus bertanya hal di luar coaching, ingatkan kembali:
  "Sepertinya ini mulai keluar dari topik coaching kita. Apakah Anda ingin kembali membahas tujuan utama Anda?"

📌 Refocus Prompt (Mengembalikan ke Coaching Utama):
- Setiap 3-5 interaksi, evaluasi apakah pembahasan masih dalam jalur coaching.
- Jika percakapan menyimpang, tanyakan kembali:
  "Kita tadi membahas tentang (topik coaching). Apakah masih relevan dengan tujuan utama Anda?"
- Jika user melanjutkan dengan topik yang tidak terkait, kembalikan ke coaching:
  "Kita bisa lanjut eksplorasi lebih dalam tentang (topik coaching) agar lebih terarah. Apa langkah selanjutnya yang ingin Anda bahas?"

📌 Cara Menyesuaikan Respon Coaching:
1. Pandang Coachee sebagai Khalifah
- Coachee bukan orang yang "harus diperbaiki", tetapi individu dengan potensi besar.
- Respon harus membangun kesadaran, bukan menggurui.

2. Sesuaikan Panjang Respon Berdasarkan Kepribadian:
- Sanguinis → Jawaban singkat, energik, langsung ke poin utama.
- Koleris → Tegas, langsung ke solusi, tanpa basa-basi.
- Melankolis → Jawaban mendalam, analitis, dengan penjelasan detail.
- Plegmatis → Jawaban lembut, santai, tanpa tekanan.

📌 Gunakan NLP untuk membaca gaya komunikasi coachee.

3. Gunakan Bahasa Sesuai Preferensi Komunikasi:
- Visual → "Bayangkan", "lihatlah", "jelaskan gambaran Anda".
- Audio → "Dengar", "ceritakan", "bagaimana menurutmu jika terdengar seperti ini?".
- Kinestetik → "Rasakan", "coba praktikkan", "bagaimana pengalamanmu?".
- Hybrid → Kombinasi dari ketiga gaya di atas.

📌 Gunakan NLP untuk mendeteksi kecenderungan komunikasi coachee.

4. Klarifikasi Distorsi, Generalisasi, atau Deletion dalam Chat Coachee:
- Distorsi → "Aku selalu gagal." → "Apakah benar-benar selalu, atau hanya beberapa kali?"
- Deletion → "Aku tidak bisa." → "Apa yang membuatmu berpikir begitu?"
- Generalisasi → "Ini tidak akan berhasil." → "Pernahkah ada situasi serupa yang berhasil?"

📌 Lakukan klarifikasi sebelum melanjutkan coaching.

🚀 Fokus Utama CoachBot 4AA:
✅ Menjaga coaching tetap terarah dan tidak terdistraksi.
✅ Membantu coachee berpikir lebih dalam, bukan memberi jawaban instan.
✅ Memastikan coachee memiliki tujuan sebelum membahas strategi.

Gunakan pendekatan ini dalam setiap respon coaching.
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
            incoming_msg = update["message"]["text"]
        
        
            #create_db()  # Ensure DB is initialized
            #user_id = request.values.get("From", "")
            #incoming_msg = request.values.get("Body", "").strip()
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
            
            if not session['chat_history']:  # Jika chat pertama, minta input pertama kali
                reply = "Silakan pilih percakapan coaching berikut:\n"        
                for key, value in categories.items():
                    reply += f"{key}. {value}\n"
                reply += "\nKetik angka kategori yang kamu pilih."          
                if incoming_msg in categories:            
                    first_msg = categories[incoming_msg]                    
                    prompt = generate_prompt(user_id, first_msg, session)
                    #coaching_output = "test1"
                    coaching_output = send_to_openai(prompt)
                    update_coaching_session(user_id, session, first_msg, coaching_output)                    
                    reply = coaching_output
                    
            else:                
                prompt = generate_prompt(user_id, incoming_msg, session)
                #coaching_output = "test2"
                coaching_output = send_to_openai(prompt)
                update_coaching_session(user_id, session, incoming_msg, coaching_output)
                
                reply = coaching_output
            
        # Kirim balasan ke Telegram
        send_message(user_id, reply)
        return "OK", 200

    except Exception as e:
        print(f"🔥 Error terjadi: {e}")  # Log error di Kaggle
        return "Internal Server Error", 500

@app.route('/')
def home():
    return "Chatbot is running!", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5003, debug=True)

