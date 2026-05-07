import os
import asyncio
import json
from logger_store import add_log

# In-memory store for interactive chat history (used for OpenAI fallback)
CONVERSATIONS = {}

async def get_swiggy_access_token():
    token = os.environ.get("SWIGGY_STAGING_TOKEN", "mock-token-for-local-prototype")
    add_log("info", "Obtained Swiggy OAuth access token.")
    return token

async def process_order_via_agent(transcription, session_id="default"):
    """
    Simulates Deepmind agent routing to Swiggy MCP servers (Food, Instamart, Dineout).
    Falls back to direct OpenAI if the 'agents' SDK is unavailable.
    """
    add_log("info", f"Processing input for session {session_id}: '{transcription}'")
    
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        add_log("warning", "OPENAI_API_KEY is not set.")
        return '{"text": "System requires OPENAI_API_KEY to process requests.", "options": []}'
        
    try:
        # Try importing the official Deepmind Agents SDK
        from agents import Agent, Runner
        from agents.mcp import MCPServerStreamableHttp
        
        token = await get_swiggy_access_token()
        
        # Configure the 3 Swiggy MCP Server endpoints
        swiggy_food = MCPServerStreamableHttp(params={"url": "https://mcp.swiggy.com/food", "headers": {"Authorization": f"Bearer {token}"}})
        swiggy_instamart = MCPServerStreamableHttp(params={"url": "https://mcp.swiggy.com/instamart", "headers": {"Authorization": f"Bearer {token}"}})
        swiggy_dineout = MCPServerStreamableHttp(params={"url": "https://mcp.swiggy.com/dineout", "headers": {"Authorization": f"Bearer {token}"}})
        
        agent = Agent(
            name="SwiggyUniversalAgent",
            instructions=(
                "You are the Swiggy Universal Assistant. Based on the user's prompt, identify and route the request to the correct MCP server: "
                "1. Food Delivery -> use food MCP. "
                "2. Groceries -> use instamart MCP. "
                "3. Table Booking -> use dineout MCP.\n"
                "CRITICAL: You must ALWAYS respond with a strictly formatted JSON object. "
                "Schema: {\"text\": \"Your natural language response here\", \"options\": [{\"label\": \"Button Text\", \"action\": \"User prompt representing the button action\"}]}. "
                "Provide 'options' as an array of logical next steps (like increasing/reducing items, checkout). Do NOT wrap in markdown."
            ),
            mcp_servers=[swiggy_food, swiggy_instamart, swiggy_dineout],
        )
        
        result = await Runner.run(agent, transcription)
        return result.final_output
        
    except ImportError:
        # Fallback to direct OpenAI if the deepmind SDK isn't installed
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=api_key)
        
        if session_id not in CONVERSATIONS:
            CONVERSATIONS[session_id] = [
                {
                    "role": "system", 
                    "content": (
                        "You are the Swiggy Universal Assistant powered by Deepmind models. "
                        "Identify which Swiggy API to hit based on the prompt: Food Delivery, Groceries (Instamart), or Table Booking (Dineout). "
                        "Since you are in fallback mode, simulate the API interaction. "
                        "CRITICAL: You must ALWAYS respond with a strictly formatted JSON object. "
                        "Schema: {\"text\": \"Your natural language response here\", \"options\": [{\"label\": \"Button Text\", \"action\": \"User prompt representing the button action\"}]}. "
                        "Provide menus and subsequent steps (increasing/reducing items, confirming order) as 'options'. Do NOT wrap the output in markdown."
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
        
        add_log("success", f"Fallback agent execution completed for {session_id}.")
        return reply_content
        
    except Exception as e:
        add_log("error", f"Agent execution failed: {str(e)}")
        return json.dumps({"text": f"Agent Error: {str(e)}", "options": []})

def run_agent_sync(transcription, session_id="default"):
    """Synchronous wrapper for Flask endpoints."""
    return asyncio.run(process_order_via_agent(transcription, session_id))