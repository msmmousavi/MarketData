from flask import Flask
import MarketData  

app = Flask(__name__)

@app.route("/")
def main():
    # فرض کن توی MarketData تابع main داری که خروجی پیام رو برمی‌گردونه
    result = MarketData.main()  # یا تابعی که متن گزارش رو برمی‌گردونه
    return f"<pre>{result}</pre>"  # فرمت ساده متن داخل <pre> برای نمایش بهتر

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
