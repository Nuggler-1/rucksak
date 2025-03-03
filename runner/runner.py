from loguru import logger
import random
import time
import csv
import sys
import questionary
from utils import error_handler, sleeping, clear_file, floor_decimal
from constants import DEFAULT_PRIVATE_KEYS, DEFAULT_DEPOSIT_ADDRESSES, DEFAULT_PROXIES, DEFAULT_REPORT_PATH
from config import TOKEN_LIST, USD_POSITION_SIZE, CUSTOM_POSITION_SIZE, MAX_POSITION_DIFFERENCE, RANDOMIZE, REPORT_TYPE, CLOSE_PREVIOUS_POSITIONS
from backpack.backpack import Backpack_account
from backpack.backpack_deposit import OKX

class Runner(): 

    def __init__(self,private_keys:list):
        self.private_keys = private_keys
        self.accounts = []
        pass

    def _get_order_size(self, account:Backpack_account, token:str): #готово

        if USD_POSITION_SIZE != 0: 
            amount_usd = random.uniform(USD_POSITION_SIZE[0], USD_POSITION_SIZE[1])
            order_size = round(amount_usd, 2)
            round_value = 2

        else: 
            order_size = random.uniform(CUSTOM_POSITION_SIZE[token][0], CUSTOM_POSITION_SIZE[token][1])
            decimals = account.get_token_decimals(token)
            order_size = round(order_size, decimals)
            round_value = decimals

        return order_size, round_value

    def _generate_positions_amounts(self,): #готово 

        i = 0
        amounts = []
        logger.info('Creating positions list for each wallet, it might take some time...\n')
        clear_file('memory/amounts.txt')
        token_list = [i for i in TOKEN_LIST if '_PERP' in i]
        for private_key in self.private_keys:

            account = Backpack_account(private_key)
            if i%2 == 0: 
                token = random.choice(token_list)
                isBuy = 1
                order_size, round_value = self._get_order_size(account, token)
            
            else: 
                isBuy = 0
                order_size = order_size * random.uniform(1 - MAX_POSITION_DIFFERENCE/100, 1 + MAX_POSITION_DIFFERENCE/100)
                order_size = round(order_size, round_value)

            i+=1

            amounts.append([private_key, isBuy, order_size, token])
        
        for amount in amounts:

            with open('memory/amounts.txt', "a", encoding="utf-8") as file:
                file.write(str(amount[0]) +':'+ str(amount[1]) + ':' + str(amount[2]) + ':' + str(amount[3]) + '\n')

    def _get_order_type_and_size (self,private_key:str):

        positions= []

        with open('memory/amounts.txt', 'r') as f: 
            for line in f: 
                position = line.strip().split(':')
                positions.append(position)

        for position in positions:
            if private_key in position: 
                if USD_POSITION_SIZE!=0:
                    amount_type = 'USD'
                else:
                    amount_type = 'TOKEN'
                return bool(int(position[1])), float(position[2]), str(position[3]), amount_type
            
    @error_handler('sending order', attempts=1)
    def _send_order(self, private_key:str): #готово

        isBuy, amount, token, amount_type = self._get_order_type_and_size(private_key)
        account = Backpack_account(private_key)
        if CLOSE_PREVIOUS_POSITIONS: 
            closed = account.close_all_positions()
            if closed:
                sleeping('action')
        side = 'LONG' if isBuy else 'SHORT'
        logger.opt(colors=True).info(f'{account.public_key_b64}: Opening {"<green>LONG</green>" if isBuy else "<red>SHORT</red>"} order on {token} - size {amount} {amount_type}')
        
        order = account.open_futures_pos(
            token, 
            'Bid' if isBuy else 'Ask', 
            amount_usd = 0 if amount_type == 'TOKEN' else amount,
            amount_token = 0 if amount_type == 'USD' else amount
        )
        if not order: 
            raise Exception(f'{account.public_key_b64}: Order {amount} {token} {side} failed {order}')
        else: 
            return 1
        
    @error_handler('selling spot tokens')
    def _sell_spot_tokens(self,private_key:str): #готово

        account = Backpack_account(private_key)
        balances = account.get_balances()
        tokens_to_sell = []

        for token in balances.keys(): 

            if token == 'USDC': 
                continue

            decimals = account.get_token_decimals(f'{token}_USDC')
            balance = floor_decimal( float(balances[token]['available']), decimals)

            if balance != 0 : 
                tokens_to_sell.append([f'{token}_USDC', balance])

        if len(tokens_to_sell) < 1: 
            logger.info(f'{account.public_key_b64}: nothing to sell')
            return 1
        
        for token in tokens_to_sell:

            logger.info(f"{account.public_key_b64}: selling {token[0].split('_')[0]}")

            response = account.post_limit_order(token[0], 'Ask', amount_token = token[1])
            assert response['status'] == 'Filled', f'failed to fill sell order on {token[0]} - status {response["status"]}'

            logger.success(f"{account.public_key_b64}: sell order filled {response['executedQuantity']} {response['symbol'].split('_')[0]} at {response['price']} (total: {response['executedQuoteQuantity'] } USD)")
            if token != tokens_to_sell[-1]:
                sleeping('action')
        
        return 1

    @error_handler('sending spot buy order',)  
    def  _send_spot_buy_order(self, private_key:str):

        token_list = [i for i in TOKEN_LIST if '_PERP' not in i]
        token = random.choice(token_list)
        account = Backpack_account(private_key)
        balance = account.get_balances('USDC')

        amount_usd = 0
        if USD_POSITION_SIZE != 0: 
            amount_usd = random.uniform(USD_POSITION_SIZE[0], USD_POSITION_SIZE[1])
            order_size = round(amount_usd, 2)
            if order_size > balance: 
                order_size = balance
            round_value = 2

        else: 
            order_size = random.uniform(CUSTOM_POSITION_SIZE[token][0], CUSTOM_POSITION_SIZE[token][1])
            decimals = account.get_token_decimals(token)
            order_size = round(order_size, decimals)
            round_value = decimals

        buying_amount = f'{order_size} USD of' if USD_POSITION_SIZE!=0 else f'{order_size} '
        logger.info(f"{account.public_key_b64}: buying {buying_amount} {token.split('_')[0]}")

        if amount_usd != 0:
            order = account.post_limit_order(token, 'Bid', amount_usd = order_size)
        
        else: 
            order = account.post_limit_order(token, 'Bid', amount_token = order_size)

        assert order['status'] == 'Filled', f'failed to fill buy order on {token} - status {order["status"]}'

        logger.success(f"{account.public_key_b64}: buy order filled {order['executedQuantity']} {order['symbol'].split('_')[0]} at {order['price']} (total: {order['executedQuoteQuantity'] } USD)")
        
        return 1
    
    def check_spot_balances(self,):
        for private_key in self.private_keys:
            account = Backpack_account(private_key)
            account.get_token_balances()
            print()
    
    def open_spot_positions(self,):
        if RANDOMIZE: 
            random.shuffle(self.private_keys)
        for private_key in self.private_keys:
            self._send_spot_buy_order(private_key)
            if private_key != self.private_keys[-1]:
                sleeping('account')
    
    def close_spot_positions(self,):
        if RANDOMIZE: 
            random.shuffle(self.private_keys)
        for private_key in self.private_keys:
            self._sell_spot_tokens(private_key)
            if private_key != self.private_keys[-1]:
                sleeping('account')
    
    def volume_spot_mode(self, runs: int, delay: list[int]):
        for _ in range(runs): 
            self.open_spot_positions()

            n = random.uniform(*delay)
            logger.info(f'sleeping till next step: {n} seconds')
            time.sleep(n)
            self.close_spot_positions()

            n = random.uniform(*delay)
            logger.info(f'sleeping till next step: {n} seconds')
            time.sleep(n)
            print()
            logger.info(f'Checking spot balances now')
            self.check_spot_balances()
        logger.info('Volume spot mode finished')
    
        
    def open_positions(self,): 
        self._generate_positions_amounts()
        if RANDOMIZE: 
            random.shuffle(self.private_keys)
        for private_key in self.private_keys:
            order = self._send_order(private_key)
            if not order: 
                continue
            if private_key != self.private_keys[-1]: 
                sleeping('account')
        logger.info('All orders placed')
        return 1
    
    def close_positions(self,start_delay: int = 0): 
        if RANDOMIZE: 
            random.shuffle(self.private_keys)
        if start_delay:
            time.sleep(start_delay)

        for private_key in self.private_keys:
            account = Backpack_account(private_key)
            res = account.close_all_positions()
            if not res: 
                continue
            if private_key != self.private_keys[-1]:
                sleeping('account')
                
    def check_stats(self,): 
        with open(DEFAULT_REPORT_PATH, mode='w', newline='', encoding='utf-8') as file:
            pass
        for private_key in self.private_keys:
            account = Backpack_account(private_key)
            account.get_open_positions()
            balance = account.get_overall_balance()
            volume = account.get_volume()
            logger.info(f'{account.public_key_b64}: BALANCE {balance} | VOLUME {volume}')
            with open(DEFAULT_REPORT_PATH, mode='a', newline='', encoding='utf-8') as file:

                if REPORT_TYPE == 'PRIVATE': 
                    data = [account.private_key, round(float(balance), 1), int(volume)]
                elif REPORT_TYPE == 'PUBLIC': 
                    data = [account.public_key_b64, round(float(balance), 1), int(volume)]
                else: 
                    raise Exception(f'unknown report mode, check REPORT_TYPE')

                writer = csv.writer(file)
                writer.writerow(data)
            time.sleep(1)
        logger.info('Stats checked')
    
    def volume_perp_mode(self, runs_delay: list[int], runs: int): 
        for _ in range(runs): 
            self.open_positions()

            n = random.uniform(*runs_delay)
            logger.info(f'sleeping till next step: {n} seconds')
            time.sleep(n)
            self.close_positions()

            n = random.uniform(*runs_delay)
            logger.info(f'sleeping till next step: {n} seconds')
            time.sleep(n)
            logger.info(f'Checking stats now')
            self.check_stats()
            
        logger.info('Volume perp mode finished')

    def deposit_mode(self, deposit_token: str, deposit_amount: list[float]):#USDC/SOL/USDT 
        if RANDOMIZE:
            random.shuffle(self.private_keys)

        for private_key in self.private_keys:
            account = Backpack_account(private_key)
            address = account.get_deposit_address('Solana')
            okx = OKX()
            res = okx.withdraw(address, deposit_token, deposit_amount)
            if private_key != self.private_keys[-1] and res != 0:
                sleeping('account')
        logger.info('Deposits are finished')
    
    def withdraw_mode(self, withdraw_token: str, amount: list[float] | int):
        if RANDOMIZE:
            random.shuffle(self.private_keys)
        for private_key in self.private_keys: 
            account = Backpack_account(private_key)
            res = account.withdraw(symbol = withdraw_token, percent_to_withdraw=amount)
            if private_key != self.private_keys[-1] and res != 0:
                sleeping('account')

    def run(self,): 

        if len(self.private_keys) == 0: 
            logger.warning('Please upload at least one private key!')
            sys.exit()

        while True:

            choice = questionary.select(
                        "Select work mode:",
                        choices=[
                            "Buy spot positions", 
                            "Sell spot postions",
                            "Loop spot mode",
                            "Check spot balances",
                            "Open perp forks", 
                            "Close all perp positions",
                            "Loop perp mode",
                            "Deposit to Backpack",
                            #"Withdraw from Backpack",
                            "Check stats",
                            "Run range of wallets", 
                            "Run specific wallets",
                            "Reset selction of wallets",
                            "Exit"
                        ]
                    ).ask()
            
            try:
                    
                match choice: 

                    case "Buy spot positions":
                        self.open_spot_positions()

                    case "Sell spot postions":
                        self.close_spot_positions()

                    case "Loop spot mode":
                        min_run_delay = int(
                            questionary.text(f'Input min run delay in seconds: ').unsafe_ask()
                        )
                        max_run_delay = int(
                            questionary.text(f'Input max run delay in seconds: ').unsafe_ask()
                        )
                        runs = int(
                            questionary.text(f'Input amount of runs: ').unsafe_ask()
                        )
                        self.volume_spot_mode(runs, [min_run_delay, max_run_delay])

                    case "Check spot balances":
                        self.check_spot_balances()

                    case "Open perp forks":
                        if len(self.private_keys) %2 != 0:
                            answer = questionary.select(
                                'Amount of wallets is not even, unbalanced positions will be opened, you sure?',
                                choices=[
                                    'Yes',
                                    'Exit'
                                ]
                            ).unsafe_ask()
                            if answer == 'Exit':
                                continue
                        self.open_positions()
                    
                    case "Close all perp positions":
                        delay = int(
                            questionary.text(f'Input start delay in seconds: ').unsafe_ask()
                        )
                        if delay:
                            logger.info(f'Starting delay for {delay} seconds')
                        self.close_positions(delay)
                    
                    case "Deposit to Backpack":
                        deposit_token = questionary.select(
                            "Select token to deposit",
                            choices=[
                                "USDC",
                                "SOL",
                                "USDT"
                            ]
                        ).unsafe_ask()
                        min_deposit_amount = float(
                            questionary.text(f'Input min deposit amount: ').unsafe_ask()
                        )
                        max_deposit_amount = float(
                            questionary.text(f'Input max deposit amount: ').unsafe_ask()
                        )
                        self.deposit_mode(deposit_token, [min_deposit_amount, max_deposit_amount])
                    
                    case "Withdraw from Backpack":
                        withdraw_token = questionary.select(
                            "Select token to withdraw",
                            choices=[
                                "USDC",
                                "SOL",
                                "USDT"
                            ]
                        ).unsafe_ask()
                        
                        min_amount = float(
                            questionary.text(f'Input mint percent of balance to withdraw: ').unsafe_ask()
                        )
                        if min_amount != 100:
                            max_amount = float(
                                questionary.text(f'Input max percent of balance to withdraw: ').unsafe_ask()
                            )
                            amounts = [min_amount, max_amount]
                        else:
                            amounts = 100
                        self.withdraw_mode(withdraw_token, amounts)
                    
                    case "Check stats":
                        self.check_stats()

                    case "Loop perp mode":
                        min_run_delay = int(
                            questionary.text(f'Input min run delay in seconds: ').unsafe_ask()
                        )
                        max_run_delay = int(
                            questionary.text(f'Input max run delay in seconds: ').unsafe_ask()
                        )
                        runs = int(
                            questionary.text(f'Input amount of runs: ').unsafe_ask()
                        )
                        self.volume_mode([min_run_delay, max_run_delay], runs)

                    case "Run specific wallets": 
                        while True: 
                            addresses = [Backpack_account(private_key).public_key_b64 for private_key in self.private_keys]
                            choice = questionary.checkbox(
                                "Select wallets to run:",
                                choices=[
                                    *addresses
                                ]
                            ).unsafe_ask()


                            if len(choice) == 0: 
                                logger.warning('Please select at least one wallet (USE SPACE TO SELECT)')
                                continue    

                            new_private_keys = []
                            for address in choice: 
                                index = addresses.index(address)
                                new_private_keys.append(self.private_keys[index])

                            self.private_keys = new_private_keys
                            break

                    case "Run range of wallets": 

                        while True: 

                            addresses = [Backpack_account(private_key).public_key_b64 for private_key in self.private_keys]
                            choice = questionary.checkbox(
                                "Select range of wallets to run (first and last):",
                                choices=[
                                    *addresses
                                ]
                            ).unsafe_ask()

                            if len(choice) !=  2: 
                                logger.warning('Please select first and last wallet in range (ONLY 2 WALLETS)')
                                continue

                            first_index = addresses.index(choice[0])
                            last_index = addresses.index(choice[1])

                            self.private_keys = self.private_keys[first_index:last_index+1]
                            break
                    
                    case "Reset selection of wallets": 

                        with open(DEFAULT_PRIVATE_KEYS, 'r', encoding='utf-8') as f: 
                            self.private_keys = f.read().splitlines()

                    case "Exit": 
                        sys.exit()

                    case _:
                        pass

            except KeyboardInterrupt:
                logger.info("exiting to main menu")
                continue