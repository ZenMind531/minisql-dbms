# Implementation Plan: MiniSQL 教学数据库系统

**Branch**: `001-minisql-dbms` | **Date**: 2026-09-07 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/001-minisql-dbms/spec.md`

## Summary

实现一个教学用小型关系数据库系统，覆盖课程三阶段：
① SQL 编译器（词法→语法→语义→逻辑计划→规则式优化）；
② 页式存储（4KB 页管理 + LRU/FIFO 缓冲池）；
③ 数据库引擎（算子执行、行/页映射、系统目录、CLI）。
技术路线：Python 3.11 标准库，递归下降 Parser，slotted-page 页布局，
OrderedDict 实现 LRU，pytest 测试，按模块契约并行开发。

## Technical Context

**Language/Version**: Python 3.11
**Primary Dependencies**: 仅标准库（struct / json / os / logging）；测试用 pytest
**Storage**: 自研页式文件存储（每表一个数据文件 + 系统目录文件，4KB 页）
**Testing**: pytest（单元 + 集成 + 端到端），自研 fuzz 脚本（扩展项）
**Target Platform**: Windows / Linux / macOS 桌面（CLI）
**Project Type**: cli（编译器 + 存储引擎 + CLI 的单体教学系统）
**Performance Goals**: 教学数据量（数千行）下任意单条 SQL 响应 < 1s
**Constraints**: 核心功能仅标准库；页大小固定 4KB；单进程无并发
**Scale/Scope**: 4 类 SQL 语句、6 个逻辑算子、约 3–5k 行代码、4 人分工

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 原则 | 检查结果 |
|------|----------|
| I. 模块化优先 | ✅ 四模块 + contracts/ 冻结接口，结构见下 |
| II. 错误可定位不崩溃 | ✅ 统一错误类型体系（T006）先行，贯穿所有任务 |
| III. 测试先行 | ✅ tasks.md 中每个模块测试任务排在实现任务之前 |
| IV. 文法即文档 | ✅ docs/grammar.md 为独立任务，Parser 任务以其为准 |
| V. 可解释性 | ✅ 阶段验收含讲解演练；报告含 AI 使用说明 |

**Gate: PASS（无违规，Phase 1 后复查仍为 PASS）**

## Project Structure

### Documentation (this feature)

```text
specs/001-minisql-dbms/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output（模块接口契约）
│   ├── compiler-api.md
│   ├── storage-api.md
│   └── engine-api.md
└── tasks.md             # /speckit-tasks 输出
```

### Source Code (repository root)

```text
database_system/
├── sql_compiler/          # SQL 编译器模块
│   ├── lexer.py           # 词法分析器
│   ├── parser.py          # 语法分析器（递归下降）
│   ├── ast_nodes.py       # AST 节点定义
│   ├── semantic.py        # 语义分析器
│   ├── planner.py         # 执行计划生成器
│   ├── optimizer.py       # 规则式优化器
│   └── catalog.py         # 模式目录管理
├── storage/               # 存储系统模块
│   ├── page.py            # 页式存储实现（4KB slotted page）
│   ├── buffer.py          # 缓冲池（LRU/FIFO + 命中统计 + 日志）
│   └── file_manager.py    # 文件与页分配管理
├── engine/                # 数据库引擎模块
│   ├── executor.py        # 执行引擎（算子执行）
│   ├── storage_engine.py  # 行/页映射、序列化
│   └── catalog_manager.py # 系统目录持久化（特殊表）
├── cli/
│   └── main.py            # REPL + 脚本模式入口
├── utils/
│   ├── constants.py       # 页大小等常量
│   ├── errors.py          # 统一错误类型（Lex/Parse/Semantic/Storage/Exec）
│   └── helpers.py
tests/
├── test_lexer.py  test_parser.py  test_semantic.py  test_planner.py
├── test_storage.py  test_buffer.py
├── test_engine.py  test_e2e.py
└── sql/                 # 测试用 SQL 脚本（正常 + 各类错误）
docs/
├── grammar.md           # SQL 子集文法（显式提交）
└── design.md            # AST / Catalog / Plan 结构说明
README.md
```

**Structure Decision**: 单体单项目（single project），直接采用课程建议布局，
按模块目录天然对应 4 人分工边界；契约文件在 contracts/ 先行冻结。

## Complexity Tracking

> 无违规，无需论证。
