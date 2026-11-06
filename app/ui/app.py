"""Streamlit 前端：知识问答 + 文档管理。

只做一件事：调 FastAPI 接口。
启动：
    终端1: python -m uvicorn app.main:app --reload
    终端2: streamlit run app/ui/app.py
"""
from __future__ import annotations

import html
import os
import re
import uuid

import httpx
import markdown as md
import streamlit as st

API = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")
TIMEOUT = 180.0
EXAMPLES = (
    ("迟到一次扣多少钱？", "考勤"),
    ("年假没休完可以顺延吗？", "假期"),
    ("出差住宿标准是多少？", "报销"),
)

st.set_page_config(
    page_title="私有知识库问答",
    page_icon=":material/menu_book:",
    layout="wide",
)

ss = st.session_state


# ---------------------------------------------------------------- 状态

def new_session() -> dict:
    sid = uuid.uuid4().hex[:8]
    session = {"id": sid, "title": "新对话", "messages": []}
    ss.sessions.insert(0, session)
    ss.current = sid
    return session


ss.setdefault("sessions", [])
ss.setdefault("current", None)
ss.setdefault("collapsed", False)
ss.setdefault("dark", False)
ss.setdefault("pending_q", None)
ss.setdefault("regen_q", None)
ss.setdefault("type_msg", None)
ss.setdefault("just_expanded", False)
ss.setdefault("confirm_delete", None)
ss.setdefault("seen_msgs", set())


def current_session() -> dict:
    for session in ss.sessions:
        if session["id"] == ss.current:
            return session
    return new_session()


session = current_session()
messages = session["messages"]

# ---------------------------------------------------------------- 设计令牌

LIGHT = """
  --bg: #FAF7F4;
  --bg-2: #F4EFE9;
  --ink: #4A4442;
  --ink-2: #8C8481;
  --ink-3: #B3ABA6;
  --blue: #94B8E8;
  --blue-soft: #E4EEF9;
  --blue-deep: #6E93C8;
  --peach: #F2C9C0;
  --peach-soft: #FBEDE9;
  --ai-bubble: #F4EFEB;
  --user-bubble: #94B8E8;
  --user-text: #FFFFFF;
  --glass: rgba(255, 255, 255, 0.55);
  --glass-strong: rgba(255, 255, 255, 0.72);
  --glass-border: rgba(255, 255, 255, 0.6);
  --line: rgba(74, 68, 66, 0.10);
  --line-2: rgba(74, 68, 66, 0.06);
  --shadow: 0 10px 30px rgba(120, 100, 88, 0.08);
  --shadow-strong: 0 16px 40px rgba(120, 100, 88, 0.14);
  --shadow-blue: 0 10px 26px rgba(148, 184, 232, 0.30);
  --caret: #6E93C8;
"""

DARK = """
  --bg: #1B1917;
  --bg-2: #242120;
  --ink: #EDE7E1;
  --ink-2: #A79D96;
  --ink-3: #7C736D;
  --blue: #86A9DA;
  --blue-soft: #2A3444;
  --blue-deep: #6E93C8;
  --peach: #E3B4A9;
  --peach-soft: #3A2E2A;
  --ai-bubble: #2A2624;
  --user-bubble: #6E93C8;
  --user-text: #FFFFFF;
  --glass: rgba(255, 255, 255, 0.06);
  --glass-strong: rgba(255, 255, 255, 0.10);
  --glass-border: rgba(255, 255, 255, 0.12);
  --line: rgba(255, 255, 255, 0.12);
  --line-2: rgba(255, 255, 255, 0.07);
  --shadow: 0 10px 30px rgba(0, 0, 0, 0.30);
  --shadow-strong: 0 16px 40px rgba(0, 0, 0, 0.42);
  --shadow-blue: 0 10px 26px rgba(0, 0, 0, 0.35);
  --caret: #9DBBE6;
"""

RAIL_OPEN = 300
RAIL_SHUT = 100

CSS = """
<style>
:root {
__VARS__
  --rail: __RAIL__px;
  --sans: "Noto Sans SC", "PingFang SC", "Microsoft YaHei", "Segoe UI", sans-serif;
  --mono: "Cascadia Mono", "Consolas", ui-monospace, monospace;
  --ease: cubic-bezier(0.22, 0.61, 0.36, 1);
}

html, body, [data-testid="stAppViewContainer"], [data-testid="stMain"] {
  background: var(--bg);
  color: var(--ink);
  font-family: var(--sans);
}
[data-testid="stAppViewContainer"] {
  background-color: var(--bg);
  background-image:
    radial-gradient(46rem 32rem at 10% 6%, rgba(148, 184, 232, .20), transparent 62%),
    radial-gradient(40rem 28rem at 92% 78%, rgba(242, 201, 192, .26), transparent 64%),
    radial-gradient(32rem 26rem at 58% 10%, rgba(242, 201, 192, .12), transparent 70%);
  background-attachment: fixed;
  background-repeat: no-repeat;
}
[data-theme="dark"] [data-testid="stAppViewContainer"] {
  background-image:
    radial-gradient(46rem 32rem at 10% 6%, rgba(110, 147, 200, .22), transparent 62%),
    radial-gradient(40rem 28rem at 92% 78%, rgba(150, 100, 86, .18), transparent 64%);
}
[data-testid="stHeader"] { background: transparent; }
[data-testid="stToolbar"], [data-testid="stAppDeployButton"], [data-testid="stStatusWidget"] { display: none; }
[data-testid="stSidebar"] { display: none; }

[data-testid="stMainBlockContainer"], .block-container {
  max-width: none;
  padding: 18px 34px 170px var(--rail);
  transition: padding-left .55s var(--ease);
}
.st-key-shell { max-width: 900px; margin: 0 auto; }

::selection { background: var(--blue-soft); color: var(--ink); }
a { color: var(--blue-deep); text-underline-offset: 3px; }
:focus-visible { outline: 2px solid var(--blue); outline-offset: 3px; border-radius: 6px; }
* { scrollbar-width: thin; scrollbar-color: rgba(148, 184, 232, .38) transparent; }
::-webkit-scrollbar { width: 8px; height: 8px; }
::-webkit-scrollbar-thumb { background: rgba(148, 184, 232, .34); border-radius: 999px; }
::-webkit-scrollbar-thumb:hover { background: rgba(148, 184, 232, .55); }
::-webkit-scrollbar-track { background: transparent; }

/* ------------------------------------------------------------ 侧边栏
   控制中心式玻璃：低不透明度基底 + 高模糊高饱和 + 顶部反光 + 蓝粉橙细彩边 + 多层柔光 */
.st-key-sidebar {
  position: fixed; left: 20px; top: 18px; bottom: 18px; width: 260px; z-index: 500;
  padding: 16px 14px 96px;
  background:
    linear-gradient(180deg,
      rgba(255, 255, 255, .62) 0%,
      rgba(255, 255, 255, .18) 22%,
      rgba(255, 255, 255, .02) 46%,
      rgba(255, 255, 255, .10) 100%),
    radial-gradient(120% 70% at 88% 100%, rgba(242, 201, 192, .26), transparent 62%),
    radial-gradient(100% 60% at 0% 0%, rgba(148, 184, 232, .13), transparent 52%),
    rgba(255, 255, 255, .26);
  backdrop-filter: blur(26px) saturate(185%);
  -webkit-backdrop-filter: blur(26px) saturate(185%);
  border: 0;
  border-radius: 24px;
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, .70),
    inset 0 -1px 0 rgba(255, 255, 255, .28),
    0 24px 48px -22px rgba(96, 82, 74, .26),
    0 10px 22px -14px rgba(148, 184, 232, .30),
    0 2px 6px rgba(96, 82, 74, .05);
  overflow: hidden;
  transition: width .55s var(--ease), background .55s var(--ease), box-shadow .6s var(--ease),
              backdrop-filter .6s var(--ease), padding .55s var(--ease);
}
/* 细彩边：蓝 → 粉 → 橙，SVG 1px 描边，叠在玻璃之上 */
.glass-ring {
  position: fixed; left: 20px; top: 18px; width: 260px; height: calc(100vh - 36px);
  z-index: 501; pointer-events: none; overflow: visible;
  opacity: .66; transition: opacity .6s var(--ease), width .55s var(--ease);
}
.glass-ring rect {
  x: .5px; y: .5px; width: calc(100% - 1px); height: calc(100% - 1px);
  rx: 23.5px; ry: 23.5px; fill: none; stroke: url(#kbRing); stroke-width: 1;
}
body:has(.st-key-sidebar:hover) .glass-ring { opacity: .95; }
[data-rail="closed"] .glass-ring { width: 60px; }
[data-theme="dark"] .glass-ring { opacity: .34; }
[data-theme="dark"] body:has(.st-key-sidebar:hover) .glass-ring { opacity: .6; }
/* 顶部反光：一层很淡的白，落在玻璃上沿 */
.st-key-sidebar::after {
  content: ""; position: absolute; left: 0; right: 0; top: 0; height: 132px;
  border-radius: 24px 24px 40% 40% / 24px 24px 22% 22%;
  background:
    radial-gradient(120% 90% at 18% 0%, rgba(255, 255, 255, .55), rgba(255, 255, 255, 0) 62%),
    linear-gradient(180deg, rgba(255, 255, 255, .30), rgba(255, 255, 255, 0));
  pointer-events: none; z-index: 0;
  transition: opacity .6s var(--ease);
}
.st-key-sidebar > * { position: relative; z-index: 1; }
.st-key-sidebar:hover {
  background:
    linear-gradient(180deg,
      rgba(255, 255, 255, .72) 0%,
      rgba(255, 255, 255, .24) 24%,
      rgba(255, 255, 255, .04) 48%,
      rgba(255, 255, 255, .12) 100%),
    radial-gradient(120% 70% at 88% 100%, rgba(242, 201, 192, .32), transparent 62%),
    radial-gradient(100% 60% at 0% 0%, rgba(148, 184, 232, .17), transparent 52%),
    rgba(255, 255, 255, .34);
  backdrop-filter: blur(34px) saturate(210%);
  -webkit-backdrop-filter: blur(34px) saturate(210%);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, .82),
    inset 0 -1px 0 rgba(255, 255, 255, .34),
    0 30px 58px -22px rgba(96, 82, 74, .30),
    0 14px 30px -14px rgba(148, 184, 232, .38),
    0 3px 8px rgba(96, 82, 74, .06);
}
.st-key-sidebar:hover::after { opacity: 1; }
[data-theme="dark"] .st-key-sidebar {
  background:
    linear-gradient(180deg, rgba(255, 255, 255, .12) 0%, rgba(255, 255, 255, .02) 40%, rgba(255, 255, 255, .04) 100%),
    rgba(255, 255, 255, .05);
  backdrop-filter: blur(26px) saturate(160%);
  -webkit-backdrop-filter: blur(26px) saturate(160%);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, .14),
    0 24px 48px -22px rgba(0, 0, 0, .55),
    0 2px 6px rgba(0, 0, 0, .25);
}
[data-theme="dark"] .st-key-sidebar::before { opacity: .30; }
[data-theme="dark"] .st-key-sidebar::after { opacity: .35; }
[data-theme="dark"] .st-key-sidebar:hover { backdrop-filter: blur(34px) saturate(175%); }
.st-key-sidebar > div { gap: .4rem; }
.st-key-sidebar [data-testid="stElementContainer"]:has(.side-foot) {
  position: absolute; left: 14px; right: 14px; bottom: 60px;
}
.st-key-sidebar .st-key-theme_toggle {
  position: absolute; left: 14px; right: 14px; bottom: 14px;
}

.brand { display: flex; align-items: center; gap: 9px; padding: 4px 6px 10px; }
.brand-mark {
  width: 30px; height: 30px; border-radius: 10px; flex: none;
  background: linear-gradient(140deg, var(--blue) 0%, var(--peach) 130%);
  color: #FFFFFF; font-size: 13px; font-weight: 600;
  display: grid; place-items: center; letter-spacing: .02em;
}
.brand-text { font-size: 14.5px; font-weight: 600; color: var(--ink); letter-spacing: .01em; white-space: nowrap; }
.brand-text span { color: var(--ink-2); font-weight: 400; font-size: 12px; display: block; margin-top: 1px; }

.side-label {
  font-size: 11px; color: var(--ink-2); letter-spacing: .12em;
  padding: 14px 8px 4px; white-space: nowrap;
}
.side-foot {
  margin-top: auto; padding-top: 10px; border-top: 1px solid var(--line-2);
  font-size: 10.5px; color: var(--ink-3); line-height: 1.6; white-space: nowrap;
}
.st-key-sidebar [data-testid="stElementContainer"]:has(.side-foot) { margin-top: auto; }

.st-key-sidebar [data-testid="stButton"] { margin: 0; }
.st-key-sidebar [data-testid="stButton"] button {
  justify-content: flex-start; text-align: left; width: 100%;
  border: 0; background: transparent; color: var(--ink);
  border-radius: 12px; padding: 9px 10px; min-height: 40px;
  font-size: 13px; font-weight: 400; box-shadow: none;
  transition: transform .45s var(--ease), background .45s var(--ease), color .45s var(--ease);
}
.st-key-sidebar [data-testid="stButton"] button p {
  margin: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.st-key-sidebar [data-testid="stButton"] button:hover {
  background: var(--blue-soft); color: var(--ink); transform: translateX(3px);
}
.st-key-sidebar [data-testid="stButton"] button:active { transform: translateX(3px) scale(.99); }

.st-key-sidebar [data-testid="stButton"] button > div { width: 100%; justify-content: flex-start; }
.st-key-sidebar [data-testid="stButton"] button p { text-align: left; }

.st-key-new_chat [data-testid="stButton"] button {
  background: rgba(148, 184, 232, .16); color: var(--ink); font-weight: 500;
  border: 1px solid rgba(148, 184, 232, .28);
}
.st-key-new_chat [data-testid="stButton"] button:hover { background: rgba(148, 184, 232, .26); }

.st-key-rail [data-testid="stButton"] button {
  justify-content: center; padding: 8px; min-height: 34px; border-radius: 10px;
}
.st-key-rail [data-testid="stButton"] button p,
.st-key-clear_chat [data-testid="stButton"] button p { display: none; }
.st-key-clear_chat [data-testid="stButton"] button { padding: 8px; min-height: 34px; }

/* 选中会话：雾霾蓝底 + 左侧指示条 */
[class*="st-key-sessionsel-"] [data-testid="stButton"] button {
  background: rgba(148, 184, 232, .34); font-weight: 500; position: relative;
}
[class*="st-key-sessionsel-"] [data-testid="stButton"] button::before {
  content: ""; position: absolute; left: 4px; top: 50%; transform: translateY(-50%);
  width: 3px; height: 18px; border-radius: 999px; background: var(--blue-deep);
}

/* 折叠态 */
[data-rail="closed"] .st-key-sidebar { width: 60px; padding: 14px 9px; }
[data-rail="closed"] .st-key-sidebar .brand-text,
[data-rail="closed"] .st-key-sidebar .side-label,
[data-rail="closed"] .st-key-sidebar .side-foot { opacity: 0; pointer-events: none; }
[data-rail="closed"] .st-key-sidebar .brand { justify-content: center; padding: 2px 0 8px; }
[data-rail="closed"] .st-key-sidebar [data-testid="stButton"] button { justify-content: center; padding: 8px; }
[data-rail="closed"] .st-key-sidebar [data-testid="stButton"] button p { display: none; }
[data-rail="closed"] .st-key-sidebar [data-testid="stButton"] button::before { display: none; }

.st-key-sidebar > div > div { animation: sideIn .55s var(--ease) both; }
.st-key-sidebar > div > div:nth-child(1) { animation-delay: .02s; }
.st-key-sidebar > div > div:nth-child(2) { animation-delay: .07s; }
.st-key-sidebar > div > div:nth-child(3) { animation-delay: .12s; }
.st-key-sidebar > div > div:nth-child(4) { animation-delay: .17s; }
.st-key-sidebar > div > div:nth-child(5) { animation-delay: .22s; }
.st-key-sidebar > div > div:nth-child(6) { animation-delay: .27s; }
.st-key-sidebar > div > div:nth-child(n+7) { animation-delay: .32s; }

/* ------------------------------------------------------------ 顶部导航 */
.st-key-topnav {
  position: sticky; top: 0; z-index: 40;
  margin: 0 0 6px; padding: 16px 22px;
  background: rgba(250, 247, 244, .58);
  backdrop-filter: blur(10px) saturate(135%);
  -webkit-backdrop-filter: blur(10px) saturate(135%);
  border: 1px solid rgba(255, 255, 255, .55); border-radius: 20px;
  box-shadow: 0 6px 20px rgba(120, 100, 88, .05);
  transition: backdrop-filter .55s var(--ease), background .55s var(--ease),
              box-shadow .55s var(--ease), border-color .55s var(--ease);
}
.st-key-topnav.scrolled {
  background: rgba(250, 247, 244, .82);
  backdrop-filter: blur(18px) saturate(150%);
  -webkit-backdrop-filter: blur(18px) saturate(150%);
  border-color: var(--glass-border);
  box-shadow: var(--shadow);
}
[data-theme="dark"] .st-key-topnav { background: rgba(27, 25, 23, .62); }
[data-theme="dark"] .st-key-topnav.scrolled { background: rgba(27, 25, 23, .86); }

.tn-title { font-size: 25px; font-weight: 600; color: var(--ink); margin: 0 0 6px; letter-spacing: .01em; }
.tn-lede { font-size: 12.5px; color: var(--ink-2); margin: 0; line-height: 1.75; }
.tn-status { display: flex; gap: 16px; justify-content: flex-end; font-size: 11.5px; color: var(--ink-2); white-space: nowrap; }
.tn-status b { color: var(--ink); font-weight: 500; font-family: var(--mono); font-size: 11px; }
.tn-status .dot { display: inline-block; width: 5px; height: 5px; border-radius: 50%; background: #7FB79A; margin-right: 6px; vertical-align: 2px; }
.tn-status .dot.off { background: #D08B80; }

/* ------------------------------------------------------------ 页签 */
[data-testid="stTabs"] { max-width: 900px; margin: 0 auto; }
[data-testid="stTabs"] [role="tablist"] {
  gap: 24px; border-bottom: 1px solid var(--line); padding: 0; margin-top: 4px;
}
[data-testid="stTab"] {
  padding: 13px 0 11px; background: transparent; color: var(--ink-2);
  font-size: 13.5px; letter-spacing: .02em; transition: color .4s var(--ease);
}
[data-testid="stTab"] p { margin: 0; }
[data-testid="stTab"][aria-selected="true"] { color: var(--ink); }
[data-testid="stTab"]:hover { color: var(--ink); }
[data-testid="stTabs"] [role="tablist"] [data-selected] [class*="SelectionIndicator"],
[data-testid="stTabs"] [role="tablist"] [class*="SelectionIndicator"] {
  bottom: 0; height: 2px; border-radius: 999px; background: var(--blue-deep);
}

/* ------------------------------------------------------------ 消息 */
.chat { display: flex; flex-direction: column; gap: 18px; padding: 22px 2px 8px; }
.msg { display: flex; gap: 12px; align-items: flex-start; }
.msg.user { justify-content: flex-end; }
.msg .avatar {
  width: 30px; height: 30px; border-radius: 10px; flex: none;
  display: grid; place-items: center; margin-top: 2px;
  background: linear-gradient(140deg, var(--blue) 0%, var(--peach) 135%);
  color: #FFF; font-size: 11px; font-weight: 600; letter-spacing: .02em;
}
.bubble {
  max-width: 76%; padding: 14px 18px; border-radius: 16px;
  font-size: 14.5px; line-height: 1.85; color: var(--ink);
  box-shadow: 0 1px 2px rgba(120, 100, 88, .04);
}
.msg.user .bubble {
  background: var(--user-bubble); color: var(--user-text);
  border-bottom-right-radius: 6px; font-size: 14.5px;
}
.msg.ai .bubble { background: var(--ai-bubble); border-bottom-left-radius: 6px; }
.msg.enter .bubble, .msg.enter .avatar { animation: msgIn .55s var(--ease) both; }
.msg.no-enter .bubble, .msg.no-enter .avatar { animation: none !important; }

.prose p { margin: 0 0 .55em; }
.prose p:last-child { margin-bottom: 0; }
.prose strong { font-weight: 600; }
.prose ul, .prose ol { margin: .3em 0 .7em; padding-left: 1.35em; }
.prose li { margin: .12em 0; }
.prose li::marker { color: var(--blue-deep); }
.prose h1, .prose h2, .prose h3 { font-size: 15px; margin: .7em 0 .35em; }
.prose code {
  font-family: var(--mono); font-size: .86em; background: rgba(148, 184, 232, .16);
  padding: 1px 5px; border-radius: 5px;
}
.prose pre {
  background: var(--glass-strong); border: 1px solid var(--line);
  padding: 12px 14px; border-radius: 12px; overflow-x: auto;
}
.prose sup.ref {
  font-family: var(--mono); font-size: .62em; line-height: 0; color: var(--blue-deep);
  vertical-align: super; padding-left: 1px; font-weight: 600;
}
.type-caret {
  display: inline-block; width: 2px; height: 1em; margin-left: 2px;
  background: var(--caret); border-radius: 2px; vertical-align: -2px;
  animation: caret 1.05s ease-in-out infinite;
}

/* 出处折叠 */
.sources { margin-top: 12px; padding-top: 10px; border-top: 1px solid var(--line-2); }
.sources input { position: absolute; opacity: 0; pointer-events: none; }
.sources label {
  display: inline-flex; align-items: center; gap: 8px; cursor: pointer;
  font-size: 11.5px; color: var(--ink-2); letter-spacing: .04em;
  padding: 3px 0; transition: color .4s var(--ease);
}
.sources label:hover { color: var(--blue-deep); }
.sources label::after {
  content: ""; width: 5px; height: 5px; border-right: 1.5px solid currentColor;
  border-bottom: 1.5px solid currentColor; transform: rotate(45deg) translateY(-1px);
  transition: transform .45s var(--ease);
}
.sources input:checked ~ label::after { transform: rotate(225deg) translateY(-1px); }
.sources-body {
  display: grid; grid-template-rows: 0fr;
  transition: grid-template-rows .5s var(--ease), opacity .5s var(--ease);
  opacity: 0;
}
.sources input:checked ~ .sources-body { grid-template-rows: 1fr; opacity: 1; }
.sources-body > div { overflow: hidden; }
.sources ol { list-style: none; margin: 8px 0 0; padding: 0; display: flex; flex-direction: column; gap: 6px; }
.sources li { display: flex; gap: 8px; align-items: baseline; font-size: 12.5px; color: var(--ink-2); }
.sources .n { font-family: var(--mono); font-size: 10.5px; color: var(--blue-deep); }
.sources .doc { color: var(--ink); }
.sources .pg { font-family: var(--mono); font-size: 10.5px; color: var(--ink-3); }
.msg-meta { margin: 0; font-family: var(--mono); font-size: 10.5px; color: var(--ink-3); white-space: nowrap; }
.msg-foot { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-top: 10px; min-height: 22px; }

.actions { display: flex; gap: 4px; margin: 0; opacity: 0; transition: opacity .45s var(--ease); }
.msg:hover .actions, .actions:focus-within { opacity: 1; }
.actions button {
  border: 0; background: transparent; color: var(--ink-2); cursor: pointer;
  font-family: var(--sans); font-size: 11.5px; padding: 4px 8px; border-radius: 8px;
  transition: background .4s var(--ease), color .4s var(--ease);
}
.actions button:hover { background: rgba(148, 184, 232, .18); color: var(--ink); }

/* 思考中 */
.thinking { display: inline-flex; gap: 7px; align-items: center; padding: 4px 2px; }
.thinking i {
  width: 7px; height: 7px; border-radius: 50%; display: block;
  background: var(--blue); opacity: .35;
  animation: breathe 1.9s var(--ease) infinite;
}
.thinking i:nth-child(2) { background: var(--peach); animation-delay: .28s; }
.thinking i:nth-child(3) { background: var(--blue-deep); animation-delay: .56s; }

/* ------------------------------------------------------------ 空状态 */
.st-key-empty { padding-top: 26px; }
.empty-hello { font-size: 19px; font-weight: 600; color: var(--ink); margin: 0 0 6px; }
.empty-sub { font-size: 12.5px; color: var(--ink-2); margin: 0 0 20px; }
.st-key-quick { margin: 0 0 4px; }
.st-key-quick [data-testid="stButton"] { margin: 0; }
.st-key-quick [data-testid="stButton"] button {
  display: block; width: 100%; height: auto; min-height: 92px; text-align: left;
  padding: 16px; border-radius: 18px; border: 1px solid var(--glass-border);
  background: var(--glass); backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px); box-shadow: var(--shadow);
  color: var(--ink); font-size: 13.5px; line-height: 1.6; font-weight: 400;
  transition: transform .5s var(--ease), box-shadow .5s var(--ease),
              background .5s var(--ease), border-color .5s var(--ease);
}
.st-key-quick [data-testid="stButton"] button:hover {
  transform: translateY(-3px); background: var(--glass-strong);
  box-shadow: var(--shadow-strong); border-color: rgba(148, 184, 232, .5);
}
.st-key-quick [data-testid="stButton"] button:active { transform: translateY(-1px) scale(.995); }
.st-key-quick [data-testid="stButton"] button p { margin: 0; line-height: 1.6; }
.st-key-quick [data-testid="stColumn"]:nth-child(1) button p::before { content: "考勤制度"; }
.st-key-quick [data-testid="stColumn"]:nth-child(2) button p::before { content: "假期政策"; }
.st-key-quick [data-testid="stColumn"]:nth-child(3) button p::before { content: "差旅报销"; }
.st-key-quick [data-testid="stButton"] button p::before {
  display: block; font-size: 10.5px; color: var(--blue-deep);
  letter-spacing: .1em; margin-bottom: 8px; font-weight: 500;
}

/* ------------------------------------------------------------ 文档 */
.section-title { font-size: 15.5px; font-weight: 600; color: var(--ink); margin: 26px 0 4px; }
.section-hint { font-size: 12px; color: var(--ink-2); margin: 0 0 12px; }
[data-testid="stFileUploaderDropzone"] {
  border: 1px dashed rgba(148, 184, 232, .55); border-radius: 18px;
  background: var(--glass); backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px); padding: 14px 16px;
  display: flex; align-items: center; gap: 14px;
  transition: border-color .5s var(--ease), background .5s var(--ease);
}
[data-testid="stFileUploaderDropzone"]:hover { border-color: var(--blue); background: var(--glass-strong); }
[data-testid="stFileUploaderDropzone"] [data-testid="stBaseButton-secondary"] {
  border: 1px solid rgba(148, 184, 232, .45); background: rgba(255, 255, 255, .7);
  border-radius: 12px; min-height: 32px; padding: 5px 12px; color: var(--ink); box-shadow: none;
}
[data-testid="stFileUploaderDropzone"] [data-testid="stBaseButton-secondary"] p { display: none; }
[data-testid="stFileUploaderDropzone"] [data-testid="stBaseButton-secondary"]::after {
  content: "选择文件"; font-family: var(--sans); font-size: 12.5px;
}
[data-testid="stFileUploaderDropzoneInstructions"] span { font-size: 0; }
[data-testid="stFileUploaderDropzoneInstructions"] span::after {
  content: "把文件拖到这里，或点击左侧选择（PDF / Word / Markdown / TXT）";
  font-size: 12px; color: var(--ink-2); font-family: var(--sans);
}

.st-key-doclist [data-testid="stHorizontalBlock"] {
  border-bottom: 1px solid var(--line-2); padding: 9px 0; gap: 12px;
  transition: background .4s var(--ease);
}
.st-key-doclist [data-testid="stHorizontalBlock"]:hover { background: rgba(148, 184, 232, .07); }
.doc-row { display: flex; align-items: baseline; gap: 14px; min-width: 0; }
.doc-name { font-size: 13.5px; color: var(--ink); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.doc-meta { font-family: var(--mono); font-size: 10.5px; color: var(--ink-3); white-space: nowrap; }
.confirm {
  margin: 4px 0 12px; padding: 12px 16px; border-radius: 14px;
  background: var(--peach-soft); border: 1px solid rgba(242, 201, 192, .7);
  font-size: 13px; color: var(--ink);
}

/* ------------------------------------------------------------ 控件 */
[data-testid="stButton"] button {
  border-radius: 12px; font-family: var(--sans); font-size: 13px; font-weight: 500;
  border: 1px solid var(--line); background: rgba(255, 255, 255, .7); color: var(--ink);
  box-shadow: none; padding: 7px 14px; min-height: 36px;
  transition: background .4s var(--ease), border-color .4s var(--ease),
              transform .4s var(--ease), box-shadow .4s var(--ease);
}
[data-testid="stButton"] button:hover { border-color: rgba(148, 184, 232, .6); background: #FFF; }
[data-theme="dark"] [data-testid="stButton"] button { background: rgba(255,255,255,.06); }
[data-testid="stButton"] [data-testid="stBaseButton-primary"] {
  background: var(--blue); border-color: var(--blue); color: #FFF;
  box-shadow: 0 6px 16px rgba(148, 184, 232, .35);
}
[data-testid="stButton"] [data-testid="stBaseButton-primary"]:hover {
  background: var(--blue-deep); border-color: var(--blue-deep); color: #FFF;
  box-shadow: var(--shadow-blue);
}
[data-testid="stButton"] button:active { transform: scale(.985); }
[data-testid="stButton"] [data-testid="stBaseButton-tertiary"] {
  border: 0; background: transparent; padding: 5px 8px; min-height: 30px;
  font-size: 12px; color: var(--ink-2); justify-content: flex-end;
}
[data-testid="stButton"] [data-testid="stBaseButton-tertiary"]:hover { color: var(--blue-deep); background: transparent; }

[data-testid="stAlert"] { border-radius: 16px; }
[data-testid="stAlertContainer"] { border-radius: 16px; font-size: 13px; padding: 12px 16px; backdrop-filter: blur(8px); }
[data-testid="stAlertContainer"] p { margin: 0; }

.st-key-regen [data-testid="stButton"] button { justify-content: flex-end; font-size: 11.5px; color: var(--ink-2); }
.st-key-regen [data-testid="stButton"] button svg { transition: transform .55s var(--ease); }
.st-key-regen [data-testid="stButton"] button:hover svg { transform: rotate(120deg); }

/* 底部输入 */
[data-testid="stBottom"] { background: transparent; border: 0; padding-left: var(--rail); }
[data-testid="stBottomBlockContainer"] {
  max-width: 100%; padding: 0 34px 16px 0;
  transition: padding-left .55s var(--ease);
}
[data-testid="stBottom"] .stChatInput { max-width: 900px; margin: 0 auto; }
[data-testid="stChatInput"] {
  background: var(--glass); backdrop-filter: blur(14px) saturate(140%);
  -webkit-backdrop-filter: blur(14px) saturate(140%);
  border: 1px solid var(--glass-border); border-radius: 22px;
  box-shadow: var(--shadow); padding: 7px 8px 7px 10px;
  transition: box-shadow .5s var(--ease), border-color .5s var(--ease),
              transform .5s var(--ease), background .5s var(--ease);
}
[data-testid="stChatInput"]:focus-within {
  border-color: rgba(148, 184, 232, .75);
  box-shadow: 0 14px 34px rgba(148, 184, 232, .28);
  transform: translateY(-2px); background: var(--glass-strong);
}
[data-testid="stChatInput"] > div {
  background: rgba(255, 255, 255, .92); border: 0; border-radius: 16px; padding: 4px 10px;
}
[data-theme="dark"] [data-testid="stChatInput"] > div { background: rgba(255, 255, 255, .08); }
[data-theme="dark"] [data-testid="stBottom"] > div { background: transparent !important; }
[data-testid="stChatInputTextArea"] {
  font-family: var(--sans); font-size: 14px; color: var(--ink); padding: 9px 2px;
  background: transparent; line-height: 1.6;
}
[data-testid="stChatInputTextArea"]::placeholder { color: var(--ink-3); }
[data-testid="stChatInputSubmitButton"] {
  width: 34px; height: 34px; border-radius: 12px; border: 0;
  background: var(--blue); color: #FFF;
  transition: background .4s var(--ease), box-shadow .4s var(--ease), transform .35s var(--ease);
}
[data-testid="stChatInputSubmitButton"]:hover:not(:disabled) {
  background: var(--blue-deep); box-shadow: 0 8px 18px rgba(148, 184, 232, .45);
}
[data-testid="stChatInputSubmitButton"]:active:not(:disabled) { transform: scale(.92); }
[data-testid="stChatInputSubmitButton"]:disabled { background: var(--line); color: var(--bg); }

/* Toast */
.kb-toast {
  position: fixed; left: 50%; bottom: 120px; transform: translate(-50%, 12px);
  z-index: 9999; padding: 10px 18px; border-radius: 14px;
  background: var(--glass-strong); backdrop-filter: blur(14px);
  -webkit-backdrop-filter: blur(14px); border: 1px solid var(--glass-border);
  box-shadow: var(--shadow-strong); color: var(--ink); font-size: 12.5px;
  opacity: 0; transition: opacity .45s var(--ease), transform .45s var(--ease);
  pointer-events: none;
}
.kb-toast.show { opacity: 1; transform: translate(-50%, 0); }

[data-testid="stVerticalBlock"] { gap: .5rem; }
[data-testid="stMarkdownContainer"] p { line-height: 1.7; }

@keyframes msgIn {
  from { opacity: 0; transform: translateY(12px); }
  to { opacity: 1; transform: none; }
}
@keyframes sideIn {
  from { opacity: 0; transform: translateX(-8px); }
  to { opacity: 1; transform: none; }
}
@keyframes breathe {
  0%, 100% { opacity: .3; transform: scale(.9); }
  50% { opacity: 1; transform: scale(1); }
}
@keyframes caret {
  0%, 100% { opacity: 1; }
  50% { opacity: .12; }
}

@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation-duration: .01ms !important; transition-duration: .01ms !important; }
}

@media (max-width: 900px) {
  :root { --rail: 84px; }
  [data-testid="stAppViewContainer"] { overflow-x: hidden; }
  .st-key-topnav [data-testid="stHorizontalBlock"] { flex-wrap: wrap; gap: 8px; }
  .st-key-topnav [data-testid="stColumn"] { flex: 1 1 100% !important; width: 100% !important; min-width: 0 !important; }
  .tn-status { justify-content: flex-start; flex-wrap: wrap; white-space: normal; row-gap: 4px; }
  [data-testid="stBottom"] .stChatInput { max-width: 100%; }
  [data-testid="stChatInputTextArea"] { font-size: 13.5px; }
  .bubble { max-width: 92%; font-size: 14px; }
  [data-testid="stFileUploaderDropzoneInstructions"] span::after { content: "拖到此处，或点击左侧选择"; }
  .st-key-topnav [data-testid="stColumn"]:last-child { text-align: right; }
  .st-key-sidebar { width: 60px; padding: 14px 9px; }
  .glass-ring { width: 60px; }
  .st-key-sidebar .brand-text, .st-key-sidebar .side-label, .st-key-sidebar .side-foot { display: none; }
  .st-key-sidebar [data-testid="stButton"] button p { display: none; }
  .st-key-sidebar [data-testid="stButton"] button { justify-content: center; padding: 8px; }
  [data-testid="stMainBlockContainer"], .block-container { padding: 12px 18px 150px var(--rail); }
  [data-testid="stBottomBlockContainer"] { padding: 0 18px 12px var(--rail); }
  .st-key-topnav { padding: 12px 14px; }
  .tn-title { font-size: 19px; }
  .tn-status { gap: 10px; font-size: 10.5px; }
  .bubble { max-width: 88%; }
  .st-key-quick [data-testid="stButton"] button { min-height: 72px; }
}
</style>
""".replace("__VARS__", DARK if ss.dark else LIGHT).replace("__RAIL__", str(RAIL_SHUT if ss.collapsed else RAIL_OPEN))

st.markdown(CSS, unsafe_allow_html=True)

# 主题标记 + 轻量脚本（打字机 / 复制 / Toast / 顶栏滚动态）
st.html(
    f"<div id='kb-theme' data-theme='{'dark' if ss.dark else 'light'}' "
    f"data-rail='{'closed' if ss.collapsed else 'open'}' style='display:none'></div>"
    """
<script>
(function () {
  var W = window;
  W.__kb = W.__kb || { seen: new Set(), typed: new Set() };
  var S = W.__kb;

  function toast(text) {
    var old = document.querySelector('.kb-toast');
    if (old) old.remove();
    var el = document.createElement('div');
    el.className = 'kb-toast';
    el.textContent = text;
    document.body.appendChild(el);
    requestAnimationFrame(function () { el.classList.add('show'); });
    setTimeout(function () {
      el.classList.remove('show');
      setTimeout(function () { el.remove(); }, 500);
    }, 1900);
  }
  W.__kbToast = toast;

  function typingAllowed() {
    return !window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  }

  function typeEl(el) {
    var msg = el.closest('.msg');
    var id = msg ? msg.dataset.msgId : null;
    if (id && S.typed.has(id)) return;
    if (el.dataset.typed === '1') return;
    if (!typingAllowed()) { el.dataset.typed = '1'; if (id) S.typed.add(id); return; }

    var walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT, null);
    var nodes = [], n;
    while ((n = walker.nextNode())) { if (n.nodeValue && n.nodeValue.trim()) nodes.push(n); }
    if (!nodes.length) { el.dataset.typed = '1'; return; }

    var full = nodes.map(function (x) { return x.nodeValue; });
    nodes.forEach(function (x) { x.nodeValue = ''; });
    var total = full.reduce(function (a, t) { return a + t.length; }, 0);
    var perTick = Math.max(1, Math.round(total / 110));

    var cursor = document.createElement('span');
    cursor.className = 'type-caret';
    nodes[0].parentNode.insertBefore(cursor, nodes[0].nextSibling);

    var ti = 0, ci = 0;
    var timer = setInterval(function () {
      var budget = perTick;
      while (budget > 0 && ti < nodes.length) {
        var t = full[ti], remain = t.length - ci;
        var take = Math.min(budget, remain);
        nodes[ti].nodeValue = t.slice(0, ci + take);
        ci += take; budget -= take;
        if (ci >= t.length) {
          ti += 1; ci = 0;
          if (ti < nodes.length) {
            nodes[ti].parentNode.insertBefore(cursor, nodes[ti].nextSibling);
          }
        }
      }
      if (ti >= nodes.length) {
        clearInterval(timer);
        cursor.remove();
        el.dataset.typed = '1';
        if (id) S.typed.add(id);
      }
    }, 24);
  }

  function ensureRing() {
    if (document.querySelector('.glass-ring')) return;
    var NS = 'http://www.w3.org/2000/svg';
    var svg = document.createElementNS(NS, 'svg');
    svg.setAttribute('class', 'glass-ring');
    svg.setAttribute('aria-hidden', 'true');
    var defs = document.createElementNS(NS, 'defs');
    var grad = document.createElementNS(NS, 'linearGradient');
    grad.setAttribute('id', 'kbRing');
    grad.setAttribute('x1', '0%'); grad.setAttribute('y1', '0%');
    grad.setAttribute('x2', '100%'); grad.setAttribute('y2', '100%');
    [['0%', '#94B8E8'], ['38%', '#C9C6EC'], ['68%', '#F2C9C0'], ['100%', '#F6D8B8']]
      .forEach(function (pair) {
        var stop = document.createElementNS(NS, 'stop');
        stop.setAttribute('offset', pair[0]);
        stop.setAttribute('stop-color', pair[1]);
        grad.appendChild(stop);
      });
    defs.appendChild(grad);
    var rect = document.createElementNS(NS, 'rect');
    rect.setAttribute('x', '0.5'); rect.setAttribute('y', '0.5');
    rect.setAttribute('width', '100%'); rect.setAttribute('height', '100%');
    rect.setAttribute('rx', '23.5'); rect.setAttribute('ry', '23.5');
    rect.setAttribute('fill', 'none');
    rect.setAttribute('stroke', 'url(#kbRing)');
    rect.setAttribute('stroke-width', '1');
    svg.appendChild(defs); svg.appendChild(rect);
    document.body.appendChild(svg);
  }

  function scan() {
    var root = document.getElementById('kb-theme');
    if (root) {
      document.documentElement.setAttribute('data-theme', root.dataset.theme);
      document.documentElement.setAttribute('data-rail', root.dataset.rail);
    }

    document.querySelectorAll('.msg[data-msg-id]').forEach(function (msg) {
      var id = msg.dataset.msgId;
      if (S.seen.has(id)) {
        msg.classList.add('no-enter');
        msg.classList.remove('enter');
      } else {
        S.seen.add(id);
      }
    });
    document.querySelectorAll('[data-typewriter="1"]').forEach(typeEl);
  }

  document.addEventListener('click', function (e) {
    var copyBtn = e.target.closest('[data-copy]');
    if (copyBtn) {
      var msg = copyBtn.closest('.msg');
      var body = msg ? msg.querySelector('.bubble-text') : null;
      var text = body ? body.innerText.trim() : '';
      var fallback = function () {
        var ta = document.createElement('textarea');
        ta.value = text;
        ta.style.position = 'fixed'; ta.style.left = '-9999px'; ta.style.opacity = '0';
        document.body.appendChild(ta);
        ta.select();
        var ok = false;
        try { ok = document.execCommand('copy'); } catch (err) { ok = false; }
        ta.remove();
        toast(ok ? '已复制到剪贴板' : '复制失败，请手动选择');
      };
      if (navigator.clipboard && text) {
        navigator.clipboard.writeText(text).then(function () { toast('已复制到剪贴板'); }, fallback);
      } else {
        fallback();
      }
      return;
    }
    var fbBtn = e.target.closest('[data-feedback]');
    if (fbBtn) {
      toast(fbBtn.dataset.feedback === 'up' ? '谢谢，已记录这条回答有帮助' : '谢谢，已记录，我们会继续改进');
      return;
    }
    var regen = e.target.closest('[data-regen-toast]');
    if (regen) { toast('正在重新生成'); }
  });

  function bindScroll() {
    var nav = document.querySelector('.st-key-topnav');
    if (!nav) return;
    var scroller = nav.parentElement;
    while (scroller && scroller !== document.body) {
      var style = getComputedStyle(scroller);
      if (/(auto|scroll)/.test(style.overflowY) && scroller.scrollHeight > scroller.clientHeight) break;
      scroller = scroller.parentElement;
    }
    if (!scroller || scroller === document.body) scroller = window;
    var onScroll = function () {
      var top = (scroller === window) ? window.scrollY : scroller.scrollTop;
      nav.classList.toggle('scrolled', top > 6);
    };
    scroller.addEventListener('scroll', onScroll, { passive: true });
    onScroll();
  }

  scan();
  ensureRing();
  setTimeout(function () { scan(); ensureRing(); bindScroll(); }, 400);
  if (!W.__kbObserver) {
    W.__kbObserver = new MutationObserver(function () { scan(); });
    W.__kbObserver.observe(document.body, { childList: true, subtree: true });
  }
})();
</script>
""",
    unsafe_allow_javascript=True,
)


# ---------------------------------------------------------------- HTTP 封装


def api_get(path: str):
    return httpx.get(f"{API}{path}", timeout=TIMEOUT)


def api_post(path: str, json: dict | None = None, files: dict | None = None):
    return httpx.post(f"{API}{path}", json=json, files=files, timeout=TIMEOUT)


def api_delete(path: str):
    return httpx.delete(f"{API}{path}", timeout=TIMEOUT)


def fetch_health() -> dict | None:
    try:
        resp = api_get("/health")
        return resp.json() if resp.status_code == 200 else None
    except httpx.HTTPError:
        return None


def fetch_documents() -> list[dict]:
    try:
        resp = api_get("/api/documents")
        return resp.json() if resp.status_code == 200 else []
    except httpx.HTTPError:
        return []


def queue_question() -> None:
    """输入框回调：把问题挂起，交给下一次 rerun 渲染。"""
    text = (ss.get("ask_box") or "").strip()
    if text:
        ss.pending_q = text


# ---------------------------------------------------------------- 渲染零件

CITE_RE = re.compile(r"[ \t]*\[(\d{1,2})\]")


def fmt(n) -> str:
    try:
        return f"{int(n):,}"
    except (TypeError, ValueError):
        return str(n)


def render_markdown(text: str) -> str:
    safe = html.escape(text, quote=False)
    body = md.markdown(safe, extensions=["extra", "sane_lists"], output_format="html5")
    return CITE_RE.sub(lambda m: f'<sup class="ref">{m.group(1)}</sup>', body)


def sources_html(citations: list[dict], uid: str) -> str:
    if not citations:
        return ""
    items = "".join(
        f'<li><span class="n">{c["index"]}</span>'
        f'<span class="doc">{html.escape(str(c["doc_name"]))}</span>'
        f'<span class="pg">第 {fmt(c["page_no"])} 页</span></li>'
        for c in citations
    )
    return (
        f'<div class="sources"><input type="checkbox" id="src-{uid}">'
        f'<label for="src-{uid}">出处 · {len(citations)} 条</label>'
        f'<div class="sources-body"><div><ol>{items}</ol></div></div></div>'
    )


def actions_html() -> str:
    return (
        '<div class="actions">'
        '<button type="button" data-copy="1">复制</button>'
        '<button type="button" data-feedback="up">有帮助</button>'
        '<button type="button" data-feedback="down">待改进</button>'
        "</div>"
    )


def message_html(msg: dict, enter: bool = True, typewriter: bool = False) -> str:
    mid = msg["id"]
    cls = "msg enter" if enter else "msg no-enter"
    if msg["role"] == "user":
        return (
            f'<div class="{cls} user" data-msg-id="{mid}">'
            f'<div class="bubble">{html.escape(msg["content"])}</div></div>'
        )
    tw = ' data-typewriter="1"' if typewriter else ""
    meta = f'<p class="msg-meta">耗时 {int(msg["elapsed_ms"])} ms</p>' if msg.get("elapsed_ms") else "<span></span>"
    return (
        f'<div class="{cls} ai" data-msg-id="{mid}">'
        f'<div class="avatar">AI</div>'
        f'<div class="bubble">'
        f'<div class="bubble-text prose"{tw}>{render_markdown(msg["content"])}</div>'
        f'{sources_html(msg.get("citations") or [], mid)}'
        f'<div class="msg-foot">{meta}{actions_html()}</div>'
        "</div></div>"
    )


def thinking_html() -> str:
    return (
        '<div class="msg ai"><div class="avatar">AI</div>'
        '<div class="bubble"><span class="thinking"><i></i><i></i><i></i></span></div></div>'
    )


def status_html() -> str:
    if health:
        return (
            '<div class="tn-status"><span><i class="dot"></i>服务正常</span>'
            f"<span>库内 <b>{fmt(chunks)}</b> 块</span>"
            f"<span>模型 <b>{html.escape(str(health.get('llm_model', '—')))}</b></span></div>"
        )
    return (
        '<div class="tn-status"><span><i class="dot off"></i>未连接</span>'
        "<span>库内 <b>—</b></span><span>模型 <b>—</b></span></div>"
    )


# ---------------------------------------------------------------- 数据

health = fetch_health()
documents = fetch_documents() if health else []
chunks = health.get("chunks", 0) if health else 0

# ---------------------------------------------------------------- 侧边栏

with st.container(key="sidebar"):
    head_left, head_right = st.columns([5, 1], vertical_alignment="center")
    with head_left:
        st.html(
            '<div class="brand"><div class="brand-mark">KB</div>'
            '<div class="brand-text">知识库问答<span>Knowledge Base</span></div></div>'
        )
    with head_right:
        with st.container(key="rail"):
            if st.button(
                "展开侧栏" if ss.collapsed else "收起侧栏",
                icon=":material/chevron_right:" if ss.collapsed else ":material/chevron_left:",
                help="展开侧栏" if ss.collapsed else "收起侧栏",
                key="toggle_rail",
            ):
                ss.collapsed = not ss.collapsed
                st.rerun()

    if st.button("新建对话", icon=":material/add:", key="new_chat", width="stretch"):
        new_session()
        ss.pending_q = None
        ss.regen_q = None
        st.rerun()

    if not ss.collapsed:
        st.html('<div class="side-label">最近会话</div>')
    for item in ss.sessions[:8]:
        selected = item["id"] == ss.current
        label = item["title"]
        with st.container(key=f"sessionsel-{item['id']}" if selected else f"session-{item['id']}"):
            if st.button(
                label,
                icon=":material/chat_bubble:",
                key=f"goto-{item['id']}",
                width="stretch",
                help=label,
            ):
                ss.current = item["id"]
                st.rerun()

    st.html('<div class="side-foot">阶段 1 · 本地向量库<br>答案只取自库内资料</div>')
    if st.button(
        "深色模式" if not ss.dark else "浅色模式",
        icon=":material/dark_mode:" if not ss.dark else ":material/light_mode:",
        key="theme_toggle",
        width="stretch",
    ):
        ss.dark = not ss.dark
        st.rerun()

# 细彩边叠加层由下方脚本注入（st.html 会过滤 SVG 标签）

# ---------------------------------------------------------------- 主区

with st.container(key="shell"):
    with st.container(key="topnav"):
        col_title, col_status, col_clear = st.columns([5.6, 3.6, 0.8], vertical_alignment="center")
        with col_title:
            st.html(
                '<h1 class="tn-title">私有知识库问答</h1>'
                '<p class="tn-lede">把制度、手册、规范放进库里，用一句话问出来；每条结论都能翻回原文那一页。</p>'
            )
        with col_status:
            st.html(status_html())
        with col_clear:
            if st.button(
                "清空对话",
                icon=":material/restart_alt:",
                help="清空当前会话",
                key="clear_chat",
                type="tertiary",
            ):
                session["messages"] = []
                ss.type_msg = None
                st.rerun()

# ---------------------------------------------------------------- 页签

tab_ask, tab_docs = st.tabs(["问答", "文档"], key="nav", on_change="rerun", default="问答")
active = ss.get("nav") or "问答"

with tab_ask:
    pending = ss.pending_q

    if not messages and not pending and not ss.regen_q:
        with st.container(key="empty"):
            st.html(
                '<p class="empty-hello">今天想查点什么？</p>'
                f'<p class="empty-sub">库内 {fmt(chunks)} 块内容、{fmt(len(documents))} 份文档，'
                "下面的问题可以直接点。</p>"
            )
            with st.container(key="quick"):
                cols = st.columns(len(EXAMPLES), gap="small")
                for idx, (question, _tag) in enumerate(EXAMPLES):
                    with cols[idx]:
                        if st.button(question, key=f"quick-{idx}", width="stretch"):
                            ss["ask_box"] = question
                            st.rerun()

    if messages:
        parts = []
        for msg in messages:
            fresh = msg["id"] not in ss.seen_msgs
            parts.append(message_html(msg, enter=fresh, typewriter=(msg["id"] == ss.type_msg)))
            ss.seen_msgs.add(msg["id"])
        st.html('<div class="chat">' + "".join(parts) + "</div>")
        ss.type_msg = None
        last_user = next(
            (m["content"] for m in reversed(messages) if m["role"] == "user"), None
        )
        if last_user:
            with st.container(key="regen"):
                if st.button("重新生成", icon=":material/refresh:", key="regen_btn", type="tertiary"):
                    if messages and messages[-1]["role"] == "assistant":
                        ss.seen_msgs.discard(messages.pop()["id"])
                    ss.regen_q = last_user
                    ss.type_msg = None
                    st.rerun()

    ask_text = None
    if pending:
        ss.pending_q = None
        user_msg = {"id": uuid.uuid4().hex[:8], "role": "user", "content": pending}
        messages.append(user_msg)
        if session["title"] == "新对话":
            session["title"] = pending[:16]

        ss.seen_msgs.add(user_msg["id"])
        st.html('<div class="chat">' + message_html(user_msg, enter=True) + "</div>")
        ask_text = pending
    elif ss.regen_q:
        ask_text = ss.regen_q
        ss.regen_q = None

    if ask_text:
        slot = st.empty()
        slot.html('<div class="chat">' + thinking_html() + "</div>")

        try:
            resp = api_post("/api/ask", json={"question": ask_text})
        except httpx.HTTPError as exc:
            slot.empty()
            st.error(f"请求失败：{exc}", title="没能拿到回答")
            resp = None

        if resp is not None and resp.status_code == 200:
            data = resp.json()
            answer = {
                "id": uuid.uuid4().hex[:8],
                "role": "assistant",
                "content": data["answer"],
                "citations": data["citations"],
                "elapsed_ms": data.get("elapsed_ms"),
            }
            messages.append(answer)
            ss.seen_msgs.add(answer["id"])
            slot.html('<div class="chat">' + message_html(answer, enter=True, typewriter=True) + "</div>")
        elif resp is not None:
            slot.empty()
            st.error(f"接口返回 {resp.status_code}：{resp.text}", title="没能拿到回答")

if active == "问答":
    st.chat_input(
        "问一句，回车发送" if health else "后端未连接，先启动接口服务",
        key="ask_box",
        on_submit=queue_question,
        disabled=not health,
    )

with tab_docs:
    st.html(
        '<p class="section-title">上传文档</p>'
        '<p class="section-hint">PDF / Word(.docx) / Markdown / TXT，单个文件最大 50 MB。</p>'
    )
    uploaded = st.file_uploader(
        "选择文件",
        type=["pdf", "docx", "md", "markdown", "txt"],
        label_visibility="collapsed",
        disabled=not health,
    )

    if uploaded is not None:
        if st.button("上传并入库", type="primary", width="stretch"):
            with st.spinner("解析、分块、向量化入库"):
                files = {
                    "file": (
                        uploaded.name,
                        uploaded.getvalue(),
                        uploaded.type or "application/octet-stream",
                    )
                }
                try:
                    resp = api_post("/api/documents", files=files)
                except httpx.HTTPError as exc:
                    st.error(f"请求失败：{exc}", title="没能上传")
                    resp = None

            if resp is not None and resp.status_code == 200:
                data = resp.json()
                st.success(f"已入库：{data['doc_name']}，共 {fmt(data['chunks'])} 块")
                st.rerun()
            elif resp is not None:
                st.error(f"入库失败（{resp.status_code}）：{resp.text}", title="没能上传")

    st.html(
        '<p class="section-title">已有文档</p>'
        f'<p class="section-hint">共 {fmt(len(documents))} 份，删除会移除该文档的全部内容块。</p>'
    )

    if ss.confirm_delete:
        st.html(
            f'<div class="confirm">确认删除 <b>{html.escape(ss.confirm_delete)}</b>？'
            "该文档的全部内容块会一起移除。</div>"
        )
        c_ok, c_cancel, _ = st.columns([2, 2, 6])
        if c_ok.button("确认删除", key="del-ok", type="primary"):
            api_delete(f"/api/documents/{ss.confirm_delete}")
            ss.confirm_delete = None
            st.rerun()
        if c_cancel.button("取消", key="del-cancel"):
            ss.confirm_delete = None
            st.rerun()

    if not health:
        st.html('<p class="section-hint">连上后端后才能看到文档列表。</p>')
    elif not documents:
        st.html('<p class="section-hint">知识库还是空的，先上传一份文档。</p>')
    else:
        with st.container(key="doclist"):
            for i, doc in enumerate(documents):
                name = doc["doc_name"]
                c_name, c_act = st.columns([8, 2], vertical_alignment="center")
                c_name.markdown(
                    f'<div class="doc-row"><span class="doc-name" title="{html.escape(name)}">'
                    f"{html.escape(name)}</span>"
                    f'<span class="doc-meta">{fmt(doc["chunks"])} 块 / {fmt(doc["pages"])} 页</span></div>',
                    unsafe_allow_html=True,
                )
                if c_act.button("删除", key=f"del-{i}", type="tertiary", width="stretch"):
                    ss.confirm_delete = name
                    st.rerun()
