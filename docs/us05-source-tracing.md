# US-05 — 来源追溯实现与验证

## 核实的需求与基线

2026-11-25（America/New_York）只读查询 GitHub REST API：

- #21–#25 均有标题，但 `body=null`、评论为空；没有可读取的子任务独立验收细则。
- 五个 issue 的 `parent_issue_url` 都指向 [#5](https://github.com/Zihao-Zhang-00/hvac-bid-compliance-copilot/issues/5)，并非按编号推断。
- #5 要求可靠页码、对应原始招标文件、可定位支持文本、保留原文或片段、不可靠来源人工审核、不编造页码。
- PR #28 为 open / merged=false，head 为 `382cc47f35f128ae9a041f659e3223a0e49696cf`。
- 分支 `feature/us05-source-tracing` 基于最新获取的 main：`b48e5887cb36b67db9774cab9b59bee5dacda854`。没有合并或复制 PR #28 的分类实现。
- 仓库及适用父目录未发现 AGENTS.md。已读取 README、backend/requirements.txt 和 .github/workflows/backend-tests.yml。
- 本地开发未 push、创建远程 PR、发表评论、关闭 issue 或合并分支。

Zenhub 的独立板卡元数据未读取；需求证据来自 GitHub 完整 issue 对象、评论集合及明确父子关系。没有把未提供的子任务正文当作已知要求。

## 输入、输出与信任边界

输入为同一 PDF 的 `pages: list[dict]`，每项包含唯一正整数 `page_number` 与字符串 `text`，以及现有 `RequirementExtractionResult`。PDF parser 以物理页面顺序从 **1** 编号，包括空白页；不是 PDF 内印刷页码或逻辑页标签。零散页面保留已有编号，不重新编号。

输出仍为 `RequirementExtractionResult` / `TenderRequirement`，新增可选 `source_trace`：

| 字段 | 含义 |
| --- | --- |
| original_source_page | 模型最初提供的页码，更正后仍保存 |
| status | matched / missing / ambiguous |
| verified_source_page | 唯一匹配页；缺失或歧义为 null |
| match_method | casefold_whitespace_exact |
| evidence | 每个命中的实际页码、原文 text、start_char、end_char |

字符偏移是 **parser 返回的页面文本**中的 Python Unicode 字符索引，从 0 开始、右端不包含。不是 PDF 字节偏移、图像坐标或 OCR 坐标。

`source_page` 为兼容旧调用方而保留：唯一匹配时可更正；缺失或歧义时仍是未核验的原始模型页码。**下游只能用 `source_trace.verified_source_page` 显示“已确认来源”；不能把旧字段或 needs_review=False 当作验证证明。** 未经 tracing 的对象 `source_trace=None`，序列化时省略该字段，保持原有 fixture/调用契约。

LLM 输出中的 `source_trace` 一律丢弃，由服务端重新计算；模型不能提交自己的验证结果。结构化模型的 schema 会看到可选扩展字段，但提取 prompt 仍只要求原有字段。

## 匹配与审核规则

1. 复用 requirement_provenance，供 JSON 页码恢复及 quote review 共用，未引入第二套匹配器。
2. 对完整 requirement_text 作 Unicode casefold、连续空白折叠，扫描所有输入页面。数字、否定词、标点及其他字符不删除或近似替换。
3. 防止部分单词、数字、小数片段及半个 Unicode casefold 展开字符命中。
4. 只在一个不同页面命中：matched；保留该页面所有出现位置。模型页码不同则可靠更正，同时 needs_review=True。
5. 多个不同页面命中：ambiguous；保留所有候选证据，verified_source_page=null，不凭模型页码选一个。
6. 没有命中：missing；证据为空，verified_source_page=null，不生成替代引用。
7. missing / ambiguous / 页码更正均触发审核；原 needs_review=True 永不清除。
8. 保留 requirement_text、category、mandatory、evidence_needed；返回新对象，不修改输入页面或结果。重复调用 typed tracing 得到相同结果。
9. 规范化仅用于匹配，证据直接由原页面切片，保留原始大小写、换行与空白。

不使用模糊阈值、embedding、向量数据库或额外 LLM。matched 仅表示确定性文本定位，不证明模型已经正确理解整条法律/业务语义；可能遗漏引文周围的条件或否定上下文。大小写折叠也不能证明大小写敏感单位在语义上等价。审核者仍应结合原页上下文判断。

### 与 US-03 的严格校验兼容

没有降低原有页码校验规则：无效类型、非正整数、缺少必填字段仍被拒绝。**模型报告的页码不在输入页集合中、又不能唯一纠正时，extract_requirements 继续抛出原有 ValueError**，不会输出伪造页码；调用方应将这次提取失败交人工处理。页码在集合内但条款无法定位时，返回 missing / ambiguous 与 needs_review=True。

直接使用 `trace_source_pages` 可以对已构建的 typed result 表达缺失来源（包括来源不在提供页面集合中），但不会放宽 extraction 的 US-03 安全校验。现有拒绝非法页码的回归测试未修改。

## 子任务、实现与测试映射

子任务没有正文，以下按其真实标题、父 issue 验收条件及用户明确约束映射。

| 子任务 | 实现 | 验证 |
| --- | --- | --- |
| #21 Define Source Tracing Logic | 本文的数据契约、状态、页码约定与审核规则；SourceTrace/SourceEvidence | 旧 JSON 契约、类型校验、重复调用与序列化回读 |
| #22 Implement Source Page Matching | provenance 的统一规范化、位置映射、全页搜索、唯一页纠正 | 正确/错误页、大小写/空白、Unicode、数字/否定差异、部分 token 拒绝 |
| #23 Handle Missing and Ambiguous Sources | missing/ambiguous/null 已确认页、保留候选、审核 OR 规则 | 零命中、多页相同原文、模型页码提示不消除歧义、原审核标记保留 |
| #24 Preserve Source Evidence | 原页面切片、字符偏移、原始模型页码、深拷贝 | 原文精确保留、多次出现、无关字段保留、输入不变、模型伪造 trace 被覆盖 |
| #25 Add Automated Tests and Validate Source Tracing | 新测试与独立 US-04 接口验证脚本 | 全部 187 项 pytest；98.81% 语句+分支综合覆盖；US-04 八种情形双顺序验证 |

## 修改文件与理由

- `backend/app/requirement_schema.py`：兼容性的可选追溯元数据；旧对象未核验时不新增 JSON 键。
- `backend/app/requirement_provenance.py`：扩展既有匹配器，保留页码恢复入口，增加原文证据及 typed tracing。
- `backend/app/requirement_quote_review.py`：原入口委托统一追溯，避免重复规则。
- `backend/app/requirement_extractor.py`：恢复阶段开启服务端 trace，保留页码更正前的值。
- `backend/tests/test_source_tracing.py`：33 个确定性测试用例，覆盖需求约束及真实合成 PDF 字节解析。
- `backend/scripts/validate_us04_source_contract.py`：只读加载用户提供的 US-04 分类器文件，验证两种处理顺序，不复制分类器实现。
- `README.md`：提供实现与复现文档入口。
- `docs/us05-source-tracing.md`：需求证据、实现契约、验收映射、限制与 PR 草稿。

未修改分类规则、依赖、CI 门槛、旧测试、评分或合规报告模块。

## 实际执行结果

环境：macOS，Python 3.12.10；复用相邻 `review-pr28-venv`，所有 requirements.txt 固定版本均一致，`python -m pip check` 通过。

在 backend 运行（实际解释器是 `../../review-pr28-venv/bin/python`）：

```bash
../../review-pr28-venv/bin/python -m pytest tests -v \
  --cov=app --cov-branch --cov-report=term-missing --cov-fail-under=90
../../review-pr28-venv/bin/python -m scripts.validate_us04_source_contract \
  --classifier ../../review-pr28-worktree/backend/app/requirement_classifier.py
../../review-pr28-venv/bin/python -m pip check
git diff --check
```

- pytest：**187 passed**。
- CI 同样的分支覆盖检查：**98.81%**，门槛 **90%**；来源模块显示 **98%**。
- 外部 PR #28 分类器接口：**8 cases passed**，每种均验证 US-04→US-05 和 US-05→US-04、元数据保留、审核标记和重复调用。不是 PR #28 全套测试或合并验证。
- pip check / diff check：通过。
- 首次回归为 153 passed / 1 failed，发现新增空字段改变旧 JSON；通过在 None 时省略扩展字段修复，没有更改旧测试。

## 自行复现

```bash
cd /Users/sjhsjh/Documents/ChatGPT/Agent项目/us05-source-tracing/backend
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pytest tests -v \
  --cov=app --cov-branch --cov-report=term-missing --cov-fail-under=90
.venv/bin/python -m scripts.validate_us04_source_contract \
  --classifier ../../review-pr28-worktree/backend/app/requirement_classifier.py
```

在其他机器，把 classifier 参数替换为 PR #28 指定提交的独立只读 checkout 中的文件路径。最后一项独立验证可在该 checkout 可用时执行；主 pytest 套件不依赖 PR #28。

可只运行新测试：`.venv/bin/python -m pytest tests/test_source_tracing.py -v`。

真实模型验证按已有脚本约定：配置 `LLM_API_URL`、`LLM_API_KEY`、`LLM_MODEL` 后，执行：

```bash
.venv/bin/python -m scripts.evaluate_extraction --output /tmp/us05-live-evaluation.json
```

该脚本使用仓库合成逐页 JSON，不是上传真实 PDF 的端到端测试。此次没有配置这三个环境变量，因此没有执行真实模型推理，也不重复声称历史 qwen3 基线结果。

## 尚未验证与限制

- 无仓库内可用的真实招标 PDF；未执行真实 PDF + 真实模型端到端评估。
- 新 PDF 集成测试使用 reportlab 生成的合成 PDF，实际经过 pypdf 解析，LLM 响应为 ReplayLLM。
- 不支持 OCR、跨页拼接、断词修复、语义改写或近似匹配；这些可能返回 missing，要求审核。
- 假定输入页面来自同一份文档。当前契约没有持久化文件 ID / hash 或图像坐标；证据不能代替保管原始 PDF。
- 全页扫描及保存所有命中适合当前 MVP；大型文件未做性能基准。
- 仅本地执行 CI 等价命令，未触发或宣称远程 GitHub Actions 已通过。
- 没有提交私有招标文件或派生内容。

## English PR draft

**Title:** `feat: trace extracted requirements to verified source pages (US-05)`

**Description:**

Model-provided page numbers previously lacked an explicit verification result and retained no source excerpts. This change extends the existing provenance and quote-review pipeline with deterministic page matching and auditable evidence.

- Add optional source trace metadata with original model page, matched/missing/ambiguous status, verified page, and exact parser-text excerpts with character offsets.
- Confirm only a unique matching page; preserve all candidates for ambiguous matches, flag missing sources, and retain existing review decisions.
- Reuse the same case/whitespace-normalized matcher for recovery and review, protecting against partial word/number matches. Do not use fuzzy matching or additional model services.
- Preserve legacy fields and untraced JSON serialization. Keep US-03 strict rejection of out-of-input model pages when a unique correction is unavailable.
- Add deterministic regression tests, synthetic PDF parsing integration, and an external US-04 classifier contract check. Classification rules remain unchanged.

Validation: 187 backend tests passed; statement/branch coverage 98.81% against the unchanged 90% threshold. Eight external US-04 contract cases passed in both stage orders against PR #28 head `382cc47`. Dependency and diff checks passed.

Limitations: no live-model or private tender PDF evaluation; exact lexical location is not semantic verification; no OCR or cross-page matching. Consumers must use `source_trace.verified_source_page` to display a confirmed source.

Related: #5, #21, #22, #23, #24, #25. Child issues have no bodies or comments; implementation follows the parent acceptance criteria and the documented constraints. PR #28 remains unmerged and its implementation is not included here.
