-- MiniSQL 端到端演示（US3 验收，T034）
-- 运行：bash start.sh --file tests/sql/demo_e2e.sql --data ./tmp/minidb
-- 链路：建表 → 插入 → 条件查询 → 删除 → 全表查询

CREATE TABLE student(id INT, name VARCHAR(32), age INT);
INSERT INTO student(id,name,age) VALUES (1,'Alice',20);
INSERT INTO student(id,name,age) VALUES (2,'Bob',17);
INSERT INTO student(id,name,age) VALUES (3,'Tom',22);

-- age > 18 且 id != 3：只有 Alice 满足
SELECT id, name FROM student WHERE age > 18 AND id != 3;

DELETE FROM student WHERE id = 1;

-- 删完再看：应该只剩 Bob 和 Tom
SELECT * FROM student;
