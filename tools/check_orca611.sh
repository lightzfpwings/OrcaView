#!/bin/sh
# Run three small serial calculations with a user-supplied, licensed ORCA 6.1.1.
set -eu
if [ "$#" -ne 2 ]; then
    echo "Usage: sh check_orca611.sh /absolute/path/to/orca /absolute/path/to/orcaview" >&2
    exit 2
fi
engine=$1
driver=$2
for binary in "$engine" "$driver"; do
    case "$binary" in
        /*) ;;
        *) echo "需要可执行文件的绝对路径: $binary" >&2; exit 2 ;;
    esac
    [ -f "$binary" ] && [ -x "$binary" ] || { echo "无法执行 $binary" >&2; exit 2; }
done
run_dir=$(mktemp -d "${PWD}/orcaview-611-XXXXXX")
echo "输入与日志目录：$run_dir"
cat > "$run_dir/water.xyz" <<'XYZ'
3
water, angstrom
O 0.000000 0.000000 0.000000
H 0.758602 0.000000 0.586541
H -0.758602 0.000000 0.586541
XYZ
run_case() (
    case_name=$1
    shift
    mkdir "$run_dir/$case_name"
    cd "$run_dir/$case_name"
    "$driver" preview "$run_dir/water.xyz" --job SP --cores 1 --maxcore 500 "$@" > job.inp
    echo "运行 $case_name"
    "$engine" job.inp > job.out 2>&1 || { echo "计算失败，见 $PWD/job.out" >&2; exit 1; }
    grep -Eq 'Program Version[[:space:]]+6\.1\.1([[:space:]]|$)' job.out &&
        grep -q 'ORCA TERMINATED NORMALLY' job.out &&
        grep -Eq 'FINAL SINGLE POINT ENERGY[[:space:]]+-?[0-9]' job.out ||
        { echo "请核对版本、终止状态和总能量：$PWD/job.out" >&2; exit 1; }
)
run_case smd --method B3LYP --solvation SMD --solvent water --set scf.MaxIter=150
run_case rimp2 --method RI-MP2 --ri RIJONX --set mp2.DoRegMP2=true
run_case eom --method EOM-CCSD --nroots 2 --set mdci.NDav=8
echo "三个输入均在 ORCA 6.1.1 正常结束。各步的能量和激发根请查阅各自的 job.out。"
