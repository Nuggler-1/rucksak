from loguru import logger
import random
import time
import csv
import sys
import os
import questionary
from utils import error_handler, sleeping, clear_file, floor_decimal
from constants import DEFAULT_PRIVATE_KEYS, DEFAULT_DEPOSIT_ADDRESSES, DEFAULT_PROXIES, DEFAULT_REPORT_PATH
from config import TOKEN_LIST, USD_POSITION_SIZE, USE_LAST_WALLETS, ACCOUNTS_PER_FORK, CUSTOM_POSITION_SIZE, MAX_POSITION_DIFFERENCE, RANDOMIZE, REPORT_TYPE, CLOSE_PREVIOUS_POSITIONS
from backpack.backpack import Backpack_account
from backpack.backpack_deposit import OKX

class Runner(): 

    def __init__(self,private_keys:list):
        self.private_keys = private_keys
        self.accounts = []
        
    def _update_random_seed(self,):
        seed = int.from_bytes(os.urandom(8), byteorder='big')
        seed ^= int(time.time() * 1000)
        seed ^= os.getpid()
        random.seed(seed)

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
        
        amounts = []
        logger.info('Creating positions list for each wallet, it might take some time...')
        logger.info('')
        clear_file('memory/amounts.txt')
        token_list = [i for i in TOKEN_LIST if '_PERP' in i]
        
        # Разбиваем аккаунты на группы случайного размера
        private_keys = self.private_keys.copy()
        while private_keys:
            # Определяем размер текущей группы
            if len(private_keys) < ACCOUNTS_PER_FORK[0]:
                if USE_LAST_WALLETS and len(private_keys) > 1: 
                    group_size = len(private_keys)
                    group_keys = private_keys
                    private_keys = []
                else: 
                    logger.warning(f'Total {len(private_keys)} unused wallets left')
                    break
            else: 
                group_size = min(random.randint(ACCOUNTS_PER_FORK[0], ACCOUNTS_PER_FORK[1]), len(private_keys))
                group_keys = private_keys[:group_size]
                private_keys = private_keys[group_size:]
            
            token = random.choice(token_list)
            account = Backpack_account(group_keys[0])

            total_long_size = 0
            group_amounts = []
            
            long_accounts = group_keys[:group_size//2 + group_size%2]
            short_accounts = group_keys[group_size//2 + group_size%2:]
            
            # Генерируем лонги
            for key in long_accounts:
                self._update_random_seed()
                order_size, round_value = self._get_order_size(account, token)
                total_long_size += order_size
                group_amounts.append([key, 1, order_size, token])
            
            # Проверяем максимальный возможный объем для шортов
            max_short_capacity = len(short_accounts) * USD_POSITION_SIZE[1]
            if total_long_size > max_short_capacity:
                scale_factor = max_short_capacity / total_long_size
                total_long_size = 0
                # Масштабируем лонги
                for amount in group_amounts:
                    if amount[1] == 1:  # только для лонгов
                        amount[2] = round(amount[2] * scale_factor, round_value)
                        total_long_size += amount[2]
            
            # Генерируем шорты
            remaining_size = total_long_size
            short_positions = []
            for i, key in enumerate(short_accounts):
                self._update_random_seed()
                if i == len(short_accounts) - 1: #последняя шорт позиция с небольшой разницей 
                    order_size = remaining_size * random.uniform(
                        1 - MAX_POSITION_DIFFERENCE/100, 
                        1 + MAX_POSITION_DIFFERENCE/100
                    )
                    if order_size > USD_POSITION_SIZE[1]: #если больше верхней границы - распределяем по остальным аккаунтам
                        excess = order_size - USD_POSITION_SIZE[1]
                        order_size = USD_POSITION_SIZE[1]
                        # распределяем лишнее 
                        for pos in short_positions:
                            available_space = USD_POSITION_SIZE[1] - pos[2]
                            if available_space > 0:
                                add_size = min(excess, available_space)
                                pos[2] = round(pos[2] + add_size, round_value)
                                excess -= add_size
                                if excess <= 0:
                                    break
                else:
                    # Распределяем шорт позиции неравномерно
                    size_portion = random.choice([random.uniform(0.3, 0.45), random.uniform(0.55, 0.7)])  # Макс разница 40%
                    order_size = remaining_size * size_portion
                    order_size = min(order_size, USD_POSITION_SIZE[1])
                    remaining_size -= order_size
                
                order_size = round(order_size, round_value)
                short_positions.append([key, 0, order_size, token])
            
            group_amounts.extend(short_positions)
            amounts.extend(group_amounts)
            
            logger.opt(colors=True).info(f'Fork group of <c>{len(group_amounts)} wallets</c> generated')
            logger.opt(colors=True).info(f'Total size: <m>{round(sum([i[2] for i in group_amounts]), 2)}$</m>')
            logger.opt(colors=True).info(f'Token used: <m>{token}</m>')
            for wallet in group_amounts:
                logger.opt(colors=True).info(f'{Backpack_account.public_key(wallet[0])}: <c>{wallet[2]} $</c> {"<green>LONG</green>" if wallet[1] else "<red>SHORT</red>"}')
            logger.info('')

        # Записываем все позиции в файл
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
        
        return None, None, None, None
            
    @error_handler('sending order', attempts=1)
    def _send_order(self, private_key:str): #готово

        isBuy, amount, token, amount_type = self._get_order_type_and_size(private_key)
        if not token: 
            return 0 

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

    def check_open_perp_positions(self,):
        total_profit = 0
        total_opened_size = 0
        for private_key in self.private_keys:
            account = Backpack_account(private_key)
            profit, size = account.check_all_positions()
            total_profit += profit
            total_opened_size += size
        logger.info('')
        logger.opt(colors=True).info(f'Total profit: <m>{round(total_profit,2)}</m>')
        logger.opt(colors=True).info(f'Total opened size: <m>{round(total_opened_size,2)}</m>')
                
    def check_stats(self,): 
        with open(DEFAULT_REPORT_PATH, mode='w', newline='', encoding='utf-8') as file:
            pass
        overall_balance = 0
        overall_points = 0
        for private_key in self.private_keys:
            account = Backpack_account(private_key)
            account.get_open_positions()
            balance, points = account.get_overall_balance()
            volume = account.get_volume()
            logger.opt(colors=True).info(f'{account.public_key_b64}: BALANCE <c>{round(balance,1):>5} $</c> | VOLUME <c>{volume:>8} $</c> | POINTS <m>{points:>4}</m>')
            overall_balance += float(balance)
            overall_points += int(points)
            with open(DEFAULT_REPORT_PATH, mode='a', newline='', encoding='utf-8') as file:

                if REPORT_TYPE == 'PRIVATE': 
                    data = [account.private_key, round(float(balance), 1), int(volume), points]
                elif REPORT_TYPE == 'PUBLIC': 
                    data = [account.public_key_b64, round(float(balance), 1), int(volume), points]
                else: 
                    raise Exception(f'unknown report mode, check REPORT_TYPE')

                writer = csv.writer(file)
                writer.writerow(data)
            time.sleep(1)
        logger.info('')
        logger.opt(colors=True).info(f'OVERALL BALANCE <c>{overall_balance:>6} $</c> | OVERALL POINTS <m>{overall_points:>4}</m>')
        logger.info('')
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
                    "Spot",
                    "Perp",
                    "Deposit to Backpack",
                    "Run range of wallets", 
                    "Run specific wallets",
                    "Reset selection of wallets",
                    "Exit"
                ]
            ).ask()
            
            try:

                match choice: 

                    case "Spot":
                        action = questionary.select(
                            'Select action',
                            [
                                "Buy spot positions", 
                                "Sell spot postions",
                                "Loop spot mode",
                                "Check spot balances",
                                "Exit"
                            ]
                        ).unsafe_ask()
                        
                    case "Perp":
                        action = questionary.select(
                            'Select action',
                            [
                                "Open perp forks", 
                                "Close all perp positions",
                                "Loop perp mode",
                                #"Withdraw from Backpack",
                                "Check open perp positions",
                                "Check stats",
                                'Exit'
                            ]
                        ).unsafe_ask()

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
                        continue

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
                        continue

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
                        continue
                    
                    case "Reset selection of wallets": 

                        with open(DEFAULT_PRIVATE_KEYS, 'r', encoding='utf-8') as f: 
                            self.private_keys = f.read().splitlines()
                        continue
                    
                    case "Exit":
                        sys.exit()

                    case _:
                        logger.warning('Invalid choice')
                        #continue
                    
                match action: 

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
                        """
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
                        """
                        self.open_positions()

                    case "Check open perp positions":
                        self.check_open_perp_positions()
                    
                    case "Close all perp positions":
                        delay = str(
                            questionary.text(f'Input start delay in seconds: ').unsafe_ask()
                        )
                        if len(delay)> 0:
                            logger.info(f'Starting delay for {delay} seconds')
                            self.close_positions(int(delay))
                    
                    
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

                    case "Exit": 
                        continue 
                    
                    case _:
                        pass

            except KeyboardInterrupt:
                logger.info("exiting to main menu")
                continue
                       

            