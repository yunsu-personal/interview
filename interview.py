
import tkinter as tk
from tkinter import messagebox
import random
import time
import threading
import asyncio
import edge_tts
import pygame
import os
import tempfile
import uuid
import queue as thread_queue


# =========================================================
# 1. 음성 재생 초기화
# =========================================================

pygame.mixer.init()

TEMP_DIR = os.path.join(tempfile.gettempdir(), "interview_simulator_tts")
os.makedirs(TEMP_DIR, exist_ok=True)


# =========================================================
# 2. 질문 목록
# =========================================================

base_questions = {
    "ko": [
        "우리 회사에 지원한 이유는 무엇인가요?",
        "본인의 강점은 무엇인가요?",
        "단점은 무엇인가요?",
        "팀워크 경험을 말해주세요.",
        "어려움을 극복한 경험은?",
        "커리어 목표는?",
        "최근 배운 것은?",
        "스트레스 관리 방법은?",
        "성공 경험을 하나 말해주세요.",
        "실패 경험을 말해주세요."
    ],
    "ja": [
        "志望動機を教えてください。",
        "あなたの強みは何ですか？",
        "弱みは何ですか？",
        "チーム経験を教えてください。",
        "困難を乗り越えた経験は？",
        "キャリアプランは？",
        "最近学んだことは？",
        "ストレス対処法は？",
        "成功体験を教えてください。",
        "失敗経験を教えてください。"
    ],
    "en": [
        "Why do you want to join us?",
        "What are your strengths?",
        "What is your weakness?",
        "Tell me about teamwork experience.",
        "Describe a challenge you overcame.",
        "What are your career goals?",
        "What did you learn recently?",
        "How do you handle stress?",
        "Tell me about a success.",
        "Tell me about a failure."
    ]
}


# 면접 시작 시 고정 질문 2개
start_fixed = {
    "ko": [
        "자기 소개 먼저 간단하게 들어볼까요?",
        "전직하려는 이유가 뭔가요?"
    ],
    "ja": [
        "まず簡単に自己紹介をお願いします。",
        "転職理由を教えてください。"
    ],
    "en": [
        "Could you briefly introduce yourself?",
        "Why are you changing jobs?"
    ]
}


# 면접 마지막 고정 질문
end_fixed = {
    "ko": [
        "마지막으로 지원자분께서 궁금하신 점이 있습니까?"
    ],
    "ja": [
        "最後に何か質問はありますか？"
    ],
    "en": [
        "Do you have any questions for us?"
    ]
}


# 사용자가 추가한 질문
# 프로그램을 종료하면 초기화되는 메모리 저장 방식
user_questions = {
    "ko": [],
    "ja": [],
    "en": []
}


# 언어별 음성
voice_map = {
    "ko": "ko-KR-InJoonNeural",
    "ja": "ja-JP-KeitaNeural",
    "en": "en-US-GuyNeural"
}


# =========================================================
# 3. 프로그램 상태
# =========================================================

selected_lang = "ko"

question_queue = []

timer_running = False
start_time = 0

current_audio = None
current_audio_session = None

# 질문이 바뀔 때마다 증가시켜 이전 작업의 결과를 무시
session_id = 0

# 음성 생성 스레드와 GUI 사이의 결과 전달용 큐
tts_results = thread_queue.Queue()

app_closing = False


# =========================================================
# 4. 임시 음성 파일 관리
# =========================================================

def safe_remove(filename):
    """임시 음성 파일 삭제."""
    if not filename:
        return

    try:
        if os.path.exists(filename):
            os.remove(filename)
    except OSError:
        # Windows에서 파일 사용이 끝나지 않은 경우 등
        pass


def stop_audio():
    """현재 재생 중인 음성을 중지하고 파일을 정리."""
    global current_audio, current_audio_session

    try:
        pygame.mixer.music.stop()
        pygame.mixer.music.unload()
    except pygame.error:
        pass

    safe_remove(current_audio)

    current_audio = None
    current_audio_session = None


# =========================================================
# 5. 음성 생성
# =========================================================

def generate_audio(text, lang, session):
    """
    별도 스레드에서 음성을 생성한다.
    이 함수에서는 Tkinter 위젯을 직접 조작하지 않는다.
    """

    filename = os.path.join(
        TEMP_DIR,
        f"interview_{uuid.uuid4().hex}.mp3"
    )

    try:
        async def create_audio():
            communicate = edge_tts.Communicate(
                text,
                voice_map[lang]
            )
            await communicate.save(filename)

        asyncio.run(create_audio())

        if not os.path.exists(filename):
            raise RuntimeError("음성 파일이 생성되지 않았습니다.")

        if os.path.getsize(filename) == 0:
            raise RuntimeError("생성된 음성 파일이 비어 있습니다.")

        tts_results.put({
            "session": session,
            "filename": filename,
            "error": None
        })

    except Exception as e:
        safe_remove(filename)

        tts_results.put({
            "session": session,
            "filename": None,
            "error": str(e)
        })


def poll_tts_results():
    """
    메인 스레드에서 음성 생성 결과를 확인한다.
    Tkinter와 pygame 조작은 여기서 처리한다.
    """

    if app_closing:
        return

    while True:
        try:
            result = tts_results.get_nowait()
        except thread_queue.Empty:
            break

        filename = result["filename"]
        result_session = result["session"]

        # 이미 다음 질문으로 넘어갔다면 이전 결과는 폐기
        if result_session != session_id:
            safe_remove(filename)
            continue

        if result["error"]:
            stop_timer()
            question_label.config(
                text="음성 생성 실패\n인터넷 연결 및 오류 메시지를 확인하세요."
            )

            messagebox.showerror(
                "음성 생성 오류",
                "질문 음성을 생성하지 못했습니다.\n\n"
                + result["error"]
            )

            continue

        play_audio(filename, result_session)

    root.after(100, poll_tts_results)


# =========================================================
# 6. 음성 재생 및 재생 완료 확인
# =========================================================

def play_audio(filename, session):
    """메인 스레드에서 음성을 재생한다."""
    global current_audio, current_audio_session

    if session != session_id:
        safe_remove(filename)
        return

    try:
        pygame.mixer.music.load(filename)
        pygame.mixer.music.play()

        current_audio = filename
        current_audio_session = session

        # 재생 완료 여부를 메인 스레드에서 주기적으로 확인
        root.after(100, check_audio_finished, session, filename)

    except Exception as e:
        safe_remove(filename)

        messagebox.showerror(
            "음성 재생 오류",
            "음성 파일을 재생하지 못했습니다.\n\n" + str(e)
        )


def check_audio_finished(session, filename):
    """음성이 끝나면 타이머를 시작한다."""

    global current_audio, current_audio_session

    if app_closing:
        return

    # 이전 질문의 재생 확인 작업이라면 종료
    if session != session_id:
        return

    if current_audio_session != session:
        return

    try:
        playing = pygame.mixer.music.get_busy()
    except pygame.error:
        playing = False

    if playing:
        root.after(100, check_audio_finished, session, filename)
        return

    # 재생 완료: 파일을 해제하고 삭제
    try:
        pygame.mixer.music.unload()
    except pygame.error:
        pass

    safe_remove(filename)

    current_audio = None
    current_audio_session = None

    # 질문 음성이 끝난 시점부터 답변 시간 측정
    start_timer()


# =========================================================
# 7. 타이머
# =========================================================

def start_timer():
    global timer_running, start_time

    stop_timer()

    timer_running = True
    start_time = time.time()

    update_timer()


def update_timer():
    if not timer_running or app_closing:
        return

    elapsed = int(time.time() - start_time)

    minutes = elapsed // 60
    seconds = elapsed % 60

    timer_label.config(
        text=f"{minutes:02d}:{seconds:02d}"
    )

    root.after(200, update_timer)


def stop_timer():
    global timer_running

    timer_running = False
    timer_label.config(text="00:00")


# =========================================================
# 8. 면접 진행
# =========================================================

def start_interview():
    global question_queue

    middle_questions = (
        base_questions[selected_lang]
        + user_questions[selected_lang]
    )

    # 중간 질문은 중복 없이 무작위 순서로 출제
    random.shuffle(middle_questions)

    question_queue = (
        start_fixed[selected_lang]
        + middle_questions
        + end_fixed[selected_lang]
    )

    lock_controls(True)
    next_btn.config(state="normal")

    ask_next()


def ask_next():
    global question_queue, session_id

    if app_closing:
        return

    # 이전 음성 생성 또는 재생 결과가 더 이상 유효하지 않도록 설정
    session_id += 1
    this_session = session_id

    stop_timer()
    stop_audio()

    if not question_queue:
        end_interview()
        return

    question = question_queue.pop(0)

    question_label.config(text=question)

    # 현재 선택된 언어로 음성 생성
    threading.Thread(
        target=generate_audio,
        args=(question, selected_lang, this_session),
        daemon=True
    ).start()


def end_interview():
    global session_id, question_queue

    # 진행 중인 음성 생성 결과도 무효화
    session_id += 1

    question_queue = []

    stop_timer()
    stop_audio()

    question_label.config(text="면접 종료")

    lock_controls(False)
    next_btn.config(state="disabled")


# =========================================================
# 9. 질문 관리
# =========================================================

def open_manager():
    lang = selected_lang

    win = tk.Toplevel(root)
    win.title(f"질문 관리 - {lang.upper()}")
    win.geometry("620x450")
    win.transient(root)

    tk.Label(
        win,
        text=f"{lang.upper()} 사용자 질문",
        font=("Meiryo", 12, "bold")
    ).pack(pady=(12, 5))

    tk.Label(
        win,
        text="질문을 수정하거나 추가한 뒤 저장하세요."
    ).pack(pady=(0, 8))

    container = tk.Frame(win)
    container.pack(fill="both", expand=True, padx=12, pady=5)

    canvas = tk.Canvas(container)
    scrollbar = tk.Scrollbar(
        container,
        orient="vertical",
        command=canvas.yview
    )

    entry_frame = tk.Frame(canvas)

    entry_frame.bind(
        "<Configure>",
        lambda event: canvas.configure(
            scrollregion=canvas.bbox("all")
        )
    )

    canvas_window = canvas.create_window(
        (0, 0),
        window=entry_frame,
        anchor="nw"
    )

    canvas.configure(yscrollcommand=scrollbar.set)

    canvas.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")

    canvas.bind(
        "<Configure>",
        lambda event: canvas.itemconfigure(
            canvas_window,
            width=event.width
        )
    )

    entries = []

    def add_entry(value=""):
        row = tk.Frame(entry_frame)
        row.pack(fill="x", pady=3)

        entry = tk.Entry(
            row,
            font=("Meiryo", 10)
        )
        entry.pack(
            side="left",
            fill="x",
            expand=True,
            padx=(0, 5)
        )

        entry.insert(0, value)
        entries.append(entry)

        def delete_entry():
            entry.destroy()
            row.destroy()
            entries.remove(entry)

        tk.Button(
            row,
            text="삭제",
            command=delete_entry
        ).pack(side="right")

        return entry

    for question in user_questions[lang]:
        add_entry(question)

    def add_new_entry():
        entry = add_entry()
        entry.focus_set()

    tk.Button(
        win,
        text="＋ 질문 추가",
        command=add_new_entry,
        width=16
    ).pack(pady=5)

    def save_questions():
        user_questions[lang] = [
            entry.get().strip()
            for entry in entries
            if entry.winfo_exists() and entry.get().strip()
        ]

        messagebox.showinfo(
            "저장 완료",
            "질문을 저장했습니다.",
            parent=win
        )

        win.destroy()

    tk.Button(
        win,
        text="저장",
        command=save_questions,
        width=18,
        height=2
    ).pack(pady=(3, 12))


# =========================================================
# 10. 언어 및 화면 제어
# =========================================================

def set_lang(lang):
    global selected_lang

    selected_lang = lang
    lang_label.config(text=f"언어: {lang.upper()}")


def lock_controls(lock):
    state = "disabled" if lock else "normal"

    start_btn.config(state=state)
    manage_btn.config(state=state)

    for button in lang_buttons:
        button.config(state=state)


# =========================================================
# 11. 프로그램 종료
# =========================================================

def close_app():
    global app_closing, session_id

    app_closing = True
    session_id += 1

    stop_timer()
    stop_audio()

    try:
        pygame.mixer.quit()
    except pygame.error:
        pass

    root.destroy()


# =========================================================
# 12. GUI 구성
# =========================================================

root = tk.Tk()
root.title("면접 시뮬레이터 v5.0")
root.geometry("600x520")
root.protocol("WM_DELETE_WINDOW", close_app)

lang_frame = tk.Frame(root)
lang_frame.pack(pady=8)

lang_buttons = []

for text, code in [
    ("한국어", "ko"),
    ("日本語", "ja"),
    ("English", "en")
]:
    button = tk.Button(
        lang_frame,
        text=text,
        width=12,
        command=lambda c=code: set_lang(c)
    )

    button.grid(
        row=0,
        column=len(lang_buttons),
        padx=5
    )

    lang_buttons.append(button)


lang_label = tk.Label(
    root,
    text="언어: KO",
    font=("Meiryo", 11)
)
lang_label.pack(pady=3)


manage_btn = tk.Button(
    root,
    text="질문 관리",
    width=24,
    height=2,
    command=open_manager
)
manage_btn.pack(pady=8)


start_btn = tk.Button(
    root,
    text="모의 면접 시작",
    width=24,
    height=2,
    command=start_interview
)
start_btn.pack(pady=5)


question_label = tk.Label(
    root,
    text="대기 중",
    wraplength=540,
    justify="center",
    font=("Meiryo", 14),
    height=4
)
question_label.pack(pady=18, fill="x", padx=15)


timer_label = tk.Label(
    root,
    text="00:00",
    font=("Arial", 28)
)
timer_label.pack(pady=5)


btn_frame = tk.Frame(root)
btn_frame.pack(pady=22)


next_btn = tk.Button(
    btn_frame,
    text="다음 질문",
    width=16,
    height=2,
    state="disabled",
    command=ask_next
)
next_btn.grid(row=0, column=0, padx=12)


exit_btn = tk.Button(
    btn_frame,
    text="종료",
    width=16,
    height=2,
    command=end_interview
)
exit_btn.grid(row=0, column=1, padx=12)


# 음성 생성 결과를 GUI 스레드에서 계속 확인
root.after(100, poll_tts_results)

root.mainloop()
