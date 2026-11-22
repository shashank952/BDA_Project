"""Thin, reliable wrapper around the Hadoop Java entry points.

Why not `hdfs.cmd` / `hadoop.cmd`? On Windows those batch wrappers were observed
to (a) always exit 0 even when the command failed and (b) truncate arguments at
`=` (creating `/raw/source` instead of `/raw/source=bts`). Both behaviours are
unacceptable for a pipeline that must report failures honestly, so every call
goes straight to `java -cp <hadoop classpath> <main class>`.

Scopes:
    hdfs       -> FsShell only (put, ls, stat, test, rm ...)
    mapreduce  -> FsShell + MapReduce/YARN client classes (job submission)
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.common.config import load_settings  # noqa: E402

_SCOPE_PATTERNS = {
    "hdfs": [
        "etc/hadoop",
        "share/hadoop/common/*",
        "share/hadoop/common/lib/*",
        "share/hadoop/hdfs/*",
        "share/hadoop/hdfs/lib/*",
    ],
    "mapreduce": [
        "etc/hadoop",
        "share/hadoop/common/*",
        "share/hadoop/common/lib/*",
        "share/hadoop/hdfs/*",
        "share/hadoop/hdfs/lib/*",
        "share/hadoop/mapreduce/*",
        "share/hadoop/mapreduce/lib/*",
        "share/hadoop/yarn/*",
        "share/hadoop/yarn/lib/*",
    ],
}


class HadoopUnavailableError(RuntimeError):
    pass


def hadoop_home() -> Path:
    home = load_settings().hadoop_home
    if not (home / "bin").exists():
        raise HadoopUnavailableError(
            f"Hadoop not found at {home}. Set AIRLINE_HADOOP_HOME or edit config/settings.yaml."
        )
    return home


def java_binary() -> Path:
    java = load_settings().java_home / "bin" / ("java.exe" if os.name == "nt" else "java")
    if not java.exists():
        raise HadoopUnavailableError(
            f"Java not found at {java}. Hadoop 3.2.4 needs JDK 8/11; "
            "set AIRLINE_JAVA_HOME or edit config/settings.yaml."
        )
    return java


def hadoop_env() -> dict[str, str]:
    home = hadoop_home()
    env = os.environ.copy()
    env["JAVA_HOME"] = str(load_settings().java_home)
    env["HADOOP_HOME"] = str(home)
    env["HADOOP_CONF_DIR"] = str(home / "etc" / "hadoop")
    env["PATH"] = os.pathsep.join([str(home / "bin"), str(load_settings().java_home / "bin"), env.get("PATH", "")])
    return env


def classpath(scope: str = "hdfs") -> str:
    if scope not in _SCOPE_PATTERNS:
        raise ValueError(f"Unknown classpath scope: {scope}")
    home = hadoop_home()
    return os.pathsep.join(str(home / pattern.replace("/", os.sep)) for pattern in _SCOPE_PATTERNS[scope])


def java(
    main_class: str,
    args: list[str],
    *,
    jvm_args: list[str] | None = None,
    scope: str = "hdfs",
    timeout: int = 900,
) -> subprocess.CompletedProcess:
    command = [str(java_binary()), "-Xmx1g", *(jvm_args or []), "-cp", classpath(scope), main_class, *args]
    return subprocess.run(command, capture_output=True, text=True, env=hadoop_env(), timeout=timeout)


def fs(*args: str, check: bool = True, timeout: int = 900) -> subprocess.CompletedProcess:
    result = java("org.apache.hadoop.fs.FsShell", list(args), timeout=timeout)
    if check and result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()[:600]
        raise HadoopUnavailableError(f"hdfs {' '.join(args)} failed (exit {result.returncode}): {detail}")
    return result


def dfsadmin(*args: str, check: bool = True, timeout: int = 300) -> subprocess.CompletedProcess:
    """Administrative HDFS commands (-report, -safemode, ...) live under DFSAdmin, not FsShell."""
    result = java("org.apache.hadoop.hdfs.tools.DFSAdmin", list(args), timeout=timeout)
    if check and result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()[:600]
        raise HadoopUnavailableError(f"hdfs dfsadmin {' '.join(args)} failed: {detail}")
    return result


def run_jar(
    jar: Path,
    args: list[str],
    *,
    jvm_args: list[str] | None = None,
    timeout: int = 3600,
) -> subprocess.CompletedProcess:
    return java("org.apache.hadoop.util.RunJar", [str(jar), *args], jvm_args=jvm_args, scope="mapreduce", timeout=timeout)


def streaming_jar() -> Path:
    jar = hadoop_home() / "share" / "hadoop" / "tools" / "lib" / "hadoop-streaming-3.2.4.jar"
    if not jar.exists():
        candidates = sorted((hadoop_home() / "share" / "hadoop" / "tools" / "lib").glob("hadoop-streaming-*.jar"))
        if not candidates:
            raise HadoopUnavailableError("hadoop-streaming jar not found in $HADOOP_HOME/share/hadoop/tools/lib")
        jar = candidates[-1]
    return jar


def ping() -> str:
    """Return a short environment descriptor; raises when Hadoop is unusable."""
    result = fs("-ls", "/", check=False, timeout=120)
    if result.returncode != 0:
        raise HadoopUnavailableError(
            "HDFS is not reachable. Start it with "
            f"'{hadoop_home() / 'sbin' / 'start-dfs.cmd'}' (Windows) or '$HADOOP_HOME/sbin/start-dfs.sh'."
        )
    return f"hadoop={hadoop_home()} java={java_binary()} hdfs_ok=True"
