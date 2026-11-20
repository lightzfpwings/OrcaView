"""不可变的模块间契约；所有长度坐标统一为 Å。"""

from dataclasses import dataclass
from typing import Optional, Tuple

from ._validation import finite_number, integer as _integer
from .block_options import BlockOverride, validated_block_values
from .elements import ATOMIC_NUMBERS
from .integrals import BASES, orbital_and_aux_keywords
from .methods import ALL_JOBS, METHODS, dispersion_options, frozen_core_options, pno_options, reference_options
from ._state_methods import validate_parameters
from .solvation import validate_solvation


SUPPORTED_METHODS = tuple(METHODS)
SUPPORTED_BASES = BASES


@dataclass(frozen=True)
class Atom:
    """元素符号大小写必须符合化学惯例，坐标单位为 Å。"""

    element: str
    x: float
    y: float
    z: float

    def validate(self) -> None:
        if not isinstance(self.element, str) or self.element not in ATOMIC_NUMBERS:
            raise ValueError(f"不支持的元素符号：{self.element!r}")
        for coordinate in (self.x, self.y, self.z):
            finite_number(coordinate, "原子坐标")


@dataclass(frozen=True)
class Bond:
    """a 和 b 为从零开始的原子索引；启发式推断只生成单键。"""

    a: int
    b: int
    order: int = 1


@dataclass(frozen=True)
class Molecule:
    name: str
    atoms: Tuple[Atom, ...]
    bonds: Tuple[Bond, ...] = ()
    charge: int = 0
    multiplicity: int = 1

    @property
    def electron_count(self) -> int:
        return sum(ATOMIC_NUMBERS[atom.element] for atom in self.atoms) - self.charge

    def validate_structure(self) -> None:
        """XYZ 只携带几何，不据此猜测电荷或自旋。"""
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("分子名称必须是非空字符串")
        if not self.atoms:
            raise ValueError("分子至少需要一个原子")
        if not isinstance(self.atoms, tuple) or not isinstance(self.bonds, tuple):
            raise ValueError("atoms 和 bonds 必须使用不可变 tuple")
        for atom in self.atoms:
            if not isinstance(atom, Atom):
                raise ValueError("atoms 中必须是 Atom 对象")
            atom.validate()
        seen = set()
        for bond in self.bonds:
            if not isinstance(bond, Bond):
                raise ValueError("bonds 中必须是 Bond 对象")
            _integer(bond.a, "键的起点", 0)
            _integer(bond.b, "键的终点", 0)
            _integer(bond.order, "键级", 1)
            if bond.a >= len(self.atoms) or bond.b >= len(self.atoms) or bond.a == bond.b:
                raise ValueError("化学键必须连接两个有效且不同的原子")
            if bond.order > 3:
                raise ValueError("当前原型只接受 1、2、3 键级")
            key = tuple(sorted((bond.a, bond.b)))
            if key in seen:
                raise ValueError("同一对原子不能重复定义化学键")
            seen.add(key)

    def validate(self) -> None:
        self.validate_structure()
        _integer(self.charge, "总电荷")
        _integer(self.multiplicity, "自旋多重度", 1)
        electrons = self.electron_count
        unpaired = self.multiplicity - 1
        if electrons < 0:
            raise ValueError("总电荷导致电子数为负")
        if unpaired > electrons or (electrons - unpaired) % 2:
            raise ValueError("电子数与自旋多重度不相容；请检查总电荷及多重度")


@dataclass(frozen=True)
class CalculationSpec:
    """ORCA 6.1 输入子集；高级方法适用性仍需要用户判断。"""

    method: str = "B3LYP"
    basis: str = "def2-SVP"
    job_type: str = "SP"
    cores: int = 4
    maxcore_mb: int = 1000
    active_electrons: Optional[int] = None
    active_orbitals: Optional[int] = None
    nroots: Optional[int] = None
    reference_functional: Optional[str] = None
    integral_approximation: str = "Auto"
    aux_j: Optional[str] = None
    aux_jk: Optional[str] = None
    aux_c: Optional[str] = None
    cabs: Optional[str] = None
    pno_preset: str = "Auto"
    integration_grid: str = "Auto"
    relativity: str = "Auto"
    dispersion: str = "Auto"
    electron_channel: Optional[str] = None
    wavefunction: str = "Auto"
    frozen_core: str = "Auto"
    block_options: Tuple[BlockOverride, ...] = ()
    solvation_model: str = "Gas"
    solvent: Optional[str] = None

    @property
    def peak_maxcore_per_process(self) -> int:
        """Largest configured per-process MaxCore among the successive ORCA modules."""
        return max((self.maxcore_mb, *(item.value for item in self.block_options
                                      if item.key.casefold() == "maxcore")))

    def validate(self) -> None:
        if not isinstance(self.method, str) or self.method not in METHODS:
            raise ValueError(f"未收录计算方法 {self.method!r}")
        if self.job_type not in ALL_JOBS:
            raise ValueError("未知作业类型，可选 " + "、".join(ALL_JOBS))
        if self.job_type not in METHODS[self.method].job_types:
            allowed = "、".join(METHODS[self.method].job_types)
            raise ValueError(f"{self.method} 当前模板支持的任务为 {allowed}")
        _integer(self.cores, "CPU 核数", 1)
        _integer(self.maxcore_mb, "每核内存 MB", 1)
        validate_parameters(self.method, self.active_electrons, self.active_orbitals,
                            self.nroots, self.reference_functional, self.electron_channel)
        orbital_and_aux_keywords(self)
        if self.pno_preset not in pno_options(self.method):
            raise ValueError(f"{self.method} 不支持 PNO 阈值 {self.pno_preset!r}")
        if self.dispersion not in dispersion_options(self.method):
            raise ValueError(f"{self.method} 不支持色散设置 {self.dispersion!r}")
        if self.wavefunction not in reference_options(self.method):
            raise ValueError(f"{self.method} 不支持所选参考波函数")
        if self.wavefunction in ("ROHF", "ROKS") and self.job_type != "SP":
            raise ValueError("限制性开壳层参考模板仅提供单点能")
        if self.frozen_core not in frozen_core_options(self.method):
            raise ValueError(f"{self.method} 不支持所选冻结芯设置")
        validate_solvation(self)
        validated_block_values(self)
