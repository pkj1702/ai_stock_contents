import yfinance as yf
import pandas as pd
import json
import os
import ta
from datetime import datetime
import mplfinance as mpf
import matplotlib.pyplot as plt
import numpy as np

def get_stock_price(ticker):
    """
    주어진 티커(종목 코드)의 실시간 주가 정보를 조회하는 함수
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

def forward(tickers: str) -> str:
    ticker_list = [ticker.strip() for ticker in tickers.split(",") if ticker.strip()]
    if not ticker_list:
        raise ValueError("No valid tickers provided.")
    
    # 티커 유효성 검증
    valid_tickers = []
    invalid_tickers = []
    for ticker in ticker_list:
        try:
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
    for ticker in valid_tickers:
        try:
            # 실시간 주가 정보 조회
            realtime_data = get_stock_price(ticker)
            
            # 국내/해외 주식 구분하여 데이터 다운로드
            if ticker.endswith('.KS') or ticker.endswith('.KQ'):
                print(f"Downloading Korean stock data for {ticker}...")
                df = yf.download(ticker, period="10d", interval="1h", progress=False)
            else:
                print(f"Downloading international stock data for {ticker}...")
                df = yf.download(ticker, period="20d", interval="1h", progress=False)
            
            # 멀티인덱스 확인 및 처리
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            
            if df.empty:
                print(f"Data for {ticker} could not be found. Skipping.")
                continue
            
            # 데이터 타입 변환 처리
            numeric_columns = ['Open', 'High', 'Low', 'Close', 'Volume']
            for col in numeric_columns:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col].squeeze(), errors='coerce')
            
            # NaN 값이 있는 행을 제거
            df = df.dropna(subset=['Open', 'High', 'Low', 'Close'])
            
            if len(df) == 0:
                print(f"After cleaning, no data remains for {ticker}. Skipping.")
                continue
            
            # 날짜 인덱스 확인
            if not isinstance(df.index, pd.DatetimeIndex):
                df.index = pd.to_datetime(df.index)
            
            # 기술적 지표 계산
            close_series = pd.to_numeric(df['Close'].squeeze(), errors='coerce')
            
            # RSI 계산
            rsi_indicator = ta.momentum.RSIIndicator(close=close_series, window=14, fillna=True)
            df['RSI'] = rsi_indicator.rsi()
            
            # 이동평균선 계산
            df['SMA20'] = ta.trend.SMAIndicator(close=close_series, window=20, fillna=True).sma_indicator()
            df['SMA60'] = ta.trend.SMAIndicator(close=close_series, window=60, fillna=True).sma_indicator()
            df['SMA120'] = ta.trend.SMAIndicator(close=close_series, window=120, fillna=True).sma_indicator()
            
            # 볼린저 밴드 계산
            bollinger = ta.volatility.BollingerBands(close=close_series, window=20, window_dev=2, fillna=True)
            df['BB_High'] = bollinger.bollinger_hband()
            df['BB_Low'] = bollinger.bollinger_lband()
            df['BB_Middle'] = bollinger.bollinger_mavg()
            
            # 최신 기술 지표 값 추출
            latest_indicators = {
                "RSI": float(df['RSI'].iloc[-1]) if not pd.isna(df['RSI'].iloc[-1]) else None,
                "SMA20": float(df['SMA20'].iloc[-1]) if not pd.isna(df['SMA20'].iloc[-1]) else None,
                "SMA60": float(df['SMA60'].iloc[-1]) if not pd.isna(df['SMA60'].iloc[-1]) else None,
                "SMA120": float(df['SMA120'].iloc[-1]) if not pd.isna(df['SMA120'].iloc[-1]) else None,
                "BB_High": float(df['BB_High'].iloc[-1]) if not pd.isna(df['BB_High'].iloc[-1]) else None,
                "BB_Middle": float(df['BB_Middle'].iloc[-1]) if not pd.isna(df['BB_Middle'].iloc[-1]) else None,
                "BB_Low": float(df['BB_Low'].iloc[-1]) if not pd.isna(df['BB_Low'].iloc[-1]) else None
            }
            
            # 캔들차트 생성
            plot_filename = f"{ticker}_technical_analysis.png"
            
            # addplot 설정
            apds = [
                mpf.make_addplot(df['SMA20'], panel=0, color='blue', width=1, label='SMA20'),
                mpf.make_addplot(df['SMA60'], panel=0, color='orange', width=1, label='SMA60'),
                mpf.make_addplot(df['SMA120'], panel=0, color='purple', width=1, label='SMA120'),
                mpf.make_addplot(df['BB_High'], panel=0, color='red', width=1, linestyle='--', label='BB High'),
                mpf.make_addplot(df['BB_Middle'], panel=0, color='black', width=1, label='BB Middle'),
                mpf.make_addplot(df['BB_Low'], panel=0, color='green', width=1, linestyle='--', label='BB Low'),
                mpf.make_addplot(df['RSI'], panel=2, color='orange', ylabel='RSI', label='RSI'),
                mpf.make_addplot([70] * len(df), panel=2, color='red', linestyle='dashed', label='Overbought (70)'),
                mpf.make_addplot([30] * len(df), panel=2, color='green', linestyle='dashed', label='Oversold (30)')
            ]
            
            # 차트 생성
            fig, axes = mpf.plot(
                df,
                type='candle',
                volume=True,
                volume_panel=1,
                addplot=apds,
                panel_ratios=(4, 1, 1),
                figratio=(12,10),
                figscale=1.2,
                title=f"{ticker} - Technical Analysis (Candlestick)",
                style='yahoo',
                returnfig=True
            )
            
            # 범례 추가
            axes[0].legend(loc='upper left')
            axes[2].set_title('Volume', loc='left')
            axes[4].legend(loc='upper left')
            
            # 차트 저장
            fig.savefig(plot_filename)
            plt.close(fig)
            
            # 결과 데이터 준비
            df_with_date = df.reset_index()
            results[ticker] = {
                "realtime_data": realtime_data,
                "latest_indicators": latest_indicators,
                "historical_data": {
                    "Date": df_with_date.iloc[:, 0].dt.strftime("%Y-%m-%d").tolist(),
                    "Open": df['Open'].tolist(),
                    "High": df['High'].tolist(),
                    "Low": df['Low'].tolist(),
                    "Close": df['Close'].tolist(),
                    "Volume": df['Volume'].tolist(),
                    "RSI": df['RSI'].tolist(),
                    "SMA20": df['SMA20'].tolist(),
                    "SMA60": df['SMA60'].tolist(),
                    "SMA120": df['SMA120'].tolist(),
                    "BollingerBands": {
                        "High": df['BB_High'].tolist(),
                        "Middle": df['BB_Middle'].tolist(),
                        "Low": df['BB_Low'].tolist()
                    }
                },
                "plot_file": plot_filename
            }
            
        except Exception as e:
            print(f"Error processing {ticker}: {str(e)}")
            import traceback
            traceback.print_exc()
    
    # 결과 저장
    if results:
        try:
            results_json = json.dumps(results, indent=2)
            output_file = "stock_technical_analysis.json"
            with open(output_file, "w", encoding="utf-8") as f:
                f.write(results_json)
            print(f"Results saved to {output_file}")
            return results_json
        except Exception as e:
            print(f"Error saving results to JSON: {str(e)}")
            return json.dumps({"error": str(e)})
    else:
        return "{}"

if __name__ == "__main__":
    ticker_input = input("주식 종목 코드를 입력하세요 (쉼표로 구분, 예: AAPL,MSFT,005930.KS): ").strip()
    result = forward(ticker_input)
    print("분석 완료!") 