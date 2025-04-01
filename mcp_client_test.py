from mcp import ClientSession, StdioServerParameters, types
from mcp.client.stdio import stdio_client
import os
import asyncio
from dotenv import load_dotenv
import json

# Load environment variables from .env file
load_dotenv()

# Create server parameters for stdio connection
server_params = StdioServerParameters(
    command="python",  
    args=["mcp_servers\\gmail.py"],
    env=os.environ.copy()
)

async def run():
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(
            read, write
        ) as session:
            # Initialize the connection
            await session.initialize()
            print("Successfully connected to Gmail MCP server!")
            
            # List available tools
            response = await session.list_tools()
            print("\nAvailable tools:")
            available_tools = [{
                "name": tool.name,
                "description": tool.description[:50] + "..." if len(tool.description) > 50 else tool.description
            } for tool in response.tools]
            
            for tool in available_tools:
                print(f"- {tool['name']}: {tool['description']}")

            # Example 1: Search Gmail with a query
            print("\n\n--- Example 1: Search Gmail with a query ---")
            query = "from:noreply@medium.com in:inbox"
            print(f"Searching for: {query}")

            # Get the result and extract the actual result data
            tool_response = await session.call_tool("get_gmail_message", arguments={"query": query})

            # Extract the text content and parse as JSON
            json_str = tool_response.content[0].text

            # Parse the JSON string into a Python dictionary
            result = json.loads(json_str)
                
            # Check for error
            if "error" in result:
                print(f"\nError: {result['error']}")
            else:
                print(f"\nFound email:")
                print(f"ID: {result.get('id', 'N/A')}")
                print(f"Thread ID: {result.get('threadId', 'N/A')}")
                print(f"Label IDs: {', '.join(result.get('labelIds', []))}")
                print(f"Subject: {result.get('subject', 'N/A')}")
                print(f"From: {result.get('from', 'N/A')}")
                print(f"To: {result.get('to', 'N/A')}")
                print(f"Date: {result.get('date', 'N/A')}")
                print(f"\nSnippet:\n{result.get('snippet', 'N/A')}")
                print(f"\nBody (HTML):\n{result.get('body', 'N/A')[:500]}...")  # Truncating HTML output for readability
                
                # Get the message ID for the next example
                message_id = result.get('id')
                if message_id:
                    # Example 2: Get email by ID
                    print("\n\n--- Example 2: Get email by ID ---")
                    print(f"Retrieving message with ID: {message_id}")
                    
                    # Extract result data properly
                    id_tool_response = await session.call_tool("get_gmail_message", arguments={"message_id": message_id})
                    id_json_str = id_tool_response.content[0].text
                    id_result = json.loads(id_json_str)
                    
                    if "error" in id_result:
                        print(f"\nError: {id_result['error']}")
                    else:
                        print(f"\nRetrieved email details:")
                        print(f"ID: {id_result.get('id', 'N/A')}")
                        print(f"Thread ID: {id_result.get('threadId', 'N/A')}")
                        print(f"Label IDs: {', '.join(id_result.get('labelIds', []))}")
                        print(f"Subject: {id_result.get('subject', 'N/A')}")
                        print(f"From: {id_result.get('from', 'N/A')}")
                        print(f"To: {id_result.get('to', 'N/A')}")
                        print(f"Date: {id_result.get('date', 'N/A')}")
                        print(f"\nSnippet:\n{id_result.get('snippet', 'N/A')}")
                        print(f"\nBody (HTML):\n{id_result.get('body', 'N/A')[:500]}...")  # Truncating HTML output for readability
            
            # Example 3: Test error handling - missing parameters
            print("\n\n--- Example 3: Test error handling - missing parameters ---")
            error_tool_response = await session.call_tool("get_gmail_message", arguments={})
            error_result_json = error_tool_response.content[0].text
            error_result = json.loads(error_result_json)
            print(f"Result with no parameters: {error_result}")
            
            # Example 4: Test error handling - non-existent message
            print("\n\n--- Example 4: Test error handling - non-existent query ---")
            not_found_tool_response = await session.call_tool(
                "get_gmail_message", 
                arguments={"query": "from:nonexistent123456@example.com subject:\"This Should Not Exist\" after:2099/01/01"}
            )
            not_found_result_json = not_found_tool_response.content[0].text
            not_found_result = json.loads(not_found_result_json)
            print(f"Result with non-existent query: {not_found_result}")
            
            # Example 5: Extract articles from Medium Daily Digest
            print("\n\n--- Example 5: Extract articles from Medium Daily Digest ---")
            medium_query = "from:noreply@medium.com in:inbox"
            print(f"Searching for Medium Daily Digest: {medium_query}")
            
            # Get Medium Daily Digest email
            medium_response = await session.call_tool("get_gmail_message", arguments={"query": medium_query})
            medium_json_str = medium_response.content[0].text
            medium_result = json.loads(medium_json_str)
            
            # Check for error in email retrieval
            if "error" in medium_result:
                print(f"\nError retrieving Medium Daily Digest: {medium_result['error']}")
            else:
                print(f"\nFound Medium Daily Digest email:")
                print(f"Subject: {medium_result.get('subject', 'N/A')}")
                print(f"From: {medium_result.get('from', 'N/A')}")
                print(f"Date: {medium_result.get('date', 'N/A')}")
                
                # Extract and process articles from the email
                email_body = medium_result.get('body', '')
                
                # Call the extract_medium_articles tool
                articles_response = await session.call_tool("extract_medium_articles", arguments={"email_body": email_body})
                articles_json_str = articles_response.content[0].text
                articles = json.loads(articles_json_str)
                
                # Display the extracted articles
                if not articles:
                    print("\nNo articles were found in this email or it's not a Medium Daily Digest.")
                else:
                    # print(f"\nExtracted {len(articles)} articles from the Medium Daily Digest:")
                    # print(type(articles))
                    print(articles_response)
                    # for i, article in enumerate(articles, 1):
                    #     print(f"\nArticle {i}:")
                    #     print(f"Title: {article.get('Article Name', 'N/A')}")
                    #     print(f"Author: {article.get('Author', 'N/A')}")
                    #     print(f"Link: {article.get('Link', 'N/A')}")
            
            # Example 6: Test error handling with non-Medium email
            print("\n\n--- Example 6: Test extract_medium_articles with non-Medium email ---")
            non_medium_query = "NOT from:medium.com in:inbox"
            print(f"Searching for non-Medium email: {non_medium_query}")
            
            # Get a non-Medium email
            non_medium_response = await session.call_tool("get_gmail_message", arguments={"query": non_medium_query})
            non_medium_json_str = non_medium_response.content[0].text
            non_medium_result = json.loads(non_medium_json_str)
            
            if "error" in non_medium_result:
                print(f"\nError retrieving non-Medium email: {non_medium_result['error']}")
            else:
                non_medium_body = non_medium_result.get('body', '')
                
                try:
                    # Try to extract articles from a non-Medium email
                    test_response = await session.call_tool("extract_medium_articles", arguments={"email_body": non_medium_body})
                    
                    # Handle potential empty response
                    if not test_response.content:
                        print("The extract_medium_articles tool returned an empty response.")
                        test_result = []
                    else:
                        test_json_str = test_response.content[0].text
                        test_result = json.loads(test_json_str)
                    
                    # Check the result
                    if not test_result:
                        print("Successfully detected non-Medium email and returned empty list as expected.")
                    else:
                        print(f"Unexpected result: Found {len(test_result)} articles in a non-Medium email.")
                
                except Exception as e:
                    print(f"Error testing extract_medium_articles with non-Medium email: {str(e)}")

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
