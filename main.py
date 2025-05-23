import os
import re
import json
import logging
from flask import Flask, render_template, request, jsonify
from openai import OpenAI
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# Настройка логирования
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Загрузка переменных окружения
load_dotenv()

# Получение API-ключа OpenAI и URL базы данных
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

# Setting the Supabase database URL directly (hardcoded for reliability)
DB_URL = "postgresql://postgres.zhjfohmbdqpljgcvgwbl:HackDB2025!@aws-0-eu-north-1.pooler.supabase.com:6543/postgres"

# Log the connection info
logger.info(f"Using Supabase database connection: {DB_URL[:25]}...")

# Инициализация Flask приложения
app = Flask(__name__)

# Инициализация OpenAI клиента
# the newest OpenAI model is "gpt-4o" which was released May 13, 2024.
client = OpenAI(api_key=OPENAI_API_KEY)

# Создание соединения с базой данных
try:
    # Удаляем 'postgresql://' и добавляем 'postgresql+psycopg2://' для корректной работы с SQLAlchemy
    if DB_URL and DB_URL.startswith('postgresql://'):
        db_connection_url = DB_URL
    else:
        raise ValueError("Invalid database URL format")
        
    engine = create_engine(db_connection_url)
    logger.info("Successfully connected to database")
except Exception as e:
    logger.error(f"Failed to connect to database: {str(e)}")
    raise

def get_table_info():
    """
    Получает информацию о таблицах и их схемах из базы данных.
    Возвращает строку с информацией о таблицах.
    """
    try:
        with engine.connect() as conn:
            # Запрос для получения списка таблиц
            table_query = """
            SELECT tablename 
            FROM pg_catalog.pg_tables 
            WHERE schemaname != 'pg_catalog' 
            AND schemaname != 'information_schema'
            """
            tables = conn.execute(text(table_query)).fetchall()
            
            # Сбор информации о каждой таблице
            table_info = []
            for table in tables:
                table_name = table[0]
                # Запрос для получения информации о столбцах таблицы
                column_query = f"""
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_name = '{table_name}'
                ORDER BY ordinal_position
                """
                columns = conn.execute(text(column_query)).fetchall()
                
                # Формирование описания таблицы
                column_descriptions = [
                    f"{col[0]} {col[1]}" for col in columns
                ]
                table_description = f"CREATE TABLE {table_name} (\n  "
                table_description += ",\n  ".join(column_descriptions)
                table_description += "\n);"
                table_info.append(table_description)
            
            return "\n\n".join(table_info)
    except Exception as e:
        logger.error(f"Error getting table info: {str(e)}")
        return "Error getting database schema information."

def get_tables_and_columns():
    """
    Получает информацию о таблицах и их столбцах для отображения в интерфейсе.
    Возвращает список словарей с информацией о таблицах.
    """
    try:
        with engine.connect() as conn:
            # Запрос для получения списка таблиц
            table_query = """
            SELECT tablename 
            FROM pg_catalog.pg_tables 
            WHERE schemaname != 'pg_catalog' 
            AND schemaname != 'information_schema'
            """
            tables = conn.execute(text(table_query)).fetchall()
            
            # List of tables to hide from the client dropdown
            hidden_tables = ['users']
            
            result = []
            for table in tables:
                table_name = table[0]
                
                # Skip hidden tables
                if table_name in hidden_tables:
                    continue
                    
                # Запрос для получения информации о столбцах таблицы
                column_query = f"""
                SELECT column_name
                FROM information_schema.columns 
                WHERE table_name = '{table_name}'
                ORDER BY ordinal_position
                """
                columns = conn.execute(text(column_query)).fetchall()
                column_names = [col[0] for col in columns]
                
                result.append({
                    "name": table_name,
                    "columns": column_names
                })
            
            return result
    except Exception as e:
        logger.error(f"Error getting tables and columns: {str(e)}")
        return []

def clean_sql_query(query):
    """
    Очищает SQL-запрос от комментариев и дополнительного текста,
    оставляя только исполняемый SQL.
    """
    # Удаление комментариев в стиле SQL (-- и /* */)
    query = re.sub(r'--.*?$', '', query, flags=re.MULTILINE)
    query = re.sub(r'/\*.*?\*/', '', query, flags=re.DOTALL)
    
    # Удаление backticks, которые часто добавляет LLM
    query = query.replace('`', '')
    
    # Проверка и ограничение запроса только SELECT-запросами
    if not query.strip().upper().startswith('SELECT'):
        if 'SELECT' in query.upper():
            # Извлечение части запроса, начинающейся с SELECT
            select_match = re.search(r'SELECT\s+.*', query, re.IGNORECASE | re.DOTALL)
            if select_match:
                query = select_match.group(0)
            else:
                raise ValueError("No valid SELECT statement found in query")
        else:
            raise ValueError("Only SELECT queries are allowed")
    
    # Remove any semicolons from the query as they can cause issues with prepared statements
    query = query.strip()
    if query.endswith(';'):
        query = query[:-1]
    
    # Make sure there are no multiple statements
    if ';' in query:
        # Keep only the first statement
        query = query.split(';')[0].strip()
    
    return query

def generate_sql_query(query, table_info):
    """
    Генерирует SQL-запрос на основе естественного языка с использованием OpenAI API.
    
    Args:
        query (str): Запрос на естественном языке
        table_info (str): Информация о схеме базы данных
        
    Returns:
        str: Сгенерированный SQL-запрос
    """
    # Получаем актуальную схему базы данных перед каждым запросом
    current_table_info = get_table_info()
    
    # Создание инструкции для модели
    prompt = f"""
    Ты - эксперт по SQL, который преобразует вопросы на естественном языке в SQL-запросы.
    
    На основе приведенной ниже схемы базы данных составь SQL-запрос, отвечающий на вопрос пользователя.
    Верни ТОЛЬКО SQL-запрос без объяснений, markdown форматирования или комментариев.
    
    Схема базы данных (это точная и актуальная схема, используй только эти таблицы и столбцы):
    {current_table_info}
    
    Важные правила:
    1. Генерируй ТОЛЬКО SELECT-запросы
    2. Не добавляй комментарии, backticks или markdown форматирование
    3. Используй только существующие таблицы и столбцы из схемы выше
    4. Убедись, что запрос может быть выполнен напрямую в PostgreSQL
    5. Используй псевдонимы для столбцов, чтобы сделать результаты более читаемыми
    6. Добавляй ORDER BY, когда это уместно
    7. Ограничивай результаты до 100 строк, если не указано иное
    8. Тщательно проверяй наличие таблиц и столбцов в схеме перед их использованием
    
    Вопрос пользователя: {query}
    
    SQL-запрос (только запрос, без комментариев или объяснений):
    """
    
    try:
        # Вызываем OpenAI API
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are an SQL expert specializing in PostgreSQL."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1
        )
        
        # Извлекаем сгенерированный SQL-запрос
        generated_sql = response.choices[0].message.content.strip()
        
        # Очищаем запрос от возможного markdown форматирования
        generated_sql = re.sub(r'```sql|```', '', generated_sql)
        generated_sql = generated_sql.strip()
        
        # Очистка SQL-запроса и проверка его безопасности
        cleaned_sql = clean_sql_query(generated_sql)
        
        logger.info(f"Generated SQL query: {cleaned_sql}")
        return cleaned_sql
        
    except Exception as e:
        logger.error(f"Error generating SQL: {str(e)}")
        raise ValueError(f"Failed to generate SQL: {str(e)}")

def execute_sql_query(sql_query):
    """
    Выполняет SQL-запрос и возвращает результаты.
    
    Args:
        sql_query (str): SQL-запрос
        
    Returns:
        tuple: (результаты в виде списка словарей, список имен столбцов)
    """
    try:
        # Ensure SQL query is properly sanitized
        if not sql_query or not isinstance(sql_query, str):
            raise ValueError("Invalid SQL query")
            
        # Remove any trailing semicolons and ensure no multiple statements
        sql_query = sql_query.strip()
        if sql_query.endswith(';'):
            sql_query = sql_query[:-1]
            
        # Ensure there are no multiple statements with semicolons
        if ';' in sql_query:
            sql_query = sql_query.split(';')[0].strip()
        
        # Ensure query starts with SELECT for safety
        if not sql_query.upper().startswith('SELECT'):
            raise ValueError("Only SELECT queries are allowed")
            
        # Подключение к базе данных
        with engine.connect() as conn:
            # Выполнение запроса
            result = conn.execute(text(sql_query))
            
            # Получение имен столбцов
            columns = result.keys()
            
            # Преобразование результатов в список словарей
            rows = []
            for row in result:
                rows.append({column: value for column, value in zip(columns, row)})
            
            logger.info(f"Query executed successfully. Found {len(rows)} results")
            return rows, list(columns)
    except Exception as e:
        logger.error(f"Error executing SQL query: {str(e)}")
        raise ValueError(f"Error executing query: {str(e)}")

@app.route('/')
def index():
    """Главная страница с интерфейсом чата"""
    return render_template('index.html')

@app.route('/api/tables', methods=['GET'])
def get_db_tables():
    """API для получения информации о таблицах"""
    try:
        tables = get_tables_and_columns()
        return jsonify({"tables": tables})
    except Exception as e:
        logger.error(f"Error getting tables: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/query', methods=['POST'])
def process_query():
    """API для обработки запроса на естественном языке"""
    try:
        # Получение запроса из JSON
        data = request.get_json()
        if not data or 'query' not in data:
            return jsonify({"error": "No query provided"}), 400
        
        user_query = data['query']
        logger.info(f"Received query: {user_query}")
        
        # Получение актуальной информации о таблицах
        table_info = get_table_info()
        logger.info(f"Retrieved table schema before query generation, schema length: {len(table_info)}")
        
        try:
            # Генерация SQL-запроса
            sql_query = generate_sql_query(user_query, table_info)
            
            # Выполнение запроса
            results, columns = execute_sql_query(sql_query)
            
            # Формирование ответа
            response = {
                "sql": sql_query,
                "results": results,
                "columns": columns
            }
            
            return jsonify(response)
            
        except ValueError as e:
            # Если ошибка связана с неправильным SQL, пытаемся указать конкретнее, что именно не так
            error_msg = str(e)
            if "relation" in error_msg and "does not exist" in error_msg:
                # Извлекаем имя таблицы из сообщения об ошибке
                import re
                table_match = re.search(r"relation \"(\w+)\" does not exist", error_msg)
                if table_match:
                    missing_table = table_match.group(1)
                    available_tables = []
                    
                    # Получаем список существующих таблиц для подсказки
                    with engine.connect() as conn:
                        tables_query = """
                        SELECT tablename 
                        FROM pg_catalog.pg_tables 
                        WHERE schemaname != 'pg_catalog' AND schemaname != 'information_schema'
                        """
                        tables = conn.execute(text(tables_query)).fetchall()
                        available_tables = [table[0] for table in tables]
                    
                    error_msg = f"Table '{missing_table}' does not exist. "
                    if available_tables:
                        error_msg += f"Available tables: {', '.join(available_tables)}"
                
            return jsonify({
                "error": error_msg,
                "sql": sql_query if 'sql_query' in locals() else None
            }), 400
    
    except ValueError as e:
        logger.error(f"Error processing query: {str(e)}")
        return jsonify({"error": str(e)}), 400
    
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        return jsonify({"error": "An unexpected error occurred"}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=True)