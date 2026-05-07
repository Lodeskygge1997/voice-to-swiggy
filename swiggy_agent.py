import os
import json
import asyncio
from logger_store import add_log

# Create in-memory storage for active conversations
# In a true production app, this would use Redis or Supabase
CONVERSATIONS = {}

def run_agent_sync(transcription: str, session_id: str = "default") -> str:
    """Synchronous wrapper for the async agent runner."""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
    return loop.run_until_complete(process_order_via_agent(transcription, session_id))

async def process_order_via_agent(transcription: str, session_id: str) -> str:
    """
    Process the user's input through the DeepMind/OpenAI agents SDK.
    Uses the Swiggy Universal Assistant pattern.
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key and not os.environ.get("GEMINI_API_KEY") and not os.environ.get("GROQ_API_KEY") and not os.environ.get("OPENROUTER_API_KEY") and not os.environ.get("HUGGINGFACE_API_KEY"):
        return json.dumps({"text": "API key is missing. Cannot process request.", "options": []})
        
    try:
        # Attempt to use the robust agents SDK
        from agents import Agent, Runner
        from mcp.client.streamable_http import MCPServerStreamableHttp
        
        token = os.environ.get("SWIGGY_TOKEN", "mock_token")
        
        # Configure the 3 Swiggy MCP Server endpoints
        swiggy_food = MCPServerStreamableHttp(params={"url": "https://mcp.swiggy.com/food", "headers": {"Authorization": f"Bearer {token}"}})
        swiggy_instamart = MCPServerStreamableHttp(params={"url": "https://mcp.swiggy.com/instamart", "headers": {"Authorization": f"Bearer {token}"}})
        swiggy_dineout = MCPServerStreamableHttp(params={"url": "https://mcp.swiggy.com/dineout", "headers": {"Authorization": f"Bearer {token}"}})
        
        agent = Agent(
            name="SwiggyUniversalAgent",
            instructions=(
                "You are the Swiggy Universal Assistant. Your job is to gather all necessary parameters "
                "from the user before making an API call to the MCP servers.\n"
                "- For Food Delivery (food MCP): Ask for the delivery location, specific items, and quantity if not provided.\n"
                "- For Groceries (instamart MCP): Ask for the specific items, quantity, and delivery location if not provided.\n"
                "- For Table Booking (dineout MCP): Ask for the location/city, preferred time, type of setting (e.g., indoor/outdoor, casual/fine-dining), and number of people if not provided.\n"
                "Once you have gathered the required parameters, route the request to the correct MCP server.\n"
                "CRITICAL: You must ALWAYS respond with a strictly formatted JSON object. "
                "Schema: {\"text\": \"Your natural language response here\", \"options\": [{\"label\": \"Button Text\", \"action\": \"User prompt representing the button action\"}]}. "
                "Provide 'options' as an array of logical next steps (like quick reply buttons for times, locations, or confirming). Do NOT wrap in markdown."
            ),
            mcp_servers=[swiggy_food, swiggy_instamart, swiggy_dineout],
        )
        
        result = await Runner.run(agent, transcription)
        return result.final_output
        
    except ImportError:
        # Fallback to free LLMs (Gemini or Groq) using the OpenAI SDK compatibility layer
        from openai import AsyncOpenAI
        
        # Priority list of free providers (Groq > OpenRouter > HuggingFace > Gemini > OpenAI)
        providers = []
        if os.environ.get("GROQ_API_KEY"):
            providers.append({
                "client": AsyncOpenAI(api_key=os.environ.get("GROQ_API_KEY"), base_url="https://api.groq.com/openai/v1"),
                "model": "llama-3.3-70b-versatile",
                "name": "Groq"
            })
        if os.environ.get("OPENROUTER_API_KEY"):
            providers.append({
                "client": AsyncOpenAI(api_key=os.environ.get("OPENROUTER_API_KEY"), base_url="https://openrouter.ai/api/v1"),
                "model": "meta-llama/llama-3-8b-instruct:free",
                "name": "OpenRouter"
            })
        if os.environ.get("HUGGINGFACE_API_KEY"):
            providers.append({
                "client": AsyncOpenAI(api_key=os.environ.get("HUGGINGFACE_API_KEY"), base_url="https://api-inference.huggingface.co/v1/"),
                "model": "meta-llama/Meta-Llama-3-8B-Instruct",
                "name": "HuggingFace"
            })
        if os.environ.get("GEMINI_API_KEY"):
            providers.append({
                "client": AsyncOpenAI(api_key=os.environ.get("GEMINI_API_KEY"), base_url="https://generativelanguage.googleapis.com/v1beta/openai/"),
                "model": "gemini-2.0-flash",
                "name": "Gemini"
            })
        if os.environ.get("OPENAI_API_KEY"):
            providers.append({
                "client": AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY")),
                "model": "gpt-4o",
                "name": "OpenAI"
            })
            
        if not providers:
            return json.dumps({"text": "No API keys configured. Cannot process request.", "options": []})
        
        if session_id not in CONVERSATIONS:
            CONVERSATIONS[session_id] = [
                {
                    "role": "system", 
                    "content": (
                        "You are the Swiggy Universal Assistant powered by Deepmind models. "
                        "Follow this strict multi-step flow to assist the user:\n\n"
                        "Step 1: GREETING & DOMAIN SELECTION\n"
                        "Welcome the user and ask them to choose a service: 'Food Delivery', 'Instamart (Groceries)', or 'Dineout (Table Booking)'. Do not ask for anything else yet.\n\n"
                        "Step 2: ADDRESS SELECTION (If Food or Instamart)\n"
                        "Once they select Food or Instamart, you MUST present these exact 3 saved addresses and ask them to choose one:\n"
                        "1. Flat 203, Aryan Apartments, Chembur\n"
                        "2. Flat 205, Aryan Apartments, Chembur\n"
                        "3. Flat 1101, Tulsi Vihar, Chembur\n"
                        "Do not ask for order items until the address is selected.\n\n"
                        "Step 3: GATHER REQUIREMENTS\n"
                        "- If Food/Instamart (and address is selected): Ask them what items they would like to order.\n"
                        "- If Dineout: Ask for the location/city, preferred time, type of setting (indoor/outdoor), and number of people.\n\n"
                        "Step 4: FINALIZATION\n"
                        "Once all parameters (Service, Address/Location, Items/Details) are confirmed, finalize the order.\n"
                        "CRITICAL: When the user's order or booking is fully confirmed, you MUST include the exact hidden string '[SESSION_FINISHED]' somewhere in your text response to clear the session memory.\n\n"
                        "CRITICAL FORMATTING RULES: You must ALWAYS respond with a strictly formatted JSON object. "
                        "Schema: {\"text\": \"Your natural language response here\", \"options\": [{\"label\": \"Button Text\", \"action\": \"User prompt representing the button action\"}]}. "
                        "Provide logical next steps as 'options' (e.g., buttons for the 3 addresses, or buttons for Food/Instamart/Dineout). Do NOT wrap the output in markdown."
                    )
                }
            ]
            
        CONVERSATIONS[session_id].append({"role": "user", "content": transcription})
        
        last_error = None
        for provider in providers:
            try:
                response = await provider["client"].chat.completions.create(
                    model=provider["model"],
                    messages=CONVERSATIONS[session_id],
                    temperature=0.7
                )
                
                reply_content = response.choices[0].message.content
                
                # Check for session reset intent
                if "[SESSION_FINISHED]" in reply_content:
                    reply_content = reply_content.replace("[SESSION_FINISHED]", "")
                    if session_id in CONVERSATIONS:
                        del CONVERSATIONS[session_id]
                    add_log("info", f"Order confirmed. Session {session_id} memory wiped.")
                else:
                    CONVERSATIONS[session_id].append({"role": "assistant", "content": reply_content})
                    
                add_log("success", f"Fallback agent execution completed via {provider['name']} for {session_id}.")
                return reply_content
                
            except Exception as e:
                last_error = str(e)
                add_log("warning", f"{provider['name']} LLM failed: {last_error}. Trying next provider...")
                continue
                
        # If all providers fail
        add_log("error", f"All LLM providers failed. Last error: {last_error}")
        if last_error and "429" in last_error:
            return json.dumps({
                "text": "My servers are currently experiencing high traffic. Please try your order again in a few moments.",
                "options": []
            })
        return json.dumps({"text": f"Agent Error: {last_error}", "options": []})
        
    except Exception as e:
        add_log("error", f"Agent execution failed: {str(e)}")
        return json.dumps({"text": f"Agent Error: {str(e)}", "options": []})