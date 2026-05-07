import os
import json
import asyncio
from logger_store import add_log

# Create in-memory storage for active conversations
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
    Process the user's input through the fallback LLM providers.
    Uses the Swiggy Universal Assistant pattern.
    """
    try:
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
            return json.dumps({"text": "No API keys configured. Please check your environment variables.", "options": []})
        
        if session_id not in CONVERSATIONS:
            CONVERSATIONS[session_id] = [
                {
                    "role": "system", 
                    "content": (
                        "You are the Swiggy Universal Assistant. Follow this strictly sequential flow:\n\n"
                        "Step 1: SERVICE SELECTION\n"
                        "Greet the user and ask them to choose a service using these exact customer-centric buttons:\n"
                        "- 'Order Delicious Food' (action: Food Delivery)\n"
                        "- 'Quick Groceries (Instamart)' (action: Instamart)\n"
                        "- 'Book a Table (Dineout)' (action: Dineout)\n\n"
                        "Step 2: ADDRESS SELECTION (Skip for Dineout)\n"
                        "If the user chose Food or Instamart, you MUST show these 3 addresses as buttons and ask them to pick one before proceeding:\n"
                        "1. Flat 203, Aryan Apartments, Chembur\n"
                        "2. Flat 205, Aryan Apartments, Chembur\n"
                        "3. Flat 1101, Tulsi Vihar, Chembur\n\n"
                        "Step 3: USER-LED CONVERSATION\n"
                        "Once the service and address (if applicable) are set, acknowledge the selection and wait for the user to lead the conversation. Ask them: 'Great! What would you like to order today?' or 'What kind of place are you looking to book?'\n\n"
                        "Step 4: FINALIZATION\n"
                        "When the order is confirmed, include '[SESSION_FINISHED]' to reset memory.\n\n"
                        "CRITICAL FORMATTING: Always respond with JSON: {\"text\": \"message\", \"options\": [{\"label\": \"Btn Text\", \"action\": \"prompt\"}]}. Do NOT suggest specific food items (like 'Burgers') until the user mentions them."
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
        return json.dumps({"text": f"Agent Error: {last_error}", "options": []})
        
    except Exception as e:
        add_log("error", f"Agent execution failed: {str(e)}")
        return json.dumps({"text": f"Agent Error: {str(e)}", "options": []})
