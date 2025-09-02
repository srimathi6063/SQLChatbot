import os
import gradio as gr
import logging
from datetime import datetime
import request_handler

# Logging configuration
logging.basicConfig(
    filename="logFile.log",
    level=logging.INFO,
    format="%(asctime)s %(levelname)s | %(message)s"
)

def format_db_result(db_result):
    if not db_result or 'rows' not in db_result or not db_result['rows']:
        return "🧐 **No Results Found**\n\nYour query executed successfully but returned no data."

    columns = db_result.get('columns', [])
    rows = db_result.get('rows', [])

    if len(rows) > 20:
        display_rows = rows[:20]
        truncated = True
    else:
        display_rows = rows
        truncated = False

    result = f"📋 **Query Results** ({len(rows)} record{'s' if len(rows) != 1 else ''})\n\n"
    header = "| " + " | ".join(columns) + " |\n"
    separator = "|" + "|".join([" --- " for _ in columns]) + "|\n"
    result += header + separator

    for row in display_rows:
        formatted_row = []
        for cell in row:
            if cell is None:
                formatted_row.append("*NULL*")
            elif isinstance(cell, str) and len(cell) > 50:
                formatted_row.append(cell[:47] + "...")
            else:
                formatted_row.append(str(cell))
        result += "| " + " | ".join(formatted_row) + " |\n"

    if truncated:
        result += f"\n⚠️ **Note**: Showing first 20 records out of {len(rows)} total records."

    return result

def chatbot(user_input, history=None):
    if history is None:
        history = []

    logging.info(f"USER: {user_input}")
    
    response = request_handler.handle_user_query(user_input)
    
    if "error" in response:
        answer = f"🔥 **Error**\n\n{response['error']}"
        if 'sql' in response:
            answer += f"\n\n**📝 Generated SQL:**\n```sql\n{response['sql']}\n```"
    else:
        sql_display = response['sql']
        if response.get("corrected", False):
            answer = (
                f"✅ **Query Corrected and Executed Successfully**\n\n"
                f"**📝 Corrected SQL:**\n```sql\n{sql_display}\n```\n\n"
                f"**📊 Results:**\n{format_db_result(response['result'])}"
            )
        else:
            answer = (
                f"✅ **Query Executed Successfully**\n\n"
                f"**📝 Generated SQL:**\n```sql\n{sql_display}\n```\n\n"
                f"**📊 Results:**\n{format_db_result(response['result'])}"
            )

    history = history + [[user_input, answer]]
    return history, ""

def clear_chat():
    return [], ""

# Custom CSS for a modern chat interface
custom_css = """
@import url('https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;500;600;700&display=swap');

.gradio-container {
    font-family: 'Poppins', sans-serif !important;
    background-color: #f5f7fa !important;
    min-height: 100vh;
}

/* Chat container styling */
.chatbot {
    border-radius: 16px !important;
    box-shadow: 0 4px 30px rgba(0, 0, 0, 0.05) !important;
    border: 1px solid rgba(255, 255, 255, 0.3) !important;
    background: rgba(255, 255, 255, 0.8) !important;
    backdrop-filter: blur(10px) !important;
    height: 70vh !important;
}

/* Message bubbles */
.chatbot .message {
    padding: 12px 16px !important;
    border-radius: 18px !important;
    margin: 8px 0 !important;
    line-height: 1.5 !important;
}

.chatbot .message.user {
    background: linear-gradient(135deg, #6e8efb 0%, #4a6cf7 100%) !important;
    color: white !important;
    border-bottom-right-radius: 4px !important;
    margin-left: auto !important;
    max-width: 80% !important;
}

.chatbot .message.bot {
    background: white !important;
    color: #333 !important;
    border: 1px solid #e5e7eb !important;
    border-bottom-left-radius: 4px !important;
    margin-right: auto !important;
    max-width: 80% !important;
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05) !important;
}

/* Input area */
.textbox textarea {
    border-radius: 12px !important;
    border: 1px solid #e5e7eb !important;
    padding: 12px 16px !important;
    font-size: 15px !important;
    background: white !important;
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05) !important;
}

.textbox textarea:focus {
    border-color: #4a6cf7 !important;
    box-shadow: 0 0 0 2px rgba(74, 108, 247, 0.2) !important;
}

/* Buttons */
.button {
    border-radius: 12px !important;
    padding: 8px 16px !important;
    font-weight: 500 !important;
    transition: all 0.2s ease !important;
}

.button.primary {
    background: linear-gradient(135deg, #6e8efb 0%, #4a6cf7 100%) !important;
    color: white !important;
    border: none !important;
}

.button.secondary {
    background: white !important;
    color: #4a6cf7 !important;
    border: 1px solid #e5e7eb !important;
}

.button:hover {
    transform: translateY(-2px) !important;
    box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1) !important;
}

/* Example cards */
.example-card {
    border-radius: 12px !important;
    padding: 16px !important;
    background: white !important;
    border: 1px solid #e5e7eb !important;
    cursor: pointer !important;
    transition: all 0.2s ease !important;
    margin-bottom: 12px !important;
}

.example-card:hover {
    transform: translateY(-2px) !important;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08) !important;
    border-color: #4a6cf7 !important;
}

.example-card h3 {
    margin: 0 0 8px 0 !important;
    font-size: 15px !important;
    font-weight: 600 !important;
    color: #111827 !important;
}

.example-card p {
    margin: 0 !important;
    font-size: 13px !important;
    color: #6b7280 !important;
}

/* Header */
.header {
    text-align: center !important;
    margin-bottom: 24px !important;
}

.header h1 {
    font-size: 28px !important;
    font-weight: 700 !important;
    color: #111827 !important;
    margin-bottom: 8px !important;
}

.header p {
    font-size: 15px !important;
    color: #6b7280 !important;
    margin: 0 !important;
}
"""

# Example questions
example_questions = [
    {
        "title": "Top Customers",
        "description": "Show me the top 5 customers by total amount",
        "query": "Who are the top 5 customers by total amount?"
    },
    {
        "title": "Monthly Invoices",
        "description": "What are the invoices in July month?",
        "query": "What are the invoices in July month?"
    },
    {
        "title": "Organization Total",
        "description": "Total invoice amount for UNIWARE SYSTEMS PVT LTD",
        "query": "Total invoice amount of UNIWARE SYSTEMS PVT LTD organization"
    },
    {
        "title": "Highest Invoice",
        "description": "Show me the highest total amount invoice customer",
        "query": "Show me the highest total amount invoice customer"
    },

    {
        "title": "Customer Count",
        "description": "How many customers do we have?",
        "query": "How many customers do we have?"
    }
]

# Create the Gradio interface
with gr.Blocks(
    theme=gr.themes.Soft(
        primary_hue="blue",
        secondary_hue="blue"
    ),
    css=custom_css,
    title="🤖  CHAT WITH DATABASE"
) as demo:

    # Header section
    with gr.Column(elem_classes="header"):
        gr.HTML("""
        <div style="text-align: center;">
            <h1>🤖  CHAT WITH DATABASE</h1>
            <p>Transform natural language into powerful SQL queries</p>
        </div>
        """)

    with gr.Row():
        # Main chat column
        with gr.Column(scale=2):
            chatbot_ui = gr.Chatbot(
                label="Chat with your database",
                bubble_full_width=False,
                show_copy_button=True,
                render_markdown=True,
                avatar_images=(
                    "https://i.imgur.com/8B7Qh0P.png",  # User avatar
                    "https://i.imgur.com/4QZQZ9Q.png"   # Bot avatar
                )
            )
            
            with gr.Row():
                user_input = gr.Textbox(
                    placeholder="Ask your database anything...",
                    label="Your Query",
                    lines=2,
                    max_lines=5,
                    container=False
                )
                
            with gr.Row():
                submit_btn = gr.Button("Send", variant="primary")
                clear_btn = gr.Button("Clear", variant="secondary")

        # Examples column
        with gr.Column(scale=1):
            gr.HTML("<h3 style='margin-bottom: 16px;'>💡 Example Queries</h3>")
            
            for example in example_questions:
                with gr.Column(elem_classes="example-card"):
                    gr.HTML(f"""
                    <h3>{example['title']}</h3>
                    <p>{example['description']}</p>
                    """).click(
                        fn=lambda q=example['query']: q,
                        outputs=user_input
                    )

    # Event handlers
    def handle_query(user_input, history):
        new_history, _ = chatbot(user_input, history)
        return new_history, ""

    submit_btn.click(
        fn=handle_query,
        inputs=[user_input, chatbot_ui],
        outputs=[chatbot_ui, user_input]
    )

    user_input.submit(
        fn=handle_query,
        inputs=[user_input, chatbot_ui],
        outputs=[chatbot_ui, user_input]
    )

    clear_btn.click(
        fn=clear_chat,
        outputs=[chatbot_ui, user_input]
    )

    # Load initial welcome message
    demo.load(
        fn=lambda: ([[
            None,
            """🎉 **Welcome to your SQL AI Assistant!**

I can help you query your database using natural language. Here are some things I can do:

- **Answer questions** about your data
- **Generate SQL queries** from plain English
- **Explain results** in an easy-to-understand format

Try clicking on one of the example queries to get started, or type your own question!"""
        ]], ""),
        outputs=[chatbot_ui, user_input]
    )

if __name__ == "__main__":
    demo.launch()