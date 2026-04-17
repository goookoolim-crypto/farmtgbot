from urllib.parse import unquote, parse_qs
from utils.core import logger
from fake_useragent import UserAgent
from data import config
import ssl, certifi
import json

import aiohttp
import asyncio
import random

class Blum:
    def __init__(self, thread: int, init_data: str):
        self.thread = thread
        self.init_data = init_data

        try:
            parsed = {k: v[0] for k, v in parse_qs(init_data).items()}
            user_info = json.loads(parsed.get('user', '{}'))
            self.name = user_info.get('first_name', f'account_{thread}')
        except Exception:
            self.name = f'account_{thread}'

        self.proxy = None
        self.auth_token = ""
        self.ref_token=""
        headers = {
            'accept': 'application/json, text/plain, */*',
            'cache-control': 'no-cache',
            'content-type': 'application/json',
            'origin': 'https://telegram.blum.codes',
            'pragma': 'no-cache',
            'priority': 'u=1, i',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-site',
            'user-agent': UserAgent(os='android').random}
        sslcontext = ssl.create_default_context(cafile=certifi.where())
        connector = aiohttp.TCPConnector(ssl=sslcontext)
        self.session = aiohttp.ClientSession(headers=headers, trust_env=True, connector=connector)
        self.error_cnt = 0

    async def main(self):
        await asyncio.sleep(random.randint(*config.ACC_DELAY))
        try:
            while True:
                try:
                    login = await self.login()
                    if login == False:
                        return 0
                    logger.info(f"main | Thread {self.thread} | {self.name} | Start! | PROXY : {self.proxy}")
                except Exception as err:
                    logger.error(f"main | Thread {self.thread} | {self.name} | {err}")
                    return 0
                    
                try:
                    valid = await self.is_token_valid()
                    if not valid:
                        logger.warning(f"main | Thread {self.thread} | {self.name} | Token is invalid. Refreshing token...")
                        await self.refresh()
                    await asyncio.sleep(random.randint(*config.MINI_SLEEP))
                    
                    await self.claim_diamond()
                    await asyncio.sleep(random.randint(*config.MINI_SLEEP))
                    
                    timestamp, start_time, end_time = await self.balance()
                    
                    await self.get_referral_info()
                    await asyncio.sleep(random.randint(*config.MINI_SLEEP))
                    
                    if config.DO_TASKS:
                        await self.do_tasks()
                        await asyncio.sleep(random.randint(*config.MINI_SLEEP))
                    
                    if config.SPEND_DIAMONDS and 5 == 4:
                        diamonds_balance = await self.get_diamonds_balance()
                        logger.info(f"main | Thread {self.thread} | {self.name} | Have {diamonds_balance} diamonds!")
                        games_count = random.randint(*config.MAX_GAMES_COUNT)
                        logger.info(f"main | Thread {self.thread} | {self.name} | Starting play {min(games_count, diamonds_balance)} games...")
                        for _ in range(min(games_count, diamonds_balance)):
                            await self.game()
                            await asyncio.sleep(random.randint(*config.SLEEP_GAME_TIME))
                            
                    if start_time is None and end_time is None:
                        await self.start()
                        logger.info(f"main | Thread {self.thread} | {self.name} | Start farming!")
                    elif start_time is not None and end_time is not None and timestamp >= end_time:
                        timestamp, balance = await self.claim()
                        logger.success(f"main | Thread {self.thread} | {self.name} | Claimed reward! Balance: {balance}")
                    
                    logger.info(f"main | Thread {self.thread} | {self.name} | All activities in blum completed")
                    return 0
                except Exception as err:
                    logger.error(f"main | Thread {self.thread} | {self.name} | Error log: {err}")
                    await asyncio.sleep(52)
                    self.error_cnt += 1
                    if (self.error_cnt >= config.ERRORS_BEFORE_STOP):
                        return 0
        finally:
            await self.session.close()


    async def claim(self):
        try:
            resp = await self.session.post("https://game-domain.blum.codes/api/v1/farming/claim")
            resp_json = await resp.json()
            if 'message' in resp_json:
                if not (await self.is_token_valid()):
                    await self.refresh()
                return 0, "0"
            return int(resp_json.get("timestamp", 0)/1000), resp_json.get("availableBalance", "0")
        except Exception as e:
            logger.error(f"claim | Thread {self.thread} | {self.name} | {e}")
            return 0, "0"

    async def start(self):
        try:
            resp = await self.session.post("https://game-domain.blum.codes/api/v1/farming/start")
            resp_json = await resp.json()
            if 'message' in resp_json:
                if not (await self.is_token_valid()):
                    await self.refresh()
                return 0
        except Exception as e:
            logger.error(f"start | Thread {self.thread} | {self.name} | {e}")
            return 0
        
    async def balance(self):
        try:
            
            resp = await self.session.get("https://game-domain.blum.codes/api/v1/user/balance")
            resp_json = await resp.json()
            if 'message' in resp_json:
                if not (await self.is_token_valid()):
                    await self.refresh()
            timestamp = resp_json.get("timestamp")
            if timestamp is None:
                return 0, None, None
            if resp_json.get("farming"):
                start_time = resp_json.get("farming").get("startTime")
                end_time = resp_json.get("farming").get("endTime")
                return int(timestamp/1000), int(start_time/1000), int(end_time/1000)
            return int(timestamp), None, None
        except Exception as e:
            logger.error(f"balance | Thread {self.thread} | {self.name} | {e}")
            return 0, None, None

    async def login(self):
        try:
            json_data = {"query": self.init_data}
            resp = await self.session.post("https://user-domain.blum.codes/api/v1/auth/provider/PROVIDER_TELEGRAM_MINI_APP", json=json_data)
            resp = await resp.json()
            token_data = resp.get("token")
            if not token_data:
                logger.error(f"login | Thread {self.thread} | {self.name} | No token in response: {str(resp)[:200]}")
                return False
            self.ref_token = token_data.get("refresh", "")
            access = token_data.get("access", "")
            if not access:
                logger.error(f"login | Thread {self.thread} | {self.name} | No access token in response")
                return False
            self.session.headers['Authorization'] = "Bearer " + access
            return True
        except Exception as err:
            logger.error(f"login | Thread {self.thread} | {self.name} | {err}")
            if err == "Server disconnected":
                return True
            return False

    async def get_referral_info(self):
        try:
            resp = await self.session.get("https://user-domain.blum.codes/api/v1/friends/balance")
            resp_json = await resp.json()
            if 'message' in resp_json:
                if not (await self.is_token_valid()):
                    await self.refresh()
                return 0
            if resp_json['canClaim'] == True:
                claimed = await self.claim_referral()
                logger.success(f"get_ref | Thread {self.thread} | {self.name} | Claimed referral reward! Claimed: {claimed}")
        except:
            pass
    
    async def claim_referral(self):
        resp = await self.session.post("https://user-domain.blum.codes/api/v1/friends/claim")
        resp_json = await resp.json()
        if 'message' in resp_json:
            if not (await self.is_token_valid()):
                await self.refresh()
            return 0
        return resp_json['claimBalance']
    
    async def do_tasks(self):
        resp = await self.session.get("https://earn-domain.blum.codes/api/v1/tasks")
        resp_json = (await resp.json())
        if 'message' in resp_json:
            if not (await self.is_token_valid()):
                await self.refresh()
            return 0
        try:
            for tasks_all in resp_json:
                if tasks_all['sectionType']=="DEFAULT":
                    for task in tasks_all['subSections']:
                        if task['title'] == "Frens":
                            continue
                        tasks = task['tasks']
                        for task in tasks:
                            if task['status'] == "NOT_STARTED":
                                await self.session.post(f"https://earn-domain.blum.codes/api/v1/tasks/{task['id']}/start")
                                await asyncio.sleep(random.randint(*config.MINI_SLEEP))
                            elif task['status'] == "READY_FOR_CLAIM":
                                answer = await self.session.post(f"https://earn-domain.blum.codes/api/v1/tasks/{task['id']}/claim")
                                answer = await answer.json()
                                if 'message' in answer:
                                    continue
                                logger.success(f"tasks | Thread {self.thread} | {self.name} | Claimed TASK reward! Claimed: {answer['reward']}")
                                await asyncio.sleep(random.randint(*config.MINI_SLEEP))
        except Exception as err:
            logger.error(f"tasks | Thread {self.thread} | {self.name} | {err}")
    
    async def is_token_valid(self):
        response = await self.session.get("https://user-domain.blum.codes/api/v1/user/me")
        
        if response.status == 200:
            return True
        elif response.status == 401:
            error_info = await response.json()
            return error_info.get("code") != 16
        else:
            return False
    
    async def refresh(self):

        
        refresh_payload = {
            'refresh': self.ref_token
        }
        
        if "authorization" in self.session.headers:
            del self.session.headers['authorization']
            
        response = await self.session.post("https://user-domain.blum.codes/api/v1/auth/refresh",json=refresh_payload)
        
        if response.status == 200:
            data = await response.json()  
            new_access_token = data.get("access")  
            new_refresh_token = data.get("refresh")

            if new_access_token:
                self.auth_token = new_access_token  
                self.ref_token = new_refresh_token  
                self.session.headers['Authorization'] = "Bearer "+self.auth_token
                logger.info(f"refresh | Thread {self.thread} | {self.name} | Token refreshed successfully.")
            else:
                raise Exception("New access token not found in the response")
        else:
            raise Exception("Failed to refresh the token")
    
    async def get_diamonds_balance(self):
        resp = await self.session.get("https://game-domain.blum.codes/api/v1/user/balance")
        resp_json = await resp.json()
        if 'message' in resp_json:
            if not (await self.is_token_valid()):
                await self.refresh()
            return 0
        return resp_json['playPasses']
    
    async def game(self):

        response = await self.session.post('https://game-domain.blum.codes/api/v1/game/play')
        logger.info(f"game | Thread {self.thread} | {self.name} | Start DROP GAME!")
        if 'Invalid jwt token' in await response.text():
            logger.warning(f"main | Thread {self.thread} | {self.name} | Token is invalid. Refreshing token...")
            await self.refresh()
        if 'message' in await response.json():
            logger.error(f"game | Thread {self.thread} | {self.name} | DROP GAME CAN'T START")
            valid = await self.is_token_valid()
            if not valid:
                logger.warning(f"main | Thread {self.thread} | {self.name} | Token is invalid. Refreshing token...")
                await self.refresh()
            return
        text = (await response.json())['gameId']
        count = random.randint(*config.POINTS)
        if count >=160:
            await asyncio.sleep(30+(count-160)//7*4)
        else:
            await asyncio.sleep(30)
        json_data = {
            'gameId': text,
            'points': count,
        }

        response = await self.session.post('https://game-domain.blum.codes/api/v1/game/claim', json=json_data)
        
        if await response.text() == "OK":
            logger.success(f"game | Thread {self.thread} | {self.name} | Claimed DROP GAME ! Claimed: {count}")
        elif "Invalid jwt token" in await response.text():
            valid = await self.is_token_valid()
            if not valid:
                logger.warning(f"game | Thread {self.thread} | {self.name} | Token is invalid. Refreshing token...")
                await self.refresh()
        else:
            logger.error(f"game | Thread {self.thread} | {self.name} | {await response.text()}")
    
    async def claim_diamond(self):
        resp = await self.session.post("https://game-domain.blum.codes/api/v1/daily-reward?offset=-180")
        txt = await resp.text()
        if 'message' in txt:
            if not (await self.is_token_valid()):
                await self.refresh()
                return False
        return True if txt == 'OK' else txt
