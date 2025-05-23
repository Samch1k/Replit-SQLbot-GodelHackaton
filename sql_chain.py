from langchain.agents import AgentExecutor, create_openai_functions_agent
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.tools import tool
from langchain.schema import SystemMessage
from db_utils import execute_sql_query
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@tool
def generate_sql_query(query: str, table_info: str) -> str:
    """
    Generate a SQL query based on the natural language query and table information.
    
    Args:
        query (str): Natural language query from the user
        table_info (str): Information about database tables and schema
        
    Returns:
        str: The generated SQL query
    """
    return f"I need to generate a SQL query for: {query}\nTable structure: {table_info}"

@tool
def run_sql_query(sql_query: str) -> str:
    """
    Execute the given SQL query and return the results.
    
    Args:
        sql_query (str): SQL query to execute
        
    Returns:
        str: The query results
    """
    try:
        result, column_names = execute_sql_query(sql_query)
        
        # Format the result for display
        if result:
            # Format column headers
            formatted_result = "| " + " | ".join(column_names) + " |\n"
            # Add separator line
            formatted_result += "| " + " | ".join(["---" for _ in column_names]) + " |\n"
            
            # Format rows
            for row in result:
                formatted_values = []
                for val in row:
                    if val is None:
                        formatted_values.append("NULL")
                    else:
                        formatted_values.append(str(val))
                formatted_result += "| " + " | ".join(formatted_values) + " |\n"
            
            return formatted_result
        else:
            return "No results found for this query."
            
    except Exception as e:
        logger.error(f"Error executing SQL query: {e}")
        return f"Error executing SQL query: {str(e)}"

def create_sql_agent(llm, table_info):
    """
    Create an agent that can convert natural language to SQL and execute queries.
    
    Args:
        llm: Language model to use
        table_info (str): Information about database tables and schema
        
    Returns:
        AgentExecutor: An agent that can process SQL queries
    """
    # Define the agent tools
    tools = [
        run_sql_query
    ]

    # Create a system prompt for the agent
    system_prompt = f"""You are an expert SQL assistant. You help users query a PostgreSQL database by converting their 
natural language questions into SQL queries and executing them.

Here is the database schema information:
{table_info}

Follow these rules:
1. Generate clear, correct SQL queries based on user's questions
2. Use only tables and columns that exist in the schema
3. For ambiguous questions, ask for clarification
4. Format SQL queries with proper indentation and line breaks for readability
5. Always use SELECT * FROM table LIMIT 10 when the user wants to see sample data
6. Explain the SQL query if it's complex
7. NEVER make up tables or columns that don't exist in the schema
8. Ensure all SQL queries are PostgreSQL compatible
9. Prioritize performance in your queries
10. For pagination, use LIMIT and OFFSET
11. Always return the final SQL query along with the results

Respond in the following format:
SQL Query: <the generated SQL query>
Results: <the query results or error message>
Explanation: <brief explanation if needed>

Remember, your goal is to help users get accurate data with well-formed SQL queries.
"""

    # Create a prompt template with the system message and placeholders for chat history
    prompt = ChatPromptTemplate.from_messages(
        [
            SystemMessage(content=system_prompt),
            MessagesPlaceholder(variable_name="chat_history", optional=True),
            ("human", "{query}"),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
        ]
    )

    # Create the agent
    agent = create_openai_functions_agent(llm, tools, prompt)
    
    # Create the agent executor
    agent_executor = AgentExecutor(
        agent=agent,
        tools=tools,
        verbose=True,
        handle_parsing_errors=True,
        max_iterations=5,
        return_intermediate_steps=False,
    )
    
    return agent_executor
