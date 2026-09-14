# MiniSQL 教学数据库系统

MiniSQL 是一个使用 Python 3.11 和标准库实现的教学型关系数据库。当前 SQL
子集支持 `CREATE TABLE`、`INSERT`、`SELECT`、`DELETE`、`SHOW DATABASES`、
`SHOW TABLES`，以及包含比较、`NOT`、`AND`、`OR` 和括号的 `WHERE` 表达式。
SELECT 还支持多列 `ORDER BY`，每列可使用 `ASC` 或 `DESC`，默认升序。

编译器前端还支持 `DROP TABLE`、`UPDATE` 和 `LIMIT`，目前已接通 Lexer、AST
与 Parser。它们的 Semantic、Planner 和 Executor 尚未接入，因此暂时只能解析
并查看 AST，不能作为 MiniDB 端到端功能使用；尤其 LIMIT 在 B 接入前可能被
旧 Planner 忽略，不能用其执行结果判断限行是否生效。

## 快速开始

一条命令装好环境（自动建虚拟环境、装 pytest、生成 `minidb` 快捷命令）：

```bash
git clone https://github.com/ZenMind531/minisql-dbms.git && cd minisql-dbms && ./install.sh
```

装完在任意目录敲 `minidb` 进入交互式命令行，然后粘贴以下语句：

```sql
CREATE TABLE student(id INT, name VARCHAR(32), age INT);
INSERT INTO student VALUES (1, 'Alice', 20);
SELECT * FROM student WHERE age > 18;
exit;
```

数据文件存放在 `data/` 目录，退出时自动落盘。

> **当前限制**：表结构的持久化（CatalogManager）尚未接通，因此重启后
> 需要重新 `CREATE TABLE`；磁盘上的 `.dat` 数据文件本身是保留的。

## 编译器前端

编译器数据流如下：

```text
SQL 文本 → Lexer → Token 列表 → Parser → AST
```

- `database_system/sql_compiler/lexer.py`：识别 Token、跳过空白与注释，报告
  带行列号的 `LexError`。
- `database_system/sql_compiler/parser.py`：按照 `docs/grammar.md` 进行递归下降
  解析，构造 AST，报告包含实际 Token 与 expected 集合的 `ParseError`。
- `database_system/sql_compiler/ast_nodes.py`：语句、排序项和表达式 AST 接口。

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

常用查询示例：

```sql
SHOW DATABASES;
SHOW TABLES;
SELECT name FROM student ORDER BY age DESC, name ASC;
```

前端扩展语法示例：

```sql
DROP TABLE student;
UPDATE student SET name = 'Alice', age = age + 1 WHERE id = 1;
SELECT * FROM student ORDER BY age DESC LIMIT 10;
```

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

系统面向单用户、单进程教学场景。目前只显示当前数据库，但 SHOW AST 和目录
入口已为后续多数据库切换保留扩展空间。`DROP TABLE`、`UPDATE`、`LIMIT`
当前仅属于编译器前端扩展；`JOIN`、`GROUP BY`、事务和索引不属于当前范围。
