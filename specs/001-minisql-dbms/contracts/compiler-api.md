# Contract: 编译器模块接口（负责人 A、B）

> 冻结后变更需全组评审。类型标注即契约；错误一律抛 `utils.errors` 中的
> `LexError / ParseError / SemanticError`（均含 type/line/column/message）。

## Lexer（负责人 A）

```python
class Lexer:
    def __init__(self, source: str): ...
    def tokenize(self) -> list[Token]: ...
    # 多语句输入：以 ';' 分隔，返回完整流，末尾附 EOF token
    # 非法输入：抛 LexError(type="LexError", line, column, reason)，不崩溃
```

## Parser（负责人 A）

```python
class Parser:
    def __init__(self, tokens: list[Token]): ...
    def parse(self) -> list[Stmt]: ...        # 多条语句 → 语句列表
    # 语法错误：ParseError，message 含 unexpected token 与 expected 集合
```

文法以 `docs/grammar.md` 为唯一准绳；AST 节点定义见 `ast_nodes.py` 与
docs/design.md，**结构变更需 B、D 签字**（下游都依赖它）。

## SemanticAnalyzer（负责人 B）

```python
class SemanticAnalyzer:
    def __init__(self, catalog: Catalog): ...
    def analyze(self, stmt: Stmt) -> Stmt: ...  # 回填类型；错误抛 SemanticError
    # 检查：表/列存在性、类型一致性、INSERT 列数/顺序/类型匹配
```

## Catalog（负责人 B 实现，D 负责持久化）

```python
class Catalog:
    def create_table(self, name: str, columns: list[ColumnDef]) -> None
    def find_table(self, name: str) -> TableSchema | None
    def find_column(self, table: str, column: str) -> ColumnDef | None
    def get_type(self, table: str, column: str) -> TypeSpec | None
    # TypeSpec(kind="INT", length=None) | TypeSpec(kind="VARCHAR", length=1..255)
```

## Planner（负责人 B）

```python
class Planner:
    def build(self, stmt: Stmt) -> PlanNode: ...
    # SELECT → Project → Filter(可选) → SeqScan
    # DELETE → Delete(table) → Filter(可选) → SeqScan(table)
```

## Optimizer（负责人 B）

```python
class Optimizer:
    def optimize(self, plan: PlanNode) -> PlanNode: ...
    # 规则：常量折叠 / 布尔化简 / 冗余节点消除；保证语义等价
```

## 计划序列化（供测试与 D 的 executor 共用）

```python
def plan_to_json(plan: PlanNode) -> dict: ...    # tests 断言用
def plan_to_tree(plan: PlanNode) -> str: ...     # CLI 演示用
```
