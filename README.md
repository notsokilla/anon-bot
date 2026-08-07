# Запуск
cp .env  # заполнить BOT_TOKEN, ADMIN_IDS, PROVIDER_TOKEN
docker compose up --build -d

# Локально без докера
pip install -r requirements.txt
python -m app.main