import yfinance as yf
import pandas as pd
import json
import os
import ta
from datetime import datetime
import mplfinance as mpf
import matplotlib.pyplot as plt
import numpy as np

from smolagents import Tool  # Assuming the base Tool class is available

class StockAnalysisShort(Tool):
    name = "stock_analysis_tool"
    description = (
        """A tool that downloads stock price data for one or more user-provided 
        stock tickers (e.g., 'AAPL,005930.KS'), calculates technical indicators (14-day RSI, 
        20-day simple moving average, 60-day simple moving average, 120-day simple moving average, 
        and Bollinger Bands with a 20-day window and 2 standard deviations), 
        and returns the calculated numeric values as a dictionary. 
        It also includes open prices and trading volumes. Additionally, 
        it saves the results as a JSON file in the current directory. The tool now also fetches 
        real-time price data for the requested tickers, and visualizes the data in candlestick charts."""
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

    def forward(self, tickers: str) -> str:
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
                realtime_data = self.get_stock_price(ticker)
                
                # 모든 주식에 대해 동일한 파라미터로 데이터 다운로드
                print(f"Downloading stock data for {ticker}...")
                df = yf.download(ticker, period="15d", interval="1h", progress=False)
                
                # 멀티인덱스 확인 및 처리
                print(f"DataFrame shape for {ticker}: {df.shape}")
                print(f"DataFrame columns type: {type(df.columns)}")
                print(f"DataFrame columns: {df.columns.tolist()}")
                
                # 멀티인덱스 컬럼인 경우 처리
                if isinstance(df.columns, pd.MultiIndex):
                    print("Multi-level columns detected, flattening...")
                    # 첫번째 레벨의 컬럼 이름만 사용
                    df.columns = df.columns.get_level_values(0)
                    print(f"New columns: {df.columns.tolist()}")
                
                if df.empty:
                    print(f"Data for {ticker} could not be found. Skipping.")
                    continue
                
                # 데이터 타입 변환 처리
                numeric_columns = ['Open', 'High', 'Low', 'Close', 'Volume']
                
                for col in numeric_columns:
                    if col not in df.columns:
                        print(f"Column {col} not found in DataFrame for {ticker}")
                        continue
                    
                    # NaN 값을 먼저 처리하여 숫자형으로 변환
                    df[col] = df[col].fillna(0).astype(float)
                
                # NaN 값이 있는 행을 제거
                df = df.dropna(subset=['Open', 'High', 'Low', 'Close'])
                
                if len(df) == 0:
                    print(f"After cleaning, no data remains for {ticker}. Skipping.")
                    continue
                
                # 날짜가 인덱스에 있는지 확인
                if not isinstance(df.index, pd.DatetimeIndex):
                    print("Converting index to DatetimeIndex...")
                    df.index = pd.to_datetime(df.index)
                
                # 기술적 지표 계산
                close_series = df['Close']
                
                # (1) RSI 계산 - fillna=True 옵션 추가
                rsi_indicator = ta.momentum.RSIIndicator(close=close_series, window=14)
                df['RSI'] = rsi_indicator.rsi()
                
                # RSI 값 상태 확인
                print("RSI values sample:")
                print(df['RSI'].tail(10))
                print(f"RSI NaN count: {df['RSI'].isna().sum()} out of {len(df)}")
                
                # (2) 이동평균선 계산
                df['SMA5'] = ta.trend.SMAIndicator(close=close_series, window=5).sma_indicator()
                df['SMA20'] = ta.trend.SMAIndicator(close=close_series, window=20).sma_indicator()
                df['SMA60'] = ta.trend.SMAIndicator(close=close_series, window=60).sma_indicator()
                
                # (3) 볼린저 밴드 계산
                bollinger = ta.volatility.BollingerBands(close=close_series, window=20, window_dev=2)
                df['BB_High'] = bollinger.bollinger_hband()
                df['BB_Low'] = bollinger.bollinger_lband()
                df['BB_Middle'] = bollinger.bollinger_mavg()
                
                # NaN 값 확인 및 처리
                nan_count = df.isna().sum().sum()
                if nan_count > 0:
                    print(f"Found {nan_count} NaN values in the dataframe")
                    print("NaN counts per column:")
                    print(df.isna().sum())
                    # NaN 값이 있는 행 유지 (그래프에서는 해당 부분만 표시되지 않음)
                    print(f"Keeping rows with NaN values, dataframe shape: {df.shape}")
                
                if len(df) == 0:
                    print(f"No data remains for {ticker}. Skipping.")
                    continue
                
                # 최신 기술 지표 값 추출
                latest_indicators = {
                    "RSI": float(df['RSI'].iloc[-1]) if not pd.isna(df['RSI'].iloc[-1]) else None,
                    "SMA5": float(df['SMA5'].iloc[-1]) if not pd.isna(df['SMA5'].iloc[-1]) else None,
                    "SMA20": float(df['SMA20'].iloc[-1]) if not pd.isna(df['SMA20'].iloc[-1]) else None,
                    "SMA60": float(df['SMA60'].iloc[-1]) if not pd.isna(df['SMA60'].iloc[-1]) else None,
                    "BB_High": float(df['BB_High'].iloc[-1]) if not pd.isna(df['BB_High'].iloc[-1]) else None,
                    "BB_Middle": float(df['BB_Middle'].iloc[-1]) if not pd.isna(df['BB_Middle'].iloc[-1]) else None,
                    "BB_Low": float(df['BB_Low'].iloc[-1]) if not pd.isna(df['BB_Low'].iloc[-1]) else None
                }
                
                # 데이터 타입 확인
                print(f"Data types for {ticker}:")
                print(df.dtypes)
                
                # 캔들차트를 위한 데이터 준비
                # addplot 리스트 생성
                apds = []
                
                # 유효한 데이터가 있는지 확인하는 함수
                def has_valid_data(series, min_valid_points=5):
                    """
                    시리즈에 최소한의 유효한 데이터 포인트가 있는지 확인합니다.
                    min_valid_points: 시리즈가 유효하다고 판단할 최소 데이터 포인트 수
                    """
                    valid_count = (~pd.isna(series)).sum()
                    print(f"Series {series.name} has {valid_count} valid data points out of {len(series)} total")
                    return valid_count >= min_valid_points
                
                # 각 지표에 대해 유효한 데이터가 있는 경우에만 그래프에 추가 (범례 라벨 추가)
                if has_valid_data(df['SMA5']):
                    apds.append(mpf.make_addplot(df['SMA5'], panel=0, color='blue', width=1, label='SMA5'))
                else:
                    print("SMA5 has no valid data points, skipping in plot")
                    
                if has_valid_data(df['SMA20']):
                    apds.append(mpf.make_addplot(df['SMA20'], panel=0, color='orange', width=1, label='SMA20'))
                else:
                    print("SMA20 has no valid data points, skipping in plot")
                    
                if has_valid_data(df['SMA60']):
                    apds.append(mpf.make_addplot(df['SMA60'], panel=0, color='purple', width=1, label='SMA60'))
                else:
                    print("SMA60 has no valid data points, skipping in plot")
                    
                if has_valid_data(df['BB_High']):
                    apds.append(mpf.make_addplot(df['BB_High'], panel=0, color='red', width=1, linestyle='--', label='BB High'))
                else:
                    print("BB_High has no valid data points, skipping in plot")
                    
                if has_valid_data(df['BB_Middle']):
                    apds.append(mpf.make_addplot(df['BB_Middle'], panel=0, color='black', width=1, label='BB Middle'))
                else:
                    print("BB_Middle has no valid data points, skipping in plot")
                    
                if has_valid_data(df['BB_Low']):
                    apds.append(mpf.make_addplot(df['BB_Low'], panel=0, color='green', width=1, linestyle='--', label='BB Low'))
                else:
                    print("BB_Low has no valid data points, skipping in plot")
                    
                # RSI 패널은 유효한 데이터가 있는 경우에만 추가 (최소 10개 이상의 유효한 값 필요)
                has_rsi = False
                if has_valid_data(df['RSI'], min_valid_points=10):
                    # RSI를 패널 2로 변경 (거래량과 분리)
                    apds.append(mpf.make_addplot(df['RSI'], panel=2, color='orange', ylabel='RSI', label='RSI'))
                    apds.append(mpf.make_addplot([70] * len(df), panel=2, color='red', linestyle='dashed', label='Overbought (70)'))
                    apds.append(mpf.make_addplot([30] * len(df), panel=2, color='green', linestyle='dashed', label='Oversold (30)'))
                    has_rsi = True
                else:
                    print("RSI has no valid data points or insufficient points, skipping in plot")
                
                try:
                    # 캔들차트 생성 및 저장
                    plot_filename = f"technical_analysis_short_term.png"
                    print(f"Creating chart for {ticker}...")
                    
                    # 패널 비율 변경: 메인 차트, 거래량, RSI를 위한 3개 패널로 변경 (비율 4:1:1)
                    panel_ratios = (4, 1, 1)
                    
                    # returnfig=True를 사용하여 figure와 axes를 받아옴
                    fig, axes = mpf.plot(
                        df,
                        type='candle',
                        volume=True,
                        volume_panel=1,  # 거래량을 패널 1에 배치
                        addplot=apds,
                        panel_ratios=panel_ratios,  # 수정된 패널 비율
                        figratio=(12,10),  # 세로 크기 약간 증가
                        figscale=1.2,
                        title=f"{ticker} - Technical Analysis (Candlestick)",
                        style='yahoo',
                        returnfig=True  # figure와 axes 반환
                    )
                    
                    # 메인 차트 패널에 범례 추가 (캔들차트 + 이동평균선 + 볼린저 밴드)
                    axes[0].legend(loc='upper left')
                    
                    # 거래량 패널 제목 추가
                    axes[2].set_title('Volume', loc='left')
                    
                    # RSI 패널에 범례 추가 (RSI가 있는 경우)
                    if has_rsi:
                        # 여기서 axes[4]는 RSI 패널 (mplfinance에서 패널 인덱스가 0부터 시작하지만 
                        # 실제 axes 배열에서는 다른 요소들이 포함되어 있어 인덱스가 다를 수 있음)
                        axes[4].legend(loc='upper left')  
                    
                    # 그림 저장
                    fig.savefig(plot_filename)
                    plt.close(fig)
                    
                    print(f"Chart saved as {plot_filename}")
                    
                    # 날짜 형식 변환을 위해 reset_index
                    df_with_date = df.reset_index()
                    
                    # 인덱스 열의 이름 확인 및 처리
                    index_column_name = df_with_date.columns[0]  # reset_index()를 하면 첫 번째 열이 이전 인덱스
                    print(f"Index column name after reset_index: {index_column_name}")
                    
                    # JSON 변환을 위한 데이터 준비
                    results[ticker] = {
                        "realtime_data": realtime_data,
                        "latest_indicators": latest_indicators,
                        "historical_data": {
                            "Date": df_with_date[index_column_name].dt.strftime("%Y-%m-%d").tolist(),
                            "Open": df['Open'].tolist(),
                            "High": df['High'].tolist(),
                            "Low": df['Low'].tolist(),
                            "Close": df['Close'].tolist(),
                            "Volume": df['Volume'].tolist(),
                            "RSI": df['RSI'].tolist(),
                            "SMA5": df['SMA5'].tolist(),
                            "SMA20": df['SMA20'].tolist(),
                            "SMA60": df['SMA60'].tolist(),
                            "BollingerBands": {
                                "High": df['BB_High'].tolist(),
                                "Middle": df['BB_Middle'].tolist(),
                                "Low": df['BB_Low'].tolist()
                            }
                        },
                        "plot_file": plot_filename
                    }
                except Exception as e:
                    print(f"Error plotting chart for {ticker}: {str(e)}")
                    # 오류 발생 시 스택 트레이스 출력
                    import traceback
                    traceback.print_exc()
                    
            except Exception as e:
                print(f"Error processing {ticker}: {str(e)}")
                # 오류 발생 시 스택 트레이스 출력
                import traceback
                traceback.print_exc()
        
        # 결과를 JSON 파일로 저장
        if results:
            try:
                results_json = json.dumps(results, indent=2)
                additional_file_path = os.path.join(os.getcwd(), "stock_technical_analysis_short_term.json")
                with open(additional_file_path, "w", encoding="utf-8") as f:
                    f.write(results_json)
                print(f"Results saved to {additional_file_path}")
                return results_json
            except Exception as e:
                print(f"Error saving results to JSON: {str(e)}")
                return json.dumps({"error": str(e)})
        else:
            return "{}"

# 사용 예시
if __name__ == "__main__":
    tool = StockAnalysisShort()
    ticker_input = input("주식 종목 코드를 입력하세요 (쉼표로 구분, 예: AAPL,MSFT,005930.KS): ").strip()
    result = tool.forward(ticker_input)
    print("분석 완료!")