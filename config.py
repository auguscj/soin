coin_detail_url = 'https://frontend-api-v2.pump.fun/coins/mint'
coin_creator = 'https://frontend-api-v2.pump.fun/coins/user-created-coins/creator?offset=0&limit=10&includeNsfw=false'
pump_uri = "wss://pumpportal.fun/api/data"
import logging
logging.basicConfig(filename='coin.log', filemode='a', format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

bad_website_suffix = ['vip','top','teach','net']