#!/usr/bin/env python3
"""Validate BeeAgent skill outputs against Coze-aligned structure rules.

Usage:
  python3 local/scripts/validate_skill_output_structure.py \\
    --skill koujing-xiezhuan --file /path/to/output.md

  # Validate the known chat dump:
  python3 local/scripts/validate_skill_output_structure.py --from-session 5515e4fc-1188-4ad5-bee6-978221526cf0
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNTIME_CHATS = Path.home() / ".qwenpaw/hub/runtimes"


def _h2s(text: str) -> list[str]:
    return [
        re.sub(r"^#+\s*", "", ln).strip()
        for ln in text.splitlines()
        if re.match(r"^##\s+", ln)
    ]


def _has_table_with_headers(text: str, required: list[str]) -> bool:
    for block in re.finditer(r"(^\|.+\|\s*$\n(?:^\|.+\|\s*$\n?)+)", text, re.M):
        header = block.group(0).splitlines()[0]
        if all(h in header for h in required):
            return True
    return False


def _count_table_data_rows(section: str, required_headers: list[str]) -> int:
    for block in re.finditer(r"(^\|.+\|\s*$\n(?:^\|.+\|\s*$\n?)+)", section, re.M):
        lines = [ln for ln in block.group(0).splitlines() if ln.startswith("|")]
        if not lines:
            continue
        header = lines[0]
        if not all(h in header for h in required_headers):
            continue
        data = [
            ln
            for ln in lines[1:]
            if not re.match(r"^\|\s*[-:| ]+\|\s*$", ln)
        ]
        return len(data)
    return 0


def _section_after(text: str, title: str, next_titles: list[str]) -> str:
    m = re.search(rf"^##\s+{re.escape(title)}\s*$", text, re.M)
    if not m:
        return ""
    start = m.end()
    end = len(text)
    for nxt in next_titles:
        n = re.search(rf"^##\s+{re.escape(nxt)}\s*$", text[start:], re.M)
        if n:
            end = start + n.start()
            break
    return text[start:end]


def validate_koujing(text: str) -> list[str]:
    errs: list[str] = []
    if not re.search(r"^#\s*《.+口径》", text.lstrip(), re.M):
        errs.append("标题须为「《[事件名称]口径》」")
    required = [
        "一、基本信息",
        "二、事件特征与历史经验",
        "三、事件分级与启动条件",
        "四、应急组织与分工",
        "五、具体处置步骤",
        "六、处置策略与方法",
        "七、沟通对象与措施",
        "八、本场景特殊注意事项",
        "九、口径资源",
        "十、演练与维护",
    ]
    h2 = _h2s(text)
    for title in required:
        if not any(title in h for h in h2):
            errs.append(f"缺少模块：{title}")
    extras = [
        h
        for h in h2
        if not any(req in h for req in required)
        and not h.startswith(("2.", "3.", "4.", "6.", "8.", "10."))
    ]
    # allow only exact required H2s (subsections should be ###)
    for h in h2:
        if any(req == h or h.startswith(req) for req in required):
            continue
        if re.match(r"^\d+\.\d+", h):
            continue
        errs.append(f"不允许的额外二级标题：{h}")
    for mark in ["2.1", "2.2", "2.3", "3.1", "3.2", "4.1", "4.2", "4.3", "6.1", "6.2", "6.3", "8.1", "8.2", "8.3"]:
        if mark not in text:
            errs.append(f"缺少小节标记：{mark}")
    sec5 = _section_after(text, "五、具体处置步骤", required[required.index("五、具体处置步骤") + 1 :])
    n5 = _count_table_data_rows(sec5, ["时限", "具体动作", "责任方", "注意事项"])
    if n5 < 7:
        errs.append(f"第五模块处置步骤表数据行不足7（实际 {n5}）")
    sec7 = _section_after(text, "七、沟通对象与措施", required[required.index("七、沟通对象与措施") + 1 :])
    n7 = _count_table_data_rows(sec7, ["沟通目的"])
    if n7 < 1:
        errs.append("第七模块缺少沟通对象表格")
    if "银保监会" in text:
        errs.append("禁止使用已废止称谓「银保监会」")
    return errs


def validate_yuqing(text: str) -> list[str]:
    errs: list[str] = []
    required = [
        "1. 舆情摘要",
        "2. 媒体背景分析",
        "3. 内容分析",
        "4. 传播分析",
        "5. 风险研判",
        "6. 应对建议",
    ]
    for title in required:
        if title not in text:
            errs.append(f"缺少模块：{title}")
    if not re.search(r"【高】|【中】|【低】|高风险|中风险|低风险", text):
        errs.append("风险研判缺少明确定级")
    return errs


def validate_shiqian(text: str) -> list[str]:
    errs: list[str] = []
    if not re.search(r"《.+事前评估报告》", text):
        errs.append("标题须含「《…事前评估报告》」")
    for title in [
        "一、事项基本情况",
        "二、全面评估分析",
        "三、风险识别与定级",
        "四、风险缓释与优化措施",
        "五、评估结论与建议",
    ]:
        if title not in text:
            errs.append(f"缺少模块：{title}")
    return errs


def validate_paicha(text: str) -> list[str]:
    errs: list[str] = []
    if not re.search(r"《.+排查方案》", text):
        errs.append("标题须含「《…排查方案》」")
    for title in [
        "一、排查对象与范围",
        "二、重点排查内容",
        "三、排查方法与工具",
        "四、上报要求",
    ]:
        if title not in text:
            errs.append(f"缺少模块：{title}")
    return errs


def validate_yuan(text: str) -> list[str]:
    errs: list[str] = []
    if not re.search(r"《.+专项应急预案》", text):
        errs.append("标题须为「《[事件名称]专项应急预案》」")
    for title in [
        "一、基本信息",
        "二、事件特征与历史经验",
        "三、事件分级与启动条件",
        "四、应急组织与分工",
        "五、具体处置步骤",
        "六、处置策略与方法",
        "七、沟通对象与措施",
        "八、本场景特殊注意事项",
        "九、资源与支撑",
        "十、演练与维护",
    ]:
        if title not in text:
            errs.append(f"缺少模块：{title}")
    return errs


def validate_wangping(text: str) -> list[str]:
    errs: list[str] = []
    t = text.strip()
    if t.startswith("无法生成："):
        return []
    if re.search(r"^##?\s+", t, re.M) and "角色" in t[:200]:
        errs.append("正常输出不应含解释性标题/概述，仅话术列表")
    if not re.search(r"^-\s*\[.+\]\s*-\s*\[.+\]", t, re.M):
        errs.append("话术须为「- [角色] - [跟评目的]」列表格式")
    banned = ["理亏", "去投诉", "去仲裁", "追责"]
    for b in banned:
        if b in t:
            errs.append(f"护行约束疑似违反：出现「{b}」")
    return errs


def validate_weike(text: str) -> list[str]:
    errs: list[str] = []
    if not re.search(r"^#\s+.+" , text.lstrip(), re.M):
        errs.append("缺少微课标题（一级标题）")
    if len(text.strip()) < 400:
        errs.append("正文过短，不像完整微课文案")
    return errs


def validate_yanlian(text: str) -> list[str]:
    errs: list[str] = []
    if not re.search(r"《.+演练脚本》", text):
        errs.append("标题须含「《…演练脚本》」")
    if "角色" not in text:
        errs.append("缺少角色表/角色说明")
    if not re.search(r"第\s*\d+\s*场|场次|场景", text):
        errs.append("缺少场次/场景正文")
    return errs


def validate_shensu(text: str) -> list[str]:
    errs: list[str] = []
    if "撤稿" not in text and "申诉" not in text and "函" not in text[:80]:
        errs.append("输出应是申诉/撤稿函正文")
    if "具有法律效力" not in text and "保证以上内容真实有效" not in text:
        errs.append("缺少结尾法定声明句式")
    return errs


VALIDATORS = {
    "koujing-xiezhuan": validate_koujing,
    "yuqing-yanpan": validate_yuqing,
    "shiqian-pinggu": validate_shiqian,
    "paicha-fangan": validate_paicha,
    "yuan-xiezhuan": validate_yuan,
    "wangping-huashu": validate_wangping,
    "weike-wenan": validate_weike,
    "yanlian-jiaoben": validate_yanlian,
    "shensu-chegao": validate_shensu,
}


def load_session_assistant(chat_id: str) -> tuple[str, str]:
    """Return (skill_guess, assistant_text) from local runtime session files."""
    for chats_path in RUNTIME_CHATS.glob("*/working/workspaces/*/chats.json"):
        data = json.loads(chats_path.read_text(encoding="utf-8"))
        chats = data.get("chats") if isinstance(data, dict) else data
        target = None
        for c in chats or []:
            if str(c.get("id")) == chat_id:
                target = c
                break
        if not target:
            continue
        session_id = target.get("session_id")
        name = target.get("name") or ""
        sess_dir = chats_path.parent / "sessions"
        matches = list(sess_dir.rglob(f"*{session_id}*.json"))
        if not matches:
            raise SystemExit(f"session file not found for {session_id}")
        sess = json.loads(matches[0].read_text(encoding="utf-8"))

        def find_msgs(o):
            if isinstance(o, list) and o and isinstance(o[0], dict) and (
                "role" in o[0] or "content" in o[0]
            ):
                return o
            if isinstance(o, dict):
                for v in o.values():
                    r = find_msgs(v)
                    if r is not None:
                        return r
            if isinstance(o, list):
                for v in o[:50]:
                    r = find_msgs(v)
                    if r is not None:
                        return r
            return None

        msgs = find_msgs(sess) or []
        last = ""
        skill = ""
        for m in msgs:
            role = m.get("role")
            content = m.get("content")
            text = ""
            if isinstance(content, str):
                text = content
            elif isinstance(content, list):
                parts = []
                for b in content:
                    if isinstance(b, dict) and (b.get("type") == "text" or "text" in b):
                        parts.append(str(b.get("text") or ""))
                text = "\n".join(parts)
            if role == "user" and not skill:
                mskill = re.search(r"/([a-z0-9_-]+)", text)
                if mskill:
                    skill = mskill.group(1)
            if role == "assistant" and text.strip():
                # strip injected skill block remnants if any
                last = re.sub(r"<skill>[\s\S]*?</skill>", "", text).strip()
        if "口径" in name and not skill:
            skill = "koujing-xiezhuan"
        return skill, last
    raise SystemExit(f"chat id not found: {chat_id}")


def _self_test() -> int:
    """Minimal golden snippets to lock validator rules (not full-length samples)."""
    samples = {
        "koujing-xiezhuan": """# 《示例事件口径》

## 一、基本信息
x
## 二、事件特征与历史经验
### 2.1 典型表现
### 2.2 过往经验教训
### 2.3 本口径应对思路
## 三、事件分级与启动条件
### 3.1 分级标准
### 3.2 启动条件
1
2
3
4
5
## 四、应急组织与分工
### 4.1 应急小组组成
### 4.2 各角色职责
### 4.3 与业务口径的分工
## 五、具体处置步骤
| 序号 | 时限 | 具体动作 | 责任方 | 注意事项 |
|------|------|----------|--------|----------|
| 1 | 15分钟 | a | 公关 | 取证 |
| 2 | 30分钟 | b | 公关 | 取证 |
| 3 | 1小时 | c | 公关 | 取证 |
| 4 | 2小时 | d | 公关 | 取证 |
| 5 | 4小时 | e | 公关 | 取证 |
| 6 | 12小时 | f | 公关 | 取证 |
| 7 | 24小时 | g | 公关 | 取证 |
## 六、处置策略与方法
### 6.1 受众应对策略
### 6.2 媒体/舆论引导策略
### 6.3 内部协同策略
## 七、沟通对象与措施
| 沟通对象 | 沟通目的 | 沟通要点 | 渠道/方式 | 负责角色 |
|----------|----------|----------|-----------|----------|
| 客户 | 安抚 | 说明进展 | 电话 | 客服 |
## 八、本场景特殊注意事项
### 8.1 必须守住的底线
### 8.2 最容易犯的错
### 8.3 应对技巧
## 九、口径资源
卡
## 十、演练与维护
演练
""",
        "yuqing-yanpan": "## 1. 舆情摘要\nx\n## 2. 媒体背景分析\nx\n## 3. 内容分析\nx\n## 4. 传播分析\nx\n## 5. 风险研判\n风险定级【中】\n## 6. 应对建议\nx\n",
        "shiqian-pinggu": "《网点活动事前评估报告》\n### 一、事项基本情况\n### 二、全面评估分析\n### 三、风险识别与定级\n### 四、风险缓释与优化措施\n### 五、评估结论与建议\n",
        "paicha-fangan": "《某行2026年一季度声誉风险排查方案》\n### 一、排查对象与范围\n### 二、重点排查内容\n### 三、排查方法与工具\n### 四、上报要求\n",
        "yuan-xiezhuan": "《示例专项应急预案》\n## 一、基本信息\n## 二、事件特征与历史经验\n## 三、事件分级与启动条件\n## 四、应急组织与分工\n## 五、具体处置步骤\n## 六、处置策略与方法\n## 七、沟通对象与措施\n## 八、本场景特殊注意事项\n## 九、资源与支撑\n## 十、演练与维护\n",
        "wangping-huashu": "- [官方] - [澄清]\n  先核实情况再讨论。\n\n- [专家] - [正向引导]\n  建议理性看待个案。\n",
        "weike-wenan": "# 如何写好网点活动预告文案\n\n" + ("开场。" + "主体内容。" * 80 + "收尾。"),
        "yanlian-jiaoben": "《网点舆情首响演练脚本》\n应用说明\n角色表：值班员、舆情岗\n第 1 场 开场\n",
        "shensu-chegao": "撤稿申诉函\n致平台运营团队\n本函由本机构授权代表提交，具有法律效力。\n声明：本机构保证以上内容真实有效。\n",
    }
    failed = 0
    for skill, text in samples.items():
        errs = VALIDATORS[skill](text)
        status = "PASS" if not errs else "FAIL"
        print(f"{status} fixture {skill}")
        if errs:
            failed += 1
            for e in errs:
                print(f"  - {e}")
    return 1 if failed else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skill", choices=sorted(VALIDATORS))
    ap.add_argument("--file", type=Path)
    ap.add_argument("--from-session")
    ap.add_argument("--text-stdin", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()

    if args.self_test:
        return _self_test()

    skill = args.skill
    text = ""
    if args.from_session:
        skill, text = load_session_assistant(args.from_session)
        print(f"session skill={skill} chars={len(text)}")
    elif args.file:
        text = args.file.read_text(encoding="utf-8")
    elif args.text_stdin:
        text = sys.stdin.read()
    else:
        ap.error("need --file, --from-session, or --text-stdin")

    if not skill:
        ap.error("--skill required unless inferred from session")
    errs = VALIDATORS[skill](text)
    if errs:
        print(f"FAIL {skill}: {len(errs)} issue(s)")
        for e in errs:
            print(f"  - {e}")
        return 1
    print(f"PASS {skill}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
