import os
import time
import json
import telebot
import requests
from datetime import datetime, timedelta
from pymongo import MongoClient
from telebot import formatting
from bs4 import BeautifulSoup
from pymongo.server_api import ServerApi


# FOR THE HEADERS
from datetime import datetime
import secrets
import base64



class TwitterTelegramBot:
    def __init__(self):
        # Environment variables
        self.api_key = os.environ['API']
        self.channel_id = os.environ["CHANNEL_ID"]
        self.mongo_url = os.environ['MONGODB_URI']
        
        # Initialize bot and database
        self.bot = telebot.TeleBot(self.api_key)
        self.client = MongoClient(self.mongo_url, server_api=ServerApi('1'))
        self.db = self.client['tweet_api']
        self.collection = self.db['tweetcollection']
        
        # Twitter scraping cookies
        self.headers = self.generate_headers()


    def generate_headers(self):
        # Current GMT time in HTTP-date format
        date_str = datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S GMT")
        
        # Generate a fake cookie token
        token = secrets.token_hex(16)  # 32-char hex
        cookie = f"tiekoetter.com-cookie-verification={token}"
        
        return {
            "content-type": "text/html;charset=utf-8",
            "content-security-policy": (
                "default-src 'none'; script-src 'self' 'unsafe-inline'; "
                "img-src 'self' https://*.tiekoetter.cloud; "
                "style-src 'self' 'unsafe-inline'; font-src 'self' data:; "
                "connect-src 'self' https://*.twimg.com"
            ),
            "strict-transport-security": "max-age=31536000; includeSubDomains; preload",
            "referrer-policy": "no-referrer",
            "permissions-policy": "geolocation=(), microphone=(), camera=()",
            "x-content-type-options": "nosniff",
            "x-frame-options": "SAMEORIGIN",
            "x-xss-protection": "1; mode=block",
            "date": date_str,
            "x-test-cookie": cookie,
        }

    def get_values(self, values):
        """Generator function for cycling through values."""
        index = 0
        while True:
            yield values[index]
            index = (index + 1) % len(values)

    def report(self, message):
        """Send a message to Telegram."""
        try:
            self.bot.send_message(chat_id=self.channel_id, text=message, parse_mode='MarkdownV2')
            return True
        except Exception as e:
            print(f"Failed to send message: {e}")
            return False


    def get_tweet_by_userid(self, usernames, replies=True):
        """Retrieve tweets from specified usernames."""
        all_tweets = []
        try:
            for username in usernames:
                tweets_list = []
                try:
                    # Construct the correct URL based on 'replies' flag
                    url = f"https://nitter.tiekoetter.com/{username}"
                    if replies:
                        url += "/with_replies"

                    print(f"Fetching tweets for user: {username} from URL: {url}")

                    # Use the session for requests
                    response = requests.get(url, headers=self.headers, timeout=15) # Use session headers and timeout

                    if response.status_code != 200:
                        print(f"Failed to fetch page for {username}. Status: {response.status_code}")
                        all_tweets.append({username: []}) # Append empty list for failed user
                        continue # Skip to the next username

                    soup = BeautifulSoup(response.text, 'html.parser')

                    # Find the main timeline items
                    tweets = soup.select('.timeline-item')
                    print(f"Found {len(tweets)} potential tweets for {username}")

                    for tweet in tweets:
                        tweet_dict = {} # Initialize tweet_dict for each tweet

                        link_tag = tweet.select_one('.tweet-link')
                        date_tag = tweet.select_one('.tweet-date a')
                        content_tag = tweet.select_one('.tweet-content')
                        body = tweet.select_one('.tweet-body')

                        # Extract basic tweet information
                        tweet_link = link_tag['href'] if link_tag else None
                        tweet_date = date_tag['title'] if date_tag else None
                        tweet_id = tweet_link.split('/')[-1].replace('#m', '') if tweet_link else None # Handle the #m suffix

                        # Extract tweet content, handling retweets and replies
                        raw_text = content_tag.get_text(strip=True) if content_tag else ""
                        if body and body.select_one('.retweet-header'):
                            tweet_text = f"RT: {raw_text}"
                        elif body and body.select_one('.replying-to'):
                            replying_to_text = body.select_one('.replying-to').get_text()
                            tweet_text = f"{replying_to_text.replace('Replying to ', '')} {raw_text}"
                        else:
                            tweet_text = raw_text

                        # Prepare the tweet data dictionary
                        tweet_data = {
                            "ID": tweet_id,
                            "TEXT": tweet_text,
                            "TIME": (datetime.strptime(tweet_date.replace(" UTC", ""), "%b %d, %Y · %I:%M %p") + timedelta(hours=3)).strftime("%b %d, %Y · %I:%M %p"),
                            "URL": f"http://vxtwitter.com{tweet_link}" if tweet_link else None,
                            "STATS": {} # Placeholder for stats if needed later
                        }
                        tweets_list.append(tweet_data)

                except Exception as e:
                    print(f"Error processing tweets for {username}: {e}")
                    # If an error occurs for a specific user, append an empty list for that user
                    all_tweets.append({username: []})
                    continue # Continue to the next username

                # After processing all tweets for a user, append the list to all_tweets
                all_tweets.append({username: tweets_list})

        except Exception as e:
            print(f"Error in the main user loop: {e}")
            # Handle global errors if necessary, though user-specific errors are handled above

        return all_tweets


    def tg_sender(self, data):
        """Sends new tweets to Telegram and updates MongoDB."""
        try:
            for d in data:
                for user, tweets in d.items():
                    if not isinstance(tweets, list):  
                        print(f"Skipping invalid data for {user}: {tweets}")
                        continue
                    
                    ids = {tweet["ID"] for tweet in tweets}  # Use set for uniqueness
                    existing_user = self.collection.find_one({"user": user}, {"tweet_ids": 1})
                    existing_ids = set(existing_user["tweet_ids"]) if existing_user and "tweet_ids" in existing_user else set()
                    unique_new_ids = sorted(ids - existing_ids)  # Ensure only truly new IDs

                    if unique_new_ids:
                        for unique_id in unique_new_ids:
                            try:
                                unique_tweet = next((t for t in tweets if t["ID"] == unique_id), None)
                                if not unique_tweet:
                                    print(f"Tweet ID {unique_id} not found for {user}. Skipping.")
                                    continue
                                
                                message = f"""{formatting.mbold(' 🎉 New Tweet from')} [{formatting.escape_markdown(user)}]({unique_tweet["URL"]})\n\n{"💬 " if unique_tweet["TEXT"].startswith("@") else "🐦 "}{formatting.escape_markdown(unique_tweet["TEXT"])}\n\n{formatting.mbold("📅 Date: ")}{formatting.escape_markdown(str(unique_tweet["TIME"]))}"""
                                
                                if self.report(message):
                                    print(f"Sent tweet {unique_id} for user {user}")
                                    self.collection.find_one_and_update(
                                        {"user": user},
                                        {"$addToSet": {"tweet_ids": unique_id}},
                                        upsert=True
                                    )
                            except Exception as e:
                                print(f"Final Error processing tweet ID {unique_id} for user {user}: {e}")
                    else:
                        print(f"No new tweets for {user}.")
        except Exception as e:
            print(f"General processing error: {e}")
