# Module 1: Basic MCP Server - Starter Code

Welcome to Module 1! In this module, you'll build a basic MCP server that helps developers create better pull requests by analyzing code changes and suggesting appropriate templates.

## Your Task

Implement an MCP server with three tools:

1. **analyze_file_changes** - Retrieve git diff information and changed files
2. **get_pr_templates** - List available PR templates 
3. **suggest_template** - Allow Claude to suggest the most appropriate template


## Setup

### 1. Install uv

Follow the official installation instructions at: https://docs.astral.sh/uv/getting-started/installation/

### 2. Install dependencies

```bash
# Install all dependencies
uv sync

# Or install with dev dependencies for testing
uv sync --all-extras
```

### 3. Start implementing!

Open `server.py` and follow the TODO comments to implement each tool.

**Note**: The starter code includes stub implementations that return "Not implemented" errors. This allows you to:
- Run the server immediately
- Test your setup with Claude
- Replace each stub with your actual implementation
- See helpful hints about what each tool should do

## Design Philosophy

Instead of using rigid rules based on file extensions or patterns, your tools should provide Claude with raw git data and let Claude's intelligence determine:
- What type of change is being made
- Which template is most appropriate
- How to customize the template for the specific changes

## Testing Your Implementation

1. Run the unit tests:
   ```bash
   uv run pytest test_server.py -v
   ```

2. Configure the MCP server in Claude Code:
   ```bash
   # Add the MCP server
   claude mcp add pr-agent -- uv --directory /absolute/path/to/module1/starter run server.py
   
   # Verify it's configured
   claude mcp list
   ```

3. Make some changes in a git repository and ask Claude to analyze your changes and suggest a PR template

## Need Help?

- Check the solution in `../solution/` if you get stuck
- Remember: The goal is to give Claude the data it needs, not to implement complex logic yourself

# Module 2: GitHub Actions Integration - Starter Code

This is your starting point for Module 2. You'll extend the PR Agent from Module 1 with webhook handling and MCP Prompts.

## Your Task

1. **Import Required Types**: Add the necessary imports for MCP Prompts
2. **Connect to Events File**: Define the path to read webhook events
3. **Implement GitHub Actions Tools**: Complete the tools to query events
4. **Create MCP Prompts**: Build prompts for standardized CI/CD workflows

Note: The webhook server (`webhook_server.py`) is provided for you!

## Getting Started

1. Install dependencies:
   ```bash
   uv sync
   ```

2. Start the webhook server (in a separate terminal):
   ```bash
   python webhook_server.py
   ```

3. Follow the TODOs in `server.py` to implement Module 2 features

## Testing Your Implementation

1. Start your server:
   ```bash
   uv run server.py
   ```

2. In another terminal, start Cloudflare Tunnel:
   ```bash
   cloudflared tunnel --url http://localhost:8080
   ```

3. Configure GitHub webhooks with your tunnel URL

4. Test with Claude Code using the new prompts

## Implementation Hints

- The webhook server stores events in `github_events.json`
- Read the JSON file in your tools to get event data
- Prompts are simple functions that return strings with instructions
- Decorate prompt functions with `@mcp.prompt()`

## Need Help?

- Review the Module 2 documentation
- Check the solution in the `solution/` directory
- Look at the MCP documentation for Prompts: https://modelcontextprotocol.io/docs/concepts/prompts
