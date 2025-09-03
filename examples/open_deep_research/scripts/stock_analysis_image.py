import yfinance as yf
import pandas as pd
import matplotlib.pyplot as plt
import ta
import tempfile
import os
from smolagents import Tool  # Assuming the base Tool class is available in this module

class StockAnalysisTool(Tool):
    name = "stock_analysis_tool"
    description = (
        """A tool that downloads 250 days of daily stock price data for one or more user-provided 
        stock tickers (e.g., 'AAPL,005930.KS'), calculates technical indicators (14-day RSI, 
        20-day simple moving average, and Bollinger Bands with a 20-day window and 2 standard deviations), 
        and generates charts for each stock."""
    )
    inputs = {
        "tickers": {
            "type": "string",
            "description": "Comma-separated list of stock tickers (e.g., 'AAPL,005930.KS')"
        }
    }
    output_type = "image"

    def forward(self, tickers: str) -> str:
        # 입력된 ticker 문자열을 콤마로 분리하여 리스트로 변환
        ticker_list = [ticker.strip() for ticker in tickers.split(",") if ticker.strip()]
        if not ticker_list:
            raise ValueError("No valid tickers provided.")
        num_tickers = len(ticker_list)
        
        # 각 ticker마다 3개의 플롯(행)을 생성하므로, (3 x num_tickers) 형태의 서브플롯 생성
        fig, axes = plt.subplots(nrows=3, ncols=num_tickers, figsize=(5 * num_tickers, 12))
        
        # ticker가 하나일 경우에도 axes를 2차원 배열로 변환하여 통일성 유지
        if num_tickers == 1:
            axes = [[axes[0]], [axes[1]], [axes[2]]]
        
        for col, ticker in enumerate(ticker_list):
            # 250일치 일일 주가 데이터를 다운로드
            df = yf.download(ticker, period="250d", interval="1d")
            if df.empty:
                raise ValueError(f"Data for {ticker} could not be found.")
            df.reset_index(inplace=True)
            close_series = df["Close"].squeeze()
            
            # 14일 RSI 계산
            rsi_indicator = ta.momentum.RSIIndicator(close=close_series, window=14)
            df["RSI"] = rsi_indicator.rsi()
            
            # 20일 단순 이동평균(SMA) 계산
            sma_indicator = ta.trend.SMAIndicator(close=close_series, window=20)
            df["SMA20"] = sma_indicator.sma_indicator()
            
            # 볼린저 밴드 계산 (20일 창, 2 표준편차)
            bollinger = ta.volatility.BollingerBands(close=close_series, window=20, window_dev=2)
            df["BB_High"] = bollinger.bollinger_hband()
            df["BB_Low"] = bollinger.bollinger_lband()
            df["BB_Middle"] = bollinger.bollinger_mavg()
            
            # --- Plot 1: 주가와 볼린저 밴드 ---
            ax = axes[0][col]
            ax.plot(df["Date"], df["Close"], label="Close")
            ax.plot(df["Date"], df["BB_High"], label="Bollinger High", linestyle="--")
            ax.plot(df["Date"], df["BB_Middle"], label="Bollinger Middle", linestyle="--")
            ax.plot(df["Date"], df["BB_Low"], label="Bollinger Low", linestyle="--")
            ax.set_title(f"{ticker} Price and Bollinger Bands")
            ax.set_xlabel("Date")
            ax.set_ylabel("Price")
            ax.legend()
            ax.grid(True)
            
            # --- Plot 2: RSI ---
            ax = axes[1][col]
            ax.plot(df["Date"], df["RSI"], label="RSI", color="orange")
            ax.axhline(70, color="red", linestyle="--", label="Overbought")
            ax.axhline(30, color="green", linestyle="--", label="Oversold")
            ax.set_title("Relative Strength Index (RSI)")
            ax.set_xlabel("Date")
            ax.set_ylabel("RSI")
            ax.legend()
            ax.grid(True)
            
            # --- Plot 3: 주가와 20일 단순 이동평균 ---
            ax = axes[2][col]
            ax.plot(df["Date"], df["Close"], label="Close")
            ax.plot(df["Date"], df["SMA20"], label="20-day SMA", color="magenta")
            ax.set_title("Price and 20-day Simple Moving Average")
            ax.set_xlabel("Date")
            ax.set_ylabel("Price")
            ax.legend()
            ax.grid(True)
        
        plt.tight_layout()
        
        # 현재 작업 디렉토리에 "stock_analysis.png"로도 저장 (추가 저장)
        additional_file_path = os.path.join(os.getcwd(), "stock_analysis.png")
        plt.savefig(additional_file_path)
        
        # 임시 파일로 저장 후 그 파일 경로를 반환 (기존 동작)
        tmpfile = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
        plt.savefig(tmpfile.name)
        plt.close(fig)
        return tmpfile.name
