#!/usr/bin/env python3
"""**S4a 出口判据** —— `harness/vla_runtime.py` 的**可手算短轨迹逐字段手核** + 12 道带牙的闸。

**依据**：裁定 65-6（`d_handoff_to_a2_20260929.md` §15.5）「对着真实 env 跑一条**可手算的短轨迹**，
**逐字段手核**」，对撞 v4 `01_开发技术方案.md:350` P3「用可手算短轨迹核对 target、mask、goal 和来源」
（文件身份三元组见 `CITATIONS`，裁定 64）。

## 手算表（`n_replan=2, H=4, prime_mode="hold"`，8 帧）——**这张表是人算的，不是脚本算的**

第 `g` 代在 `t_g = 2g` 发请求；`slot_c=[0,1]`、`slot_e=[2,3]`、`slot_d=[]`（H=2n ⇒ D 空）。
帧 `f` 的执行来源 = 第 `g-1` 代的 E，索引 `idx = f - t_{g-1}`：

| abs_frame | 请求发生在这一帧？ | source | chunk(gen) | chunk_index | 执行的动作（stub: `[100g+i, -(100g+i)]`） | 人算依据 |
|---|---|---|---|---|---|---|
| 0 | 是（g=0） | **hold** | — | — | `hold_action` | priming：t=0 无已承诺队列（附录二 §1） |
| 1 | — | **hold** | — | — | `hold_action` | 同上 |
| 2 | 是（g=1） | policy | **0** | **2** | `[2, -2]` | `idx = 2 - t_0 = 2 ∈ E=[2,3)` |
| 3 | — | policy | **0** | **3** | `[3, -3]` | `idx = 3 - 0 = 3 ∈ E` |
| 4 | 是（g=2） | policy | **1** | **2** | `[102, -102]` | `idx = 4 - t_1 = 4-2 = 2 ∈ E` |
| 5 | — | policy | **1** | **3** | `[103, -103]` | `idx = 5-2 = 3` |
| 6 | 是（g=3） | policy | **2** | **2** | `[202, -202]` | `idx = 6 - t_2 = 6-4 = 2` |
| 7 | — | policy | **2** | **3** | `[203, -203]` | `idx = 7-4 = 3` |

⇒ 请求数 = **4**（g=0..3）；`activated` 行 = 8（每帧**恰好一行**）；
`not_activated` 行 = 每代 `|C|+|D| = 2+0` × 4 代 = **8**；`expired` = 0。

## 用法
    /root/venvs/pi05_sim/bin/python scripts/a2_s4a_vla_runtime_verify.py            # stub env（手算表）
    /root/venvs/pi05_sim/bin/python scripts/a2_s4a_vla_runtime_verify.py --real-env  # 真实 gym_aloha（主线 n=25/H=50）
**没有 `--policy pi05`（本轮不实现）**：真模型臂属 **S4b**，且 S4b 的 outcome 四类判定
blocked on C2 的 `harness/env_gym_aloha.py`（裁定 62 三条硬约束）。S4a 的 `policy_executed=false`
是**如实声明**，不是遗漏 —— 本脚本用确定性 stub 策略（动作恒等于 hold）正是为了让
「哪一代哪一索引在哪个绝对帧被下发」完全可手算。
真模型臂将来要跑时：必须先 `eval "$(bash scripts/e_activate_gpu_render.sh --print)"`（裁定 70），
在 `daily_report.md` 事前申报（>10 min 门槛），并确认当时没有生效中的静默窗口（裁定 73）。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import platform
import subprocess
import sys
import time
from datetime import datetime

REPO = pathlib.Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from harness import vla_runtime as VR                      # noqa: E402
from harness.contracts import EVENT_KINDS as CONTRACT_KINDS  # noqa: E402
from harness.ledger import EXECUTION_STATUS, FRAME_SOURCES, EVENT_KINDS as LEDGER_KINDS, FactLedger  # noqa: E402

# 裁定 64：**任何 v4 行号引用必须带文件身份三元组 (相对路径, sha256-12, 行号)**
_V4 = "RL_Harness_v4_20260924/materials/06_三轮递进调研与方案复审_20260923"
CITATIONS = [
    {"path": f"{_V4}/appendices/01_接口契约与开发验收.md", "sha256_12": "aae20ffe604f", "lines": [103, 105, 106, 107, 111, 115, 375],
     "used_for": "H≥2n / C-E-D 三槽 / 迟到规则 / 每帧单一来源 / requested→committed→activated 分别记录"},
    {"path": f"{_V4}/appendices/02_异步动作时间轴与学习目标.md", "sha256_12": "a6ab42165ab3", "lines": [11, 36, 38, 63],
     "used_for": "固定时间槽 + 显式动作队列；C 必须读已承诺的真实命令队列（不是新 proposal 的前 n 步）"},
    {"path": f"{_V4}/01_开发技术方案.md", "sha256_12": "0a9a2092e18a", "lines": [347, 350],
     "used_for": "P0「请求／入队／执行可区分，能选择 n」；P3「用可手算短轨迹核对 target、mask、goal 和来源」"},
]

HAND_TABLE = [
    # abs_frame, source, gen, chunk_index, action
    (0, "hold", None, None, None),
    (1, "hold", None, None, None),
    (2, "policy", 0, 2, [2.0, -2.0]),
    (3, "policy", 0, 3, [3.0, -3.0]),
    (4, "policy", 1, 2, [102.0, -102.0]),
    (5, "policy", 1, 3, [103.0, -103.0]),
    (6, "policy", 2, 2, [202.0, -202.0]),
    (7, "policy", 2, 3, [203.0, -203.0]),
]


# ── 裁定 84§4 的全线规则 `top_level_aggregate_must_declare_semantics`（A2 自己的产物先合规）──────
AGGREGATE_FIELD_SEMANTICS = {
    "_rule": ("裁定 84§4：**任何顶层汇总布尔/数值必须写明聚合语义（OR/AND/mean/worst/diff/count）**、"
              "**由一把闸或就地重算看守**、**不得留初值**。反例 = 裁定 84§3 里 D 自己撤回的"
              "「分量相加 33.13 ms > 同 run 同口径实测总量 26.28 ms」（新自查项 "
              "`component_sum_must_not_exceed_measured_total`）。"),
    "_sibling_rule": ("裁定 84§4 的另一条 `boolean_field_reading_must_be_declared` 在本产物族里的承载 = "
                      "`cases.*.design_points_open_to_d.*`（每个设计点都写 `value` / `status` / `ruling` / "
                      "`overturnable_if`）与 `scripts/a2_egl_latency_remeasure.py` 的 `POLICY_EXECUTED_DEFINITION`。"),
    "all_ok": {"aggregate": "AND", "over": "gates[*].ok",
               "recomputed": "`n_ok == len(gates)`，在所有闸算完之后就地算，**不留初值**",
               "guard": "每条闸各自带 `ok` ⇒ 读者可逐条复核；退出码 `0 if (n_ok == len(gates) and all_have_teeth) else 3`"},
    "n_gates / n_ok": {"aggregate": "count", "over": "`len(gates)` / `sum(1 for g in gates.values() if g.get('ok'))`",
                       "note": "**闸数会变**（17 → 18，裁定 83§5② 加了 G18）⇒ 引用闸数必须带 `generated_at`"},
    "gate_teeth_mutation_selftest.all_have_teeth": {
        "aggregate": "AND", "over": "detail[*].teeth",
        "teeth_definition": ("`teeth = baseline_ok AND (NOT mutant_ok)` —— **两处都要**：基线必须绿、"
                             "篡改后必须红。只红不绿（恒假牙）与只绿不红（装饰品）**都不算有牙**"),
        "note": "`gates_tested` 计的是**变异体条数**（23），不是闸数（18）：G12/G13/G15/G17/G18 各有多条变异体"},
    "gates.G18_timeout_scope_td_only_83_5_2.ok": {
        "aggregate": "AND", "over": ["checks 的 10 项全 true", "validator_teeth 的 7 条红牙全 `raised`",
                                     "绿见证 `green_witness_valid_records == passed`"],
        "guard": "裁定 83.2 `green_witness_required`：**没有绿见证的单向断言不算牙**"},
    "cases.*.training_view.td_eligible / bc_eligible": {
        "aggregate": "NOT-OR（= 无任何隔离原因）", "over": "`td_isolation_reasons` / `bc_isolation_reasons` 分别判空",
        "warning": ("**`TrainingView.isolation_reasons` 是 td ∪ bc 的并集**（`harness/contracts.py:40` 是冻结面、"
                    "加不了分列字段）⇒ 裁定 83§5② 的 `td_only` 之后**只看它会误判**："
                    "`bc_eligible=true` 与 `isolation_reasons` 非空**可以同时成立**。"
                    "分列看账本 `episode_end` 事件的 `td_isolation_reasons` / `bc_isolation_reasons`。"
                    "详见 `docs/a2_s4_vla_runtime_interface_20260929.md` §12.4")},
    "cases.real_env.budget_fraction": {
        "aggregate": "worst（单臂单值）", "over": "`wall_ms_per_ctrl_step ÷ 34.0 ms`",
        "caveat": ("**该臂是 CPU 软渲染口径**（实测 `GL_RENDERER=llvmpipe (LLVM 15.0.7, 256 bits)`、"
                   "取数路径 `inside_real_render`）⇒ `budget_fraction 3.64` **不是主线口径、不得与 "
                   "GPU 干净窗的 0.7703–0.8009 互搬**（裁定 46.4 / 53.6 / 71）。"
                   "主线权威值见 `daily_report.md` §13.1 与裁定 84§1")},
    "cases.*.timing_report.realtime_closed_loop_claim": {
        "aggregate": "constant_false", "over": "恒 `false`，**不是任何测量的汇总**",
        "guard": ("裁定 75.5 / 83§5④ / 84§6：`async_overlap=false`、异步未实现 ⇒ 不得声称异步实时闭环；"
                  "G17a 的牙 = 把它改成 `true` 即红。**裁定 84§6 只解除了「同步闭环在预算内」的措辞禁令，"
                  "异步禁令继续有效**")},
    "contracts_py_modified / frozen_surface_touched": {
        "aggregate": "constant（声明 + 实测 sha 双证）",
        "over": "`contracts_py_sha256_12` 与 `ledger_py_sha256_12` 由本脚本运行时 `sha256sum` 实算，不是抄来的",
        "guard": "调用方另用 `git status --porcelain harness/contracts.py harness/runtime_adapter.py configs/` 复核（必须空输出）"},
}


# ───────────────────────── stub env / policy（可手算）─────────────────────────
class StubEnv:
    """确定性 stub：`state=[f, -f]`、`hold_action=[0.5, -0.5]`；**不需要 mujoco、不占 GPU**。"""
    dt_s = 0.034
    control_hz = VR.MAINLINE_CONTROL_HZ
    max_episode_steps = 300
    d_a = 2

    def __init__(self, n_frames: int = 8, drop_images: bool = False):
        self.f = 0
        self.n_frames = n_frames
        self.applied: list = []
        # `drop_images=True` = **变异体**：模拟 G3 那族静默退化（images={}），用来给 G16 上牙
        self.drop_images = drop_images

    def render_backend(self) -> tuple[str, ...]:
        return ("stub_env", "no_renderer", "n/a", "stub", "0cam", "0px")

    def _fake_images(self, frame: int) -> dict:
        """确定性占位图（2×2×3，值 = frame/255）：**键齐全**即可，S4a 不验像素内容。"""
        if self.drop_images:
            return {}
        v = float(frame) / 255.0
        return {k: [[[v, v, v], [v, v, v]], [[v, v, v], [v, v, v]]] for k in VR.REQUIRED_IMAGE_KEYS}

    def _obs(self, frame: int) -> VR.ObsBundle:
        return VR.ObsBundle(frame=frame, images=self._fake_images(frame), state=[float(frame), -float(frame)],
                            state_raw_14d=[float(frame), -float(frame)], goal_id="A_to_B",
                            dt_s=self.dt_s, control_hz=self.control_hz,
                            representation_version="stub", render_backend=self.render_backend())

    def reset(self, seed: int) -> VR.ObsBundle:
        self.f = 0
        self.applied = []
        return self._obs(0)

    def observe(self, frame: int) -> VR.ObsBundle:
        return self._obs(frame)

    def hold_action(self):
        return [0.5, -0.5]

    def apply(self, action):
        self.applied.append((self.f, list(action)))
        self.f += 1
        return 0.0, False, (self.f >= self.n_frames), {"qpos": [float(self.f), -float(self.f)]}


class StubPolicy:
    """`actions[i] = [100·g + i, -(100·g + i)]` ⇒ 每个索引的值都能口算。"""
    chunk_size = 4

    def __init__(self, stats_version: str = "s2_stats@stub1234", policy_version: str = "stub_policy@v1",
                 slow_factor: float = 0.0, mutate_version_after_commit: bool = False):
        self.stats_version = stats_version
        self.policy_version = policy_version
        self.slow_factor = slow_factor
        self.mutate_version_after_commit = mutate_version_after_commit
        self.g = 0
        self.calls = 0

    def reset(self, seed: int) -> None:
        self.g = 0
        self.calls = 0

    def select_chunk(self, obs: VR.ObsBundle) -> VR.ActionChunk:
        g = self.g
        self.g += 1
        self.calls += 1
        H = self.chunk_size
        acts = [[100.0 * g + i, -(100.0 * g + i)] for i in range(H)]

        class _A:  # 轻量替身：runtime 只用 .shape[0] 与 [idx]
            def __init__(self, rows):
                self.rows = rows
                self.shape = (len(rows), len(rows[0]))

            def __getitem__(self, i):
                return self.rows[i]

        if self.mutate_version_after_commit:
            self.policy_version = self.policy_version + "_MUTATED"
        n = 2
        return VR.ActionChunk(
            request_id="placeholder", chunk_index=-1, chunk_id=f"stub-chunk-{g}", lease_generation=-1,
            epoch=0, actions=_A(acts), created_at_frame=-1, planned_frames=(-1, -1),
            slot_c=tuple(range(0, n)), slot_e=tuple(range(n, 2 * n)), slot_d=tuple(range(2 * n, H)),
            dt_s=0.034, control_hz=VR.MAINLINE_CONTROL_HZ, n_replan=n, chunk_size=H,
            inference_wall_s=(self.slow_factor if self.slow_factor else None),
            deadline_frame=-1, deadline_s=-1.0, policy_version=self.policy_version,
            stats_version=self.stats_version, shim_sha256_12="stub", representation_version="placeholder")


# ───────────────────────── 真实 env 适配器（A2 自己的渲染路径）──────────────────
class GymAlohaAdapter:
    """真实 `gym_aloha/AlohaTransferCube-v0` + 主线 shim（`DT=0.034`）+ **A2 自己的三相机渲染路径**。

    相机与键映射沿用 G3 已验证的实现（`scripts/a2_pi05_zeroshot_eval.py:190`、`:249`–`:250`），
    **不走 `AlohaEnv._format_raw_obs`**（它只交 `top`、还白渲染 2 张，见 S4 草案 §2.3）。
    """
    CAM_MAP = {"top": "angle", "left_wrist": "left_wrist", "right_wrist": "right_wrist"}

    def __init__(self, image_size: int = 224, render: bool = True, dt: float = VR.MAINLINE_DT_S):
        from envs import gym_aloha_shim as shim
        self.shim = shim
        self.env, self.applied_rec = shim.make_env(VR.ENV_ID, dt=dt, obs_type="pixels_agent_pos",
                                                   render_mode="rgb_array")
        self.live = shim.read_live_timing(self.env)
        self.dt_s = float(self.live["control_timestep_s"])
        self.control_hz = float(self.live["control_hz"])
        self.max_episode_steps = VR.MAINLINE_MAX_EPISODE_STEPS
        self.image_size = image_size
        self.render = render
        self.physics = self.env.unwrapped._env.physics
        self.task = self.env.unwrapped._env.task
        self.hold = None
        self.f = 0
        self.n_renders = 0
        self._gl_renderer_cached: str | None = None
        self._gl_probe_path: str | None = None

    def _probe_gl_renderer(self) -> tuple[str, str]:
        """返回 (GL_RENDERER, 取数路径)。**裁定 72：自检必须走真实取数路径**。

        裸调 `glGetString` 在没有 current context 时返回 NULL ⇒ 会被误读成"没有渲染器"，
        所以必须标注这次读到的值是从哪条路径来的：
          `inside_real_render` = 在 `physics.render()` 刚返回、mujoco 的 GL 上下文仍 current 时读到（**可信**）；
          `bare_no_context`    = 没有真实渲染兜底、裸调读到（**不可信，只作占位**）。
        """
        try:
            from OpenGL.GL import GL_RENDERER, glGetString
            v = glGetString(GL_RENDERER)
        except Exception as exc:
            return f"error:{type(exc).__name__}", "probe_failed"
        if not v:
            return "null_context", "bare_no_context"
        if self._gl_renderer_cached:
            return self._gl_renderer_cached, (self._gl_probe_path or "inside_real_render")
        val = v.decode() if isinstance(v, bytes) else str(v)
        return val, (self._gl_probe_path or "bare_no_context")

    def render_backend(self) -> tuple[str, ...]:
        gl = os.environ.get("MUJOCO_GL")
        rend, path = self._probe_gl_renderer()
        import mujoco
        # 相机数按**本适配器实际会不会渲染**报，不按 CAM_MAP 的静态长度报：
        # `--no-render` 时若仍写 `3cam@224`，representation_version 就会给状态-only 口径盖上视觉口径的章。
        n_cam = len(self.CAM_MAP) if self.render else 0
        return (sys.executable.split("/")[-2], f"MUJOCO_GL={gl}",
                f"GL_RENDERER={rend}|probe={path}",
                f"mujoco={mujoco.__version__}", "viperx300s_bimanual", f"{n_cam}cam@{self.image_size}")

    def _state(self):
        import numpy as np
        return np.asarray(self.task.get_qpos(self.physics), dtype="float32")

    def _images(self):
        import numpy as np
        out = {}
        if not self.render:
            return out
        for key, cam in self.CAM_MAP.items():
            a = self.physics.render(height=self.image_size, width=self.image_size, camera_id=cam)
            out[key] = np.asarray(a).transpose(2, 0, 1).astype("float32") / 255.0
            if self._gl_renderer_cached is None:
                # 就在真实渲染之后立刻读 ⇒ 上下文仍 current，这条读数是事实（裁定 71/72）
                try:
                    from OpenGL.GL import GL_RENDERER, glGetString
                    v = glGetString(GL_RENDERER)
                    if v:
                        self._gl_renderer_cached = v.decode() if isinstance(v, bytes) else str(v)
                        self._gl_probe_path = "inside_real_render"
                except Exception:
                    pass
        self.n_renders += 1
        return out

    def _obs(self, frame: int) -> VR.ObsBundle:
        st = self._state()
        return VR.ObsBundle(frame=frame, images=self._images(), state=st, state_raw_14d=st.copy(),
                            goal_id="transfer_cube_right_to_left", dt_s=self.dt_s,
                            control_hz=self.control_hz, representation_version="see_runtime",
                            render_backend=self.render_backend())

    def reset(self, seed: int) -> VR.ObsBundle:
        self.env.reset(seed=seed)
        self.physics = self.env.unwrapped._env.physics
        self.f = 0
        st = self._state()
        # hold = 当前 qpos（arm 维是绝对关节角；夹爪维夹到 [0,1]）
        h = [float(x) for x in st[:14]]
        for gi in (6, 13):
            h[gi] = min(max(h[gi], 0.0), 1.0)
        self.hold = h
        return self._obs(0)

    def observe(self, frame: int) -> VR.ObsBundle:
        return self._obs(frame)

    def hold_action(self):
        if self.hold is None:
            raise VR.VlaRuntimeError("hold_action 在 reset 之前被调用（不许静默填 0）")
        return list(self.hold)

    def apply(self, action):
        import numpy as np
        a = np.asarray(action, dtype="float32").reshape(-1)
        if a.shape[0] != 14:
            raise VR.VlaRuntimeError(f"动作维度 {a.shape[0]} != 14（gym_aloha 的 action_space）")
        obs, reward, terminated, truncated, info = self.env.step(a)
        self.f += 1
        return float(reward), bool(terminated), bool(truncated), {"qpos": [float(x) for x in self._state()[:14]]}

    def close(self):
        try:
            self.env.close()
        except Exception:
            pass


class RealEnvStubPolicy:
    """真实 env 上的**确定性**策略：每个索引都返回 `hold`（初始 qpos）⇒ 机械臂保持不动，
    于是「哪一代哪一索引在哪个绝对帧被下发」这件事**完全可手算**（动作值恒定，不引入模型不确定性）。"""
    chunk_size = VR.MAINLINE_CHUNK_SIZE

    def __init__(self, adapter: GymAlohaAdapter, n_replan: int = VR.MAINLINE_N_REPLAN,
                 stats_version: str = VR.STATS_VERSION_ABSENT):
        self.adapter = adapter
        self.n_replan = n_replan
        self.stats_version = stats_version          # **真实情况就是 NONE**（裁定 44.1 / 49.2）
        self.policy_version = "deterministic_hold@v1"
        self.g = 0

    def reset(self, seed: int) -> None:
        self.g = 0

    def select_chunk(self, obs: VR.ObsBundle) -> VR.ActionChunk:
        g = self.g
        self.g += 1
        H = self.chunk_size
        n = self.n_replan
        base = list(self.adapter.hold)
        acts = [list(base) for _ in range(H)]

        class _A:
            def __init__(self, rows):
                self.rows = rows
                self.shape = (len(rows), len(rows[0]))

            def __getitem__(self, i):
                return self.rows[i]

        return VR.ActionChunk(
            request_id="placeholder", chunk_index=-1, chunk_id=f"hold-chunk-{g}", lease_generation=-1,
            epoch=0, actions=_A(acts), created_at_frame=-1, planned_frames=(-1, -1),
            slot_c=tuple(range(0, n)), slot_e=tuple(range(n, 2 * n)), slot_d=tuple(range(2 * n, H)),
            dt_s=self.adapter.dt_s, control_hz=self.adapter.control_hz, n_replan=n, chunk_size=H,
            inference_wall_s=None, deadline_frame=-1, deadline_s=-1.0,
            policy_version=self.policy_version, stats_version=self.stats_version,
            shim_sha256_12=self.adapter.shim.shim_sha256_12(), representation_version="placeholder")


def load_snapshot() -> dict:
    try:
        la = os.getloadavg()
    except Exception:
        la = (None, None, None)
    stat = {}
    try:
        for ln in pathlib.Path("/sys/fs/cgroup/cpu/cpu.stat").read_text().splitlines():
            k, _, v = ln.partition(" ")
            stat[k] = int(v)
    except Exception:
        pass
    return {"ts": datetime.now().astimezone().isoformat(timespec="seconds"),
            "loadavg_1m": la[0], "loadavg_5m": la[1], "loadavg_15m": la[2], "cpu_stat": stat}


def _cotenant_summary(samples: list, baseline_load: dict) -> dict:
    """按**裁定 73** 的判据给运行时采样下一个污染结论（判据逐字实现，不另造）。

    判据原文：窗内**有非本线 GPU 进程**，或 **`loadavg_1m` 高出（窗前基线）≥5** ⇒ `contaminated`。
    注意：CPU-only 的闲置他进程**不触发**该判据（判据写的是 GPU 进程），但**如实登记**，不隐藏。
    """
    if not samples:
        return {"verdict": "unknown_no_runtime_samples", "n_samples": 0,
                "rule": "裁定 73：非本线 GPU 进程 或 loadavg_1m 高出基线 ≥5 ⇒ contaminated"}
    gpu = [int(sm.get("gpu_compute_proc_count") or 0) for sm in samples]
    las = [float(sm["loadavg_1m"]) for sm in samples if sm.get("loadavg_1m") is not None]
    base = float((baseline_load or {}).get("loadavg_1m") or 0.0)
    other = [p for sm in samples for p in (sm.get("other_python_procs") or [])]
    idle_other = [p for p in other if float(p.get("pcpu") or 0.0) < 1.0]
    hit_gpu = max(gpu) > 0 if gpu else False
    hit_load = bool(las) and (max(las) - base) >= 5.0
    return {
        "verdict": ("contaminated" if (hit_gpu or hit_load) else "not_contaminated"),
        "rule": "裁定 73：非本线 GPU 进程 或 loadavg_1m 高出基线 ≥5 ⇒ contaminated",
        "n_samples": len(samples),
        "collected_at_run_time": all(sm.get("collected_at_run_time") is True for sm in samples),
        "gpu_compute_proc_count_max": max(gpu) if gpu else None,
        "gpu_trigger": hit_gpu,
        "loadavg_1m_baseline": base, "loadavg_1m_min": min(las) if las else None,
        "loadavg_1m_max": max(las) if las else None,
        "loadavg_trigger": hit_load,
        "nr_throttled_values": sorted({sm.get("nr_throttled") for sm in samples if sm.get("nr_throttled") is not None}),
        "non_self_cpu_procs_observed": len(other),
        "non_self_cpu_procs_all_idle": len(other) == len(idle_other),
        "non_self_cpu_proc_detail": other[:6],
        "note": ("CPU-only 的闲置他进程**不触发**裁定 73 的判据（判据写的是 GPU 进程），"
                 "但如实登记；归因强度只能是 inferred（裁定 76.1）"),
        "attribution_strength": "inferred_from_pid_and_timeline",
    }


def make_cotenant_sampler() -> "callable":
    """**运行时**共租证据采样器（裁定 76.3 红线 `cotenant_evidence_must_be_runtime`）。

    A2 上一轮被记纪律缺口的正是这一点：`cotenant_evidence.collected_at_run_time=false`（22:38 事后重建）。
    本轮改成 runtime 交给 `ChunkedVlaRuntime`，由它按墙钟节流调用（默认 ≥2 s 一次），
    并把**采样器自身开销单列**（`cotenant_sampling_ms_per_ctrl_step`），不藏进 other。

    **归因强度如实标注**：裁定 76.1 已明确容器内 `process_name` 为空、PID 跨命名空间不可见
    ⇒ 即便运行时采到 PID，把它归到某一条线仍只能是 `inferred`，**不得写 `confirmed`**。
    """
    def sample() -> dict:
        out: dict = {"ts": datetime.now().astimezone().isoformat(timespec="seconds"),
                     "self_pid": os.getpid()}
        try:
            la = os.getloadavg()
            out["loadavg_1m"], out["loadavg_5m"], out["loadavg_15m"] = la[0], la[1], la[2]
        except Exception as exc:
            out["loadavg_error"] = f"{type(exc).__name__}: {exc}"
        try:
            stat = {}
            for ln in pathlib.Path("/sys/fs/cgroup/cpu/cpu.stat").read_text().splitlines():
                k, _, v = ln.partition(" ")
                stat[k] = int(v)
            out["nr_throttled"] = stat.get("nr_throttled")
        except Exception as exc:
            out["cpu_stat_error"] = f"{type(exc).__name__}: {exc}"
        try:
            r = subprocess.run(["nvidia-smi", "--query-compute-apps=pid,used_memory",
                                "--format=csv,noheader"], capture_output=True, text=True, timeout=15)
            procs = [ln.strip() for ln in r.stdout.splitlines() if ln.strip()]
            out["gpu_compute_procs"] = procs
            out["gpu_compute_proc_count"] = len(procs)
            out["nvidia_smi_exit"] = r.returncode
            out["nvidia_smi_stderr"] = (r.stderr or "").strip()[:200]
        except Exception as exc:
            out["gpu_compute_procs_error"] = f"{type(exc).__name__}: {exc}"
        try:
            r = subprocess.run(["ps", "-eo", "pid,etimes,pcpu,comm"], capture_output=True,
                               text=True, timeout=15)
            mine = os.getpid()
            others = []
            for ln in r.stdout.splitlines()[1:]:
                parts = ln.split()
                if len(parts) >= 4 and parts[0].isdigit() and int(parts[0]) != mine:
                    if any(t in parts[-1] for t in ("python", "mujoco", "render")):
                        others.append({"pid": int(parts[0]), "etimes_s": int(parts[1]),
                                       "pcpu": float(parts[2]), "comm": parts[-1]})
            out["other_python_procs"] = others[:20]
            out["other_python_proc_count"] = len(others)
        except Exception as exc:
            out["ps_error"] = f"{type(exc).__name__}: {exc}"
        out["collected_at_run_time"] = True
        out["attribution_strength"] = "inferred_from_pid_and_timeline"
        out["attribution_note"] = ("裁定 76.1：容器内 `process_name` 为空、PID 跨命名空间不可见 "
                                   "⇒ 运行时采样能保证**时刻**是真的，但把某个 PID 归到某条线仍只能是 inferred，"
                                   "**不得写 confirmed**")
        return out
    return sample


def sha12(p: pathlib.Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()[:12]


# ───────────────────────── 闸（每条都要能被具体篡改打红）──────────────────────
def run_stub_case(*, n_frames: int = 8, prime_mode: str = "hold", slow_factor: float = 0.0,
                  stats_version: str = "s2_stats@stub1234", mutate_version: bool = False,
                  n_replan: int = 2, ledger_path: pathlib.Path | None = None,
                  env_horizon: int | None = None, drop_images: bool = False) -> dict:
    """`env_horizon` = StubEnv 的截断长度，**与循环帧数解耦**。

    为什么需要它：默认 `env_horizon == n_frames` ⇒ 循环最后一帧必然 truncated ⇒
    `finalize("timeout")`。**裁定 83§5② 之后 timeout 的语义变了**：原先 runtime 保守隔离把
    `bc_eligible` 也判 False，现在 `timeout_isolation_scope=td_only` ⇒ timeout 局是
    **TD 隔离、BC 保留但打标（`truncated_by_timelimit=true`）**。
    G8 要验的仍是「有 stats ⇒ 不因 stats 被隔离」⇒ **依旧需要一个不截断的干净参照**
    （否则 `bc_eligible is True` 这条会因为 timeout 口径放宽而"侥幸绿"，绿的原因与 stats 无关）；
    **G18 则反过来需要一个必然截断的案例**来验 timeout 口径 ⇒ 两种案例都必须留着。
    """
    env = StubEnv(n_frames=(env_horizon if env_horizon is not None else n_frames),
                  drop_images=drop_images)
    pol = StubPolicy(stats_version=stats_version, slow_factor=slow_factor,
                     mutate_version_after_commit=mutate_version)
    pol.chunk_size = 4
    ledger = None
    if ledger_path is not None:
        # SQLite 是**追加**的：同一文件被多次运行复用会让行数变成内存侧的整数倍（G14 假红）。
        # 不用 rm ⇒ 旧账本改名留档（与 run_real_case 同一处置，裁定 35.1）。
        if ledger_path.exists():
            ledger_path.rename(ledger_path.with_suffix(
                f".before_{datetime.now().strftime('%H%M%S_%f')}.sqlite"))
        ledger = FactLedger(ledger_path)
    rt = VR.ChunkedVlaRuntime(pol, env, episode_id="stub-ep0", goal_id="A_to_B", epoch=7,
                              n_replan=n_replan, dt_s=0.034, prime_mode=prime_mode, ledger=ledger,
                              shim_sha256_12="stub_shim_1234")
    rt.reset(seed=1000)
    steps = []
    tv = None
    err = None
    ended = "none"
    try:
        for _ in range(n_frames):
            r = rt.step()
            steps.append({"abs_frame": r.abs_frame, "source": r.source,
                          "execution_status": r.execution_status, "chunk_index": r.chunk_index,
                          "lease_generation": r.lease_generation, "late_choice": r.late_choice,
                          "action": [float(x) for x in r.action]})
            if r.truncated:
                ended = "timeout"      # gym 的 TimeLimit 截断 ⇒ 按秒登记（裁定 58.3）
                break
            if r.terminated:
                ended = "terminated"
                break
        tv = rt.finalize(ended, reward=0.0)
    except Exception as exc:
        err = f"{type(exc).__name__}: {exc}"
    out = {"steps": steps, "error": err, "n_requests": pol.calls,
           "representation_version": rt.representation_version,
           "manifest_caliber": rt.manifest_caliber(),
           # 契约事件流是 ActionEvent|OutcomeEvent 混合；OutcomeEvent 无 kind 字段
           # （harness/contracts.py:33-40，冻结面）⇒ 沿用仓内既有读法 getattr(ev,"kind","")
           # （rule_source: harness/ledger.py:457），把两类分流，避免把 OutcomeEvent 混进词表闸。
           "contract_event_kinds": [k for e in rt.contract_events if (k := getattr(e, "kind", ""))],
           "contract_outcome_event_count": sum(1 for e in rt.contract_events if not getattr(e, "kind", "")),
           "schedule_event_kinds": [e["kind"] for e in rt.schedule_events],
           "timing_report": rt.timing_report(),
           "frame_facts": rt.frame_facts, "late_records": rt.late_records,
           "deadline_pairs": [{"created_at_frame": c.created_at_frame, "deadline_frame": c.deadline_frame,
                               "deadline_s": c.deadline_s, "n_replan": c.n_replan, "dt_s": c.dt_s,
                               "chunk_id": c.chunk_id, "inference_wall_s": c.inference_wall_s,
                               "slot_budget_s": c.deadline_s,
                               "late": bool(c.inference_wall_s is not None and c.inference_wall_s > c.deadline_s)}
                              for c in rt.chunks.values()],
           "isolation_reasons": rt.isolation_reasons,
           "training_view": (None if tv is None else {
               "td_eligible": tv.td_eligible, "bc_eligible": tv.bc_eligible,
               "execution_mask": list(tv.execution_mask), "bc_mask": list(tv.bc_mask),
               "terminal_kind": tv.terminal_kind, "isolation_reasons": list(tv.isolation_reasons)}),
           # 裁定 83§5②：BC 溯源字段（`TrainingView` 是冻结面、加不了字段 ⇒ runtime 侧产出）
           "bc_record_extras": dict(rt.last_bc_record_extras),
           "design_points_open_to_d": rt.design_points_open_to_d()}
    if ledger is not None:
        out["ledger"] = {"path": str(ledger_path), "stats": ledger.stats(),
                         "n_frames_rows": len(ledger.frames(episode_id="stub-ep0")),
                         "n_event_rows": len(ledger.events(episode_id="stub-ep0"))}
        ledger.close()
    return out


def gate_hand_table(res: dict) -> dict:
    """G1：**逐字段手核**——脚本输出必须与人算表 `HAND_TABLE` 完全一致（含动作数值）。"""
    diffs = []
    got = res["steps"]
    if len(got) != len(HAND_TABLE):
        diffs.append(f"帧数 {len(got)} != 手算表 {len(HAND_TABLE)}")
    for i, (f, src, gen, idx, act) in enumerate(HAND_TABLE):
        if i >= len(got):
            break
        g = got[i]
        if g["abs_frame"] != f:
            diffs.append(f"frame {i}: abs_frame {g['abs_frame']} != {f}")
        if g["source"] != src:
            diffs.append(f"frame {f}: source {g['source']} != {src}")
        if (gen is None) != (g["lease_generation"] in (None, -1)):
            diffs.append(f"frame {f}: lease_generation {g['lease_generation']} vs 手算 gen={gen}")
        if gen is not None and g["lease_generation"] != gen:
            diffs.append(f"frame {f}: lease_generation {g['lease_generation']} != {gen}")
        if idx is not None and g["chunk_index"] != idx:
            diffs.append(f"frame {f}: chunk_index {g['chunk_index']} != {idx}")
        if act is not None and [round(x, 6) for x in g["action"]] != act:
            diffs.append(f"frame {f}: action {g['action']} != {act}")
        if src == "policy" and g["execution_status"] != "activated":
            diffs.append(f"frame {f}: policy 帧必须是 activated，实为 {g['execution_status']}")
    if res["n_requests"] != 4:
        diffs.append(f"请求数 {res['n_requests']} != 手算 4")
    return {"ok": not diffs, "diffs": diffs, "hand_table": HAND_TABLE,
            "note": "手算表在**脚本注释里由人算出**（`n=2,H=4`），脚本只负责比对 ⇒ 判据不是自证"}


def gate_frame_uniqueness(res: dict) -> dict:
    """G2：**每个绝对帧最多一行 `activated`**（附录一 :115「每个绝对帧只采纳一个来源」）。"""
    from collections import Counter
    act_rows = [r for r in res["frame_facts"] if r["execution_status"] == "activated"]
    cnt = Counter(r["abs_frame"] for r in act_rows)
    dup = {k: v for k, v in cnt.items() if v > 1}
    na = [r for r in res["frame_facts"] if r["execution_status"] == "not_activated"]
    return {"ok": not dup, "duplicated_abs_frames": dup, "n_activated_rows": len(act_rows),
            "n_not_activated_rows": len(na),
            "expected_not_activated_rows": "每代 |C|+|D| = 2+0，共 4 代 ⇒ 8",
            "rule": "activated 行 = 权威；not_activated 行 = 逐提案记账（可同帧多行，见模块 docstring）"}


def gate_cd_never_activated(res: dict) -> dict:
    """G3：C 段与 D 段的索引**永不**出现为 activated（附录二 §1：当前 proposal 的前 n 项不产生物理动作）。"""
    bad = []
    for r in res["frame_facts"]:
        if r["execution_status"] != "activated":
            continue
        idx = r["chunk_index"]
        gen = r["lease_generation"]
        if idx is None:
            continue
        # 该帧的 owner 代际 = gen；E 段 = [n, 2n) = [2,4)
        if not (2 <= idx < 4):
            bad.append({"abs_frame": r["abs_frame"], "gen": gen, "chunk_index": idx})
    return {"ok": not bad, "activated_outside_E": bad, "E_segment_for_stub": "[2,4)"}


def gate_vocabularies(res: dict) -> dict:
    """G4：两套词表都不许新造值；账本 kind ∈ ledger.EVENT_KINDS、契约 kind ∈ contracts.EVENT_KINDS。"""
    bad_c = sorted({k for k in res["contract_event_kinds"] if k not in CONTRACT_KINDS})
    bad_l = sorted({k for k in res["schedule_event_kinds"] if k not in LEDGER_KINDS})
    bad_s = sorted({r["source"] for r in res["frame_facts"] if r["source"] not in FRAME_SOURCES})
    bad_e = sorted({r["execution_status"] for r in res["frame_facts"] if r["execution_status"] not in EXECUTION_STATUS})
    ok = not (bad_c or bad_l or bad_s or bad_e)
    return {"ok": ok, "bad_contract_kinds": bad_c, "bad_ledger_kinds": bad_l,
            "bad_sources": bad_s, "bad_execution_status": bad_e,
            "note": "契约 7 类 kind（contracts.py:10）+ 账本 kind（ledger.py:31）；**不新增 kind**（裁定 65-6）"}


def gate_three_phase(res: dict) -> dict:
    """G5：requested → accepted → committed **分别记录**（附录一 :375），且顺序正确、每代各一条。"""
    kinds = res["contract_event_kinds"]
    seq = [k for k in kinds if k in ("requested", "accepted", "committed")]
    ok = True
    reasons = []
    for i in range(0, len(seq) - 2, 3):
        if seq[i:i + 3] != ["requested", "accepted", "committed"]:
            ok = False
            reasons.append(f"位置 {i} 的三元组是 {seq[i:i+3]}")
    n_req = kinds.count("requested")
    if n_req != res["n_requests"]:
        ok = False
        reasons.append(f"requested {n_req} != 请求数 {res['n_requests']}")
    for k in ("request_received", "request_admitted", "result_committed"):
        if res["schedule_event_kinds"].count(k) != res["n_requests"]:
            ok = False
            reasons.append(f"账本事件 {k} 数量 {res['schedule_event_kinds'].count(k)} != {res['n_requests']}")
    return {"ok": ok, "reasons": reasons, "n_requests": res["n_requests"],
            "contract_triple_count": {"requested": n_req, "accepted": kinds.count("accepted"),
                                      "committed": kinds.count("committed")}}


def gate_deadline_units(res: dict) -> dict:
    """G6：`deadline` 是**绝对帧 int**，且 `deadline_s = n·dt` 同时可核（S4 草案 §3.4 的静默错点）。"""
    chunks = [e for e in res["frame_facts"] if e.get("request_id")]
    evs = [e for e in res["schedule_event_kinds"]]
    dl = [e for e in res.get("deadline_pairs", [])]
    ok = bool(dl) and all(d["deadline_frame"] == d["created_at_frame"] + d["n_replan"]
                          and abs(d["deadline_s"] - d["n_replan"] * d["dt_s"]) < 1e-12
                          and isinstance(d["deadline_frame"], int) for d in dl)
    return {"ok": ok, "deadline_pairs": dl,
            "why": "若把秒填进 int 字段（0.068→0）⇒ 每帧都判 deadline miss、全部 expired，而日志看起来正常"}


def gate_late_policy(res_slow: dict) -> dict:
    """G7（用**慢推理变异体**的结果）：迟到 ⇒ `expired` 事件 + 迟到帧**不得**被写成 policy/activated（裁定 65-3③）。"""
    kinds = res_slow["contract_event_kinds"]
    n_expired = kinds.count("expired")
    late_gens = {r["generation"] for r in res_slow["late_records"]}
    bad = [r for r in res_slow["frame_facts"]
           if r["execution_status"] == "activated" and r["source"] == "policy"
           and r["lease_generation"] in late_gens]
    hold_frames = [r for r in res_slow["frame_facts"] if r["source"] == "hold"]
    ok = (n_expired > 0 and not bad and len(hold_frames) > 0
          and "hold_start" in res_slow["schedule_event_kinds"])
    return {"ok": ok, "n_expired_events": n_expired, "late_generations": sorted(late_gens),
            "late_frames_marked_as_policy_activated": bad,
            "n_hold_frames": len(hold_frames),
            "hold_start_emitted": "hold_start" in res_slow["schedule_event_kinds"],
            "rule": "异常事实保留、不重标成\"准时\"（附录一 :111）；`late_choice` 三态必须记（裁定 65-3①）"}


def gate_stats_guard(res_none: dict, res_ok: dict) -> dict:
    """G8：`stats_version="NONE"` ⇒ **硬隔离**（td/bc 都 False + 原因 + 账本事件）；有 stats ⇒ 不隔离。"""
    tv = res_none["training_view"] or {}
    ok_none = (bool(res_none["isolation_reasons"]) and tv.get("td_eligible") is False
               and tv.get("bc_eligible") is False
               and "verdict_identity_absent" in res_none["schedule_event_kinds"])
    tv2 = res_ok["training_view"] or {}
    ok_ok = (not any("stats_version" in r for r in res_ok["isolation_reasons"])
             and tv2.get("bc_eligible") is True)
    return {"ok": bool(ok_none and ok_ok),
            "none_case": {"isolation_reasons": res_none["isolation_reasons"],
                          "td_eligible": tv.get("td_eligible"), "bc_eligible": tv.get("bc_eligible"),
                          "verdict_identity_absent_emitted": "verdict_identity_absent" in res_none["schedule_event_kinds"]},
            "with_stats_case": {"isolation_reasons": res_ok["isolation_reasons"], "bc_eligible": tv2.get("bc_eligible")},
            "why": "G3 的 0/20 根因就是 `features={}` 静默 pass-through ⇒ 不许再让它静默通过（S4 草案 §3.1 的牙）"}


def gate_h_ge_2n() -> dict:
    """G9：`H < 2n` 必须**拒绝构造**（附录一 :103；π₀.₅ 出厂 n=H=50 就是不合规的那个）。"""
    env = StubEnv()
    pol = StubPolicy()
    pol.chunk_size = 4
    try:
        VR.ChunkedVlaRuntime(pol, env, episode_id="x", goal_id="g", n_replan=4)
        return {"ok": False, "raised": None, "why": "H=4 < 2n=8 却没报错 ⇒ 闸无牙"}
    except VR.VlaRuntimeError as exc:
        return {"ok": True, "raised": str(exc)[:160]}


def gate_version_switch(mutate: bool = True) -> dict:
    """G10：chunk 内**换 policy_version** 必须报错（附录一 :279）。

    `mutate=False` 只给变异自检用（造一个"没换版本"的对照，证明这道闸确实对报错敏感）。
    """
    res = run_stub_case(n_frames=4, mutate_version=mutate)
    ok = bool(res["error"]) and "279" in (res["error"] or "") or ("policy_version" in (res["error"] or ""))
    return {"ok": bool(res["error"]), "error": res["error"],
            "rule": "不得在一个正在执行的 chunk 内悄悄换模型或 normalizer"}


def gate_vocab_mutation() -> dict:
    """G11：往 `_frame` 塞一个词表外的 source/status 必须报错（不许新造值）。"""
    env = StubEnv()
    pol = StubPolicy(); pol.chunk_size = 4
    rt = VR.ChunkedVlaRuntime(pol, env, episode_id="x", goal_id="g", n_replan=2)
    errs = {}
    for kw, val in (("source", "teleport"), ("execution_status", "mostly_activated")):
        try:
            rt._frame(abs_frame=0, **{kw: val}, **{"source" if kw != "source" else "execution_status": "policy",
                                                    "request_id": None, "chunk_id": None, "chunk_index": None,
                                                    "lease_generation": 0, "proposed_action": None, "a_rl": None,
                                                    "driver_command": None, "measured_state": None})
            errs[kw] = "未报错 ⇒ 闸无牙"
        except VR.VlaRuntimeError as exc:
            errs[kw] = f"raised: {str(exc)[:90]}"
    return {"ok": all(str(v).startswith("raised") for v in errs.values()), "detail": errs}


def gate_rep_version_and_caliber(res: dict) -> dict:
    """G12：`late_policy` 进 representation_version（裁定 65-3②）+ 四条强制 manifest 字段（裁定 65-2）。"""
    rv = res["representation_version"]
    # 裁定 83§5② 硬约束②：`timeout_bc=kept_flagged` **必须**进版本串（`timeout_td=` 一并核）
    need_rv = ["late=hold", "n_replan=2", "H=4", "stats=", "shim=stub_shim_1234", "render=",
               "timeout_td=isolated", "timeout_bc=kept_flagged"]
    miss_rv = [x for x in need_rv if x not in rv]
    mc = res["manifest_caliber"]
    need_mc = {"control_hz": 29.411765, "max_episode_steps": 300, "episode_horizon_s": 10.2,
               "published_gym_aloha_caliber": VR.PUBLISHED_GYM_ALOHA_CALIBER}
    miss_mc = {k: (mc.get(k), v) for k, v in need_mc.items() if mc.get(k) != v}
    ok = not miss_rv and not miss_mc and bool(mc.get("not_comparable_horizon"))
    return {"ok": ok, "representation_version": rv, "missing_in_rep_version": miss_rv,
            "manifest_mismatch": miss_mc,
            "not_comparable_horizon_present": bool(mc.get("not_comparable_horizon"))}


def gate_prime_modes(res_hold: dict, res_first: dict) -> dict:
    """G13：`prime_mode` 两案必须**行为不同**（否则这个开关是装饰品）。"""
    h = [s["source"] for s in res_hold["steps"][:2]]
    f = [s["source"] for s in res_first["steps"][:2]]
    return {"ok": h != f, "prime_hold_first_two_frames": h, "prime_first_chunk_first_two_frames": f,
            "status": ("裁定 83§5① **已裁 `prime_mode=hold`**（进 `representation_version`）；"
                       "本闸守的是「这个开关不是装饰品」——两案行为必须不同，否则裁定无从落地")}


def gate_timeout_scope(res_timeout: dict, res_clean: dict) -> dict:
    """G18：裁定 83§5② `timeout_isolation_scope=td_only` 的三条硬约束（**机器判，不靠文书**）。

    - **TD 侧隔离**：timeout 局 `td_eligible=False`（截断本该 bootstrap、不是终止）；
    - **BC 侧保留但打标**：`bc_eligible=True` **且** `truncated_by_timelimit=True`、`bc_kept_flagged=True`；
    - **版本串**：`representation_version` 含 `timeout_bc=kept_flagged` + `timeout_td=isolated`；
    - **干净参照**（`terminal_kind=none`）：`truncated_by_timelimit=False`、`bc_kept_flagged=False`，
      且 td/bc **都** eligible ⇒ 证明"BC 保留"不是把隔离整体关掉（滑向 `neither` 会让这条红）；
    - **两个 validator 必须有牙**（裁定 83.1 输入级变异体）+ **绿见证**（裁定 83.2）。
    """
    tv = res_timeout["training_view"] or {}
    ex = res_timeout.get("bc_record_extras") or {}
    tv2 = res_clean["training_view"] or {}
    ex2 = res_clean.get("bc_record_extras") or {}
    rv = res_timeout["representation_version"]
    checks = {
        "timeout_terminal_kind": tv.get("terminal_kind") == "timeout",
        "td_isolated": tv.get("td_eligible") is False,
        "bc_kept": tv.get("bc_eligible") is True,
        "flag_present": ex.get("truncated_by_timelimit") is True,
        "bc_kept_flagged": ex.get("bc_kept_flagged") is True,
        "scope_is_td_only": ex.get("timeout_isolation_scope") == "td_only",
        "rep_version_timeout_bc": "timeout_bc=kept_flagged" in rv,
        "rep_version_timeout_td": "timeout_td=isolated" in rv,
        "clean_not_flagged": (ex2.get("truncated_by_timelimit") is False
                              and ex2.get("bc_kept_flagged") is False),
        "clean_both_eligible": (tv2.get("td_eligible") is True and tv2.get("bc_eligible") is True),
    }
    teeth = {}
    # 硬约束③的牙：把 truncated 当 terminal / 成功 ⇒ 必须抛
    for name, bad_rec in (
            ("truncated_as_terminated", {"terminal_kind": "timeout", "truncated_by_timelimit": True,
                                         "terminated": True}),
            ("truncated_as_success_kind", {"terminal_kind": "success", "truncated_by_timelimit": True}),
            ("truncated_as_done", {"terminal_kind": "timeout", "truncated_by_timelimit": True,
                                   "done": True}),
            ("truncated_as_is_terminal", {"terminal_kind": "timeout", "truncated_by_timelimit": True,
                                          "is_terminal": True}),
    ):
        try:
            VR.validate_truncation_not_terminal(bad_rec)
            teeth[name] = "no_raise"
        except VR.VlaRuntimeError:
            teeth[name] = "raised"
    # 硬约束①的牙：BC 记录缺标 / 标成 False ⇒ 必须抛
    for name, bad_rec in (("flag_missing", {"terminal_kind": "timeout"}),
                          ("flag_false", {"terminal_kind": "timeout", "truncated_by_timelimit": False}),
                          ("flag_none", {"terminal_kind": "timeout", "truncated_by_timelimit": None})):
        try:
            VR.validate_bc_timeout_record(bad_rec)
            teeth[name] = "no_raise"
        except VR.VlaRuntimeError:
            teeth[name] = "raised"
    # 绿见证（裁定 83.2 `green_witness_required`）：合规记录两个 validator 都不许抛，
    # 且**非 timeout 记录缺标也不该抛**（否则这条牙是"凡记录必抛"的单向装饰品）
    try:
        VR.validate_bc_timeout_record(dict(ex))
        VR.validate_truncation_not_terminal(dict(ex))
        VR.validate_bc_timeout_record({"terminal_kind": "none"})
        teeth["green_witness_valid_records"] = "passed"
    except VR.VlaRuntimeError as exc:
        teeth["green_witness_valid_records"] = f"raised: {exc}"
    red_teeth = {k: v for k, v in teeth.items() if k != "green_witness_valid_records"}
    ok = (all(checks.values()) and all(v == "raised" for v in red_teeth.values())
          and teeth["green_witness_valid_records"] == "passed")
    return {"ok": bool(ok), "checks": checks, "validator_teeth": teeth,
            "n_red_teeth": len(red_teeth), "representation_version": rv,
            "timeout_bc_record_extras": ex, "clean_bc_record_extras": ex2,
            "ruling": VR.TIMEOUT_RULING, "v4_basis": VR.TIMEOUT_V4_BASIS,
            "why": ("`td_only` 把 BC 数据放回来了；放回来的数据若不带 `truncated_by_timelimit`，"
                    "下游就会把 10.2 s 处被剪断的局当完整经验用 ⇒ 这条闸守的是「保留但打标」四个字")}


def gate_vision_guard(res_novision: dict, res_ok: dict) -> dict:
    """G16：`obs.images={}` ⇒ **硬隔离**（td/bc False + 原因 + 账本事件）；键齐全 ⇒ 不因视觉被隔离。

    牙的来源：G3 的 `0/20` 根因是 `normalizer_processor.config.features={}` 静默 pass-through。
    同一族事故在 S4 的形式就是「images 空映射 ⇒ 悄悄退化成状态输入」——任务书明令 A2 不得自行退化，
    所以这条必须是**机器强制**，不能只写在文档里。事件 kind 复用既有词表（不新造，裁定 65-6）。
    """
    reasons = res_novision["isolation_reasons"]
    tv = res_novision["training_view"] or {}
    kinds = res_novision["schedule_event_kinds"]
    fired = (any(str(r).startswith("vision_channel_absent") for r in reasons)
             and tv.get("td_eligible") is False and tv.get("bc_eligible") is False
             and "verdict_identity_absent" in kinds)
    clean = not any("vision_channel_absent" in str(r) for r in res_ok["isolation_reasons"])
    vocab_ok = all(k in LEDGER_KINDS for k in kinds)
    return {"ok": bool(fired and clean and vocab_ok),
            "novision_case": {"isolation_reasons": reasons, "td_eligible": tv.get("td_eligible"),
                              "bc_eligible": tv.get("bc_eligible"),
                              "verdict_identity_absent_emitted": "verdict_identity_absent" in kinds},
            "with_images_case_isolated_for_vision": not clean,
            "no_new_event_kind_invented": vocab_ok,
            "why": "空图像通道静默通过 = G3 0/20 的同型根因；S4a 把它变成硬失败"}


def gate_ledger_roundtrip(res: dict) -> dict:
    """G14：写进 SQLite 的行必须能被读回来，且计数与内存侧一致（防"只写内存、账本空转"）。"""
    led = res.get("ledger")
    if not led:
        return {"ok": False, "reason": "没有 ledger 结果"}
    # 内存侧事件数：产物里 schedule_event_kinds 与 rt.schedule_events 是 1:1 派生（本文件 :361/:667）
    n_ev_mem = len(res["schedule_events"]) if "schedule_events" in res else len(res["schedule_event_kinds"])
    ok = (led["n_frames_rows"] == len(res["frame_facts"]) and led["n_event_rows"] == n_ev_mem)
    return {"ok": ok, "ledger": led, "in_memory": {"frames": len(res["frame_facts"]),
                                                   "events": n_ev_mem},
            "memory_event_count_source": ("schedule_events" if "schedule_events" in res
                                          else "schedule_event_kinds（1:1 派生）")}



def gate_async_minimal_evidence(res_stub: dict, res_real: dict | None) -> dict:
    """G17（裁定 75.5 / 75.4）：**S4a 骨架必须含**异步最小证据字段，且 34 ms/步是**软约束**。

    75.5 的四项：① 队列不枯竭（`queue_drain_events`）② `wall_ms_per_ctrl_step` 与
    `amortized_inference_ms` **分列** ③ 负载对 ④ **运行时** cotenant 采样。
    75.4：`budget_fraction > 1` **不得判硬失败/红** ⇒ 本闸**故意不拿它当判据**，
    只查 `overload_flag` 存在且是 bool、`budget_verdict` 写明是软约束。
    """
    need = ["caliber", "wall_ms_per_ctrl_step", "amortized_inference_ms_per_ctrl_step",
            "env_step_ms_per_ctrl_step", "queue_drain_count", "queue_drain_events",
            "queue_never_drained", "cotenant_samples", "cotenant_collected_at_run_time",
            "overload_flag", "budget_fraction", "budget_verdict",
            "episode_sim_seconds_covered", "realtime_closed_loop_claim", "per_step_budget_ms"]
    per_case = {}
    ok = True
    for name, res, need_cotenant in (("stub_main", res_stub, False), ("real_env", res_real, True)):
        if res is None:
            per_case[name] = {"skipped": "本臂未跑"}
            continue
        tr = res.get("timing_report") or {}
        missing = [k for k in need if k not in tr]
        separate = (isinstance(tr.get("wall_ms_per_ctrl_step"), (int, float))
                    and isinstance(tr.get("amortized_inference_ms_per_ctrl_step"), (int, float)))
        no_claim = tr.get("realtime_closed_loop_claim") is False
        soft = (isinstance(tr.get("overload_flag"), bool)
                and "soft_constraint" in str(tr.get("budget_verdict", "")))
        n_frames = (res.get("n_frames_done") if "n_frames_done" in res else len(res.get("steps", [])))
        dt = 0.034
        seconds_ok = abs(float(tr.get("episode_sim_seconds_covered", -1)) - n_frames * dt) < 1e-6
        cot_ok = (tr.get("cotenant_collected_at_run_time") is True) if need_cotenant else True
        cot_runtime_honest = all(sm.get("collected_at_run_time") is True
                                 and sm.get("attribution_strength") != "confirmed"
                                 for sm in (tr.get("cotenant_samples") or []))
        case_ok = bool(not missing and separate and no_claim and soft and seconds_ok and cot_ok
                       and cot_runtime_honest)
        ok = ok and case_ok
        per_case[name] = {"ok": case_ok, "missing_fields": missing,
                          "wall_and_inference_separately_listed": separate,
                          "realtime_closed_loop_claim": tr.get("realtime_closed_loop_claim"),
                          "overload_flag": tr.get("overload_flag"),
                          "budget_fraction": tr.get("budget_fraction"),
                          "budget_fraction_gt_1_is_NOT_a_red_here": "裁定 75.4：软约束",
                          "episode_sim_seconds_covered_ok": seconds_ok,
                          "episode_sim_seconds_covered": tr.get("episode_sim_seconds_covered"),
                          "queue_drain_count": tr.get("queue_drain_count"),
                          "queue_never_drained": tr.get("queue_never_drained"),
                          "cotenant_samples_n": len(tr.get("cotenant_samples") or []),
                          "cotenant_collected_at_run_time": tr.get("cotenant_collected_at_run_time"),
                          "cotenant_required_for_this_case": need_cotenant,
                          "attribution_never_claimed_confirmed": cot_runtime_honest,
                          "caliber": tr.get("caliber")}
    return {"ok": ok, "cases": per_case,
            "rulings": ["75.5（异步最小证据四项 + 禁止声称实时闭环）", "75.4（34 ms/步 = 软约束）",
                        "76.3（cotenant 必须运行时采）", "76.1（归因不得写 confirmed）"]}


# ─────────────────── 变异自检：逐闸证明「有牙」（裁定 71/72 的自检纪律）───────────────────
def mutation_self_test(res: dict) -> dict:
    """对**产物**做一处具体篡改、或对 runtime 做一处放宽，闸必须变红。

    为什么必须有这一步：每条闸的 docstring 都写着「要能被具体篡改打红」，
    但**没有变异测试，那句话就只是注释**。裁定 72 要求自检走真实取数路径 ⇒
    这里篡改的是真实产物对象（深拷贝），跑的是真实闸函数。
    """
    import copy
    out = {}

    def rec(name, baseline, mutant, note=""):
        out[name] = {"baseline_ok": bool(baseline.get("ok")), "mutant_ok": bool(mutant.get("ok")),
                     "teeth": bool(baseline.get("ok")) and not bool(mutant.get("ok")),
                     "tamper": note}

    R = res
    def cp(k):
        return copy.deepcopy(R[k])

    # G1：改一个动作数值（手算表对不上）
    m = cp("stub_main"); m["steps"][2]["action"] = [999.0, -999.0]
    rec("G1", gate_hand_table(R["stub_main"]), gate_hand_table(m), "steps[2].action → [999,-999]")

    # G2：同一绝对帧塞第二行 activated
    m = cp("stub_main")
    act = next(r for r in m["frame_facts"] if r["execution_status"] == "activated")
    m["frame_facts"].append(dict(act))
    rec("G2", gate_frame_uniqueness(R["stub_main"]), gate_frame_uniqueness(m), "复制一行 activated（同帧两来源）")

    # G3：把某行 activated 的索引改到 C 段
    m = cp("stub_main")
    for r in m["frame_facts"]:
        if r["execution_status"] == "activated" and r["chunk_index"] is not None:
            r["chunk_index"] = 0
            break
    rec("G3", gate_cd_never_activated(R["stub_main"]), gate_cd_never_activated(m), "activated 的 chunk_index → 0（C 段）")

    # G4：塞一个词表外的契约 kind
    m = cp("stub_main"); m["contract_event_kinds"].append("teleported")
    rec("G4", gate_vocabularies(R["stub_main"]), gate_vocabularies(m), "契约 kind 里加 'teleported'")

    # G5：抽掉一条 accepted（三阶段不再分别记录）
    m = cp("stub_main"); m["contract_event_kinds"].remove("accepted")
    rec("G5", gate_three_phase(R["stub_main"]), gate_three_phase(m), "删一条 'accepted'")

    # G6：把 deadline 的绝对帧改错一位（模拟"秒填进 int 字段"那族错）
    m = cp("stub_main"); m["deadline_pairs"][0]["deadline_frame"] += 1
    rec("G6", gate_deadline_units(R["stub_main"]), gate_deadline_units(m), "deadline_pairs[0].deadline_frame += 1")

    # G7：把迟到事实抹掉（expired 事件消失）
    m = cp("stub_late_mutant"); m["contract_event_kinds"] = [k for k in m["contract_event_kinds"] if k != "expired"]
    rec("G7", gate_late_policy(R["stub_late_mutant"]), gate_late_policy(m), "删掉全部 'expired' 事件")

    # G8：把 NONE 案例的隔离原因清空（= 静默放行）
    m = cp("stub_stats_none"); m["isolation_reasons"] = []
    rec("G8", gate_stats_guard(R["stub_stats_none"], R["stub_clean_reference"]),
        gate_stats_guard(m, R["stub_clean_reference"]), "stats=NONE 案例的 isolation_reasons 清空")

    # G9：把 runtime 换成"构造总是成功"的放宽版
    saved = VR.ChunkedVlaRuntime
    try:
        VR.ChunkedVlaRuntime = lambda *a, **kw: object()
        mut9 = gate_h_ge_2n()
    finally:
        VR.ChunkedVlaRuntime = saved
    rec("G9", gate_h_ge_2n(), mut9, "放宽 runtime：H<2n 也放行")

    # G10：不换版本（对照）⇒ 没有报错可抓
    rec("G10", gate_version_switch(True), gate_version_switch(False), "policy 不再中途换版本")

    # G11：把 _frame 换成不校验词表的放宽版
    saved_f = VR.ChunkedVlaRuntime._frame
    try:
        VR.ChunkedVlaRuntime._frame = lambda self, **kw: None
        mut11 = gate_vocab_mutation()
    finally:
        VR.ChunkedVlaRuntime._frame = saved_f
    rec("G11", gate_vocab_mutation(), mut11, "放宽 _frame：词表外值也不报错")

    # G12：改口径字段
    m = cp("stub_main"); m["manifest_caliber"]["max_episode_steps"] = 176
    rec("G12", gate_rep_version_and_caliber(R["stub_main"]), gate_rep_version_and_caliber(m),
        "max_episode_steps → 176（裁定 65-2 已作废的那个数）")

    # G13：两种 prime_mode 喂同一份结果（开关变装饰品）
    rec("G13", gate_prime_modes(R["stub_main"], R["stub_prime_first_chunk"]),
        gate_prime_modes(R["stub_main"], cp("stub_main")), "prime 两案喂同一份产物")

    # G18（裁定 83§5② `timeout_isolation_scope=td_only`）：四种篡改，逐一证明这条闸有牙（裁定 83.1）。
    # (a) 把 BC 侧的标记摘掉 = 「保留但无痕」⇒ 下游会把 10.2 s 处被剪断的局当完整经验
    m = cp("stub_main"); m["bc_record_extras"] = dict(m["bc_record_extras"])
    m["bc_record_extras"]["truncated_by_timelimit"] = False
    rec("G18a", gate_timeout_scope(R["stub_main"], R["stub_clean_reference"]),
        gate_timeout_scope(m, R["stub_clean_reference"]),
        "bc_record_extras.truncated_by_timelimit → False（保留但无痕）")
    # (b) 版本串里的 token 改回 isolated = 版本串与常量脱节、对下游撒谎
    m = cp("stub_main")
    m["representation_version"] = m["representation_version"].replace("timeout_bc=kept_flagged",
                                                                       "timeout_bc=isolated")
    rec("G18b", gate_timeout_scope(R["stub_main"], R["stub_clean_reference"]),
        gate_timeout_scope(m, R["stub_clean_reference"]),
        "representation_version 的 timeout_bc=kept_flagged → isolated（版本串撒谎）")
    # (c) 把 TD 侧的隔离也关掉 = 滑向 `neither`（截断被当正常收尾、target 不再 bootstrap）
    m = cp("stub_main"); m["training_view"] = dict(m["training_view"])
    m["training_view"]["td_eligible"] = True
    rec("G18c", gate_timeout_scope(R["stub_main"], R["stub_clean_reference"]),
        gate_timeout_scope(m, R["stub_clean_reference"]),
        "timeout 局 td_eligible → True（滑向 neither：截断被当正常收尾）")
    # (d) 给干净参照也打上截断标 = 标记不再区分 timeout / 非 timeout，字段沦为装饰品
    m2 = cp("stub_clean_reference"); m2["bc_record_extras"] = dict(m2["bc_record_extras"])
    m2["bc_record_extras"]["truncated_by_timelimit"] = True
    m2["bc_record_extras"]["bc_kept_flagged"] = True
    rec("G18d", gate_timeout_scope(R["stub_main"], R["stub_clean_reference"]),
        gate_timeout_scope(R["stub_main"], m2),
        "干净参照（terminal_kind=none）也被打 truncated_by_timelimit=True（标记失去区分力）")

    # G14：账本行数与内存侧脱钩
    m = cp("stub_main"); m["ledger"]["n_frames_rows"] += 1
    rec("G14", gate_ledger_roundtrip(R["stub_main"]), gate_ledger_roundtrip(m), "账本 frame 行数 +1")

    # G16：把视觉缺失的隔离原因清空（= 允许静默退化成状态输入）
    m = cp("stub_vision_absent_mutant"); m["isolation_reasons"] = []
    rec("G16", gate_vision_guard(R["stub_vision_absent_mutant"], R["stub_clean_reference"]),
        gate_vision_guard(m, R["stub_clean_reference"]), "images={} 案例的 isolation_reasons 清空")

    # G15（只在跑了真实 env 臂时）：改一帧的来源
    if "real_env" in R:
        # 篡改口径字段（把 control_hz 写成生态公布值 50.0）⇒ caliber_ok 变 False。
        # 这正是裁定 58.3 / 65-2 禁止的那种「跨口径污染」，所以拿它当 G15 的牙最合适。
        m = cp("real_env"); m["manifest_caliber"]["control_hz"] = 50.0
        rec("G15", gate_real_env(R["real_env"]), gate_real_env(m),
            "manifest_caliber.control_hz → 50.0（把 50 Hz 生态口径混进 29.4118 Hz 主线）")

    # G17：把「实时闭环」声称塞回去（裁定 75.5 明禁）⇒ 必须红
    m = cp("stub_main"); m["timing_report"] = dict(m["timing_report"]); m["timing_report"]["realtime_closed_loop_claim"] = True
    rec("G17a", gate_async_minimal_evidence(R["stub_main"], R.get("real_env")),
        gate_async_minimal_evidence(m, R.get("real_env")),
        "timing_report.realtime_closed_loop_claim → True（异步未实测就声称实时闭环）")
    # G17 的第二处牙：把摊薄推理与墙钟合并成一个数（= 不再"分列"）⇒ 必须红
    m = cp("stub_main"); m["timing_report"] = dict(m["timing_report"])
    m["timing_report"].pop("amortized_inference_ms_per_ctrl_step", None)
    rec("G17b", gate_async_minimal_evidence(R["stub_main"], R.get("real_env")),
        gate_async_minimal_evidence(m, R.get("real_env")),
        "删掉 amortized_inference_ms_per_ctrl_step（75.5 要求与墙钟**分列**）")
    # G17 的第三处牙：把 cotenant 采样标成事后重建 ⇒ 真实 env 臂必须红（裁定 76.3）
    if "real_env" in R:
        m = cp("real_env"); m["timing_report"] = dict(m["timing_report"])
        m["timing_report"]["cotenant_samples"] = []
        m["timing_report"]["cotenant_collected_at_run_time"] = False
        rec("G17c", gate_async_minimal_evidence(R["stub_main"], R["real_env"]),
            gate_async_minimal_evidence(R["stub_main"], m),
            "真实 env 臂的 cotenant 采样清空（= 退回事后重建，裁定 76.3 红线）")

    n_teeth = sum(1 for v in out.values() if v["teeth"])
    return {"gates_tested": len(out), "gates_with_teeth": n_teeth,
            "all_have_teeth": n_teeth == len(out), "detail": out}


# ───────────────────────── 真实 env 臂（主线 n=25 / H=50）─────────────────────
def run_real_case(args, n_frames: int = 55) -> dict:
    adapter = GymAlohaAdapter(image_size=args.image_size, render=not args.no_render)
    pol = RealEnvStubPolicy(adapter, n_replan=VR.MAINLINE_N_REPLAN, stats_version=VR.STATS_VERSION_ABSENT)
    ledger_path = pathlib.Path(args.out_dir) / "ledger_real_env.sqlite"
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    if ledger_path.exists():
        bak = ledger_path.with_suffix(f".before_{datetime.now().strftime('%H%M%S')}.sqlite")
        ledger_path.rename(bak)          # 不用 rm；旧账本改名留档（裁定 35.1）
    ledger = FactLedger(ledger_path)
    rt = VR.ChunkedVlaRuntime(pol, adapter, episode_id="a2-s4a-real-ep0",
                              goal_id="transfer_cube_right_to_left", epoch=0,
                              n_replan=VR.MAINLINE_N_REPLAN, dt_s=adapter.dt_s,
                              ledger=ledger, shim_sha256_12=adapter.shim.shim_sha256_12(),
                              # 裁定 76.3 红线：**运行时**采共租证据，不再事后重建
                              cotenant_sampler=make_cotenant_sampler(),
                              cotenant_sample_interval_s=2.0)
    load0 = load_snapshot()
    t0 = time.perf_counter()
    obs = rt.reset(seed=args.seed)
    steps = []
    ended = "none"
    for _ in range(n_frames):
        r = rt.step()
        steps.append({"abs_frame": r.abs_frame, "source": r.source,
                      "execution_status": r.execution_status, "chunk_index": r.chunk_index,
                      "lease_generation": r.lease_generation, "late_choice": r.late_choice,
                      "reward": r.reward, "action_head": [round(float(x), 4) for x in list(r.action)[:3]]})
        if r.truncated:
            ended = "timeout"
            break
        if r.terminated:
            ended = "terminated"
            break
    wall = time.perf_counter() - t0
    tv = rt.finalize(ended, reward=0.0)
    load1 = load_snapshot()
    # 手算：n=25 ⇒ 帧 0..24 = prime hold；帧 25..49 = chunk0 的 E（idx=25..49）；帧 50..54 = chunk1 的 E（idx=25..29）
    expected = []
    for f in range(len(steps)):
        if f < 25:
            expected.append((f, "hold", None, None))
        else:
            g = (f // 25) - 1
            expected.append((f, "policy", g, f - g * 25))
    diffs = []
    for (f, src, gen, idx), got in zip(expected, steps):
        if got["abs_frame"] != f or got["source"] != src:
            diffs.append(f"frame {f}: got source={got['source']} want {src}")
        if gen is not None:
            if got["lease_generation"] != gen:
                diffs.append(f"frame {f}: lease_generation {got['lease_generation']} != {gen}")
            if got["chunk_index"] != idx:
                diffs.append(f"frame {f}: chunk_index {got['chunk_index']} != {idx}")
    out = {
        "case": "real_env_gym_aloha",
        "env_id": VR.ENV_ID, "morphology": VR.MORPHOLOGY,
        "live_timing": adapter.live, "shim_sha256_12": adapter.shim.shim_sha256_12(),
        "representation_version_shim": adapter.shim.REPRESENTATION_VERSION,
        "n_frames_requested": n_frames, "n_frames_done": len(steps), "steps": steps,
        "hand_computed_expectation": {
            "rule": "n=25 ⇒ f<25 prime hold；f≥25 ⇒ gen=(f//25)-1、idx=f-25·gen",
            "first_policy_frame": 25,
            # 显式人算，不用「碰巧对上」的公式：请求发生在槽边界 f=0/25/50 ⇒ 55 帧内 3 次
            "expected_request_frames": [0, 25, 50],
            "expected_requests": 3,
            "expected_frame_owners": "f0-24 hold(prime) / f25-49 gen0 idx25-49 / f50-54 gen1 idx25-29",
            "derivation": ("closed_form_rederivation_by_A2：脚本用闭式 g=(f//25)-1、idx=f-25g 独立重推，"
                           "**不调用 runtime 的槽位代码**；强度低于 stub 侧那张逐格人写的 HAND_TABLE"
                           "（后者是 `hand_written_table`），故此处如实标弱一档，不冒称人算表"),
        },
        "diffs_vs_hand_computation": diffs,
        "n_requests": pol.g,
        "renders_of_3cam_224": adapter.n_renders,
        "wall_s": round(wall, 3),
        "wall_ms_per_ctrl_step": round(wall / max(1, len(steps)) * 1000, 3),
        "per_step_budget_ms": 34.0,
        "budget_fraction": round((wall / max(1, len(steps)) * 1000) / 34.0, 4),
        "budget_fraction_caliber": {
            "render_backend_fact": list(adapter.render_backend()),
            "verdict": ("**这个数字不是主线口径**：本臂 `GL_RENDERER` 事实为 llvmpipe（CPU 软渲染），"
                        "`budget_fraction` 因此必然 >1；它只证明「接线与账目在 CPU 口径下自洽」，"
                        "不得被读成 S4 在主线超预算 3 倍"),
            "mainline_gpu_caliber_crossref": {
                "env_only_egl_nvidia_run2": {"env_step_fps": 65.865,
                                             "artifact": "runs/vla/a2_egl_latency_20260929/latency_mainline_egl_gpu.json"},
                "env_only_egl_nvidia_run1": {"env_step_fps": 30.522, "note": "保守端（裁定 70 规划口径）"},
                "env_only_mesa_llvmpipe": {"env_step_fps": 9.577,
                                           "artifact": "runs/vla/a2_egl_latency_20260929/latency_retro_label_no_prefix.json"},
                "rule": "跨口径数字**不得互搬**（裁定 46.4 / 53.6）；并列时必须各自带 GL_RENDERER 事实与负载对",
            },
            "load_pair": "见 load_before / load_after / nr_throttled_delta（每个吞吐数字成对带负载，纪律要求）",
        },
        "episode_seconds_covered": round(len(steps) * adapter.dt_s, 4),
        "observation_cadence": {
            "renders_of_3cam_224": adapter.n_renders,
            "n_control_frames": len(steps),
            "why_so_few": ("runtime **只在槽边界（发起新请求时）取观测**：55 帧内请求发生在 f=0/25/50，"
                           "加 reset 一次 ⇒ 4 次三相机渲染，A2 侧渲染成本被 1:n 摊薄；"
                           "每控制步的墙钟由 `env.step()` 主导（gym_aloha 在 `pixels_agent_pos` 下自己还会渲染，"
                           "见 `envs/gym_aloha_shim.py` 与 S4 草案 §2.3 的 `_format_raw_obs` 浪费 2 张）"),
            "implication": "S4a 的墙钟不能拿来推「渲染是瓶颈」；那件事已由 a2_egl_latency_remeasure 分口径测过",
        },
        "manifest_caliber": rt.manifest_caliber(),
        "representation_version": rt.representation_version,
        # 裁定 75.5：`wall_ms_per_ctrl_step` 与 `amortized_inference_ms` **分列**；
        # 裁定 75.4：34 ms/步是**软约束** ⇒ `overload_flag` 而不是硬失败
        "timing_report": rt.timing_report(),
        # 同上：ActionEvent / OutcomeEvent 分流（rule_source: harness/ledger.py:457）
        "contract_event_kinds": [k for e in rt.contract_events if (k := getattr(e, "kind", ""))],
        "contract_outcome_event_count": sum(1 for e in rt.contract_events if not getattr(e, "kind", "")),
        "schedule_event_kinds": [e["kind"] for e in rt.schedule_events],
        "frame_facts": rt.frame_facts,
        "deadline_pairs": [{"created_at_frame": c.created_at_frame, "deadline_frame": c.deadline_frame,
                            "deadline_s": c.deadline_s, "n_replan": c.n_replan, "dt_s": c.dt_s,
                            "chunk_id": c.chunk_id, "inference_wall_s": c.inference_wall_s}
                           for c in rt.chunks.values()],
        "training_view": {"td_eligible": tv.td_eligible, "bc_eligible": tv.bc_eligible,
                          "terminal_kind": tv.terminal_kind, "isolation_reasons": list(tv.isolation_reasons),
                          "execution_mask_nonzero": sum(1 for x in tv.execution_mask if x),
                          "bc_mask_nonzero": sum(1 for x in tv.bc_mask if x)},
        # 裁定 83§5②：BC 溯源字段（真实 env 臂的局绝大多数以 timeout 收尾 ⇒ 这组字段是主战场）
        "bc_record_extras": dict(rt.last_bc_record_extras),
        "isolation_reasons": rt.isolation_reasons,
        "ledger": {"path": str(ledger_path), "n_frames_rows": len(ledger.frames(episode_id="a2-s4a-real-ep0")),
                   "n_event_rows": len(ledger.events(episode_id="a2-s4a-real-ep0")), "stats": ledger.stats()},
        "load_before": load0, "load_after": load1,
        # 裁定 73 的污染判据就地算一遍：**窗内有非本线 GPU 进程**，或 **loadavg_1m 高出基线 ≥5** ⇒ contaminated
        "cotenant_summary": _cotenant_summary(rt.timing_report().get("cotenant_samples") or [], load0),
        "nr_throttled_delta": (load1.get("cpu_stat", {}).get("nr_throttled", 0)
                               - load0.get("cpu_stat", {}).get("nr_throttled", 0)),
        "render_backend": list(adapter.render_backend()),
        "ruling_82_5_render_rate_caveat": {
            "text": ("裁定 82.5：egl/GPU 下 wrist 相机**不逐位可复现**、`raw_first` 臂渲染速率被抬高 "
                     "`inflation_pct=8.3%` ⇒ **渲染速率类**数字必须带此 caveat；**推理延迟类**不受影响（不经 GL）。"
                     "A2 已被 D 免责（`gl_identity_via_mujoco()` 在 `make_env` 之前 = `raw_first`、安全；"
                     "`gl_identity_after_dm_render` 只调 `glGetString` 不建 Renderer ⇒ 亦安全）"),
            "applies_to_this_arm": ("**不适用**：本臂 `GL_RENDERER` 事实 = llvmpipe（CPU 软渲染），"
                                    "而 E 实测 **osmesa/mesa 路径下三相机全部逐位一致** ⇒ 82.5 的非确定性与 "
                                    "8.3% 抬速都是 egl/GPU 光栅化现象，不落在本臂上"),
            "must_follow_any_future_egl_arm": True,
            "affected_fields_if_egl": ["observe_render_ms_per_ctrl_step", "env_step_ms_per_ctrl_step",
                                       "wall_ms_per_ctrl_step"],
            "unaffected_fields": ["amortized_inference_ms_per_ctrl_step（推理不经 GL）"],
        },
        "pixel_bitwise_criteria_used": False,
        "pixel_bitwise_criteria_note": ("D 在 23:4x §5 要求「S4a 若涉及像素复现判据，按 §2 重定范围执行」⇒ "
                                        "**A2 实查：S4a 的 17 条闸没有任何一条比对像素**"
                                        "（`grep -n 'bitwise|逐位|allclose|array_equal|pixel'` 只命中 "
                                        "`obs_type=\"pixels_agent_pos\""
                                        " 这个 env 配置项与一处文档叙述）；判据全是**状态/来源/代际/索引/账目**层面的，"
                                        "所以该条件指令对 S4a 不生效"),
        "policy_executed": False,
        "capability_claim": False,
        "success_metrics_collected": False,
        "success_rate_column": "not_an_exit_criterion（裁定 65-6③：S4 只取结构与字段证据）",
    }
    ledger.close()
    adapter.close()
    return out


def gate_real_env(res: dict) -> dict:
    diffs = res["diffs_vs_hand_computation"]
    act_rows = [r for r in res["frame_facts"] if r["execution_status"] == "activated"]
    from collections import Counter
    dup = {k: v for k, v in Counter(r["abs_frame"] for r in act_rows).items() if v > 1}
    mc = res["manifest_caliber"]
    caliber_ok = (mc.get("control_hz") == 29.411765 and mc.get("max_episode_steps") == 300
                  and mc.get("episode_horizon_s") == 10.2 and mc.get("n_replan") == 25
                  and mc.get("chunk_size") == 50 and mc.get("h_ge_2n") is True
                  and mc.get("late_policy") == "hold")
    led_ok = (res["ledger"]["n_frames_rows"] == len(res["frame_facts"])
              and res["ledger"]["n_event_rows"] == len(res["schedule_event_kinds"]))
    iso_ok = bool(res["isolation_reasons"]) and res["training_view"]["td_eligible"] is False
    ok = (not diffs and not dup and caliber_ok and led_ok and iso_ok
          and res["live_timing"].get("matches_mainline") is True)
    return {"ok": ok, "diffs_vs_hand_computation": diffs[:8], "duplicated_activated_frames": dup,
            "manifest_caliber_ok": caliber_ok, "ledger_roundtrip_ok": led_ok,
            "stats_isolation_ok": iso_ok,
            "live_timing_matches_mainline": res["live_timing"].get("matches_mainline"),
            "control_hz": res["live_timing"].get("control_hz"),
            "n_frames": res["n_frames_done"], "n_requests": res["n_requests"],
            "renders_of_3cam_224": res["renders_of_3cam_224"],
            "note": ("**真实 env + 主线 n=25/H=50**：帧 0–24 = prime hold、帧 25–49 = chunk0 的 E（idx 25–49）、"
                     "帧 50+ = chunk1 的 E —— 期望值由 A2 用闭式独立重推（**不调用 runtime 的槽位代码**），"
                     "脚本只做比对；强度弱于 stub 侧逐格人写的 HAND_TABLE，详见 "
                     "`cases.real_env.hand_computed_expectation.derivation`"),
            "policy_executed": res["policy_executed"], "capability_claim": res["capability_claim"]}


# ───────────────────────── main ────────────────────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default="runs/vla/a2_s4a_vla_runtime_20260929")
    ap.add_argument("--real-env", action="store_true", help="加跑真实 gym_aloha 臂（主线 n=25/H=50）")
    ap.add_argument("--image-size", type=int, default=224)
    ap.add_argument("--no-render", action="store_true", help="真实 env 臂不渲染（只验接线，最省 CPU）")
    ap.add_argument("--seed", type=int, default=1000)
    ap.add_argument("--n-frames", type=int, default=55)
    args = ap.parse_args()

    out_dir = pathlib.Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    load0 = load_snapshot()

    print("[case] stub 手算表（n=2,H=4,prime=hold）…", flush=True)
    res_main = run_stub_case(n_frames=8, prime_mode="hold", ledger_path=out_dir / "ledger_stub.sqlite")
    print("[case] stub 迟到变异体（推理墙钟 5 s ≫ 槽预算 0.068 s）…", flush=True)
    res_slow = run_stub_case(n_frames=8, slow_factor=5.0)
    print("[case] stub stats_version=NONE（硬隔离）…", flush=True)
    res_none = run_stub_case(n_frames=8, stats_version=VR.STATS_VERSION_ABSENT)
    print("[case] stub prime_mode=first_chunk（对照）…", flush=True)
    res_first = run_stub_case(n_frames=8, prime_mode="first_chunk")
    print("[case] stub 干净参照（有 stats、env 不截断 ⇒ terminal_kind=none）…", flush=True)
    res_clean = run_stub_case(n_frames=8, env_horizon=64)
    print("[case] stub 视觉缺失变异体（images={} ⇒ 必须硬隔离，不许静默退化成状态输入）…", flush=True)
    res_novision = run_stub_case(n_frames=8, env_horizon=64, drop_images=True)

    gates = {
        "G1_hand_table_field_by_field": gate_hand_table(res_main),
        "G2_one_activated_row_per_abs_frame": gate_frame_uniqueness(res_main),
        "G3_C_and_D_never_activated": gate_cd_never_activated(res_main),
        "G4_vocabularies_not_extended": gate_vocabularies(res_main),
        "G5_requested_accepted_committed_separate": gate_three_phase(res_main),
        "G6_deadline_units_are_absolute_frames": gate_deadline_units(res_main),
        "G7_late_policy_hold_never_relabels_activated": gate_late_policy(res_slow),
        "G8_stats_version_NONE_hard_isolation": gate_stats_guard(res_none, res_clean),
        "G9_H_ge_2n_refuses_construction": gate_h_ge_2n(),
        "G10_version_switch_inside_chunk_raises": gate_version_switch(),
        "G11_frame_vocabulary_mutation_raises": gate_vocab_mutation(),
        "G12_rep_version_and_caliber_fields": gate_rep_version_and_caliber(res_main),
        "G13_prime_mode_switch_is_not_decorative": gate_prime_modes(res_main, res_first),
        "G14_ledger_roundtrip_matches_memory": gate_ledger_roundtrip(res_main),
        "G16_vision_channel_absent_hard_isolation": gate_vision_guard(res_novision, res_clean),
        "G18_timeout_scope_td_only_83_5_2": gate_timeout_scope(res_main, res_clean),
    }
    cases = {"stub_main": res_main, "stub_late_mutant": res_slow,
             "stub_stats_none": res_none, "stub_prime_first_chunk": res_first,
             "stub_clean_reference": res_clean, "stub_vision_absent_mutant": res_novision}

    if args.real_env:
        print("[case] 真实 gym_aloha（主线 n=25/H=50，shim DT=0.034）…", flush=True)
        res_real = run_real_case(args, n_frames=args.n_frames)
        cases["real_env"] = res_real
        gates["G15_real_env_hand_computed_mapping"] = gate_real_env(res_real)
    # G17 无论有没有跑真实 env 臂都要判（stub 臂也必须有 75.5 的字段）
    gates["G17_async_minimal_evidence_75_4_75_5"] = gate_async_minimal_evidence(
        res_main, cases.get("real_env"))

    print("[selftest] 变异自检：逐闸做一处具体篡改，证明闸会红…", flush=True)
    mutation = mutation_self_test(cases)

    n_ok = sum(1 for g in gates.values() if g.get("ok"))
    payload = {
        "gate_teeth_mutation_selftest": mutation,
        "probe": "a2_s4a_vla_runtime_verify",
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "generator": "scripts/a2_s4a_vla_runtime_verify.py",
        "generator_sha256_12": sha12(pathlib.Path(__file__).resolve()),
        "target_file": "harness/vla_runtime.py",
        "target_sha256_12": sha12(REPO / "harness/vla_runtime.py"),
        "contracts_py_sha256_12": sha12(REPO / "harness/contracts.py"),
        "contracts_py_modified": False,
        "ledger_py_sha256_12": sha12(REPO / "harness/ledger.py"),
        "frozen_surface_touched": [],
        "args": vars(args),
        "citations_file_identity_triple": CITATIONS,
        "citations_note": "裁定 64：只有行号的引用不可核验 ⇒ 每条都带 (相对路径, sha256-12, 行号)",
        "authoritative_source_for_three_phase": {
            "contract_statement": "appendices/01_接口契约与开发验收.md:375",
            "p0_promotion_basis": "01_开发技术方案.md:347",
            "note": "裁定 64-1：双文件双引用（A2 此前只引附录一，且 §2.4 把 T25 写成 :346，实为 :345 —— 已更正）"},
        "gates": gates,
        "n_gates": len(gates), "n_ok": n_ok, "all_ok": n_ok == len(gates),
        "aggregate_field_semantics": AGGREGATE_FIELD_SEMANTICS,
        # 精确到案例，不用一句全局 True 盖过去（裁定 64/72：不得声称强于实有的证据）
        "hand_table_is_human_computed": {
            "stub_main": ("true_hand_written：HAND_TABLE 是本文件顶部逐格人写的常量"
                          "（含每帧的动作数值与 idx 算式），闸只做比对"),
            "real_env": ("closed_form_rederivation_by_A2：闭式 g=(f//25)-1、idx=f-25g 独立重推，"
                         "**不调用 runtime 的槽位代码**，强度弱于人写表 ⇒ 见 "
                         "cases.real_env.hand_computed_expectation.derivation"),
        },
        "capability_claim": False,
        "success_metrics_collected": False,
        "success_rate_column": "not_an_exit_criterion（裁定 65-6③）",
        "policy_executed": any(c.get("policy_executed") for c in cases.values() if isinstance(c, dict)),
        "gpu_used": False,
        "s4b_not_done": {"what": "四类判定（成功/失败/超时/未知）接 ledger，且必须独立于 reward==4",
                         "blocked_on": "C2 的 harness/env_gym_aloha.py（裁定 62 三条硬约束）"},
        "design_points_open_to_d": res_main["design_points_open_to_d"],
        "load_before": load0, "load_after": load_snapshot(),
        "cases": cases,
    }
    payload["nr_throttled_delta_total"] = (payload["load_after"].get("cpu_stat", {}).get("nr_throttled", 0)
                                           - load0.get("cpu_stat", {}).get("nr_throttled", 0))
    p = out_dir / "s4a_verification.json"
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=1, default=str))
    print(f"[written] {p}", flush=True)
    for k, v in gates.items():
        print(f"  [{'PASS' if v.get('ok') else 'FAIL'}] {k}", flush=True)
        if not v.get("ok"):
            print(f"         {json.dumps({kk: vv for kk, vv in v.items() if kk != 'hand_table'}, ensure_ascii=False, default=str)[:400]}", flush=True)
    print(f"[summary] {n_ok}/{len(gates)} gates PASS", flush=True)
    print(f"[summary] 变异自检 {mutation['gates_with_teeth']}/{mutation['gates_tested']} 条闸有牙"
          f"（all_have_teeth={mutation['all_have_teeth']}）", flush=True)
    bad_teeth = [k for k, v in mutation["detail"].items() if not v["teeth"]]
    if bad_teeth:
        print(f"[summary] **无牙的闸**：{bad_teeth}", flush=True)
    return 0 if (n_ok == len(gates) and mutation["all_have_teeth"]) else 3


if __name__ == "__main__":
    sys.exit(main())
