import requests
import pandas as pd
import json
from datetime import datetime, timedelta

class CoinFilter:
    def __init__(self, config_file="config.json"):
        # Load configuration
        with open(config_file, "r") as f:
            self.config = json.load(f)
        
        self.pumpfun_url = self.config["api_endpoints"]["pumpfun"]
        self.dexscreener_url = self.config["api_endpoints"]["dexscreener"]
        self.gmgn_ai_url = self.config["api_endpoints"]["gmgn_ai"]
        self.rocker_universe_url = self.config["api_endpoints"]["rocker_universe"]
        self.rugcheck_url = self.config["api_endpoints"]["rugcheck"]
        self.tweetscout_url = self.config["api_endpoints"]["tweetscout"]
        
        self.filters = self.config["filters"]
        self.blacklist = self.config["blacklist"]
        self.use_rocker_api = self.config["volume_check"]["use_rocker_api"]
        self.coins_data = []

    # Step 1: PumpFun Integration
    def fetch_pumpfun_coins(self):
        print("Fetching data from PumpFun...")
        response = requests.get(self.pumpfun_url)
        if response.status_code == 200:
            self.coins_data = response.json()
            print(f"Fetched {len(self.coins_data)} coins.")
            return self.analyze_pumpfun_data()
        else:
            raise Exception(f"Failed to fetch data from PumpFun: {response.status_code}")
    
    def analyze_pumpfun_data(self):
        print("Analyzing PumpFun data...")
        migrated_coins = [
            coin for coin in self.coins_data 
            if coin.get("status") == "migrated" and coin["symbol"] not in self.blacklist["memecoins"]
        ]
        print(f"Found {len(migrated_coins)} migrated coins (after memecoin filtering).")
        return migrated_coins

    # Step 2: DexScreener Integration
    def fetch_dexscreener_tokens(self, migrated_coins):
        print("Fetching and filtering tokens from DexScreener...")
        filtered_tokens = []
        for coin in migrated_coins:
            response = requests.get(f"{self.dexscreener_url}/tokens/{coin['id']}")
            if response.status_code == 200:
                token_data = response.json()
                if self.filter_dexscreener_data(token_data, coin["developer"]):
                    if self.verify_volume(token_data) and self.verify_contract(token_data):
                        social_media_status = self.check_social_media(coin["symbol"])
                        token_data["social_media_status"] = social_media_status
                        filtered_tokens.append(token_data)
        print(f"Filtered {len(filtered_tokens)} tokens from DexScreener.")
        return filtered_tokens

    def filter_dexscreener_data(self, token_data, developer_address):
        try:
            pair_age = datetime.now() - datetime.strptime(token_data["pairAge"], "%Y-%m-%dT%H:%M:%S")
            one_hour_txns = token_data.get("oneHourTxns", 0)
            five_min_txns = token_data.get("fiveMinTxns", 0)
            
            return (
                pair_age <= timedelta(hours=self.filters["pair_age_hours"]) and 
                one_hour_txns >= self.filters["min_1h_txns"] and 
                five_min_txns >= self.filters["min_5m_txns"] and 
                developer_address not in self.blacklist["developers"]
            )
        except KeyError:
            return False

    def verify_volume(self, token_data):
        if self.use_rocker_api:
            print(f"Validating volume with Rocker Universe for token {token_data['symbol']}...")
            response = requests.post(self.rocker_universe_url, json={"tokenId": token_data["id"]})
            if response.status_code == 200:
                return response.json().get("isValid", False)
            else:
                print(f"Failed to validate volume for {token_data['symbol']} using Rocker Universe.")
                return False
        else:
            print(f"Validating volume with custom algorithm for token {token_data['symbol']}...")
            return self.custom_volume_check(token_data)
    
    def verify_contract(self, token_data):
        print(f"Checking contract for token {token_data['symbol']} on RugCheck...")
        response = requests.post(self.rugcheck_url, json={"tokenAddress": token_data["contract"]})
        if response.status_code == 200:
            data = response.json()
            if data.get("status") != "Good":
                print(f"Token {token_data['symbol']} failed RugCheck verification.")
                return False
            if data.get("isBundledSupply", False):
                print(f"Token {token_data['symbol']} has a bundled supply. Adding to blacklist.")
                self.blacklist["memecoins"].append(token_data["symbol"])
                self.blacklist["developers"].append(token_data["developer"])
                return False
            return True
        else:
            print(f"Failed to verify contract for {token_data['symbol']} using RugCheck.")
            return False

    def check_social_media(self, token_symbol):
        """
        Check the social media score of the token using TweetScout API.
        - "Good" if score > 450
        - "Medium" if score <= 450
        """
        print(f"Checking social media status for {token_symbol} on TweetScout...")
        response = requests.get(f"{self.tweetscout_url}?symbol={token_symbol}")
        if response.status_code == 200:
            score = response.json().get("score", 0)
            if score > self.filters["tweetscout_score_threshold"]:
                print(f"Token {token_symbol} has a good social media score ({score}).")
                return "Good"
            else:
                print(f"Token {token_symbol} has a medium social media score ({score}).")
                return "Medium"
        else:
            print(f"Failed to check social media status for {token_symbol}.")
            return "Unknown"

    # Step 3: GMGN.ai Integration
    def analyze_gmgn_ai(self, tokens):
        print("Analyzing data from GMGN.ai...")
        analyzed_tokens = []
        for token in tokens:
            response = requests.get(f"{self.gmgn_ai_url}/holders/{token['id']}")
            if response.status_code == 200:
                holder_data = response.json()
                if self.evaluate_holders(holder_data):
                    analyzed_tokens.append(token)
        print(f"Analyzed and filtered {len(analyzed_tokens)} tokens based on GMGN.ai criteria.")
        return analyzed_tokens

    def evaluate_holders(self, holder_data):
        try:
            total_supply = holder_data["totalSupply"]
            top_holders = sum(holder_data["holders"][:5]) / total_supply
            return top_holders < 0.2
        except KeyError:
            return False

    # Master Workflow
    def run(self):
        migrated_coins = self.fetch_pumpfun_coins()
        tokens = self.fetch_dexscreener_tokens(migrated_coins)
        analyzed_tokens = self.analyze_gmgn_ai(tokens)
        print(f"Final filtered tokens: {len(analyzed_tokens)}")
        return analyzed_tokens


if __name__ == "__main__":
    coin_filter = CoinFilter()
    filtered_coins = coin_filter.run()

    # Save results to a CSV
    if filtered_coins:
        pd.DataFrame(filtered_coins).to_csv("filtered_coins.csv", index=False)
        print("Filtered coins saved to 'filtered_coins.csv'")
