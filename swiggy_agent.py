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
                        "Your job is to act as an intelligent chat agent that gathers necessary parameters from the user before finalizing an order.\n"
                        "- For Food Delivery: Prompt for specific items, quantity, and delivery location if missing.\n"
                        "- For Groceries (Instamart): Prompt for specific items, quantity, and delivery location if missing.\n"
                        "- For Table Booking (Dineout): Prompt for the location/city, preferred time, type of setting (indoor/outdoor), filtering criteria, and number of people if missing.\n"
                        "Since you are in fallback mode, simulate the API interaction once all parameters are gathered.\n"
                        "CRITICAL: You must ALWAYS respond with a strictly formatted JSON object. "
                        "Schema: {\"text\": \"Your natural language response here\", \"options\": [{\"label\": \"Button Text\", \"action\": \"User prompt representing the button action\"}]}. "
                        "Provide logical next steps as 'options' (e.g. quick reply buttons for times, locations, items, or confirming the order). Do NOT wrap the output in markdown."
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