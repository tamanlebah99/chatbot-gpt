# Gunakan image Python
FROM python:3.9

# Set working directory
WORKDIR /app

# Salin file proyek
COPY . .

# Install library yang dibutuhkan
RUN pip install -r requirements.txt

# Jalankan aplikasi
CMD ["gunicorn", "-b", "0.0.0.0:5003", "main:app"]

