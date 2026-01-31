"""
Discord GitHub Polling Bot
Monitors a public GitHub repository and sends Discord messages when:
- A new Pull Request is created
- A new Issue is created

No repository access required - uses GitHub's public API
"""

import os
import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv
import aiohttp
import asyncio
from datetime import datetime, timezone
import json

load_dotenv()

# Configuration
DISCORD_BOT_TOKEN = os.getenv('DISCORD_BOT_TOKEN')
DISCORD_CHANNEL_ID = int(os.getenv('DISCORD_CHANNEL_ID', '0'))
GITHUB_REPO = os.getenv('GITHUB_REPO')  # Format: "owner/repo" e.g., "microsoft/vscode"
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN', '')  # Optional - increases rate limit
CHECK_INTERVAL = int(os.getenv('CHECK_INTERVAL', '60'))  # Check every 60 seconds

# Storage for tracking seen items
SEEN_FILE = 'seen_items.json'

# Initialize Discord bot
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# Track what we've already seen
seen_prs = set()
seen_issues = set()


def load_seen_items():
    """Load previously seen items from file"""
    global seen_prs, seen_issues
    try:
        if os.path.exists(SEEN_FILE):
            with open(SEEN_FILE, 'r') as f:
                data = json.load(f)
                seen_prs = set(data.get('prs', []))
                seen_issues = set(data.get('issues', []))
                print(f"Loaded {len(seen_prs)} seen PRs and {len(seen_issues)} seen issues")
    except Exception as e:
        print(f"Error loading seen items: {e}")
        seen_prs = set()
        seen_issues = set()


def save_seen_items():
    """Save seen items to file"""
    try:
        with open(SEEN_FILE, 'w') as f:
            json.dump({
                'prs': list(seen_prs),
                'issues': list(seen_issues)
            }, f)
    except Exception as e:
        print(f"Error saving seen items: {e}")


async def fetch_github_data(session, url):
    """Fetch data from GitHub API"""
    headers = {
        'Accept': 'application/vnd.github.v3+json',
    }
    
    # Add authentication if token is provided (increases rate limit)
    if GITHUB_TOKEN:
        headers['Authorization'] = f'token {GITHUB_TOKEN}'
    
    try:
        async with session.get(url, headers=headers) as response:
            if response.status == 200:
                return await response.json()
            elif response.status == 403:
                print("Rate limit exceeded. Consider adding a GITHUB_TOKEN to increase limits.")
                return None
            else:
                print(f"GitHub API error: {response.status}")
                return None
    except Exception as e:
        print(f"Error fetching GitHub data: {e}")
        return None


def create_pr_embed(pr):
    """Create a Discord embed for pull request"""
    embed = discord.Embed(
        title=f"🔀 New Pull Request: {pr['title']}",
        url=pr['html_url'],
        description=(pr['body'][:500] if pr.get('body') else "No description provided") + ("..." if pr.get('body') and len(pr['body']) > 500 else ""),
        color=discord.Color.green(),
        timestamp=datetime.fromisoformat(pr['created_at'].replace('Z', '+00:00'))
    )
    
    embed.add_field(name="Repository", value=GITHUB_REPO, inline=True)
    embed.add_field(name="Author", value=pr['user']['login'], inline=True)
    embed.add_field(name="Branch", value=f"{pr['head']['ref']} → {pr['base']['ref']}", inline=False)
    
    if pr.get('labels'):
        labels = ', '.join([label['name'] for label in pr['labels']])
        if labels:
            embed.add_field(name="Labels", value=labels, inline=False)
    
    embed.set_thumbnail(url=pr['user']['avatar_url'])
    embed.set_footer(text=f"PR #{pr['number']}")
    
    return embed


def create_issue_embed(issue):
    """Create a Discord embed for issue"""
    embed = discord.Embed(
        title=f"🐛 New Issue: {issue['title']}",
        url=issue['html_url'],
        description=(issue['body'][:500] if issue.get('body') else "No description provided") + ("..." if issue.get('body') and len(issue['body']) > 500 else ""),
        color=discord.Color.red(),
        timestamp=datetime.fromisoformat(issue['created_at'].replace('Z', '+00:00'))
    )
    
    embed.add_field(name="Repository", value=GITHUB_REPO, inline=True)
    embed.add_field(name="Author", value=issue['user']['login'], inline=True)
    
    if issue.get('labels'):
        labels = ', '.join([label['name'] for label in issue['labels']])
        if labels:
            embed.add_field(name="Labels", value=labels, inline=False)
    
    embed.set_thumbnail(url=issue['user']['avatar_url'])
    embed.set_footer(text=f"Issue #{issue['number']}")
    
    return embed


async def send_discord_message(embed):
    """Send embed to Discord channel"""
    try:
        channel = bot.get_channel(DISCORD_CHANNEL_ID)
        if channel:
            await channel.send(embed=embed)
        else:
            print(f"Channel {DISCORD_CHANNEL_ID} not found")
    except Exception as e:
        print(f"Error sending Discord message: {e}")


@tasks.loop(seconds=CHECK_INTERVAL)
async def check_repository():
    """Periodically check repository for new PRs and issues"""
    print(f"Checking repository: {GITHUB_REPO}")
    
    async with aiohttp.ClientSession() as session:
        # Check for new Pull Requests
        pr_url = f"https://api.github.com/repos/{GITHUB_REPO}/pulls?state=open&sort=created&direction=desc&per_page=10"
        prs = await fetch_github_data(session, pr_url)
        
        if prs:
            new_prs = []
            for pr in prs:
                pr_id = pr['id']
                if pr_id not in seen_prs:
                    new_prs.append(pr)
                    seen_prs.add(pr_id)
            
            # Send notifications for new PRs (in reverse order, oldest first)
            for pr in reversed(new_prs):
                embed = create_pr_embed(pr)
                await send_discord_message(embed)
                print(f"New PR detected: #{pr['number']} - {pr['title']}")
                await asyncio.sleep(1)  # Small delay between messages
        
        # Check for new Issues
        issue_url = f"https://api.github.com/repos/{GITHUB_REPO}/issues?state=open&sort=created&direction=desc&per_page=10"
        issues_data = await fetch_github_data(session, issue_url)
        
        if issues_data:
            # Filter out pull requests (GitHub API returns PRs as issues too)
            issues = [issue for issue in issues_data if 'pull_request' not in issue]
            
            new_issues = []
            for issue in issues:
                issue_id = issue['id']
                if issue_id not in seen_issues:
                    new_issues.append(issue)
                    seen_issues.add(issue_id)
            
            # Send notifications for new issues (in reverse order, oldest first)
            for issue in reversed(new_issues):
                embed = create_issue_embed(issue)
                await send_discord_message(embed)
                print(f"New issue detected: #{issue['number']} - {issue['title']}")
                await asyncio.sleep(1)  # Small delay between messages
        
        # Save seen items
        save_seen_items()


@check_repository.before_loop
async def before_check_repository():
    """Wait for bot to be ready before starting the loop"""
    await bot.wait_until_ready()
    print("Bot is ready, starting repository monitoring...")


@bot.event
async def on_ready():
    """Bot ready event"""
    print(f'Discord bot logged in as {bot.user.name} (ID: {bot.user.id})')
    print(f'Monitoring repository: {GITHUB_REPO}')
    print(f'Notification channel ID: {DISCORD_CHANNEL_ID}')
    print(f'Check interval: {CHECK_INTERVAL} seconds')
    print('------')
    
    # Load previously seen items
    load_seen_items()
    
    # Start the monitoring task
    if not check_repository.is_running():
        check_repository.start()


@bot.command(name='status')
async def status(ctx):
    """Check bot status"""
    if ctx.channel.id == DISCORD_CHANNEL_ID:
        await ctx.send(f"✅ Monitoring **{GITHUB_REPO}**\n"
                      f"📊 Tracking {len(seen_prs)} PRs and {len(seen_issues)} issues\n"
                      f"⏱️ Checking every {CHECK_INTERVAL} seconds")


@bot.command(name='reset')
@commands.has_permissions(administrator=True)
async def reset(ctx):
    """Reset tracking (admin only)"""
    if ctx.channel.id == DISCORD_CHANNEL_ID:
        global seen_prs, seen_issues
        seen_prs.clear()
        seen_issues.clear()
        save_seen_items()
        await ctx.send("🔄 Tracking reset! Will notify about all current open PRs and issues on next check.")


if __name__ == '__main__':
    # Validate environment variables
    if not DISCORD_BOT_TOKEN:
        raise ValueError("DISCORD_BOT_TOKEN environment variable is required")
    if not DISCORD_CHANNEL_ID:
        raise ValueError("DISCORD_CHANNEL_ID environment variable is required")
    if not GITHUB_REPO:
        raise ValueError("GITHUB_REPO environment variable is required (format: owner/repo)")
    
    print("Starting Discord GitHub Polling Bot...")
    print(f"Will monitor: {GITHUB_REPO}")
    print(f"Check interval: {CHECK_INTERVAL} seconds")
    
    # Run bot
    bot.run(DISCORD_BOT_TOKEN)