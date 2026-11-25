import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from orcaview.core import resource_defaults as resources


class DefaultTests(unittest.TestCase):
    def test_capacity_and_memory_headroom(self):
        for cpu, memory, result in (
            (128, 131072, (16, 4096)),
            (8, 131072, (8, 4096)),
            (64, 65536, (12, 4096)),
            (12, 8192, (1, 4096)),
            (4, 2048, (1, 1536)),
            (4, 0, (1, 1)),
            (None, None, (4, 1000)),
            (2, None, (2, 1000)),
            (None, 65536, (4, 4096)),
        ):
            with self.subTest(cpu=cpu, memory=memory):
                self.assertEqual(resources.ResourceAssessment(cpu, memory).recommend(), result)

    def test_only_unspecified_value_is_adjusted(self):
        host = resources.ResourceAssessment(16, 32768)
        self.assertEqual(host.recommend(cores=32), (32, 768))
        self.assertEqual(host.recommend(maxcore_mb=8192), (3, 8192))
        self.assertEqual(host.recommend(maxcore_mb=128000), (1, 128000))
        self.assertEqual(host.recommend(cores=60, maxcore_mb=8192), (60, 8192))
        for invalid in (0, -1, True, 1.5, "4"):
            for field in ("cores", "maxcore_mb"):
                with self.subTest(field=field, invalid=invalid), self.assertRaises(ValueError):
                    host.recommend(**{field: invalid})


class ResourceProbeTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name)
        self.proc = self.base / "proc"
        (self.proc / "self").mkdir(parents=True)

    def write(self, directory, name, value):
        directory.mkdir(parents=True, exist_ok=True)
        (directory / name).write_text(str(value))

    def mount(self, root, mount, fs, controllers="rw"):
        escaped_mount = str(mount).replace(" ", r"\040")
        return f"32 31 0:31 {root} {escaped_mount} rw - {fs} cgroup {controllers}\n"

    def test_available_memory_before_free_and_missing_counters(self):
        self.assertIsNone(resources._linux_memory(self.proc))
        self.write(self.proc, "meminfo", "MemFree:      1024 kB\nMemAvailable:      4096 kB\n")
        self.assertEqual(resources._linux_memory(self.proc), 4)
        self.write(self.proc, "meminfo", "MemFree:      1024 kB\n")
        self.assertEqual(resources._linux_memory(self.proc), 1)

    def test_unified_subtree_ancestor_quota_and_available_memory(self):
        mount = self.base / "mounted cgroup"
        child = mount / "batch"
        self.write(self.proc / "self", "cgroup", "0::/jobs/batch\n")
        self.write(self.proc / "self", "mountinfo", self.mount("/jobs", mount, "cgroup2"))
        self.write(mount, "cpu.max", "250000 100000")
        self.write(child, "cpu.max", "max 100000")
        self.write(mount, "memory.max", 16000 * 1024 ** 2)
        self.write(mount, "memory.current", 14000 * 1024 ** 2)
        self.write(child, "memory.max", 4000 * 1024 ** 2)
        self.write(child, "memory.current", 100 * 1024 ** 2)
        self.assertEqual(resources._cgroup_limits(self.proc), (2, 2000))
        self.write(child, "cpu.max", "50000 100000")
        self.write(child, "memory.current", 4000 * 1024 ** 2)
        self.assertEqual(resources._cgroup_limits(self.proc), (1, 0))
        self.write(self.proc / "self", "cgroup", "0::/batch\n")
        self.assertEqual(resources._cgroup_limits(self.proc), (1, 0))

    def test_legacy_controller_mounts_and_unlimited_sentinel(self):
        cpu, memory = self.base / "cpu", self.base / "memory"
        self.write(self.proc / "self", "cgroup", "9:cpu,cpuacct:/task\n8:memory:/task")
        self.write(self.proc / "self", "mountinfo", self.mount("/", cpu, "cgroup", "rw,cpu,cpuacct")
                   + self.mount("/", memory, "cgroup", "rw,memory"))
        self.write(cpu, "cpu.cfs_quota_us", "-1")
        self.write(cpu / "task", "cpu.cfs_period_us", "100000")
        self.write(cpu / "task", "cpu.cfs_quota_us", "400000")
        self.write(memory, "memory.limit_in_bytes", 9223372036854771712)
        self.assertEqual(resources._cgroup_limits(self.proc), (4, None))
        self.write(memory / "task", "memory.limit_in_bytes", 8000 * 1024 ** 2)
        self.write(memory / "task", "memory.usage_in_bytes", 200 * 1024 ** 2)
        self.assertEqual(resources._cgroup_limits(self.proc), (4, 7800))

    def test_slurm_current_node_or_smallest_known_node(self):
        env = {"SLURM_JOB_NUM_NODES": "3", "SLURM_NTASKS": "96",
               "SLURM_JOB_CPUS_PER_NODE": "16(x2),8", "SLURM_MEM_PER_CPU": "1000"}
        self.assertEqual(resources._slurm_limits(env), (8, 8000))
        self.assertEqual(resources._slurm_limits(dict(env, SLURM_NODEID="1")), (16, 16000))
        self.assertEqual(resources._slurm_limits(dict(env, SLURM_CPUS_ON_NODE="4")), (4, 4000))
        env = {"SLURM_JOB_NUM_NODES": "1", "SLURM_NTASKS": "3", "SLURM_CPUS_PER_TASK": "2",
               "SLURM_CPUS_ON_NODE": "8", "SLURM_MEM_PER_NODE": "32000"}
        self.assertEqual(resources._slurm_limits(env), (6, 32000))
        self.assertEqual(resources._slurm_limits({"SLURM_JOB_NUM_NODES": "4",
                                                  "SLURM_NTASKS": "128"}), (None, None))

    def test_macos_page_size_and_probe_failure(self):
        output = 'Mach Virtual Memory Statistics: (page size of 16384 bytes)\n'
        output += 'Pages free:    8000.\nPages inactive:  4800.\n'
        with mock.patch.object(subprocess, "run", return_value=mock.Mock(stdout=output)):
            self.assertEqual(resources._mac_memory(), 200)
        with mock.patch.object(subprocess, "run", side_effect=PermissionError):
            self.assertIsNone(resources._mac_memory())

    def test_detector_intersects_job_os_affinity_and_memory(self):
        with mock.patch.object(resources.sys, "platform", "linux"), \
             mock.patch.object(resources.os, "cpu_count", return_value=32), \
             mock.patch.object(resources.os, "sched_getaffinity", create=True, return_value={2, 3}), \
             mock.patch.object(resources, "_linux_memory", return_value=20000), \
             mock.patch.object(resources, "_cgroup_limits", return_value=(8, 15000)), \
             mock.patch.dict(resources.os.environ, {"SLURM_MEM_PER_NODE": "12000"}, clear=True):
            self.assertEqual(resources.detect_resources(), resources.ResourceAssessment(2, 12000))
