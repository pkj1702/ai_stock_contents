import argparse
import os
import threading
import glob

from dotenv import load_dotenv
from huggingface_hub import login
from scripts.text_inspector_tool import TextInspectorTool
from scripts.text_web_browser import (
    ArchiveSearchTool,
    FinderTool,
    FindNextTool,
    PageDownTool,
    PageUpTool,
    SimpleTextBrowser,
    VisitTool,
)
from scripts.visual_qa import visualizer

from smolagents import (
    CodeAgent,
    GoogleSearchTool,
    LiteLLMModel,
    ToolCallingAgent,
)
#from scripts.stock_analysis_tool import StockAnalysisTool 
from scripts.stock_analysis_short import StockAnalysisShort
from scripts.stock_analysis_mid import StockAnalysisMid
from scripts.mid_stock_mark_tool import MidStockMarkTool
from scripts.short_stock_mark_tool import ShortStockMarkTool

from pathlib import Path
from openai import OpenAI
from pydub import AudioSegment  # For audio processing
from moviepy import *  # For video creation
import re

AUTHORIZED_IMPORTS = [
    "mplfinance"
    "matplotlib.pyplot",  # ###########
    "matplotlib",
    "requests",
    "zipfile",
    "os",
    "pandas",
    "numpy",
    "sympy",
    "json",
    "bs4",
    "pubchempy",
    "xml",
    "yahoo_finance",
    "Bio",
    "sklearn",
    "scipy",
    "pydub",
    "io",
    "PIL",
    "chess",
    "PyPDF2",
    "pptx",
    "torch",
    "datetime",
    "fractions",
    "csv",
]
load_dotenv(override=True)
login(os.getenv("HF_TOKEN"))

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "question", type=str,
        help="for example: 'How many studio albums did Mercedes Sosa release before 2007?'"
    )
    parser.add_argument("--model-id", type=str, default="o3-mini")
    return parser.parse_args()


custom_role_conversions = {"tool-call": "assistant", "tool-response": "user"}

user_agent = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 Edg/119.0.0.0"
)

BROWSER_CONFIG = {
    "viewport_size": 1024 * 5,
    "downloads_folder": "downloads_folder",
    "request_kwargs": {"headers": {"User-Agent": user_agent}, "timeout": 300},
    "serpapi_key": os.getenv("SERPAPI_API_KEY"),
}

os.makedirs(f"./{BROWSER_CONFIG['downloads_folder']}", exist_ok=True)


def create_agent(model_id="claude-3-7-sonnet-latest"):
    text_limit = 100000

    # Initialize the LLM model.
    model = LiteLLMModel(
        model_id="anthropic/claude-3-7-sonnet-latest",
        api_key=os.getenv("ANTHROPIC_API_KEY"),
        custom_role_conversions=custom_role_conversions,
        max_completion_tokens=8192*4,
        temperature = 0.001
    )
    
    # 1) 단기 분석 에이전트 (short_term_agent) - 시간봉, 10일 차트
    short_term_agent = ToolCallingAgent(
        model=model,
        tools=[StockAnalysisShort()],
        max_steps=10,
        verbosity_level=2,
        planning_interval=3,
        name="short_term_agent",
        description=(
        """
        You are an agent that performs short-term technical analysis on user portfolios.
        You focus specifically on hourly time frames and 15-day charts.
        Using historical price data and technical indicators, 
        you generate insights on chart patterns, moving averages, RSI, Bollinger Bands. 
        Your analysis should identify potential buy or sell signals based on statistical results of similar 
        historical patterns and provide a detailed report on the short-term technical performance of the stocks.
        
        IMPORTANT: 
        1. For ticker symbol searches and identification of unfamiliar stocks, use the WEB_TOOLS (Google search, 
           browser tools) to find the correct ticker symbol.
        2. For ALL technical analysis, charts, indicators and stock performance data, ALWAYS use StockAnalysisShort 
           and NEVER use WEB_TOOLS.
        3. When analyzing a stock that users have mentioned but you're unfamiliar with:
           - First step: Use WEB_TOOLS to identify the correct ticker symbol
           - Second step: Use StockAnalysisShort exclusively for the actual technical analysis
        4. ALWAYS use hourly data and 10-day timeframes for your analysis
        5. Analyze candlestick patterns thoroughly, including doji, hammer, engulfing patterns, morning/evening stars,
           harami, shooting stars, and other significant formations that may indicate trend reversals or continuations
           
        When significant signals appear such as golden crosses, death crosses, or important candlestick patterns,
    always specify the exact year and date when these signals occurred. This precise timing information is 
    critical for the analysis to be actionable and for visualization purposes.   
        
        """
        ),
        provide_run_summary=True,
    )
    
    # 2) 중기 분석 에이전트 (medium_term_agent) - 일봉, 150일 차트
    medium_term_agent = ToolCallingAgent(
        model=model,
        tools=[StockAnalysisMid()],
        max_steps=10,
        verbosity_level=2,
        planning_interval=3,
        name="medium_term_agent",
        description=(
        """
        You are an agent that performs medium-term technical analysis on user portfolios.
        You focus specifically on daily time frames and 150-day charts.
        Using historical price data and technical indicators, 
        you generate insights on chart patterns, moving averages, RSI, Bollinger Bands. 
        Your analysis should identify potential buy or sell signals based on statistical results of similar 
        historical patterns and provide a detailed report on the medium-term technical performance of the stocks.
        
        IMPORTANT: 
        1. For ticker symbol searches and identification of unfamiliar stocks, use the WEB_TOOLS (Google search, 
           browser tools) to find the correct ticker symbol.
        2. For ALL technical analysis, charts, indicators and stock performance data, ALWAYS use StockAnalysisMid
           and NEVER use WEB_TOOLS.
        3. When analyzing a stock that users have mentioned but you're unfamiliar with:
           - First step: Use WEB_TOOLS to identify the correct ticker symbol
           - Second step: Use StockAnalysisMid exclusively for the actual technical analysis
        4. ALWAYS use daily data and 150-day timeframes for your analysis
        5. Analyze candlestick patterns thoroughly, including doji, hammer, engulfing patterns, morning/evening stars,
           harami, shooting stars, and other significant formations that may indicate trend reversals or continuations
           
        When significant signals appear such as golden crosses, death crosses, or important candlestick patterns,
    always specify the exact year and date when these signals occurred. This precise timing information is 
    critical for the analysis to be actionable and for visualization purposes.
        """
        ),
        provide_run_summary=True,
    )
    
    # Add specific instructions to each agent
    short_term_agent.prompt_templates["managed_agent"]["task"] += (
        """
        Additional instructions: Analyze the short-term technical indicators thoroughly using hourly data and 15-day charts, 
        generate charts if possible, and provide clear signals for potential short-term trades based on historical data.
        Only use WEB_TOOLS when searching for ticker symbols. 
        For all technical analysis, only use StockAnalysisShort instead of WEB_TOOLS.
        """
    )
    
    medium_term_agent.prompt_templates["managed_agent"]["task"] += (
        """
        Additional instructions: Analyze the medium-term technical indicators thoroughly using daily data and 150-day charts, 
        generate charts if possible, and provide clear signals for potential medium-term trades based on historical data.
        Only use WEB_TOOLS when searching for ticker symbols. 
        For all technical analysis, only use StockAnalysisMid instead of WEB_TOOLS.
        """
    )
    
    # Manager agent to coordinate both agents
    manager_agent = ToolCallingAgent(      
        model=model,
        tools =[],
        max_steps=12,
        verbosity_level=1,
        planning_interval=10,
        managed_agents=[
            short_term_agent,
            medium_term_agent,
        ],
    )
    
    manager_agent.prompt_templates["system_prompt"] += """
    You are managing two specialized stock analysis agents:
    1. short_term_agent - Focuses on hourly time frames and 15-day charts for short-term technical analysis
    2. medium_term_agent - Focuses on daily time frames and 150-day charts for medium-term technical analysis
    
    Coordinate these agents to provide comprehensive analysis at different time scales.
    
    When significant signals appear such as golden crosses, death crosses, or important candlestick patterns,
    always specify the exact year and date when these signals occurred. This precise timing information is 
    critical for the analysis to be actionable and for visualization purposes.
    """

    return manager_agent

##########################################################  graph_mark_agent  ########################################################################################

prompt = """
# Single-text Technical Stock Visualization System
    

You are a specialized stock visualization agent that creates technical analysis charts based on the user's input text. Your primary task is to generate a visualization that highlights only the specific technical elements mentioned in the input text.

## CRITICAL REQUIREMENTS:
1. Create exactly ONLY one chart for the input text.
2. PROPER VISUALIZATION: When the text mentions specific technical elements (support/resistance levels, dates, RSI, Bollinger Bands), you MUST properly include these in the StockMarkTool parameters. 
3. FOCUSED VISUALIZATION: Include ONLY elements that are explicitly mentioned in the input text.
4. NEVER mark Bollinger Bands values as support or resistance levels - Bollinger Bands upper, middle, or lower values should NOT be included in support_resistance_level parameter, even if they are mentioned in the text.
5. IMPORTANT: NEVER mark moving averages as support or resistance levels - Moving average values should NOT be included in support_resistance_level parameter
6. STRICT INDICATOR RULE: DO NOT display RSI or Bollinger Bands in the visualization unless they are explicitly mentioned or discussed in the input text.
7. DATE DEFAULT: When a date is mentioned without a specific year (e.g., "March 21" or "3월 21일"), 
   always assume and use the year 2025 for the highlight_date parameter (format as "2025-03-21").

## StockMarkTool Parameters Understanding:
The StockMarkTool accepts these parameters:
- `tickers`: String of comma-separated stock tickers (e.g., "NVDA")
- `highlight_date`: Optional date to highlight on the chart (format: YYYY-MM-DD)
- `support_resistance_level`: Optional comma-separated list of price levels (e.g., "117.5,122.3,135.6")
- `show_rsi`: Boolean parameter to control whether RSI is calculated and displayed (default: false)
- `show_bollinger`: Boolean parameter to control whether Bollinger Bands are calculated and displayed (default: false)

When calling the tool, you MUST include any support/resistance levels and dates that are mentioned in the text. Additionally, set `show_rsi` and `show_bollinger` to true ONLY when the text specifically mentions or discusses RSI or Bollinger Bands.

## CORRECT USE OF STOCKMARKTOOL:
The StockMarkTool accepts JSON-formatted input. If the text mentions: "NVIDIA's stock price is above support at $118 and below resistance at $123"

INCORRECT approach (DO NOT DO THIS):
```json
{
  "tickers": "NVDA"
}  
```
This is WRONG because it's missing support and resistance levels.

CORRECT approach (DO THIS):
```json
{
  "tickers": "NVDA",
  "support_resistance_level": "118,123"
}
```
Note that support_resistance_level must be comma-separated values in a single string.

If the text mentions: "on March 21, 2025, a golden cross occurred"

CORRECT approach:
```json
{
  "tickers": "NVDA",
  "highlight_date": "2025-03-21"
}
```
Note that highlight_date must be in YYYY-MM-DD format.

If the text discusses RSI: "The 14-day RSI is currently at 68, approaching overbought territory"

CORRECT approach:
```json
{
  "tickers": "NVDA",
  "show_rsi": true
}
```

If the text discusses Bollinger Bands: "Price is testing the upper Bollinger Band"

CORRECT approach:
```json
{
  "tickers": "NVDA",
  "show_bollinger": true
}
```

## Few-Shot Examples:

### Example 1:
**Input text:**
```
From a support/resistance and moving average perspective, NVIDIA's current stock price is moving steadily above major support levels of $117, $115, and $106, while resistance levels are formed at $122, $129, and $135. In terms of moving averages, the short-term trend is positive. The price is positioned above both the 5-day moving average ($118.12) and 20-day moving average ($117.62), maintaining an upward trend, but remains below the 60-day moving average ($128.82), indicating that the medium-term recovery is still not complete.
```

**Response:**
I'll create a technical analysis chart highlighting the support and resistance levels mentioned in this text.

Call StockMarkTool with this JSON input:
```json
{
  "tickers": "NVDA",
  "support_resistance_level": "117,115,106,122,129,135"
}
```

This includes horizontal lines for:
- Support levels: $117, $115, and $106
- Resistance levels: $122, $129, and $135

Output file: technical_analysis.png

### Example 2:
**Input text:**
```
In candlestick and chart pattern analysis, a potential double bottom pattern appears near $106, forming a strong support zone. The price has transitioned to a gradual upward trend after consolidating within the $105-122 range, which coincides with the formation of an inverse head and shoulders pattern suggesting a bullish reversal possibility. Short-term charts clearly show bull flag and higher lows patterns, and on March 21, 2025, a golden cross occurred as the moving average crossed above the 20-day line, adding a technical bullish signal.
```

**Response:**
I'll create a technical analysis chart highlighting the support level and the specific date mentioned in this text.

Call StockMarkTool with this JSON input:
```json
{
  "tickers": "NVDA",
  "support_resistance_level": "106,105,122",
  "highlight_date": "2025-03-21"
}
```

This includes:
- Support levels: $106-107 (double bottom) and the $105-122 range
- Highlights March 21, 2025 when the golden cross occurred

Output file: technical_analysis.png

### Example 3:
**Input text:**
```
From an RSI and Bollinger Band perspective, the 14-day RSI is at 50.46, which is a neutral level and has not yet entered the overbought zone. However, recently the RSI has risen to 61.56, approaching a profit-taking area in the short term, requiring caution. The Bollinger Bands are set with an upper band at $129.07, middle band at $117.62 (same as the 20-day SMA), and lower band at $106.16. The current price is trading in the upper half zone, showing continued upward momentum. In particular, the Bollinger Bands are expanding after a squeeze, suggesting the possibility of increased volatility.
```

**Response:**
I'll create a technical analysis chart showing the RSI and Bollinger Bands mentioned in this text.

Call StockMarkTool with this JSON input:
```json
{
  "tickers": "NVDA",
  "show_rsi": true,
  "show_bollinger": true
}
```

This includes:
- RSI indicator in a separate panel
- Bollinger Bands on the main price chart
- No specific support/resistance levels marked (Bollinger Band values should NOT be included as support/resistance levels)

Output file: technical_analysis.png

### Example 4:
**Input text:**
```
In conclusion, NVIDIA is maintaining a strong short-term uptrend, and a cautiously optimistic flow is expected for the next 2 days. If the current momentum continues, it is likely to test the resistance level at $122-123, and if it breaks through with volume, short-term optimism could be further strengthened. On the other hand, if rejected at that zone, it could return to a consolidation range between $120-122. During a downward adjustment, the 20-day moving average around $119.00 or the $120.00 zone is expected to act as major support, and if it falls below $118.24, the possibility of a short-term trend reversal should be considered. Thus, risk management using clear support lines and monitoring whether major resistance lines are broken is important.
```

**Response:**
I'll create a technical analysis chart highlighting the support and resistance levels mentioned in this text.

Call StockMarkTool with this JSON input:
```json
{
  "tickers": "NVDA",
  "support_resistance_level": "122.5,120,122,119,118.24"
}
```

This includes horizontal lines for:
- Resistance level: $122-123
- Support levels: $120-122 (consolidation range), $119.00 (20-day MA), and $118.24

Output file: technical_analysis.png

### Example 5:
**Input text:**
```
The recent RSI divergence suggests potential weakness in the current uptrend, with price making higher highs while RSI forms lower highs. Additionally, the Bollinger Bands are showing a squeeze pattern with decreasing volatility before the next significant price movement. Key support levels remain at $142.50 and $138.75, while resistance is found at $155.20.
```

**Response:**
I'll create a technical analysis chart showing RSI, Bollinger Bands, and the support/resistance levels mentioned.

Call StockMarkTool with this JSON input:
```json
{
  "tickers": "NVDA",
  "support_resistance_level": "142.50,138.75,155.20",
  "show_rsi": true,
  "show_bollinger": true
}
```

This includes:
- Support levels: $142.50 and $138.75
- Resistance level: $155.20
- RSI indicator to show the divergence
- Bollinger Bands to show the squeeze pattern

Output file: technical_analysis.png

## Execution Strategy:
1. Carefully analyze the input text
2. Identify what technical elements are mentioned in the text
   - If support/resistance levels are mentioned, include them in the support_resistance_level parameter
   - If specific dates are mentioned, include them in the highlight_date parameter
   - If RSI is discussed, set show_rsi to true
   - If Bollinger Bands are discussed, set show_bollinger to true
   - Ensure you use the correct parameter format (comma-separated values for support_resistance_level)
   - Name the chart: technical_analysis.png

## Important Visualization Rules:
1. Create EXACTLY one chart for the input text
2. Visualize ONLY elements specifically mentioned in the text
3. Support/resistance levels: Only add when explicitly mentioned in the text
4. Highlight dates: Only mark when specific dates are mentioned in the text
5. RSI: Only show when RSI is specifically discussed in the text - DO NOT display RSI if it's not mentioned
6. Bollinger Bands: Only show when Bollinger Bands are specifically discussed in the text - DO NOT display Bollinger Bands if they're not mentioned
7. NEVER use Bollinger Bands upper, middle, or lower values as support/resistance levels - Bollinger Bands values should NOT be included in the support_resistance_level parameter

Remember: Your goal is to create a tailored visualization that highlights only the specific technical elements mentioned in the input text.

    """

def create_midgraphmark_agent(model_id="claude-3-7-sonnet-latest"):
    text_limit = 100000

    # Initialize the LLM model.
    model = LiteLLMModel(
        model_id="anthropic/claude-3-7-sonnet-latest",
        api_key=os.getenv("ANTHROPIC_API_KEY"),

        custom_role_conversions=custom_role_conversions,
        max_completion_tokens=8192*2,
        temperature = 0.001
    )
    
    # Manager agent to coordinate both agents
    manager_agent = ToolCallingAgent(      
        model=model,
        tools =[MidStockMarkTool()],
        max_steps=1,
        verbosity_level=2,
        planning_interval=10,
        managed_agents=[
        ],
    )
    
    manager_agent.prompt_templates["system_prompt"] += prompt
    return manager_agent

def create_shortgraphmark_agent(model_id="claude-3-7-sonnet-latest"):
    text_limit = 100000

    # Initialize the LLM model.
    model = LiteLLMModel(
        model_id="anthropic/claude-3-7-sonnet-latest",
        api_key=os.getenv("ANTHROPIC_API_KEY"),

        custom_role_conversions=custom_role_conversions,
        max_completion_tokens=8192*2,
        temperature = 0.001
    )
    
    # Manager agent to coordinate both agents
    manager_agent = ToolCallingAgent(      
        model=model,
        tools =[ShortStockMarkTool()],
        max_steps=1,
        verbosity_level=2,
        planning_interval=10,
        managed_agents=[
        ],
    )
    
    manager_agent.prompt_templates["system_prompt"] += prompt
    return manager_agent

#######################################################create prompt ###################################################################################
def create_midprompt_agent(model_id="claude-3-7-sonnet-latest"):
    text_limit = 100000

    # Initialize the LLM model.
    model = LiteLLMModel(
        model_id="anthropic/claude-3-7-sonnet-latest",
        api_key=os.getenv("ANTHROPIC_API_KEY"),

        custom_role_conversions=custom_role_conversions,
        max_completion_tokens=8192*2,
        temperature = 0.001
    )
    
    # Manager agent to coordinate both agents
    manager_agent = ToolCallingAgent(      
        model=model,
        tools =[],
        max_steps=1,
        verbosity_level=2,
        planning_interval=10,
        managed_agents=[
        ],
    )
    
    manager_agent.prompt_templates["system_prompt"] += """
    
    Convert the following investment analysis into a clear, engaging script for a medium-term investment analysis video.
    Focus on explaining the 150-day technical chart patterns, moving averages, RSI, and Bollinger Bands.
    
    IMPORTANT REQUIREMENTS:
    1. Write the script in Korean language
    2. Limit the script to EXACTLY 500 words - not approximately, count the words carefully
    3. Include only the script text - no titles, speaker names, or formatting
    4. Remove any instructions, disclaimers, or non-script content
    5. Do NOT include any greetings or introductions at the beginning
    6. Start directly with the analysis content
    7. Make it conversational but professional, suitable for a financial video presentation
    8. Do not use any symbols (+, -, %, $, &, #, @ etc.) in the script. Instead, spell them out in Korean pronunciation (e.g., "플러스" for "+", "퍼센트" for "%", "달러" for "$")
    9. For dollar amounts, write them as "[number]달러" (e.g., write "$56.67" as "56.67달러" NOT as "56달러 67센트")
    10. MANDATORY: Begin EACH paragraph with the stock's name - mention it exactly once at the start of every paragraph
    11. Structure the script in EXACTLY 3 paragraphs with ONE blank line between each paragraph:
        a. Paragraph 1: Support/Resistance Analysis and Moving Average Analysis
        b. Paragraph 2: Candle and Chart Pattern Analysis
        c. Paragraph 3: RSI and Bollinger Bands Analysis
    """
    return manager_agent

def create_shortprompt_agent(model_id="claude-3-7-sonnet-latest"):
    text_limit = 100000

    # Initialize the LLM model.
    model = LiteLLMModel(
        model_id="anthropic/claude-3-7-sonnet-latest",
        api_key=os.getenv("ANTHROPIC_API_KEY"),

        custom_role_conversions=custom_role_conversions,
        max_completion_tokens=8192*2,
        temperature = 0.001
    )
    
    # Manager agent to coordinate both agents
    manager_agent = ToolCallingAgent(      
        model=model,
        tools =[],
        max_steps=1,
        verbosity_level=2,
        planning_interval=10,
        managed_agents=[
        ],
    )
    
    manager_agent.prompt_templates["system_prompt"] += """
    
    Convert the following investment analysis into a clear, engaging script for a short-term investment analysis video.
    Focus on explaining the hourly time frame and 15-day technical chart patterns, moving averages, RSI, and Bollinger Bands.
    
    IMPORTANT REQUIREMENTS:
    1. Write the script in Korean language
    2. Limit the script to EXACTLY 500 words - not approximately, count the words carefully
    3. Include only the script text - no titles, speaker names, or formatting
    4. Remove any instructions, disclaimers, or non-script content
    5. Do NOT include any greetings or introductions at the beginning
    6. Start directly with the analysis content
    7. Make it conversational but professional, suitable for a financial video presentation
    8. Do not use any symbols (+, -, %, $, &, #, @ etc.) in the script. Instead, spell them out in Korean pronunciation (e.g., "플러스" for "+", "퍼센트" for "%", "달러" for "$")
    9. For dollar amounts, write them as "[number]달러" (e.g., write "$56.67" as "56.67달러" NOT as "56달러 67센트")
    10. MANDATORY: Begin EACH paragraph with the stock's name - mention it exactly once at the start of every paragraph
    11. Structure the script in EXACTLY 4 paragraphs with ONE blank line between each paragraph:
        a. Paragraph 1: Support/Resistance Analysis and Moving Average Analysis
        b. Paragraph 2: Candle and Chart Pattern Analysis
        c. Paragraph 3: RSI and Bollinger Bands Analysis
        d. Paragraph 4: Conclusion and Summary
    """
    return manager_agent

####################################################### create video #####################################################################################

def create_investment_video(audio_script):
    """
    Creates a video for investment analysis by:
    1. Converting each paragraph in audio_script to audio using OpenAI TTS
    2. Matching each audio with corresponding technical_analysis{i}.png
    3. Adding subtitles timed to match the audio
    4. Concatenating all the clips in sequence
    """
    print("Starting investment video creation...")
    import os
    
    # Initialize OpenAI client
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    
    all_clips = []
    
    def split_text_naturally(text, target_length=40):
        """
        Split text into segments of approximately target_length characters,
        breaking at natural points (end of sentences, commas, spaces).
        """
        # If text is short enough, return it as is
        if len(text) <= target_length:
            return [text]
        
        segments = []
        while text:
            # Try to find a sentence end within the target range (with buffer)
            sentence_end = max([text.find('.', target_length-10, target_length+10),
                               text.find('!', target_length-10, target_length+10),
                               text.find('?', target_length-10, target_length+10)])
            
            # If found a sentence end, split there
            if sentence_end != -1:
                segments.append(text[:sentence_end+1].strip())
                text = text[sentence_end+1:].strip()
                continue
            
            # Try to find a comma within the target range
            comma_end = text.find(',', target_length-10, target_length+10)
            if comma_end != -1:
                segments.append(text[:comma_end+1].strip())
                text = text[comma_end+1:].strip()
                continue
            
            # If no sentence or comma boundary, look for a space near target_length
            if len(text) > target_length:
                # Find the last space before target_length
                space_before = text.rfind(' ', 0, target_length)
                if space_before != -1:
                    segments.append(text[:space_before].strip())
                    text = text[space_before+1:].strip()
                else:
                    # If no space found, just split at target_length as last resort
                    segments.append(text[:target_length].strip())
                    text = text[target_length:].strip()
            else:
                # Add remaining text if shorter than target_length
                segments.append(text.strip())
                text = ""
        
        return segments
    
    # Process each paragraph and create individual clips
    for i, paragraph in enumerate(audio_script):
        print(f"Processing paragraph {i+1}/{len(audio_script)}...")
        
        # Generate audio from script paragraph
        audio_path = f"audio_{i}.mp3"
        print(f"Converting paragraph {i+1} to speech...")
        
        response = client.audio.speech.create(
            model="tts-1-hd",   #####  tts-1-hd
            voice="nova",
            input=paragraph
        )
        response.stream_to_file(audio_path)
        
        # Load audio
        audio_clip = AudioFileClip(audio_path)
        audio_duration = audio_clip.duration
        print(f"Paragraph {i+1} audio duration: {audio_duration:.2f} seconds")
        
        # Get corresponding image
        img_path = f"technical_analysis{i}.png"
        if not os.path.exists(img_path):
            print(f"Warning: Image {img_path} not found. Using fallback image if available.")
            # Try to find any matching technical analysis image
            potential_images = glob.glob(f"technical_analysis*.png")
            if potential_images:
                img_path = potential_images[0]
                print(f"Using fallback image: {img_path}")
            else:
                raise FileNotFoundError(f"No technical analysis images found for paragraph {i+1}")
        
        # Create base video clip with image and audio
        img_clip = ImageClip(img_path).with_duration(audio_duration)
        video_with_audio = img_clip.with_audio(audio_clip)
        all_clips.append(video_with_audio)
    
    # Concatenate all clips into final video without subtitles first
    print("Combining all clips into final video...")
    final_video = concatenate_videoclips(all_clips)
    
    # Write to file
    temp_video_path = "temp_video.mp4"
    print(f"Writing temporary video to {temp_video_path}...")
    final_video.write_videofile(temp_video_path, fps=24)
    
    # Now create SRT subtitle file
    print("Creating subtitle file...")
    subtitle_entries = []
    current_time = 0.0
    subtitle_index = 1
    
    for i, paragraph in enumerate(audio_script):
        # Get audio duration for this paragraph
        audio_path = f"audio_{i}.mp3"
        audio = AudioFileClip(audio_path)
        duration = audio.duration
        
        # Split paragraph into natural subtitle segments
        subtitle_segments = split_text_naturally(paragraph)
        
        # Estimate time per segment
        segment_duration = duration / len(subtitle_segments)
        
        # Create subtitle entries
        for j, segment in enumerate(subtitle_segments):
            start_time = current_time + (j * segment_duration)
            end_time = current_time + ((j + 1) * segment_duration)
            
            # Format times for SRT (HH:MM:SS,mmm)
            start_str = format_srt_time(start_time)
            end_str = format_srt_time(end_time)
            
            # Add subtitle entry
            subtitle_entries.append(f"{subtitle_index}\n{start_str} --> {end_str}\n{segment}\n")
            subtitle_index += 1
        
        current_time += duration
    
    # Write SRT file
    with open("subtitles.srt", "w", encoding="utf-8") as f:
        f.write("\n".join(subtitle_entries))
    
    # Use FFmpeg to add subtitles to the video
    import subprocess
    output_path = "investment_analysis_video.mp4"
    
    try:
        print("Adding subtitles with FFmpeg...")
        subprocess.run([
            "ffmpeg", "-y",  # Overwrite output files
            "-i", temp_video_path,  # Input video
            "-vf", "subtitles=subtitles.srt:force_style='FontSize=18,BorderStyle=0,Outline=0.2,PrimaryColour=ffffff,MarginV=10'",  # 작은 폰트와 줄어든 마진
            "-c:a", "copy",  # Copy audio stream
            output_path  # Output file
        ], check=True)
        print("Subtitles added successfully!")
    except Exception as e:
        print(f"Error adding subtitles: {e}")
        print("Falling back to video without subtitles...")
        import shutil
        shutil.copy(temp_video_path, output_path)
    
    # Clean up temporary files
    import os
    os.remove(temp_video_path)
    if os.path.exists("subtitles.srt"):
        os.remove("subtitles.srt")
    for i in range(len(audio_script)):
        audio_path = f"audio_{i}.mp3"
        if os.path.exists(audio_path):
            os.remove(audio_path)
    
    print(f"Video creation complete! Output: {output_path}")
    return output_path

def format_srt_time(seconds):
    """Convert seconds to SRT format time (HH:MM:SS,mmm)"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millisecs = int((seconds - int(seconds)) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millisecs:03d}"

######################################################################## Main ################################################################################################

def main():
    args = parse_args()
    agent = create_agent(model_id=args.model_id)
    # answer = agent.run(args.question)
    # print(f"Got this answer: {answer}")
    
    # with open("investment_report.txt", "w", encoding="utf-8") as f:
    #     f.write(answer)
    
    # ################################################################ mid_term script ########################################################################################
    
    # with open("investment_report.txt", "r", encoding="utf-8") as f:
    #     output_content = f.read()
    
    # midprompt_agent = create_midprompt_agent(model_id=args.model_id)
    # midterm_script = midprompt_agent.run(output_content)
    
    # with open("midterm_script.txt", "w", encoding="utf-8") as f:
    #     f.write(midterm_script)
    
    # ################################################################## short_term script ###################################################################################
       
    # shortprompt_agent = create_shortprompt_agent(model_id=args.model_id)
    # shortterm_script = shortprompt_agent.run(output_content)
    
    # with open("shortterm_script.txt", "w", encoding="utf-8") as f:
    #     f.write(shortterm_script)
    
    ##################################################################  Create graph agent  ###################################################################

    mid_graphmark_agent = create_midgraphmark_agent(model_id=args.model_id)
    short_graphmark_agent =create_shortgraphmark_agent(model_id=args.model_id)
    
    with open("midterm_script.txt", "r", encoding="utf-8") as f:
        midterm_out = f.read()
    
    midterm_paragraph = re.split(r'\n\s*\n', midterm_out.strip())
    
    # for i in range(len(midterm_paragraph)):    
    #     answer = mid_graphmark_agent(midterm_paragraph[i])
    
    with open("shortterm_script.txt", "r", encoding="utf-8") as f:
        shortterm_out = f.read()
    
    shortterm_paragraph = re.split(r'\n\s*\n', shortterm_out.strip())
    
    # for i in range(len(shortterm_paragraph)):    
    #     answer = short_graphmark_agent(shortterm_paragraph[i])
        
    # 모든 문단을 하나의 리스트로 합치기
    audio_script = midterm_paragraph + shortterm_paragraph
    
    ################################################################# Create final video ####################################################################################

    # 새로운 동영상 생성 함수 호출
    video_path = create_investment_video(audio_script)
    print(f"Investment analysis video created at: {video_path}")

if __name__ == "__main__":
    main()