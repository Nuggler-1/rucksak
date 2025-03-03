from config import *
from utils import * 
import constants
from loguru import logger

class OKX(): 
    def __init__(self, ):
        self.account = ccxt.okx({
        'apiKey': API_KEY,
        'secret': API_SECRET,
	    'password': API_PASSPHRASE,
        'enableRateLimit': True,
        'options': {
            'defaultType': 'spot'
        }
    })

    @error_handler('okx withdrawal')
    def withdraw(self, deposit_address:str, deposit_token: str, deposit_amount: list[float]):

        logger.info(f'Withdrawing {deposit_token} from OKX to {deposit_address}')

        mapping = constants.OKX_MAPPING[deposit_token]
        amount = random.uniform(deposit_amount[0], deposit_amount[1]) 
        rounding = random.randrange(0,3) if deposit_token != 'SOL' else random.randrange(1,3)
        amount = round(amount, rounding)
        mapping = constants.OKX_MAPPING[deposit_token]

        self.account.withdraw(
            code    = mapping['token'],
            amount  = amount,
            address = deposit_address,
            tag     = None, 
            params  = {
                "chain": mapping['network'],
                "fee":mapping['fee'],
                "password":"",
                "toAddr":deposit_address
            }
        )

        logger.success(f'Deposited {deposit_token} from OKX on {deposit_address}')
        return 1

        
