
from config import * 
from utils import * 
from runner.runner import Runner
from constants import LOGO, DEFAULT_PRIVATE_KEYS, PROJECT

logger.remove()
logger.add(
    sys.stdout,
    format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> |  <level>{message}</level>",
    colorize=True
)

def main(): 
    
    logger.opt(raw=True).info(LOGO)
    logger.opt(raw=True, colors=True).info("<red>"+PROJECT+"</red>")
    with open(DEFAULT_PRIVATE_KEYS, 'r') as file:
        private_keys = file.read().splitlines()
    runner = Runner(private_keys)
    runner.run()

if __name__ == '__main__': 
    main()