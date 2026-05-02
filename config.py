import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.environ["BOT_TOKEN"]
ADMIN_CHAT_ID = int(os.environ["ADMIN_CHAT_ID"])
PAYPAL_LINK = os.environ["PAYPAL_LINK"]
SHOP_NAME = os.environ.get("SHOP_NAME", "Vape Shop")
SHOP_INFO = os.environ.get("SHOP_INFO", "Premium vaping products.")
CONTACT_INFO = os.environ.get("CONTACT_INFO", "Contact us via Telegram.")
CATALOG_PATH = os.environ.get("CATALOG_PATH", "catalog.json")
ORDERS_PATH = os.environ.get("ORDERS_PATH", "orders.json")
WEBAPP_URL = os.environ.get("WEBAPP_URL", "")
