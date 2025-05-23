import os
import re
import logging
import pandas as pd
import plotly.express as px
import chainlit as cl
from sqlalchemy import create_engine, text
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
from langchain.chains import create_sql_query_chain
from langchain_community.utilities.sql_database import SQLDatabase

# Настройка логирования
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Получение секретов из переменных окружения
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
SUPABASE_DB_URL = os.environ.get("SUPABASE_DB_URL")

# Если переменная DATABASE_URL существует, используем её (для обратной совместимости)
db_url = os.environ.get("DATABASE_URL", SUPABASE_DB_URL)

# Проверка наличия необходимых API ключей
if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY environment variable not set")
if not db_url:
    raise ValueError("DATABASE connection URL not set. Please set SUPABASE_DB_URL")

logger.info("Initializing application with database URL: %s", db_url[:20] + "...")

# Инициализация LLM модели
# the newest OpenAI model is "gpt-4o" which was released May 13, 2024.
llm = ChatOpenAI(
    model="gpt-4o",
    temperature=0.1,  # Небольшая вариативность для лучшей адаптации к запросам
    api_key=OPENAI_API_KEY
)

# Подключение к базе данных
try:
    db = SQLDatabase.from_uri(db_url)
    # Создание экземпляра SQLAlchemy engine для работы с pandas
    engine = create_engine(db_url)
    logger.info("Successfully connected to database")
except Exception as e:
    logger.error(f"Failed to connect to database: {str(e)}")
    raise

# Получение схемы таблиц
def get_table_schema():
    """Получает информацию о схеме базы данных"""
    try:
        schema_info = db.get_table_info()
        logger.info(f"Retrieved database schema, length: {len(schema_info)}")
        return schema_info
    except Exception as e:
        logger.error(f"Error getting database schema: {str(e)}")
        return "Error retrieving database schema."

# Функция для очистки SQL-запроса сгенерированного LLM
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
    
    # Проверка на наличие точки с запятой в конце
    query = query.strip()
    if not query.endswith(';'):
        query += ';'
    
    return query

# Инициализация SQL chain для генерации запросов
template = """
You are an expert Oracle SQL assistant that converts natural language questions to SQL.

Based on the database schema below, write a SELECT query that answers the user's question.
Return ONLY the SQL query without any explanation, comments, or markdown formatting.

Database Schema:
{schema}

Important rules:
1. ONLY generate a valid SELECT query.
2. Do NOT include any explanations or comments in your response.
3. Make sure the tables and columns referenced exist in the schema.
4. Only generate a SQL query that can be executed directly.
5. Use aliases for column names to make results more readable.
6. Add an ORDER BY clause when appropriate.
7. Limit results to 100 rows maximum unless specified otherwise.

User Question: {question}

SQL Query (IMPORTANT: return ONLY the SQL query):"""

prompt = ChatPromptTemplate.from_template(template)
sql_chain = create_sql_query_chain(llm, db, prompt=prompt)

# Функция для выполнения SQL-запроса и получения результатов в виде pandas DataFrame
def execute_sql(query):
    """Выполняет SQL-запрос и возвращает результаты как pandas DataFrame"""
    try:
        # Очистка запроса
        clean_query = clean_sql_query(query)
        logger.info(f"Executing SQL query: {clean_query}")
        
        # Выполнение запроса
        with engine.connect() as connection:
            df = pd.read_sql_query(text(clean_query), connection)
        
        logger.info(f"Query executed successfully. Result shape: {df.shape}")
        return df, None
    except Exception as e:
        logger.error(f"Error executing SQL query: {str(e)}")
        return None, str(e)

@cl.on_chat_start
async def on_chat_start():
    """Инициализация сессии чата и отображение приветственного сообщения"""
    try:
        # Получаем схему базы данных
        schema = get_table_schema()
        
        # Сохраняем схему в сессии пользователя
        cl.user_session.set("schema", schema)
        
        # Извлекаем имена таблиц для приветственного сообщения
        table_pattern = r"CREATE TABLE (\w+)"
        tables = re.findall(table_pattern, schema)
        
        # Если таблицы не найдены, используем запасной вариант с описанием таблиц
        if not tables:
            tables = ["technologies", "projects"]
            logger.warning("No tables found in schema, using fallback table list")
        
        # Приветственное сообщение с доступными таблицами
        welcome_message = f"""# 👋 Добро пожаловать в Oracle SQL Assistant!

Я могу помочь вам запрашивать базу данных, используя естественный язык.

### Доступные таблицы:
{', '.join(f'`{table}`' for table in tables)}

### Примеры запросов:
- "Какие технологии чаще всего используются в проектах?"
- "Покажи все проекты, начатые после 2020 года"
- "Сколько проектов у нас в разработке?"
"""
        
        await cl.Message(content=welcome_message).send()
        
    except Exception as e:
        error_message = f"⚠️ Ошибка при инициализации: {str(e)}"
        logger.error(error_message)
        await cl.Message(content=error_message).send()

@cl.on_message
async def on_message(message: cl.Message):
    """Обработка сообщений пользователя и генерация SQL-ответов"""
    # Получаем вопрос пользователя
    user_question = message.content
    logger.info(f"Received user question: {user_question}")
    
    # Получаем схему из сессии пользователя
    schema = cl.user_session.get("schema")
    if not schema:
        logger.warning("Schema not found in session, fetching again")
        schema = get_table_schema()
        cl.user_session.set("schema", schema)
    
    # Создаем сообщение о том, что идет обработка
    thinking_msg = cl.Message(content="🤔 Обрабатываю ваш запрос...")
    await thinking_msg.send()
    
    try:
        # Генерация SQL-запроса из естественного языка
        await thinking_msg.update(content="🔍 Генерирую SQL-запрос...")
        logger.info("Generating SQL query for user question")
        
        sql_query = await cl.make_async(sql_chain.invoke)({"question": user_question, "schema": schema})
        logger.info(f"Generated SQL query: {sql_query}")
        
        # Исполнение SQL-запроса
        await thinking_msg.update(content=f"⚙️ Выполняю SQL-запрос:\n```sql\n{sql_query}\n```")
        
        # Получаем результаты в виде DataFrame
        df, error = execute_sql(sql_query)
        
        if error:
            # Ошибка при выполнении запроса
            await thinking_msg.update(content=f"""⚠️ Ошибка при выполнении запроса:
```sql
{sql_query}
```

**Ошибка**: {error}
""")
            return
        
        # Определяем метод визуализации на основе формы результата
        elements = []
        
        if df.empty:
            # Нет результатов
            result_content = "Запрос не вернул результатов."
        else:
            # Форматируем результат как таблицу Markdown
            table_md = df.to_markdown(index=False)
            result_content = f"## Результаты запроса\n\n{table_md}"
            
            # Проверяем, подходят ли данные для визуализации в виде графика
            if len(df.columns) == 2 and df.shape[0] > 1 and df.shape[0] <= 15:
                # Два столбца с несколькими строками - хороший кандидат для столбчатой диаграммы
                # Проверяем, является ли второй столбец числовым
                if pd.api.types.is_numeric_dtype(df.iloc[:, 1]):
                    try:
                        # Создаем столбчатую диаграмму Plotly
                        fig = px.bar(df, x=df.columns[0], y=df.columns[1], 
                                     title=f"Результаты: {df.shape[0]} строк",
                                     labels={df.columns[0]: df.columns[0], df.columns[1]: df.columns[1]})
                        
                        # Форматирование графика для темной темы
                        fig.update_layout(
                            template="plotly_dark",
                            paper_bgcolor="rgba(0,0,0,0)",
                            plot_bgcolor="rgba(30,30,30,0.3)",
                            margin=dict(l=20, r=20, t=40, b=20),
                        )
                        
                        # Добавляем элемент Plotly
                        elements = [cl.Plotly(name="results_chart", figure=fig)]
                        logger.info("Created bar chart visualization")
                    except Exception as viz_error:
                        logger.error(f"Error creating visualization: {str(viz_error)}")
        
        # Подготовка итогового ответа с SQL-запросом и результатами
        final_content = f"""### SQL-запрос
```sql
{sql_query}
```

{result_content}

Найдено {df.shape[0]} строк и {df.shape[1]} столбцов.
"""
        
        # Отправляем итоговое сообщение с запросом и результатами
        if elements:
            await thinking_msg.update(content=final_content, elements=elements)
        else:
            await thinking_msg.update(content=final_content)
            
    except Exception as e:
        # Ошибка при генерации или обработке SQL
        error_message = f"⚠️ Произошла ошибка: {str(e)}"
        logger.error(error_message)
        await thinking_msg.update(content=error_message)