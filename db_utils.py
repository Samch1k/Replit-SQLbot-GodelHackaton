import os
import psycopg2
from psycopg2 import sql
from dotenv import load_dotenv
import logging

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_db_connection():
    """Create and return a database connection."""
    try:
        connection = psycopg2.connect(os.getenv("DATABASE_URL"))
        return connection
    except Exception as e:
        logger.error(f"Database connection error: {e}")
        raise Exception(f"Failed to connect to the database: {e}")

def get_table_info():
    """
    Get information about tables and their schemas from the database.
    Returns a string with table information.
    """
    try:
        connection = get_db_connection()
        cursor = connection.cursor()
        
        # Query to get table information
        cursor.execute("""
            SELECT 
                table_name,
                column_name,
                data_type,
                column_default,
                is_nullable
            FROM 
                information_schema.columns
            WHERE 
                table_schema = 'public'
            ORDER BY 
                table_name, ordinal_position;
        """)
        
        tables = cursor.fetchall()
        
        # Format the table info
        if not tables:
            return "No tables found in the database."
        
        # Group by table
        table_info = {}
        for row in tables:
            table_name, column_name, data_type, column_default, is_nullable = row
            
            if table_name not in table_info:
                table_info[table_name] = []
            
            nullable = "NULL" if is_nullable == "YES" else "NOT NULL"
            default = f"DEFAULT {column_default}" if column_default else ""
            
            table_info[table_name].append(
                f"{column_name} {data_type} {nullable} {default}".strip()
            )
        
        # Format as string
        result = []
        for table_name, columns in table_info.items():
            result.append(f"CREATE TABLE {table_name} (\n  " + ",\n  ".join(columns) + "\n);")
        
        cursor.close()
        connection.close()
        
        # Additional query to get foreign key relationships
        connection = get_db_connection()
        cursor = connection.cursor()
        
        cursor.execute("""
            SELECT
                tc.table_name, 
                kcu.column_name, 
                ccu.table_name AS foreign_table_name,
                ccu.column_name AS foreign_column_name 
            FROM 
                information_schema.table_constraints AS tc 
                JOIN information_schema.key_column_usage AS kcu
                ON tc.constraint_name = kcu.constraint_name
                AND tc.table_schema = kcu.table_schema
                JOIN information_schema.constraint_column_usage AS ccu 
                ON ccu.constraint_name = tc.constraint_name
                AND ccu.table_schema = tc.table_schema
            WHERE tc.constraint_type = 'FOREIGN KEY';
        """)
        
        foreign_keys = cursor.fetchall()
        
        # Add foreign key information
        if foreign_keys:
            result.append("\n-- Foreign Key Relationships:")
            for fk in foreign_keys:
                table, column, ref_table, ref_column = fk
                result.append(f"-- {table}.{column} -> {ref_table}.{ref_column}")
        
        cursor.close()
        connection.close()
        
        return "\n\n".join(result)
        
    except Exception as e:
        logger.error(f"Error fetching table information: {e}")
        return f"Error getting table information: {str(e)}"

def execute_sql_query(query):
    """
    Execute a SQL query and return the results.
    
    Args:
        query (str): SQL query to execute
        
    Returns:
        tuple: (results, column_names)
    """
    try:
        # Input validation
        if not query or not isinstance(query, str):
            logger.error(f"Invalid SQL query: {query}")
            raise ValueError("Invalid SQL query")
        
        # Strip any trailing semicolons to prevent multi-query execution
        query = query.strip()
        if query.endswith(';'):
            query = query[:-1]
        
        # Prevent multiple queries from being executed
        if query.count(';') > 0:
            logger.error(f"Multiple SQL queries detected: {query}")
            raise ValueError("Multiple SQL queries are not allowed")
        
        # Establish database connection
        connection = get_db_connection()
        cursor = connection.cursor()
        
        # Execute the query
        cursor.execute(query)
        
        # Get column names
        column_names = [desc[0] for desc in cursor.description] if cursor.description else []
        
        # Fetch results
        results = cursor.fetchall()
        
        # Commit changes if needed (for INSERT, UPDATE, DELETE)
        if query.strip().upper().startswith(('INSERT', 'UPDATE', 'DELETE')):
            connection.commit()
            results = [f"Query affected {cursor.rowcount} rows"]
        
        # Close connections
        cursor.close()
        connection.close()
        
        return results, column_names
        
    except Exception as e:
        logger.error(f"Error executing SQL query: {e}")
        raise Exception(f"Error executing SQL query: {str(e)}")
