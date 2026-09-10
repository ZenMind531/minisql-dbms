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

语句节点为 `CreateTableStmt`、`InsertStmt`、`SelectStmt`、`DeleteStmt`。表达式
节点为 `IdentifierExpr`、`LiteralExpr`、`UnaryExpr`、`BinaryExpr`。

- `SelectStmt.columns=None` 表示 `SELECT *`。
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

## 错误处理

Lexer 对非法字符、非法数字、未闭合字符串和块注释抛 `LexError`。Parser 对
缺失关键字、分隔符、表达式或非法 VARCHAR 长度抛 `ParseError`。错误保存实际
Token 的行列号，ParseError 消息同时包含 actual Token 和 expected 集合。

## 示例

```sql
SELECT name FROM student WHERE age > 18 AND id != 3;
```

关键表达式 AST：

```text
BinaryExpr(AND)
├── BinaryExpr(>, IdentifierExpr(age), LiteralExpr(18))
└── BinaryExpr(!=, IdentifierExpr(id), LiteralExpr(3))
```
