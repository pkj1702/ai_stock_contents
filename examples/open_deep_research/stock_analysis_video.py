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
from prompts.stockvideo_prompts import *

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
    """메인 주식 분석 에이전트 생성 - 단기/중기 분석을 담당하는 두 개의 하위 에이전트를 관리"""
    text_limit = 100000

    # Initialize the LLM model.
    model = LiteLLMModel(
        model_id="anthropic/claude-3-7-sonnet-latest",
        api_key=os.getenv("ANTHROPIC_API_KEY"),
        custom_role_conversions=custom_role_conversions,
        max_completion_tokens=8192*4,
        temperature = 0.001
    )
    
    # 1) 단기 분석 에이전트 - 시간봉, 10일 차트 분석 (트레이딩 관점)
    short_term_agent = ToolCallingAgent(
        model=model,
        tools=[StockAnalysisShort()],
        max_steps=10,
        verbosity_level=2,
        planning_interval=3,
        name="short_term_agent",
        description=SHORT_TERM_AGENT_DESCRIPTION,
        provide_run_summary=True,
    )
    
    # 2) 중기 분석 에이전트 - 일봉, 150일 차트 분석 (투자 관점)
    medium_term_agent = ToolCallingAgent(
        model=model,
        tools=[StockAnalysisMid()],
        max_steps=10,
        verbosity_level=2,
        planning_interval=3,
        name="medium_term_agent",
        description=MEDIUM_TERM_AGENT_DESCRIPTION,
        provide_run_summary=True,
    )
    
    # 각 에이전트에 특화된 추가 지시사항 설정
    short_term_agent.prompt_templates["managed_agent"]["task"] += SHORT_TERM_AGENT_ADDITIONAL_TASK
    medium_term_agent.prompt_templates["managed_agent"]["task"] += MEDIUM_TERM_AGENT_ADDITIONAL_TASK
    
    # 관리자 에이전트 - 단기/중기 분석 에이전트들을 조율하고 종합 분석 제공
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
    
    manager_agent.prompt_templates["system_prompt"] += MANAGER_AGENT_SYSTEM_PROMPT

    return manager_agent

##########################################################  차트 마킹 에이전트들  ########################################################################################
# 분석 텍스트에 맞는 차트 이미지를 생성하는 에이전트들

prompt = GRAPH_MARK_AGENT_PROMPT

def create_midgraphmark_agent(model_id="claude-3-7-sonnet-latest"):
    """중기 분석용 차트 마킹 에이전트 - 분석 내용에 따라 차트에 기술적 지표를 표시"""
    text_limit = 100000

    # Initialize the LLM model.
    model = LiteLLMModel(
        model_id="anthropic/claude-3-7-sonnet-latest",
        api_key=os.getenv("ANTHROPIC_API_KEY"),
        custom_role_conversions=custom_role_conversions,
        max_completion_tokens=8192*2,
        temperature = 0.001
    )
    
    # 중기 차트 마킹 도구를 사용하는 에이전트
    manager_agent = ToolCallingAgent(      
        model=model,
        tools =[MidStockMarkTool()],  # 일봉 차트 마킹 도구
        max_steps=1,
        verbosity_level=2,
        planning_interval=10,
        managed_agents=[],
    )
    
    manager_agent.prompt_templates["system_prompt"] += prompt
    manager_agent.prompt_templates["managed_agent"]["task"] = MANAGED_AGENT_TASK_TEMPLATE
    return manager_agent

def create_shortgraphmark_agent(model_id="claude-3-7-sonnet-latest"):
    """단기 분석용 차트 마킹 에이전트 - 단기 트레이딩 관점의 차트 마킹"""
    text_limit = 100000

    # Initialize the LLM model.
    model = LiteLLMModel(
        model_id="anthropic/claude-3-7-sonnet-latest",
        api_key=os.getenv("ANTHROPIC_API_KEY"),
        custom_role_conversions=custom_role_conversions,
        max_completion_tokens=8192*2,
        temperature = 0.001
    )
    
    # 단기 차트 마킹 도구를 사용하는 에이전트
    manager_agent = ToolCallingAgent(      
        model=model,
        tools =[ShortStockMarkTool()],  # 시간봉 차트 마킹 도구
        max_steps=1,
        verbosity_level=2,
        planning_interval=10,
        managed_agents=[],
    )
    
    manager_agent.prompt_templates["system_prompt"] += prompt
    manager_agent.prompt_templates["managed_agent"]["task"] = MANAGED_AGENT_TASK_TEMPLATE
    return manager_agent

####################################################### 스크립트 생성 에이전트들 ###################################################################################
# 분석 리포트를 비디오용 스크립트로 변환하는 에이전트들

def create_midprompt_agent(model_id="claude-3-7-sonnet-latest"):
    """중기 분석 리포트를 비디오 스크립트로 변환하는 에이전트"""
    text_limit = 100000

    # Initialize the LLM model.
    model = LiteLLMModel(
        model_id="anthropic/claude-3-7-sonnet-latest",
        api_key=os.getenv("ANTHROPIC_API_KEY"),
        custom_role_conversions=custom_role_conversions,
        max_completion_tokens=8192*2,
        temperature = 0.001
    )
    
    # 스크립트 변환 에이전트 (도구 없이 텍스트 변환만 수행)
    manager_agent = ToolCallingAgent(      
        model=model,
        tools =[],
        max_steps=1,
        verbosity_level=2,
        planning_interval=10,
        managed_agents=[],
    )
    
    manager_agent.prompt_templates["system_prompt"] += MID_PROMPT_AGENT_SYSTEM_PROMPT
    return manager_agent

def create_shortprompt_agent(model_id="claude-3-7-sonnet-latest"):
    """단기 분석 리포트를 비디오 스크립트로 변환하는 에이전트"""
    text_limit = 100000

    # Initialize the LLM model.
    model = LiteLLMModel(
        model_id="anthropic/claude-3-7-sonnet-latest",
        api_key=os.getenv("ANTHROPIC_API_KEY"),
        custom_role_conversions=custom_role_conversions,
        max_completion_tokens=8192*2,
        temperature = 0.001
    )
    
    # 스크립트 변환 에이전트
    manager_agent = ToolCallingAgent(      
        model=model,
        tools =[],
        max_steps=1,
        verbosity_level=2,
        planning_interval=10,
        managed_agents=[],
    )
    
    manager_agent.prompt_templates["system_prompt"] += SHORT_PROMPT_AGENT_SYSTEM_PROMPT
    return manager_agent

def create_final_prompt_agent(model_id="claude-3-7-sonnet-latest"):
    """최종 스크립트 다듬기 에이전트 - 자연스러운 음성용 텍스트로 변환"""
    text_limit = 100000

    # Initialize the LLM model.
    model = LiteLLMModel(
        model_id="anthropic/claude-3-7-sonnet-latest",
        api_key=os.getenv("ANTHROPIC_API_KEY"),
        custom_role_conversions=custom_role_conversions,
        max_completion_tokens=8192*2,
        temperature = 0.001
    )
    
    # 최종 스크립트 편집 에이전트
    manager_agent = ToolCallingAgent(      
        model=model,
        tools =[],
        max_steps=1,
        verbosity_level=2,
        planning_interval=10,
        managed_agents=[],
    )
    
    manager_agent.prompt_templates["system_prompt"] += FINAL_PROMPT_AGENT_SYSTEM_PROMPT
    return manager_agent

####################################################### 비디오 생성 함수 #####################################################################################

def create_investment_video(audio_script, subtitle_script):
    """
    투자 분석 비디오 생성 함수
    - 차트 이미지와 AI 음성을 결합하여 자막이 포함된 분석 동영상 제작
    - 문장 단위로 구분하여 자연스러운 흐름 유지
    
    Parameters:
    - audio_script: TTS 음성 생성용 스크립트 (발음 최적화된 텍스트)
    - subtitle_script: 자막 표시용 스크립트 (원본 텍스트)
    """
    print("Starting investment video creation...")
    import os
    import re
    
    # Initialize OpenAI client
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    
    # 오디오 스크립트와 자막 스크립트를 라인별로 분리 처리
    # 문자열 또는 리스트 형태 모두 지원
    if isinstance(audio_script, str):
        audio_lines = [line.strip() for line in audio_script.split('\n') if line.strip()]
    else:
        audio_lines = []
        for item in audio_script:
            if isinstance(item, str):
                lines = [line.strip() for line in item.split('\n') if line.strip()]
                audio_lines.extend(lines)
    
    if isinstance(subtitle_script, str):
        subtitle_lines = [line.strip() for line in subtitle_script.split('\n') if line.strip()]
    else:
        subtitle_lines = []
        for item in subtitle_script:
            if isinstance(item, str):
                lines = [line.strip() for line in item.split('\n') if line.strip()]
                subtitle_lines.extend(lines)
    
    # Ensure both scripts have the same number of lines
    if len(audio_lines) != len(subtitle_lines):
        print(f"Warning: Audio script has {len(audio_lines)} lines but subtitle script has {len(subtitle_lines)} lines.")
        # Use the minimum number of lines
        min_lines = min(len(audio_lines), len(subtitle_lines))
        audio_lines = audio_lines[:min_lines]
        subtitle_lines = subtitle_lines[:min_lines]
    
    all_clips = []
    subtitle_entries = []
    subtitle_index = 1
    current_time = 0.0
    
    # 각 라인별로 오디오와 자막을 동시 처리
    for i, (audio_line, subtitle_line) in enumerate(zip(audio_lines, subtitle_lines)):
        print(f"Processing line {i+1}/{len(audio_lines)}: {subtitle_line[:30]}...")
        
        # 문장부호(마침표, 쉼표) 기준으로 세그먼트 분할 - 자연스러운 음성 흐름을 위함
        audio_segments = re.split(r'(?<=[.,])\s+', audio_line)
        subtitle_segments = re.split(r'(?<=[.,])\s+', subtitle_line)
        
        # Clean empty segments
        audio_segments = [seg.strip() for seg in audio_segments if seg.strip()]
        subtitle_segments = [seg.strip() for seg in subtitle_segments if seg.strip()]
        
        # Ensure both have the same number of segments
        if len(audio_segments) != len(subtitle_segments):
            print(f"Warning: Line {i+1} has {len(audio_segments)} audio segments but {len(subtitle_segments)} subtitle segments.")
            # Use the minimum number of segments
            min_segments = min(len(audio_segments), len(subtitle_segments))
            audio_segments = audio_segments[:min_segments]
            subtitle_segments = subtitle_segments[:min_segments]
        
        if not audio_segments:  # Skip if no valid segments
            continue
            
        # 각 라인에 해당하는 차트 이미지 찾기 (차트 마킹 에이전트가 생성한 이미지)
        img_path = f"technical_analysis{i}.png"
        if not os.path.exists(img_path):
            print(f"경고: 이미지 {img_path}를 찾을 수 없습니다. 대체 이미지를 사용합니다.")
            potential_images = glob.glob("technical_analysis*.png")
            if potential_images:
                img_path = potential_images[0]
                print(f"대체 이미지 사용: {img_path}")
            else:
                raise FileNotFoundError(f"라인 {i+1}에 해당하는 기술적 분석 이미지를 찾을 수 없습니다.")
        
        segment_clips = []
        
        # 각 세그먼트 쌍(오디오-자막) 처리
        for j, (audio_segment, subtitle_segment) in enumerate(zip(audio_segments, subtitle_segments)):
            # OpenAI TTS API를 사용하여 음성 생성
            audio_path = f"audio_{i}_{j}.mp3"
            print(f"라인 {i+1}의 세그먼트 {j+1}/{len(audio_segments)} 음성 변환 중: {audio_segment}")
            
            response = client.audio.speech.create(
                model="tts-1-hd",
                voice="nova",
                input=audio_segment
            )
            response.stream_to_file(audio_path)
            
            # Load audio and get duration
            audio_clip = AudioFileClip(audio_path)
            audio_duration = audio_clip.duration
            print(f"Segment audio duration: {audio_duration:.2f} seconds")
            
            # Create clip with image and this segment's audio
            img_clip = ImageClip(img_path).with_duration(audio_duration)
            video_with_audio = img_clip.with_audio(audio_clip)
            segment_clips.append(video_with_audio)
            
            # Add subtitle entry using subtitle segment
            start_time = current_time
            end_time = current_time + audio_duration
            
            start_str = format_srt_time(start_time)
            end_str = format_srt_time(end_time)
            
            subtitle_entries.append(f"{subtitle_index}\n{start_str} --> {end_str}\n{subtitle_segment}\n")
            subtitle_index += 1
            
            current_time += audio_duration
        
        # Concatenate all segments from this line
        if segment_clips:
            line_clip = concatenate_videoclips(segment_clips)
            all_clips.append(line_clip)
    
    # 모든 클립을 최종 비디오로 결합
    print("모든 클립을 최종 비디오로 결합하는 중...")
    if all_clips:
        final_video = concatenate_videoclips(all_clips)
        
        # 임시 비디오 파일로 출력
        temp_video_path = "temp_video.mp4"
        print(f"임시 비디오를 {temp_video_path}에 저장 중...")
        final_video.write_videofile(temp_video_path, fps=24)
        
        # Write SRT file
        with open("subtitles.srt", "w", encoding="utf-8") as f:
            f.write("\n".join(subtitle_entries))
        
        # Use FFmpeg to add subtitles to the video
        import subprocess
        output_path = "investment_analysis_video.mp4"
        
        try:
            print("FFmpeg로 자막 추가 중...")
            # FFmpeg를 사용하여 자막을 비디오에 하드코딩 (한글 지원, 스타일 적용)
            subprocess.run([
                "ffmpeg", "-y",
                "-i", temp_video_path,
                "-vf", "subtitles=subtitles.srt:force_style='FontSize=18,BorderStyle=0,Outline=0.2,PrimaryColour=ffffff,MarginV=10'",
                "-c:a", "copy",
                output_path
            ], check=True)
            print("자막이 성공적으로 추가되었습니다!")
        except Exception as e:
            print(f"자막 추가 중 오류 발생: {e}")
            print("자막 없는 비디오로 대체합니다...")
            import shutil
            shutil.copy(temp_video_path, output_path)
        
        # Clean up temporary files
        os.remove(temp_video_path)
        if os.path.exists("subtitles.srt"):
            os.remove("subtitles.srt")
        for i in range(len(audio_lines)):
            for j in range(10):  # Assuming max 10 segments per line
                audio_path = f"audio_{i}_{j}.mp3"
                if os.path.exists(audio_path):
                    os.remove(audio_path)
        
        print(f"Video creation complete! Output: {output_path}")
        return output_path
    else:
        print("Error: No clips were created. Check your input scripts.")
        return None

# Keep the existing format_srt_time function unchanged
def format_srt_time(seconds):
    """Convert seconds to SRT format time (HH:MM:SS,mmm)"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millisecs = int((seconds - int(seconds)) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millisecs:03d}"

def cleanup_analysis_files():
    """
    비디오 생성 과정에서 생성된 임시 분석 파일들(PNG, JSON)을 정리하는 함수
    - 차트 이미지와 분석 데이터 파일들을 삭제하여 디스크 공간 확보
    """
    print("임시 분석 파일들을 정리하는 중...")
    
    # analysis가 포함된 PNG 파일들 찾기
    png_files = glob.glob("*analysis*.png")
    
    # analysis가 포함된 JSON 파일들 찾기  
    json_files = glob.glob("*analysis*.json")
    
    deleted_files = []
    
    # PNG 파일들 삭제
    for png_file in png_files:
        try:
            os.remove(png_file)
            deleted_files.append(png_file)
            print(f"삭제됨: {png_file}")
        except OSError as e:
            print(f"삭제 실패 {png_file}: {e}")
    
    # JSON 파일들 삭제
    for json_file in json_files:
        try:
            os.remove(json_file)
            deleted_files.append(json_file)
            print(f"삭제됨: {json_file}")
        except OSError as e:
            print(f"삭제 실패 {json_file}: {e}")
    
    if deleted_files:
        print(f"총 {len(deleted_files)}개의 분석 파일이 정리되었습니다.")
    else:
        print("정리할 분석 파일이 없습니다.")
    
    return deleted_files

################################################### Main ###################################################

################################################### 메인 실행 함수 ###################################################

def main():
    """주식 분석 비디오 생성 메인 프로세스
    1. 주식 분석 수행 (단기/중기)
    2. 분석 결과를 비디오 스크립트로 변환
    3. 차트 이미지 생성
    4. 음성 합성 및 비디오 제작
    """
    args = parse_args()
    
    # 1단계: 주식 분석 수행 - 단기/중기 분석을 총괄하는 관리자 에이전트 생성
    agent = create_agent(model_id=args.model_id)
    answer = agent.run(args.question)
    print(f"분석 결과: {answer}")
    
    # 분석 결과를 텍스트 파일로 저장
    with open("investment_report.txt", "w", encoding="utf-8") as f:
        f.write(answer)
    
    ########################################### 2단계: 스크립트 변환 ##############################################
    
    output_content = answer  
    
    # 중기 분석 리포트를 비디오 스크립트로 변환
    midprompt_agent = create_midprompt_agent(model_id=args.model_id)
    midterm_script = midprompt_agent.run(output_content)
    
    # 단기 분석 리포트를 비디오 스크립트로 변환
    shortprompt_agent = create_shortprompt_agent(model_id=args.model_id)
    shortterm_script = shortprompt_agent.run(output_content)
    
    ########################################### 3단계: 최종 스크립트 다듬기 ############################################
    
    # 자연스러운 음성 변환을 위한 최종 스크립트 에이전트
    final_prompt_agent = create_final_prompt_agent(model_id=args.model_id)
    
    # 중기 스크립트를 문단별로 분할하여 각각 다듬기
    midterm_paragraph = re.split(r'\n\s*\n', midterm_script.strip())
    mid_final_script = ""
    
    for i in range(len(midterm_paragraph)):    
        mid_final_script += final_prompt_agent.run(midterm_paragraph[i]) + "\n\n"
        
    # 단기 스크립트를 문단별로 분할하여 각각 다듬기
    shortterm_paragraph = re.split(r'\n\s*\n', shortterm_script.strip())
    short_final_script = ""
    
    for i in range(len(shortterm_paragraph)):    
        short_final_script += final_prompt_agent.run(shortterm_paragraph[i]) + "\n\n"

    
    ###############################################  4단계: 차트 이미지 생성  ###################################
    # 스크립트 내용에 맞는 기술적 분석 차트 이미지들을 생성
    
    mid_graphmark_agent = create_midgraphmark_agent(model_id=args.model_id)
    short_graphmark_agent = create_shortgraphmark_agent(model_id=args.model_id)
    
    # 중기 분석 스크립트에 대응하는 차트 이미지 생성
    midterm_paragraph = re.split(r'\n\s*\n', mid_final_script.strip())
    
    for i in range(len(midterm_paragraph)):   # 각 문단별로 처리
        ex = midterm_paragraph[i].split('\n')
        for j in range(1, len(ex) + 1):  # 문장별로 누적하여 차트 마킹
            accumulated_text = '\n'.join(ex[:j])
            answer = mid_graphmark_agent(accumulated_text)
    
    # 단기 분석 스크립트에 대응하는 차트 이미지 생성
    shortterm_paragraph = re.split(r'\n\s*\n', short_final_script.strip())
    
    for i in range(len(shortterm_paragraph)):   # 각 문단별로 처리
        ex = shortterm_paragraph[i].split('\n')
        for j in range(1, len(ex) + 1):  # 문장별로 누적하여 차트 마킹
            accumulated_text2 = '\n'.join(ex[:j])
            answer = short_graphmark_agent(accumulated_text2)
        
    ###############################################  5단계: 음성용 스크립트 생성  ###################################
    
    # 중기 + 단기 스크립트를 하나로 합쳐서 자막용 스크립트 생성
    subtitle_script = mid_final_script + short_final_script
    
    # 음성 변환에 최적화된 스크립트 생성을 위한 LLM 모델
    audio_llm = LiteLLMModel(
        model_id="anthropic/claude-3-7-sonnet-latest",
        api_key=os.getenv("ANTHROPIC_API_KEY"),
        max_completion_tokens=8192*4,
        temperature=0.001  # Slightly more creative for natural dialogue
    )
    
    # 자막 스크립트를 TTS에 적합한 발음 친화적 스크립트로 변환
    audio_prompt = AUDIO_PROMPT_TEMPLATE.format(subtitle_script=subtitle_script)
       
    messages = [
        {"role": "user", "content": audio_prompt}
    ]
    response = audio_llm(messages)
    audio_script = response.content  # ChatMessage 객체에서 content를 추출
    
    ################################################################# 6단계: 최종 비디오 생성 ####################################################################################

    # 음성, 차트 이미지, 자막을 결합하여 최종 투자 분석 동영상 생성
    video_path = create_investment_video(audio_script, subtitle_script)
    print(f"투자 분석 비디오가 생성되었습니다: {video_path}")
    
    # 비디오 생성 완료 후 임시 파일들 정리 (디스크 공간 확보)
    cleanup_analysis_files()

if __name__ == "__main__":
    main()