#!/usr/bin/env python3
"""
WSGI приложение для запуска Chainlit
"""
import os
import subprocess
import threading
import time
from flask import Flask, render_template_string

app = Flask(__name__)

chainlit_process = None

def run_chainlit():
    """Запускает процесс Chainlit"""
    global chainlit_process
    try:
        env = os.environ.copy()
        chainlit_process = subprocess.Popen(
            ["chainlit", "run", "app.py", "--host", "0.0.0.0", "--port", "8000"],
            env=env
        )
        chainlit_process.wait()
    except Exception as e:
        print(f"Ошибка при запуске Chainlit: {e}")

@app.route('/')
def index():
    """Основная страница, перенаправляющая на Chainlit UI"""
    # HTML с автоматическим перенаправлением на Chainlit
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>SQL Assistant</title>
        <meta http-equiv="refresh" content="0;url=http://localhost:8000">
        <script>
            window.location.href = window.location.href.replace(':5000', ':8000');
        </script>
        <style>
            body {
                font-family: Arial, sans-serif;
                margin: 40px;
                text-align: center;
                background-color: #21232d;
                color: #ffffff;
            }
            .container {
                max-width: 600px;
                margin: 0 auto;
                padding: 20px;
                background-color: #2d2f3b;
                border-radius: 8px;
                box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
            }
            h1 {
                color: #6c8eef;
            }
            p {
                font-size: 18px;
                line-height: 1.6;
            }
            a {
                color: #6c8eef;
                text-decoration: none;
            }
            a:hover {
                text-decoration: underline;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>SQL Ассистент</h1>
            <p>Перенаправление на интерфейс Chainlit...</p>
            <p>Если автоматическое перенаправление не работает, <a href="http://localhost:8000">нажмите здесь</a>.</p>
        </div>
    </body>
    </html>
    """
    return render_template_string(html)

# Запуск Chainlit в отдельном потоке
def start_chainlit_thread():
    """Запускает Chainlit в отдельном потоке"""
    thread = threading.Thread(target=run_chainlit)
    thread.daemon = True
    thread.start()
    # Ждем немного, чтобы Chainlit успел запуститься
    time.sleep(2)

# Запускаем Chainlit при запуске приложения
start_chainlit_thread()

if __name__ == '__main__':
    # Приложение Flask будет служить прокси к Chainlit
    app.run(host='0.0.0.0', port=5000)