# GitHub Tasks Bot

A Discord bot that sends notifications to a specified channel when new tasks are merged/

## Features

- Listens for GitHub webhook events
- Sends formatted Discord messages when PRs are merged
- Configurable through environment variables

## Prerequisites

- Discord Bot Token
- GitHub Personal Access Token (PAT)
- Discord Channel ID
- GitHub Repository name

## Setup

1. Clone this repository
2. Install dependencies using uv:
   ```bash
   uv pip install -r requirements.txt
   ```
3. Copy `.env.example` to `.env` and fill in your credentials:
   ```bash
   cp .env.example .env
   ```
4. Edit `.env` with your actual values:
   - `DISCORD_BOT_TOKEN`: Your Discord bot token
   - `DISCORD_CHANNEL_ID`: The ID of the channel where notifications should be sent
   - `GITHUB_PAT`: Your GitHub Personal Access Token
   - `GITHUB_REPO`: The repository name in format `owner/repo`

## GitHub Webhook Setup

1. Go to your GitHub repository settings
2. Navigate to Webhooks > Add webhook
3. Set the Payload URL to your server's webhook endpoint (e.g., `http://your-server:8000/webhook`)
4. Set Content type to `application/json`
5. Select "Pull requests" as the event to listen for
6. Save the webhook

## Running the Bot

To run the bot locally:

```bash
python src/bot.py
```

The bot will start a FastAPI server on port 8000 to receive GitHub webhooks and connect to Discord.

## Security Notes

- Keep your `.env` file secure and never commit it to version control
- Use a strong GitHub PAT with minimal required permissions
- The webhook endpoint verifies GitHub signatures to ensure requests are legitimate 