import asyncio
import cloudscraper
import json
import time
from loguru import logger
import requests
from colorama import Fore, Back, Style, init
from datetime import datetime, timedelta

init(autoreset=True)

print("\n" + " " * 16 + f"{Fore.CYAN}Base Code Credit @Kishan2930{Style.RESET_ALL}")
print(Fore.MAGENTA + "Running Nodepay Directly From Your IP..." + Style.RESET_ALL)

def truncate_token(token):
    return f"{token[:5]}--{token[-5:]}"

logger.remove()
logger.add(lambda msg: print(msg, end=''), format="{message}", level="INFO")

PING_INTERVAL = 15
RETRIES = 10
PING_DURATION = 1800  # 30 minutes in seconds

DOMAIN_API = {
    "SESSION": "http://api.nodepay.ai/api/auth/session",
    "PING": [
        "https://nw.nodepay.org/api/network/ping"
    ],
    "EARN_INFO": "https://api.nodepay.ai/api/earn/info",
    "MISSION": "https://api.nodepay.ai/api/mission?platform=MOBILE",
    "COMPLETE_MISSION": "https://api.nodepay.ai/api/mission/complete-mission"
}

CONNECTION_STATES = {
    "CONNECTED": 1,
    "DISCONNECTED": 2,
    "NONE_CONNECTION": 3
}

scraper = cloudscraper.create_scraper(
    browser={
        'browser': 'chrome',
        'platform': 'windows',
        'desktop': True
    }
)

class AccountData:
    def __init__(self, token, index):
        self.token = token
        self.index = index
        self.status_connect = CONNECTION_STATES["NONE_CONNECTION"]
        self.account_info = {}
        self.retries = 0
        self.last_ping_status = 'Waiting...'
        self.browser_ids = [
            {
                'ping_count': 0,
                'successful_pings': 0,
                'score': 0,
                'start_time': time.time(),
                'last_ping_time': None
            }
        ]

    def reset(self):
        self.status_connect = CONNECTION_STATES["NONE_CONNECTION"]
        self.account_info = {}
        self.retries = 3

async def retrieve_tokens():
    try:
        with open('tokens.txt', 'r') as file:
            tokens = file.read().splitlines()
        return tokens
    except Exception as e:
        logger.error(f"{Fore.RED}Failed to load tokens: {e}{Style.RESET_ALL}")
        raise SystemExit("Exiting due to failure in loading tokens")

async def execute_request(url, data, account, method="POST"):
    headers = {
        "Authorization": f"Bearer {account.token}",
        "Content-Type": "application/json",
    }
    
    if url == DOMAIN_API["EARN_INFO"] or url == DOMAIN_API["MISSION"] or url == DOMAIN_API["COMPLETE_MISSION"]:
        headers.update({
            "user-agent": "1.2.6+12 (Android 10; Nexus; unknown)",
            "accept-encoding": "gzip",
            "Host": "api.nodepay.ai"
        })
    elif url in DOMAIN_API["PING"]:
        headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://app.nodepay.ai/",
            "Accept": "application/json, text/plain, */*",
            "Origin": "chrome-extension://lgmpfmgeabnnlemejacfljbmonaomfmm",
            "Sec-Ch-Ua": '"Chromium";v="130", "Google Chrome";v="130", "Not?A_Brand";v="99"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "cors-site"
        })
    
    if method == "POST":
        headers["content-length"] = str(len(json.dumps(data)))

    try:
        if method == "GET":
            response = scraper.get(url, headers=headers, timeout=60)
        else:
            response = scraper.post(url, json=data, headers=headers, timeout=60)
        response.raise_for_status()
    except Exception as e:
        logger.error(f"{Fore.RED}Error during API call for token {truncate_token(account.token)}: {e}{Style.RESET_ALL}")
        raise ValueError(f"Failed API call to {url}")

    return response.json()

async def fetch_earning_info(account):
    try:
        response = await execute_request(DOMAIN_API["EARN_INFO"], {}, account, method="GET")
        if response['success']:
            data = response['data']
            logger.info(f"{Fore.CYAN}[{time.strftime('%H:%M:%S')}][{account.index}]{Style.RESET_ALL} Status Of {Fore.YELLOW}{data['season_name']}{Style.RESET_ALL}")
            logger.info(f"{Fore.GREEN}Total Earning: {Style.RESET_ALL}{Fore.YELLOW}{data['total_earning']}{Style.RESET_ALL}")
            logger.info(f"{Fore.GREEN}Today's Earning: {Style.RESET_ALL}{Fore.YELLOW}{data['today_earning']}{Style.RESET_ALL}")
            logger.info(f"{Fore.GREEN}Current point: {Style.RESET_ALL}{Fore.YELLOW}{data['current_point']}{Style.RESET_ALL}")
            logger.info(f"{Fore.GREEN}Pending point: {Style.RESET_ALL}{Fore.YELLOW}{data['pending_point']}{Style.RESET_ALL}")
        else:
            logger.error(f"{Fore.RED}Failed to fetch earning info: {response}{Style.RESET_ALL}")
    except Exception as e:
        logger.error(f"{Fore.RED}Error fetching earning info: {e}{Style.RESET_ALL}")

async def check_and_claim_rewards(account):
    try:
        response = await execute_request(DOMAIN_API["MISSION"], {}, account, method="GET")
        data = response.get('data', [])
        
        logger.info(f"{Fore.CYAN}Checking rewards for account {account.index}{Style.RESET_ALL}")
        
        for item in data:
            if item['id'] == "1":  # Daily Reward
                await process_daily_reward(account, item)
            elif item['id'] == "19":  # Hourly Reward (Mobile Resource)
                await process_hourly_reward(account, item)

    except Exception as e:
        logger.error(f"{Fore.RED}Error checking rewards: {e}{Style.RESET_ALL}")

async def process_daily_reward(account, reward_data):
    if reward_data.get('status') == "AVAILABLE":
        logger.info(f"{Fore.GREEN}Daily Reward is available. Attempting to claim.{Style.RESET_ALL}")
        await claim_reward(account, reward_data['id'], "Daily")
    elif reward_data.get('status') == "LOCK":
        logger.info(f"{Fore.YELLOW}Daily Reward has already been claimed today.{Style.RESET_ALL}")
    else:
        remain_time = reward_data.get('remain_time', 0) / 1000  # Convert to seconds
        logger.info(f"{Fore.YELLOW}Daily Reward will be available in {timedelta(seconds=remain_time)}{Style.RESET_ALL}")

async def process_hourly_reward(account, reward_data):
    current_process = reward_data.get('current_process', 0)
    target_process = reward_data.get('target_process', 1)
    
    if current_process >= 6:
        logger.info(f"{Fore.GREEN}Hourly Reward is ready to claim. Progress: {current_process}/{target_process}{Style.RESET_ALL}")
        await claim_reward(account, reward_data['id'], "Hourly")
    else:
        logger.info(f"{Fore.YELLOW}Hourly Reward not ready yet. Progress: {current_process}/{target_process}{Style.RESET_ALL}")

async def claim_reward(account, mission_id, reward_type):
    try:
        data = {"mission_id": str(mission_id)}
        response = await execute_request(DOMAIN_API["COMPLETE_MISSION"], data, account)
        if response.get('success'):
            earned_points = response['data']['earned_points']
            logger.info(f"{Fore.GREEN}{reward_type} Reward Claimed: {earned_points} points{Style.RESET_ALL}")
        else:
            logger.error(f"{Fore.RED}Failed to claim {reward_type} reward: {response}{Style.RESET_ALL}")
    except Exception as e:
        logger.error(f"{Fore.RED}Error claiming {reward_type} reward: {e}{Style.RESET_ALL}")

async def perform_ping(account):
    current_time = time.time()
    logger.info(f"{Fore.CYAN}[{time.strftime('%H:%M:%S')}][{account.index}]{Style.RESET_ALL} Attempting to send ping for token {Fore.CYAN}{truncate_token(account.token)}{Style.RESET_ALL}")

    if account.browser_ids[0]['last_ping_time'] and (current_time - account.browser_ids[0]['last_ping_time']) < PING_INTERVAL:
        logger.info(f"{Fore.YELLOW}Woah there! Not enough time has elapsed.{Style.RESET_ALL}")
        return

    account.browser_ids[0]['last_ping_time'] = current_time

    for url in DOMAIN_API["PING"]:
        try:
            data = {
                "id": account.account_info.get("uid"),
                "browser_id": account.browser_ids[0],
                "timestamp": int(time.time())
            }
            response = await execute_request(url, data, account)
            ping_result, network_quality = "success" if response["code"] == 0 else "failed", response.get("data", {}).get("ip_score", "N/A")

            if ping_result == "success":
                logger.info(f"{Fore.CYAN}[{time.strftime('%H:%M:%S')}][{account.index}]{Style.RESET_ALL} Ping {Fore.GREEN}{ping_result}{Style.RESET_ALL} from {Fore.CYAN}{truncate_token(account.token)}{Style.RESET_ALL}, Network Quality: {Fore.GREEN}{network_quality}{Style.RESET_ALL}")
                account.browser_ids[0]['successful_pings'] += 1
                return
            else:
                logger.warning(f"{Fore.RED}Ping {ping_result}{Style.RESET_ALL} for token {truncate_token(account.token)}")

        except Exception as e:
            logger.error(f"{Fore.RED}Ping failed for token {truncate_token(account.token)}: {e}{Style.RESET_ALL}")

async def collect_profile_info(account):
    try:
        response = await execute_request(DOMAIN_API["SESSION"], {}, account)
        if response.get("success"):
            account.account_info = response["data"]
            data = account.account_info
            logger.info(f"{Fore.CYAN}Account Info for {Fore.YELLOW}{data['name']}{Fore.CYAN} :{Style.RESET_ALL}")
            logger.info(f"{Fore.GREEN}Email: {Fore.YELLOW}{data['email']}{Style.RESET_ALL}")
            logger.info(f"{Fore.GREEN}Referral Link: {Fore.YELLOW}{data['referral_link']}{Style.RESET_ALL}")
            logger.info(f"{Fore.GREEN}State: {Fore.YELLOW}{data['state']}{Style.RESET_ALL}")
            logger.info(f"{Fore.GREEN}Network Earning Rate: {Fore.YELLOW}{data['network_earning_rate']}{Style.RESET_ALL}")
            #logger.info(f"{Fore.GREEN}Total Balance: {Fore.YELLOW}{data['balance']['total_collected']}{Style.RESET_ALL}")
            #logger.info(f"{Fore.GREEN}Current Balance: {Fore.YELLOW}{data['balance']['current_amount']}{Style.RESET_ALL}")
            
            if account.account_info.get("uid"):
                await fetch_earning_info(account)
                await check_and_claim_rewards(account)
        else:
            logger.warning(f"{Fore.RED}Session failed for token {truncate_token(account.token)}{Style.RESET_ALL}")
    except Exception as e:
        logger.error(f"{Fore.RED}Failed to collect profile info for token {truncate_token(account.token)}: {e}{Style.RESET_ALL}")

async def process_account(account):
    await collect_profile_info(account)

async def ping_all_accounts(accounts):
    start_time = time.time()
    while time.time() - start_time < PING_DURATION:
        ping_tasks = [perform_ping(account) for account in accounts]
        await asyncio.gather(*ping_tasks)
        await asyncio.sleep(PING_INTERVAL)

async def main():
    tokens = await retrieve_tokens()
    accounts = [AccountData(token, index) for index, token in enumerate(tokens, start=1)]

    while True:
        # Process all accounts for rewards
        tasks = [process_account(account) for account in accounts]
        await asyncio.gather(*tasks)

        # Perform pinging for all accounts for 30 minutes
        await ping_all_accounts(accounts)

        # Sleep for a short duration before starting the next cycle
        await asyncio.sleep(60)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info(f"{Fore.YELLOW}Program terminated by user.{Style.RESET_ALL}")
        tasks = asyncio.all_tasks()
        for task in tasks:
            task.cancel()
        asyncio.get_event_loop().run_until_complete(asyncio.gather(*tasks, return_exceptions=True))
        asyncio.get_event_loop().close()


