from urllib.parse import unquote, parse_qs
import threading
import requests
import urllib3
import json
import random
import config
import time
import os

report_bug_text = "If you have done all the steps correctly and you think this is a bug, report it to github.com/aDarkDev with response. response: {}"
authenticate_error = "Please follow the steps correctly. Not authenticated."

class MaxAuthFailuresExceeded(Exception):
    """Raised when an account exhausts its auth retry budget."""
    pass

class NotPx:
    MAX_AUTH_FAILURES = 50
    UpgradePaintReward = {
        2: {
            "Price": 5,
        },
        3: {
            "Price": 100,
        },
        4: {
            "Price": 200,
        },
        5: {
            "Price": 300,
        },
        6: {
            "Price": 500,
        },
        7: {
            "Price": 600,
            "Max": 1
        }
    }

    UpgradeReChargeSpeed = {
        2: {
            "Price": 5,
        },
        3: {
            "Price": 100,
        },
        4: {
            "Price": 200,
        },
        5: {
            "Price": 300,
        },
        6: {
            "Price": 400,
        },
        7: {
            "Price": 500,
        },
        8: {
            "Price": 600,
        },
        9: {
            "Price": 700,
        },
        10: {
            "Price": 800,
        },
        11: {
            "Price": 900,
            "Max":1
        }
    }
    
    UpgradeEnergyLimit = {
        2: {
            "Price": 5,
        },
        3: {
            "Price": 100,
        },
        4: {
            "Price": 200,
        },
        5: {
            "Price": 300,
        },
        6: {
            "Price": 400,
            "Max": 1
        }
    }

    def __init__(self, init_data: str) -> None:
        self.session = requests.Session()
        if config.USE_PROXY:
            self.session.proxies = config.PROXIES
        self.init_data = init_data

        try:
            parsed = {k: v[0] for k, v in parse_qs(init_data).items()}
            user_info = json.loads(parsed.get('user', '{}'))
            self.session_name = user_info.get('first_name', 'unknown')
        except Exception:
            self.session_name = 'unknown'

        self._auth_failures = 0
        self.__update_headers()

    def __update_headers(self):
        self.session.headers = {
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Authorization': f'initData {self.init_data}',
            'Priority': 'u=1, i',
            'Referer': 'https://notpx.app/',
            'Sec-Ch-Ua': 'Chromium;v=119, Not?A_Brand;v=24',
            'Sec-Ch-Ua-Mobile': '?0',
            'Sec-Ch-Ua-Platform': 'Linux',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-origin',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.6045.105 Safari/537.36',
        }

    def request(self, method, end_point, key_check, data=None):
        while True:
            try:
                if method == "get":
                    response = self.session.get(f"https://notpx.app/api/v1{end_point}", timeout=5)
                else:
                    response = self.session.post(f"https://notpx.app/api/v1{end_point}", timeout=5, json=data)
                if "failed to parse" in response.text:
                    print("[x] {}NotPixel internal error. Wait 5 minutes...{}".format(Colors.RED, Colors.END))
                    time.sleep(5 * 60)
                elif response.status_code == 200:
                    if self._auth_failures:
                        print("[+] {}{}{}: recovered after {} auth failure(s){}".format(
                            Colors.CYAN, self.session_name, Colors.END,
                            self._auth_failures, Colors.END
                        ))
                        self._auth_failures = 0
                    if key_check in response.text:
                        return response.json()
                    else:
                        raise Exception(report_bug_text.format(response.text))
                elif response.status_code >= 500:
                    body_preview = response.text[:200].replace("\n", " ")
                    print("[!] {}{}{}: HTTP {} on {} (server-side): {}".format(
                        Colors.CYAN, self.session_name, Colors.END,
                        response.status_code, end_point, body_preview
                    ))
                    time.sleep(5)
                else:
                    self._auth_failures += 1
                    body_preview = response.text[:200].replace("\n", " ")
                    print("[!] {}{}{}: HTTP {} on {} (auth fail #{}): {}".format(
                        Colors.CYAN, self.session_name, Colors.END,
                        response.status_code, end_point, self._auth_failures, body_preview
                    ))
                    if self._auth_failures == 5:
                        print("[!!] {}{}{}: {}5 consecutive auth failures. Most likely your Telegram account has never opened NotPixel. Go to t.me/notpixel on your phone and tap Launch to register.{}".format(
                            Colors.CYAN, self.session_name, Colors.END, Colors.YELLOW, Colors.END
                        ))
                    if self._auth_failures >= 10:
                        backoff = min(300, 10 * (self._auth_failures - 9))
                        print("[!!] {}{}{}: {}{} consecutive auth failures, sleeping {}s before next retry{}".format(
                            Colors.CYAN, self.session_name, Colors.END,
                            Colors.YELLOW, self._auth_failures, backoff, Colors.END
                        ))
                        time.sleep(backoff)
                    if self._auth_failures >= self.MAX_AUTH_FAILURES:
                        raise MaxAuthFailuresExceeded(
                            f"{self.session_name}: {self._auth_failures} consecutive auth failures, giving up"
                        )
                    self.session.headers.update({
                        "Authorization": "initData " + self.init_data
                    })
                    print("[+] Authorization re-applied from stored init_data")
                    time.sleep(2)

            except (requests.exceptions.ConnectionError,
                    urllib3.exceptions.NewConnectionError,
                    requests.exceptions.Timeout) as exc:
                label = type(exc).__name__
                print("[!] {}{}{} {}. Sleeping for 5s...".format(Colors.RED, label, Colors.END, end_point))
                time.sleep(5)

            continue

    def claim_mining(self):
        return self.request("get","/mining/claim","claimed")['claimed']

    def accountStatus(self):
        return self.request("get","/mining/status","speedPerSecond")

    def autoPaintPixel(self):
        colors = [ "#FFFFFF" , "#000000" , "#00CC78" , "#BE0039" ]
        random_pixel = (random.randint(100,990) * 1000) + random.randint(100,990)
        data = {"pixelId":random_pixel,"newColor":random.choice(colors)}

        return self.request("post","/repaint/start","balance",data)['balance']
    
    def paintPixel(self,x,y,hex_color):
        pixelformated = (y * 1000) + x + 1
        data = {"pixelId":pixelformated,"newColor":hex_color}

        return self.request("post","/repaint/start","balance",data)['balance']

    def upgrade_paintreward(self):
        return self.request("get","/mining/boost/check/paintReward","paintReward")['paintReward']
    
    def upgrade_energyLimit(self):
        return self.request("get","/mining/boost/check/energyLimit","energyLimit")['energyLimit']
    
    def upgrade_reChargeSpeed(self):
        return self.request("get","/mining/boost/check/reChargeSpeed","reChargeSpeed")['reChargeSpeed']
    
class Colors:
    """ ANSI color codes """
    BLACK = "\033[0;30m"
    RED = "\033[0;31m"
    GREEN = "\033[0;32m"
    BROWN = "\033[0;33m"
    BLUE = "\033[0;34m"
    PURPLE = "\033[0;35m"
    CYAN = "\033[0;36m"
    LIGHT_GRAY = "\033[0;37m"
    DARK_GRAY = "\033[1;30m"
    LIGHT_RED = "\033[1;31m"
    LIGHT_GREEN = "\033[1;32m"
    YELLOW = "\033[1;33m"
    LIGHT_BLUE = "\033[1;34m"
    LIGHT_PURPLE = "\033[1;35m"
    LIGHT_CYAN = "\033[1;36m"
    LIGHT_WHITE = "\033[1;37m"
    BOLD = "\033[1m"
    FAINT = "\033[2m"
    ITALIC = "\033[3m"
    UNDERLINE = "\033[4m"
    BLINK = "\033[5m"
    NEGATIVE = "\033[7m"
    CROSSED = "\033[9m"
    END = "\033[0m"
    if not __import__("sys").stdout.isatty():
        for _ in dir():
            if isinstance(_, str) and _[0] != "_":
                locals()[_] = ""
    else:
        if __import__("platform").system() == "Windows":
            kernel32 = __import__("ctypes").windll.kernel32
            kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
            del kernel32


print(r"""{}
 _   _       _  ______       ______       _   
| \ | |     | | | ___ \      | ___ \     | |  
|  \| | ___ | |_| |_/ /_  __ | |_/ / ___ | |_ 
| . ` |/ _ \| __|  __/\ \/ / | ___ \/ _ \| __|
| |\  | (_) | |_| |    >  <  | |_/ / (_) | |_ 
\_| \_/\___/ \__\_|   /_/\_\ \____/ \___/ \__|
                                              
        NotPx Auto Paint & Claim by aDarkDev - v2.0 {}""".format(Colors.BLUE, Colors.END))


def painter(NotPxClient:NotPx,session_name:str):
    print("[+] {}Auto painting started{}.".format(Colors.CYAN,Colors.END))
    while True:
        try:
            user_status = NotPxClient.accountStatus()
            if not user_status:
                time.sleep(5)
                continue
            else:
                charges = user_status['charges']
                levels_recharge = user_status['boosts']['reChargeSpeed'] + 1
                levels_paintreward = user_status['boosts']['paintReward'] + 1
                levels_energylimit = user_status['boosts']['energyLimit'] + 1
                user_balance = user_status['userBalance']

            if levels_recharge - 1 < config.RE_CHARGE_SPEED_MAX and NotPx.UpgradeReChargeSpeed[levels_recharge]['Price'] <= user_balance:
                status = NotPxClient.upgrade_reChargeSpeed()
                print("[+] {}ReChargeSpeed Upgrade{} to level {} result: {}".format(Colors.CYAN,Colors.END,levels_recharge,status))
                user_balance -= NotPx.UpgradeReChargeSpeed[levels_recharge]['Price']

            if levels_paintreward - 1 < config.PAINT_REWARD_MAX and NotPx.UpgradePaintReward[levels_paintreward]['Price'] <= user_balance:
                status = NotPxClient.upgrade_paintreward()
                print("[+] {}PaintReward Upgrade{} to level {} result: {}".format(Colors.CYAN,Colors.END,levels_paintreward,status))
                user_balance -= NotPx.UpgradePaintReward[levels_paintreward]['Price']

            if levels_energylimit - 1 < config.ENERGY_LIMIT_MAX and NotPx.UpgradeEnergyLimit[levels_energylimit]['Price'] <= user_balance:
                status = NotPxClient.upgrade_energyLimit()
                print("[+] {}EnergyLimit Upgrade{} to level {} result: {}".format(Colors.CYAN,Colors.END,levels_energylimit,status))
                user_balance -= NotPx.UpgradeEnergyLimit[levels_energylimit]['Price']
                
            if charges > 0:
                for _ in range(charges):
                    balance = NotPxClient.autoPaintPixel()
                    print("[+] {}{}{}: 1 {}Pixel painted{} successfully. User new balance: {}{}{}".format(
                        Colors.CYAN,session_name,Colors.END,
                        Colors.GREEN,Colors.END,
                        Colors.GREEN,balance,Colors.END
                    ))
                    t = random.randint(1,6)
                    print("[!] {}{} anti-detect{}: Sleeping for {}...".format(Colors.CYAN,session_name,Colors.END,t))
                    time.sleep(t)
            else:
                print("[!] {}{}{}: {}No charge available{}. Sleeping for 10 minutes...".format(
                    Colors.CYAN,session_name,Colors.END,
                    Colors.YELLOW,Colors.END
                ))
                time.sleep(600)
        except MaxAuthFailuresExceeded as e:
            print("[!!] {}{}{}: {}{}{}. Painter thread exiting.".format(
                Colors.CYAN, session_name, Colors.END,
                Colors.RED, e, Colors.END
            ))
            return
        except requests.exceptions.ConnectionError:
            print("[!] {}{}{}: {}ConnectionError{}. Sleeping for 5s...".format(
                    Colors.CYAN,session_name,Colors.END,
                    Colors.RED,Colors.END
                ))
            time.sleep(5)
        except urllib3.exceptions.NewConnectionError:
            print("[!] {}{}{}: {}NewConnectionError{}. Sleeping for 5s...".format(
                    Colors.CYAN,session_name,Colors.END,
                    Colors.RED,Colors.END
                ))
            time.sleep(5)
        except requests.exceptions.Timeout:
            print("[!] {}{}{}: {}Timeout Error{}. Sleeping for 5s...".format(
                    Colors.CYAN,session_name,Colors.END,
                    Colors.RED,Colors.END
                ))
            time.sleep(5)
        
        
def mine_claimer(NotPxClient: NotPx, session_name: str):
    time.sleep(5)

    print("[+] {}Auto claiming started{}.".format(Colors.CYAN, Colors.END))
    while True:
        try:
            acc_data = NotPxClient.accountStatus()
            
            if acc_data is None:
                print("[!] {}{}{}: {}Failed to retrieve account status. Retrying...{}".format(Colors.CYAN, session_name, Colors.END, Colors.RED, Colors.END))
                time.sleep(5)
                continue
            
            if 'fromStart' in acc_data and 'speedPerSecond' in acc_data:
                fromStart = acc_data['fromStart']
                speedPerSecond = acc_data['speedPerSecond']
                if fromStart * speedPerSecond > 0.3:
                    claimed_count = round(NotPxClient.claim_mining(), 2)
                    print("[+] {}{}{}: {} NotPx Token {}claimed{}.".format(
                        Colors.CYAN, session_name, Colors.END,
                        claimed_count, Colors.GREEN, Colors.END
                    ))
            else:
                print("[!] {}{}{}: {}Unexpected account data format. Retrying...{}".format(Colors.CYAN, session_name, Colors.END, Colors.RED, Colors.END))
            
            print("[!] {}{}{}: Sleeping for 1 hour...".format(Colors.CYAN, session_name, Colors.END))
            time.sleep(3600)
        except MaxAuthFailuresExceeded as e:
            print("[!!] {}{}{}: {}{}{}. Claimer thread exiting.".format(
                Colors.CYAN, session_name, Colors.END,
                Colors.RED, e, Colors.END
            ))
            return

def multithread_starter():
    data_file = 'data.txt'
    if not os.path.exists(data_file):
        print(f'[x] {Colors.RED}data.txt not found!{Colors.END}')
        return
    datas = [line.strip() for line in open(data_file).readlines() if line.strip()]
    if not datas:
        print(f'[x] {Colors.RED}0 accounts in data.txt{Colors.END}')
        return
    for idx, init_data in enumerate(datas):
        try:
            session_name = f'account_{idx+1}'
            cli = NotPx(init_data)
            threading.Thread(target=painter, args=[cli, session_name]).start()
            threading.Thread(target=mine_claimer, args=[cli, session_name]).start()
        except Exception as e:
            print(f'[!] {Colors.RED}Error on account {idx+1}{Colors.END}: {e}')

if __name__ == "__main__":
    autostart = os.environ.get("NOTPIXEL_AUTOSTART", "0") == "1"
    if autostart:
        if not os.path.exists('data.txt') or not [l for l in open('data.txt').readlines() if l.strip()]:
            print(f'[x] {Colors.RED}NOTPIXEL_AUTOSTART=1 but no data in data.txt{Colors.END}')
            raise SystemExit(1)
        lines = [l for l in open('data.txt').readlines() if l.strip()]
        print(f'[+] {Colors.GREEN}NOTPIXEL_AUTOSTART=1{Colors.END} - starting mine+claim with {len(lines)} account(s)')
        multithread_starter()
        while True:
            time.sleep(3600)

    while True:
        option = input("[!] {}Enter 1{} to show instructions for adding accounts, {}2 for start{} mine + claim: ".format(Colors.BLUE,Colors.END,Colors.BLUE,Colors.END))
        if option == "1":
            print(f"\n{Colors.GREEN}To add accounts:{Colors.END}")
            print(f"1. Open Telegram Desktop with DevTools enabled")
            print(f"2. Open https://t.me/notpixel")
            print(f"3. Extract tgWebAppData from the WebView")
            print(f"4. Paste one init_data token per line in data.txt")
            print(f"5. Then select option 2 to start\n")
        elif option == "2":
            print("{}Warning!{} Most airdrops utilize {}UTC detection to prevent cheating{}, which means they monitor your sleep patterns and the timing of your tasks. It's advisable to {}run your script when you're awake and to pause it before you go to sleep{}.".format(
                Colors.YELLOW,Colors.END,Colors.YELLOW,Colors.END,Colors.YELLOW,Colors.END
            ))
            multithread_starter()
            while True:
                time.sleep(3600)
