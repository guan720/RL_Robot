#!/usr/bin/env bash
# 复现本项目环境（阶段 0）。已在本机实测跑通，注释里写清了每个坑。
#
# 用法：
#   bash scripts/setup_env.sh            # 建 venv + 装依赖 + 自检
#   VENV=/root/venvs/rlrobot bash scripts/setup_env.sh
#
# 七个必须知道的点（都是本机实测踩过的）：
#   1. venv 用 --system-site-packages，直接复用 base 里的 torch 2.4.1+cu124（GPU 版）。
#      否则要重下 800MB 级别的 torch，而且很可能装成 CPU 版。
#   2. stable-baselines3 必须钉 <2.8。SB3 2.8+ 要求 torch>=2.8，pip 会去下
#      torch 2.14（554MB）外加一串 nvidia-* CUDA 包（数 GB），并且盖掉 GPU torch。
#      本机代理下载只有 ~240 KB/s，这个坑会浪费一小时以上。
#   3. gymnasium 钉 <1.3 以匹配 SB3 2.7.x。
#   4. opencv-python 钉 <5：不钉的话 pip 会先下 opencv 5.0（74MB）再回溯到 4.14（77MB），
#      在本机代理限速下白等十几分钟。
#   5. mujoco 钉 >=3.3,<3.10：实测 mujoco 3.13.0 + robosuite 1.5.2 会在建环境时
#      `assert get_joint_qpos_addr(...)` 失败；robosuite 官方上限也是 <3.10。本机用 3.9.0 通过。
#   6. numpy 钉 >=2：base env 里 jax 0.10.2 需要 numpy>=2，否则 `import stable_baselines3`
#      直接 AttributeError: StringDType（venv 继承了 base 的包，这个坑很容易踩）。
#   7. 同一个进程里「先用 MuJoCo 建 EGL 渲染上下文，再 import torch/tensorflow」会段错误(exit 139)。
#      本项目脚本各自独立进程，不受影响；env_check.py 里做导入探测时用了子进程隔离。
#   8. **（0929 新增，C 的 ADR-C-006 + D 的 裁定 29.4 §19-B③）安装口径 = lock 优先 + `--no-deps`。**
#      本脚本原先只按**范围 pin** 装（下面那段 `numpy>=2` / `robosuite==1.5.2` …），
#      0929 检修后重装时被解析器判死：`robosuite 1.5.2 → mink==0.0.5 → numpy<2.0.0`，与 `numpy>=2` 冲突
#      ⇒ `ResolutionImpossible`。而 `requirements.lock.txt` 是 9/28 **实际装成并跑通全量回归**的 freeze
#      （`mink==1.2.0` + `numpy==2.4.6` + `robosuite==1.5.2` 三者共存），C 0929 按 lock + `--no-deps`
#      重建后与 9/28 的 lock **逐包相同（28/28）**。
#      口径裁定（C 提出、D 采纳）：**解析器到不了某个组合，不代表那个组合不可用**；
#      lock 是「实际装成什么」的事实源，范围 pin 是「意图」，两者冲突时**以 lock 复现**并把冲突报给 D，
#      而不是就地放宽 pin。范围 pin 只作为 lock 缺失时的回退，并打 WARN。
#   9. **pip 版本必须记进 lock**：C 实测 venv 原装 pip 24.0 → 升到 26.2.1 后解析器更严、
#      会回溯到 `mink 0.0.5`，这正是上面那次 `ResolutionImpossible` 的**直接触发条件**。
#      所以 lock 头部记 `# pip==<version>`，本脚本下次运行时**装回那个版本**，
#      让「解析器行为」本身也可复现（不再无条件 `-U pip`）。
set -euo pipefail

VENV="${VENV:-/root/venvs/rlrobot}"
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# ===========================================================================
# P0-2（D→B 执行单 §2）：`requirements.lock.txt` 的 **freeze 覆写护栏** —— 事前拒绝。
#
# 风险（D 现场发现，可核）：本脚本末尾是 `pip freeze --local > requirements.lock.txt`。
# 0929 起已经**存在一个自足 venv**（`.codex-persist/envs/rlrobot`，
# `include-system-site-packages = false`，82 个本地包）。若有人
#   VENV=/workspace/.../.codex-persist/envs/rlrobot bash scripts/setup_env.sh
# 那份 **28 pin 的门禁溯源件会被就地覆写成 82 pin**（含 torch/nvidia-*），头部 provenance 四行也被改写。
# 后果三条：① C 的 `c_env_manifest.py::_parse_lock` 从 28 变 82（`n_pins` 与 `lock.sha256_12` 全变）；
# ② B 的 `b_env_provenance_guard.py` G3「28 个项目 pin」基线失配；
# ③ `requirements.lock.txt` 是 0928 那批产物的溯源件之一，覆写它与裁定 32.4 保护 0928 lock
#    的理由**同型**（把可核事实换成新事实、旧的永久不可答）。
# `b_env_provenance_guard.py` 的 G1 只能**事后**报 RED（sha 变了），拦不住手滑 ⇒ 这里做**事前**护栏。
#
# 采用 D 倾向的 **(a) 断言后拒绝 + (c) 事前备份**：
#   (a) freeze 前读 `$VENV/pyvenv.cfg` 的 `include-system-site-packages`；
#       为 `false`（自足 venv）⇒ **不写** `requirements.lock.txt`，直接 `exit 1` 并打印该怎么办。
#       **故意不选**「改写到 `requirements.persistent.lock.txt`」那条分支：那份文件的生成器是
#       `scripts/d_build_persistent_lock.py`（D 所有，依赖闭包 BFS、82 pin），
#       本脚本再写一份就是**第二个写者**（裁定 21 单一来源；0929 B 已经吃过一次写权碰撞）。
#   (c) 真要写之前，把旧 lock `cp -p` 到 `runs/infra/b_lock_history/requirements.lock.<sha12>.txt`
#       （**禁 rm**；与 C 对 0928 两份 lock 做逐字节备份同型）。
# **不采用 (b) 数量闸**（freeze 行数 != 28 就拒绝）：它会在**合法重新 pin** 时也拒绝，
# 需要再开一个 `--allow-lock-rewrite` 开关，等于把「什么时候可以改事实源」变成两个判据；
# (a) 已经覆盖了实际观察到的那条风险路径（指向自足 venv）。要加数量闸请先报 D。
#
# 护栏放在**最前面**（早于建 venv、早于任何 pip install）：自足 venv 在 NFS 上建成后按**只读**对待
# （D §9：两个容器同时写会写坏它），所以不止不能覆写 lock，连往里 pip install 都不该发生。
#
# 牙：`bash scripts/setup_env.sh --guard-selftest` 双向演示（自足 venv 拒绝 / 继承 venv 放行）。
#     没有牙的护栏按裁定 27.1 视为没有护栏。
# ===========================================================================
LOCK_HISTORY_DIR="$REPO/runs/infra/b_lock_history"

_cfg_flag() {  # $1=venv 目录 $2=键名 → 回显 pyvenv.cfg 里的值（去空白；找不到回显空）
  sed -n "s/^[[:space:]]*$2[[:space:]]*=[[:space:]]*\(.*\)$/\1/p" "$1/pyvenv.cfg" 2>/dev/null \
    | head -1 | tr -d '[:space:]'
}

# 回显 "allow:<说明>" 或 "refuse:<原因>"。判定只看**可核事实**（pyvenv.cfg / 文件是否存在），
# 不看调用者的意图声明 —— 否则护栏就退化成一句注释。
lock_write_verdict() {  # $1=venv 目录 $2=目标 lock 路径
  local v="$1" ssp
  if [ -f "$v/pyvenv.cfg" ]; then
    ssp="$(_cfg_flag "$v" include-system-site-packages)"
    if [ "$ssp" = "false" ]; then
      echo "refuse:venv 是**自足**的（$v/pyvenv.cfg: include-system-site-packages=false）。requirements.lock.txt 是 28 pin 的门禁溯源件，只能由带 --system-site-packages 的**继承** venv 生成；在自足 venv 上 freeze 会得到 82 pin（含 torch/nvidia-*），把可核事实换成新事实。要持久环境的 lock 请跑 scripts/d_build_persistent_lock.py（生成 requirements.persistent.lock.txt，D 所有）；验收跑 scripts/b_env_provenance_guard.py。"
      return
    fi
    if [ -z "$ssp" ]; then
      echo "refuse:$v/pyvenv.cfg 里读不到 include-system-site-packages ⇒ **无法确认 venv 类型**，按不可确认处理（不当作继承 venv 放行）。"
      return
    fi
    echo "allow:include-system-site-packages=$ssp（继承 venv，freeze 只列 venv 内包 ⇒ 与 28 pin 口径一致）"
    return
  fi
  if [ ! -x "$v/bin/python" ]; then
    echo "allow:venv 尚不存在，本脚本会用 --system-site-packages 新建（继承 venv）"
    return
  fi
  echo "refuse:$v 有 bin/python 却没有 pyvenv.cfg ⇒ 不是标准 venv，无法确认类型，按不可确认处理。"
}

# (c) 事前备份：把即将被覆写的 lock 逐字节留档到 b_lock_history/，文件名带旧内容 sha12。
backup_lock() {  # $1=lock 路径
  local lock="$1" sha dst
  [ -f "$lock" ] || { echo "  (旧 lock 不存在，无需备份)"; return 0; }
  sha="$(sha256sum "$lock" | cut -c1-12)"
  mkdir -p "$LOCK_HISTORY_DIR"
  dst="$LOCK_HISTORY_DIR/$(basename "$lock").$sha.txt"
  if [ -f "$dst" ]; then
    echo "  已有同内容备份：$dst"
  else
    cp -p "$lock" "$dst"
    echo "  事前备份：$lock → $dst（sha256_12=$sha）"
  fi
}

guard_selftest() {
  # 双向演示：自足 venv 必须**拒绝**、继承 venv 必须**放行**；再加两条边界（读不到键 / 非标准 venv）。
  # 全部在临时目录上做fixture，**不碰**仓库里的真 lock。禁 rm ⇒ 临时目录留着不删。
  local tmp rc=0 n=0 nbad=0
  tmp="$(mktemp -d "${TMPDIR:-/tmp}/b_freeze_guard_selftest_XXXXXX")"
  echo "==> 护栏 selftest（fixture 目录：$tmp）"

  _fixture() {  # $1=名字 $2=pyvenv.cfg 内容（空串=不写该文件） $3=是否造 bin/python
    local d="$tmp/$1"
    mkdir -p "$d"
    [ -n "$2" ] && printf '%s\n' "$2" > "$d/pyvenv.cfg"
    if [ "$3" = "yes" ]; then mkdir -p "$d/bin"; : > "$d/bin/python"; chmod +x "$d/bin/python"; fi
  }
  _expect() {  # $1=用例名 $2=期望前缀(allow/refuse) $3=实际回显
    n=$((n + 1))
    case "$3" in
      "$2:"*) echo "  [PASS] $1 → ${3%%:*}" ;;
      *)      echo "  [FAIL] $1 → 期望 $2，实测：$3"; rc=1; nbad=$((nbad + 1)) ;;
    esac
  }

  _fixture selfsufficient "include-system-site-packages = false" no
  _fixture inheriting     "include-system-site-packages = true"  no
  _fixture nokey          "version = 3.11.9"                     no
  _fixture nonstandard    ""                                     yes
  _fixture notcreated     ""                                     no

  _expect "自足 venv（false）必须拒绝"        refuse "$(lock_write_verdict "$tmp/selfsufficient" "$tmp/x.lock")"
  _expect "继承 venv（true）必须放行"          allow  "$(lock_write_verdict "$tmp/inheriting" "$tmp/x.lock")"
  _expect "读不到该键 ⇒ 按不可确认拒绝"        refuse "$(lock_write_verdict "$tmp/nokey" "$tmp/x.lock")"
  _expect "有 bin/python 无 pyvenv.cfg ⇒ 拒绝" refuse "$(lock_write_verdict "$tmp/nonstandard" "$tmp/x.lock")"
  _expect "venv 尚不存在 ⇒ 放行（将新建继承 venv）" allow "$(lock_write_verdict "$tmp/notcreated" "$tmp/x.lock")"

  # (c) 备份这一支也要有牙：备份必须**逐字节相同**且文件名带旧内容 sha12。
  printf 'a==1\nb==2\n' > "$tmp/old.lock"
  LOCK_HISTORY_DIR="$tmp/history"
  backup_lock "$tmp/old.lock" > "$tmp/backup.log" 2>&1
  local want sha got
  sha="$(sha256sum "$tmp/old.lock" | cut -c1-12)"
  want="$tmp/history/old.lock.$sha.txt"
  n=$((n + 1))
  if [ -f "$want" ] && cmp -s "$want" "$tmp/old.lock"; then
    echo "  [PASS] 事前备份逐字节相同且文件名带 sha12（$sha）"
  else
    echo "  [FAIL] 备份缺失或内容不同：期望 $want"; rc=1; nbad=$((nbad + 1))
  fi
  # 反向：备份**不得**在旧 lock 不存在时凭空造文件（防空比对被读成通过）
  n=$((n + 1))
  if [ ! -f "$tmp/absent.lock" ]; then
    backup_lock "$tmp/absent.lock" > /dev/null 2>&1
    got="$(find "$tmp/history" -name 'absent.lock*' | wc -l | tr -d '[:space:]')"
    if [ "$got" = "0" ]; then echo "  [PASS] 旧 lock 不存在时不凭空造备份";
    else echo "  [FAIL] 旧 lock 不存在却造出了 $got 份备份"; rc=1; nbad=$((nbad + 1)); fi
  fi

  echo "==> 护栏 selftest：$((n - nbad))/$n 符合预期 → 护栏$([ "$rc" = 0 ] && echo '' || echo '**不**')有牙"
  return "$rc"
}

if [ "${1:-}" = "--guard-selftest" ]; then
  guard_selftest
  exit $?
fi

echo "==> 仓库: $REPO"
echo "==> venv: $VENV"

# 事前护栏：判定不通过就**在动任何东西之前**退出（不建 venv、不 pip install、不 freeze）。
VERDICT="$(lock_write_verdict "$VENV" "$REPO/requirements.lock.txt")"
case "$VERDICT" in
  allow:*)  echo "==> freeze 护栏：放行（${VERDICT#allow:}）" ;;
  refuse:*) echo "!! freeze 护栏：**拒绝**写 requirements.lock.txt" >&2
            echo "!!   原因：${VERDICT#refuse:}" >&2
            echo "!!   （D→B 执行单 §2；事后检测见 scripts/b_env_provenance_guard.py 的 G1/G3）" >&2
            exit 1 ;;
  *)        echo "!! freeze 护栏：判定回显不可解析：$VERDICT" >&2; exit 1 ;;
esac

# HuggingFace 直连不通，必须走镜像（ManiSkill 资产 / LeRobot 数据集都要）
export HF_ENDPOINT="${HF_ENDPOINT:-https://hf-mirror.com}"
# MuJoCo 离屏渲染：egl 用 GPU，osmesa 用 CPU。本机两个库都在。
export MUJOCO_GL="${MUJOCO_GL:-egl}"

if [ ! -x "$VENV/bin/python" ]; then
  echo "==> 创建 venv（继承 system site-packages 以复用 torch）"
  python3 -m venv --system-site-packages "$VENV"
fi

"$VENV/bin/python" -c "import torch; print('==> 继承的 torch:', torch.__version__, 'cuda:', torch.cuda.is_available())"

LOCK="$REPO/requirements.lock.txt"

# pip：lock 头部记了版本就装回那个版本（解析器行为可复现），没记才 -U。
PIP_RECORDED="$(sed -n 's/^# pip==\([^ ]*\).*/\1/p' "$LOCK" 2>/dev/null | head -1 || true)"
if [ -n "${PIP_RECORDED:-}" ]; then
  echo "==> pip 按 lock 记录的版本装回：pip==$PIP_RECORDED（解析器行为可复现）"
  "$VENV/bin/pip" install --no-input --progress-bar off "pip==$PIP_RECORDED"
else
  echo "==> lock 里没记 pip 版本，本次 -U pip（下次 freeze 会记进去）"
  "$VENV/bin/pip" install --no-input --progress-bar off --prefer-binary -U pip
fi

echo "==> 安装依赖（走 USTC/aliyun 镜像，pypi.org 直连不通）"
if [ -s "$LOCK" ]; then
  INSTALL_MODE="lock"
  echo "==> 口径 = lock 精确安装 + --no-deps（跳过解析器）：$LOCK"
  "$VENV/bin/pip" install --no-input --progress-bar off --prefer-binary \
    -r "$LOCK" --no-deps
else
  INSTALL_MODE="range_pin_fallback"
  echo "!! WARN 回退到**范围 pin** —— lock 缺失。已知风险：pip>=26 的解析器会判" >&2
  echo "!!      robosuite 1.5.2 -> mink==0.0.5 -> numpy<2.0.0 与 numpy>=2 冲突（ResolutionImpossible）。" >&2
  echo "!!      真撞上时不要就地放宽 pin：按 C 的 ADR-C-006 用 lock + --no-deps 复现，并把冲突报给 D。" >&2
  "$VENV/bin/pip" install --no-input --progress-bar off --prefer-binary \
    "numpy>=2" \
    "gymnasium<1.3" \
    "stable-baselines3[extra]<2.8" \
    "opencv-python<5" \
    "mujoco>=3.3.0,<3.10" \
    py-trees \
    imageio-ffmpeg \
    "robosuite==1.5.2"
fi

echo "==> 锁定版本清单"
# 注意：--local 只列 venv 里装的包。torch / pyyaml / imageio 等是从 base 继承的，
# 不会出现在 requirements.txt 里；换一台机器复现时会漏装，所以单独记一份。
#
# 2026-09-28 起：freeze 结果写 requirements.lock.txt，**不再覆写 requirements.txt**。
# 原因：requirements.txt 是人工 pin 的意图文件，被 freeze 覆写后 pin 会静默漂移
# （实测 robosuite 1.5.2 -> 1.5.1，直接导致 pinned_object_rng 失效 + state obs 从
#  60 维变 53 维，当天所有接触实验作废）。lock 是「实际装了什么」，两者必须分开。
# 头部四行是**注释**：B 的 `b_selfcheck_reproducibility.py`（L0-f/L0-g 只匹配 `robosuite==` 开头的行）
# 与 C 的 `c_env_manifest.py::_parse_lock`（显式跳过 `#` 与 `-` 开头的行）都会忽略它们，
# 所以记 provenance 不会污染任何一侧的 pin 解析。
# (c) 事前备份 + **临写前复判**：护栏不能只在脚本开头看一眼 —— 中间那几十步 pip install
# 有可能换掉 `$VENV` 的语义（例如有人中途 export VENV=...），而覆写是不可逆的事实替换。
VERDICT2="$(lock_write_verdict "$VENV" "$LOCK")"
case "$VERDICT2" in
  allow:*)  echo "==> freeze 护栏（临写前复判）：放行（${VERDICT2#allow:}）"
            backup_lock "$LOCK" ;;
  refuse:*) echo "!! freeze 护栏（临写前复判）：**拒绝**覆写 $LOCK" >&2
            echo "!!   原因：${VERDICT2#refuse:}" >&2
            exit 1 ;;
  *)        echo "!! freeze 护栏：判定回显不可解析：$VERDICT2" >&2; exit 1 ;;
esac
{
  echo "# generated_by=scripts/setup_env.sh"
  echo "# generated_at=$(date -Is)"
  echo "# install_mode=$INSTALL_MODE"
  echo "# python=$("$VENV/bin/python" -c 'import sys;print(".".join(map(str,sys.version_info[:3])))')"
  echo "# pip=$("$VENV/bin/pip" --version | awk '{print $2}')"
  "$VENV/bin/pip" freeze --local
} > "$LOCK"
if ! "$VENV/bin/python" -c "import robosuite,sys;sys.exit(0 if robosuite.__version__=='1.5.2' else 1)"; then
  echo "!! robosuite 版本不是 1.5.2 —— pinned_object_rng 与 state obs 布局都会变，" >&2
  echo "!! 接触实验结果不可与历史记录比较。请重装：pip install 'robosuite==1.5.2'" >&2
fi
"$VENV/bin/python" - "$REPO/requirements-inherited.json" <<'PYEOF'
# 语义**按 venv 类型分别解释**（D→B 执行单 §2 顺带条；已写进 B→C 交接单）：
#   · **继承 venv**（include-system-site-packages=true，本脚本的既定口径）：
#     `metadata.version(key)` 看得见 base 里的包 ⇒ 这份文件是「从 base 继承了什么」的真实清单，
#     `jax` 有值说明 base 的 jax 0.10.2 会被继承进来（09-24 那次 ImportError 的污染源）。
#   · **自足 venv**（false，例如 `.codex-persist/envs/rlrobot`）：
#     `jax` / `tensorflow` 会记成 `NOT INSTALLED` —— **这是设计意图，不是采集失败**
#     （增补十 §31 末条：新 venv 里 `import jax`/`import tensorflow` 都 ModuleNotFoundError）。
#     此时这份文件的含义变成「venv 内自带了什么」，**不能**再读成「继承了什么」。
# ⇒ 读这份文件必须同时读 venv 类型；C 的 `inherited_packages` 分类同此口径（0929 B 已实测
#   C 的 manifest 把 pip/setuptools 误归成 inherited，那两条其实是 venv 自带）。
import json, sys
from importlib import metadata
keys = ["torch", "torchvision", "pyyaml", "imageio", "scipy", "pandas",
        "matplotlib", "pillow", "psutil", "rich", "jax"]
out = {}
for key in keys:
    try:
        out[key] = metadata.version(key)
    except Exception:
        out[key] = "NOT INSTALLED"
with open(sys.argv[1], "w", encoding="utf-8") as fh:
    json.dump(out, fh, indent=2, ensure_ascii=False)
print("==> 从 base 继承的关键包已写入", sys.argv[1])
PYEOF

echo "==> 自检"
cd "$REPO"
MUJOCO_GL="$MUJOCO_GL" "$VENV/bin/python" scripts/env_check.py

echo "==> 可复现性门禁（B 线，接触实验前必须全过）"
MUJOCO_GL="$MUJOCO_GL" "$VENV/bin/python" scripts/b_selfcheck_reproducibility.py \
  --repeats 2 --json-out runs/infra/b_reproducibility/selfcheck.json \
  || echo "!! 可复现性自检未全过，先修再跑接触实验（详见 docs/b_reproducibility_incident_20260928.md）"

cat <<TIP

完成。下一步：
  source $VENV/bin/activate
  export HF_ENDPOINT=https://hf-mirror.com
  python scripts/smoke_random_policy.py --task Lift --episodes 1
  python scripts/train_reach.py --config configs/reach_sac.yaml
TIP
