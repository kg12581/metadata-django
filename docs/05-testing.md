# 自动化测试与报告

## 运行

```bash
pip install -r requirements-dev.txt
mkdir -p testcase/reports
python -m pytest testcase -q \
  --html=testcase/reports/report.html --self-contained-html \
  --junitxml=testcase/reports/results.xml
```

也可直接 `python -m pytest testcase -q`(不带报告)。

## 测试覆盖

```text
testcase/
  conftest.py                       Django 初始化 + 禁止真实 LLM/远端调用
  common/test_models.py             密码加密落库/解密、类型枚举、模型字段
  services/test_schema_sync.py      类型映射/差异检测/建表与 ALTER SQL
  services/test_lineage.py          INSERT/CTAS 血缘解析与入库
  services/test_etl_tools.py        Debezium 消息解析、T+1 日期窗口
  api/test_views.py                 健康检查/页面渲染/文档/数据源 CRUD(密码掩码)/
                                    血缘/对账与调度校验/AI mock/脚本列表
  frontend/test_pages_snapshot.py   关键页面 HTML 快照(snapshots/)
  tools/test_scheduler_scripts.py   调度命令构造/脚本路径安全
```

原则: 单元层只测纯逻辑, API 层只用本地 SQLite 测试库, 外部依赖(LLM/远端库/crontab)
一律 mock 或跳过, 测试可离线、可重复、可进 CI。

## 报告与截图

- HTML 报告: `testcase/reports/report.html`(运行后生成)
- JUnit XML: `testcase/reports/results.xml`(供 CI 展示)
- 页面快照: `testcase/snapshots/*.html`(测试自动生成)
- 页面截图: `testcase/screenshots/*.png`(Chrome 无头模式截图, 人工核对用)

## CI

GitHub Actions `.github/workflows/ci.yml` 会在 push/PR 时运行本套件并把报告上传为 artifact。
