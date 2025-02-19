from flask import Flask, request, jsonify
import requests
import yfinance as yf
import json
from datetime import datetime
import pytz

# 1) Import CORS
from flask_cors import CORS

app = Flask(__name__)

# 2) Enable CORS
CORS(app)

###################################################
# REPLACE THESE WITH YOUR REAL API KEYS
###################################################
ALPHA_VANTAGE_API_KEY = "PQ5YDACTKBCNRKRS"
MARKETSTACK_API_KEY   = "09b0eb7d29e5c82ac215d068f8f134cc"
TWELVE_DATA_API_KEY   = "89c076b1d14d48a1ae90b4f4a304ff4d"
FINNHUB_API_KEY       = "cuq3fh1r01qviv3j0pb0cuq3fh1r01qviv3j0pbg"

API_LOG_FILE = "api_log.json"  # File to store API usage data

###################################################
# FUNCTION TO WRITE API USAGE TO FILE
###################################################
def write_api_log(api_name):
    try:
        with open(API_LOG_FILE, "r") as file:
            api_usage = json.load(file)
    except (FileNotFoundError, json.JSONDecodeError):
        api_usage = {}

    api_usage[api_name] = api_usage.get(api_name, 0) + 1

    with open(API_LOG_FILE, "w") as file:
        json.dump(api_usage, file, indent=4)

###################################################
# FUNCTION TO CHECK MARKET STATUS
###################################################
def get_market_status(market):
    now_utc = datetime.now(pytz.utc)

    # Indian Market (NSE/BSE)
    if market == "IN":
        # Convert UTC -> India time
        india_tz = pytz.timezone("Asia/Kolkata")
        now = now_utc.astimezone(india_tz)

        # Market hours: Mon-Fri, 9:15 AM to 3:30 PM
        open_time = now.replace(hour=9, minute=15, second=0, microsecond=0)
        close_time = now.replace(hour=15, minute=30, second=0, microsecond=0)

        if now.weekday() < 5 and open_time <= now <= close_time:
            return "Open"
        return "Closed"

    # US Market (NYSE/NASDAQ)
    elif market == "GLOBAL":
        # Convert UTC -> Eastern Time
        est_tz = pytz.timezone("America/New_York")
        now = now_utc.astimezone(est_tz)

        # Market hours: Mon-Fri, 9:30 AM to 4:00 PM
        open_time = now.replace(hour=9, minute=30, second=0, microsecond=0)
        close_time = now.replace(hour=16, minute=0, second=0, microsecond=0)

        if now.weekday() < 5 and open_time <= now <= close_time:
            return "Open"
        return "Closed"

    # Crypto Market (24/7)
    elif market == "CRYPTO":
        return "Open"

    return "N/A"

###################################################
# SYMBOL MAPPING FOR ALPHA VANTAGE & MARKETSTACK
###################################################
def map_symbol_for_alpha_vantage(symbol):
    if symbol.endswith(".NS"):
        return symbol.replace(".NS", ".BSE")
    return symbol

def map_symbol_for_marketstack(symbol):
    if symbol.endswith(".NS"):
        return symbol.replace(".NS", ".XNSE")
    if symbol.endswith(".BSE"):
        return symbol.replace(".BSE", ".XBOM")
    return symbol

###################################################
# INDIAN STOCK PRICE (AlphaVantage → MarketStack → yfinance)
###################################################
def get_price_alpha_vantage(symbol):
    mapped_symbol = map_symbol_for_alpha_vantage(symbol)
    try:
        url = (
            f"https://www.alphavantage.co/query"
            f"?function=GLOBAL_QUOTE"
            f"&symbol={mapped_symbol}"
            f"&apikey={ALPHA_VANTAGE_API_KEY}"
        )
        resp = requests.get(url).json()
        if "Global Quote" in resp and "05. price" in resp["Global Quote"]:
            price = float(resp["Global Quote"]["05. price"])
            write_api_log("AlphaVantage")
            return price, "AlphaVantage"
    except Exception as e:
        print("Alpha Vantage error:", e)
    return None, None

def get_price_marketstack(symbol):
    mapped_symbol = map_symbol_for_marketstack(symbol)
    try:
        url = (
            f"http://api.marketstack.com/v1/eod/latest"
            f"?access_key={MARKETSTACK_API_KEY}"
            f"&symbols={mapped_symbol}"
        )
        resp = requests.get(url).json()
        if "data" in resp and len(resp["data"]) > 0:
            price = float(resp["data"][0]["close"])
            write_api_log("MarketStack")
            return price, "MarketStack"
    except Exception as e:
        print("MarketStack error:", e)
    return None, None

def get_price_yfinance(symbol):
    try:
        stock = yf.Ticker(symbol)
        df = stock.history(period="1d")
        if not df.empty:
            price = float(df["Close"].iloc[-1])
            write_api_log("YahooFinance")
            return price, "YahooFinance"
    except Exception as e:
        print("yfinance error:", e)
    return None, None

###################################################
# GLOBAL STOCK PRICE (TwelveData → Finnhub → yfinance)
###################################################
def get_price_twelvedata(symbol):
    try:
        url = f"https://api.twelvedata.com/price?symbol={symbol}&apikey={TWELVE_DATA_API_KEY}"
        resp = requests.get(url).json()
        if "price" in resp:
            write_api_log("TwelveData")
            return float(resp["price"]), "TwelveData"
    except Exception as e:
        print("Twelve Data error:", e)
    return None, None

def get_price_finnhub(symbol):
    try:
        url = f"https://finnhub.io/api/v1/quote?symbol={symbol}&token={FINNHUB_API_KEY}"
        resp = requests.get(url).json()
        if "c" in resp and resp["c"] != 0:
            write_api_log("Finnhub")
            return float(resp["c"]), "Finnhub"
    except Exception as e:
        print("Finnhub error:", e)
    return None, None

###################################################
# CRYPTO PRICE (Binance → CoinGecko)
###################################################
def format_crypto_symbol(symbol):
    return symbol.upper() + "USDT"

def get_price_binance(symbol):
    formatted_symbol = format_crypto_symbol(symbol)
    try:
        url = f"https://api.binance.com/api/v3/ticker/price?symbol={formatted_symbol}"
        resp = requests.get(url).json()
        if "price" in resp:
            write_api_log("Binance")
            return float(resp["price"]), "Binance"
    except Exception as e:
        print("Binance error:", e)
    return None, None

def get_price_coingecko(symbol):
    formatted_symbol = symbol.lower()
    try:
        url = f"https://api.coingecko.com/api/v3/simple/price?ids={formatted_symbol}&vs_currencies=usd"
        resp = requests.get(url).json()
        if formatted_symbol in resp and "usd" in resp[formatted_symbol]:
            write_api_log("CoinGecko")
            return float(resp[formatted_symbol]["usd"]), "CoinGecko"
    except Exception as e:
        print("CoinGecko error:", e)
    return None, None

###################################################
# FETCH PRICE BASED ON MARKET TYPE
###################################################
def fetch_price(symbol, market):
    """
    Priority Order:
      - IN: AlphaVantage → MarketStack → yfinance
      - GLOBAL: TwelveData → Finnhub → yfinance
      - CRYPTO: Binance → CoinGecko
    """
    if market == "IN":
        return get_price_alpha_vantage(symbol) or get_price_marketstack(symbol) or get_price_yfinance(symbol)
    elif market == "GLOBAL":
        return get_price_twelvedata(symbol) or get_price_finnhub(symbol) or get_price_yfinance(symbol)
    elif market == "CRYPTO":
        return get_price_binance(symbol) or get_price_coingecko(symbol)
    return None, None

###################################################
# FLASK ENDPOINT
###################################################
@app.route("/stock", methods=["GET"])
def stock():
    user_symbol = request.args.get("symbol")
    market_param = request.args.get("market")

    if not user_symbol:
        return jsonify({"error": "Stock symbol is required"}), 400

    if market_param not in ["IN", "GLOBAL", "CRYPTO"]:
        return jsonify({"error": "Invalid market. Use 'IN', 'GLOBAL', or 'CRYPTO'"}), 400

    price, source = fetch_price(user_symbol, market_param)
    market_status = get_market_status(market_param)

    if price is None:
        return jsonify({"error": "All APIs failed for this symbol."}), 503

    return jsonify({
        "symbol": user_symbol,
        "price": price,
        "source": source,
        "market_used": market_param,
        "market_status": market_status
    })

@app.route("/")
def home():
    return "Welcome to my Flask Stock API!"

@app.route("/search", methods=["GET"])
def search_symbols():
    # 1) Get the user’s query from the URL
    query = request.args.get("query")
    if not query:
        return jsonify({"error": "Missing query parameter"}), 400

    # 2) Build the Finnhub URL
    url = f"https://finnhub.io/api/v1/search?q={query}&token={FINNHUB_API_KEY}"

    # 3) Call Finnhub
    resp = requests.get(url).json()

    # 4) Return the JSON from Finnhub directly to React
    return jsonify(resp)

@app.route("/search", methods=["GET"])
def search_symbols():
    query = request.args.get("query")
    market = request.args.get("market")  # "CRYPTO", "IN", or "GLOBAL"

    if not query:
        return jsonify({"error": "Missing query"}), 400
    if not market:
        return jsonify({"error": "Missing market"}), 400

    if market == "CRYPTO":
        # Call CoinGecko search endpoint
        url = f"https://api.coingecko.com/api/v3/search?query={query}"
        resp = requests.get(url).json()

        # 'resp["coins"]' is a list of coins
        # Each coin has { id, symbol, name, ... }
        if "coins" in resp:
            # We'll convert it into a standardized format
            results = []
            for coin in resp["coins"]:
                # coin["id"], coin["symbol"], coin["name"]
                item = {
                    "symbol": coin["symbol"].upper(), 
                    "description": coin["name"]
                }
                results.append(item)
            return jsonify({"result": results})
        else:
            return jsonify({"result": []})

    else:
        # For IN or GLOBAL, call Finnhub
        # (same code as your old search, but we can handle both IN and GLOBAL the same)
        finnhub_url = f"https://finnhub.io/api/v1/search?q={query}&token={FINNHUB_API_KEY}"
        finnhub_resp = requests.get(finnhub_url).json()
        # Typically finnhub_resp = {"count":..., "result":[{"symbol":"AAPL","description":"APPLE INC",...}]}
        return jsonify(finnhub_resp)



if __name__ == "__main__":
    app.run(debug=True)
