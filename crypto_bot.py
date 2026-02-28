import requests
import time
import json
from datetime import datetime

# CONFIG
TELEGRAM_TOKEN = "8298660046:AAExiv5EiEWZHR8JOleCx6gIBQBq0rM_PlQ"
CHAT_ID = "8272607717"
CHECK_INTERVAL = 3600  # Check every hour

# Track already alerted coins so we don't spam
alerted_coins = set()

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Telegram error: {e}")

def get_l2_coins():
    """Fetch coins from CoinGecko with L2/layer-2 related categories"""
    url = "https://api.coingecko.com/api/v3/coins/markets"
    params = {
        "vs_currency": "usd",
        "category": "layer-2",
        "order": "volume_desc",
        "per_page": 50,
        "page": 1,
        "sparkline": False,
        "price_change_percentage": "24h,7d"
    }
    try:
        r = requests.get(url, params=params, timeout=10)
        return r.json() if r.status_code == 200 else []
    except:
        return []

def get_coin_details(coin_id):
    """Get detailed info about a specific coin"""
    url = f"https://api.coingecko.com/api/v3/coins/{coin_id}"
    params = {
        "localization": False,
        "tickers": False,
        "market_data": True,
        "community_data": True,
        "developer_data": True
    }
    try:
        r = requests.get(url, params=params, timeout=10)
        return r.json() if r.status_code == 200 else None
    except:
        return None

def score_coin(coin, details):
    """
    Score a coin based on utility signals.
    Returns (score, reasons) tuple.
    Higher score = more interesting.
    """
    score = 0
    reasons = []

    # --- Market cap: sweet spot for growth potential ---
    market_cap = coin.get("market_cap", 0)
    if 10_000_000 < market_cap < 500_000_000:
        score += 2
        reasons.append(f"✅ Sweet spot market cap (${market_cap:,.0f}) — room to grow")
    elif market_cap < 10_000_000:
        score -= 1  # Too small, risky
    
    # --- Volume to market cap ratio (healthy trading activity) ---
    volume = coin.get("total_volume", 0)
    if market_cap > 0:
        vol_ratio = volume / market_cap
        if vol_ratio > 0.1:
            score += 2
            reasons.append(f"✅ Strong volume/mcap ratio ({vol_ratio:.2f}) — active trading")
        elif vol_ratio < 0.01:
            score -= 1
            reasons.append(f"⚠️ Low volume/mcap ratio ({vol_ratio:.2f}) — low interest")

    # --- Price momentum ---
    change_24h = coin.get("price_change_percentage_24h", 0) or 0
    change_7d = coin.get("price_change_percentage_7d_in_currency", 0) or 0
    
    if 5 < change_24h < 30:
        score += 1
        reasons.append(f"✅ Healthy 24h gain ({change_24h:.1f}%) — not overheated")
    elif change_24h > 50:
        score -= 1
        reasons.append(f"⚠️ Possibly overheated 24h gain ({change_24h:.1f}%)")
    
    if change_7d > 10:
        score += 1
        reasons.append(f"✅ Strong 7d momentum ({change_7d:.1f}%)")

    if details:
        # --- Developer activity ---
        dev_data = details.get("developer_data", {})
        commits = dev_data.get("commit_count_4_weeks", 0) or 0
        if commits > 50:
            score += 2
            reasons.append(f"✅ Active development ({commits} commits in 4 weeks)")
        elif commits > 10:
            score += 1
            reasons.append(f"✅ Some development activity ({commits} commits in 4 weeks)")
        elif commits == 0:
            score -= 2
            reasons.append(f"🚨 No development activity — dead project risk")

        # --- Community activity ---
        community = details.get("community_data", {})
        twitter_followers = community.get("twitter_followers", 0) or 0
        reddit_subscribers = community.get("reddit_subscribers", 0) or 0
        
        if twitter_followers > 50_000:
            score += 1
            reasons.append(f"✅ Strong Twitter following ({twitter_followers:,})")
        
        if reddit_subscribers > 5_000:
            score += 1
            reasons.append(f"✅ Active Reddit community ({reddit_subscribers:,} subscribers)")

        # --- Check description for utility keywords ---
        desc = details.get("description", {}).get("en", "").lower()
        utility_keywords = ["defi", "dex", "bridge", "gaming", "nft marketplace", 
                           "lending", "yield", "staking", "payments", "real world"]
        found_keywords = [kw for kw in utility_keywords if kw in desc]
        if len(found_keywords) >= 2:
            score += 2
            reasons.append(f"✅ Real utility: {', '.join(found_keywords[:3])}")
        elif len(found_keywords) == 1:
            score += 1
            reasons.append(f"✅ Some utility focus: {found_keywords[0]}")

        # --- ATH distance (not already pumped to ATH) ---
        ath_change = details.get("market_data", {}).get("ath_change_percentage", {}).get("usd", 0) or 0
        if ath_change < -50:
            score += 1
            reasons.append(f"✅ Far from ATH ({ath_change:.0f}%) — potential upside")
        elif ath_change > -10:
            score -= 1
            reasons.append(f"⚠️ Near ATH ({ath_change:.0f}%) — limited upside?")

    return score, reasons

def format_alert(coin, details, score, reasons):
    name = coin.get("name", "Unknown")
    symbol = coin.get("symbol", "?").upper()
    price = coin.get("current_price", 0)
    market_cap = coin.get("market_cap", 0)
    change_24h = coin.get("price_change_percentage_24h", 0) or 0
    change_7d = coin.get("price_change_percentage_7d_in_currency", 0) or 0

    desc = ""
    if details:
        full_desc = details.get("description", {}).get("en", "")
        desc = full_desc[:300] + "..." if len(full_desc) > 300 else full_desc
        desc = desc.replace("*", "").replace("_", "")

    message = f"""🚨 *L2 OPPORTUNITY FOUND* 🚨

*{name} (${symbol})*
💰 Price: ${price:,.4f}
📊 Market Cap: ${market_cap:,.0f}
📈 24h: {change_24h:+.1f}% | 7d: {change_7d:+.1f}%
⭐ Score: {score}/10

*Why it looks good:*
{chr(10).join(reasons)}

*What it does:*
{desc if desc else 'No description available.'}

🔍 Research more: https://www.coingecko.com/en/coins/{coin.get('id', '')}

_Always DYOR. This is not financial advice._
"""
    return message

def run():
    print(f"[{datetime.now()}] Bot started. Checking every {CHECK_INTERVAL//60} minutes.")
    send_telegram("🤖 *Crypto L2 Bot is live!*\nI'll message you when I find a promising L2 utility coin. Checking every hour.")
    
    while True:
        print(f"[{datetime.now()}] Scanning L2 coins...")
        coins = get_l2_coins()
        
        if not coins:
            print("No coins returned, will retry next cycle.")
        
        for coin in coins:
            coin_id = coin.get("id")
            if coin_id in alerted_coins:
                continue
            
            # Get detailed data
            details = get_coin_details(coin_id)
            time.sleep(1.5)  # Respect rate limits
            
            score, reasons = score_coin(coin, details)
            
            print(f"  {coin.get('name')}: score={score}")
            
            if score >= 6:  # Only alert on strong signals
                print(f"  → ALERTING on {coin.get('name')} (score={score})")
                message = format_alert(coin, details, score, reasons)
                send_telegram(message)
                alerted_coins.add(coin_id)
        
        print(f"[{datetime.now()}] Scan complete. Sleeping for {CHECK_INTERVAL//60} minutes...")
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    run()
