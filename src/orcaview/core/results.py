"""Versioned scalar and array payloads shared by import, analysis and display."""

from contextlib import contextmanager
from dataclasses import dataclass, field
from hashlib import sha256
import math
import mmap
import os
from pathlib import Path
import struct
import tempfile
from typing import Optional, Tuple, Union

from ._validation import Versioned, finite_number, identifiers, integer, nonempty, require_tuple
from .provenance import ArtifactRef, Provenance, new_id
from .snapshots import GeometryRef, GeometrySnapshot


Number = Union[float, int]


@dataclass(frozen=True)
class DatasetAxis(Versioned):
    kind: str
    ids: Optional[Tuple[str, ...]] = None

    def __post_init__(self):
        nonempty(self.kind, "轴类型")
        if self.ids is not None:
            identifiers(self.ids, "轴 ID")
        elif self.kind in ("atom", "orbital", "mode", "state", "spin"):
            raise ValueError(f"{self.kind} 轴必须提供有序身份")


@dataclass(frozen=True)
class ResultDataset(Versioned):
    kind: str
    geometry: GeometryRef
    provenance: Provenance
    dtype: str
    shape: Tuple[int, ...]
    unit: str
    values: Optional[Tuple[Optional[Number], ...]] = None
    axes: Tuple[DatasetAxis, ...] = ()
    array_ref: Optional[ArtifactRef] = None
    missing_reason: Optional[str] = None
    method: Optional[str] = None
    density: Optional[str] = None
    spin: Optional[str] = None
    state_id: Optional[str] = None
    quality: Tuple[str, ...] = ()
    data_version: int = 1
    dataset_id: str = field(default_factory=new_id)

    def __post_init__(self):
        nonempty(self.dataset_id, "dataset_id")
        nonempty(self.kind, "数据类型")
        integer(self.data_version, "数据类型版本", 1)
        if not isinstance(self.geometry, GeometryRef) or not isinstance(self.provenance, Provenance):
            raise ValueError("结果必须绑定几何和来源")
        nonempty(self.unit, "单位")
        if self.dtype not in ("float64", "int64"):
            raise ValueError("当前结果 dtype 支持 float64 和 int64")
        require_tuple(self.shape, "shape")
        require_tuple(self.axes, "轴")
        if len(self.axes) != len(self.shape):
            raise ValueError("轴数必须与 shape 的维数相符")
        for size, axis in zip(self.shape, self.axes):
            integer(size, "维度", 1)
            if not isinstance(axis, DatasetAxis) or (axis.ids is not None and len(axis.ids) != size):
                raise ValueError("轴身份与 shape 不一致")
        for label in ("method", "density", "spin", "state_id", "missing_reason"):
            if getattr(self, label) is not None:
                nonempty(getattr(self, label), label)
        identifiers(self.quality, "质量说明")

        if self.array_ref is not None:
            if (not isinstance(self.array_ref, ArtifactRef) or self.array_ref.format != "raw-le"
                    or self.array_ref.sha256 is None):
                raise ValueError("外部数组需要 raw-le 文件及 SHA-256")
            if self.values is not None or self.missing_reason is not None:
                raise ValueError("外部数组不能同时声明内联值或缺失")
        elif self.values is None:
            if self.missing_reason is None:
                raise ValueError("缺少结果载荷时必须给出缺失原因")
        else:
            require_tuple(self.values, "结果值")
            if len(self.values) != math.prod(self.shape):
                raise ValueError("结果数量与 shape 不一致")
            if (None in self.values) != (self.missing_reason is not None):
                raise ValueError("缺失值与缺失原因必须同时声明")
            if self.dtype == "float64":
                values = tuple(None if v is None else finite_number(v, "结果值") for v in self.values)
                object.__setattr__(self, "values", values)
            else:
                for value in self.values:
                    if value is not None and (type(value) is not int or not -2**63 <= value < 2**63):
                        raise ValueError("结果值超出 int64 范围或类型不符")

    @property
    def valid_mask(self) -> Optional[Tuple[bool, ...]]:
        """Row-major mask for inline values. Whole missing and external payloads have no inline mask."""
        if self.values is None:
            return None
        return tuple(value is not None for value in self.values)

    def validate_geometry(self, snapshot: GeometrySnapshot) -> None:
        if self.geometry != snapshot.ref:
            raise ValueError("结果与实际几何引用不一致")
        if not snapshot.atom_ids:
            raise ValueError("分子至少需要一个原子")
        atoms = set(snapshot.atom_ids)
        for axis in self.axes:
            if axis.kind == "atom" and not atoms.issuperset(axis.ids):
                raise ValueError("结果轴包含该几何中不存在的原子 ID")

    @contextmanager
    def open_array(self, path: Path):
        """Yield a verified, read-only mapping. Release borrowed buffers before leaving the block."""
        if self.array_ref is None:
            raise ValueError("数据集没有外部数组")
        size = math.prod(self.shape) * 8
        digest = sha256()
        # A private copy stays immutable even if the source is edited or replaced.
        with Path(path).open("rb") as source, tempfile.TemporaryFile() as owned:
            if os.fstat(source.fileno()).st_size != size:
                raise ValueError("外部数组字节数与 dtype/shape 不符")
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                if owned.tell() + len(chunk) > size or len(chunk) % 8:
                    raise ValueError("外部数组长度已改变")
                if self.dtype == "float64" and any(not math.isfinite(v) for (v,) in struct.iter_unpack("<d", chunk)):
                    raise ValueError("外部数组包含非有限实数")
                digest.update(chunk)
                owned.write(chunk)
            if owned.tell() != size or digest.hexdigest() != self.array_ref.sha256:
                raise ValueError("外部数组内容与记录的 SHA-256 或大小不符")
            owned.flush()
            with mmap.mmap(owned.fileno(), size, access=mmap.ACCESS_READ) as mapping:
                yield mapping
