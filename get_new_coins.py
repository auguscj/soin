import asyncio
from config import pump_uri,coin_detail_url,coin_creator,logging
import aiohttp
import websockets
import json
import requests
import time
import sqlite3
from datetime import datetime
import aiosqlite
# from getprice import get_price
from filter import base_filter

conn = sqlite3.connect('coins.db')
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS coins
             (coin_name text, mint text, found_time text,init_cap real, five_min_cap real, ten_min_cap real,creator text,website text,telegram text,twitter text,if_done text)''')


async def subscribe():
    async with aiosqlite.connect("coins.db") as db:
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with websockets.connect(pump_uri) as websocket:
                payload = {
                    "method": "subscribeNewToken",
                }
                await websocket.send(json.dumps(payload))
                async for message in websocket:
                    result = json.loads(message)
                    logging.error(f"Begin to get {result}")
                    await extract_coin_detail_from_message(result,session,db)

async def fetch_json(session,url,url_type="pump"):
    try:
        async with session.get(url) as response:
            if url_type=="pump":
                if response.statusCode==200:
                    return await response.json()
                else:
                    logging.error(f"Fail to fetch {url},status:{response}")
            else:
                if response.status==200:
                    return await response.json()
                else:
                    logging.error(f"Fail to fetch {url},status:{response}")
    except Exception as e:
        logging.error(f"Error fetching {url}:{e}")
    return None


def extract_values(json_obj, keys_to_find):
    results = {key: None for key in keys_to_find}  # 初始化所有键为 None

    def _recursive_search(obj):
        if isinstance(obj, dict):  # 如果是字典
            for key, value in obj.items():
                if key in keys_to_find:  # 如果键匹配
                    results[key] = value
                if isinstance(value, (dict, list)):  # 如果值是嵌套字典或列表，继续递归
                    _recursive_search(value)
        elif isinstance(obj, list):  # 如果是列表
            for item in obj:
                _recursive_search(item)

    _recursive_search(json_obj)
    return results

async def extract_coin_detail_from_message(pump_message,session,db):
    try:

        logging.error(f"Begin to extract_coin_detail_from_message {pump_message['mint']}")
        ipfs_uri = pump_message['uri']
        mint = pump_message['mint']
        coin_name = pump_message['symbol']
        creator = pump_message['traderPublicKey']
        vSolInBondingCurve = pump_message['vSolInBondingCurve']
        vTokensInBondingCurve = pump_message['vTokensInBondingCurve']

        current_price = f"{(vSolInBondingCurve / vTokensInBondingCurve):.10f}"
        pump_url = coin_detail_url.replace('mint', mint)
        coin_detail_json = await fetch_json(session,pump_url)
        website = None
        telegram = None
        twitter = None
        if coin_detail_json and coin_detail_json:
            logging.error(f"success call api {pump_url}")
            # creator = coin_detail_json['creator']
            twitter = coin_detail_json['twitter']
            telegram = coin_detail_json['telegram']
            website = coin_detail_json['website']
        else:
            coin_detail_json = await fetch_json(session, ipfs_uri,"ifps")
            if coin_detail_json:
                logging.error(f"pump api fail, success call api {ipfs_uri}: {coin_detail_json}")
                keys = {"website", "twitter", "telegram"}
                found_value = extract_values(coin_detail_json,keys)
                website = found_value['website']
                twitter = found_value['twitter']
                telegram = found_value['telegram']
            else:
                logging.error("Both pump/ifps api call fail,ignore current coin")
                logging.error("\n")
                return False
        # bondingCurveKey = pump_message['bondingCurveKey']
        # price_dic = await get_price(mint,bondingCurveKey)
        # price = price_dic['price']
        now = datetime.now()
        current_time = now.strftime('%Y-%m-%d %H:%M')

        filter_result = base_filter(twitter,website)
        if filter_result:
            sql = f"INSERT INTO coins VALUES ('{coin_name}', '{mint}', '{current_time}', '{current_price}', 0.0,0.0,'{creator}','{website}','{telegram}','{twitter}','no')"
            logging.error(sql)
            await db.execute(sql)
            await  db.commit()
            logging.error(f" extract_coin_detail_from_message finish ")
        else:
            logging.error(f"{mint} {website} {twitter} didn't pass filter")
    except KeyError:
        pass
    except Exception as e:
        logging.error(f"extract_coin_detail_from_message error:{e}")

    logging.error("\n")



if __name__=="__main__":
    while True:
        try:
            asyncio.get_event_loop().run_until_complete(subscribe())  # 尝试运行函数
        except Exception as e:
            logging.error(str(e),exc_info=True)
            time.sleep(10)








