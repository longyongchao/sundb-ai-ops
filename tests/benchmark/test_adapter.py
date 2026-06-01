"""LILAC Loghub-2.0 适配器单元测试"""

import os
import re
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from benchmark.lilac_adapter import LilacLoghubAdapter, generate_logformat_regex
from benchmark.loghub_settings import benchmark_settings


class TestLogFormatRegex:
    """验证 generate_logformat_regex 对所有 14 个数据集 log_format 的正确性。"""

    SAMPLE_LINES = {
        "HDFS": "081109 203518 148 INFO dfs.DataNode$PacketResponder: PacketResponder 1 for block blk_38865049064139660 terminating",
        "Hadoop": "2015-10-17 15:37:49,537 INFO [IPC Server handler 7 on 35985] org.apache.hadoop.mapred.TaskAttemptListenerImpl: Progress of TaskAttempt attempt_1445062781478_0001_m_000000_0 is : 0.0",
        "Spark": "17/06/09 20:11:11 INFO storage.BlockManager: Found block rdd_42_20 locally",
        "Apache": "[Sun Dec 04 04:47:44 2005] [notice] workerEnv.init() ok /etc/httpd/conf/workers2.properties",
        "Proxifier": "[10.30 16:54:36] chrome.exe - proxy.cse.cuhk.edu.hk:5070 close, 3 bytes sent, 0 bytes received, lifetime <1 sec",
        "HealthApp": "20171012-13:24:41:672|Step_Counter|6329|REPORT : 1",
    }

    @pytest.mark.parametrize("dataset", list(benchmark_settings.keys()))
    def test_log_format_compiles(self, dataset):
        """每个数据集的 log_format 应能编译为有效正则。"""
        setting = benchmark_settings[dataset]
        headers, regex = generate_logformat_regex(setting["log_format"])
        assert "Content" in headers
        assert regex is not None

    @pytest.mark.parametrize("dataset,line", list(SAMPLE_LINES.items()))
    def test_sample_line_matches(self, dataset, line):
        """样本日志行应能被对应 log_format 正则匹配。"""
        setting = benchmark_settings[dataset]
        headers, regex = generate_logformat_regex(setting["log_format"])
        match = regex.match(line)
        assert match is not None, f"{dataset} regex failed to match: {line}"
        assert "Content" in match.groupdict()
        assert len(match.group("Content")) > 0

    def test_hdfs_fields_extraction(self):
        """HDFS 格式应正确提取各字段。"""
        setting = benchmark_settings["HDFS"]
        headers, regex = generate_logformat_regex(setting["log_format"])
        line = "081109 203518 148 INFO dfs.DataNode$PacketResponder: Received block blk_123 of size 67108864"
        match = regex.match(line)
        assert match is not None
        fields = match.groupdict()
        assert fields["Date"] == "081109"
        assert fields["Time"] == "203518"
        assert fields["Pid"] == "148"
        assert fields["Level"] == "INFO"
        assert "Received block" in fields["Content"]


class TestLilacAdapter:
    """端到端测试：创建临时日志文件，运行适配器，验证 CSV 输出。"""

    SAMPLE_LOG = """081109 203518 148 INFO dfs.DataNode$PacketResponder: PacketResponder 1 for block blk_38865049064139660 terminating
081109 203518 148 INFO dfs.DataNode$PacketResponder: PacketResponder 0 for block blk_-6670958622368987959 terminating
081109 203519 148 INFO dfs.DataNode$PacketResponder: PacketResponder 2 for block blk_38865049064139660 terminating
081109 203519 148 INFO dfs.FSNamesystem: BLOCK* NameSystem.allocateBlock: /mnt/hadoop/mapred/system/job_200811092030_0001/job.jar. blk_4868460839898259058
081109 203520 148 INFO dfs.DataNode$DataXceiver: Receiving block blk_-6670958622368987959 src: /10.250.14.224:42816 dest: /10.250.14.224:50010
"""

    def test_parse_produces_csvs(self, tmp_path):
        """适配器应生成 structured.csv 和 templates.csv。"""
        log_dir = tmp_path / "HDFS"
        log_dir.mkdir()
        log_file = log_dir / "HDFS_2k.log"
        log_file.write_text(self.SAMPLE_LOG)

        outdir = str(tmp_path / "output")
        adapter = LilacLoghubAdapter(
            log_format=benchmark_settings["HDFS"]["log_format"],
            indir=str(log_dir),
            outdir=outdir,
            rex=benchmark_settings["HDFS"]["regex"],
            enable_llm=False,
            enable_drain3=True,
        )
        adapter.parse("HDFS_2k.log")

        structured = os.path.join(outdir, "HDFS_2k.log_structured.csv")
        templates = os.path.join(outdir, "HDFS_2k.log_templates.csv")

        assert os.path.exists(structured)
        assert os.path.exists(templates)

        import pandas as pd
        df = pd.read_csv(structured)
        assert "LineId" in df.columns
        assert "EventId" in df.columns
        assert "EventTemplate" in df.columns
        assert "Content" in df.columns
        assert len(df) == 5

        tdf = pd.read_csv(templates)
        assert "EventId" in tdf.columns
        assert "EventTemplate" in tdf.columns
        assert "Occurrences" in tdf.columns

    def test_event_id_is_deterministic(self, tmp_path):
        """相同模板应产生相同 EventId。"""
        eid1 = LilacLoghubAdapter._compute_event_id("PacketResponder <*> for block <*> terminating")
        eid2 = LilacLoghubAdapter._compute_event_id("PacketResponder <*> for block <*> terminating")
        assert eid1 == eid2
        assert len(eid1) == 8


class TestEvaluator:
    """评测指标计算测试。"""

    def test_perfect_pa(self):
        """完全匹配时 PA=1.0。"""
        from benchmark.evaluator import compute_pa
        templates = ["template A", "template B", "template A"]
        assert compute_pa(templates, templates) == 1.0

    def test_zero_pa(self):
        """完全不匹配时 PA=0.0。"""
        from benchmark.evaluator import compute_pa
        parsed = ["X", "Y", "Z"]
        truth = ["A", "B", "C"]
        assert compute_pa(parsed, truth) == 0.0

    def test_ga_perfect_grouping(self):
        """完美分组时 GA=1.0。"""
        from benchmark.evaluator import compute_ga
        templates = ["T1", "T1", "T2", "T2"]
        assert compute_ga(templates, templates) == 1.0

    def test_ga_wrong_grouping(self):
        """错误分组时 GA < 1.0。"""
        from benchmark.evaluator import compute_ga
        truth = ["T1", "T1", "T2", "T2"]
        parsed = ["A", "B", "C", "C"]
        assert compute_ga(parsed, truth) < 1.0

    def test_fga_bounds(self):
        """FGA 应在 [0, 1] 范围内。"""
        from benchmark.evaluator import compute_fga
        truth = ["T1", "T1", "T2", "T3"]
        parsed = ["A", "A", "B", "B"]
        fga = compute_fga(parsed, truth)
        assert 0.0 <= fga <= 1.0

    def test_template_level_perfect(self):
        """完美匹配时 PTA=RTA=FTA=1.0。"""
        from benchmark.evaluator import compute_template_level
        templates = ["T1", "T1", "T2", "T3"]
        result = compute_template_level(templates, templates)
        assert result["pta"] == 1.0
        assert result["rta"] == 1.0
        assert result["fta"] == 1.0
