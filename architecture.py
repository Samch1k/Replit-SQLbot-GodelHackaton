
import graphviz

# Create a new directed graph
dot = graphviz.Digraph('Architecture', comment='Project Architecture')
dot.attr(rankdir='TB')

# Add nodes for main components
dot.node('client', 'Web Client\n(Browser)', shape='box')
dot.node('flask', 'Flask App\n(main.py)', shape='box')
dot.node('chainlit', 'Chainlit UI\n(app.py)', shape='box')
dot.node('db', 'PostgreSQL\nDatabase', shape='cylinder')
dot.node('openai', 'OpenAI API\n(GPT-4)', shape='cloud')
dot.node('sql_chain', 'SQL Chain\n(sql_chain.py)', shape='box')
dot.node('db_utils', 'DB Utils\n(db_utils.py)', shape='box')

# Add edges
dot.edge('client', 'flask', 'HTTP')
dot.edge('client', 'chainlit', 'WebSocket')
dot.edge('flask', 'db_utils', 'queries')
dot.edge('chainlit', 'sql_chain', 'queries')
dot.edge('sql_chain', 'openai', 'API calls')
dot.edge('sql_chain', 'db_utils', 'executes')
dot.edge('db_utils', 'db', 'SQL')

# Save the diagram
dot.render('architecture', format='png', cleanup=True)
print("Architecture diagram generated as 'architecture.png'")
