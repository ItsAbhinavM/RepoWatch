"""
GitHub → Discord Notifier
Triggers on:
- New Pull Request
- New Issue
"""

import os
import json
import requests

DISCORD_WEBHOOK = os.environ["DISCORD_WEBHOOK"]

def send_to_discord(payload):
    response = requests.post(DISCORD_WEBHOOK, json=payload)
    if response.status_code not in (200, 204):
        raise RuntimeError(f"Discord webhook failed: {response.text}")

def format_pr(event):
    pr = event["pull_request"]
    repo = event["repository"]["full_name"]

    return {
        "embeds": [{
            "title": f"🔀 New Pull Request: {pr['title']}",
            "url": pr["html_url"],
            "description": pr["body"][:500] if pr["body"] else "No description provided",
            "color": 0x2ECC71,
            "fields": [
                {"name": "Repository", "value": repo, "inline": True},
                {"name": "Author", "value": pr["user"]["login"], "inline": True},
                {"name": "Branch", "value": f"{pr['head']['ref']} → {pr['base']['ref']}", "inline": False}
            ]
        }]
    }

def format_issue(event):
    issue = event["issue"]
    repo = event["repository"]["full_name"]

    return {
        "embeds": [{
            "title": f"🐛 New Issue: {issue['title']}",
            "url": issue["html_url"],
            "description": issue["body"][:500] if issue["body"] else "No description provided",
            "color": 0xE74C3C,
            "fields": [
                {"name": "Repository", "value": repo, "inline": True},
                {"name": "Author", "value": issue["user"]["login"], "inline": True}
            ]
        }]
    }

def main():
    event_path = os.environ["GITHUB_EVENT_PATH"]
    with open(event_path) as f:
        event = json.load(f)

    event_name = os.environ["GITHUB_EVENT_NAME"]

    if event_name == "pull_request" and event["action"] == "opened":
        send_to_discord(format_pr(event))

    elif event_name == "issues" and event["action"] == "opened":
        send_to_discord(format_issue(event))

if __name__ == "__main__":
    main()

