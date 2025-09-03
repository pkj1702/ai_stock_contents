import yfinance as yf
import pandas as pd
import json
import os
import ta
from datetime import datetime, timedelta
import mplfinance as mpf
import matplotlib.pyplot as plt
import numpy as np

from smolagents import Tool  # Assuming the base Tool class is available

class ShortStockMarkTool(Tool):
    name = "stock_analysis_tool"
    description = (
        """A tool that downloads stock price data for one or more user-provided 
        stock tickers (e.g., 'AAPL,005930.KS'), calculates technical indicators such as
        simple moving averages (5-day, 20-day, 60-day), 14-day RSI, and Bollinger Bands
        with a 20-day window and 2 standard deviations, and returns the calculated values as a dictionary. 
        The tool also fetches real-time price data, visualizes the data in candlestick charts,
        and allows highlighting specific timestamps, adding support lines (in blue) and resistance lines (in red) on the charts.
        All technical indicators (SMAs, RSI, and Bollinger Bands) are optional and can be toggled on/off.
        """
    )
    inputs = {
        "tickers": {
            "type": "string",
            "description": "Comma-separated list of stock tickers (e.g., 'AAPL,005930.KS')"
        },
        "highlight_timestamps": {  
            "type": "string",
            "description": "Optional comma-separated list of timestamps to highlight on the chart (format: YYYY-MM-DD HH, ex: 2023-03-15 14)",
            "nullable": True
        },
        "support_level": {
            "type": "string",
            "description": "Optional comma-separated list of price levels to show as support lines (blue color)",
            "nullable": True
        },
        "resistance_level": {
            "type": "string",
            "description": "Optional comma-separated list of price levels to show as resistance lines (red color)",
            "nullable": True
        },
        "show_sma5": {
            "type": "boolean",
            "description": "Whether to calculate and display the 5-hour Simple Moving Average (default: False)",
            "nullable": True
        },
        "show_sma20": {
            "type": "boolean",
            "description": "Whether to calculate and display the 20-hour Simple Moving Average (default: False)",
            "nullable": True
        },
        "show_sma60": {
            "type": "boolean",
            "description": "Whether to calculate and display the 60-hour Simple Moving Average (default: False)",
            "nullable": True
        },
        "show_rsi": {
            "type": "boolean",
            "description": "Whether to calculate and display the RSI indicator (default: False)",
            "nullable": True
        },
        "show_bollinger": {
            "type": "boolean",
            "description": "Whether to calculate and display Bollinger Bands (default: False)",
            "nullable": True
        }
    }
    output_type = "any"

    def get_next_available_filename(self):
        """
        Finds the next available technical_analysis[n].png filename
        """
        index = 0
        while True:
            filename = f"technical_analysis{index}.png"
            if not os.path.exists(filename):
                return filename, index
            index += 1

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

    def forward(self, tickers: str, highlight_timestamps: str = None,  # Changed from highlight_dates to highlight_timestamps
                support_level: str = None, resistance_level: str = None,
                show_sma5: bool = False, show_sma20: bool = False, show_sma60: bool = False,
                show_rsi: bool = False, show_bollinger: bool = False) -> str:
        ticker_list = [ticker.strip() for ticker in tickers.split(",") if ticker.strip()]
        if not ticker_list:
            raise ValueError("No valid tickers provided.")
        
        # 강조할 타임스탬프 파싱 - 날짜와 시간(시간만) 포함
        highlight_datetimes = []
        if highlight_timestamps:  # Changed from highlight_dates to highlight_timestamps
            for timestamp_str in highlight_timestamps.split(','):  # Changed variable name
                timestamp_str = timestamp_str.strip()
                try:
                    # 시간 정보가 포함된 경우 (YYYY-MM-DD HH)
                    if len(timestamp_str.split()) > 1:
                        date_part, hour_part = timestamp_str.split()
                        # 시간만 있고 분/초가 없는 경우 "00:00" 추가
                        if ":" not in hour_part:
                            timestamp_str = f"{date_part} {hour_part}:00:00"
                        # 시간과 분이 있지만 초가 없는 경우 ":00" 추가
                        elif hour_part.count(":") == 1:
                            timestamp_str = f"{timestamp_str}:00"
                    
                    # 타임스탬프로 변환
                    date_time = pd.to_datetime(timestamp_str)
                    highlight_datetimes.append(date_time)
                    print(f"Will highlight candle for timestamp: {date_time.strftime('%Y-%m-%d %H:00:00')}")
                except Exception as e:
                    print(f"Invalid timestamp format: {timestamp_str}. Error: {str(e)}")
                    print("Using format YYYY-MM-DD HH. Skipping this timestamp.")
        
        # 지지선 값 파싱
        support_values = []
        if support_level:
            for level in support_level.split(','):
                try:
                    support_values.append(float(level.strip()))
                    print(f"Will add support line at price: {float(level.strip())}")
                except ValueError:
                    print(f"Invalid support level value: {level}. Skipping this level.")
        
        # 저항선 값 파싱
        resistance_values = []
        if resistance_level:
            for level in resistance_level.split(','):
                try:
                    resistance_values.append(float(level.strip()))
                    print(f"Will add resistance line at price: {float(level.strip())}")
                except ValueError:
                    print(f"Invalid resistance level value: {level}. Skipping this level.")
        
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
                
                # 모든 주식에 대해 동일한 설정으로 데이터 다운로드
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
                
                # (1) 이동평균선 계산 (옵션에 따라 계산)
                if show_sma5:
                    print("Calculating 5-day SMA as requested...")
                    df['SMA5'] = ta.trend.SMAIndicator(close=close_series, window=5).sma_indicator()
                else:
                    print("Skipping 5-day SMA calculation as per user request")
                    df['SMA5'] = pd.Series([np.nan] * len(df), index=df.index)

                if show_sma20:
                    print("Calculating 20-day SMA as requested...")
                    df['SMA20'] = ta.trend.SMAIndicator(close=close_series, window=20).sma_indicator()
                else:
                    print("Skipping 20-day SMA calculation as per user request")
                    df['SMA20'] = pd.Series([np.nan] * len(df), index=df.index)

                if show_sma60:
                    print("Calculating 60-day SMA as requested...")
                    df['SMA60'] = ta.trend.SMAIndicator(close=close_series, window=60).sma_indicator()
                else:
                    print("Skipping 60-day SMA calculation as per user request")
                    df['SMA60'] = pd.Series([np.nan] * len(df), index=df.index)
                
                # (2) RSI 계산 - 옵션이 활성화된 경우에만 계산
                if show_rsi:
                    print("Calculating RSI as requested...")
                    rsi_indicator = ta.momentum.RSIIndicator(close=close_series, window=14)
                    df['RSI'] = rsi_indicator.rsi()
                    
                    # RSI 값 상태 확인
                    print("RSI values sample:")
                    print(df['RSI'].tail(10))
                    print(f"RSI NaN count: {df['RSI'].isna().sum()} out of {len(df)}")
                else:
                    print("Skipping RSI calculation as per user request")
                    df['RSI'] = pd.Series([np.nan] * len(df), index=df.index)
                
                # (3) 볼린저 밴드 계산 - 옵션이 활성화된 경우에만 계산
                if show_bollinger:
                    print("Calculating Bollinger Bands as requested...")
                    bollinger = ta.volatility.BollingerBands(close=close_series, window=20, window_dev=2)
                    df['BB_High'] = bollinger.bollinger_hband()
                    df['BB_Low'] = bollinger.bollinger_lband()
                    df['BB_Middle'] = bollinger.bollinger_mavg()
                else:
                    print("Skipping Bollinger Bands calculation as per user request")
                    df['BB_High'] = pd.Series([np.nan] * len(df), index=df.index)
                    df['BB_Low'] = pd.Series([np.nan] * len(df), index=df.index)
                    df['BB_Middle'] = pd.Series([np.nan] * len(df), index=df.index)
                
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
                latest_indicators = {}
                
                # SMA 값을 조건부로 추가
                if show_sma5:
                    latest_indicators["SMA5"] = float(df['SMA5'].iloc[-1]) if not pd.isna(df['SMA5'].iloc[-1]) else None
                if show_sma20:
                    latest_indicators["SMA20"] = float(df['SMA20'].iloc[-1]) if not pd.isna(df['SMA20'].iloc[-1]) else None
                if show_sma60:
                    latest_indicators["SMA60"] = float(df['SMA60'].iloc[-1]) if not pd.isna(df['SMA60'].iloc[-1]) else None
                
                # RSI가 계산된 경우만 포함
                if show_rsi:
                    latest_indicators["RSI"] = float(df['RSI'].iloc[-1]) if not pd.isna(df['RSI'].iloc[-1]) else None
                
                # 볼린저 밴드가 계산된 경우만 포함
                if show_bollinger:
                    latest_indicators["BB_High"] = float(df['BB_High'].iloc[-1]) if not pd.isna(df['BB_High'].iloc[-1]) else None
                    latest_indicators["BB_Middle"] = float(df['BB_Middle'].iloc[-1]) if not pd.isna(df['BB_Middle'].iloc[-1]) else None
                    latest_indicators["BB_Low"] = float(df['BB_Low'].iloc[-1]) if not pd.isna(df['BB_Low'].iloc[-1]) else None
                
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
                if show_sma5 and has_valid_data(df['SMA5']):
                    apds.append(mpf.make_addplot(df['SMA5'], panel=0, color='green', width=1, label='SMA5'))
                else:
                    if show_sma5:
                        print("SMA5 has no valid data points, skipping in plot")
                    else:
                        print("SMA5 skipped as per user request")
                    
                if show_sma20 and has_valid_data(df['SMA20']):
                    apds.append(mpf.make_addplot(df['SMA20'], panel=0, color='purple', width=1, label='SMA20'))
                else:
                    if show_sma20:
                        print("SMA20 has no valid data points, skipping in plot")
                    else:
                        print("SMA20 skipped as per user request")
                    
                if show_sma60 and has_valid_data(df['SMA60']):
                    apds.append(mpf.make_addplot(df['SMA60'], panel=0, color='orange', width=1, label='SMA60'))
                else:
                    if show_sma60:
                        print("SMA60 has no valid data points, skipping in plot")
                    else:
                        print("SMA60 skipped as per user request")
                
                # 볼린저 밴드는 옵션이 활성화된 경우에만 추가
                if show_bollinger:
                    if has_valid_data(df['BB_High']):
                        apds.append(mpf.make_addplot(df['BB_High'], panel=0, color='gray', width=1, linestyle='--', label='BB High'))
                    else:
                        print("BB_High has no valid data points, skipping in plot")
                        
                    if has_valid_data(df['BB_Middle']):
                        apds.append(mpf.make_addplot(df['BB_Middle'], panel=0, color='black', width=1, label='BB Middle'))
                    else:
                        print("BB_Middle has no valid data points, skipping in plot")
                        
                    if has_valid_data(df['BB_Low']):
                        apds.append(mpf.make_addplot(df['BB_Low'], panel=0, color='gray', width=1, linestyle='--', label='BB Low'))
                    else:
                        print("BB_Low has no valid data points, skipping in plot")
                
                # 지지선 추가 (파란색) - 범례에서 제외
                blue_color = (0, 0, 1, 0.8)  # RGB 파란색에 80% 불투명도
                for level in support_values:
                    apds.append(mpf.make_addplot(
                        [level] * len(df), 
                        panel=0, 
                        color=blue_color, 
                        width=2, 
                        linestyle='-'
                    ))
                    print(f"Added support line at price: {level} with blue color")
                
                # 저항선 추가 (빨간색) - 범례에서 제외
                red_color = (1, 0, 0, 0.8)  # RGB 빨간색에 80% 불투명도
                for level in resistance_values:
                    apds.append(mpf.make_addplot(
                        [level] * len(df), 
                        panel=0, 
                        color=red_color, 
                        width=2, 
                        linestyle='-'
                    ))
                    print(f"Added resistance line at price: {level} with red color")
                
                # RSI 패널을 옵션에 따라 추가 또는 생략
                has_rsi = False
                if show_rsi and has_valid_data(df['RSI'], min_valid_points=10):
                    # RSI를 패널 2로 변경 (거래량과 분리)
                    apds.append(mpf.make_addplot(df['RSI'], panel=2, color='orange', ylabel='RSI', label='RSI'))
                    apds.append(mpf.make_addplot([70] * len(df), panel=2, color='red', linestyle='dashed', label='Overbought (70)'))
                    apds.append(mpf.make_addplot([30] * len(df), panel=2, color='green', linestyle='dashed', label='Oversold (30)'))
                    has_rsi = True
                    print("Added RSI panel to chart")
                else:
                    if show_rsi:
                        print("RSI has no valid data points or insufficient points, skipping in plot")
                    else:
                        print("RSI panel skipped as per user request")
                
                # 하이라이트할 타임스탬프들이 있는지 확인하고, 해당 시간의 캔들에 마커 표시
                highlight_indices = []
                if highlight_datetimes:
                    for highlight_datetime in highlight_datetimes:
                        # 시간 정보만 비교 (분/초 무시)
                        target_date = highlight_datetime.date()
                        target_hour = highlight_datetime.hour
                        
                        # 해당 날짜와 시간에 맞는 캔들 찾기
                        matching_indices = []
                        for i, idx in enumerate(df.index):
                            if idx.date() == target_date and idx.hour == target_hour:
                                matching_indices.append(i)
                        
                        if matching_indices:
                            # 해당 시간대의 첫 번째 캔들 선택
                            highlight_idx = matching_indices[0]
                            highlight_indices.append(highlight_idx)
                            print(f"Found matching timestamp at index {highlight_idx}: {df.index[highlight_idx]}")
                        else:
                            # 일치하는 시간이 없으면 같은 날짜에서 가장 가까운 시간 찾기
                            same_date_indices = [i for i, idx in enumerate(df.index) if idx.date() == target_date]
                            
                            if same_date_indices:
                                closest_idx = None
                                min_hour_diff = 24  # 최대 시간 차이
                                
                                for i in same_date_indices:
                                    hour_diff = abs(df.index[i].hour - target_hour)
                                    if hour_diff < min_hour_diff:
                                        min_hour_diff = hour_diff
                                        closest_idx = i
                                
                                if closest_idx is not None:
                                    highlight_indices.append(closest_idx)
                                    print(f"Exact hour match not found. Using closest hour at index {closest_idx}: {df.index[closest_idx]}")
                                    print(f"Hour difference: {min_hour_diff}")
                            else:
                                print(f"No data found for date {target_date}")
                    
                    # 모든 하이라이트할 날짜에 대해 마커 표시
                    if highlight_indices:
                        highlight_points = [np.nan] * len(df)
                        for idx in highlight_indices:
                            highlight_points[idx] = df['High'].iloc[idx] * 1.03  # 고가보다 약간 위에 표시
                        
                        # 마커 표시 - 범례에서 제외
                        apds.append(mpf.make_addplot(highlight_points, panel=0, type='scatter', 
                                                  marker='*', markersize=900, color=(0, 0, 1, 0.1)))
                        
                        print(f"Added {len(highlight_indices)} highlight markers")
                
                try:
                    # 캔들차트 생성 및 저장
                    # 여기서부터 수정: 순차적 파일 이름 사용
                    plot_filename, plot_index = self.get_next_available_filename()
                    print(f"Creating chart for {ticker}... Saving as {plot_filename}")
                    
                    # 패널 비율 및 설정 변경
                    # RSI가 활성화된 경우 3개 패널 (메인 차트, 거래량, RSI), 아니면 2개 패널 (메인 차트, 거래량)
                    if has_rsi:
                        panel_ratios = (4, 1, 1)  # 메인 차트, 거래량, RSI
                    else:
                        panel_ratios = (4, 1)  # 메인 차트, 거래량만
                    
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
                    
                    # 하이라이트된 타임스탬프 정보 추가
                    highlighted_timestamps_info = []
                    for idx in highlight_indices:
                        timestamp_info = {
                            "date": df.index[idx].strftime("%Y-%m-%d"),
                            "time": df.index[idx].strftime("%H:00"),  # 시간만 포함 (분/초 제외)
                            "open": float(df['Open'].iloc[idx]),
                            "high": float(df['High'].iloc[idx]),
                            "low": float(df['Low'].iloc[idx]),
                            "close": float(df['Close'].iloc[idx]),
                            "volume": float(df['Volume'].iloc[idx])
                        }
                        highlighted_timestamps_info.append(timestamp_info)
                    
                    # 지지선 및 저항선 정보 추가
                    support_info = [float(level) for level in support_values] if support_values else []
                    resistance_info = [float(level) for level in resistance_values] if resistance_values else []
                    
                    # 기본 historical_data 준비
                    historical_data = {
                        "Date": df_with_date[index_column_name].dt.strftime("%Y-%m-%d").tolist(),
                        "Time": df_with_date[index_column_name].dt.strftime("%H:00").tolist(),  # 시간만 포함 (분/초 제외)
                        "Open": df['Open'].tolist(),
                        "High": df['High'].tolist(),
                        "Low": df['Low'].tolist(),
                        "Close": df['Close'].tolist(),
                        "Volume": df['Volume'].tolist(),
                    }
                    
                    # SMA가 계산된 경우에만 추가
                    if show_sma5:
                        historical_data["SMA5"] = df['SMA5'].tolist()
                    if show_sma20:
                        historical_data["SMA20"] = df['SMA20'].tolist()
                    if show_sma60:
                        historical_data["SMA60"] = df['SMA60'].tolist()
                    
                    # RSI가 계산된 경우에만 추가
                    if show_rsi:
                        historical_data["RSI"] = df['RSI'].tolist()
                    
                    # 볼린저 밴드가 계산된 경우에만 추가
                    if show_bollinger:
                        historical_data["BollingerBands"] = {
                            "High": df['BB_High'].tolist(),
                            "Middle": df['BB_Middle'].tolist(),
                            "Low": df['BB_Low'].tolist()
                        }
                    
                    # JSON 변환을 위한 데이터 준비
                    results[ticker] = {
                        "realtime_data": realtime_data,
                        "latest_indicators": latest_indicators,
                        "historical_data": historical_data,
                        "highlighted_timestamps": highlighted_timestamps_info,  # 이름 변경
                        "support_levels": support_info,
                        "resistance_levels": resistance_info,
                        "plot_file": plot_filename,
                        "plot_index": plot_index,  # 파일 인덱스도 저장
                        "indicators_shown": {
                            "sma5": show_sma5,
                            "sma20": show_sma20,
                            "sma60": show_sma60,
                            "rsi": show_rsi,
                            "bollinger_bands": show_bollinger
                        }
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
                additional_file_path = os.path.join(os.getcwd(), "stock_technical_analysis.json")
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
    try:
        tool = ShortStockMarkTool()
        
        # JSON 형식의 입력 받기
        json_input = input("파라미터를 JSON 형식으로 입력하세요: ")
        params = json.loads(json_input)
        
        # 파라미터 추출
        ticker_input = params.get("tickers", "")
        highlight_timestamps = params.get("highlight_timestamps")  # 이름 변경
        support_level = params.get("support_level")
        resistance_level = params.get("resistance_level")
        show_sma5 = params.get("show_sma5", True)
        show_sma20 = params.get("show_sma20", True)
        show_sma60 = params.get("show_sma60", True)
        show_rsi = params.get("show_rsi", False)
        show_bollinger = params.get("show_bollinger", False)
        
        if not ticker_input:
            print("오류: 종목 코드(tickers)는 필수 입력사항입니다.")
        else:
            # forward 함수 호출
            result = tool.forward(ticker_input, highlight_timestamps, support_level, resistance_level,
                               show_sma5, show_sma20, show_sma60, show_rsi, show_bollinger)
            print("분석 완료!")
            
    except json.JSONDecodeError as e:
        print(f"JSON 파싱 오류: {str(e)}")
        print("올바른 JSON 형식 예시:")
        print("""
{
  "tickers": "AAPL,MSFT,005930.KS",
  "highlight_timestamps": "2023-03-15 14,2023-03-16 09",
  "support_level": "150.5,155.0",
  "resistance_level": "170.0,175.5",
  "show_sma5": true,
  "show_sma20": true,
  "show_sma60": true,
  "show_rsi": true,
  "show_bollinger": true
}
        """)
    except Exception as e:
        print(f"오류 발생: {str(e)}")