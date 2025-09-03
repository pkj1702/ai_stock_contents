import yfinance as yf
import pandas as pd
import json
import os
import ta
from datetime import datetime
from smolagents import Tool  # Assuming the base Tool class is available

class StockAnalysisTool(Tool):
    name = "stock_analysis_tool"
    description = (
        """A tool that downloads 250 days of daily stock price data for one or more user-provided 
        stock tickers (e.g., 'AAPL,005930.KS'), calculates technical indicators (14-day RSI, 
        20-day simple moving average, 60-day simple moving average, 120-day simple moving average, 
        and Bollinger Bands with a 20-day window and 2 standard deviations), 
        and returns the calculated numeric values as a dictionary. 
        It also includes open prices and trading volumes. Additionally, 
        it saves the results as a JSON file in the current directory. The tool now also fetches 
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
            # 티커 객체 생성
            stock = yf.Ticker(ticker)
            
            # 종목 정보 가져오기
            info = stock.info
            
            # 현재 시간
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # 필요한 정보 추출
            # 종목에 따라 일부 정보가 없을 수 있어 예외 처리
            try:
                company_name = info.get('shortName', '정보 없음')
                current_price = info.get('currentPrice', info.get('regularMarketPrice', 0))
                previous_close = info.get('previousClose', 0)
                change = current_price - previous_close if previous_close else 0
                change_percent = (change / previous_close * 100) if previous_close else 0
                market_cap = info.get('marketCap', 0)
                volume = info.get('volume', 0)
                
                # 결과 반환
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
            # 실시간 주가 정보 가져오기
            realtime_data = self.get_stock_price(ticker)
            
            # 히스토리컬 데이터 가져오기
            df = yf.download(ticker, period="250d", interval="1d", progress=False)
            if df.empty:
                raise ValueError(f"Data for {ticker} could not be found.")
            df.reset_index(inplace=True)
            
            # [핵심] RSI 계산에 사용할 종가를 1차원 Series로 만든다
            close_series = df["Close"].squeeze()
                
            # RSI (14일)
            rsi_indicator = ta.momentum.RSIIndicator(close=close_series, window=14)
            df["RSI"] = rsi_indicator.rsi()
            
            # 20일 이동평균선
            sma20 = ta.trend.SMAIndicator(close=close_series, window=20).sma_indicator()
            df["SMA20"] = sma20
            
            # 60일 이동평균선
            sma60 = ta.trend.SMAIndicator(close=close_series, window=60).sma_indicator()
            df["SMA60"] = sma60
            
            # 120일 이동평균선
            sma120 = ta.trend.SMAIndicator(close=close_series, window=120).sma_indicator()
            df["SMA120"] = sma120
            
            # 볼린저 밴드 (20일, 2표준편차)
            bollinger = ta.volatility.BollingerBands(close=close_series, window=20, window_dev=2)
            df["BB_High"] = bollinger.bollinger_hband()
            df["BB_Low"] = bollinger.bollinger_lband()
            df["BB_Middle"] = bollinger.bollinger_mavg()
            
            # 최근 기술적 지표 값 가져오기
            latest_indicators = {
                "RSI": float(df["RSI"].iloc[-1]) if not pd.isna(df["RSI"].iloc[-1]) else None,
                "SMA20": float(df["SMA20"].iloc[-1]) if not pd.isna(df["SMA20"].iloc[-1]) else None,
                "SMA60": float(df["SMA60"].iloc[-1]) if not pd.isna(df["SMA60"].iloc[-1]) else None,
                "SMA120": float(df["SMA120"].iloc[-1]) if not pd.isna(df["SMA120"].iloc[-1]) else None,
                "BB_High": float(df["BB_High"].iloc[-1]) if not pd.isna(df["BB_High"].iloc[-1]) else None,
                "BB_Middle": float(df["BB_Middle"].iloc[-1]) if not pd.isna(df["BB_Middle"].iloc[-1]) else None,
                "BB_Low": float(df["BB_Low"].iloc[-1]) if not pd.isna(df["BB_Low"].iloc[-1]) else None
            }
            
            # 결과 딕셔너리화
            results[ticker] = {
                "realtime_data": realtime_data,  # 실시간 데이터 추가
                "latest_indicators": latest_indicators,  # 최신 기술적 지표 추가
                "historical_data": {
                    "Date": df["Date"].dt.strftime("%Y-%m-%d").values.tolist(),
                    "Open": df["Open"].values.tolist(),
                    "Close": df["Close"].values.tolist(),
                    "Volume": df["Volume"].values.tolist(),  # 거래량
                    "RSI": df["RSI"].values.tolist(),
                    "SMA20": df["SMA20"].values.tolist(),
                    "SMA60": df["SMA60"].values.tolist(),
                    "SMA120": df["SMA120"].values.tolist(),
                    "BollingerBands": {
                        "High": df["BB_High"].values.tolist(),
                        "Middle": df["BB_Middle"].values.tolist(),
                        "Low": df["BB_Low"].values.tolist()
                    }
                }
            }
            
        results_json = json.dumps(results, indent=2)
        additional_file_path = os.path.join(os.getcwd(), "stock_analysis.json")
        with open(additional_file_path, "w", encoding="utf-8") as f:
            f.write(results_json)
            
        return results_json

# 사용 예시
if __name__ == "__main__":
    # 도구 생성
    tool = StockAnalysisTool()
    
    # 사용자로부터 티커 입력 받기
    ticker_input = input("주식 종목 코드를 입력하세요 (쉼표로 구분, 예: AAPL,MSFT,005930.KS): ").strip()
    
    # 분석 실행
    result = tool.forward(ticker_input)