"""A2 · S4b 同批件①②③ —— **运行时** prompt 非法 bin 牙 + `pad_vector` 缺口登记 + `renderer_class` 三点读数。

## 为什么必须有这个文件（D 的派工原文，不是 A2 自选题）
`rl_harness_supervision/d_handoff_to_a2_20260930.md` §一「同批必须做的三件」：

1. **运行时 `-1` prompt 牙**（§23.2）：`processor_pi05.py:77` 的**结构不对称** ——
   `x ≥ 1 → bin 255`（合法饱和，优雅退化）、`x < −1 → bin −1`（**非法 token，静默拼进 prompt**）。
   牙必须在**运行时**（不只是离线 stats）证明：任一维出现 `-1` ⇒ 红。
   **判的是「真正拼进 prompt 的文本」**，不是判归一化后的浮点数组 —— 后者只证明"我算了一遍
   `np.digitize`"，不证明"模型这一口吃到的是非法 token"。两者的差就是本文件存在的理由。
2. **`pad_vector`（`processor_pi05.py:72`）的缺口按 `not_measured` 登记**：D 未测过这一维，
   **不得假设安全**（三值纪律：空集 → `null` + 非零退出，不许写 `false`/`0`）。
3. **`renderer_class` 三点读数**（起点 / 运行内 / 终点）：终点若未在运行内测就写 `null` 并标
   `measurement_kind`，**不许拿起点值顶替**。这构成 E 的 C4 复验第三方证据（`params:1412`
   `c4_reverify_piggybacks_no_window`：搭便车、不单开窗口）。

## 三个红线族在本文件里的落点（照裁定 85/88/92/93.5 逐条对上）
* **三值纪律**：`verdict ∈ {"GREEN","RED",null}`；`measurement_status ∈ {"measured","not_measured"}`。
  **空集聚合 ⇒ `verdict=null` + `measurement_status="not_measured"` + `nonzero_exit_required=True`**
  （`aggregate_prompt_audit([])` 就是这个形状）。不许把"一条都没测"写成"0 命中"。
* **`absence_of_measurement_is_not_measurement_of_absence`**：`pad_vector_gap_registration()`
  返回的 `value` 是 `null`、`safe` 是 `null`，**不是** `false`、**不是** `0`。
* **审计器必须自证模式覆盖（裁定 93.5 / 缺陷类 ⑲）**：本文件的识别模式是
  `PROMPT_STATE_RE`（从 prompt 文本里抠出 `State: …;` 段）。它必须先证明自己**抓得到已知形态的坏样本**
  ⇒ `pattern_coverage_probe()` 注入一条已知非法形态的 prompt，抓不到 ⇒ **审计器自己红**，
  产物里落 `pattern_coverage_probe: {injected_bad_form, detected: true}`；缺这颗探针 ⇒ `not_measured`、不得报绿。

## 边界
* **不改** `harness/contracts.py` / `harness/ledger.py` / `harness/norm_contract.py`（C2 的写入面）
  / `lerobot/**`（site-packages 第三方资产）。本文件只**读** `processor_pi05.py` 的行为、
  只**旁路挂钩** `PolicyProcessorPipeline.register_after_step_hook`（`lerobot/processor/pipeline.py:1264`），
  钩子用完 `unregister_after_step_hook` 摘掉，不改管线语义。
* bin 定义与 `harness/norm_contract.py:63`（`N_BINS=256`）、`:93`–`:94`（`SAT_BIN_HIGH=255` /
  `SAT_BIN_LOW=-1`）**同值**；本文件不另立常量口径，只在这里给运行时的**读法**。
* 产物禁用「跑通/学会/达标」；归因只写 `inferred`。
"""
from __future__ import annotations

import hashlib
import os
import pathlib
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Sequence

import numpy as np

MODULE_PATH = pathlib.Path(__file__).resolve()
MODULE_REPRESENTATION_VERSION = "a2-prompt-bin-guard-v1"
CST = timezone(timedelta(hours=8))

# ── bin 口径（与 harness/norm_contract.py:63/:93/:94 同值，不另立）──────────────────────
N_BINS = 256
SAT_BIN_HIGH = N_BINS - 1          # x ≥ 1 ⇒ 255（**合法**饱和）
ILLEGAL_BIN_LOW = -1               # x < −1 ⇒ −1（**非法** token，静默进 prompt）
MAX_STATE_DIM = 32                 # processor_pi05.py:55 / :72

# ── 运行时挂钩点（读自 lerobot 实现，不是猜的）────────────────────────────────────────
PI05_TOKENIZER_STEP_CLASS = "Pi05PrepareStateTokenizerProcessorStep"
PI05_TOKENIZER_STEP_FILE = "lerobot/policies/pi05/processor_pi05.py"
PI05_DIGITIZE_LINE = 77            # np.digitize(state_np, bins=np.linspace(-1,1,257)[:-1]) - 1
PI05_PROMPT_FORMAT_LINES = "81-84"  # f"Task: {cleaned_text}, State: {state_str};\nAction: "
PI05_PAD_VECTOR_LINE = 72          # state = pad_vector(state, self.max_state_dim)
PI05_PAD_VECTOR_DEF = "lerobot/policies/pi05/modeling_pi05.py:133"

# prompt 的形状由 `processor_pi05.py:83` 的 f-string 决定：
#   f"Task: {cleaned_text}, State: {state_str};\nAction: "
# 其中 `state_str = " ".join(map(str, discretized_states[i]))` ⇒ **State: 与 ; 之间是空格分隔的整数**。
PROMPT_STATE_RE = re.compile(r"State:\s*(?P<body>[-0-9\s]*?)\s*;", re.DOTALL)
# 对照探针用的**宽形态**正则（裁定 93.5：审计器必须先证明自己的模式覆盖对象空间的全部形态）：
# 若 f-string 改了分隔符/尾标点，窄正则会静默 0 命中 ⇒ 宽形态负责发现这件事。
PROMPT_STATE_LOOSE_RE = re.compile(r"State:(?P<body>[^;]*);", re.DOTALL)
INT_TOKEN_RE = re.compile(r"-?\d+")
# 第三层：`State:` 标记**在**、但两种带终止符的形态都抠不出来 ⇒ 这是**形状漂移**，
# 不是"没有 state 段"。裁定 93.5 的要求是审计器自己红，而不是把它读成 `not_measured` 蒙混过去
# （本文件的对照探针第 4 形态就是靠这一层抓到的；漏掉它 = 缺陷类 ⑲ 的实例）。
PROMPT_STATE_MARKER_RE = re.compile(r"State\s*:", re.IGNORECASE)


def module_sha256_12() -> str:
    return hashlib.sha256(MODULE_PATH.read_bytes()).hexdigest()[:12]


def now_iso() -> str:
    return datetime.now(CST).isoformat(timespec="seconds")


# ══════════════════════════ ① 运行时 prompt 非法 bin 牙 ══════════════════════════
def digitize_bins(x: Sequence[float] | np.ndarray) -> np.ndarray:
    """**逐字镜像** `processor_pi05.py:77` 的离散化（同一份 bins 表达式）。

    这一份是"离线重算"路径，只用来与运行时读到的 prompt 文本**对账**；
    判定一律以 `audit_prompt_text()`（读真文本）为准 —— 两者的差就是缺陷面。
    """
    arr = np.asarray(x, dtype=np.float64).reshape(-1)
    return np.digitize(arr, bins=np.linspace(-1, 1, N_BINS + 1)[:-1]) - 1


def parse_state_tokens(prompt: str) -> dict[str, Any]:
    """从**真正拼进 prompt 的文本**里抠出 state 整数序列。

    返回里必须带 `parse_path`：`narrow_re` / `loose_re_only` / `no_state_segment`。
    `loose_re_only` = 窄形态没抓到、宽形态抓到了 ⇒ **prompt 形状漂了**，牙自己要先红
    （缺陷类 ⑲：绿是审计模式覆盖不全造成的）。
    """
    out: dict[str, Any] = {"prompt_len": len(prompt), "prompt_head": prompt[:120],
                           "prompt_tail": prompt[-60:], "narrow_matched": False,
                           "loose_matched": False, "state_marker_present": False,
                           "parse_path": "no_state_segment", "tokens": [], "n_tokens": 0}
    m = PROMPT_STATE_RE.search(prompt)
    body: str | None = None
    if m is not None:
        out["narrow_matched"] = True
        body = m.group("body")
        out["parse_path"] = "narrow_re"
    else:
        ml = PROMPT_STATE_LOOSE_RE.search(prompt)
        if ml is not None:
            out["loose_matched"] = True
            body = ml.group("body")
            out["parse_path"] = "loose_re_only"
            out["loose_body_head"] = body[:160]
    if body is None:
        mm = PROMPT_STATE_MARKER_RE.search(prompt)
        if mm is not None:
            out["state_marker_present"] = True
            out["parse_path"] = "state_marker_present_unparsed"
            tail = prompt[mm.start():mm.start() + 200]
            out["unparsed_tail_head"] = tail
            # 形状漂移时仍尽力把整数抠出来（**用于登记**，判定走 RED 分支，不走计数分支）
            out["tokens"] = [int(t) for t in INT_TOKEN_RE.findall(tail)]
            out["n_tokens"] = len(out["tokens"])
        return out
    out["state_marker_present"] = True
    toks = [int(t) for t in INT_TOKEN_RE.findall(body)]
    out["tokens"] = toks
    out["n_tokens"] = len(toks)
    out["state_segment_raw"] = body.strip()[:400]
    return out


def audit_prompt_text(prompt: str) -> dict[str, Any]:
    """**牙本体**：判一条真实 prompt 文本里有没有非法 bin `-1`。

    三值：`verdict="RED"`（检出 `-1`）/ `"GREEN"`（读到 state 段且无 `-1`）/ `null`（**没读到**
    state 段 ⇒ `not_measured`，**不许**当成 GREEN）。
    `illegal_bin_hits` 逐维登记（维度索引 = prompt 里的 token 序，即 `pad_vector` 之后的槽位序）。
    """
    p = parse_state_tokens(prompt)
    toks = p["tokens"]
    res: dict[str, Any] = {
        "artifact": "prompt_bin_audit",
        "audited_object": "the_text_actually_concatenated_into_the_prompt",
        "not_audited_object": "the_normalized_float_array（离线重算不等于运行时事实）",
        "source_of_bin_semantics": f"{PI05_TOKENIZER_STEP_FILE}:{PI05_DIGITIZE_LINE}"
                                   f"（prompt 形状 :{PI05_PROMPT_FORMAT_LINES}）",
        "parse_path": p["parse_path"], "narrow_matched": p["narrow_matched"],
        "loose_matched": p["loose_matched"], "prompt_len": p["prompt_len"],
        "prompt_head": p["prompt_head"], "n_state_tokens": len(toks),
    }
    if p["parse_path"] in ("loose_re_only", "state_marker_present_unparsed"):
        # 形状漂了：窄模式没覆盖 ⇒ 牙自己的模式覆盖不足（裁定 93.5）⇒ 红，不报绿。
        res.update({"verdict": "RED", "measurement_status": "measured",
                    "red_class": "audit_pattern_coverage_drift",
                    "illegal_bin_hits": [], "n_illegal_bin_minus1": 0,
                    "n_state_tokens_best_effort": p["n_tokens"],
                    "state_marker_present": p["state_marker_present"],
                    "why": ("窄形态正则 `PROMPT_STATE_RE` 没抠出带终止符的 state 段"
                            f"（parse_path={p['parse_path']}）⇒ prompt 文本形状与 "
                            "`processor_pi05.py:83` 的 f-string 不再同形；"
                            "按裁定 93.5 这属审计器自身模式覆盖问题 ⇒ 判红，不许报绿、"
                            "也不许读成 `not_measured` 蒙混过去（缺陷类 ⑲ 的实例）")})
        return res
    if p["parse_path"] == "no_state_segment" or not toks:
        res.update({"verdict": None, "measurement_status": "not_measured",
                    "illegal_bin_hits": [], "n_illegal_bin_minus1": None,
                    "why": ("prompt 文本里读不到 `State: …;` 段（或段内 0 个整数）⇒ "
                            "这是**没测到**，不是**测到没有**；三值纪律要求写 null，不许写 GREEN/0")})
        return res
    arr = np.asarray(toks, dtype=np.int64)
    illegal_idx = [int(i) for i in np.flatnonzero(arr == ILLEGAL_BIN_LOW)]
    sat_high_idx = [int(i) for i in np.flatnonzero(arr == SAT_BIN_HIGH)]
    out_of_range = [int(i) for i in np.flatnonzero((arr < ILLEGAL_BIN_LOW) | (arr > SAT_BIN_HIGH))]
    verdict = "RED" if (illegal_idx or out_of_range) else "GREEN"
    res.update({
        "verdict": verdict, "measurement_status": "measured",
        "n_illegal_bin_minus1": len(illegal_idx),
        "illegal_bin_hits": illegal_idx,
        "illegal_bin_dims_first16": illegal_idx[:16],
        "n_saturated_bin_255": len(sat_high_idx),
        "saturated_bin_255_dims": sat_high_idx[:32],
        "n_out_of_legal_range": len(out_of_range),
        "out_of_legal_range_dims": out_of_range[:32],
        "token_min": int(arr.min()), "token_max": int(arr.max()),
        "state_dim_after_pad": len(toks),
        "expected_state_dim_after_pad": MAX_STATE_DIM,
        "pad_dim_matches_max_state_dim": bool(len(toks) == MAX_STATE_DIM),
        "red_class": ("illegal_bin_minus1_in_prompt" if illegal_idx else
                      ("token_outside_legal_bin_range" if out_of_range else None)),
        "saturation_is_legal_note": ("bin 255 是 `x ≥ 1` 的**合法**优雅饱和（`processor_pi05.py:77` 的上侧），"
                                     "**不判红**；只逐维登记，因为 dim6/dim13 顶 bin 饱和是真物理"
                                     "（D 的边界口径：不当 bug 报）"),
        "why": (f"prompt 文本里检出 {len(illegal_idx)} 维非法 bin `-1`"
                f"（维度 {illegal_idx[:16]}）⇒ `x < -1` 的下侧越界被 `np.digitize` 变成"
                f"**非法 token 静默进 prompt**（结构不对称：上侧 255 合法、下侧 -1 非法）"
                if verdict == "RED" else
                f"prompt 文本里 {len(toks)} 维 state token 全部落在合法 bin 区间 [0,{SAT_BIN_HIGH}]"),
    })
    return res


def aggregate_prompt_audit(audits: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """多帧/多局聚合。**空集 ⇒ `verdict=null` + 非零退出要求**（三值纪律，不许写 GREEN/0）。"""
    audits = list(audits)
    if not audits:
        return {"artifact": "prompt_bin_audit_aggregate", "n_audits": 0, "verdict": None,
                "measurement_status": "not_measured", "nonzero_exit_required": True,
                "n_illegal_bin_minus1": None, "illegal_bin_dims_union": [],
                "why": ("聚合输入是空集 ⇒ 没有一条 prompt 被审过。按三值纪律这是 `not_measured`"
                        "（`null` + 非零退出），**不是** `GREEN`、**不是** `0 命中`")}
    measured = [a for a in audits if a.get("measurement_status") == "measured"]
    reds = [a for a in audits if a.get("verdict") == "RED"]
    union: set[int] = set()
    for a in audits:
        union.update(int(i) for i in (a.get("illegal_bin_hits") or []))
    n_illegal = sum(int(a.get("n_illegal_bin_minus1") or 0) for a in audits)
    return {
        "artifact": "prompt_bin_audit_aggregate",
        "n_audits": len(audits), "n_measured": len(measured),
        "n_not_measured": len(audits) - len(measured),
        "verdict": ("RED" if reds else ("GREEN" if measured else None)),
        "measurement_status": ("measured" if measured else "not_measured"),
        "nonzero_exit_required": bool(not measured),
        "n_prompts_red": len(reds),
        "n_illegal_bin_minus1": (n_illegal if measured else None),
        "illegal_bin_dims_union": sorted(union),
        "n_illegal_bin_dims_union": len(union),
        "red_classes": sorted({str(a.get("red_class")) for a in reds if a.get("red_class")}),
        "aggregate_semantics": ("`n_illegal_bin_minus1` 是**逐 prompt 计数之和**（同一维在多帧重复出现会重复计）；"
                                "`illegal_bin_dims_union` 才是**去重后的维度集合**。两者不得互替"),
        "why": (f"{len(reds)}/{len(audits)} 条 prompt 判红；非法 bin 维度并集 {sorted(union)}"
                if reds else
                f"{len(measured)}/{len(audits)} 条 prompt 判绿、0 维出现非法 bin `-1`"
                if measured else "无一条 measured ⇒ null"),
    }


def pattern_coverage_probe() -> dict[str, Any]:
    """**裁定 93.5 的对照探针**：先证明本文件的识别模式抓得到已知形态的坏引用。

    注入 4 条**已知形态**的坏 prompt（含真 f-string 同形、含维度数不等于 32、含负号紧贴、
    含形状漂移），逐条报 `detected`。任一条抓不到 ⇒ `auditor_self_verdict="RED"`（审计器自己红）。
    """
    def mk(tokens: Sequence[int], *, tail: str = ";\nAction: ", head: str = "Task: transfer the red cube, ") -> str:
        return f"{head}State: {' '.join(str(int(t)) for t in tokens)}{tail}"

    injected = [
        {"form": "canonical_fstring_shape_with_one_minus1",
         "prompt": mk([0] * 13 + [ILLEGAL_BIN_LOW] + [7] * 18),
         "expect_detected": True, "expect_illegal_dims": [13]},
        {"form": "all_dims_minus1",
         "prompt": mk([ILLEGAL_BIN_LOW] * MAX_STATE_DIM),
         "expect_detected": True, "expect_illegal_dims": list(range(MAX_STATE_DIM))},
        {"form": "minus1_glued_to_neighbours_no_space_padding",
         "prompt": mk([5, ILLEGAL_BIN_LOW, ILLEGAL_BIN_LOW, 255]),
         "expect_detected": True, "expect_illegal_dims": [1, 2]},
        {"form": "shape_drift_state_segment_without_semicolon",
         "prompt": "Task: x, State: " + " ".join(["0"] * 31 + ["-1"]) + "\nAction: ",
         "expect_detected": True, "expect_parse_path": "state_marker_present_unparsed",
         "expect_note": "窄正则要求 `;` 收尾 ⇒ 这条由**形状漂移**分支判红（本探针曾实测漏检、已补第三层）"},
        {"form": "shape_drift_uppercase_and_newline_separator",
         "prompt": "Task: x, STATE:\n" + "\n".join(["0"] * 5 + ["-1"]) + "\nAction: ",
         "expect_detected": True, "expect_parse_path": "state_marker_present_unparsed",
         "expect_note": "大写 `STATE:` + 换行分隔 ⇒ 同样必须由形状漂移分支判红"},
    ]
    detail = []
    for case in injected:
        a = audit_prompt_text(case["prompt"])
        detected = bool(a.get("verdict") == "RED")
        dims = sorted(int(i) for i in (a.get("illegal_bin_hits") or []))
        exp = case.get("expect_illegal_dims")
        dim_ok = (dims == sorted(exp)) if exp is not None else True
        exp_path = case.get("expect_parse_path")
        path_ok = (a.get("parse_path") == exp_path) if exp_path is not None else True
        detail.append({"injected_bad_form": case["form"], "detected": detected,
                       "illegal_dims_observed": dims, "illegal_dims_expected": exp,
                       "dims_match": dim_ok, "verdict": a.get("verdict"),
                       "red_class": a.get("red_class"), "parse_path": a.get("parse_path"),
                       "parse_path_expected": exp_path, "parse_path_match": path_ok,
                       "expect_note": case.get("expect_note"),
                       "ok": bool(detected and dim_ok and path_ok)})
    all_ok = all(d["ok"] for d in detail)
    # 阴性对照：合法 prompt 必须**不**被判红（否则牙是恒真的，等于没有牙）
    neg = audit_prompt_text(mk([0, 128, SAT_BIN_HIGH, 7] + [0] * 28))
    negative_ok = bool(neg.get("verdict") == "GREEN" and neg.get("n_illegal_bin_minus1") == 0)
    return {
        "artifact": "pattern_coverage_probe",
        "discipline": "reference_auditor_must_prove_its_own_pattern_coverage（裁定 93.5 / 缺陷类 ⑲）",
        "n_injected_bad_forms": len(injected), "detail": detail,
        "injected_bad_form": [d["injected_bad_form"] for d in detail],
        "detected": all_ok,
        "negative_control": {"form": "legal_bins_only_including_255",
                             "verdict": neg.get("verdict"),
                             "n_illegal_bin_minus1": neg.get("n_illegal_bin_minus1"),
                             "ok": negative_ok,
                             "why": "合法 prompt（含 bin 255 的**合法**上侧饱和）必须判绿；判红 ⇒ 牙恒真"},
        "auditor_self_verdict": ("GREEN" if (all_ok and negative_ok) else "RED"),
        "if_probe_missing_then": "not_measured，且**不得报绿**（裁定 93.5 原文）",
    }


class PromptCapture:
    """旁路挂钩 `PolicyProcessorPipeline`，抓**真正进模型的那一条 prompt 文本**。

    为什么用 hook 而不是自己再跑一遍 tokenizer step：自己跑一遍得到的是**另一份**文本，
    与模型实际吃到的那份之间没有任何绑定 ⇒ 那正是"离线 stats 绿、运行时红"的分叉形状。
    `register_after_step_hook`（`lerobot/processor/pipeline.py:1264`）在**每个 step 之后**回调，
    本类只在 `Pi05PrepareStateTokenizerProcessorStep` 之后取
    `transition[COMPLEMENTARY_DATA]["task"]`（`processor_pi05.py:86` 写回的位置）。
    """

    def __init__(self, pipeline: Any, *, task_key: str = "task", keep_last_n: int = 512):
        self.pipeline = pipeline
        self.task_key = task_key
        self.keep_last_n = int(keep_last_n)
        self.step_class_hits: dict[str, int] = {}
        self.prompts: list[str] = []
        self.n_captures = 0
        self.hook_error: str | None = None
        self.attached = False
        self._hook = self._make_hook()

    def _make_hook(self):
        def hook(idx: int, transition: Any) -> None:
            try:
                steps = list(getattr(self.pipeline, "steps", []) or [])
                cls_name = type(steps[idx]).__name__ if idx < len(steps) else "unknown"
                self.step_class_hits[cls_name] = self.step_class_hits.get(cls_name, 0) + 1
                if cls_name != PI05_TOKENIZER_STEP_CLASS:
                    return
                from lerobot.processor.core import TransitionKey
                comp = transition.get(TransitionKey.COMPLEMENTARY_DATA, {}) or {}
                val = comp.get(self.task_key)
                self.n_captures += 1
                if isinstance(val, (list, tuple)):
                    for v in val:
                        if isinstance(v, str):
                            self.prompts.append(v)
                elif isinstance(val, str):
                    self.prompts.append(val)
                if len(self.prompts) > self.keep_last_n:
                    self.prompts = self.prompts[-self.keep_last_n:]
            except Exception as exc:                                  # noqa: BLE001
                # 钩子里抛异常会污染推理主循环 ⇒ 吞掉但**必须留痕**，
                # 由 `audit()` 把"没抓到"判成 `not_measured`，不判绿。
                self.hook_error = f"{type(exc).__name__}: {exc}"
        return hook

    def attach(self) -> "PromptCapture":
        if self.attached:
            return self
        self.pipeline.register_after_step_hook(self._hook)
        self.attached = True
        return self

    def detach(self) -> None:
        if not self.attached:
            return
        try:
            self.pipeline.unregister_after_step_hook(self._hook)
        except Exception as exc:                                      # noqa: BLE001
            self.hook_error = (self.hook_error or "") + f" | detach:{type(exc).__name__}: {exc}"
        self.attached = False

    def __enter__(self) -> "PromptCapture":
        return self.attach()

    def __exit__(self, *_exc: Any) -> None:
        self.detach()

    def last_prompt(self) -> str | None:
        return self.prompts[-1] if self.prompts else None

    def audit(self, *, prompts: Sequence[str] | None = None) -> dict[str, Any]:
        """对本轮抓到的 prompt 逐条审 + 聚合。**0 条 ⇒ `not_measured` + 非零退出要求**。"""
        ps = list(self.prompts if prompts is None else prompts)
        per = [audit_prompt_text(p) for p in ps]
        agg = aggregate_prompt_audit(per)
        agg.update({
            "capture_mechanism": f"register_after_step_hook on {PI05_TOKENIZER_STEP_CLASS}",
            "capture_hook_file_line": "lerobot/processor/pipeline.py:1264（register_after_step_hook）",
            "prompt_writeback_file_line": f"{PI05_TOKENIZER_STEP_FILE}:86"
                                          "（transition[COMPLEMENTARY_DATA][task_key] = full_prompts）",
            "n_hook_captures": self.n_captures,
            "step_class_hits": dict(self.step_class_hits),
            "tokenizer_step_seen": bool(self.step_class_hits.get(PI05_TOKENIZER_STEP_CLASS, 0) > 0),
            "hook_error": self.hook_error,
            "attached_at_audit_time": bool(self.attached),
            "pattern_coverage_probe": pattern_coverage_probe(),
        })
        if not ps:
            agg["why"] = ("本轮**一条 prompt 都没抓到**（hook 未命中 tokenizer step / 未推理 / "
                          f"hook_error={self.hook_error!r}）⇒ `not_measured`，不许读成 0 命中")
        if agg.get("pattern_coverage_probe", {}).get("auditor_self_verdict") != "GREEN":
            agg["verdict"] = "RED"
            agg["red_class"] = ((agg.get("red_class") or "") + "+auditor_pattern_coverage_self_red")
            agg["why"] = (str(agg.get("why")) + "｜对照探针自证失败 ⇒ 审计器自己红（裁定 93.5）")
        agg["per_prompt_first3"] = per[:3]
        return agg


def attach_prompt_capture(pipeline: Any, **kw: Any) -> PromptCapture:
    return PromptCapture(pipeline, **kw).attach()


# ══════════════════════════ ② `pad_vector` 缺口 = `not_measured` ══════════════════════════
def pad_vector_gap_registration(*, measured: bool = False,
                                evidence: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """`processor_pi05.py:72` 的 `pad_vector(state, max_state_dim=32)` —— **D 未测过这一维**。

    三值纪律落地：默认 `measured=False` ⇒ `value=null` / `safe=null` /
    `measurement_status="not_measured"`。**不许**写 `false`、**不许**写 `0`、**不许**假设安全。
    只有当调用方给出**实测证据**（`measured=True` + `evidence`）时才允许写阳性/阴性结论。

    未测的具体缺口（登记为 `open_questions`，不是结论）：
      * 14 维 state → 32 维的**填充值**是什么（`modeling_pi05.py:133` 的实现），
        填充槽位离散化后落在哪个 bin；若填充值使 `digitize` 出 `-1`，则**每一帧**都带 18 维非法 token。
      * `pad_vector` 对 `dim > 32` 的输入是**截断**还是**抛**（截断 = 静默丢维）。
      * batch 维/设备维的处理是否与 `NormalizerProcessorStep` 的输出形状一致。
    """
    ev = dict(evidence or {})
    if not measured:
        return {
            "artifact": "pad_vector_gap_registration",
            "subject": f"{PI05_TOKENIZER_STEP_FILE}:{PI05_PAD_VECTOR_LINE} → {PI05_PAD_VECTOR_DEF}",
            "measurement_status": "not_measured",
            "value": None, "safe": None, "verdict": None,
            "nonzero_exit_required": False,
            "must_not_be_written_as": ["false", "0", "safe", "no_defect"],
            "why": ("D 未测过这一维（`d_handoff_to_a2_20260930.md` §一-2 原文：「D 未测过这一维，"
                    "**不得假设安全**」）⇒ 按三值纪律登记为 `not_measured`；"
                    "`absence_of_measurement_is_not_measurement_of_absence`"),
            "open_questions": [
                "14→32 的填充值是什么、填充槽位离散化后落哪个 bin（若出 -1 则每帧带 18 维非法 token）",
                "dim>32 的输入是截断还是抛（截断 = 静默丢维）",
                "batch/设备维形状是否与 NormalizerProcessorStep 的输出一致",
            ],
            "partial_evidence_available": {
                "runtime_state_dim_after_pad": ev.get("runtime_state_dim_after_pad"),
                "note": ("运行时 prompt 文本里的 token 数（`audit_prompt_text.state_dim_after_pad`）"
                         "是**旁证**：它证明 pad 之后的**长度**，不证明填充**值**是否合法。"
                         "若长度 != 32 ⇒ 形状与 `max_state_dim` 不符，属另一类缺陷"),
            },
            "authority": "d_handoff_to_a2_20260930.md §一-2；裁定 88.3-1（三值纪律）",
        }
    return {"artifact": "pad_vector_gap_registration",
            "subject": f"{PI05_TOKENIZER_STEP_FILE}:{PI05_PAD_VECTOR_LINE} → {PI05_PAD_VECTOR_DEF}",
            "measurement_status": "measured", "evidence": ev,
            "value": ev.get("value"), "safe": ev.get("safe"), "verdict": ev.get("verdict"),
            "nonzero_exit_required": bool(ev.get("verdict") == "RED"),
            "authority": "调用方给出实测证据后才允许写阳性/阴性结论"}


# ══════════════════════════ ③ `renderer_class` 三点读数 ══════════════════════════
RENDERER_POINTS = ("at_start", "in_run", "at_end")


def classify_renderer(gl_renderer: str | None) -> str | None:
    """GL_RENDERER 原文 → `renderer_class`。分类口径与 `scripts/b2_s1_probe5_egl_render_cost.py:174`
    同形（`NVIDIA` ⇒ `nvidia_gpu`），**读不到 ⇒ `null`，不猜 `software`**。"""
    if gl_renderer is None:
        return None
    r = str(gl_renderer).upper()
    if not r or r.startswith("ERROR:") or r == "NULL_CONTEXT":
        return None
    if "NVIDIA" in r:
        return "nvidia_gpu"
    if any(t in r for t in ("LLVMPIPE", "SOFTPIPE", "SWRAST", "MESA OFFSCREEN")):
        return "software"
    return "other_gpu"


class RendererClassLedger:
    """`renderer_class` 的**三点**读数（起点 / 运行内 / 终点）。

    硬规则（D 的派工原文）：**终点若未在运行内测就写 `null` 并标 `measurement_kind`，
    不许拿起点值顶替**。所以本类不给 `at_end` 提供任何"从 at_start 回填"的路径；
    `snapshot()` 里 `at_end.value` 只有两种来源：`record("at_end", …)` 显式写过的值，或 `null`。
    """

    def __init__(self) -> None:
        self._rec: dict[str, dict[str, Any]] = {
            p: {"value": None, "renderer_class": None, "gl_renderer_raw": None,
                "measurement_kind": "not_measured", "measured_at": None,
                "probe_path": None, "mujoco_gl_env": None}
            for p in RENDERER_POINTS}
        self._in_run_gl_context_live = False

    def record(self, point: str, gl_renderer_raw: str | None, *,
               probe_path: str = "unspecified", measurement_kind: str = "measured_in_process") -> None:
        if point not in RENDERER_POINTS:
            raise ValueError(f"unknown renderer_class point {point!r}，可选 {RENDERER_POINTS}")
        if measurement_kind == "not_measured":
            raise ValueError("measurement_kind='not_measured' 不允许由 record() 写（那是默认态，"
                             "写它等于把'没测'伪造成'测了'）")
        self._rec[point] = {
            "value": gl_renderer_raw, "renderer_class": classify_renderer(gl_renderer_raw),
            "gl_renderer_raw": gl_renderer_raw, "measurement_kind": measurement_kind,
            "measured_at": now_iso(), "probe_path": probe_path,
            "mujoco_gl_env": os.environ.get("MUJOCO_GL"),
        }
        if point == "in_run" and gl_renderer_raw:
            self._in_run_gl_context_live = True

    def probe_gl_renderer(self, *, point: str, inside_real_render: bool = False) -> dict[str, Any]:
        """真实取数路径（裁定 72：自检必须走真实取数路径）。

        `inside_real_render=True` 表示这次读发生在 `physics.render()` 刚返回、GL 上下文仍 current
        的时候（**可信**）；否则是裸调，读到 NULL 时**必须**写 `null_context`、不许猜。
        """
        kind = "measured_inside_real_render" if inside_real_render else "measured_bare_no_context"
        try:
            from OpenGL.GL import GL_RENDERER, glGetString
            v = glGetString(GL_RENDERER)
        except Exception as exc:                                      # noqa: BLE001
            raw = f"error:{type(exc).__name__}"
            self.record(point, raw, probe_path="probe_failed", measurement_kind=kind)
            return dict(self._rec[point], error=f"{type(exc).__name__}: {exc}")
        if not v:
            # 读到 NULL ⇒ **一律** `not_measured_no_gl_context`，与"是不是刚渲染过"无关。
            # 修前的写法在 `inside_real_render=True` 时把 NULL 记成 `measured_inside_real_render`
            # ⇒ 那是**把"没测到"写成"测到了"**（红线 `absence_of_measurement_is_not_measurement_of_absence`）。
            # `inside_real_render` 只影响 `probe_path`（记"试过哪条取数路径"），不影响 measurement_kind。
            self._rec[point] = {"value": None, "renderer_class": None,
                                "gl_renderer_raw": "null_context",
                                "measurement_kind": "not_measured_no_gl_context",
                                "measured_at": now_iso(),
                                "probe_path": ("inside_real_render_attempted_but_null"
                                               if inside_real_render else "bare_no_context"),
                                "inside_real_render_attempted": bool(inside_real_render),
                                "mujoco_gl_env": os.environ.get("MUJOCO_GL"),
                                "why_null": ("`glGetString(GL_RENDERER)` 返回 NULL = 本线程没有 current "
                                             "GL 上下文（dm_control 的渲染可能跑在 RenderExecutor 的"
                                             "工作线程上）⇒ 读不到就是读不到，**不猜 software**")}
            return dict(self._rec[point])
        raw = v.decode() if isinstance(v, bytes) else str(v)
        self.record(point, raw, probe_path=("inside_real_render" if inside_real_render
                                            else "bare_with_context"), measurement_kind=kind)
        return dict(self._rec[point])

    def snapshot(self) -> dict[str, Any]:
        end = self._rec["at_end"]
        start = self._rec["at_start"]
        in_run = self._rec["in_run"]
        same = None
        if end["measurement_kind"] != "not_measured" and start["renderer_class"] is not None:
            same = bool(end["renderer_class"] == start["renderer_class"])
        return {
            "artifact": "renderer_class_three_points",
            "points": {p: dict(self._rec[p]) for p in RENDERER_POINTS},
            "at_start": start["renderer_class"],
            "in_run": in_run["renderer_class"],
            "at_end": end["renderer_class"],
            "at_end_measurement_kind": end["measurement_kind"],
            "at_end_is_null_because_not_measured_in_run": bool(
                end["renderer_class"] is None and end["measurement_kind"].startswith("not_measured")),
            "start_must_not_substitute_for_end": True,
            "end_equals_start": same,
            "in_run_gl_context_was_live": bool(self._in_run_gl_context_live),
            "stability_verdict": (None if same is None else ("stable" if same else "CHANGED")),
            "c4_piggyback_evidence_for_e": {
                "what_e_needs": ("`renderer_class` 回 `nvidia_gpu` ⇒ 证明 E 的前缀改动无害"
                                 "（`params:1412` `c4_reverify_piggybacks_no_window`）"),
                "renderer_class_at_start": start["renderer_class"],
                "renderer_class_in_run": in_run["renderer_class"],
                "renderer_class_at_end": end["renderer_class"],
                "conclusion": (None if (start["renderer_class"] is None and in_run["renderer_class"] is None)
                               else ("nvidia_gpu_observed"
                                     if "nvidia_gpu" in (start["renderer_class"],
                                                         in_run["renderer_class"],
                                                         end["renderer_class"])
                                     else "nvidia_gpu_not_observed")),
                "attribution_strength": "inferred_from_gl_renderer_string",
            },
            "measurement_kind_vocabulary": [
                "measured_inside_real_render", "measured_bare_no_context",
                "not_measured", "not_measured_no_gl_context"],
        }


def gpu_window_readings(*, extra: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """一次 GPU 窗口读数：三网 + `loadavg`(3 点) + `nr_throttled` + `memory.used`。

    **成对纪律**：任何吞吐/延迟数字都必须成对引 `loadavg`(3 点) + `nr_throttled`
    （裁定 46.4 / 53.6 / 85.7）。cgroup 配额 12 核，`nproc=112` 是假象 ⇒ 分母用配额。
    三网占用判定复用 E 的探测器（不重造）；调用方若未提供 `calib` 模块，
    `three_net` 段写 `not_measured`，**不写 0**。
    """
    import subprocess
    out: dict[str, Any] = {"ts": now_iso()}
    try:
        la = os.getloadavg()
        out["loadavg"] = f"{la[0]:.2f} {la[1]:.2f} {la[2]:.2f}"
        out["loadavg_1m"], out["loadavg_5m"], out["loadavg_15m"] = la[0], la[1], la[2]
    except Exception as exc:                                          # noqa: BLE001
        out["loadavg"] = None
        out["loadavg_error"] = f"{type(exc).__name__}: {exc}"
    try:
        stat: dict[str, int] = {}
        for ln in pathlib.Path("/sys/fs/cgroup/cpu/cpu.stat").read_text().splitlines():
            k, _, v = ln.partition(" ")
            stat[k] = int(v)
        out["nr_throttled"] = stat.get("nr_throttled")
        out["nr_periods"] = stat.get("nr_periods")
        out["throttled_time_ns"] = stat.get("throttled_time")
    except Exception as exc:                                          # noqa: BLE001
        out["nr_throttled"] = None
        out["cpu_stat_error"] = f"{type(exc).__name__}: {exc}"
    try:
        r = subprocess.run(["nvidia-smi", "--query-gpu=utilization.gpu,memory.used,memory.total",
                            "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=30)
        parts = [p.strip() for p in (r.stdout or "").splitlines()[0].split(",")]
        out["gpu_util_pct"] = int(parts[0])
        out["gpu_memory_used_mib"] = int(parts[1])
        out["gpu_memory_total_mib"] = int(parts[2])
    except Exception as exc:                                          # noqa: BLE001
        out["gpu_error"] = f"{type(exc).__name__}: {exc}"
    try:
        r = subprocess.run(["nvidia-smi", "--query-compute-apps=pid,process_name,used_memory",
                            "--format=csv,noheader"], capture_output=True, text=True, timeout=30)
        rows = [ln.strip() for ln in (r.stdout or "").splitlines() if ln.strip()]
        out["n_compute_apps"] = len(rows)
        out["compute_apps"] = rows[:20]
    except Exception as exc:                                          # noqa: BLE001
        out["compute_apps_error"] = f"{type(exc).__name__}: {exc}"
        out["n_compute_apps"] = None
    out["cgroup_quota_cores"] = _cgroup_quota_cores()
    out["nproc_is_misleading"] = True
    if extra:
        out.update(extra)
    return out


def _cgroup_quota_cores() -> int | None:
    try:
        q = pathlib.Path("/sys/fs/cgroup/cpu/cpu.cfs_quota_us").read_text().strip()
        p = pathlib.Path("/sys/fs/cgroup/cpu/cpu.cfs_period_us").read_text().strip()
        if q == "-1":
            return None
        return max(1, int(int(q) / int(p)))
    except Exception:                                                 # noqa: BLE001
        return None


def three_net_readings(calib_module: Any | None, *, own_pid: int | None = None,
                       strict: bool = False, snapshot_fn: Any | None = None) -> dict[str, Any]:
    """三网占用判定：**复用 E 的探测器，不重造**（裁定 85.0-2 / 92）。

    `calib_module` = `scripts/e_mainline_render_calib.py`（`fd582e261e87` 或其后继）。
    未提供 ⇒ 三网段写 `not_measured`（**不写 0**），并由调用方判 `unknown_not_collected`。

    **修过的一个真实缺陷（登记，不静默）**：本函数原先调 `calib_module.three_net_snapshot(...)`，
    但 `three_net_snapshot()` 的**所有者不是 E 的探测器**，而是 A2 的
    `scripts/a2_egl_latency_remeasure.py:218`（它内部才调 E 的 `card_busy()`）。E 的模块上没有这个
    名字 ⇒ 旧代码每次都落进 `except` 分支、返回 `not_measured`，看起来"守纪律"，实际是
    **探测器根本没被调用**（缺陷类：`silent_not_measured_masking_a_wiring_bug`）。
    现在显式解析所有者模块，并把**被复用件的身份**落进返回值，使"复用的是哪一版"可核。
    """
    if calib_module is None:
        return {"measurement_status": "not_measured", "three_net": None,
                "why": "未提供 E 的探测器模块 ⇒ 三网读数缺失，按三值纪律写 not_measured，不写 0"}
    owner_path = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "a2_egl_latency_remeasure.py"
    owner_id = {"path": "scripts/a2_egl_latency_remeasure.py", "exists": owner_path.exists(),
                "sha256_12": (hashlib.sha256(owner_path.read_bytes()).hexdigest()[:12]
                              if owner_path.exists() else None),
                "role": "`three_net_snapshot()` 的所有者（内部调 E 的 `card_busy()`）"}
    if snapshot_fn is None:
        try:
            import importlib.util
            import sys as _sys
            spec = importlib.util.spec_from_file_location("a2_egl_latency_remeasure", owner_path)
            mod = importlib.util.module_from_spec(spec)
            _sys.modules.setdefault("a2_egl_latency_remeasure", mod)
            spec.loader.exec_module(mod)
            snapshot_fn = mod.three_net_snapshot
        except Exception as exc:                                        # noqa: BLE001
            return {"measurement_status": "not_measured", "three_net": None,
                    "snapshot_owner": owner_id,
                    "error": f"{type(exc).__name__}: {exc}",
                    "error_class": "snapshot_owner_unimportable",
                    "why": ("解析不到 `three_net_snapshot()` 的所有者 ⇒ `not_measured`（**不写 0**）；"
                            "这条路径曾被一个接线缺陷长期占用，见本函数 docstring")}
    try:
        snap = snapshot_fn(calib_module, own_pid=own_pid or os.getpid(),
                           strict=strict, with_memory=True)
    except Exception as exc:                                          # noqa: BLE001
        return {"measurement_status": "not_measured", "three_net": None,
                "snapshot_owner": owner_id,
                "error": f"{type(exc).__name__}: {exc}",
                "error_class": "snapshot_call_failed"}
    keys = ("n_compute_apps", "n_foreign_fd_holders", "n_other_line_gpu_intent",
            "n_other_line_script_wide", "foreign_fd_holders", "other_line_gpu_intent",
            "other_line_script_wide", "memory_used_mib", "strict", "scan_overhead_s")
    out = {k: snap.get(k) for k in keys if k in snap}
    out["measurement_status"] = "measured"
    out["busy_per_detector"] = snap.get("busy_per_detector")
    out["detector_module"] = getattr(calib_module, "__file__", None)
    out["detector_sha256_12"] = (hashlib.sha256(
        pathlib.Path(out["detector_module"]).read_bytes()).hexdigest()[:12]
        if out.get("detector_module") else None)
    out["snapshot_owner"] = owner_id
    out["own_descendants_excluded"] = snap.get("own_descendants_also_excluded")
    if not strict:
        # 三值纪律：`strict=False` 时 E 的 `card_busy()` 只把 cmdline **窄档**放进 `cmdline_hits`
        # ⇒ `n_other_line_script_wide` 恒为 0，那是**没测**，不是**测到没有**。
        out["wide_net_measurement_status"] = "not_measured_under_strict_false"
        out["wide_net_note"] = ("`n_other_line_script_wide=0` 在 `strict=False` 下是**假零**："
                                "宽档根本没被采。要测宽档必须 `strict=True`")
    out["reuse_not_reimplement"] = "card_busy()/three_net_snapshot() 来自 E 的探测器，A2 不重造（裁定 85.0-2）"
    return out
