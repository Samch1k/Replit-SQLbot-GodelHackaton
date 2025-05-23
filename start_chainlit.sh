#!/bin/bash
# Скрипт для запуска Chainlit

# Установка переменных окружения (если нужно)
export PORT=${PORT:-5000}

# Запуск Chainlit
echo "Запуск Chainlit на порту $PORT..."
chainlit run app.py --host 0.0.0.0 --port $PORT