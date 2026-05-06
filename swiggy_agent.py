# swiggy_agent.py
import os
import asyncio
from logger_store import add_log

async def get_swiggy_access_token():
    """
    Mock OAuth flow for local prototyping.
    In production, this would handle the OAuth 2.1 PKCE redirect flow 
    with /.well-known/oauth-authorization-server as per Swiggy docs.
    """
    token = os.environ.get("SWIGGY_STAGING_TOKEN", "mock-token-for-local-prototype")
    add_log("info", "Obtained Swiggy OAuth access token.")
    return token

async def process_order_via_agent(transcription):
    """
    Connects to the Swiggy MCP server and passes the transcription to the Agent.
    """
    add_log("info", f"Initializing Swiggy Agent for input: '{transcription}'")
    
    # Check for LLM API Key
    if not os.environ.get("OPENAI_API_KEY"):
        add_log("warning", "OPENAI_API_KEY is not set. Agent cannot think.")
        return f"System requires OPENAI_API_KEY to process: '{transcription}'"
    
    try:
        from agents import Agent, Runner
        from agents.mcp import MCPServerStreamableHttp
        
        token = await get_swiggy_access_token()
        
        # Connect to real Swiggy MCP Server over SSE
        swiggy_food = MCPServerStreamableHttp(
            params={
                "url": "https://mcp.swiggy.com/food",
                "headers": {"Authorization": f"Bearer {token}"},
            },
        )
        
        agent = Agent(
            name="FoodOrderingAgent",
            instructions="Help users order food on Swiggy. Always call get_addresses first, then search_restaurants.",
            mcp_servers=[swiggy_food],
        )
        
        add_log("info", "Connecting to https://mcp.swiggy.com/food...")
        await swiggy_food.connect()
        
        add_log("info", "Running LLM Agent...")
        result = await Runner.run(agent, transcription)
        
        add_log("success", f"Agent execution completed.")
        return result.final_output
        
    except ImportError:
        add_log("warning", "The official 'agents' SDK is not installed on this environment. Using prototype fallback.")
        return f"Swiggy Agent Prototype Received: '{transcription}'. (Install Swiggy Agents SDK to complete the true HTTP connection)"
    except Exception as e:
        add_log("error", f"Agent execution failed: {str(e)}")
        # If it returns a 401, it means the mock token was rejected by Swiggy's staging server
        if "401" in str(e):
            return f"Swiggy Auth Error: Your staging token was rejected. Please complete the OAuth process."
        return f"Agent Error: {str(e)}"

def run_agent_sync(transcription):
    """Synchronous wrapper for Flask endpoints."""
    return asyncio.run(process_order_via_agent(transcription))