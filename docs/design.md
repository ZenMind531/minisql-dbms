# MiniSQL 编译器前端设计

## 数据流与边界

```text
SQL source
   ↓ Lexer.tokenize()
list[Token]（末尾包含 EOF）
   ↓ Parser.parse()
list[Stmt]
   ↓ SemanticAnalyzer（成员 B）
```

Lexer 不判断语句结构，Parser 不查询 Catalog，也不进行类型检查。这样词法、
语法和语义错误能够明确归属到各自阶段。

## Token

每个 `Token` 保存 `type`、原始 `lexeme`、1-based `line` 和 `column`。Token
分为 KEYWORD、IDENTIFIER、CONST、OPERATOR、DELIMITER 和 EOF。关键字匹配
大小写不敏感，但词素保持源码拼写；字符串 Token 保留引号和 `''` 转义。

## AST

语句节点为 `CreateTableStmt`、`InsertStmt`、`SelectStmt`、`DeleteStmt`、
`ShowDatabasesStmt`、`ShowTablesStmt`。表达式节点为 `IdentifierExpr`、
`LiteralExpr`、`UnaryExpr`、`BinaryExpr`。

- `SelectStmt.columns=None` 表示 `SELECT *`。
- `SelectStmt.order_by` 保存有序的 `OrderByItem` 列表；每项记录列名及是否降序。
- `InsertStmt.columns=None` 表示省略目标列列表。
- 字符串 AST 值去掉外围引号，并将 `''` 解码为 `'`。
- 正负号使用 UnaryExpr 表示，不属于数字 Token。
- 每个节点携带源码起始位置；B 可以在 `Expr.resolved_type` 回填类型。

## 递归下降 Parser

Parser 的函数层级直接对应 `docs/grammar.md`：

```text
expression
└── or_expression
    └── and_expression
        └── comparison_expression
            └── not_expression
                └── additive_expression
                    └── multiplicative_expression
                        └── unary_expression
                            └── primary_expression
```

越靠下优先级越高，因此满足 `NOT > 比较 > AND > OR`；加减、乘除和一元
正负号也按文法显式分层。二元运算使用循环构造左结合树，比较只允许出现一次。
括号重新进入 `expression`，覆盖默认优先级。嵌套深度设有安全上限，过深输入
报告 `ParseError`，不会泄漏 Python `RecursionError`。

## SHOW 与排序计划

`SHOW DATABASES` 显示当前 `--data` 目录名称；`SHOW TABLES` 显示按名称升序排列
的用户表，并隐藏内部 `__catalog__` 表。SHOW 节点保持独立，后续增加多数据库
切换时可以扩展目录提供者，而无需改变现有语法。

SELECT 的 ORDER BY 支持多列，每列可独立使用 `ASC`、`DESC`，省略方向时默认
为 `ASC`。排序计划位于投影之前：

```text
Project → Sort → Filter（可选）→ SeqScan
```

因此排序列不必出现在 SELECT 列表中。执行器从最后一个排序键向前进行稳定排序，
从而保持 SQL 中从左到右的排序优先级。

## 错误处理

Lexer 对非法字符、非法数字、未闭合字符串和块注释抛 `LexError`。Parser 对
缺失关键字、分隔符、表达式或非法 VARCHAR 长度抛 `ParseError`。错误保存实际
Token 的行列号，ParseError 消息同时包含 actual Token 和 expected 集合。

## 示例

```sql
SELECT name FROM student WHERE age > 18 AND id != 3;
SELECT name FROM student ORDER BY age DESC, name ASC;
SHOW DATABASES;
SHOW TABLES;
```

关键表达式 AST：

```text
BinaryExpr(AND)
├── BinaryExpr(>, IdentifierExpr(age), LiteralExpr(18))
└── BinaryExpr(!=, IdentifierExpr(id), LiteralExpr(3))
```
