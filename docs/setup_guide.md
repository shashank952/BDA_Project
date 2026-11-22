# Setup guide

Target environment for this repository: a single Windows machine acting as a pseudo-distributed
Hadoop node. The same commands work on Linux/macOS through the `.sh` wrappers in `scripts/`.

## 1. Prerequisites

| Requirement | Version used and verified | Notes |
| --- | --- | --- |
| JDK | OpenJDK 8u504 (Temurin) | Hadoop 3.2.4 does not run on JDK 17+. `JAVA_HOME` must point at JDK 8, even if a newer `java` is on `PATH`. |
| Hadoop | 3.2.4 | Needs `bin/winutils.exe` and `bin/hadoop.dll` on Windows. |
| Python | 3.12 | pandas 3.x, Flask 3.x, Streamlit 1.6x, Plotly 7.x |
| Hive | 3.1.3 | Binary distribution; embedded Derby metastore |
| Disk | ~5 GB free | 339 MB archives + 1.06 GB cleaned + 1.0 GB HDFS copies + Hive libs (1.1 GB) |
| Memory | 8 GB+ | 15.4 GB on the machine used for the reported measurements |

## 2. Install Hadoop on Windows

1. Unpack Hadoop to a path without spaces, e.g. `D:\hadoop\hadoop-3.2.4`.
2. Put `winutils.exe` and `hadoop.dll` in `%HADOOP_HOME%\bin`.
3. Set persistent environment variables:
   ```
   HADOOP_HOME=D:\hadoop\hadoop-3.2.4
   JAVA_HOME=D:\java\jdk8u504-b01
   PATH=%HADOOP_HOME%\bin;%JAVA_HOME%\bin;%PATH%
   ```
4. Configure `etc\hadoop\core-site.xml`:
   ```xml
   <property><name>fs.defaultFS</name><value>hdfs://localhost:9000</value></property>
   ```
5. Configure `etc\hadoop\hdfs-site.xml` (replication 1, local data dirs):
   ```xml
   <property><name>dfs.replication</name><value>1</value></property>
   <property><name>dfs.namenode.name.dir</name><value>D:\hadoop\hadoop-3.2.4\data\namenode</value></property>
   <property><name>dfs.datanode.data.dir</name><value>D:\hadoop\hadoop-3.2.4\data\datanode</value></property>
   ```
6. Format once, then start:
   ```powershell
   hdfs namenode -format
   & "$env:HADOOP_HOME\sbin\start-dfs.cmd"
   ```
7. Verify before going further:
   ```powershell
   jps                      # expect NameNode and DataNode
   hdfs dfs -mkdir -p /tmp/check
   hdfs dfs -ls /
   ```

The NameNode stays in safe mode for roughly 30 seconds after start; "Cannot create directory:
Name node is in safe mode" during that window is expected. Check with `hdfs dfsadmin -safemode get`.

## 3. Install Apache Hive

```powershell
# download and extract (archived release)
Invoke-WebRequest https://archive.apache.org/dist/hive/hive-3.1.3/apache-hive-3.1.3-bin.tar.gz -OutFile hive.tgz
New-Item -ItemType Directory D:\hive -Force
tar -xzf hive.tgz -C D:\hive
```

Point `config/settings.yaml -> hive.home` at `D:/hive/apache-hive-3.1.3-bin`. The project ships
its own `config/hive/hive-site.xml` (embedded Derby, `mapreduce.framework.name=local`,
`hive.exec.mode.local.auto=false`) and passes `HIVE_CONF_DIR` explicitly, so nothing in
`$HIVE_HOME/conf` needs editing.

Hive is invoked as `java -cp <hadoop classpath>;<hive>/lib/* org.apache.hadoop.hive.cli.CliDriver`,
not through `hive.cmd` - see the note in `docs/architecture.md` about the Windows wrappers.

HDFS scratch and warehouse directories need group/other write access because Hive resolves the
user name in lower case on Windows:

```powershell
hdfs dfs -mkdir -p /tmp/hive /user/hive /airline-delay/hive/warehouse
hdfs dfs -chmod -R 777 /tmp/hive /user/hive /airline-delay/hive/warehouse
```

## 4. Python environment

```powershell
python -m pip install -r requirements.txt
```

`config/settings.yaml` already points at `hadoop_home`, `java_home`, `hive.home` and the HDFS URI
for the reference machine. Overridable without editing files:

```
AIRLINE_HADOOP_HOME, AIRLINE_JAVA_HOME, AIRLINE_HDFS_URI,
AIRLINE_MR_FRAMEWORK, AIRLINE_API_HOST, AIRLINE_API_PORT, AIRLINE_API_URL
```

## 5. Run the pipeline

```powershell
python scripts/download_dataset.py --year 2025 --months 1-12
python -m src.preprocessing.clean_data --year 2025 --months 1-12
python scripts/hdfs_ops.py init
python scripts/hdfs_ops.py upload-raw --year 2025
python scripts/hdfs_ops.py upload-processed --year 2025 --months 1-12
python -m src.mapreduce.run_jobs --year 2025 --months 1-12 --validate
python -m src.hive.run_queries --all --validate
```

Then start the two services:

```powershell
python -m src.backend.app            # API on http://127.0.0.1:5050
streamlit run src/dashboard/app.py   # dashboard on http://localhost:8501
```

## 6. Reproducibility checks

```powershell
python -m pytest tests -q                     # 73 tests
python -m src.mapreduce.run_jobs --year 2025 --months 1-12 --validate-only
python scripts/hdfs_ops.py verify --year 2025 --month 1
```

## 7. Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| `Connection refused: localhost:9000` | HDFS not running | `start-dfs.cmd`, then `jps` |
| `Name node is in safe mode` | 30 s startup window | Wait, or `hdfs dfsadmin -safemode leave` |
| `CreateSymbolicLink error (1314)` on YARN containers | Windows lacks `SeCreateSymbolicLinkPrivilege` | Keep `AIRLINE_MR_FRAMEWORK=local`, or enable Developer Mode / run as Administrator |
| MapReduce: `subprocess failed with code 2`, `exec [python.exe, , ...]` | Streaming parser injected an empty argument because the command was quoted | Leave the command unquoted; paths must not contain spaces |
| Last CSV column ends with a tab | Streaming `TextOutputFormat` separator | The runner sets `mapreduce.output.textoutputformat.separator=` to empty |
| Hive: `The dir: /tmp/hive on HDFS should be writable` | HDFS dir owner differs in case from the resolved user | `hdfs dfs -chmod -R 777 /tmp/hive` |
| Hive: `Cannot run program ...\bin\hadoop` (error 193) | Local-auto mode spawns the Linux shell script | `hive.exec.mode.local.auto=false` (already set) |
| Hive: `FAILED: Execution Error ... MapredLocalTask`, yet output exists | Hive retried a failed local attempt successfully | The runner validates the result directory instead of the log text |
| Derby `Another instance of Derby may have already booted` | Two Hive sessions at once | Embedded Derby is single-session; run queries sequentially |
| `Illegal character in opaque part` on `-files` | Hadoop parsed a Windows path as a URI | Local mode passes absolute paths and no `-files` |
| Cleaning reads 0 rows | Wrong `--months` spec or archives not downloaded | Check `data/raw/bts/year=2025/*.zip` |
| API returns 503 | Analytical outputs not generated | `python -m src.hive.run_queries --all` |
| Dashboard cannot reach API | API stopped or different port | `python -m src.backend.app`, or set `AIRLINE_API_URL` |

## 8. Uninstall / reset

The pipeline is safe to re-run: cleaning overwrites its own partitions, MapReduce deletes its
output directory first, and Hive uses `INSERT OVERWRITE`. To reset completely, delete
`data/processed`, `data/quarantine`, `outputs/analytics`, `metastore`, and the HDFS paths under
`/airline-delay` except `raw/` - raw archives are never rewritten by any stage.
