import tkinter as tk
from tkinter import messagebox
import random
import time
import threading
import asyncio
import edge_tts
from playsound import playsound
import os
import uuid
from deep_translator import GoogleTranslator

# ---------------- Globals ----------------
user_questions = []
queue = []
timer_running = False
start_time = 0
selected_lang = "ko"

fixed_questions = [
    "자기 소개 먼저 간단하게 들어볼까요?",
    "전직하려는 이유가 뭔가요?"
]

voice_map = {
    "ko": "ko-KR-InJoonNeural",
    "ja": "ja-JP-KeitaNeural",
    "en": "en-US-GuyNeural"
}

# ---------------- Translate ----------------
def translate(text):
    return GoogleTranslator(source='auto', target=selected_lang).translate(text)

# ---------------- TTS ----------------
def speak(text):
    filename = f"{uuid.uuid4()}.mp3"
    voice = voice_map[selected_lang]

    async def run():
        com = edge_tts.Communicate(text, voice)
        await com.save(filename)

    asyncio.run(run())
    playsound(filename)
    os.remove(filename)

# ---------------- Timer ----------------
def start_timer():
    global timer_running, start_time
    timer_running = True
    start_time = time.time()
    update_timer()

def update_timer():
    if timer_running:
        e = int(time.time() - start_time)
        timer_label.config(text=f"{e//60:02d}:{e%60:02d}")
        root.after(500, update_timer)

def stop_timer():
    global timer_running
    timer_running = False

# ---------------- Interview Flow ----------------
def start_interview():
    global queue

    if not user_questions:
        messagebox.showwarning("경고","질문이 없습니다.")
        return

    # 고정 질문 + 랜덤 질문 큐 생성
    queue = fixed_questions + random.sample(user_questions, len(user_questions))

    # 버튼 잠금
    start_btn.config(state="disabled")
    add_btn.config(state="disabled")
    next_btn.config(state="normal")

    for b in lang_buttons:
        b.config(state="disabled")

    ask_next()

def ask_next():
    global queue

    if not queue:
        messagebox.showinfo("끝","모든 질문 완료")
        end_interview()
        return

    stop_timer()
    q = queue.pop(0)
    question_label.config(text=q)

    threading.Thread(target=play_and_timer,args=(q,),daemon=True).start()

def play_and_timer(q):
    translated = translate(q)
    speak(translated)
    start_timer()

def end_interview():
    stop_timer()
    question_label.config(text="면접 종료")

    start_btn.config(state="normal")
    add_btn.config(state="normal")
    next_btn.config(state="disabled")

    for b in lang_buttons:
        b.config(state="normal")

# ---------------- Add Questions ----------------
def open_add_window():
    win = tk.Toplevel(root)
    win.title("질문 추가")

    frame = tk.Frame(win)
    frame.pack(padx=10,pady=10)

    entries=[]

    def add_entry(event=None):
        e=tk.Entry(frame,width=60,font=("Meiryo",11))
        e.pack(pady=3)
        e.bind("<Return>",add_entry)
        entries.append(e)
        e.focus()

    add_entry()

    def save():
        for e in entries:
            t=e.get().strip()
            if t:
                user_questions.append(t)
        win.destroy()

    tk.Button(win,text="확인",command=save).pack(pady=5)

# ---------------- Language ----------------
def set_lang(lang):
    global selected_lang
    selected_lang=lang
    lang_label.config(text=f"언어: {lang.upper()}")

# ---------------- UI ----------------
root=tk.Tk()
root.title("면접 시뮬레이터")
root.geometry("540x470")

lang_frame=tk.Frame(root)
lang_frame.pack(pady=5)

lang_buttons=[]
for i,(txt,code) in enumerate([("한국어","ko"),("日本語","ja"),("English","en")]):
    b=tk.Button(lang_frame,text=txt,width=10,command=lambda c=code:set_lang(c))
    b.grid(row=0,column=i,padx=5)
    lang_buttons.append(b)

lang_label=tk.Label(root,text="언어: KO")
lang_label.pack()

add_btn=tk.Button(root,text="질문 추가",width=24,height=2,command=open_add_window)
add_btn.pack(pady=8)

start_btn=tk.Button(root,text="모의 면접 시작",width=24,height=2,command=start_interview)
start_btn.pack(pady=5)

question_label=tk.Label(root,text="대기 중",wraplength=480,font=("Meiryo",13))
question_label.pack(pady=25)

timer_label=tk.Label(root,text="00:00",font=("Arial",22))
timer_label.pack()

btn_frame=tk.Frame(root)
btn_frame.pack(pady=25)

next_btn=tk.Button(btn_frame,text="다음 질문",width=14,height=2,state="disabled",command=ask_next)
next_btn.grid(row=0,column=0,padx=12)

exit_btn=tk.Button(btn_frame,text="종료",width=14,height=2,command=end_interview)
exit_btn.grid(row=0,column=1,padx=12)

root.mainloop()