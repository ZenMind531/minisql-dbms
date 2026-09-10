# MiniSQL 教学数据库系统

MiniSQL 是一个使用 Python 3.11 和标准库实现的教学型关系数据库。当前 SQL
子集支持 `CREATE TABLE`、`INSERT`、`SELECT`、`DELETE`，以及包含比较、
`NOT`、`AND`、`OR` 和括号的 `WHERE` 表达式。

## 编译器前端

编译器数据流如下：

```text
SQL 文本 → Lexer → Token 列表 → Parser → AST
```

- `database_system/sql_compiler/lexer.py`：识别 Token、跳过空白与注释，报告
  带行列号的 `LexError`。
- `database_system/sql_compiler/parser.py`：按照 `docs/grammar.md` 进行递归下降
  解析，构造 AST，报告包含实际 Token 与 expected 集合的 `ParseError`。
- `database_system/sql_compiler/ast_nodes.py`：四类语句和表达式 AST 的稳定接口。

文法唯一准绳是 `docs/grammar.md`，AST 与 Parser 的设计说明见
`docs/design.md`。

## 安装与启动

项目要求 Python 3.11。初始化脚本会在仓库内创建 `.venv` 并安装 pytest，
不会把项目依赖安装到系统 Python。

### Windows（PowerShell）

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\install.ps1
.\start.ps1
```

### Linux

Debian/Ubuntu 如果还没有 Python 3.11 和 venv，可先安装系统包：

```bash
sudo apt-get update
sudo apt-get install -y python3.11 python3.11-venv
bash install.sh
bash start.sh
```

进入 `MiniDB>` 后，每条 SQL 必须以分号结束；输入 `exit;` 退出。

## 启动模式

交互模式（数据默认保存在 `data/`）：

```powershell
# Windows
.\start.ps1

# Linux
bash start.sh
```

执行 SQL 文件并选择数据目录：

```powershell
# Windows
.\start.ps1 --file tests/sql/demo_compiler.sql --data .\tmp\minidb

# Linux
bash start.sh --file tests/sql/demo_compiler.sql --data ./tmp/minidb
```

只运行编译器演示，不创建数据库文件：

```powershell
# Windows
.\start.ps1 --compile-only tests/sql/demo_compiler.sql

# Linux
bash start.sh --compile-only tests/sql/demo_compiler.sql
```

查看全部参数：

```powershell
.\start.ps1 --help       # Windows
bash start.sh --help     # Linux
```

## 运行编译器演示（底层 Python 命令）

从命令行传入 SQL：

```powershell
python -m database_system.sql_compiler.demo --compile-only --sql "CREATE TABLE student(id INT, name VARCHAR(32)); SELECT * FROM student;"
```

或者读取 SQL 文件：

```powershell
python -m database_system.sql_compiler.demo --compile-only tests/sql/demo_compiler.sql
```

演示会依次输出 Token、AST、语义检查、原始 Logical Plan 和优化后的 Plan。

## 测试

项目测试使用 pytest，同时保持与标准库 unittest 兼容：

```powershell
# Windows
.\.venv\Scripts\python.exe -m pytest tests -v

# Linux
./.venv/bin/python -m pytest tests -v
```

只运行组员 A 的测试：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_ast_nodes.py tests/test_lexer.py tests/test_parser.py tests/test_sql_cases.py -v
```

编译器案例集合位于 `tests/sql/compiler_cases.json`，包含正常、词法错误、语法
错误和语义错误输入。

## 当前范围

系统面向单用户、单进程教学场景。`UPDATE`、`JOIN`、`ORDER BY`、
`GROUP BY`、事务和索引不属于当前必做范围。
