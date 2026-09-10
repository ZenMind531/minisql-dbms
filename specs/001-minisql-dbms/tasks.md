---
description: "Task list for MiniSQL 教学数据库系统 (4-person team)"
---

# Tasks: MiniSQL 教学数据库系统

**Input**: Design documents from `/specs/001-minisql-dbms/`
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/ ✅
**Tests**: 包含（宪章 III「测试先行」为 NON-NEGOTIABLE）
**团队**: 4 人，负责人标注 (A)(B)(C)(D)，见文末「四人分工总览」

> 状态同步于 2026-09-10。勾选表示仓库中已有对应实现与测试；T028、T034
> 等未勾选项仍是正式交付缺口。

## Format: `[ID] [P?] [Story] (负责人) 描述（含文件路径）`

---

## Phase 1: Setup（全员，约 0.5 天）

- [x] T001 按 plan.md 创建目录结构 `database_system/{sql_compiler,storage,engine,cli,utils}`、`tests/`、`docs/`（全员，D 执行）
- [x] T002 [P] 初始化 git 仓库、`.gitignore`、`README.md`（运行/构建说明骨架）（D）
- [x] T003 [P] 配置 pytest（`pytest.ini`）与 Python 3.11 开发环境，全组跑通空测试（D）

---

## Phase 2: Foundational（阻塞性基础设施，全员评审）

**⚠️ CRITICAL**：以下接口/基础类型未定稿前，任何人不得开始各自模块实现

- [x] T004 编写 `docs/grammar.md`：SQL 子集文法（四类语句 + WHERE 表达式优先级 NOT>比较>AND>OR + 强制 `VARCHAR(n)`，1≤n≤255）（A 主笔，全员评审冻结）
- [x] T005 [P] 定义 AST 节点 `database_system/sql_compiler/ast_nodes.py`（语句节点+表达式节点，带 line/column）（A 起草，B/D 评审签字）
- [x] T006 [P] 实现统一错误类型 `database_system/utils/errors.py`：LexError/ParseError/SemanticError/StorageError/ExecError，均含 type/line/column/message（B）
- [x] T007 [P] 定义常量与工具 `database_system/utils/constants.py`（PAGE_SIZE=4096 等）与 `utils/helpers.py`（C）
- [x] T008 全组评审并冻结 contracts/ 三份接口契约（全员，组长 D 归档）

**Checkpoint**: 文法、AST、错误类型、契约冻结 → 各模块并行开工

---

## Phase 3: User Story 1 — SQL 编译器 (Priority: P1) 🎯 MVP（负责人 A、B）

**Goal**: SQL 文本 → Token → AST → 语义检查 → Logical Plan → 优化 Plan，错误精确定位不崩溃
**Independent Test**: `pytest tests/test_lexer.py test_parser.py test_semantic.py test_planner.py -v` + quickstart「编译器演示」

### Tests（先写，确认 FAIL 再实现）⚠️

- [x] T009 [P] [US1] 词法测试 `tests/test_lexer.py`：五类 Token、行列号、注释、大小写、`''` 转义、未闭合字符串/非法字符报错（A）
- [x] T010 [P] [US1] 语法测试 `tests/test_parser.py`：四类语句 AST 结构、AND/OR/NOT/括号优先级树形、`AND;` 等错误含期望集合（A）
- [x] T011 [P] [US1] 语义测试 `tests/test_semantic.py`：表/列不存在、INT+VARCHAR 类型错误、INSERT 列数/类型不匹配（B）
- [x] T012 [P] [US1] 计划与优化测试 `tests/test_planner.py`：SelectStmt→Project/Filter/SeqScan、DeleteStmt→Delete/Filter/SeqScan 结构断言（plan_to_json）、常量折叠 `1=1 AND age>10+8 → age>18` 前后等价（B）

### Implementation

- [x] T013 [US1] 实现 `database_system/sql_compiler/lexer.py`（按 contracts/compiler-api.md；T009 转绿）（A）
- [x] T014 [US1] 实现 `database_system/sql_compiler/parser.py` 递归下降（依赖 T004/T005/T013；T010 转绿）（A）
- [x] T015 [P] [US1] 实现 `database_system/sql_compiler/catalog.py` 内存版（create_table/find_table/find_column/get_type）（B）
- [x] T016 [US1] 实现 `database_system/sql_compiler/semantic.py`（依赖 T015；类型规则集中管理；T011 转绿）（B）
- [x] T017 [US1] 实现 `database_system/sql_compiler/planner.py` + `plan_to_json/plan_to_tree`（B）
- [x] T018 [US1] 实现 `database_system/sql_compiler/optimizer.py`（常量折叠/布尔化简/冗余消除；T012 转绿）（B）
- [x] T019 [US1] 编译器流水线演示入口（`--compile-only` 模式，打印 Token→AST→Plan→优化 Plan）（A/B 合做）
- [x] T020 [US1] 编写 `tests/sql/` 编译器测试 SQL 集：正常、词法错、语法错、语义错、边界（空/超长/大小写/多语句）≥ 30 条（A）

**Checkpoint**: 课程第一阶段验收标准达成 → 组内验收（演示 + 每人讲解自己函数）

---

## Phase 4: User Story 2 — 页式存储系统 (Priority: P2)（负责人 C，D 支援）

**Goal**: 4KB slotted page + 文件管理 + LRU/FIFO 缓冲池（命中统计+日志+脏页写回）
**Independent Test**: `pytest tests/test_storage.py test_buffer.py -v`，固定访问序列命中率与手工推演一致

### Tests（先写）⚠️

- [x] T021 [P] [US2] 页测试 `tests/test_storage.py`：insert/get/delete/满页返回 None、to_bytes/from_bytes 往返一致（C）
- [x] T022 [P] [US2] 缓冲池测试 `tests/test_buffer.py`：LRU/FIFO 固定序列命中与淘汰顺序、pin 页不可淘汰、全帧 pinned 时 StorageError、unpin(dirty=True) 后 flush、stats 数值（C）

### Implementation

- [x] T023 [US2] 实现 `database_system/storage/page.py`（slotted page，页头 32B 布局见 data-model.md；T021 转绿）（C）
- [x] T024 [US2] 实现 `database_system/storage/file_manager.py`（页 0 文件头；数据页从 1 开始；allocate/free/read/write_page，空闲页链表）（C）
- [x] T025 [US2] 实现 `database_system/storage/buffer.py`（OrderedDict LRU/FIFO、dirty 写回、stats、logging；T022 转绿）（C）
- [x] T026 [US2] 持久化验证脚本：写入→杀进程→重启读回断言一致（可复用为集成测试 `tests/test_storage_persist.py`）（C）

**Checkpoint**: 课程第二阶段验收标准达成 → 组内验收（C 主讲页布局与淘汰过程推演）

---

## Phase 5: User Story 3 — 端到端数据库引擎 + CLI (Priority: P3)（负责人 D，全员集成）

**Goal**: 执行引擎 + 行/页映射 + 系统目录持久化 + CLI，四类 SQL 端到端跑通且重启后数据在
**Independent Test**: quickstart「端到端演示」+ `tests/test_e2e.py`

### Tests（先写）⚠️

- [x] T027 [P] [US3] 引擎测试 `tests/test_engine.py`：建表/插入/扫描/删除行数与内容断言（D）
- [ ] T028 [P] [US3] 端到端测试 `tests/test_e2e.py`：demo_e2e.sql 输出逐行比对 + 重启持久化断言（D）

### Implementation

- [x] T029 [US3] 实现 `database_system/engine/storage_engine.py`：行序列化（struct 定长）、行/页映射、scan/delete_where（依赖 T023–T025）（D）
- [x] T030 [US3] 实现 `database_system/engine/catalog_manager.py`：首次启动 bootstrap `__catalog__`（不递归登记自身）、普通表登记失败回滚新建数据文件、启动重建内存 Catalog（依赖 T029）（D）
- [x] T031 [US3] 实现 `database_system/engine/executor.py`：CreateTable/Insert/SeqScan/Filter/Project 算子执行（D）
- [x] T032 [US3] 实现顶层编排 `MiniDB.execute()` 与 `database_system/cli/main.py`（REPL + `--file` + `--compile-only` + 退出 flush）（D）
- [x] T033 [US3] 全员集成联调：编译器(A/B) × 引擎(D) × 存储(C) 接口对齐，修复集成问题（全员）
- [ ] T034 [US3] `tests/sql/demo_e2e.sql` 定稿（quickstart 中七条演示 SQL + 重启验证步骤）（D）

**Checkpoint**: 课程第三阶段验收标准达成 → 全组按教师验收形式彩排（随机讲解/现场改需求/现场 Debug）

---

## Phase 6: Polish & 交付物

- [x] T035 [P] 完善 `README.md`（构建/运行/演示命令）与 `docs/design.md`（AST/Catalog/Plan 结构说明）（A）
- [ ] T036 [P] 整理测试报告：测试用例清单、运行结果截图/日志、失败案例分析（C）
- [ ] T037 实习报告：关键设计决策、问题定位过程、AI 辅助使用说明、四人贡献说明（D 汇总，全员供稿）
- [ ] T038 [P] 扩展项：ORDER BY 与固定种子 Fuzz 已完成；UPDATE、Plan 可视化未实现（认领制）
- [ ] T039 最终验收彩排：按 quickstart.md 全流程演示一遍，每人随机抽讲一个函数（全员）

---

## Dependencies & Execution Order

```text
Phase 1 Setup (T001–T003)
   └─ Phase 2 Foundational (T004–T008)  ← 冻结文法/AST/契约，阻塞一切
        ├─ Phase 3 US1 编译器 (T009–T020)   [A、B 并行]
        ├─ Phase 4 US2 存储   (T021–T026)   [C 主导，可与 Phase 3 完全并行]
        └─ Phase 5 US3 引擎   (T027–T034)   [D 主导，依赖 US1+US2 接口]
             └─ Phase 6 Polish (T035–T039)
```

- US1 与 US2 接口零耦合，**可以并且应该并行**；D 在 Phase 3/4 期间做集成脚手架（MiniDB 骨架、契约桩测试）。
- US3 是汇流点，风险最高：A/B/C 完成各自阶段后立即投入 T033 集成。

## Requirement Traceability

| 需求 | 主要任务 |
|------|----------|
| FR-001–FR-005 | T004, T005, T009, T010, T013, T014, T020 |
| FR-006–FR-010 | T006, T011, T012, T015–T020 |
| FR-011–FR-013A | T007, T021–T026 |
| FR-014–FR-017、FR-016A | T027–T034 |
| SC-001–SC-004 | T009–T020, T028 |
| SC-005 | T021, T022 |
| SC-006 | T026, T028, T034, T039 |
| SC-007 | 各阶段 Checkpoint, T039 |

## 四人分工总览

| 成员 | 角色 | 负责模块 | 主任务 | 验收讲解点 |
|------|------|----------|--------|------------|
| **A** | 编译器前端 | lexer.py, parser.py, ast_nodes.py, grammar.md | T004,T005,T009,T010,T013,T014,T019,T020,T035 | 现场画 AST、讲表达式优先级与错误恢复 |
| **B** | 编译器后端 | semantic.py, catalog.py, planner.py, optimizer.py, errors.py | T006,T011,T012,T015–T019 | 讲类型规则、名字绑定、优化前后计划等价 |
| **C** | 存储系统 | page.py, file_manager.py, buffer.py | T007,T021–T026,T036 | 讲 slotted page 布局、LRU/FIFO 推演、脏页写回 |
| **D** | 引擎与集成（组长） | executor.py, storage_engine.py, catalog_manager.py, cli/main.py, MiniDB | T001–T003,T027–T034,T037,T039 | 讲执行算子数据流、目录持久化、端到端演示 |

**协作规则**：
1. 契约（contracts/）先行冻结，跨模块改动需对方负责人同意（宪章 I）。
2. 每人对自己的模块测试通过率负责；隐藏测试失败按模块归责修复。
3. 每人必须能讲清自己模块每一行（宪章 V）；答辩前互相抽问彩排。
4. 周节奏建议：第 1–2 周 Phase 1–3，第 3 周 Phase 4（与 Phase 3 并行），第 4 周 Phase 5 集成，第 5 周 Polish + 彩排。

## Parallel Example

```bash
# Foundational 完成后同时启动：
A: T009/T010 (词法语法测试)      B: T011/T012 (语义计划测试)
C: T021/T022 (存储测试)          D: MiniDB 集成骨架 + 契约桩
# US1 内并行：
A: T013 lexer.py                 B: T015 catalog.py（互不依赖）
```
