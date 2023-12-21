import logging
import dotenv
logging.basicConfig(level=logging.INFO)
dotenv.load_dotenv()
logging.info(f'Environment variables loaded and logging setup.')