"""测试聚合函数执行器"""
import tempfile
from pathlib import Path

from database_system.engine.executor import Executor
from database_system.engine.storage_engine import StorageEngine
from database_system.sql_compiler.catalog import Catalog
from database_system.sql_compiler.lexer import Lexer
from database_system.sql_compiler.parser import Parser
from database_system.sql_compiler.semantic import SemanticAnalyzer
from database_system.sql_compiler.planner import Planner
from database_system.sql_compiler.optimizer import Optimizer


def test_aggregate_executor():
    """测试聚合函数的完整执行"""
    with tempfile.TemporaryDirectory() as tmpdir:
        data_dir = Path(tmpdir)
        engine = StorageEngine(data_dir)
        catalog = Catalog()
        planner = Planner()
        optimizer = Optimizer()
        executor = Executor(engine, catalog)

        def compile_sql(sql: str):
            """编译 SQL 语句"""
            tokens = Lexer(sql).tokenize()
            statements = Parser(tokens).parse()
            analyzed = SemanticAnalyzer(catalog).analyze(statements[0])
            plan = planner.build(analyzed)
            return optimizer.optimize(plan)

        # 1. 创建表
        sql = "CREATE TABLE student (name VARCHAR(50), age INT, score INT);"
        plan = compile_sql(sql)
        result = executor.execute(plan)
        print(f"创建表: {result}")
        assert result == "OK"
        # 2. 插入测试数据
        test_data = [
            ("INSERT INTO student VALUES ('Alice', 20, 85);", "Alice", 20, 85),
            ("INSERT INTO student VALUES ('Bob', 20, 90);", "Bob", 20, 90),
            ("INSERT INTO student VALUES ('Charlie', 21, 75);", "Charlie", 21, 75),
            ("INSERT INTO student VALUES ('David', 21, 95);", "David", 21, 95),
            ("INSERT INTO student VALUES ('Eve', 22, 80);", "Eve", 22, 80),
        ]
        for sql, name, age, score in test_data:
            plan = compile_sql(sql)
            result = executor.execute(plan)
            print(f"插入: {name}, {age}, {score} -> {result}")

        # 3. 测试 COUNT(*)
        print("\n=== 测试 COUNT(*) ===")
        sql = "SELECT COUNT(*) FROM student;"
        plan = compile_sql(sql)
        result = executor.execute(plan)
        print(f"COUNT(*): {result}")
        assert result == [(5,)], f"期望 [(5,)]，得到 {result}"

        # 4. 测试 SUM 和 AVG
        print("\n=== 测试 SUM 和 AVG ===")
        sql = "SELECT SUM(score), AVG(score) FROM student;"
        plan = compile_sql(sql)
        result = executor.execute(plan)
        print(f"SUM(score), AVG(score): {result}")
        total = 85 + 90 + 75 + 95 + 80
        avg = total // 5
        assert result == [(total, avg)], f"期望 [{(total, avg)}]，得到 {result}"

        # 5. 测试 MIN 和 MAX
        print("\n=== 测试 MIN 和 MAX ===")
        sql = "SELECT MIN(score), MAX(score) FROM student;"
        plan = compile_sql(sql)
        result = executor.execute(plan)
        print(f"MIN(score), MAX(score): {result}")
        assert result == [(75, 95)], f"期望 [(75, 95)]，得到 {result}"

        # 6. 测试 GROUP BY
        print("\n=== 测试 GROUP BY ===")
        sql = "SELECT age, COUNT(*) FROM student GROUP BY age;"
        plan = compile_sql(sql)
        result = executor.execute(plan)
        print(f"GROUP BY age: {result}")
        result_sorted = sorted(result)
        expected = [(20, 2), (21, 2), (22, 1)]
        assert result_sorted == expected, f"期望 {expected}，得到 {result_sorted}"

        # 7. 测试 GROUP BY + 多个聚合函数
        print("\n=== 测试 GROUP BY + 多个聚合 ===")
        sql = "SELECT age, COUNT(*), AVG(score) FROM student GROUP BY age;"
        plan = compile_sql(sql)
        result = executor.execute(plan)
        print(f"GROUP BY age with COUNT and AVG: {result}")
        result_sorted = sorted(result)
        expected = [
            (20, 2, (85 + 90) // 2),  # age=20: 2人, avg=87
            (21, 2, (75 + 95) // 2),  # age=21: 2人, avg=85
            (22, 1, 80),               # age=22: 1人, avg=80
        ]
        assert result_sorted == expected, f"期望 {expected}，得到 {result_sorted}"

        # 8. 测试 HAVING
        print("\n=== 测试 HAVING ===")
        sql = "SELECT age, COUNT(*) FROM student GROUP BY age HAVING COUNT(*) > 1;"
        plan = compile_sql(sql)
        result = executor.execute(plan)
        print(f"HAVING COUNT(*) > 1: {result}")
        result_sorted = sorted(result)
        expected = [(20, 2), (21, 2)]
        assert result_sorted == expected, f"期望 {expected}，得到 {result_sorted}"

        # 9. 测试 WHERE + GROUP BY + HAVING
        print("\n=== 测试 WHERE + GROUP BY + HAVING ===")
        sql = """
            SELECT age, COUNT(*), AVG(score)
            FROM student
            WHERE score >= 80
            GROUP BY age
            HAVING COUNT(*) >= 2;
        """
        plan = compile_sql(sql)
        result = executor.execute(plan)
        print(f"复杂查询: {result}")
        # WHERE score >= 80: Alice(20,85), Bob(20,90), David(21,95), Eve(22,80)
        # GROUP BY age: 20有2人, 21有1人, 22有1人
        # HAVING COUNT(*) >= 2: 只有age=20满足
        expected = [(20, 2, (85 + 90) // 2)]
        assert result == expected, f"期望 {expected}，得到 {result}"

        # 10. 测试 COUNT(DISTINCT)
        print("\n=== 测试 COUNT(DISTINCT) ===")
        sql = "SELECT COUNT(DISTINCT age) FROM student;"
        plan = compile_sql(sql)
        result = executor.execute(plan)
        print(f"COUNT(DISTINCT age): {result}")
        assert result == [(3,)], f"期望 [(3,)]，得到 {result}"

        print("\n✅ 所有聚合函数执行器测试通过！")

        # 关闭存储引擎以释放文件句柄
        engine.close()


if __name__ == "__main__":
    test_aggregate_executor()
