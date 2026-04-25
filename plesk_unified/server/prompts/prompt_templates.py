from fastmcp import FastMCP


def register_prompts(mcp: FastMCP):
    """
    Register standard prompt templates for Plesk development and administration.
    """

    @mcp.prompt(name="plesk-extension-dev-guide")
    def plesk_extension_dev_guide(extension_name: str, target_language: str) -> str:
        """
        Generate a starter guide for developing a new Plesk extension.
        """
        return f"""You are an expert Plesk Extension developer.
Help me design and implement a new Plesk extension called "{extension_name}"
using {target_language}.

Please follow these steps:
1. Use `search_plesk_unified(query="{extension_name} development guide",
   category="guide")` to find relevant architectural patterns.
2. Use `search_plesk_unified(query="{target_language} sdk hooks",
   category="js-sdk" if "{target_language}".lower() == "javascript" else "php-stubs")`
   to find specific implementation details.
3. Provide a step-by-step roadmap including directory structure,
   `meta.xml` configuration, and a basic code example.

Goal: Create a robust, secure, and idiomatic Plesk extension."""

    @mcp.prompt(name="plesk-api-integration")
    def plesk_api_integration(api_operation: str) -> str:
        """
        Instructions and examples for integrating with a Plesk API operation.
        """
        return f"""You are a technical expert in Plesk API integrations.
I need to implement the "{api_operation}" operation in my application.

Please:
1. Search for the "{api_operation}" specification using
   `search_plesk_unified(query="{api_operation}", category="api")`.
2. Explain whether this should use the XML-RPC API or the REST API.
3. Provide a complete request example (XML or JSON) and describe the
   expected response.
4. Detail any specific permissions or security considerations for this
   operation.

Focus on accuracy and compliance with the Plesk Obsidian API standards."""

    @mcp.prompt(name="plesk-cli-reference")
    def plesk_cli_reference(command_name: str) -> str:
        """
        Get detailed reference information for a Plesk CLI command.
        """
        return f"""You are a Plesk Linux administrator and CLI expert.
I need a comprehensive reference for the `{command_name}` command.

Please:
1. Retrieve the command details using
   `search_plesk_unified(query="{command_name}", category="cli")`.
2. Summarize the command's primary purpose.
3. List the most important subcommands and options with brief explanations.
4. Provide 2-3 practical examples of how to use this command in daily
   administration or automation.

Ensure the information is clear, concise, and technically accurate."""
