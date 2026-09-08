# MiniSQL SQL 子集文法

本文档是 MiniSQL 语法分析器的唯一文法准绳。`lexer.py`、`parser.py`、AST 定义和相关测试必须与本文同步。本文只定义课程必做的 CREATE TABLE、INSERT、SELECT、DELETE；UPDATE、JOIN、ORDER BY、GROUP BY、NULL 等不在当前范围内。

## 1. 记号约定

本文使用扩展巴科斯范式（EBNF）：

- 双引号中的文本表示必须原样出现的终结符，例如 `"("`。
- 大写名称表示 Lexer 产生的 Token 类型，例如 `IDENTIFIER`。
- 小写名称表示非终结符，例如 `select_statement`。
- `[ item ]` 表示 `item` 可出现零次或一次。
- `{ item }` 表示 `item` 可出现零次或多次。
- `( a | b )` 表示在 `a` 与 `b` 中选择一个。
- 关键字大小写不敏感；文法统一使用大写形式书写。

空白和注释由 Lexer 跳过，不进入 Parser。每个 Token 和 AST 节点都必须保留其起始位置的 1-based `line` 与 `column`。

## 2. 顶层结构

```ebnf
program             ::= [ statement_list ] EOF ;

statement_list      ::= statement ";" { statement ";" } ;

statement           ::= create_table_statement
                      | insert_statement
                      | select_statement
                      | delete_statement ;
```

规则说明：

- 空输入、只有空白或只有注释的输入解析为一个空语句列表。
- 每条语句都必须以分号 `;` 结束，包括输入中的最后一条语句。
- 当前版本不接受空语句，因此单独的 `;` 和连续的 `;;` 都是语法错误。
- Parser 成功后必须消费 EOF；最后一条语句之后出现非空白、非注释内容时不得静默忽略。
- 一条输入可以包含多条语句，Parser 按源码顺序返回 `list[Stmt]`。

## 3. CREATE TABLE

```ebnf
create_table_statement
                    ::= CREATE TABLE IDENTIFIER "(" column_definition
                        { "," column_definition } ")" ;

column_definition   ::= IDENTIFIER type_specification ;

type_specification  ::= INT
                      | VARCHAR "(" INTEGER_LITERAL ")" ;
```

语法与边界：

- 表至少包含一列。
- `INT` 后面不允许长度参数。
- `VARCHAR` 必须显式写成 `VARCHAR(n)`。
- `n` 必须是十进制整数，且满足 `1 <= n <= 255`；缺少长度、使用浮点数、带符号数字或越界均作为语法错误处理。
- 重复表名、重复列名等依赖 Catalog 的规则由 SemanticAnalyzer 检查，不由 Parser 判断。

示例：

```sql
CREATE TABLE student(id INT, name VARCHAR(32), age INT);
```

## 4. INSERT

```ebnf
insert_statement    ::= INSERT INTO IDENTIFIER
                        [ "(" identifier_list ")" ]
                        VALUES "(" expression_list ")" ;

identifier_list     ::= IDENTIFIER { "," IDENTIFIER } ;

expression_list     ::= expression { "," expression } ;
```

语法与边界：

- INSERT 一次只插入一行；不支持多组 `VALUES (...), (...)`。
- 列名列表可省略。列的存在性、重复列、列数以及值类型匹配由 SemanticAnalyzer 检查。
- 值位置使用统一表达式文法，但只有能被类型系统接受并最终求值的表达式才是合法插入值。
- 至少提供一个插入值；空的 `VALUES ()` 不合法。

示例：

```sql
INSERT INTO student(id, name, age) VALUES (1, 'Alice', 20);
INSERT INTO student VALUES (2, 'Bob', 17);
```

## 5. SELECT

```ebnf
select_statement    ::= SELECT select_list FROM IDENTIFIER
                        [ WHERE expression ] ;

select_list         ::= "*"
                      | identifier_list ;
```

语法与边界：

- SELECT 只读取一张表；不支持 JOIN、别名或子查询。
- 投影项只能是 `*` 或一个非空列名列表，不支持在 SELECT 列表中书写任意表达式。
- `WHERE` 后必须有表达式；该表达式最终必须具有 BOOL 类型，此规则由 SemanticAnalyzer 检查。
- 表和列是否存在由 SemanticAnalyzer 检查。

示例：

```sql
SELECT * FROM student;
SELECT id, name FROM student WHERE age > 18 AND id != 3;
```

## 6. DELETE

```ebnf
delete_statement    ::= DELETE FROM IDENTIFIER [ WHERE expression ] ;
```

语法与边界：

- 不带 WHERE 时删除目标表的全部记录。
- 带 WHERE 时，表达式最终必须具有 BOOL 类型。
- 不支持多表删除、别名、ORDER BY 或 LIMIT。

示例：

```sql
DELETE FROM student WHERE id = 1;
DELETE FROM student;
```

## 7. 表达式

表达式从低到高的完整优先级为：

1. `OR`
2. `AND`
3. 比较运算符：`=`、`!=`、`>`、`>=`、`<`、`<=`
4. 一元 `NOT`
5. 加减：`+`、`-`
6. 乘除：`*`、`/`
7. 一元正负号：`+`、`-`
8. 基本表达式与括号

这保证课程要求的相对优先级 `NOT > 比较 > AND > OR`。二元运算符均为左结合；比较运算符不可连续使用。

```ebnf
expression          ::= or_expression ;

or_expression       ::= and_expression { OR and_expression } ;

and_expression      ::= comparison_expression { AND comparison_expression } ;

comparison_expression
                    ::= not_expression
                        [ comparison_operator not_expression ] ;

comparison_operator ::= "=" | "!=" | ">" | ">=" | "<" | "<=" ;

not_expression      ::= { NOT } additive_expression ;

additive_expression ::= multiplicative_expression
                        { ( "+" | "-" ) multiplicative_expression } ;

multiplicative_expression
                    ::= unary_expression
                        { ( "*" | "/" ) unary_expression } ;

unary_expression    ::= [ "+" | "-" ] primary_expression ;

primary_expression  ::= IDENTIFIER
                      | INTEGER_LITERAL
                      | FLOAT_LITERAL
                      | STRING_LITERAL
                      | "(" expression ")" ;
```

结构示例：

```sql
age > 18 AND id != 3
```

必须构造为：

```text
BinaryExpr(AND)
├── BinaryExpr(>, IdentifierExpr(age), LiteralExpr(18))
└── BinaryExpr(!=, IdentifierExpr(id), LiteralExpr(3))
```

```sql
1 = 1 AND age > 10 + 8
```

其中 `10 + 8` 必须先于 `>` 结合，以便后续优化器执行常量折叠。

括号显式覆盖默认优先级：

```sql
(age > 18 OR id = 1) AND NOT (name = 'Bob')
```

Parser 只负责按文法构造 AST。诸如对 VARCHAR 使用算术运算、WHERE 结果不是 BOOL 等问题由 SemanticAnalyzer 按集中类型规则报告。

## 8. 词法规则

### 8.1 关键字

```text
SELECT  FROM    WHERE   CREATE  TABLE
INSERT  INTO    VALUES  DELETE  AND
OR      NOT     INT     VARCHAR
```

关键字匹配大小写不敏感，例如 `select`、`SELECT` 和 `SeLeCt` 产生同一种关键字 Token。标识符和字符串内容必须保留源码中的原始内容。

### 8.2 标识符

```ebnf
IDENTIFIER          ::= identifier_start { identifier_part } ;
identifier_start    ::= letter | "_" ;
identifier_part     ::= letter | digit | "_" ;
```

- `letter` 为 ASCII 字母 `A-Z` 或 `a-z`。
- `digit` 为 ASCII 数字 `0-9`。
- 不支持带引号标识符。
- 与关键字大小写无关匹配后，剩余符合规则的词素才产生 IDENTIFIER。

### 8.3 数字常量

```ebnf
INTEGER_LITERAL     ::= digit { digit } ;

FLOAT_LITERAL       ::= digit { digit } "." digit { digit } ;
```

- 正负号是独立运算符，不属于数字 Token，例如 `-12` 产生 `-` 与 INTEGER_LITERAL 两个 Token。
- 浮点数的小数点两侧都必须至少有一位数字；`.5`、`1.` 不合法。
- 数字后直接连接标识符字符（例如 `12abc`）视为非法数字，不拆分为两个合法 Token。
- Lexer 和 Parser 接受 FLOAT_LITERAL 并构造 AST，但当前 MiniSQL 没有 FLOAT
  数据类型；SemanticAnalyzer 必须统一报告“不支持 FLOAT 类型”。FLOAT 不得
  用作列类型，Executor 无需实现浮点运算。

### 8.4 字符串常量

```ebnf
STRING_LITERAL      ::= "'" { string_character | "''" } "'" ;
```

- 字符串使用单引号包围。
- 连续两个单引号 `''` 表示字符串内容中的一个单引号。
- Token 的词素保留原始源码；AST 的字符串值去除外围引号，并把 `''` 解码为 `'`。
- 字符串不得跨越物理行；遇到换行或 EOF 仍未闭合时抛出 LexError。
- 双引号字符串不在支持范围内。

### 8.5 运算符与分隔符

```text
运算符：=  !=  >  >=  <  <=  +  -  *  /
分隔符：(  )  ,  ;
```

Lexer 必须采用最长匹配，因此 `>=`、`<=`、`!=` 各自产生单个 Token。单独的 `!` 非法。

### 8.6 空白与注释

```ebnf
line_comment        ::= "--" { any_character_except_newline }
                        ( newline | EOF ) ;

block_comment       ::= "/*" { block_comment_character } "*/" ;
```

- 空格、制表符和换行均作为 Token 间隔跳过，但必须正确更新行列号。
- 单行注释从 `--` 开始，持续到换行之前或 EOF。
- 多行注释从 `/*` 开始，到第一个 `*/` 结束；当前版本不支持嵌套块注释。
- EOF 前未找到 `*/` 时抛出 LexError，位置指向注释起始处。
- 注释标记出现在字符串中时只是字符串内容。

## 9. 错误要求

### 9.1 词法错误

Lexer 遇到非法字符、非法数字、未闭合字符串或未闭合块注释时，必须抛出统一的 `LexError`。错误包含：

- `type="LexError"`
- 出错词素起始处的 `line`
- 出错词素起始处的 `column`
- 清晰且可操作的 `message`

Lexer 不得吞掉非法字符或用 UNKNOWN Token 继续伪装成功。

### 9.2 语法错误

Parser 遇到不符合本文文法的 Token 时，必须抛出统一的 `ParseError`。错误包含：

- `type="ParseError"`
- 实际 Token 的 `line` 与 `column`
- `unexpected token` 的类型或词素
- 当前文法位置允许的 `expected` Token 集合

例如：

```sql
SELECT name FROM student WHERE age > 18 AND;
```

Parser 在 `;` 处报告错误，expected 集合应包含可开始一元或基本表达式的 Token，例如 `NOT`、`+`、`-`、`IDENTIFIER`、INTEGER_LITERAL、FLOAT_LITERAL、STRING_LITERAL、`(`。

### 9.3 语法与语义的边界

Parser 只判断 Token 序列是否符合本文文法。以下问题交给 SemanticAnalyzer：

- 表或列不存在。
- 表名或列名重复。
- INSERT 列数、列顺序或值类型不匹配。
- 算术、比较或逻辑运算的操作数类型不兼容。
- WHERE 表达式结果不是 BOOL。
- VARCHAR 值按 UTF-8 编码后的字节数超过列定义长度。

## 10. Parser 实现映射

递归下降 Parser 应让函数层次直接对应文法层次，建议至少包含：

```text
parse
parse_statement
parse_create_table
parse_insert
parse_select
parse_delete
parse_expression
parse_or
parse_and
parse_comparison
parse_not
parse_additive
parse_multiplicative
parse_unary
parse_primary
```

不得用与本文优先级不同的通用解析捷径。若修改任何产生式，必须在同一次变更中同步更新 Parser、AST（如受影响）和对应测试；涉及冻结 Token/AST 契约时，先取得规定的评审同意。
