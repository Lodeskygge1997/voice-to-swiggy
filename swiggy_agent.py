import os
import json
import asyncio

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
    if not api_key:
        return json.dumps({"text": "OpenAI API key is missing. Cannot process request.", "options": []})
        
    try:
        # Attempt to use the robust agents SDK
        from agents import Agent, Runner
        
        # Mocking the MCP server integration as per previous architecture
        swiggy_food = "mcp://swiggy-food"
        swiggy_instamart = "mcp://swiggy-instamart"
        swiggy_dineout = "mcp://swiggy-dineout"

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
        # Fallback to direct OpenAI if the deepmind SDK isn't installed
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=api_key)
        
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
        
        try:
            response = await client.chat.completions.create(
                model="gpt-4o",
                messages=CONVERSATIONS[session_id],
                temperature=0.3
            )
            
            output = response.choices[0].message.content
            CONVERSATIONS[session_id].append({"role": "assistant", "content": output})
            return output
        except Exception as e:
            return json.dumps({"text": f"Agent Error: {str(e)}", "options": []})