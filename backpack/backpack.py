from utils import * 
from config import * 
from constants import * 

class Backpack_exchange():

    def __init__(self, proxy:dict = None): 

        self.base_url = BASE_URL
        self.session = requests.Session()
        
        if proxy!= None: 
            self.session.proxies.update(proxy)

    def _handle_request_exception(self, response): 

        status_code = response.status_code
        if status_code < 400:
            return
        if 400 <= status_code < 500:
            raise Exception(f'Request error {response.status_code}: {response.text} ')

    def get_token_price(self, symbol:str): 

        url = f'{self.base_url}api/v1/ticker?symbol={symbol}'
        
        response = self.session.get(url)
        self._handle_request_exception(response)

        return float(response.json()['lastPrice'])
    
    def get_token_decimals(self, symbol:str): 

        url = f'{self.base_url}api/v1/depth?symbol={symbol}'

        response = self.session.get(url)
        self._handle_request_exception(response)

        amount = response.json()['asks'][0][1]

        if '.' in amount:
            decimals = len(str(amount).split('.')[1])
        else: 
            decimals = 0

        return decimals



class Backpack_account(Backpack_exchange): 

    def __init__(self, private_key:str,):

        proxy = get_proxy(private_key)
        super().__init__(proxy=proxy)
        
        self.signer = Ed25519PrivateKey.from_private_bytes(base64.b64decode(private_key))

        public_key = self.signer.public_key().public_bytes_raw()
        self.public_key_hex = public_key.hex()
        self.public_key_b64 = base64.b64encode(public_key).decode(encoding='utf-8')
        self.private_key = private_key

        self.base_url = BASE_URL
        self.session = requests.Session()
        
        if proxy!=None:
            self.session.proxies.update(proxy)

        
    def _sign_message_b64(self, message:str): 

        signed_message = base64.b64encode(self.signer.sign(bytes(message, 'utf-8'))).decode(encoding='utf-8')
        return signed_message 
        
    def _generate_headers(self, timestamp:int, signature:str, window:int = 60000):

        headers = {
            'X-API-KEY': self.public_key_b64, 
            'X-SIGNATURE': signature,
            'X-TIMESTAMP': str(timestamp), 
            'X-WINDOW': str(window),
            "Content-Type": "application/json; charset=utf-8"
        } 

        return headers
    
    def _query(
            
            self,
            instruction_type: Literal[
                'balanceQuery', 
                'depositAddressQuery', 
                'depositQueryAll', 
                'fillHistoryQueryAll' ,
                'positionQuery',
                'orderCancel',
                'orderCancelAll', 
                'orderExecute',
                'orderHistoryQueryAll',
                'orderQuery',
                'orderQueryAll',
                'withdraw',
                'withdrawalQueryAll'
            ],     
            method: Literal['post', 'get'], 
            url_path:str, 
            query_data:dict = None,
            request_body:dict = None,
            window: int = 60000,
            
        ): 

        url = self.base_url + url_path

        timestamp = int(time.time() * 1000)

        signature = self._sign_query(instruction_type, timestamp, query_data, window)
        headers = self._generate_headers(timestamp, signature, window)
        self.session.headers.update(headers)

        match method:
            case 'post':
                response = self.session.post(url, json=request_body)
            case 'get': 
                response = self.session.get(url, json=request_body)
            case _ :
                raise Exception('Invalid request method')

        self._handle_request_exception(response)

        try:
            return response.json()
        except ValueError:
            return {"error": f"Could not parse JSON: {response.text}"}
    
    def _sign_query(
            self, 
            instruction_type: Literal[
                'balanceQuery', 
                'depositAddressQuery', 
                'depositQueryAll', 
                'fillHistoryQueryAll' ,
                'positionQuery',
                'orderCancel',
                'orderCancelAll', 
                'orderExecute',
                'orderHistoryQueryAll',
                'orderQuery',
                'orderQueryAll',
                'withdraw',
                'withdrawalQueryAll',
            ], 
            timestamp: int ,
            query_data: dict = None,
            window: int = 60000
        ):
        
        if query_data != None:
            sorted_data = dict(sorted(query_data.items()))
            if 'reduceOnly' in sorted_data:
                sorted_data['reduceOnly'] = str(sorted_data['reduceOnly']).lower()
            query_string = '&'.join([f"{key}={value}" for key, value in sorted_data.items()])
            query_string += f"&timestamp={timestamp}&window={window}"
        else: 
            query_string = f"timestamp={timestamp}&window={window}"
                

        signing_string = f"instruction={instruction_type}&{query_string}"
        signature = self._sign_message_b64(signing_string)

        return signature

    def get_balances(self, symbol: Literal['ALL'] = 'ALL'): 

        url_path = 'api/v1/capital'

        balances = self._query('balanceQuery','get', url_path)

        if symbol == 'ALL': 
            return balances
        else:
            return float(balances[symbol]['available'])
    
    def get_deposit_address(self, chain:Literal['Solana', 'Bitcoin', 'Ethereum', 'Polygon'] = 'Solana'): 

        url_path = f'wapi/v1/capital/deposit/address?blockchain={chain}'

        query_data = {
            'blockchain': chain
        }

        address = self._query('depositAddressQuery', 'get', url_path, query_data)['address']

        return address
    
    @error_handler('requesting volume failed', attempts=GET_VOLUME_RETRIES)
    def get_volume(self, ):

        url_path = f'wapi/v1/history/fills'

        order_history = self._query('fillHistoryQueryAll', 'get', url_path)

        volume = 0
        for order in order_history: 
            volume = volume + float(order['price']) * float(order['quantity'])

        return round(volume,2)
    
    @error_handler('getting open orders')
    def get_open_positions(self,): 

        url_path = f'api/v1/position'

        positions = self._query('positionQuery', 'get', url_path)

        return positions
    
    def _get_limit_data(self, symbol:str, amount_usd:float, side:Literal['Ask', 'Bid']): 

        url = f'{self.base_url}api/v1/depth?symbol={symbol}'

        response = self.session.get(url)

        assert response.status_code == 200, 'failed to get price'
        data = response.json()

        if side == 'Bid':
            side = 'asks'
            price = data[side][0][0]
        else: 
            side ='bids'
            price = data[side][-1][0]

        token_decimals = self.get_token_decimals(symbol)

        amount = amount_usd/float(price)
        amount = str(floor_decimal(amount, token_decimals))

        if float(amount) == 0 and side == 'asks':
            raise Exception('Buy amount is smaller than the minimal amount')

        return price, amount      
   
    
    def post_limit_order(self, symbol:str, side: Literal['Bid', 'Ask'], amount_usd:float=0, amount_token:float=0, timeInForce: Literal['IOC', 'FOK', 'GTC'] = 'IOC', postOnly: bool = False): #отдельно сделать функцию sell_all_token, которая принимает на вход значение токена, сама берет балик и продает 
        
        #ask - sell 
        #bid - buy 

        price, quantity = self._get_limit_data(symbol, amount_usd, side)

        url_path = 'api/v1/order'
        
        payload = {
            'orderType': 'Limit',
            'price': price,
            'quantity': quantity if amount_token ==0 else str(amount_token),
            'side': side,
            'symbol': symbol,
            'timeInForce': timeInForce
        }

        order = self._query('orderExecute', 'post', url_path, payload, payload)

        return order 
    
    @error_handler('opening position')
    def open_futures_pos(self, symbol:str, side: Literal['Bid', 'Ask'], amount_usd:float=0, amount_token:float=0, timeInForce: Literal['IOC', 'FOK', 'GTC'] = 'GTC', postOnly: bool = False ): 

        price, quantity = self._get_limit_data(symbol, amount_usd, side)

        url_path = 'api/v1/order'
        
        payload = {
            'orderType': 'Market',
            'quantity': quantity if amount_token ==0 else str(amount_token),
            'side': side,
            'symbol': symbol,
            'timeInForce': timeInForce, 
            'reduceOnly': False,
        }

        order = self._query('orderExecute', 'post', url_path, payload, payload)

        if order['status'] == 'Filled':
            logger.success(f'{self.public_key_b64}: order filled')
            return 1
        else: 
            logger.warning(f'{self.public_key_b64}: order failed to fill - order details: {order}')
            return 0
    
    @error_handler('closing position')
    def close_futures_pos(self,symbol:str, side_of_opened_pos: Literal['Bid', 'Ask'], size_of_opened_pos: float, timeInForce: Literal['IOC', 'FOK', 'GTC'] = 'GTC'): 
        
        logger.info(f'{self.public_key_b64}: closing position on {symbol}')
        side = 'Bid' if side_of_opened_pos == 'Ask' else 'Ask'

        url_path = 'api/v1/order'
        payload = {
            'orderType': 'Market',
            'quantity': str(abs(size_of_opened_pos)),
            'side': side,
            'symbol': symbol,
            'timeInForce': timeInForce, 
            'reduceOnly': True,
        }
        order = self._query('orderExecute', 'post', url_path, payload, payload)
        if order['status'] == 'Filled':
            logger.success(f'{self.public_key_b64}: order filled')
            return 1
        else: 
            logger.warning(f'{self.public_key_b64}: order failed to fill - order details: {order}')
            return 0

    def get_withdraw_address(self,):

        with open(DEFAULT_DEPOSIT_ADDRESSES, 'r') as f: 
            dep_addresses = f.read().splitlines()

        with open(DEFAULT_PRIVATE_KEYS, 'r') as f: 
            privates = f.read().splitlines()
                
        assert len(privates) == len(dep_addresses), 'Amount of private keys is not the same as amount of withdraw addresses. Please check'

        n = privates.index(str(self.private_key))
        dep_address = dep_addresses[n]

        return dep_address

    @error_handler('withdrawing funds')
    def withdraw(self, percent_to_withdraw:list[float] | int = 100, blockchain: Literal['Solana', 'Ethereum', 'Polygon', 'Bitcoin'] = 'Solana', symbol: str = 'USDC'): 
        
        addr = self.get_withdraw_address()
        balance = float( self.get_balances(symbol))
        
        quantity = round(balance * random.uniform(*percent_to_withdraw)/100, 1) if percent_to_withdraw != 100 else str(balance).split('.')[0] + '.' + str(balance).split('.')[1][:1]
        
        url_path = f'wapi/v1/capital/withdrawals'
        print(balance)
        print(quantity)
        payload = {
            'address': addr,
            'blockchain': blockchain,
            'quantity': str(quantity),
            'symbol': symbol
        }
        withdrawal = self._query('withdraw', 'post', url_path, payload, payload)

        return withdrawal
    
    def close_all_positions(self,): 

        positions = self.get_open_positions()
        
        if len(positions) < 1: 
            logger.info(f'{self.public_key_b64}: No positions to close')
            return 0

        for position in positions: 
            pos_size = float(position['netQuantity'])
            side = 'Bid' if pos_size > 0 else 'Ask'
            res = self.close_futures_pos(position['symbol'], side, pos_size)
            if res and position!=positions[-1]: 
                sleeping('action')
        return 1

    def check_all_positions(self,): 

        positions = self.get_open_positions()

        if len(positions) < 1: 
            logger.info(f'{self.public_key_b64}: No open positions')

        for position in positions: 
            pos_size = float(position['netQuantity'])
            side = 'Bid' if pos_size > 0 else 'Ask'
            logger.opt(colors=True).info(f'{self.public_key_b64}: <m>{position["symbol"]}</m> {"<green>LONG</green>" if side == "Bid" else "<red>SHORT</red>"} position - size: {abs(pos_size)}')

    def get_overall_balance(self,): 

        balances = self.get_balances()
        total_balance = 0
        for token in balances.keys(): 

            if token == 'USDC': 
                total_balance += float(balances['USDC']['available'])
                continue

            decimals = self.get_token_decimals(f'{token}_USDC')
            balance = float(balances[token]['available'])
            floored_balance = floor_decimal(balance , decimals)

            if floored_balance != 0 :

                price = self.get_token_price(f'{token}_USDC')
                time.sleep(1)
                total_balance = total_balance + balance*price

        return round(total_balance, 2)

    def get_token_balances(self,):   
        balances = self.get_balances()
        total_balance = 0
        positions = []
        for token in balances.keys(): 

            if token == 'USDC': 
                total_balance += float(balances['USDC']['available'])
                
                continue

            decimals = self.get_token_decimals(f'{token}_USDC')
            balance = float(balances[token]['available'])
            floored_balance = floor_decimal(balance , decimals)

            if floored_balance != 0 :

                price = self.get_token_price(f'{token}_USDC')
                time.sleep(1)
                total_balance = total_balance + balance*price
                
                positions.append([token, balances[token]['available'], round(balance*price, 2)])

        if len(positions) < 1: 
            logger.info(f'{self.public_key_b64}: No token positions')

        for position in positions: 

            logger.info(f'{self.public_key_b64}: {position[2]} USD in {position[1]} {position[0]} ')

        logger.info(f'{self.public_key_b64}: Total balance: {total_balance} USD')


    #нужен вывод 
