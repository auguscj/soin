from typing import Optional
import struct
from dataclasses import dataclass
from solders.pubkey import Pubkey
from construct import Struct, Int64ul, Flag
import requests
from solana.rpc.commitment import  Processed
from solana.rpc.async_api import AsyncClient
from solana.rpc.api import Client
from layouts import (
    LIQUIDITY_STATE_LAYOUT_V4,
    MARKET_STATE_LAYOUT_V3,
    SWAP_LAYOUT,
)
import asyncio
SOL = Pubkey.from_string("So11111111111111111111111111111111111111112")
PUMP_PROGRAM = Pubkey.from_string("6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P")
OPEN_BOOK_PROGRAM = Pubkey.from_string("srmqPvymJeFKQ4zGQed1GFppgkRHL9kaELCbyksJtPX")
RPC_ENDPOINT = "https://sparkling-young-snow.solana-mainnet.quiknode.pro/fb38cc07de75e23fe80a4f803a632c405f5dd49f"
EXPECTED_DISCRIMINATOR = struct.pack("<Q", 6966180631402821399)
LAMPORTS_PER_SOL = 1_000_000_000
TOKEN_DECIMALS = 6
TokenClient = Client(RPC_ENDPOINT)
@dataclass
class PoolKeys:
    amm_id: Pubkey
    base_mint: Pubkey
    quote_mint: Pubkey
    base_decimals: int
    quote_decimals: int
    open_orders: Pubkey
    target_orders: Pubkey
    base_vault: Pubkey
    quote_vault: Pubkey
    market_id: Pubkey
    market_authority: Pubkey
    market_base_vault: Pubkey
    market_quote_vault: Pubkey
    bids: Pubkey
    asks: Pubkey
    event_queue: Pubkey
class BondingCurveState:
    _STRUCT = Struct(
        "virtual_token_reserves" / Int64ul,
        "virtual_sol_reserves" / Int64ul,
        "real_token_reserves" / Int64ul,
        "real_sol_reserves" / Int64ul,
        "token_total_supply" / Int64ul,
        "complete" / Flag
    )
    def __init__(self, data: bytes) -> None:
        parsed = self._STRUCT.parse(data[8:])
        self.__dict__.update(parsed)
async def get_pair_address(mint):
    url = f"https://api-v3.raydium.io/pools/info/mint?mint1={mint}&poolType=all&poolSortField=default&sortType=desc&pageSize=1&page=1"
    try:
        response = requests.get(url)
        response.raise_for_status()  # 如果请求不成功，会抛出异常
        # 打印返回的 JSON 数据
        response_json = response.json()
        # 确保 'data' 和 'data' 下的数组存在
        if 'data' in response_json and 'data' in response_json['data'] and len(response_json['data']['data']) > 0:
            pair_address = response_json['data']['data'][0]['id']
            return pair_address
        else:
            # print("No pair found for this mint address.")
            return None
    except requests.exceptions.RequestException as e:
        print(f"An error occurred: {e}")
        return None
    except Exception as ex:
        print(f"Error extracting data: {ex}")
        return None
def get_bonding_curve_addresses(mint_account: Pubkey):
    bonding_curve, _ = Pubkey.find_program_address(
        [b"bonding-curve", bytes(mint_account)],  # 这里将 mint_account 转换为字节
        PUMP_PROGRAM
    )
    return bonding_curve
async def get_pump_curve_state(curve_address: Pubkey) -> BondingCurveState:
    async with AsyncClient(RPC_ENDPOINT) as client:
        response =  await client.get_account_info_json_parsed(curve_address)
        if not response.value or not response.value.data:
            raise ValueError("Invalid curve state: No data")
        data = response.value.data
        if data[:8] != EXPECTED_DISCRIMINATOR:
            raise ValueError("Invalid curve state discriminator")
        return BondingCurveState(data)
async def calculate_pump_curve_price(curve_state: BondingCurveState) -> float:
        if curve_state.virtual_token_reserves <= 0 or curve_state.virtual_sol_reserves <= 0:
            raise ValueError("Invalid reserve state")
        return (curve_state.virtual_sol_reserves / LAMPORTS_PER_SOL) / (curve_state.virtual_token_reserves / 10 ** TOKEN_DECIMALS)

async def fetch_pool_keys(pair_address: str) -> Optional[PoolKeys]:
    try:
        amm_id = Pubkey.from_string(pair_address)
        amm_data = TokenClient.get_account_info_json_parsed(amm_id, commitment=Processed).value.data
        amm_data_decoded = LIQUIDITY_STATE_LAYOUT_V4.parse(amm_data)
        marketId = Pubkey.from_bytes(amm_data_decoded.serumMarket)
        marketInfo = TokenClient.get_account_info_json_parsed(marketId, commitment=Processed).value.data
        market_decoded = MARKET_STATE_LAYOUT_V3.parse(marketInfo)
        vault_signer_nonce = market_decoded.vault_signer_nonce

        pool_keys = PoolKeys(
            amm_id=amm_id,
            base_mint=Pubkey.from_bytes(market_decoded.base_mint),
            quote_mint=Pubkey.from_bytes(market_decoded.quote_mint),
            base_decimals=amm_data_decoded.coinDecimals,
            quote_decimals=amm_data_decoded.pcDecimals,
            open_orders=Pubkey.from_bytes(amm_data_decoded.ammOpenOrders),
            target_orders=Pubkey.from_bytes(amm_data_decoded.ammTargetOrders),
            base_vault=Pubkey.from_bytes(amm_data_decoded.poolCoinTokenAccount),
            quote_vault=Pubkey.from_bytes(amm_data_decoded.poolPcTokenAccount),
            market_id=marketId,
            market_authority=Pubkey.create_program_address( 
                [bytes(marketId), bytes_of(vault_signer_nonce)],
                OPEN_BOOK_PROGRAM,
            ),
            market_base_vault=Pubkey.from_bytes(market_decoded.base_vault),
            market_quote_vault=Pubkey.from_bytes(market_decoded.quote_vault),
            bids=Pubkey.from_bytes(market_decoded.bids),
            asks=Pubkey.from_bytes(market_decoded.asks),
            event_queue=Pubkey.from_bytes(market_decoded.event_queue),
        )

        return pool_keys
    except Exception as e:
        print(f"Error fetching pool keys: {e}")
        return None
def bytes_of(value):
    if not (0 <= value < 2**64):
        raise ValueError("Value must be in the range of a u64 (0 to 2^64 - 1).")
    return struct.pack('<Q', value)
async def ray_get_token_price(pool_keys: PoolKeys) -> tuple:
        async with AsyncClient(RPC_ENDPOINT) as client:
            try:
                base_vault = pool_keys.base_vault
                quote_vault = pool_keys.quote_vault
                base_decimal = pool_keys.base_decimals
                quote_decimal = pool_keys.quote_decimals
                base_mint = pool_keys.base_mint
                
                balances_response = await client.get_multiple_accounts_json_parsed(
                    [base_vault, quote_vault], 
                    Processed
                )
                balances = balances_response.value

                pool_coin_account = balances[0]
                pool_pc_account = balances[1]

                pool_coin_account_balance = pool_coin_account.data.parsed['info']['tokenAmount']['uiAmount']
                pool_pc_account_balance = pool_pc_account.data.parsed['info']['tokenAmount']['uiAmount']

                if pool_coin_account_balance is None or pool_pc_account_balance is None:
                    return None, None
                
                if base_mint == SOL:
                    base_reserve = pool_coin_account_balance
                    quote_reserve = pool_pc_account_balance
                    token_decimal = quote_decimal
                else:
                    base_reserve = pool_pc_account_balance
                    quote_reserve = pool_coin_account_balance
                    token_decimal = base_decimal
                
                token_price = base_reserve / quote_reserve

                return token_price ,token_decimal
                #return token_price, token_decimal

            except Exception as e:
                print(f"Error occurred: {e}")
                return None, None
async def get_price(mint,bondingCurveKey):
    mint = Pubkey.from_string(mint)  # 指定代币的 mint 地址 内盘 612Yf34Fmo2hUDnNaKZsm4pyoURBh1E1fjAEW2F1pump 外盘E8UgrYCiCSJqee8KQ9mCemAMFBE7aN2tZsETKcnupump
    result = {}
    liquidity_found  = await get_pair_address(mint)
    if liquidity_found:
        result['type'] = "outside"
        token_pool_keys = await fetch_pool_keys(liquidity_found)
        current_price, token_decimal = await ray_get_token_price(token_pool_keys)
        if current_price:
            result['price'] = f"{current_price:.10f}"
    else:
        result['type'] = "inside"
        bonding_curve = Pubkey.from_string(bondingCurveKey) #监听新币那可以获取这个bonding_curve地址 从 函数get_bonding_curve_addresses也可以获取
        curve_state = await get_pump_curve_state(bonding_curve)
        if curve_state:
            current_price = await calculate_pump_curve_price(curve_state)
            if current_price:
                result['price'] = f"{current_price:.10f}"
    return result

# if __name__=="__main__":
#     asyncio.run(get_price('Hd7xoi8mTMzPNZTqEVEuQNrZT8GTqVGgz3xb8NNcn2Jh','FRcS5Mza6qgeRx8xRSd7NbxE2GnyPZ9LasGdhcFV3k9P'))
