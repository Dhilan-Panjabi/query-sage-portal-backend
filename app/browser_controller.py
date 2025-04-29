import os
import asyncio
import base64
from typing import Dict, Optional, List
from dotenv import load_dotenv
from browserbase import Browserbase
from browser_use import Agent, BrowserConfig, BrowserContextConfig
from langchain_openai import ChatOpenAI
import json
import time
import requests
from langchain_core.messages import HumanMessage

# Load environment variables
load_dotenv()

class BrowserController:
    """
    Controller class for managing browser sessions using Browserbase and browser-use
    """
    
    def __init__(self, user_id: str):
        """
        Initialize a browser controller for a specific user
        
        Args:
            user_id: Unique identifier for the user session
        """
        self.user_id = user_id
        self.session_id = None
        self.bb = Browserbase(api_key=os.getenv("BROWSERBASE_API_KEY"))
        self.project_id = os.getenv("BROWSERBASE_PROJECT_ID")
        self.session = None
        self.agent = None
        self.current_url = None
        self.streaming = False
        self.current_task = None
        self.history = []
        self.dimensions = (1024, 768)
        self.debug_links = None
        self.steps = []
        
    async def start_session(self) -> Dict:
        """
        Start a new Browserbase session
        
        Returns:
            Dict: Session information
        """
        try:
            # Create a new session on Browserbase
            width, height = self.dimensions
            session_params = {
                "project_id": self.project_id,
                "browser_settings": {
                    "viewport": {"width": width, "height": height},
                    "blockAds": True,
                },
                "region": "us-east-1",  # Use a region close to you
                "keep_alive": False,      # Keep session alive after disconnections
            }
            
            try:
                self.session = self.bb.sessions.create(**session_params)
                self.session_id = self.session.id
                print(f"Created new Browserbase session: {self.session_id}")
                print(f"Session attributes: {dir(self.session)}")  # Debug: print available attributes
                
                # Get debug links for live view
                self.debug_links = self.bb.sessions.debug(self.session_id)
                print(f"Live view URL: {self.debug_links.debuggerFullscreenUrl}")
                
                # Set the initial URL to Google
                self.current_url = "https://www.google.com"
                
                # Store connection URL for later use
                self.connection_url = self.session.connect_url
                
                # Add steps for initialization
                self.steps.append("Browser session initialized")
                self.steps.append(f"Starting with {self.current_url}")
                
                return {
                    "session_id": self.session_id,
                    "status": "connected",
                    "current_url": self.current_url,
                    "live_view_url": self.debug_links.debuggerFullscreenUrl
                }
                
            except Exception as e:
                error_message = str(e)
                if "You've exceeded your max concurrent sessions limit" in error_message:
                    # Try to get existing sessions
                    sessions = self.bb.sessions.list()
                    if sessions and len(sessions) > 0:
                        # Reuse the first active session
                        reuse_session_id = sessions[0].id # Get ID first
                        print(f"Reusing existing session due to limit: {reuse_session_id}")
                        # Explicitly get the full session object by ID using retrieve()
                        self.session = self.bb.sessions.retrieve(reuse_session_id)
                        
                        # Now access attributes from the full session object
                        self.session_id = self.session.id 
                        self.debug_links = self.bb.sessions.debug(self.session_id)
                        self.current_url = "https://www.google.com"
                        # Store connection URL for the reused session
                        self.connection_url = self.session.connect_url
                        print(f"Using connection URL: {self.connection_url}")
                        
                        # Add steps for initialization for reused session
                        self.steps.append("Browser session reused")
                        self.steps.append(f"Starting with {self.current_url}")
                        return {
                            "session_id": self.session_id,
                            "status": "connected",
                            "current_url": self.current_url,
                            "live_view_url": self.debug_links.debuggerFullscreenUrl
                        }
                    else:
                        raise e
                else:
                    raise e
            
        except Exception as e:
            error_message = str(e)
            print(f"Error starting browser session: {error_message}")
            return {
                "status": "error",
                "error": error_message
            }
    
    async def process_query(self, query: str) -> Dict:
        """
        Process a user query using the browser-use agent
        
        Args:
            query: User query to process
            
        Returns:
            Dict: Response from the agent
        """
        try:
            # Add step for processing query
            self.steps.append(f"Processing query: {query}")
            
            # Create the LLM instance
            llm = ChatOpenAI(model="gpt-4.1")
            planner_llm = ChatOpenAI(model="gpt-4.1-mini-2025-04-14")
            
            print(f"Using Browserbase connection URL: {self.connection_url}")
            
            try:
                # According to Browserbase docs, use connect_url directly as cdp_url
                browser_config = BrowserConfig(cdp_url=self.connection_url)
                
                # Create the browser instance using the simple configuration from docs
                from browser_use.browser.browser import Browser
                browser = Browser(config=browser_config)
                
                # Use a minimal context config as recommended
                context_config = BrowserContextConfig(
                    wait_for_network_idle_page_load_time=10.0,
                    highlight_elements=True
                )
                
                # Create agent with the browser instance
                agent = Agent(
                    task=query,
                    llm=llm,
                    use_vision=True,
                    planner_llm=planner_llm, 
                    planner_interval=5,
                    use_vision_for_planner=False,
                    browser=browser
                )
                
                # Add step for agent initialization
                self.steps.append("Browser agent initialized")
                
                # Run the agent
                self.steps.append("Executing query...")
                result = await agent.run()
                
                # Process result to ensure it's a string
                final_text_result = ""  # Initialize with empty string
                
                # Log the raw result for debugging
                print(f"Agent result type: {type(result).__name__}")
                print(f"Agent result: {result}")
                
                # Instead of trying to parse the complex AgentHistoryList, send it to an LLM to summarize
                try:
                    # Create a prompt for the LLM to summarize the browser agent results
                    summary_prompt = f"""
You are a helpful assistant summarizing the results of a web browsing session.

USER QUERY: {query}

BROWSER STEPS:
{chr(10).join(self.steps)}

BROWSER RESULT:
{str(result)}

Please provide a clear, concise summary of what the browser found in response to the user's query.
Format your response in a user-friendly way with proper paragraphs and, if appropriate, bullet points.
Focus on the key information discovered during the browsing session. Include all important details. 
DO NOT mention that you're summarizing anything - just provide the helpful information as if you found it yourself.
"""

                    # For LLM calls, don't use await directly which causes the AIMessage issue
                    summary_llm = ChatOpenAI(model="gpt-4.1-mini-2025-04-14", temperature=0)
                    
                    # Instead of using await directly, which causes the AIMessage issue
                    # Create a simple message and invoke synchronously
                    message = HumanMessage(content=summary_prompt)
                    try:
                        # Try synchronous completion first
                        llm_response = summary_llm.invoke([message])
                        final_text_result = llm_response.content if hasattr(llm_response, 'content') else str(llm_response)
                    except Exception as sync_error:
                        # If that fails, try a simpler approach
                        print(f"Error with sync LLM call: {sync_error}")
                        # Extract the final results directly if possible
                        if hasattr(result, 'all_results') and result.all_results:
                            for action in reversed(result.all_results):
                                if getattr(action, 'is_done', False) and getattr(action, 'success', True):
                                    final_text_result = getattr(action, 'extracted_content', '')
                                    break
                            else:
                                final_text_result = getattr(result.all_results[-1], 'extracted_content', '')
                        else:
                            final_text_result = "I found information related to your query but had trouble formatting the results."
                    
                    print(f"LLM summarized response: {final_text_result}")
                except Exception as summarization_error:
                    print(f"Error getting LLM summary: {summarization_error}")
                    # Fallback to direct extraction if the LLM summarization fails
                    if hasattr(result, 'all_results'):
                        # First, try to find a "done" action with success=True
                        done_actions = [action for action in result.all_results if getattr(action, 'is_done', False) and getattr(action, 'success', False)]
                        if done_actions:
                            # Use the last successful done action
                            final_text_result = done_actions[-1].extracted_content
                        else:
                            # If no successful done action, get the most recent action
                            final_text_result = result.all_results[-1].extracted_content if result.all_results else ""
                    else:
                        # If we can't extract directly, use a simplified response
                        final_text_result = "Based on my web search, I found information related to your query about " + query
                
                # Add step for query completion
                self.steps.append("Query execution completed")
                
                # Update current URL if needed
                if hasattr(browser, "current_url") and browser.current_url:
                    self.current_url = browser.current_url
                    # Add to history
                    if self.current_url:
                        self.history.append(self.current_url)
                        if len(self.history) > 10:
                            self.history = self.history[-10:]
                        # Add step for URL update
                        self.steps.append(f"Navigated to {self.current_url}")
                
                # Clean up browser
                await browser.close()
                
                # Final result sanitization to prevent object representation markers
                if not isinstance(final_text_result, str) or final_text_result.startswith('AgentHistoryList') or not final_text_result:
                    # Last resort fallback if everything else fails
                    final_text_result = f"I searched for information about {query}, but encountered an issue formatting the results."
                
                # Log the final result
                print(f"Final text result: {final_text_result}")
                
                # Return the summarized result
                return {
                    "status": "success",
                    "aiResponse": final_text_result,
                    "current_url": self.current_url,
                    "steps": self.steps
                }
            except Exception as browser_error:
                # If we get a browser error, provide a meaningful response
                error_message = str(browser_error)
                print(f"Browser error: {error_message}")
                self.steps.append(f"Browser error: {error_message}")
                
                # Generate a fallback response using the LLM
                try:
                    # Use a synchronous approach to avoid AIMessage await issue
                    fallback_message = "I encountered an issue while trying to browse the web: " + error_message
                    fallback_message += ". I'm unable to access web content for this query right now."
                    
                    return {
                        "status": "partial_success",
                        "aiResponse": fallback_message,
                        "current_url": self.current_url,
                        "steps": self.steps
                    }
                except Exception as llm_error:
                    print(f"Error generating fallback response: {llm_error}")
                    return {
                        "status": "error",
                        "error": f"Browser error: {error_message}. Additionally failed to generate fallback response.",
                        "aiResponse": f"I encountered an issue while trying to browse the web: {error_message}.",
                        "steps": self.steps
                    }
                
        except Exception as e:
            error_message = str(e)
            print(f"Error processing query: {error_message}")
            self.steps.append(f"Error: {error_message}")
            return {
                "status": "error",
                "error": error_message,
                "aiResponse": f"I encountered an error while processing your request: {error_message}",
                "steps": self.steps
            }
    
    def _update_current_url(self, url: str):
        """Update current URL and add step"""
        self.current_url = url
        self.steps.append(f"Now at: {url}")
    
    async def stream_browser(self, websocket):
        """
        Stream browser screenshots to a websocket
        
        Args:
            websocket: WebSocket connection
        """
        self.streaming = True
        last_steps_count = 0  # Track how many steps we've sent
        
        try:
            # Send initial connection message with Browserbase live view URL
            await websocket.send_json({
                "type": "status",
                "data": {
                    "status": "connected",
                    "session_id": self.session_id,
                }
            })
            
            # Send current URL
            await websocket.send_json({
                "type": "url",
                "data": self.current_url or "about:blank"
            })
            
            # Send steps
            await websocket.send_json({
                "type": "steps",
                "data": self.steps
            })
            last_steps_count = len(self.steps)
            
            # Keep streaming until told to stop
            interval = 0.5  # Update twice per second for more responsive updates
            while self.streaming:
                try:
                    # Send live view URL if available
                    if self.debug_links and self.debug_links.debuggerFullscreenUrl:
                        await websocket.send_json({
                            "type": "live_view_url",
                            "data": self.debug_links.debuggerFullscreenUrl
                        })
                    
                    # Send current URL
                    await websocket.send_json({
                        "type": "url",
                        "data": self.current_url or "about:blank"
                    })
                    
                    # Only send steps if they've changed
                    if len(self.steps) > last_steps_count:
                        await websocket.send_json({
                            "type": "steps",
                            "data": self.steps
                        })
                        last_steps_count = len(self.steps)
                        print(f"Sent updated steps: {len(self.steps)} steps")
                    
                    # Sleep for a short interval to avoid hammering the API
                    await asyncio.sleep(interval)
                    
                except Exception as stream_error:
                    print(f"Error during streaming: {str(stream_error)}")
                    await asyncio.sleep(interval)
            
        except Exception as e:
            print(f"WebSocket streaming error: {str(e)}")
        finally:
            # Just stop streaming, don't close the browser session
            self.streaming = False
    
    async def stop_session(self):
        """
        Stop the browser session
        """
        try:
            if self.session_id:
                # Properly close the Browserbase session
                self.bb.sessions.delete(self.session_id)
                print(f"Closed Browserbase session: {self.session_id}")
                self.session_id = None
                self.session = None
                self.agent = None
                self.streaming = False
        except Exception as e:
            print(f"Error stopping session: {str(e)}")
            # Still consider the session closed from our side
            self.session_id = None
            self.session = None
            self.agent = None
            self.streaming = False 