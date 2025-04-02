from mcp import ClientSession, StdioServerParameters, types
from mcp.client.stdio import stdio_client
import os
import asyncio
from dotenv import load_dotenv
import json
import anthropic
from datetime import datetime
import logging
import logging.handlers
import pathlib
from typing import List, Dict, Any, Optional, Union, Tuple
import sys

# Load environment variables from .env file
load_dotenv()

# Configure logging
def setup_logger(server_name: str) -> logging.Logger:
    """
    Sets up a logger for a specific MCP server with both file and console handlers.
    
    The file handler creates logs with timestamps in the filename to preserve history.
    
    Args:
        server_name: Name of the MCP server for identification in logs
        
    Returns:
        Configured logger instance
    """
    # Create logs directory if it doesn't exist
    log_dir = pathlib.Path("logs")
    log_dir.mkdir(exist_ok=True)
    
    # Create timestamp for this run
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = log_dir / f"{server_name}_{timestamp}.log"
    
    # Create logger
    logger = logging.getLogger(f"MCP_Client_{server_name}")
    logger.setLevel(logging.DEBUG)
    
    # Clear any existing handlers
    if logger.hasHandlers():
        logger.handlers.clear()
    
    # Create formatters
    detailed_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Create handlers
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(detailed_formatter)
    
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(detailed_formatter)
    
    # Add handlers to logger
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger

async def tool_calling_claude(
    session: ClientSession,
    tool_name: str,
    tool_input: Dict[str, Any],
    logger: logging.Logger,
    timeout: int = 300
) -> Dict[str, Any]:
    """
    Handles the logic for calling a tool requested by Claude and processing its response.
    
    Args:
        session: The MCP client session
        tool_name: The name of the tool to call
        tool_input: The input arguments for the tool
        logger: Logger instance for tracking the interaction
        timeout: Maximum time in seconds to wait for tool execution (default: 30)
        
    Returns:
        A dictionary containing the tool result or an error message
        
    Error Messages:
        The following error messages may be returned:
        - {"error": "Empty response from tool"} - When the tool returns no content
        - {"error": "Invalid JSON response: [error]", "raw_text": "[text]"} - When the tool returns non-JSON data
        - {"error": "Tool execution timed out"} - When the tool takes longer than the timeout period
        - {"error": "[exception message]"} - For any other exceptions that occur during tool execution
    """
    logger.info(f"Tool requested: {tool_name}")
    logger.debug(f"Tool input: {json.dumps(tool_input, indent=2)}")
    
    try:
        # Add timeout to prevent hanging
        tool_response = await asyncio.wait_for(
            session.call_tool(tool_name, arguments=tool_input),
            timeout=timeout
        )
        
        if not tool_response.content or len(tool_response.content) == 0:
            logger.error(f"Empty response from tool {tool_name}")
            return {"error": "Empty response from tool"}
            
        tool_result_text = tool_response.content[0].text
        try:
            tool_result = json.loads(tool_result_text)
            logger.info(f"Tool '{tool_name}' executed successfully")
            logger.debug(f"Tool result: {json.dumps(tool_result, indent=2)}")
            return tool_result
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing tool result as JSON: {e}")
            return {"error": f"Invalid JSON response: {e}", "raw_text": tool_result_text}
    except asyncio.TimeoutError:
        logger.error(f"Tool execution timed out after {timeout} seconds")
        return {"error": f"Tool execution timed out after {timeout} seconds"}
    except Exception as e:
        logger.error(f"Error executing tool {tool_name}: {e}")
        return {"error": str(e)}

async def claude_conversation(
    session: ClientSession,
    user_prompt: str,
    system_prompt: str,
    model: str = "claude-3-7-sonnet-20250219",
    max_tokens: int = 8192,
    temperature: float = 0,
    max_iterations: int = 10,
    max_conversation_length: int = 8,
    server_name: str = "default",
    logger: Optional[logging.Logger] = None
) -> str:
    """
    Manages a conversation with Claude that can involve tool calling.
    
    Args:
        session: The MCP client session
        user_prompt: The initial user query
        system_prompt: System prompt template (with {tools_description} placeholder)
        model: Claude model to use
        max_tokens: Maximum tokens for Claude response
        temperature: Temperature for Claude response
        max_iterations: Maximum number of conversation iterations to prevent infinite loops
        max_conversation_length: Maximum number of messages to keep in conversation history
        server_name: Name of the MCP server for logging
        logger: Optional logger instance (will create one if not provided)
        
    Returns:
        The final response from Claude
    """
    # Set up logging if not provided
    if logger is None:
        logger = setup_logger(server_name)
    
    logger.info(f"Starting conversation with Claude using {model}")
    logger.info(f"Initial user prompt: {user_prompt}")
    
    # Get information about available tools
    tools_response = await session.list_tools()
    available_tools = [{
        "name": tool.name,
        "description": tool.description,
        "input_schema": tool.inputSchema
    } for tool in tools_response.tools]
    
    logger.info(f"Available tools: {[tool['name'] for tool in available_tools]}")
    
    # Format tool info for the system prompt
    tools_info = ""
    for tool in available_tools:
        tools_info += f"Tool: {tool['name']}\n"
        tools_info += f"Description: {tool['description']}\n"
        tools_info += f"Arguments: {json.dumps(tool['input_schema'], indent=2)}\n\n"
    
    # Format the system prompt with tools information
    formatted_system_prompt = system_prompt.format(tools_description=tools_info)
    logger.debug(f"Formatted system prompt: {formatted_system_prompt}")
    
    # Keep track of conversation history
    conversation = [
        {"role": "user", "content": user_prompt}
    ]
    
    iteration_count = 0
    final_response = ""
    
    while iteration_count < max_iterations:
        iteration_count += 1
        logger.info(f"Conversation iteration {iteration_count}/{max_iterations}")
        logger.debug(f"Current conversation history: {json.dumps(conversation, indent=2)}")
        
        try:
            logger.info("Sending request to Claude...")
            response = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                tools=available_tools,
                temperature=temperature,
                system=formatted_system_prompt,
                messages=conversation
            )
            
            # Extract Claude's response
            if not response.content or len(response.content) == 0:
                logger.error("Received empty response from Claude")
                break
                
            assistant_response = response.content[0].text if response.content[0].type == "text" else ""
            logger.info("Received response from Claude")
            logger.debug(f"Claude's response: {assistant_response}")
            
            # If Claude requests a tool, process the tool use blocks
            if response.stop_reason == "tool_use":
                logger.info("Claude requested tool use")
                tool_blocks = [block for block in response.content if block.type == "tool_use"]
                
                if not tool_blocks:
                    logger.error("No tool use block found despite stop_reason indicating tool use")
                    break
                    
                for block in tool_blocks:
                    tool_name = block.name
                    tool_input = block.input
                    tool_call_id = block.id
                    
                    # Check if the requested tool exists
                    if not any(tool["name"] == tool_name for tool in available_tools):
                        logger.error(f"Claude requested unknown tool: {tool_name}")
                        tool_result = {"error": f"Unknown tool: {tool_name}"}
                        is_error = True
                    else:
                        # Execute the tool with updated parameter list
                        tool_result = await tool_calling_claude(
                            session=session,
                            tool_name=tool_name,
                            tool_input=tool_input,
                            logger=logger,
                            timeout=30  # Can be adjusted as needed
                        )
                        # Check if the tool result contains an error
                        is_error = "error" in tool_result
                    
                    # Log error information if present
                    if is_error:
                        logger.warning(f"Tool execution resulted in error: {json.dumps(tool_result)}")
                    
                    # Update conversation history
                    conversation.append({
                        "role": "assistant",
                        "content": [
                            {"type": "text", "text": assistant_response},
                            {"type": "tool_use", "id": tool_call_id, "name": tool_name, "input": tool_input}
                        ]
                    })
                    
                    # Add user message with tool result, including is_error flag when appropriate
                    user_message = {
                        "role": "user",
                        "content": [
                            {"type": "tool_result", "tool_use_id": block.id, "content": json.dumps(tool_result)}
                        ]
                    }
                    
                    # Add is_error flag to the message if there was an error
                    if is_error:
                        user_message["is_error"] = True
                        
                    conversation.append(user_message)
                
                # Manage conversation length if needed
                if len(conversation) > max_conversation_length * 2:  # *2 because each exchange has 2 messages
                    logger.info(f"Conversation getting long, trimming to last {max_conversation_length} exchanges")
                    # Keep the last N messages (pairs of user/assistant messages)
                    conversation = conversation[-max_conversation_length * 2:]
                
                # Continue the loop to let Claude process the tool results
                continue
            else:
                # If no tool use is requested, this is the final response
                logger.info("Claude provided final response")
                final_response = assistant_response
                break
        
        except Exception as e:
            logger.error(f"Error in conversation loop: {e}")
            final_response = f"Error occurred: {str(e)}"
            break
    
    if iteration_count >= max_iterations:
        logger.warning(f"Reached maximum iterations ({max_iterations}). Stopping.")
    
    return final_response

# Create server parameters for Gmail MCP server
gmail_server_params = StdioServerParameters(
    command="python",  
    args=["mcp_servers\\gmail.py"],
    env=os.environ.copy()
)

# Create server parameters for the Web Scraping MCP server
web_scraping_server_params = StdioServerParameters(
    command="python",
    args=["mcp_servers\\web_scraping.py"],
    env=os.environ.copy()
)

# Load API key from environment variables
api_key = os.getenv("ANTHROPIC_API_KEY")
if not api_key:
    print("Error: ANTHROPIC_API_KEY environment variable not set.")
    sys.exit(1)

# Initialize Claude client
client = anthropic.Anthropic(api_key=api_key)

# Default system prompt for tool use
llm_system_prompt_tool_use = """
You are an AI assistant that helps users with a broad range of requests by using special tools.

Available tools:
{tools_description}

When the user makes a request, you should:
1. Decide whether to use internal knowledge or one or more tools to fulfill the request.
2. If tools are needed, choose the most appropriate ones and use them step-by-step.
3. Interpret the tool results and present helpful, well-organized responses to the user, following any requested output formats.
4. If a tool fails or returns an error, explain the issue to the user and suggest alternatives if possible.

Guidelines:
- Use tools only when they improve accuracy, access real-time data, or enable capabilities you don't have internally.
- Explain your reasoning when it helps the user understand the process.
- Adapt to new tools as they become available. Never assume a tool exists unless it is listed.

Think step-by-step about which tools to use and in what order.
"""

async def run():
    """Main function to run the MCP client"""
    # Setup a logger for cookie validation
    logger = setup_logger("cookie_validation")
    logger.info("Starting Medium cookie validation check")
    
    # Validate Medium cookies first
    logger.info("Connecting to Web Scraping MCP server to validate Medium cookies")
    async with stdio_client(web_scraping_server_params) as (read, write):
        async with ClientSession(read, write) as session:
            # Initialize the connection
            await session.initialize()
            logger.info("Successfully connected to Web Scraping MCP server")
            
            # Call the cookie validation tool
            logger.info("Validating Medium cookies...")
            tool_response = await session.call_tool("validate_medium_cookies", arguments={})
            
            # Extract the validation result
            if tool_response.content and len(tool_response.content) > 0:
                validation_result = json.loads(tool_response.content[0].text)
                
                if not validation_result.get("valid", False):
                    error_msg = validation_result.get("error", "Unknown error with Medium cookies")
                    logger.error(f"Medium cookie validation failed: {error_msg}")
                    logger.error("Please run generate_medium_cookies.py to regenerate valid cookies.")
                    
                    # Print to console for visibility
                    print("\n")
                    print("=" * 80)
                    print("ERROR: Medium cookie validation failed!")
                    print(f"Reason: {error_msg}")
                    print("\nPlease run the following command to regenerate cookies:")
                    print("python generate_medium_cookies.py")
                    print("=" * 80)
                    print("\n")
                    
                    # Exit the program
                    sys.exit(1)
                else:
                    logger.info("Medium cookies validated successfully")
            else:
                logger.error("Empty response from validate_medium_cookies tool")
                logger.error("Unable to verify cookie validity. Exiting as a precaution.")
                
                # Print to console for visibility
                print("\n")
                print("=" * 80)
                print("ERROR: Could not verify Medium cookie validity!")
                print("Please run the following command to regenerate cookies:")
                print("python generate_medium_cookies.py")
                print("=" * 80)
                print("\n")
                
                # Exit the program
                sys.exit(1)
    
    # Continue with normal execution now that cookies are validated
    # Set up logger for the Gmail MCP server
    logger = setup_logger("gmail")
    logger.info("Starting MCP client for Gmail server")

    async with stdio_client(gmail_server_params) as (read, write):
        async with ClientSession(read, write) as session:
            # Initialize the connection
            await session.initialize()
            logger.info("Successfully connected to Gmail MCP server!")

            # Getting the list of articles from the latest Medium Daily Digest Email
            tool_response = await session.call_tool("get_medium_articles_from_gmail", arguments={})

            # Extract the articles from the tool response
            if tool_response.content and len(tool_response.content) > 0:
                json_str = tool_response.content[0].text
                articles = json.loads(json_str)
                logger.info("Successfully retrieved articles from Medium Daily Digest Email")
            
            if not isinstance(articles, list):
                logger.error("Parsed articles is not a list. Check the JSON structure.")
                return
            
            for article in articles:
                logger.info(f"Article Name: {article['Article Name']}")
                logger.info(f"Link: {article['Link']}")
                logger.info(f"Author: {article['Author']}")
    
            logger.info("All articles retrieved successfully")
    
    # Set up logger for the Web Scraping MCP server
    logger = setup_logger("web_scraping")
    logger.info("Starting MCP client for Web Scraping server")
    
    async with stdio_client(web_scraping_server_params) as (read, write):
        async with ClientSession(read, write) as session:
            # Initialize the connection
            await session.initialize()
            logger.info("Successfully connected to Web Scraping MCP server!")

            # Check if articles were retrieved from the Gmail MCP server
            if 'articles' in locals() and articles:
                # Process the first article from the list
                if len(articles) > 0:
                    selected_article = articles[0]  # You can modify this to process multiple articles
                    article_url = selected_article.get("Link")
                    article_name = selected_article.get("Article Name")
                    
                    logger.info(f"Processing article: {article_name}")
                    logger.info(f"Article URL: {article_url}")
                    
                    # Call the scrape_medium_article_content tool to get the article content
                    tool_response = await session.call_tool("scrape_medium_article_content", arguments={"short_url": article_url})
                    
                    # Extract the article content from the tool response
                    if tool_response.content and len(tool_response.content) > 0:
                        json_str = tool_response.content[0].text
                        try:
                            article_content = json.loads(json_str)
                            
                            # Enhanced error handling and validation
                            if "error" in article_content:
                                logger.error(f"Web scraping failed with error: {article_content['error']}")
                                
                                # Log debug information if available
                                if "debug_info" in article_content:
                                    debug_info = article_content["debug_info"]
                                    
                                    # Log key debugging information
                                    logger.error(f"Debug timestamp: {debug_info.get('timestamp')}")
                                    
                                    # Log process steps
                                    if "process_steps" in debug_info:
                                        logger.error("Process steps:")
                                        for step in debug_info["process_steps"]:
                                            step_details = step.get("details", {})
                                            step_details_str = json.dumps(step_details) if step_details else "No details"
                                            logger.error(f"  - {step.get('step')}: {step_details_str}")
                                    
                                    # Log authentication status
                                    logger.error(f"Authentication: attempted={debug_info.get('login_attempted', False)}, "
                                               f"successful={debug_info.get('login_successful', False)}")
                                    
                                    # Log screenshot paths
                                    if "screenshots" in debug_info and debug_info["screenshots"]:
                                        logger.error("Screenshots captured:")
                                        for screenshot in debug_info["screenshots"]:
                                            logger.error(f"  - {screenshot}")
                                    
                                    # Log recorded errors
                                    if "errors" in debug_info and debug_info["errors"]:
                                        logger.error("Recorded errors:")
                                        for error in debug_info["errors"]:
                                            logger.error(f"  - {error}")
                            elif "Name" in article_content and "Scraped text" in article_content:
                                # Only log success if we actually have content
                                content_text = article_content.get("Scraped text", "")
                                content_length = len(content_text) if content_text else 0
                                images = article_content.get("Images", [])
                                
                                if content_length > 0:
                                    logger.info("Successfully scraped article content")
                                    logger.info(f"Article title: {article_content.get('Name')}")
                                    logger.info(f"Content length: {content_length}")
                                    logger.info(f"Number of images: {len(images)}")
                                    
                                    # Content summary (first 15000 chars)
                                    if content_length > 0:
                                        summary = content_text[:150000] + "..." if len(content_text) > 15000 else content_text
                                        logger.info(f"Content preview: {summary}")
                                else:
                                    logger.error("Article was scraped but contains no content")
                                    logger.error(f"Article title: {article_content.get('Name')}")
                                    
                                    # Log article debug info if available
                                    if "article_debug" in article_content:
                                        article_debug = article_content["article_debug"]
                                        logger.error("Article debugging information:")
                                        
                                        # Log selectors tried
                                        if "selectors_tried" in article_debug:
                                            logger.error("Selectors tried:")
                                            for selector_info in article_debug["selectors_tried"]:
                                                selector = selector_info.get("selector", "unknown")
                                                found = selector_info.get("found", False)
                                                content_length = selector_info.get("content_length", 0) if found else 0
                                                logger.error(f"  - {selector}: found={found}, length={content_length}")
                                        
                                        # Log fallback information
                                        if "using_body_fallback" in article_debug:
                                            logger.error(f"Used body fallback: {article_debug.get('using_body_fallback')}")
                                        
                                        # Log potential errors
                                        if "body_fallback_error" in article_debug:
                                            logger.error(f"Body fallback error: {article_debug.get('body_fallback_error')}")
                                        
                                        if "image_extraction_error" in article_debug:
                                            logger.error(f"Image extraction error: {article_debug.get('image_extraction_error')}")
                            else:
                                logger.error("Unexpected response format from scraping tool")
                                logger.error(f"Response keys: {list(article_content.keys())}")
                        except json.JSONDecodeError as e:
                            logger.error(f"Failed to parse article content as JSON: {e}")
                            logger.error(f"Raw response: {json_str[:500]}...")
                    else:
                        logger.error("Empty response from scrape_medium_article_content tool")
                else:
                    logger.warning("No articles retrieved from Medium Daily Digest")
            else:
                logger.warning("No articles available to process")
                
            logger.info("Web scraping process completed")

if __name__ == "__main__":
    asyncio.run(run())

# Claude Tool Call API Reference:

# Call the tool from the MCP server

# # Define user prompt
# user_query = "Please extract the articles from my latest Medium Daily Digest Email."
# logger.info(f"User query: {user_query}")

# # Run conversation with Claude
# final_response = await claude_conversation(
#     session=session,
#     user_prompt=user_query,
#     system_prompt=llm_system_prompt_tool_use,
#     model="claude-3-7-sonnet-20250219",
#     max_tokens=8192,
#     temperature=0,
#     max_iterations=5,
#     max_conversation_length=8,
#     server_name="gmail",
#     logger=logger
# )

# logger.info("Conversation completed successfully")
# logger.info(f"Final response from Claude: {final_response}")
# print("\nFinal response from Claude:")
# print(final_response)


# MCP Developer API Reference:

# # List available tools
# response = await session.list_tools()
# print("\nAvailable tools:")
# print(response, "\n")
# available_tools = [{
#     "name": tool.name,
#     "description": tool.description,
#     "inputSchema": tool.inputSchema
# } for tool in response.tools]

# # Print the available tools and their input schemas
# for tool in available_tools:
#     print(f"- {tool['name']} ({tool['description']})")
#     print(f"  Input schema: {tool['inputSchema']}")

# # List available resources
# response = await session.list_resources()
# print("\nAvailable resources:")
# print(response, "\n")
# available_resources = [{
#     "uri": resource.uri,
#     "name": resource.name,
#     "description": resource.description,
#     "mimeType": resource.mimeType if hasattr(resource, 'mimeType') else 'no mime type'
# } for resource in response.resources]

# # Print the available resources and their details
# for resource in available_resources:
#     print(f"- {resource['uri']} ({resource['name']})")
#     print(f"  Description: {resource['description']}")
#     print(f"  Mime type: {resource['mimeType']}")

# # List available resource templates
# response = await session.list_resource_templates()
# print("\nAvailable resource templates:")
# print(response, "\n")
# available_resource_templates = [{
#     "uriTemplate": resource_template.uriTemplate,
#     "name": resource_template.name,
#     "description": resource_template.description,
#     "mimeType": resource_template.mimeType if hasattr(resource_template, 'mimeType') else 'no mime type'
# } for resource_template in response.resourceTemplates]

# # Print the available resource templates and their details
# for resource_template in available_resource_templates:
#     print(f"- {resource_template['uriTemplate']} ({resource_template['name']})")
#     print(f"  Description: {resource_template['description']}")
#     print(f"  Mime type: {resource_template['mimeType']}")

# # List available prompts
# response = await session.list_prompts()
# print("\nAvailable prompts:")
# print(response)
# available_prompts = [{
#     "name": prompt.name,
#     "description": prompt.description,
#     "arguments": prompt.arguments
# } for prompt in response.prompts]

# # Print the available prompts and their details
# for prompt in available_prompts:
#     print(f"- {prompt['name']} ({prompt['description']})")
#     print(f"  Arguments: {prompt['arguments']}")


# # Test resources
# content = await session.read_resource("config://app")
# print(f"\nStandard greeting: {content}")

# # Test resource templates - For a resoource template, the parameter has to already be put into the URI before passing to "read_resource"
# content = await session.read_resource("greeting://Rounak")
# print(f"\nPersonalized greeting: {content}")

# # Test prompts
# content = await session.get_prompt("debug_error", arguments={"error": "476fyu78guyi7t"})
# print(f"\nDebug error prompt: {content}")
