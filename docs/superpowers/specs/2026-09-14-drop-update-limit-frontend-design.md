# DROP TABLE、UPDATE、LIMIT 前端设计

## 目标与范围

成员 A 为 MiniSQL 增加 `DROP TABLE`、`UPDATE` 和 `LIMIT` 的词法、AST 与语法
前端支持。本轮只修改成员 A 负责的代码、测试和说明文档，不修改语义分析、
计划生成、优化器、执行器、Catalog 或存储实现。

因此，本轮完成后这三类输入可以生成稳定、带源码位置的 AST，但通过 `MiniDB`
执行时仍会由现有后端报告“不支持的语句”或“不支持的 AST”。成员 B、D 后续
分别依据本设计接入语义/计划与执行。

## SQL 文法

### DROP TABLE

```ebnf
drop_table_statement ::= DROP TABLE IDENTIFIER ;
```

只支持删除一张表；不增加 `IF EXISTS`、`CASCADE` 或一次删除多表。

### UPDATE

```ebnf
update_statement ::= UPDATE IDENTIFIER SET assignment { "," assignment }
                     [ WHERE expression ] ;
assignment       ::= IDENTIFIER "=" expression ;
```

`SET` 至少包含一个赋值项。右侧复用现有表达式文法，因此可以表达常量赋值和
`age = age + 1`。列是否存在、表达式类型是否匹配、同一列能否重复赋值由成员 B
在语义阶段决定；Parser 只负责结构。

### LIMIT

```ebnf
select_statement ::= SELECT select_list FROM IDENTIFIER
                     [ WHERE expression ]
                     [ order_by_clause ]
                     [ limit_clause ] ;
limit_clause     ::= LIMIT INTEGER_LITERAL ;
```

`LIMIT` 固定放在 `ORDER BY` 后，只接受十进制非负整数字面量，`LIMIT 0` 合法。
不支持 `OFFSET`、逗号形式、参数或表达式。负数和浮点数由 Parser 作为语法错误
拒绝。

## AST 接口

新增以下节点，均沿用 1-based `line`、`column`：

```python
@dataclass(slots=True, kw_only=True)
class DropTableStmt(ASTNode):
    table: str

@dataclass(slots=True, kw_only=True)
class Assignment(ASTNode):
    column_name: str
    value: Expr

@dataclass(slots=True, kw_only=True)
class UpdateStmt(ASTNode):
    table: str
    assignments: list[Assignment]
    where: Expr | None

@dataclass(slots=True, kw_only=True)
class LimitClause(ASTNode):
    count: int
```

`SelectStmt` 增加向后兼容的默认字段：

```python
limit: LimitClause | None = None
```

`Assignment.line/column` 指向赋值目标列，`LimitClause.line/column` 指向 `LIMIT`
关键字，语句节点指向语句首关键字。`UpdateStmt.assignments` 不允许空列表，
`LimitClause.count` 不允许负数。

## Lexer 与 Parser

Lexer 的关键字集合新增 `DROP`、`UPDATE`、`SET`、`LIMIT`，仍保持关键字大小写
不敏感、词素原样保留。

Parser 的语句分派新增 DROP 和 UPDATE。UPDATE 赋值右侧调用现有表达式入口；
逗号只用于分隔赋值项。SELECT 在可选 ORDER BY 之后解析可选 LIMIT。非法输入
继续统一抛出带行、列、实际 Token 和 expected 集合的 `ParseError`。

## 测试策略

严格采用 Red-Green-Refactor：

1. Lexer 测试先证明四个新词尚未识别为关键字。
2. AST 测试先证明新节点或字段尚不存在。
3. Parser 正常测试覆盖 DROP、多赋值 UPDATE、可选 WHERE、LIMIT 0、LIMIT 与
   ORDER BY 组合及多语句顺序。
4. Parser 错误测试覆盖缺失 TABLE/SET/赋值项、缺失 `=`、负数/浮点/缺失 LIMIT
   数值以及 LIMIT 后多余 Token。
5. 实现后运行 A 的三个测试文件，再运行 Lexer/Parser 指定验收命令，最后运行
   全部现有测试以确认未破坏旧语法。

## 文档同步与跨模块影响

同步修改 `docs/grammar.md`、`README.md`、`docs/design.md`、
`specs/001-minisql-dbms/tasks.md` 和 `docs/PROJECT_CONTEXT.md`，明确这三个扩展
当前只完成成员 A 前端。

冻结的 `specs/001-minisql-dbms/contracts/` 本轮不修改。新增 AST 是 B/D 后续工作
的输入接口，正式冻结前仍需 B、D 和全组复核；文档中必须保留这一待办，不能把
三项功能描述为端到端可执行。
