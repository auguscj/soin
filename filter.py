import requests
from config import coin_detail_url,coin_creator,logging,bad_website_suffix,bad_domains,duplicate_domains,twitter_check_url
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from collections import deque
import sqlite3
from urllib.parse import urlparse
from collections import Counter
import json

def website_format(website):
    website = website.replace("https://", "")
    website = website.replace("http://", "")
    clean_domain = website.split('/')[0] # final format like www.xx.com xx.io ....
    return clean_domain


def base_filter(twitter,website):
    #过滤双空网站
    if twitter=="None" and website=="None":
        return False

    #如果twitter网站不标准
    if twitter!="None" or twitter!="":
        if "x.com" not in twitter:
            return False

    #过滤一些后缀的网站
    website = website_format(website)
    if website in duplicate_domains:
        return False

    domain_end = website.split(".")[-1]
    if domain_end in bad_website_suffix:
        return False

    # 过滤非顶级一级二级域名
    if website.count('.') > 2:
        return False

    # 过滤掉一些著名网站
    for bad_domain in bad_domains:
        if bad_domain in website:
            return False

    return True



def find_duplicate_domain():
    conn = sqlite3.connect('coins.db')
    cursor = conn.cursor()
    cursor.execute('SELECT website FROM coins')
    websites = cursor.fetchall()

    # 提取域名部分并统计出现次数
    domain_counts = Counter(urlparse(website[0]).netloc for website in websites)

    # 筛选出出现次数大于1的域名
    duplicate_domains = {domain for domain, count in domain_counts.items() if count > 1}
    return duplicate_domains




def coin_filter(mint):
    try:
        coin_detail_response = requests.get(coin_detail_url.replace('mint', mint))
    except:
        return False
    coin_detail_json = coin_detail_response.json()
    creator = coin_detail_json['creator']
    twitter = coin_detail_json['twitter']
    telegram = coin_detail_json['telegram']
    website = coin_detail_json['website']
    usd_market_cap = coin_detail_json['usd_market_cap']
    # 条件1 twitter website telegram 只要有一个值为空就pass掉
    if not bool(website) or not bool(twitter):
        return False, 0

    if 'x.com' not in twitter:
        return False, 0

    # if 't.me' not in telegram:
    #     return False,0

    if "." not in website:
        return False, 0

    # 条件2， 判断网站是不是io或者com的，并且要是二级域名以下
    if not filter_website(website):
        logging.error(f"website not in whitelist {website}")
        return False, 0

    # 条件3 判断发币次数是否大于1
    if not filter_creator(creator):
        logging.error(f"creator create coin more than 1 {creator}")
        return False, 0

    # 条件4 爬取网站，看看网站的内容和深度
    # 爬取网站
    result = crawl_website(website)
    print(f"webstde crawl result{website} {str(result)}")
    # result['max_depth']
    # result['total_pages']
    # result['unique_urls']

    return True, usd_market_cap


def filter_website(website):
    # 判断是否是io或者com域名
    website = website.replace("https://", "")
    website = website.replace("http://", "")
    clean_domain = website.split('/')[0]
    if clean_domain.endswith('.com') or clean_domain.endswith('.io'):
        # 判断是否是顶级，一级或者二级域名
        if website.count('.') < 3:
            # 过滤掉一些完整
            for bad_domain in bad_domains:
                if bad_domain in website:
                    return False
            return True
        return False
    else:
        return False


def filter_creator(creator):
    url = coin_creator.replace('creator', creator)
    response = requests.get(url)
    result = response.json()
    if len(result) > 1:
        return False
    else:
        return True


def is_valid_url(url):
    """Check if a URL is valid and belongs to the same domain."""
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)

def check_twitter(twitter,mint):
    twitter_checker_url = twitter_check_url.replace("twitter",twitter)
    response = requests.get(twitter_checker_url)
    data = response.json()

    # 初始化一个集合来存储已经出现过的token_address
    seen_token_addresses = set()
    seen_token_addresses.add(mint)

    if data.get('data') is not None and data['data'].get('tweets') is not None:
        for tweet in data['data']['tweets']:
            token_address = tweet['token_address']
            # 如果有一个mint地址跟mint地址不一样，说明有删推过
            if token_address not in seen_token_addresses:
                return False
        return True
    else:#说明twitter不存在币的mint地址
        return False


def crawl_website(start_url, max_depth=3):
    """Crawl a website and determine its depth and page count.
    Args:
        start_url (str): The starting URL of the website.
        max_depth (int): Maximum depth to crawl.
    Returns:
        dict: A dictionary with depth, total pages, and unique URLs.
    """
    visited = set()  # To track visited URLs
    queue = deque([(start_url, 0)])  # Queue for BFS with (url, depth)
    max_reached_depth = 0
    page_count = 0

    while queue:
        url, depth = queue.popleft()

        if depth > max_depth or url in visited:
            continue

        try:
            response = requests.get(url, timeout=5)
            if response.status_code != 200:
                continue

            visited.add(url)
            page_count += 1
            max_reached_depth = max(max_reached_depth, depth)

            soup = BeautifulSoup(response.text, "html.parser")
            for a_tag in soup.find_all("a", href=True):
                next_url = urljoin(url, a_tag["href"])
                print(a_tag["href"])
                if 'github.com' in a_tag["href"]:
                    print("found github")
                if is_valid_url(next_url) and urlparse(next_url).netloc == urlparse(start_url).netloc:
                    queue.append((next_url, depth + 1))

        except Exception as e:
            print(f"Error accessing {url}: {e}")

    return {
        "max_depth": max_reached_depth,
        "total_pages": page_count,
        "unique_urls": len(visited),
    }
