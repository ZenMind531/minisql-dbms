# MiniDataGrip / MiniSQL 教学数据库

MiniDataGrip 是 MiniSQL 教学数据库的桌面管理工具。项目使用 Python 3.11 和标准库实现，从 SQL 词法、语法、语义分析和查询优化，一直到执行器、缓冲池、分页存储与磁盘持久化，适合数据库课程设计、课堂演示和源码学习。

项目提供两种使用方式：

- **MiniDataGrip GUI**：对象浏览器、多标签 SQL 控制台、数据编辑和查询计划查看；
- **MiniDB CLI**：交互式执行 SQL、运行 SQL 文件和编译器演示。

## 已支持功能

- SQL：`CREATE TABLE`、`DROP TABLE`、`INSERT`、`SELECT`、`UPDATE`、`DELETE`；
- 查询：`WHERE`、`NOT`、`AND`、`OR`、括号、比较运算、多列 `ORDER BY`、`LIMIT`；
- 元数据：`SHOW DATABASES`、`SHOW TABLES`；
- 编译器：Token、AST、语义检查、逻辑计划、规则优化和错误定位；
- 存储：4KB slotted page、LRU/FIFO 缓冲池、磁盘持久化和 Catalog 恢复；
- GUI：建表、删表、浏览数据、增删改行、保存 SQL 和查看查询计划。

当前定位是单用户、单进程的教学型数据库。`JOIN`、`GROUP BY`、事务、并发控制和索引不在当前实现范围内。

## 3 分钟快速开始

项目要求 **Python 3.11**。

### Windows

```powershell
git clone https://github.com/ZenMind531/minisql-dbms.git
cd minisql-dbms
install.cmd
```

`install.cmd` 会绕过脚本执行策略，并兼容 Windows PowerShell 5.1。安装完成后重新打开终端，直接使用：

```text
minidb          # 启动 CLI
minidatagrip    # 启动 GUI
```

### Linux

Ubuntu/Debian 使用 GUI 时需要安装 Tkinter：

```bash
sudo apt-get update
sudo apt-get install -y python3.11 python3.11-venv python3-tk
git clone https://github.com/ZenMind531/minisql-dbms.git
cd minisql-dbms
bash install.sh
```

安装完成后重新登录终端，使用 `minidb` 启动 CLI，使用 `minidatagrip` 启动 GUI。Linux GUI 需要桌面环境或已配置的 X11/Wayland；纯 SSH 终端可以使用 CLI，但不能直接显示 Tkinter 窗口。

## 使用 MiniDataGrip GUI

### 启动

```text
minidatagrip
```

默认数据保存在项目的 `data/` 目录。点击顶部“打开目录”可以切换数据库目录；关闭程序时会完成存储收尾和数据落盘。

### 界面区域

- **左侧对象浏览器**：查看表和字段，双击表可浏览前 200 行；
- **上方 SQL 控制台**：支持多个标签页，按 `Ctrl+Enter` 执行当前 SQL；
- **下方数据表格**：显示查询结果，提供新增、修改、删除和刷新操作；
- **查询计划**：查看原始计划、优化后计划和 JSON 结构；
- **消息**：查看执行结果、耗时、GUI 生成的 SQL 和错误位置。

### 图形化管理数据

1. 点击“新建表”，填写表名和字段；`VARCHAR` 长度必须在 1 到 255 之间。
2. 双击对象浏览器中的表，打开表数据。
3. 使用结果表上方按钮新增、修改或删除行。
4. 删除表或修改、删除数据前，GUI 会展示将要执行的 SQL 并要求确认。

当前系统没有主键约束。GUI 使用原始行的所有列生成 `WHERE` 条件，因此内容完全相同的多行可能被一起修改或删除，确认窗口会对此作出提醒。

### SQL 控制台与保存

点击“＋ SQL 控制台”创建标签页，输入 SQL 后点击“运行”或按 `Ctrl+Enter`。每个标签右侧都有关闭按钮；关闭包含内容的标签时，可以保存为本地 UTF-8 `.sql` 文件。

可以直接尝试：

```sql
CREATE TABLE student(id INT, name VARCHAR(32), age INT);
INSERT INTO student VALUES (1, 'Alice', 20);
INSERT INTO student VALUES (2, 'Bob', 18);

SELECT * FROM student ORDER BY age DESC LIMIT 10;
UPDATE student SET age = age + 1 WHERE id = 1;
DELETE FROM student WHERE id = 2;
SHOW TABLES;
```

多条语句可以一起执行，但每条语句都必须以分号结束。

### 查询计划

- **原始计划**：Planner 根据语义检查后的 AST 生成的逻辑步骤；
- **优化后计划**：Optimizer 完成常量折叠、布尔化简和冗余节点消除后的计划；
- **JSON**：便于展示或程序读取的结构化优化后计划。

## 使用 MiniDB CLI

进入交互模式：

```text
minidb
```

输入以分号结束的 SQL；语句可以跨行。输入 `exit;` 或 `quit;` 退出。

执行 SQL 文件并指定数据目录：

```powershell
.\start.ps1 --file tests/sql/demo_e2e.sql --data .\tmp\minidb
```

```bash
bash start.sh --file tests/sql/demo_e2e.sql --data ./tmp/minidb
```

只运行编译器演示：

```powershell
.\start.ps1 --compile-only tests/sql/demo_compiler.sql
```

```bash
bash start.sh --compile-only tests/sql/demo_compiler.sql
```

使用 `.\start.ps1 --help` 或 `bash start.sh --help` 查看全部参数。

全局命令会记录安装时的项目目录；移动或删除仓库后，请在新目录重新运行 `install.cmd` 或 `bash install.sh`。Windows 安装器将命令加入当前用户 `PATH`，无需管理员权限，也不受 PowerShell 脚本执行策略影响。

## 系统架构

```text
SQL → Lexer → Token → Parser → AST
    → SemanticAnalyzer → Planner → Optimizer → Logical Plan
    → Executor → StorageEngine → BufferPool / FileManager / Page
```

```text
database_system/
├─ sql_compiler/   # Lexer、Parser、AST、Semantic、Planner、Optimizer
├─ engine/         # MiniDB、Executor、Catalog
├─ storage/        # Page、FileManager、BufferPool、持久化
├─ gui/            # MiniDataGrip 桌面程序
└─ cli/            # 命令行入口

tests/             # 单元、集成和端到端测试
docs/              # 文法、设计、项目上下文和测试报告
specs/             # 需求、计划、任务与接口契约
```

`docs/grammar.md` 是 SQL 文法的唯一准绳，整体设计见 `docs/design.md`，当前实现状态见 `docs/PROJECT_CONTEXT.md`。

## 测试

```powershell
# Windows：完整测试
.\.venv\Scripts\python.exe -m pytest tests -q
```

```bash
# Linux：完整测试
./.venv/bin/python -m pytest tests -q
```

GUI 专项测试：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_gui_app.py tests/test_gui_controller.py tests/test_gui_dialogs.py tests/test_gui_service.py tests/test_gui_sql_builder.py tests/test_gui_theme.py -q
```

当前验证结果：GUI 专项 `20 passed`；完整回归 `296 passed, 4 skipped, 171 subtests passed`。缺少图形显示环境时，少量 Tkinter 测试可能被跳过。

## 数据与注意事项

- 默认数据目录是 `data/`，也可通过 GUI 或 CLI 参数切换；
- 表结构和数据都会持久化，重新启动后可继续查询；
- `INT` 是 32 位有符号整数；
- `VARCHAR(n)` 按 UTF-8 字节数校验，`1 <= n <= 255`；
- SQL 关键字大小写不敏感，标识符和字符串内容保持原样；
- 项目没有事务和并发控制，不要让多个进程同时写同一个数据目录。

## 用途

本项目用于数据库课程设计和教学演示。提交课程作业前，请确认学校对代码引用、协作开发和开源仓库的要求。
