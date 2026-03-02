# 🛡️ Sngre: Emergency & News Monitor (Twitter to Telegram)

An automated Python-based intelligence and filtering system. This bot monitors multiple security and emergency Twitter accounts, filters content based on specific risk keywords (wildfires, earthquakes, floods, etc.), and dispatches real-time alerts to a Telegram channel.



## 🚀 Key Features

* 📡 **Multi-Source Tracking:** Simultaneously monitors a list of official accounts (e.g., @EmergenciasEc, @segura_ep, @ECU911_, etc.).
* 🧠 **Smart Keyword Filtering:** Analyzes tweet text and only reports if it matches pre-defined risk categories (Floods, Fires, Earthquakes, Tsunamis).
* ⚡ **Serverless & Lightweight:** Runs 100% on the cloud via **GitHub Actions** (No private server or 24/7 PC required).
* 🔗 **Clean Link Previews:** Sends direct `x.com` URLs, allowing Telegram to automatically generate high-quality rich previews with images and videos.
* 💾 **State Memory:** Uses a local tracking system (`last_id.txt`) to prevent duplicate notifications and spam.

## 🛠️ How It Works

The bot follows a precise logic flow every 5-10 minutes:
1. **Trigger:** GitHub Actions wakes up the bot based on the repository's cron schedule.
2. **Scrape:** It queries RSS feeds through resilient Nitter instances to bypass Twitter API restrictions.
3. **Analyze:** The "Smart Filter" engine scans the text against the emergency dictionary.
4. **Alert:** If a new relevant tweet is found, it is pushed immediately to the Telegram API.

## ⚙️ Environment Configuration (Secrets)

To run this bot, you must configure the following **Secrets** in your GitHub repository (**Settings > Secrets and variables > Actions**):

| Secret | Description |
| --- | --- |
| `TELEGRAM_TOKEN` | Your Bot Token provided by [@BotFather](https://t.me/BotFather) |
| `TELEGRAM_TO` | Your Channel ID (e.g., `-100...`) or the public `@username` |

## 🚀 Installation & Deployment

1. **Clone the repository:**
   ```bash
   git clone [https://github.com/YOUR_USERNAME/YOUR_REPO.git](https://github.com/YOUR_USERNAME/YOUR_REPO.git)
