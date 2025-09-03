import yfinance as yf
import pandas as pd
import json
import os
from datetime import datetime
from smolagents import Tool  # Assuming the base Tool class is available

class StockDataTool(Tool):
    name = "stock_data_tool"
    description = (
        """A tool that downloads 50 days of daily stock price data for one or more user-provided 
        stock tickers (e.g., 'AAPL,005930.KS'), and returns the price data and trading volumes. 
        Additionally, it saves the results as a JSON file in the current directory. The tool also fetches 
        real-time price data for the requested tickers."""
    )
    inputs = {
        "tickers": {
            "type": "string",
            "description": "Comma-separated list of stock tickers (e.g., 'AAPL,005930.KS')"
        }
    }
    output_type = "any"
    
    def get_stock_price(self, ticker):
        """
        주어진 티커(종목 코드)의 실시간 주가를 조회하는 함수
        
        Args:
            ticker (str): 주식 종목 코드 (예: 'AAPL', '005930.KS')
            
        Returns:
            dict: 주식 정보 (가격, 변화량, 변화율 등)
        """
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            try:
                company_name = info.get('shortName', '정보 없음')
                current_price = info.get('currentPrice', info.get('regularMarketPrice', 0))
                previous_close = info.get('previousClose', 0)
                change = current_price - previous_close if previous_close else 0
                change_percent = (change / previous_close * 100) if previous_close else 0
                market_cap = info.get('marketCap', 0)
                volume = info.get('volume', 0)
                
                result = {
                    "ticker": ticker,
                    "company_name": company_name,
                    "current_price": current_price,
                    "change": change,
                    "change_percent": change_percent,
                    "previous_close": previous_close,
                    "market_cap": market_cap,
                    "volume": volume,
                    "time": current_time
                }
                
                return result
                
            except Exception as e:
                return {"error": str(e)}
            
        except Exception as e:
            return {"error": str(e)}
    
    def forward(self, tickers: str) -> str:
        ticker_list = [ticker.strip() for ticker in tickers.split(",") if ticker.strip()]
        if not ticker_list:
            raise ValueError("No valid tickers provided.")
            
        results = {}
        
        for ticker in ticker_list:
            # 실시간 주가 정보
            realtime_data = self.get_stock_price(ticker)
            
            # 250일간의 히스토리컬 데이터 다운로드
            df = yf.download(ticker, period="200d", interval="1d", progress=False)
            if df.empty:
                raise ValueError(f"Data for {ticker} could not be found.")
            df.reset_index(inplace=True)
            
            # 결과 딕셔너리에 데이터 추가
            results[ticker] = {
                "realtime_data": realtime_data,
                "historical_data": {
                    "Date": df["Date"].dt.strftime("%Y-%m-%d").values.tolist(),
                    "Open": df["Open"].values.tolist(),
                    "Close": df["Close"].values.tolist(),
                    "Volume": df["Volume"].values.tolist()
                }
            }
            
        results_json = json.dumps(results, indent=2)
        additional_file_path = os.path.join(os.getcwd(), "stock_data.json")
        with open(additional_file_path, "w", encoding="utf-8") as f:
            f.write(results_json)
            
        return results_json

# 사용 예시
if __name__ == "__main__":
    tool = StockDataTool()
    ticker_input = input("주식 종목 코드를 입력하세요 (쉼표로 구분, 예: AAPL,MSFT,005930.KS): ").strip()
    result = tool.forward(ticker_input)