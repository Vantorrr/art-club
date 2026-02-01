#!/bin/bash
# Скрипт для запуска вебхук сервера

echo "🚀 Запуск вебхук сервера для Prodamus..."
echo ""
echo "1️⃣ Установи ngrok если нет: brew install ngrok"
echo "2️⃣ В другом терминале запусти: ngrok http 8000"
echo "3️⃣ Скопируй URL из ngrok (https://xxx.ngrok.io)"
echo "4️⃣ Добавь в .env: PRODAMUS_WEBHOOK_URL=https://xxx.ngrok.io/webhook/prodamus"
echo ""
echo "Запускаем сервер на порту 8000..."
echo ""

cd /Users/pavelgalante/artclub
python -m uvicorn webhook.prodamus:app --host 0.0.0.0 --port 8000 --reload
