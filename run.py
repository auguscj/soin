import sqlite3
import time
from datetime import datetime,timedelta
from config import coin_detail_url,logging
coin_detail = coin_detail_url
from getprice import get_price

def check_time_difference():
    # 连接到SQLite数据库
    conn = sqlite3.connect('coins.db')
    cursor = conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL;")
    conn.commit()

    while True:
        current_time_seconds = datetime.now()
        # 查找出发现5分钟后时间的币，超过5分钟就不管了
        ten_minutes_ago = current_time_seconds - timedelta(minutes=5)
        ten_minutes_ago_str = ten_minutes_ago.strftime('%Y-%m-%d %H:%M')
        cursor.execute(f"SELECT found_time,mint,bonding_curveKey FROM coins where if_done='no' and found_time>'{ten_minutes_ago_str}'")
        results = cursor.fetchall()
        for result in results:
            logging.error(f"begin to get {result[1]} price")
            stored_time_str = result[0]
            mint = result[1]
            bondingCurveKey = result[2]
            try:
                time_format = '%Y-%m-%d %H:%M'
                stored_time_seconds = datetime.strptime(stored_time_str, time_format)
                # 计算时间差（这里以秒为单位计算5分钟和10分钟的差值）
                # 如果当前时间比存储的时间大4-5分钟或者9-10分钟，则抓取一次币值
                four_minutes_seconds = 2 * 55
                five_minutes_seconds = 3 * 60
                nine_minutes_seconds = 4 * 55
                ten_minutes_seconds = 5 * 60
                time_diff = current_time_seconds - stored_time_seconds
                seconds_difference = time_diff.total_seconds()
                if seconds_difference >= four_minutes_seconds and  seconds_difference <= five_minutes_seconds:
                    try:
                        price_dic = get_price(mint,bondingCurveKey)
                        price = price_dic['price']
                        logging.error("get two minute price done")
                        if price_dic['type']=="outside":
                            continue
                    except:
                        time.sleep(2)
                        continue

                    sql = f"update coins set five_min_cap='{price}' where mint='{mint}'"
                    cursor.execute(sql)
                    conn.commit()

                if seconds_difference >= nine_minutes_seconds and  seconds_difference <= ten_minutes_seconds:
                    try:
                        price_dic = get_price(mint, bondingCurveKey)
                        price = price_dic['price']
                        logging.error("get five minute price done")
                        if price_dic['type'] == "outside":
                            continue
                    except:
                        time.sleep(2)
                        continue

                    sql = f"update coins set ten_min_cap='{price}', if_done='yes' where mint='{mint}'"
                    cursor.execute(sql)
                    conn.commit()


            except Exception as e:
                logging.error(f"get price exception:{e}")


            logging.error("\n")
        time.sleep(50)  # 每分钟检查一次，可根据需求调整

    conn.close()

if __name__ == '__main__':
    check_time_difference()