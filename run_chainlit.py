#!/usr/bin/env python3
# Скрипт для запуска Chainlit приложения

import os
import subprocess
import sys

def run_chainlit():
    """
    Запускает приложение Chainlit с правильными параметрами
    """
    port = os.environ.get("PORT", "5000")
    
    print(f"Запуск Chainlit на порту {port}...")
    
    # Команда для запуска Chainlit
    cmd = ["chainlit", "run", "app.py", "--host", "0.0.0.0", "--port", port]
    
    try:
        # Запуск Chainlit в текущем процессе
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Ошибка при запуске Chainlit: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("Приложение остановлено пользователем")

if __name__ == "__main__":
    run_chainlit()