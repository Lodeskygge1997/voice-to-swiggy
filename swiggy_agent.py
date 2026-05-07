import os
import asyncio
import json
from logger_store import add_log

# In-memory store for interactive chat history
CONVERSATIONS = {}

async def get_swiggy_access_token():
    token = os.environ.get("SWIGGY_STAGING_TOKEN", "mock-token-for-local-prototype")
    add_log("info", "Obtained Swiggy OAuth access token.")
    return token

async def process_order_via_agent(transcription, session_id="default"):
    """
    Simulates Swiggy MCP agent interaction using OpenAI directly.
    Maintains interactive chat functionality using session_id.
    """
    add_log("info", f"Processing input for session {session_id}: '{transcription}'")
    
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        add_log("warning", "OPENAI_API_KEY is not set.")
        return '{"text": "System requires OPENAI_API_KEY to process requests.", "options": []}'
        
    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=api_key)
        
        # Initialize conversation if new
        if session_id not in CONVERSATIONS:
            CONVERSATIONS[session_id] = [
                {
                    "role": "system", 
                    "content": (
                        "You are a helpful Swiggy Food Ordering Assistant. "
                        "You must ALWAYS respond with a strictly formatted JSON object. "
                        "Schema: {\"text\": \"Your natural language response here\", \"options\": [{\"label\": \"Button Text\", \"action\": \"User prompt representing the button action\"}]}. "
                        "Provide 'options' as an array of logical next steps for the user based on Swiggy's mock menu: Paneer Tikka, Garlic Naan, Butter Chicken, Dal Makhani, Biryani. "
                        "Do NOT wrap the output in markdown. Start and end with curly braces."
                    )
                }
            ]
            
        CONVERSATIONS[session_id].append({"role": "user", "content": transcription})
        
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=CONVERSATIONS[session_id],
            temperature=0.7,
            response_format={"type": "json_object"}
        )
        
        reply_content = response.choices[0].message.content
        CONVERSATIONS[session_id].append({"role": "assistant", "content": reply_content})
        
        add_log("success", f"Agent execution completed for {session_id}.")
        return reply_content
        
    except Exception as e:
        add_log("error", f"Agent execution failed: {str(e)}")
        return json.dumps({
            "text": f"Agent Error: {str(e)}",
            "options": []
        })

def run_agent_sync(transcription, session_id="default"):
    """Synchronous wrapper for Flask endpoints."""
    return asyncio.run(process_order_via_agent(transcription, session_id))