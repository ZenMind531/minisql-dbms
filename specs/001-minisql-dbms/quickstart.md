# Quickstart: 验证指南

## 环境准备

```bash
cd <repo 根目录>
python --version          # 需 3.11
uv pip install pytest     # 或 pip install pytest
```

## 跑测试（每阶段验收入口）

```bash
pytest tests/ -v                    # 全部
pytest tests/test_lexer.py -v       # 单模块
```

## 编译器演示（US1 验收）

```bash
python -m database_system.cli.main --compile-only tests/sql/demo_compiler.sql
# 依次打印每条 SQL 的 Token 流 → AST → 语义 OK → Plan(树形) → 优化后 Plan
```

预期：3 条合法 SQL 全部通过；第 4 条（`... AND;`）打印
`ParseError at line L, column C: unexpected token ';', expected ...`，程序继续。

## 存储演示（US2 验收）

```bash
pytest tests/test_storage.py tests/test_buffer.py -v
# 含：页读写一致性、LRU/FIFO 固定序列命中率、脏页 flush 后重启可读
```

## 端到端演示（US3 验收，即报告附录演示 SQL）

```bash
python -m database_system.cli.main --file tests/sql/demo_e2e.sql --data ./tmp/minidb
```

`demo_e2e.sql` 内容：

```sql
CREATE TABLE student(id INT, name VARCHAR(32), age INT);
INSERT INTO student(id,name,age) VALUES (1,'Alice',20);
INSERT INTO student(id,name,age) VALUES (2,'Bob',17);
INSERT INTO student(id,name,age) VALUES (3,'Tom',22);
SELECT id, name FROM student WHERE age > 18 AND id != 3;
DELETE FROM student WHERE id = 1;
SELECT * FROM student;
```

预期输出：

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

```bash
python -m database_system.cli.main --data ./tmp/minidb
MiniDB> SELECT * FROM student;    # 应返回 Bob、Tom 两行及全部三列，证明重启后数据在
```
