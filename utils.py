from loguru import logger
import csv
import requests
import time
import random
import sys
from web3 import Web3
import multiprocessing
from math import ceil, floor
from config import ERR_ATTEMPTS
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from collections import OrderedDict
import config
import base64
import hmac
import ccxt 
import datetime
import collections
import base64
from typing import Literal
from config import *
from constants import DEFAULT_PRIVATE_KEYS, DEFAULT_PROXIES
    
def floor_decimal(value, decimals):
    
    if decimals == 0:
        return int(value)
    else:
        n = 10 ** decimals
        return floor(value * n) / n

def intToDecimal(qty, decimal):
    return int(qty * int("".join(["1"] + ["0"]*decimal)))

def decimalToInt(price, decimal):
    return price/ int("".join((["1"]+ ["0"]*decimal)))

def clear_file(file):
    file_to_clear = open(file,'w', encoding="utf-8")
    file_to_clear.close()

def write_to_file(file, result):
    with open(file, "a", encoding="utf-8") as file:
        file.write(str(result[0]) +'\t'+ str(result[1]) + '\n')

def write_results(keys, results, file_name):
    i = 0
    clear_file(file_name)
    for key in keys: 
        write_to_file(file_name,(results[i], key))
        i+=1

def generate_results(file_name, private_keys):

    RESULTS = []
    clear_file(file_name)
    i = 0
    for private_key in private_keys:
        RESULTS.append(0)
        i+=1
    write_results(private_keys, RESULTS, file_name)

def read_results(file_name): 
    
    results = []
    wallets = []
    with open(file_name, 'r') as f: 
        for line in f: 
            data = line.split()
            results.append(data[0])
            wallets.append(data[1])
        
    return results, wallets

def sleeping(type_of_delay = Literal['account', 'action']):

    if type_of_delay == 'action':
        n = random.randrange(config.WAITING_TIME_TILL_NEXT_ACTION[0], config.WAITING_TIME_TILL_NEXT_ACTION[1])
    else: 
        n = random.randrange(config.WAITING_TIME_TILL_NEXT_ACCOUNT[0], config.WAITING_TIME_TILL_NEXT_ACCOUNT[1])
    logger.info(f'Sleeping till next {type_of_delay} {n} secs')
    time.sleep(n)

def update_results(private_key, file_name='results/RESULTS.txt'):

    results, keys = read_results(file_name)
    n = keys.index(private_key)
    results[n] = int(results[n]) + 1
    write_results(keys,results, file_name)

def error_handler(error_msg, attempts = ERR_ATTEMPTS):
    def decorator(func):
        def wrapper(*args, **kwargs):
            for i in range(0, attempts):
                try: 
                    return func(*args, **kwargs)
                except Exception as e:
                    logger.error(f"{error_msg}: {str(e)}")
                    logger.info(f'Retrying in 10 sec. Attempts left: {attempts-i}')
                    time.sleep(10)
                    if i == attempts-1: 
                        return 0
        return wrapper
    return decorator

def get_proxy(private): 

    check_proxy()

    with open(DEFAULT_PROXIES, 'r') as f: 
        proxies = f.read().splitlines()
        if len(proxies) == 0:
            return None
        
    with open(DEFAULT_PRIVATE_KEYS, 'r') as f: 
        privates = f.read().splitlines()
            
    n = privates.index(str(private))
    proxy = proxies[n]
    proxy = {
        'http': f'http://{proxy}' if not proxy.startswith('http://') else proxy,
        'https':f'http://{proxy}' if not proxy.startswith('http://') else proxy
    }
    return proxy

def check_proxy():

    with open(DEFAULT_PROXIES, 'r') as f: 
        proxies = f.read().splitlines()
    with open(DEFAULT_PRIVATE_KEYS, 'r') as f: 
        stark_privates = f.read().splitlines()

    if len(proxies) < len(stark_privates) and len(proxies) != 0:
        logger.error('Proxies do not match private keys')
        sys.exit()


def match_api_key_with_address(address, api_keys):

    for api_key in api_keys:
        
        if address in api_key: 
             
            return [api_key[1], api_key[2]]
        
    return 0


def split_list_into_chunks(lst, n):
  
  size = ceil(len(lst) / n)

  return list(
    map(lambda x: lst[x * size:x * size + size],
    list(range(n)))
  )
