"""C 线：内容寻址的观测快照存储 + 表征版本冻结。

补的是 v4 附录 01 §2.3 / §5.1 的两条要求：

* **任一实际控制帧都能解释观测时刻**：相机帧与关节/夹爪数据各自记采样时刻，
  再组成带 ID 的同步观测；控制超时用本地单调时钟，跨机器记源时钟与同步误差。
  超过新鲜度或同步容差的观测**不能重打时间戳**当成新观察（`reuse_as` 会拒）。
* **表征缓存不能伪装成新表征**：每条快照绑定 `representation_version` /
  `normalizer_hash` / `features_version`；一个训练视图里混了多个表征版本就冻结该视图
  （见 `data_bridge.build_views` 的 `view_frozen_reasons`），而不是静默混用。

存储布局（默认落在 `runs/infra/c_obs_store/`，便于按来源回收）：

    <root>/index.sqlite          快照元数据索引（内容寻址，去重）
    <root>/blobs/<aa>/<sha>.npz  原始数组，保留原样以便日后重算表征

只做事实存储与新鲜度判定，不做奖励、资格或训练语义。
"""
from __future__ import annotations

import hashlib
import io
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np

DEFAULT_ROOT = Path("runs/infra/c_obs_store")
CONTRACT_VERSION = "v4-appendix01-2.3"

_INDEX_SCHEMA = """
CREATE TABLE IF NOT EXISTS obs(
  obs_ref TEXT PRIMARY KEY, inserted_ns INTEGER NOT NULL,
  episode_id TEXT, abs_frame INTEGER,
  sampled_at_ns INTEGER NOT NULL, decided_at_ns INTEGER,
  source_clock TEXT NOT NULL, sync_error_ns INTEGER,
  contract_version TEXT NOT NULL, representation_version TEXT NOT NULL,
  normalizer_hash TEXT, features_version TEXT,
  payload_path TEXT NOT NULL, payload_sha256 TEXT NOT NULL, nbytes INTEGER NOT NULL,
  keys TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS ix_obs_frame ON obs(episode_id, abs_frame);
CREATE INDEX IF NOT EXISTS ix_obs_repr ON obs(representation_version);
CREATE TABLE IF NOT EXISTS obs_usage(
  obs_ref TEXT NOT NULL, decided_at_ns INTEGER NOT NULL, recorded_ns INTEGER NOT NULL,
  PRIMARY KEY(obs_ref, decided_at_ns));
"""


class StaleObservation(RuntimeError):
    """观测超过新鲜度/同步容差，不能被当成新的决策输入复用。"""


class RepresentationMismatch(RuntimeError):
    """同一训练视图里出现多个表征/归一化版本。"""


@dataclass(frozen=True)
class ObsMeta:
    obs_ref: str
    episode_id: str | None
    abs_frame: int | None
    sampled_at_ns: int
    decided_at_ns: int | None
    source_clock: str
    sync_error_ns: int | None
    contract_version: str
    representation_version: str
    normalizer_hash: str | None
    features_version: str | None
    payload_path: str
    nbytes: int
    keys: tuple[str, ...]

    @property
    def age_ns(self) -> int | None:
        """决策时刻 - 采样时刻；没有决策时刻就是 None（未知不填 0）。"""
        if self.decided_at_ns is None:
            return None
        return int(self.decided_at_ns) - int(self.sampled_at_ns)


def canonical_bytes(observation: Mapping[str, Any]) -> tuple[bytes, tuple[str, ...], int]:
    """把观测字典规范化成字节，使内容寻址与写入顺序无关。"""
    arrays: dict[str, np.ndarray] = {}
    for key in sorted(observation):
        value = observation[key]
        arr = np.asarray(value)
        if arr.dtype == object:
            raise TypeError(f"observation[{key}] 含 object 数组，无法内容寻址")
        arrays[key] = np.ascontiguousarray(arr)
    buf = io.BytesIO()
    np.savez(buf, **arrays)
    payload = buf.getvalue()
    return payload, tuple(sorted(arrays)), len(payload)


def content_hash(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def normalizer_hash(normalizer: Mapping[str, Any] | None) -> str | None:
    """归一化统计量的内容指纹：mean/std 变了就必须换版本，不能沿用旧缓存。"""
    if normalizer is None:
        return None
    payload, _, _ = canonical_bytes({k: np.asarray(v) for k, v in normalizer.items()})
    return content_hash(payload)[:32]


class ObsStore:
    """内容寻址观测存储。`put` 去重，`get` 原样取回数组。"""

    def __init__(self, root: str | Path = DEFAULT_ROOT, *, contract_version: str = CONTRACT_VERSION):
        self.root = Path(root)
        (self.root / "blobs").mkdir(parents=True, exist_ok=True)
        self.contract_version = contract_version
        self.conn = sqlite3.connect(str(self.root / "index.sqlite"))
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(_INDEX_SCHEMA)
        self.conn.commit()

    # ---------- write ----------
    def put(self, observation: Mapping[str, Any], *, sampled_at_ns: int,
            representation_version: str, episode_id: str | None = None,
            abs_frame: int | None = None, decided_at_ns: int | None = None,
            source_clock: str = "monotonic", sync_error_ns: int | None = None,
            normalizer: Mapping[str, Any] | None = None, features_version: str | None = None,
            contract_version: str | None = None) -> ObsMeta:
        if not representation_version:
            raise ValueError("representation_version 不能为空：无版本的表征缓存不可追溯")
        payload, keys, nbytes = canonical_bytes(observation)
        obs_ref = content_hash(payload)
        relative = Path("blobs") / obs_ref[:2] / f"{obs_ref}.npz"
        target = self.root / relative
        existing = self.conn.execute("SELECT * FROM obs WHERE obs_ref=?", (obs_ref,)).fetchone()
        if existing is None:
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists():
                target.write_bytes(payload)
            self.conn.execute(
                "INSERT INTO obs(obs_ref,inserted_ns,episode_id,abs_frame,sampled_at_ns,decided_at_ns,"
                "source_clock,sync_error_ns,contract_version,representation_version,normalizer_hash,"
                "features_version,payload_path,payload_sha256,nbytes,keys)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (obs_ref, time.time_ns(), episode_id, abs_frame, int(sampled_at_ns),
                 None if decided_at_ns is None else int(decided_at_ns), source_clock,
                 None if sync_error_ns is None else int(sync_error_ns),
                 contract_version or self.contract_version, representation_version,
                 normalizer_hash(normalizer), features_version, str(relative), obs_ref, nbytes,
                 ",".join(keys)))
            self.conn.commit()
        else:
            # 同内容不同采样时刻 = 另一条快照事实；不允许把旧内容重打时间戳当新观察。
            if int(existing["sampled_at_ns"]) != int(sampled_at_ns):
                raise StaleObservation(
                    f"obs_ref {obs_ref[:12]} 已有采样时刻 {existing['sampled_at_ns']}，"
                    f"拒绝用 {sampled_at_ns} 重打时间戳")
            if existing["representation_version"] != representation_version:
                raise RepresentationMismatch(
                    f"同一份观测内容被标成两个表征版本："
                    f"{existing['representation_version']} vs {representation_version}")
        return self.meta(obs_ref)

    def bind_decision(self, obs_ref: str, decided_at_ns: int) -> ObsMeta:
        """记录该快照被哪个决策时刻使用（追加一行使用记录，不改原快照事实）。"""
        self.conn.execute(
            "INSERT OR IGNORE INTO obs_usage(obs_ref,decided_at_ns,recorded_ns) VALUES(?,?,?)",
            (obs_ref, int(decided_at_ns), time.time_ns()))
        self.conn.commit()
        return self.meta(obs_ref)

    # ---------- read ----------
    def meta(self, obs_ref: str) -> ObsMeta:
        row = self.conn.execute("SELECT * FROM obs WHERE obs_ref=?", (obs_ref,)).fetchone()
        if row is None:
            raise KeyError(f"unknown obs_ref: {obs_ref}")
        return ObsMeta(obs_ref=row["obs_ref"], episode_id=row["episode_id"],
                       abs_frame=row["abs_frame"], sampled_at_ns=int(row["sampled_at_ns"]),
                       decided_at_ns=row["decided_at_ns"], source_clock=row["source_clock"],
                       sync_error_ns=row["sync_error_ns"], contract_version=row["contract_version"],
                       representation_version=row["representation_version"],
                       normalizer_hash=row["normalizer_hash"], features_version=row["features_version"],
                       payload_path=row["payload_path"], nbytes=int(row["nbytes"]),
                       keys=tuple((row["keys"] or "").split(",")))

    def get(self, obs_ref: str) -> dict[str, np.ndarray]:
        meta = self.meta(obs_ref)
        with np.load(self.root / meta.payload_path) as zip_file:
            return {key: zip_file[key] for key in zip_file.files}

    def all_metas(self, *, representation_version: str | None = None,
                  episode_id: str | None = None) -> list[ObsMeta]:
        sql, args = "SELECT * FROM obs WHERE 1=1", []
        if representation_version is not None:
            sql += " AND representation_version=?"; args.append(representation_version)
        if episode_id is not None:
            sql += " AND episode_id=?"; args.append(episode_id)
        return [self.meta(row["obs_ref"]) for row in self.conn.execute(sql + " ORDER BY inserted_ns", args)]

    # ---------- 新鲜度 / 一致性判定 ----------
    def reuse_as(self, obs_ref: str, *, decided_at_ns: int, max_age_ns: int,
                 max_sync_error_ns: int | None = None) -> ObsMeta:
        """把一条已存快照用于某个决策时刻：超龄或超同步容差就拒绝，不重打时间戳。"""
        meta = self.meta(obs_ref)
        age = int(decided_at_ns) - int(meta.sampled_at_ns)
        problems = []
        if age > max_age_ns:
            problems.append(f"age_ns={age} > max_age_ns={max_age_ns}")
        if max_sync_error_ns is not None and meta.sync_error_ns is not None \
                and int(meta.sync_error_ns) > max_sync_error_ns:
            problems.append(f"sync_error_ns={meta.sync_error_ns} > max={max_sync_error_ns}")
        if meta.sync_error_ns is None and max_sync_error_ns is not None:
            problems.append("sync_error_ns unknown but tolerance required")
        if problems:
            raise StaleObservation(f"obs_ref {obs_ref[:12]} 不可作为该决策时刻的观测: "
                                   + "; ".join(problems))
        self.bind_decision(obs_ref, decided_at_ns)
        return meta

    def assert_single_representation(self, obs_refs: Iterable[str], *, view_name: str = "view",
                                     ignore_unknown: bool = False) -> dict[str, Any]:
        """一个训练视图只能有一个表征/归一化版本；混了就报错并列出受影响快照。"""
        versions: dict[str, list[str]] = {}
        normalizers: dict[str, list[str]] = {}
        for ref in obs_refs:
            if not ref:
                continue
            meta = self.meta(ref)
            versions.setdefault(meta.representation_version, []).append(ref)
            key = meta.normalizer_hash or "<none>"
            normalizers.setdefault(key, []).append(ref)
        problems = []
        if len(versions) > 1:
            problems.append(f"representation_version 混用: {sorted(versions)}")
        if len(normalizers) > 1:
            problems.append(f"normalizer_hash 混用: {sorted(normalizers)}")
        if problems and not ignore_unknown:
            raise RepresentationMismatch(f"{view_name}: " + "; ".join(problems))
        return {"view": view_name, "representation_versions": sorted(versions),
                "normalizer_hashes": sorted(normalizers), "problems": problems,
                "n_snapshots": sum(len(v) for v in versions.values())}

    def stats(self) -> dict[str, Any]:
        rows = self.conn.execute(
            "SELECT representation_version, COUNT(*) AS n FROM obs GROUP BY representation_version"
        ).fetchall()
        return {"root": str(self.root),
                "n_snapshots": int(self.conn.execute("SELECT COUNT(*) FROM obs").fetchone()[0]),
                "n_bytes": int(self.conn.execute("SELECT COALESCE(SUM(nbytes),0) FROM obs").fetchone()[0]),
                "per_representation": {r["representation_version"]: int(r["n"]) for r in rows}}

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "ObsStore":
        return self

    def __exit__(self, *_exc: Any) -> None:
        self.close()


def x_refs_of(samples: Sequence[Any]) -> list[str]:
    """从训练样本里取出所有 X / X_next 的快照引用，供一致性检查。"""
    out: list[str] = []
    for sample in samples:
        for attr in ("x_ref", "next_x_ref"):
            ref = getattr(sample, attr, None)
            if ref:
                out.append(str(ref))
    return out
