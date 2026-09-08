<!--
Sync Impact Report
- Version change: 0.0.0 → 1.0.0 (initial ratification)
- Modified principles: none (initial)
- Added sections: Core Principles (I–V), 技术与交付约束, 开发流程与验收, Governance
- Removed sections: none
- Follow-up TODOs: none
-->
# MiniSQL 教学数据库系统 Constitution

## Core Principles

### I. 模块化优先（模块边界不可渗透）

系统严格划分为 `sql_compiler` / `storage` / `engine` / `cli` 四个模块。
模块之间只能通过契约（contracts/）中显式声明的接口通信；禁止跨模块直接
访问内部数据结构。每个模块必须可以独立导入、独立测试。Token、AST、
Catalog、Logical Plan 是模块间的稳定接口，变更需全组评审。

### II. 错误必须可定位、不崩溃

任何非法输入（词法/语法/语义/执行期）都必须返回结构化错误：
`错误类型 + 行号 + 列号 + 原因`，禁止未捕获异常导致程序崩溃或退出。
错误路径与正常路径同等重要，验收时教师会以非法 SQL 做现场 Debug 考察。

### III. 测试先行（NON-NEGOTIABLE）

每个模块先写测试再实现（Red-Green-Refactor）。测试集必须覆盖：
正常用例、词法错误、语法错误、语义错误、边界用例（空输入、极长标识符、
多语句、大小写混合）。代码合入前该模块测试必须全部通过。

### IV. 文法即文档，代码与文法一致

SQL 子集文法必须显式提交于 `docs/grammar.md`，Parser 实现必须与文法
逐条对应；修改文法必须同步修改文档与实现。AST 结构一经定义即为
Parser / Semantic / Planner 三方契约，不得随手改动。

### V. 可解释性高于代码量

每个成员必须能现场讲解自己模块的任意函数、现场画出 AST / Logical Plan、
现场定位错误所属阶段。允许使用大模型辅助开发，但提交人必须理解并能
修改每一行代码；讲不清的代码视同未完成。

## 技术与交付约束

- 语言：Python 3.11，仅用标准库实现核心功能（pytest 仅用于测试）。
- 交付物：源码 + README + grammar.md + 设计文档 + 测试用例与运行结果 +
  实习报告（含 AI 辅助使用说明）+ 一条端到端演示 SQL。
- 范围：必做 CREATE TABLE / INSERT / SELECT / DELETE、WHERE（比较 +
  AND/OR/NOT + 括号）、页式存储（4KB）、LRU/FIFO 缓存、执行引擎、
  系统目录；UPDATE / JOIN / ORDER BY / GROUP BY 等为扩展项，不挤占
  必做项工期。

## 开发流程与验收

- 按课程三阶段推进：SQL 编译器 → 页式存储 → 数据库引擎，每阶段结束
  做一次组内验收（演示 + 讲解）。
- 接口契约（contracts/）先于实现冻结，跨模块改动需对方模块负责人同意。
- 每周一次集成，集成负责人维护主干可运行；演示以 quickstart.md 场景为准。
- 教师验收形式：隐藏测试、随机代码讲解、现场需求修改、现场 Debug，
  全组按此标准自检。

## Governance

本宪章优先级高于个人编码习惯与临时约定。修订需全组讨论、记录原因并
按语义化版本升级（MAJOR：原则删除/重定义；MINOR：新增原则；
PATCH：措辞澄清）。每次阶段验收时核对合规性；违反原则的实现必须
返工或在 plan.md 的 Complexity Tracking 中书面论证。

**Version**: 1.0.0 | **Ratified**: 2026-09-07 | **Last Amended**: 2026-09-07
