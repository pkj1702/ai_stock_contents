import yfinance as yf
import pandas as pd
import json
import os
import ta
from datetime import datetime
import matplotlib.pyplot as plt   # 시각화를 위한 matplotlib 임포트
import matplotlib
matplotlib.use('Agg')
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
        real-time price data for the requested tickers, and visualizes the data in graphs."""
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
            
        # Validate tickers before processing
        valid_tickers = []
        invalid_tickers = []
        
        for ticker in ticker_list:
            try:
                # Try to retrieve basic info to verify the ticker exists
                stock = yf.Ticker(ticker)
                # Check if we can download at least one day of data
                test_df = yf.download(ticker, period="1d", progress=False)
                
                if not test_df.empty:
                    valid_tickers.append(ticker)
                else:
                    invalid_tickers.append(ticker)
                    print(f"Warning: Ticker {ticker} returned empty data. Skipping.")
            except Exception as e:
                invalid_tickers.append(ticker)
                print(f"Invalid ticker: {ticker}. Error: {str(e)}")
        
        if not valid_tickers:
            return "{}"
        
        if invalid_tickers:
            print(f"The following tickers will be skipped: {', '.join(invalid_tickers)}")    
        
        results = {}
        
        for ticker in ticker_list:
            # 실시간 주가 정보
            realtime_data = self.get_stock_price(ticker)
            
            # 250일간의 히스토리컬 데이터 다운로드
            df = yf.download(ticker, period="250d", interval="1d", progress=False)
            if df.empty:
                raise ValueError(f"Data for {ticker} could not be found.")
            df.reset_index(inplace=True)
            
            close_series = df["Close"].squeeze()
                
            # 기술적 지표 계산
            rsi_indicator = ta.momentum.RSIIndicator(close=close_series, window=14)
            df["RSI"] = rsi_indicator.rsi()
            
            sma20 = ta.trend.SMAIndicator(close=close_series, window=20).sma_indicator()
            df["SMA20"] = sma20
            
            sma60 = ta.trend.SMAIndicator(close=close_series, window=60).sma_indicator()
            df["SMA60"] = sma60
            
            sma120 = ta.trend.SMAIndicator(close=close_series, window=120).sma_indicator()
            df["SMA120"] = sma120
            
            bollinger = ta.volatility.BollingerBands(close=close_series, window=20, window_dev=2)
            df["BB_High"] = bollinger.bollinger_hband()
            df["BB_Low"] = bollinger.bollinger_lband()
            df["BB_Middle"] = bollinger.bollinger_mavg()
            
            latest_indicators = {
                "RSI": float(df["RSI"].iloc[-1]) if not pd.isna(df["RSI"].iloc[-1]) else None,
                "SMA20": float(df["SMA20"].iloc[-1]) if not pd.isna(df["SMA20"].iloc[-1]) else None,
                "SMA60": float(df["SMA60"].iloc[-1]) if not pd.isna(df["SMA60"].iloc[-1]) else None,
                "SMA120": float(df["SMA120"].iloc[-1]) if not pd.isna(df["SMA120"].iloc[-1]) else None,
                "BB_High": float(df["BB_High"].iloc[-1]) if not pd.isna(df["BB_High"].iloc[-1]) else None,
                "BB_Middle": float(df["BB_Middle"].iloc[-1]) if not pd.isna(df["BB_Middle"].iloc[-1]) else None,
                "BB_Low": float(df["BB_Low"].iloc[-1]) if not pd.isna(df["BB_Low"].iloc[-1]) else None
            }
            
            # 그래프 시각화 생성 (2개의 subplot: 상단은 가격 및 이동평균/볼린저 밴드, 하단은 RSI)
            fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True)
            
            # 가격 및 이동평균, 볼린저 밴드 플롯
            ax1.plot(df["Date"], df["Close"], label="Close Price")
            ax1.plot(df["Date"], df["SMA20"], label="SMA20")
            ax1.plot(df["Date"], df["SMA60"], label="SMA60")
            ax1.plot(df["Date"], df["SMA120"], label="SMA120")
            ax1.plot(df["Date"], df["BB_High"], label="Bollinger High", linestyle='--', alpha=0.7)
            ax1.plot(df["Date"], df["BB_Middle"], label="Bollinger Middle", linestyle='--', alpha=0.7)
            ax1.plot(df["Date"], df["BB_Low"], label="Bollinger Low", linestyle='--', alpha=0.7)
            ax1.set_title(f"{ticker} Price and Moving Averages")
            ax1.set_ylabel("Price")
            ax1.legend()
            
            # RSI 플롯 및 과매수/과매도 라인 표시
            ax2.plot(df["Date"], df["RSI"], label="RSI", color="orange")
            ax2.axhline(70, color='red', linestyle='--', label="Overbought")
            ax2.axhline(30, color='green', linestyle='--', label="Oversold")
            ax2.set_title(f"{ticker} RSI (14-day)")
            ax2.set_ylabel("RSI")
            ax2.set_xlabel("Date")
            ax2.legend()
            
            plt.tight_layout()
            
            # 그래프를 파일로 저장
            plot_filename = f"{ticker}_technical_analysis.png"
            plt.savefig(plot_filename)
            plt.close()
            
            # 결과 딕셔너리에 plot 파일명 추가
            results[ticker] = {
                "realtime_data": realtime_data,
                "latest_indicators": latest_indicators,
                "historical_data": {
                    "Date": df["Date"].dt.strftime("%Y-%m-%d").values.tolist(),
                    "Open": df["Open"].values.tolist(),
                    "Close": df["Close"].values.tolist(),
                    "Volume": df["Volume"].values.tolist(),
                    "RSI": df["RSI"].values.tolist(),
                    "SMA20": df["SMA20"].values.tolist(),
                    "SMA60": df["SMA60"].values.tolist(),
                    "SMA120": df["SMA120"].values.tolist(),
                    "BollingerBands": {
                        "High": df["BB_High"].values.tolist(),
                        "Middle": df["BB_Middle"].values.tolist(),
                        "Low": df["BB_Low"].values.tolist()
                    }
                },
                "plot_file": plot_filename
            }
            
        results_json = json.dumps(results, indent=2)
        additional_file_path = os.path.join(os.getcwd(), "stock_technical_analysis.json")
        with open(additional_file_path, "w", encoding="utf-8") as f:
            f.write(results_json)
            
        return results_json

# 사용 예시
if __name__ == "__main__":
    tool = StockAnalysisTool()
    ticker_input = input("주식 종목 코드를 입력하세요 (쉼표로 구분, 예: AAPL,MSFT,005930.KS): ").strip()
    result = tool.forward(ticker_input)
