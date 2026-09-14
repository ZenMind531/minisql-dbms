# Quickstart: 验证指南

## 环境准备

Windows PowerShell：

```powershell
cd <repo 根目录>
Set-ExecutionPolicy -Scope Process Bypass
.\install.ps1
```

Linux：

```bash
cd <repo 根目录>
bash install.sh
```

## 跑测试（每阶段验收入口）

```powershell
# Windows
.\.venv\Scripts\python.exe -m pytest tests -v

# Linux
./.venv/bin/python -m pytest tests -v
```

## 编译器演示（US1 验收）

```powershell
.\start.ps1 --compile-only tests/sql/demo_compiler.sql   # Windows
bash start.sh --compile-only tests/sql/demo_compiler.sql # Linux
# 依次打印每条 SQL 的 Token 流 → AST → 语义 OK → Plan(树形) → 优化后 Plan
```

预期：3 条合法 SQL 全部通过；第 4 条（`... AND;`）打印
`ParseError at line L, column C: unexpected token ';', expected ...`，程序继续。

## 存储演示（US2 验收）

```bash
pytest tests/test_storage.py tests/test_buffer.py -v
# 含：页读写一致性、LRU/FIFO 固定序列命中率、脏页 flush 后重启可读
```

## 端到端演示（US3 待完成）

当前 `tests/test_engine.py` 已覆盖引擎、目录持久化与重启恢复，但正式交付要求的
`tests/test_e2e.py` 和 `tests/sql/demo_e2e.sql` 尚未创建。以下命令和脚本是
T028/T034 的验收目标，文件落地前不要把本节视为已通过：

```powershell
.\start.ps1 --file tests/sql/demo_e2e.sql --data .\tmp\minidb   # Windows
bash start.sh --file tests/sql/demo_e2e.sql --data ./tmp/minidb # Linux
```

计划中的 `demo_e2e.sql` 基础内容：

```sql
CREATE TABLE student(id INT, name VARCHAR(32), age INT);
INSERT INTO student(id,name,age) VALUES (1,'Alice',20);
INSERT INTO student(id,name,age) VALUES (2,'Bob',17);
INSERT INTO student(id,name,age) VALUES (3,'Tom',22);
SELECT id, name FROM student WHERE age > 18 AND id != 3;
DELETE FROM student WHERE id = 1;
SELECT * FROM student;
```

基础脚本预期输出：

```text
OK
1 row(s) inserted
1 row(s) inserted
1 row(s) inserted
(1, 'Alice')
1 row(s) deleted
(2, 'Bob', 17)
(3, 'Tom', 22)
```

## 持久化验证

完成 T028/T034 后，使用同一数据目录重新启动：

```powershell
.\start.ps1 --data .\tmp\minidb   # Windows
bash start.sh --data ./tmp/minidb # Linux
MiniDB> SELECT * FROM student;    # 应返回 Bob、Tom 两行及全部三列，证明重启后数据在
```
