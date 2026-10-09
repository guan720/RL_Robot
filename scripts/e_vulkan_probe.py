#!/usr/bin/env python
"""E 线：Vulkan ICD 实测探针（装了 libGLX_nvidia.so.0 + nvidia_icd.json 之后到底能不能枚举到 GPU）。

为什么单独一个探针：`ls /usr/share/vulkan/icd.d/*.json` 只能证明"配置文件在"，
不能证明 loader 真能 dlopen 到 ICD 并枚举出物理设备。SAPIEN/ManiSkill 像素档、RoboTwin
都是先 `vkCreateInstance` 再挑物理设备，挑不到就直接报错（本机历史现象：
`vk::createInstanceUnique: ErrorIncompatibleDriver`，见 `docs/infra-gpu-render.md` §6.1）。
本探针复现的正是那两步，并且**不依赖任何第三方 Vulkan 绑定**（纯 ctypes）。

判据：
  V1 vkCreateInstance 返回 VK_SUCCESS
  V2 枚举到 >=1 个物理设备
  V3 设备名含期望子串（默认 NVIDIA；负对照用 --expect-name llvmpipe）
  V4 NVIDIA 设备的 driverVersion 解出的主版本与 `nvidia-smi` 的驱动版本一致
      （NVIDIA 的 driverVersion 打包方式：major<<22 | minor<<14 | patch<<6 | build）

用法：
  python scripts/e_vulkan_probe.py --label post_install --expect-name NVIDIA
  VK_ICD_FILENAMES=/usr/share/vulkan/icd.d/lvp_icd.x86_64.json \
      python scripts/e_vulkan_probe.py --label neg_lavapipe --expect-name llvmpipe
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import re
import subprocess
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
VK_SUCCESS = 0
VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO = 1
VK_NULL_HANDLE = ctypes.c_void_p(0)


class VkInstanceCreateInfo(ctypes.Structure):
    _fields_ = [
        ("sType", ctypes.c_int),
        ("pNext", ctypes.c_void_p),
        ("flags", ctypes.c_uint32),
        ("pApplicationInfo", ctypes.c_void_p),
        ("enabledLayerCount", ctypes.c_uint32),
        ("ppEnabledLayerNames", ctypes.POINTER(ctypes.c_char_p)),
        ("enabledExtensionCount", ctypes.c_uint32),
        ("ppEnabledExtensionNames", ctypes.POINTER(ctypes.c_char_p)),
    ]


def vk_ver(v: int) -> str:
    return f"{v >> 22}.{(v >> 12) & 0x3FF}.{v & 0xFFF}"


def nvidia_driver_ver(v: int) -> str:
    return f"{v >> 22}.{(v >> 14) & 0xFF}.{(v >> 6) & 0xFF}.{v & 0x3F}"


def smi_driver_version() -> str | None:
    try:
        p = subprocess.run(["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"],
                           capture_output=True, text=True, timeout=20)
        return p.stdout.strip().splitlines()[0].strip() or None
    except Exception:  # noqa: BLE001
        return None


def probe() -> dict:
    out: dict = {"icd_env": {k: os.environ.get(k) for k in
                             ("VK_ICD_FILENAMES", "VK_DRIVER_FILES", "__NV_PRIME_RENDER_OFFLOAD")},
                 "icd_jsons": sorted(str(p) for p in Path("/usr/share/vulkan/icd.d").glob("*.json"))
                 if Path("/usr/share/vulkan/icd.d").is_dir() else [],
                 "devices": [], "error": None}
    try:
        vk = ctypes.CDLL("libvulkan.so.1")
    except OSError as exc:
        out["error"] = f"libvulkan.so.1 载入失败: {exc}"
        return out
    vk.vkCreateInstance.restype = ctypes.c_int
    vk.vkCreateInstance.argtypes = [ctypes.POINTER(VkInstanceCreateInfo), ctypes.c_void_p,
                                    ctypes.POINTER(ctypes.c_void_p)]
    vk.vkEnumeratePhysicalDevices.restype = ctypes.c_int
    vk.vkEnumeratePhysicalDevices.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32),
                                              ctypes.POINTER(ctypes.c_void_p)]
    vk.vkGetPhysicalDeviceProperties.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    vk.vkDestroyInstance.argtypes = [ctypes.c_void_p, ctypes.c_void_p]

    ci = VkInstanceCreateInfo()
    ci.sType = VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO
    inst = ctypes.c_void_p()
    rc = vk.vkCreateInstance(ctypes.byref(ci), None, ctypes.byref(inst))
    out["vkCreateInstance_rc"] = rc
    if rc != VK_SUCCESS:
        out["error"] = f"vkCreateInstance 失败 VkResult={rc}"
        return out
    count = ctypes.c_uint32(0)
    rc = vk.vkEnumeratePhysicalDevices(inst, ctypes.byref(count), None)
    out["vkEnumeratePhysicalDevices_rc"] = rc
    out["physical_device_count"] = count.value
    if rc == VK_SUCCESS and count.value > 0:
        arr = (ctypes.c_void_p * count.value)()
        vk.vkEnumeratePhysicalDevices(inst, ctypes.byref(count), arr)
        for i in range(count.value):
            buf = ctypes.create_string_buffer(1024)   # VkPhysicalDeviceProperties 前部即可
            vk.vkGetPhysicalDeviceProperties(arr[i], buf)
            # POINTER(c_uint32).contents 是标量不是数组，必须用指针下标取值
            u32 = ctypes.cast(buf, ctypes.POINTER(ctypes.c_uint32))
            i32 = ctypes.cast(buf, ctypes.POINTER(ctypes.c_int32))
            api, drv, vendor, devid, dtype = u32[0], u32[1], u32[2], u32[3], i32[4]
            name = buf.raw[20:20 + 256].split(b"\x00", 1)[0].decode(errors="replace")
            entry = {"index": i, "deviceName": name, "apiVersion": vk_ver(api),
                     "deviceType": dtype, "vendorID": hex(vendor), "deviceID": hex(devid),
                     "driverVersion_raw": drv}
            if vendor == 0x10DE:      # NVIDIA
                entry["driverVersion_nvidia"] = nvidia_driver_ver(drv)
            out["devices"].append(entry)
    vk.vkDestroyInstance(inst, None)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--label", required=True)
    ap.add_argument("--expect-name", default="NVIDIA", help="设备名必须含这个子串（大小写不敏感）")
    ap.add_argument("--out-dir", default=None)
    args = ap.parse_args()

    res = probe()
    res["label"] = args.label
    res["timestamp"] = time.strftime("%Y-%m-%d %H:%M:%S %Z")
    res["smi_driver_version"] = smi_driver_version()
    want = args.expect_name.lower()
    matched = [d for d in res["devices"] if want in (d.get("deviceName") or "").lower()]
    passed, failed = [], []

    def chk(cond, label):
        (passed if cond else failed).append(label)

    chk(res.get("vkCreateInstance_rc") == VK_SUCCESS, "V1 vkCreateInstance == VK_SUCCESS")
    chk(res.get("physical_device_count", 0) >= 1,
        f"V2 枚举到物理设备（{res.get('physical_device_count', 0)} 个）")
    chk(bool(matched), f"V3 设备名含 '{args.expect_name}'（实测: "
                       f"{[d.get('deviceName') for d in res['devices']]}）")
    if want == "nvidia":
        nv = [d.get("driverVersion_nvidia") for d in matched]
        smi = res.get("smi_driver_version")
        # 必须按数值比：NVIDIA 打包出来的 patch 段是 "1"，nvidia-smi 印的是 "01"，
        # 字符串比会假红（这个坑本脚本第一版就踩了）。
        def nums(s):
            try:
                return tuple(int(x) for x in (s or "").split(".")[:3])
            except ValueError:
                return ()
        chk(bool(nv) and smi and any(nums(v) == nums(smi) for v in nv),
            f"V4 Vulkan driverVersion {nv} 与 nvidia-smi {smi} 前三段数值一致")
    res["verdict"] = {"ok": not failed, "passed": passed, "failed": failed}

    out_dir = Path(args.out_dir) if args.out_dir else (
        REPO_ROOT / "runs" / "infra" / f"e_gpu_egl_verify_{time.strftime('%Y%m%d')}")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"vulkan_{args.label}.json"
    out_path.write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=" * 76)
    print(f"E 线 Vulkan 探针 · label={args.label} · expect-name={args.expect_name}")
    print("=" * 76)
    print(f"  VK_ICD_FILENAMES         : {res['icd_env'].get('VK_ICD_FILENAMES') or '(未设，走系统 icd.d)'}")
    print(f"  vkCreateInstance         : rc={res.get('vkCreateInstance_rc')}")
    print(f"  物理设备数               : {res.get('physical_device_count', 0)}")
    for d in res["devices"]:
        extra = f" driverVersion={d.get('driverVersion_nvidia')}" if d.get("driverVersion_nvidia") else ""
        print(f"      [{d['index']}] {d['deviceName']}  api={d['apiVersion']} "
              f"type={d['deviceType']} vendor={d['vendorID']}{extra}")
    if res.get("error"):
        print(f"  error                    : {res['error']}")
    for p in passed:
        print(f"  PASS  {p}")
    for f in failed:
        print(f"  FAIL  {f}")
    print(f"  结论: {'通过' if not failed else '不通过'}   产物: {out_path}")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
