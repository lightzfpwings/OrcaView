"""Qt 为可选依赖，核心命令始终能独立使用。"""

import argparse
from dataclasses import asdict, replace
import json
from pathlib import Path
import sys

from orcaview import __version__
from orcaview.application.session import Session
from orcaview.core.block_options import BlockOverride, available_options, parse_option_value, validated_block_values
from orcaview.core.integrals import auxiliary_options, basis_options, integral_options
from orcaview.core.methods import (ACTIVE_SPACE_METHODS, ALL_JOBS, ELECTRON_CHANNEL_METHODS, EXCITED_STATE_METHODS, METHODS,
                                   METHOD_GROUPS, REFERENCE_FUNCTIONAL_METHODS, RESPONSE_FUNCTIONALS,
                                   canonical_method, dispersion_options, frozen_core_options, pno_options,
                                   reference_options)
from orcaview.core.models import CalculationSpec
from orcaview.core.solvation import MODELS, SOLVENTS, solvation_options
from orcaview.orca.output import parse_output


def _cli_block_options(spec, arguments):
    choices = {f"{o.block}.{o.key}".casefold(): o for o in available_options(spec)}
    overrides = []
    for argument in arguments:
        path, equals, value = argument.partition("=")
        if not equals:
            raise ValueError("--set 格式为 块名.参数名=值，例如 scf.MaxIter=250")
        option = choices.get(path.strip().removeprefix("%").casefold())
        if option is None:
            raise ValueError(f"{spec.method} / {spec.job_type} 不支持手动设置 {path!r}")
        overrides.append(BlockOverride(option.block, option.key, parse_option_value(option, value)))
    return tuple(overrides)


def _approximation_flags(parser):
    parser.add_argument("--set", dest="overrides", action="append", default=[], metavar="BLOCK.KEY=VALUE",
                        help="设置输入块中的单个参数，可重复，例如 --set scf.MaxIter=250")
    parser.add_argument("--pno-preset", default="Auto")
    parser.add_argument("--dispersion", default="Auto")
    parser.add_argument("--grid", "--integration-grid", dest="grid", default="Auto")
    parser.add_argument("--relativity", default="Auto")
    parser.add_argument("--wavefunction", default="Auto")
    parser.add_argument("--frozen-core", default="Auto")
    parser.add_argument("--solvation", choices=("Gas", *MODELS), default="Gas", help="隐式溶剂模型")
    parser.add_argument("--solvent", help="溶剂名，例如 water")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="orcaview", description="OrcaView · ORCA 可视化辅助框架")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command")
    manual = sub.add_parser("manual", help="查找 ORCA 6.1.1 手册网页和 PDF 对应页")
    manual.add_argument("query", nargs="*", help="章节号、方法或关键词")
    methods = sub.add_parser("methods", help="列出计算方法，或查看指定方法可用的基组与近似")
    methods.add_argument("method", nargs="?")
    methods.add_argument("--job", choices=ALL_JOBS, default="SP")
    methods.add_argument("--basis")
    methods.add_argument("--ri", "--integral-approximation", dest="ri", default="Auto")
    methods.add_argument("--blocks", action="store_true", help="列出此方法和作业适用的输入块字段")
    _approximation_flags(methods)
    gui = sub.add_parser("gui", help="启动桌面原型（需要 GUI 可选依赖）")
    gui.add_argument("--screenshot", type=Path, help=argparse.SUPPRESS)
    preview = sub.add_parser("preview", help="校验分子并向标准输出生成 ORCA 输入")
    preview.add_argument("xyz", nargs="?", type=Path)
    preview.add_argument("--job", choices=ALL_JOBS, default="SP")
    preview.add_argument("--method", default="B3LYP", help="计算方法，完整列表见 orcaview methods")
    preview.add_argument("--basis", help="轨道基组，F12 默认 cc-pVDZ-F12，普通方法默认 def2-SVP")
    preview.add_argument("--ri", "--integral-approximation", dest="ri", default="Auto")
    for slot in ("aux-j", "aux-jk", "aux-c", "cabs"):
        preview.add_argument("--" + slot, help="显式选择辅助基组，匹配选项见 orcaview methods 方法名")
    _approximation_flags(preview)
    preview.add_argument("--electron-channel", choices=("alpha", "beta"), help="开壳层 IP/EA-EOM 自旋通道")
    preview.add_argument("--active-electrons", type=int, help="多参考方法的活性电子数")
    preview.add_argument("--active-orbitals", type=int, help="多参考方法的活性轨道数")
    preview.add_argument("--nroots", type=int, help="垂直激发计算的激发根数，默认 5")
    preview.add_argument("--reference-functional", help="TD-DFT / TDA-DFT 的参考泛函，默认 B3LYP")
    preview.add_argument("--charge", type=int, default=0)
    preview.add_argument("--multiplicity", type=int, default=1)
    preview.add_argument("--cores", type=int, default=4)
    preview.add_argument("--maxcore", type=int, default=1000, help="每核内存 MB")
    inspect = sub.add_parser("inspect", help="读取单作业输出摘要，不执行 ORCA")
    inspect.add_argument("output", type=Path)
    inspect.add_argument("--job", choices=ALL_JOBS, default="SP")
    args = parser.parse_args(argv)
    try:
        if args.command == "manual":
            from orcaview.core.manual import lookup, PDF_URL, WEB_ROOT
            for number, title, path, page, _ in lookup(" ".join(args.query)):
                print(f"{number}  {title}\n  {WEB_ROOT}{path}\n  {PDF_URL}#page={page}")
            return 0
        if args.command == "methods":
            if args.method is None:
                if args.blocks:
                    raise ValueError("--blocks 需要指定计算方法，例如 orcaview methods B3LYP --blocks")
                for family, names in METHOD_GROUPS.items():
                    print(f"{family}  " + "、".join(names))
            else:
                from orcaview.core.integrals import grid_options, scalar_options
                name = canonical_method(args.method)
                bases = basis_options(name)
                basis = args.basis if args.basis is not None else (bases or ("def2-SVP",))[0]
                if args.job not in METHODS[name].job_types or args.ri not in integral_options(name, args.job):
                    raise ValueError(f"{name} 不支持所选作业与积分组合")
                if not bases and args.basis is not None:
                    raise ValueError(f"{name} 使用内置基组，请省略 --basis")
                models = solvation_options(name, args.job)
                if args.solvation not in models or (args.solvent is not None and args.solvent.lower() not in SOLVENTS.get(args.solvation, ())):
                    raise ValueError("该方法、作业、溶剂模型或溶剂名不相容")
                print("溶剂模型  " + "、".join(models))
                if args.solvation in SOLVENTS:
                    print("溶剂  " + "、".join(SOLVENTS[args.solvation]))
                spec = CalculationSpec(method=name, job_type=args.job, basis=basis, integral_approximation=args.ri,
                                       nroots=5 if name in EXCITED_STATE_METHODS else None,
                                       solvation_model=args.solvation, solvent=args.solvent,
                                       dispersion=args.dispersion, pno_preset=args.pno_preset, wavefunction=args.wavefunction,
                                       frozen_core=args.frozen_core, relativity=args.relativity, integration_grid=args.grid)
                if args.overrides:
                    spec = replace(spec, block_options=_cli_block_options(spec, args.overrides))
                    validated_block_values(spec)
                slots = auxiliary_options(name, basis, args.ri, spec.block_options)
                for label, choices in (("任务", METHODS[name].job_types), ("轨道基组", bases or ("内置",)),
                                       ("积分", integral_options(name, args.job)), *slots.items(),
                                       ("色散", dispersion_options(name)), ("PNO", pno_options(name)),
                                       ("参考波函数", reference_options(name, args.job)), ("冻结芯", frozen_core_options(name)),
                                       ("网格", grid_options(name, args.ri)), ("相对论", scalar_options(name, basis))):
                    print(f"{label}  " + "、".join(choices))
                if name in ACTIVE_SPACE_METHODS:
                    print("活性空间  --active-electrons 与 --active-orbitals")
                if name in EXCITED_STATE_METHODS:
                    print("目标根数  --nroots")
                if name in REFERENCE_FUNCTIONAL_METHODS:
                    print("参考泛函  " + "、".join(RESPONSE_FUNCTIONALS))
                if name in ELECTRON_CHANNEL_METHODS:
                    print("开壳层电子通道  --electron-channel alpha 或 beta")
                if args.blocks:
                    for value, choices in ((args.dispersion, dispersion_options(name)), (args.pno_preset, pno_options(name)),
                                           (args.wavefunction, reference_options(name, args.job)), (args.frozen_core, frozen_core_options(name)),
                                           (args.relativity, scalar_options(name, basis)), (args.grid, grid_options(name, args.ri))):
                        if value not in choices:
                            raise ValueError(f"{name} 不支持 {value!r}，可选 " + "、".join(choices))
                    for option in available_options(spec):
                        value = " / ".join(option.choices) if option.kind == "choice" else option.kind
                        print(f"%{option.block}.{option.key}  {value}  {option.label}")
            return 0
        if args.command == "gui":
            try:
                from orcaview.gui.main_window import launch
            except ModuleNotFoundError as exc:
                if exc.name and exc.name.startswith("PySide6"):
                    print('请先安装 GUI 依赖：python3 -m pip install ".[gui]"', file=sys.stderr)
                    return 2
                raise
            return launch(args.screenshot)
        if args.command == "preview":
            method = canonical_method(args.method)
            if args.basis is not None and not METHODS[method].uses_orbital_basis:
                raise ValueError(f"{method} 使用内置基组，请省略 --basis")
            session = Session()
            if args.xyz:
                session.open_xyz(args.xyz)
            session.molecule = replace(session.molecule, charge=args.charge, multiplicity=args.multiplicity)
            nroots = args.nroots
            if nroots is None and method in EXCITED_STATE_METHODS:
                nroots = 5
            functional = args.reference_functional
            if functional is not None:
                functional = canonical_method(functional)
            elif method in REFERENCE_FUNCTIONAL_METHODS:
                functional = "B3LYP"
            session.calculation = CalculationSpec(
                method=method, basis=args.basis if args.basis is not None else (basis_options(method) or ("def2-SVP",))[0],
                job_type=args.job, cores=args.cores, maxcore_mb=args.maxcore,
                active_electrons=args.active_electrons, active_orbitals=args.active_orbitals,
                nroots=nroots, reference_functional=functional,
                integral_approximation=args.ri, aux_j=args.aux_j, aux_jk=args.aux_jk, aux_c=args.aux_c,
                cabs=args.cabs, pno_preset=args.pno_preset, dispersion=args.dispersion,
                integration_grid=args.grid, relativity=args.relativity, electron_channel=args.electron_channel,
                wavefunction=args.wavefunction, frozen_core=args.frozen_core,
                solvation_model=args.solvation, solvent=args.solvent,
            )
            if args.overrides:
                overrides = _cli_block_options(session.calculation, args.overrides)
                session.calculation = replace(session.calculation, block_options=overrides)
            print(session.input_text(), end="")
            return 0
        if args.command == "inspect":
            result = parse_output(args.output.read_text(encoding="utf-8", errors="replace"), args.job)
            print(json.dumps(asdict(result), ensure_ascii=False, indent=2))
            return 0
        parser.print_help()
        return 0
    except (ValueError, OSError) as exc:
        print("OrcaView: {}".format(exc), file=sys.stderr)
        return 2

