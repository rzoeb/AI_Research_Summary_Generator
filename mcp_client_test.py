from mcp import ClientSession, StdioServerParameters, types
from mcp.client.stdio import stdio_client
import os
import asyncio
from dotenv import load_dotenv
import json
import anthropic
from datetime import datetime

# Load environment variables from .env file
load_dotenv()

# Create server parameters for stdio connection
server_params = StdioServerParameters(
    command="python",  
    args=["mcp_servers\\gmail.py"],
    env=os.environ.copy()
)

# Load API key from environment variables
api_key = os.getenv("ANTHROPIC_API_KEY")
if not api_key:
    print("Error: ANTHROPIC_API_KEY environment variable not set.")

# Initialize Claude client
client = anthropic.Anthropic(api_key=api_key)

llm_system_prompt = """
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

user_prompt = "Please extract the articles from my latest Medium Daily Digest Email."

async def run():
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(
            read, write
        ) as session:
            # Initialize the connection
            await session.initialize()
            print("Successfully connected to Gmail MCP server!")

            # Get information about available tools
            tools_response = await session.list_tools()
            available_tools = [{
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.inputSchema
            } for tool in tools_response.tools]
            
            # Format tool info for the system prompt
            tools_info = ""
            for tool in available_tools:
                tools_info += f"Tool: {tool['name']}\n"
                tools_info += f"Description: {tool['description']}\n"
                tools_info += f"Arguments: {json.dumps(tool['input_schema'], indent=2)}\n\n"
            
            # Keep track of conversation history
            conversation = [
                {"role": "user", "content": user_prompt}
            ]
            
            while True:
                print("\nSending request to Claude with current conversation...")
                response = client.messages.create(
                    model="claude-3-7-sonnet-20250219",
                    max_tokens=8192,
                    tools=available_tools,
                    temperature=0,
                    system=llm_system_prompt.format(tools_description=tools_info),
                    messages=conversation
                )
                
                # Extract and print Claude's assistant message
                assistant_response = response.content[0].text
                print("\nClaude's response:")
                print(assistant_response)
                
                # If Claude requests a tool, process the tool use blocks
                if response.stop_reason == "tool_use":
                    tool_blocks = [block for block in response.content if block.type == "tool_use"]
                    if not tool_blocks:
                        print("No tool use block found despite stop_reason indicating tool use.")
                        break
                    for block in tool_blocks:
                        tool_name = block.name
                        tool_input = block.input  # expected to be a dict
                        tool_call_id = block.id
                        print(f"\nClaude requested tool: {tool_name} with input: {json.dumps(tool_input)}")
                        
                        # Execute the tool and parse the result
                        try:
                            tool_response = await session.call_tool(tool_name, arguments=tool_input)
                            tool_result_text = tool_response.content[0].text
                            tool_result = json.loads(tool_result_text)
                            print(f"Tool '{tool_name}' executed successfully. Result (truncated): {json.dumps(tool_result)[:500]}...")
                        except Exception as e:
                            tool_result = {"error": str(e)}
                            print(f"Error executing tool {tool_name}: {e}")
                        
                        # Append the assistant's tool use message to conversation history
                        conversation.append({
                            "role": "assistant",
                            "content": [
                                {"type": "text", "text": assistant_response},
                                {"type": "tool_use", "id": tool_call_id, "name": tool_name, "input": tool_input}
                            ]
                        })
                        # Append the tool result back to Claude as a user message (using tool_result type)
                        conversation.append({
                            "role": "user",
                            "content": [
                                {"type": "tool_result", "tool_use_id": tool_call_id, "content": json.dumps(tool_result)}
                            ]
                        })
                    # Continue the loop to let Claude process the tool results
                    continue
                else:
                    # If no tool use is requested, output the final response and exit the loop
                    print("\nFinal response from Claude:")
                    print(assistant_response)
                    break

if __name__ == "__main__":
    asyncio.run(run())


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
