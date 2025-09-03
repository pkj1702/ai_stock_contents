# 주식 분석 및 팟캐스트 생성을 위한 멀티 에이전트 시스템
# 여러 AI 에이전트들이 협력하여 주식 투자 리포트를 생성하고 팟캐스트로 변환

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

import os
import argparse
import glob

from smolagents import (
    CodeAgent,
    GoogleSearchTool,
    LiteLLMModel,
    ToolCallingAgent,
)
#from scripts.stock_analysis_tool import StockAnalysisTool 
from scripts.stock_visualization_tool import StockAnalysisTool  # 주식 시각화 도구
from scripts.stock_data_image_tool import StockDataImageTool  # 주식 데이터 이미지 생성
from scripts.sentiment_tool import SentimentTool  # 감정 분석 도구

from pathlib import Path
from openai import OpenAI
from pydub import AudioSegment  # Added import for audio processing
from prompts.podcast_prompts import *

load_dotenv(override=True)
login(os.getenv("HF_TOKEN"))

def parse_args():
    """명령행 인자를 파싱하는 함수
    
    Returns:
        argparse.Namespace: 파싱된 인자들 (질문, 모델ID, 팟캐스트 길이)
    """
    parser = argparse.ArgumentParser()
    # 분석할 주식 관련 질문 (필수 인자)
    parser.add_argument(
        "question", type=str,
        help="분석할 주식 관련 질문 (예: 'AAPL 주식의 최근 동향은?')"
    )
    # 사용할 AI 모델 ID (선택적)
    parser.add_argument("--model-id", type=str, default="o3-mini")
    # 팟캐스트 길이 선택 (1=3분, 2=10분)
    parser.add_argument(
        "--podcast-length", type=int, choices=[1, 2], default=1,
        help="팟캐스트 길이 선택: 1 = 3분 팟캐스트, 2 = 10분 팟캐스트"
    )
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
    """주식 분석을 위한 멀티 에이전트 시스템을 생성하는 함수
    
    5개의 전문 에이전트를 생성하고 매니저 에이전트가 이들을 조율합니다:
    1. stock_market_agent: 기술적 분석 담당
    2. news_analysis_agent: 뉴스 분석 담당
    3. global_macro_agent: 글로벌 경제 분석 담당
    4. stock_sector_analysis_agent: 섹터 분석 담당
    5. investment_sentiment_agent: 투자 심리 분석 담당
    
    Args:
        model_id (str): 사용할 AI 모델 ID
        
    Returns:
        ToolCallingAgent: 설정된 매니저 에이전트
    """
    text_limit = 100000  # 텍스트 처리 제한

    # AI 모델 초기화 - Claude 3.5 Sonnet 사용
    model = LiteLLMModel(
        model_id="anthropic/claude-3-7-sonnet-latest",
        api_key=os.getenv("ANTHROPIC_API_KEY"),
        custom_role_conversions=custom_role_conversions,
        max_completion_tokens=8192*4,
        temperature = 0.001
    )

    # 모든 에이전트가 공유할 웹 브라우저 및 기본 도구들 설정
    browser = SimpleTextBrowser(**BROWSER_CONFIG)
    WEB_TOOLS = [
        GoogleSearchTool(provider="serper"),
        VisitTool(browser),
        PageUpTool(browser),
        PageDownTool(browser),
        FinderTool(browser),
        FindNextTool(browser),
        ArchiveSearchTool(browser),
        TextInspectorTool(model, text_limit),
    ]
    
    # 각 에이전트별 전문 도구 설정
    # 1. 기술적 분석 에이전트용 도구 (StockAnalysisTool 추가)
    stock_market_tools = WEB_TOOLS.copy()
    stock_market_tools.append(StockAnalysisTool())  # 주식 차트 시각화 도구
    
    # 2. 글로벌 경제 분석 에이전트용 도구 (StockDataImageTool 추가)
    globalmacro_tools = WEB_TOOLS.copy()
    globalmacro_tools.append(StockDataImageTool())  # 주식 데이터 이미지 생성 도구
    
    # 3. 섹터 분석 에이전트용 도구 (StockDataImageTool 추가)
    stocksector_tools = WEB_TOOLS.copy()
    stocksector_tools.append(StockDataImageTool())  # 주식 데이터 이미지 생성 도구
    
    # 4. 투자 심리 분석 에이전트용 도구 (SentimentTool 추가)
    sentiment_tools = WEB_TOOLS.copy()
    sentiment_tools.append(SentimentTool())  # 감정 분석 도구

    # === 전문 에이전트들 생성 ===
    
    # 1) 기술적 분석 에이전트 - 차트 패턴, 지표 분석 등
    stock_market_agent = ToolCallingAgent(
        model=model,
        tools=stock_market_tools,  # 주식 분석 도구 포함
        max_steps=10,  # 최대 작업 단계 수
        verbosity_level=2,  # 로그 상세도 (0-3, 2=중간)
        planning_interval=3,  # 3단계마다 계획 재검토
        name="stock_market_agent",
        description=STOCK_MARKET_AGENT_DESCRIPTION,  # 에이전트 역할 설명
        provide_run_summary=True,  
    )
    # 기본 프롬프트에 추가 지시사항 결합
    stock_market_agent.prompt_templates["managed_agent"]["task"] += STOCK_MARKET_AGENT_TASK_ADDITION

    # 2) 뉴스 분석 에이전트 - 최신 뉴스, 업계 동향 분석
    news_analysis_agent = ToolCallingAgent(
        model=model,
        tools=WEB_TOOLS,  # 기본 웹 도구만 사용 (뉴스 검색 중심)
        max_steps=12,  # 더 많은 단계 허용 (다양한 뉴스 소스 검색)
        verbosity_level=2,
        planning_interval=4,
        name="news_analysis_agent",
        description=NEWS_ANALYSIS_AGENT_DESCRIPTION,
        provide_run_summary=True,
    )
    news_analysis_agent.prompt_templates["managed_agent"]["task"] += NEWS_ANALYSIS_AGENT_TASK_ADDITION

    # 3) 글로벌 경제 분석 에이전트 - 거시경제, 금리, 통화정책 분석
    global_macro_agent = ToolCallingAgent(
        model=model,
        tools=globalmacro_tools,
        max_steps=12,
        verbosity_level=2,
        planning_interval=4,
        name="global_macro_agent",
        description=GLOBAL_MACRO_AGENT_DESCRIPTION,
        provide_run_summary=True,
    )
    global_macro_agent.prompt_templates["managed_agent"]["task"] += GLOBAL_MACRO_AGENT_TASK_ADDITION

    # 4) 주식 섹터 분석 에이전트 - 산업별, 섹터별 트렌드 분석
    stock_sector_analysis_agent = ToolCallingAgent(
        model=model,
        tools=stocksector_tools,
        max_steps=12,
        verbosity_level=2,
        planning_interval=4,
        name="stock_sector_analysis_agent",
        description=STOCK_SECTOR_ANALYSIS_AGENT_DESCRIPTION,
        provide_run_summary=True,
    )
    stock_sector_analysis_agent.prompt_templates["managed_agent"]["task"] += STOCK_SECTOR_ANALYSIS_AGENT_TASK_ADDITION

    # 5) 투자 심리 분석 에이전트 - 시장 감정, 투자자 심리 분석
    investment_sentiment_agent = ToolCallingAgent(
        model=model,
        tools=sentiment_tools,
        max_steps=12,
        verbosity_level=2,
        planning_interval=4,
        name="investment_sentiment_agent",
        description=INVESTMENT_SENTIMENT_AGENT_DESCRIPTION,
        provide_run_summary=True,
    )
    investment_sentiment_agent.prompt_templates["managed_agent"]["task"] += INVESTMENT_SENTIMENT_AGENT_TASK_ADDITION
    
    # === 매니저 에이전트 생성 ===
    # 모든 전문 에이전트들을 조율하고 결과를 통합하는 매니저
    manager_agent = ToolCallingAgent(
        model=model,
        tools=[],  # 매니저는 직접 도구를 사용하지 않고 하위 에이전트들에게 위임
        max_steps=12,
        verbosity_level=2,
        planning_interval=10,
        managed_agents=[
            stock_market_agent,          # 기술적 분석
            news_analysis_agent,         # 뉴스 분석
            global_macro_agent,          # 글로벌 경제 분석
            stock_sector_analysis_agent, # 섹터 분석
            investment_sentiment_agent   # 투자 심리 분석
        ],
    )
    
    manager_agent.prompt_templates["system_prompt"] += MANAGER_AGENT_SYSTEM_PROMPT_ADDITION

    return manager_agent

def create_podcast_agent(model_id="claude-3-7-sonnet-latest"):
    """팟캐스트 생성을 위한 에이전트 시스템을 생성하는 함수
    
    3개의 전문 에이전트를 생성하여 팟캐스트 제작을 버쩔화합니다:
    1. persona_agent: 두 명의 팟캐스트 진행자 캐릭터 생성
    2. planning_agent: 팟캐스트 구성과 흐름 계획
    3. script_generate_agent: 최종 대본 생성 (매니저 역할)
    
    Args:
        model_id (str): 사용할 AI 모델 ID
        
    Returns:
        ToolCallingAgent: 설정된 대본 생성 에이전트
    """
    text_limit = 100000  # 텍스트 처리 제한

    # AI 모델 초기화 - 팟캐스트 생성용
    model = LiteLLMModel(
        model_id="anthropic/claude-3-7-sonnet-latest",
        api_key=os.getenv("ANTHROPIC_API_KEY"),
        custom_role_conversions=custom_role_conversions,
        max_completion_tokens=8192*4,
        temperature = 0.001
    )
    
    # === 팟캐스트 제작 전문 에이전트들 ===
    
    # 1) 페르소나 에이전트 - 두 명의 차별화된 팟캐스트 진행자 캐릭터 생성
    persona_agent = ToolCallingAgent(
        model=model,
        tools=[],
        max_steps=10,
        verbosity_level=2,
        planning_interval=3,
        name="persona_agent",
        description=PERSONA_AGENT_DESCRIPTION,
        provide_run_summary=True,
    )
    persona_agent.prompt_templates["managed_agent"]["task"] += PERSONA_AGENT_TASK_ADDITION
    
    # 2) 계획 에이전트 - 팟캐스트의 구성과 흐름 설계
    planning_agent = ToolCallingAgent(
        model=model,
        tools=[],
        max_steps=10,
        verbosity_level=2,
        planning_interval=3,
        name="planning_agent",
        description=PLANNING_AGENT_DESCRIPTION,
        provide_run_summary=True,
    )
    planning_agent.prompt_templates["managed_agent"]["task"] += PLANNING_AGENT_TASK_ADDITION
    
    # 3) 대본 생성 에이전트 (매니저) - 캐릭터와 계획을 바탕으로 최종 대본 생성
    script_generate_agent = ToolCallingAgent(    
        model=model,
        tools =[],
        max_steps=12,
        verbosity_level=2,
        planning_interval=10,
        managed_agents=[
            persona_agent,   # 캐릭터 생성 담당
            planning_agent   # 구성 계획 담당
        ],
        name="script_generate_agent",
        provide_run_summary=True,
    )
    
    script_generate_agent.prompt_templates["system_prompt"] += SCRIPT_GENERATE_AGENT_SYSTEM_PROMPT_ADDITION

    return script_generate_agent

def main():
    """메인 실행 함수 - 주식 분석부터 팟캐스트 생성까지 전체 파이프라인 실행
    
    전체 프로세스:
    1. 멀티 에이전트로 주식 분석 리포트 생성
    2. 리포트를 바탕으로 팟캐스트 대본 1차 생성
    3. 대본을 10분 버전으로 개선 (2차)
    4. 대본을 3분 버전으로 축약 (3차)
    5. 사용자 선택에 따라 오디오 생성
    6. 임시 파일들 정리
    """
    # 명령행 인자 파싱
    args = parse_args()
    
    # === 1단계: 주식 분석 리포트 생성 ===
    print(" 주식 분석을 시작합니다...")
    agent = create_agent(model_id=args.model_id)
    answer = agent.run(args.question)
    print(f"Got this answer: {answer}")
    
    # 분석 결과를 파일로 저장 
    with open("investment_report.txt", "w", encoding="utf-8") as f:
        f.write(answer)
    
    # === 2단계: 1차 팟캐스트 대본 생성 ===
    print("팟캐스트 대본 생성을 시작합니다")
    
    # 팟캐스트 에이전트로 1차 대본 생성 
    podcast_agent = create_podcast_agent(model_id=args.model_id)
    podcastscript_ver1 = podcast_agent.run(answer)
    
    print("1차 팟캐스트 대본 생성 완료")
    
    # === 3단계: 2차 팟캐스트 대본 생성 (10분 버전) ===
    print("10분 팟캐스트 대본으로 개선 중")
    
    # 2차 개선용 LLM 모델 설정 
    podcast_llm = LiteLLMModel(
        model_id="anthropic/claude-3-7-sonnet-latest",
        api_key=os.getenv("ANTHROPIC_API_KEY"),
        max_completion_tokens=8192*4,
        temperature=0.3  
    )
    
    # 10분 팟캐스트로 개선하는 프롬프트 생성
    podcast_prompt = PODCAST_ENHANCEMENT_PROMPT.format(podcastscript_ver1=podcastscript_ver1)
       
    messages = [
        {"role": "user", "content": podcast_prompt}
    ]
    response = podcast_llm(messages)
    podcastscript_ver2 = response.content  # ChatMessage 객체에서 content 추출
    
    print("10분 팟캐스트 대본 생성 완료")

    # === 4단계: 3차 팟캐스트 대본 생성 (3분 버전) ===
    print("3분 팟캐스트 대본으로 축약 중")

    # 3차 축약용 LLM 모델 설정
    podcast_3m_llm = LiteLLMModel(
        model_id="anthropic/claude-3-7-sonnet-latest",
        api_key=os.getenv("ANTHROPIC_API_KEY"),
        max_completion_tokens=8192*4,
        temperature=0.3  # 자연스러운 대화 유지
    )
    
    # 3분 팟캐스트로 축약하는 프롬프트 생성
    podcast_3m_prompt = PODCAST_CONDENSATION_PROMPT.format(podcastscript_ver2=podcastscript_ver2)
       
    messages = [
        {"role": "user", "content": podcast_3m_prompt}
    ]
    response = podcast_3m_llm(messages)
    podcastscript_ver3 = response.content  # ChatMessage 객체에서 content 추출
    
    print("3분 팟캐스트 대본 생성 완료")

    # === 5단계: 팟캐스트 오디오 생성 ===
    print("팟캐스트 오디오 생성을 시작합니다...")

    # OpenAI TTS API 클라이언트 초기화
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    
    # 사용자 선택에 따라 사용할 대본 결정 (변수에서 직접 선택)
    if args.podcast_length == 2:  # 10분 팟캐스트 선택
        podcastscript = podcastscript_ver2
        print("10분 팟캐스트 오디오를 생성합니다.")
    else:  # 3분 팟캐스트 (기본값)
        podcastscript = podcastscript_ver3
        print("3분 팟캐스트 오디오를 생성합니다.")
    
    # 대본을 대사별로 분리 (빈 줄 두 개를 기준으로 분리)
    scripts = [line for line in podcastscript.split('\n\n') if line.strip()]
    
    # 두 진행자의 음성 설정 (OpenAI TTS 음성)
    voices = ["nova", "onyx"]  # nova: 여성 목소리, onyx: 남성 목소리
    
    # 임시 오디오 파일들을 저장할 리스트
    temp_files = []
    
    # 각 대사별로 음성 생성 및 TTS 변환
    for i, script in enumerate(scripts):
        # 빈 대사는 건너뛰기
        if not script.strip():
            continue
            
        # 진행자 번호에 따라 음성 선택
        # 짝수 인덱스 = 첫번째 진행자(nova), 홀수 인덱스 = 두번째 진행자(onyx)
        voice = voices[i % 2]
        
        # 임시 오디오 파일 경로 생성
        temp_path = f"temp_speech_{i}.mp3"
        temp_files.append(temp_path)
        
        print(f"🎤 대사 {i+1}/{len(scripts)} 음성 생성 중... ({voice} 목소리)")
        
        # OpenAI TTS로 음성 생성
        response = client.audio.speech.create(
            model="tts-1",  # OpenAI TTS 모델
            voice=voice,     # 선택된 목소리
            input=script     # 변환할 텍스트
        )
        
        # 임시 파일로 저장
        response.stream_to_file(temp_path)
    
    # 모든 오디오 파일을 순차적으로 합치기
    print("오디오 파일들을 합치는 중...")
    combined = AudioSegment.empty() 
    
    for temp_file in temp_files:
        audio_segment = AudioSegment.from_mp3(temp_file)  # MP3 파일 로드
        combined += audio_segment  # 기존 오디오에 이어붙이기
    
    # 최종 팟캐스트 오디오 파일로 내보내기
    output_path = "podcast_final.mp3"
    combined.export(output_path, format="mp3")
    
    print(f"✅ 팟캐스트 오디오 파일이 {output_path}에 저장되었습니다!")
    
    # === 6단계: 임시 파일 정리 ===
    print("🧹 임시 파일들을 정리하는 중...")
    
    for temp_file in temp_files:
        try:
            os.remove(temp_file)
            print(f"✅ 임시 오디오 파일 {temp_file} 삭제 완료")
        except FileNotFoundError:
            pass  
    
    analysis_files = glob.glob("*analysis.png")
    for analysis_file in analysis_files:
        try:
            os.remove(analysis_file)
            print(f"✅ 분석 이미지 파일 {analysis_file} 삭제 완료")
        except FileNotFoundError:
            pass  
    
    print("모든 작업이 완료되었습니다")

if __name__ == "__main__":
    main()