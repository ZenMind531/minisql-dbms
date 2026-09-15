# MiniSQL 测试用例清单

> 范围：`tests/` 全量（17 个测试文件 + 1 套 SQL 用例集）
> 环境：Linux，仓库内 `.venv`，Python 3.14.4，pytest 9.1.1
> 日期：2026-09-15
> 命令：`PYTHONPATH=. .venv/bin/python -m pytest tests -q`

结果：**259 passed, 171 subtests passed**

---

## 0. 总览

| 层次 | 测试文件 | 条数 | 这一层在守什么 |
|---|---|---|---|
| **编译器前端** | `test_lexer.py` | 12 | 字符流 → Token，位置信息准确，非法字符拒绝 |
| | `test_parser.py` | 19 | Token → AST，优先级/结合性正确，语法错误带期望集合 |
| | `test_ast_nodes.py` | 10 | AST 节点自身的类型约束（不依赖下游） |
| **语义与计划** | `test_semantic.py` | 32 | 类型推导、名字绑定、INSERT 列匹配 |
| | `test_planner.py` | 47 | 计划树形状 + 优化器等价性与安全性 |
| **存储层** | `test_storage.py` | 9 | 4KB slotted page 的增删改查与序列化 |
| | `test_buffer.py` | 5 | LRU/FIFO 淘汰、pin、脏页回写 |
| | `test_storage_persist.py` | 1 | 跨进程持久化 |
| **引擎与目录** | `test_engine.py` | 38 | 目录持久化、损坏数据拒绝、建表回滚、DROP/LIMIT |
| | `test_catalog.py` | 13 | 内存元数据的校验与不可变性 |
| **组合验证** | `test_new_features.py` | 20 | DROP/UPDATE/LIMIT/SHOW/ORDER BY 的语义与计划 |
| | `test_show_order.py` | 6 | SHOW 与多列 ORDER BY 端到端 |
| | `test_errors.py` | 15 | 五类错误的契约（type/line/column/message） |
| | `test_demo.py` | 19 | 编译管线各阶段与 `--compile-only` 入口 |
| **端到端与 CLI** | `test_e2e.py` | 3 | 真实子进程跑脚本 + 重启后数据仍在 |
| | `test_cli.py` | 7 | 命令行三种模式、错误出口、readline 历史 |
| | `test_sql_cases.py` | 3 | 34 条命名 SQL 用例集的驱动与覆盖校验 |
| | `tests/sql/compiler_cases.json` | (34) | 数据驱动的 SQL 用例（见 §9） |
| | **合计** | **259** | |

---

## 1. 编译器前端

### 1.1 词法分析 `tests/test_lexer.py`（12）

| 用例 | 验证什么 |
|---|---|
| `test_tokenizes_keywords_identifiers_and_delimiters` | 关键字、标识符、分隔符（`( ) , ;`）各自成 Token，边界切分正确 |
| `test_recognizes_every_supported_keyword_case_insensitively` | 文法里的每个关键字在任意大小写下都能识别 |
| `test_tokenizes_integer_float_and_escaped_string_constants` | 整数、浮点、字符串字面量的 Token；`''` 转义还原为单个引号 |
| `test_skips_line_and_block_comments_while_tracking_positions` | `--` 与 `/* */` 注释被跳过，且跳过之后行列号仍然对得上 |
| `test_tracks_positions_across_whitespace_and_newlines` | 跨空白与换行后，Token 的行列号仍指向源码真实位置 |
| `test_uses_longest_match_for_operators` | 最长匹配：`<=` 不会被切成 `<` + `=`，`!=`、`>=` 同理 |
| `test_rejects_illegal_character_at_its_position` | 非法字符（如 `@`）报 `LexError`，行列号指向该字符本身 |
| `test_rejects_number_followed_by_identifier_characters` | `12abc` 报错——数字不能直接接标识符字符 |
| `test_rejects_decimal_without_digits_on_both_sides` | `.5` / `1.` 这类两侧缺数字的小数被拒绝 |
| `test_string_cannot_cross_a_physical_line` | 字符串不允许跨物理行，换行即报错 |
| `test_unterminated_string_reports_opening_quote` | 未闭合字符串的报错位置是**开引号**，不是文件末尾 |
| `test_unterminated_block_comment_reports_comment_start` | 未闭合块注释的报错位置是 `/*` 处 |

### 1.2 语法分析 `tests/test_parser.py`（19）

**语句结构（8 条）**

| 用例 | 验证什么 |
|---|---|
| `test_parses_create_table_and_varchar_length` | `CREATE TABLE` 的列定义与 `VARCHAR(n)` 长度进入 AST |
| `test_parses_insert_with_and_without_target_columns` | `INSERT` 带列名与不带列名两种形态的 AST 区分 |
| `test_parses_select_star_named_columns_and_delete` | `SELECT *`、具名列、`DELETE` 三类语句的 AST 结构 |
| `test_parses_drop_update_and_limit` | `DROP TABLE` / `UPDATE` / `LIMIT` 三种扩展语句可解析 |
| `test_update_where_is_optional_and_limit_zero_is_valid` | `UPDATE` 的 `WHERE` 可省；`LIMIT 0` 是合法值不是错误 |
| `test_empty_and_comment_only_input_return_no_statements` | 空输入、纯注释输入解析为**空语句列表**，不报错 |
| `test_preserves_statement_order_in_multi_statement_input` | 多语句输入保持源码顺序 |
| `test_requires_semicolon_after_every_statement` | 每条语句必须以 `;` 结束 |

**表达式优先级（4 条）**

| 用例 | 验证什么 |
|---|---|
| `test_arithmetic_precedence_and_left_associativity` | `*` `/` 优先于 `+` `-`；同级左结合（`10-3-2` 是 `(10-3)-2`） |
| `test_not_comparison_and_or_precedence` | 优先级链 `NOT > 比较 > AND > OR`，用 AST 树形断言 |
| `test_parentheses_override_default_precedence` | 括号能覆盖默认优先级 |
| `test_literals_and_unary_signs_have_expected_ast_values` | 字面量取值与一元正负号的 AST 表示 |

**错误路径（7 条）**

| 用例 | 验证什么 |
|---|---|
| `test_reports_missing_expression_after_and` | `AND;` 这类缺右操作数报错，且错误信息带**期望集合** |
| `test_rejects_chained_comparisons` | `a < b < c` 被拒绝（不做隐式结合） |
| `test_rejects_empty_and_consecutive_statements` | 空语句、连续 `;;` 报错 |
| `test_varchar_requires_integer_length_in_range` | `VARCHAR` 长度必须是整数且落在 `[1,255]` |
| `test_varchar_accepts_inclusive_boundaries` | 边界值 1 与 255 **包含在内**（off-by-one 防线） |
| `test_drop_update_and_limit_report_missing_or_invalid_parts` | 三种扩展语句的残缺写法（缺表名、缺 `SET`、负数 `LIMIT`）各自报错 |
| `test_excessive_parentheses_raise_parse_error_not_recursion_error` | **括号过度嵌套时报 `ParseError` 而不是 `RecursionError`**——前端已对深递归做了防护 |

### 1.3 AST 节点 `tests/test_ast_nodes.py`（10）

| 用例 | 验证什么 |
|---|---|
| `test_statement_nodes_match_the_four_supported_sql_statements` | 语句节点与四类 SQL 一一对应 |
| `test_column_definition_only_accepts_int_or_bounded_varchar` | 列类型只接受 `INT` 与范围内的 `VARCHAR(n)` |
| `test_type_spec_rejects_invalid_varchar_lengths_directly` | 不经解析器、直接构造非法长度也被拒绝 |
| `test_literal_value_must_match_its_literal_kind` | 字面量节点的值与种类必须自洽（字符串节点不能装整数） |
| `test_select_star_and_explicit_columns_have_one_unambiguous_field` | `SELECT *` 与具名列共用同一字段且语义无歧义 |
| `test_unary_minus_is_a_separate_normalized_ast_node` | 一元负号是独立节点，不被折叠进字面量 |
| `test_float_literal_is_representable_without_becoming_a_column_type` | 浮点可作**字面量**存在，但不能当**列类型** |
| `test_expression_type_can_be_filled_by_semantic_analysis` | 表达式节点的类型字段留给语义阶段回填 |
| `test_update_requires_assignment_and_limit_rejects_negative_count` | `UPDATE` 必须带赋值；`LIMIT` 拒绝负数 |
| `test_drop_update_and_limit_nodes_preserve_frontend_structure` | 三个扩展节点的字段结构与前端约定一致 |

---

## 2. 语义分析与计划

### 2.1 语义分析 `tests/test_semantic.py`（32）

**类型推导（12 条）**

| 用例 | 验证什么 |
|---|---|
| `test_integer_arithmetic_resolves_to_int` | 整数四则的结果类型是 `INT` |
| `test_integer_comparisons_resolve_to_bool_and_bind_column_type` | 比较结果为 `BOOL`，同时把列的类型绑定回节点 |
| `test_string_equality_and_inequality_resolve_to_bool` | 字符串 `=` / `!=` 结果为 `BOOL` |
| `test_unary_integer_signs_resolve_to_int` | 一元正负号保持 `INT` |
| `test_and_or_not_resolve_to_bool` | 三个逻辑运算符结果为 `BOOL` |
| `test_bool_equality_is_valid_but_bool_arithmetic_is_not` | `BOOL` 能比较、不能参与算术 |
| `test_logical_operators_require_bool_operands` | 逻辑运算符两侧必须是 `BOOL` |
| `test_int_plus_varchar_is_rejected` | `INT + VARCHAR` 类型错误 |
| `test_mixed_type_comparison_is_rejected` | 跨类型比较被拒绝 |
| `test_float_is_rejected_even_when_ast_can_represent_it` | 浮点**能进 AST 但过不了语义**——分层拒绝 |
| `test_long_string_reports_semantic_error_not_type_constructor_error` | 超长字符串报 `SemanticError`，不能漏出底层构造器异常 |
| `test_varchar_rejects_values_over_utf8_byte_limit` | `VARCHAR` 长度按 **UTF-8 字节**算，中文超限要报错 |

**名字绑定与表/列解析（7 条）**

| 用例 | 验证什么 |
|---|---|
| `test_valid_select_star_and_named_columns` | `SELECT *` 与具名列都能解析成功 |
| `test_select_missing_table` | 表不存在报错 |
| `test_select_missing_projection_column` | 投影列不存在报错 |
| `test_select_missing_where_column_reports_expression_position` | `WHERE` 里列不存在时，报错位置指向**该表达式**而非语句开头 |
| `test_bindings_include_projection_and_where_columns_and_reset` | 绑定表覆盖投影列与 `WHERE` 列，且每条语句后重置（不串味） |
| `test_valid_delete_and_missing_delete_column` | `DELETE` 的正常与缺列两种路径 |
| `test_insert_and_delete_missing_tables` | `INSERT`/`DELETE` 目标表不存在报错 |

**建表约束（5 条）**

| 用例 | 验证什么 |
|---|---|
| `test_create_valid_table` | 合法建表通过分析 |
| `test_create_duplicate_column_names_is_rejected` | 同表内列名重复报错 |
| `test_create_existing_table_is_rejected` | 重名表报错 |
| `test_create_analysis_does_not_register_table` | **分析阶段不改目录**——建表的副作用归执行器，语义层保持纯函数 |
| `test_varchar_accepts_empty_short_and_exact_byte_limit` | 空串、短串、恰好等于字节上限的串都合法 |

**INSERT 匹配（7 条）**

| 用例 | 验证什么 |
|---|---|
| `test_insert_matches_explicit_column_order` | 显式列名时按列名匹配 |
| `test_insert_value_count_must_match_schema` | 省略列名时值的个数必须等于列数 |
| `test_insert_value_count_must_match_explicit_columns` | 显式列名时值的个数必须等于列名个数 |
| `test_insert_rejects_unknown_or_duplicate_target_columns` | 目标列不存在或重复报错 |
| `test_insert_cannot_omit_columns_without_defaults` | 不允许漏列（本系统无默认值） |
| `test_insert_rejects_both_type_mismatch_directions` | 类型不匹配的两个方向（宽→窄、窄→宽）都拒绝 |
| `test_insert_rejects_column_references_without_source_row` | `INSERT ... VALUES (id)` 没有源行，引用列必须报错 |

**WHERE 约束（1 条）**

| 用例 | 验证什么 |
|---|---|
| `test_select_and_delete_where_require_bool` | `SELECT` 与 `DELETE` 的 `WHERE` 都必须是布尔表达式（跨类型比较的拒绝见上「类型推导」组） |

### 2.2 计划与优化 `tests/test_planner.py`（47）

**计划树形状（8 条）**

| 用例 | 验证什么 |
|---|---|
| `test_select_with_where_is_project_over_filter_over_scan` | 计划树严格是 `Project → Filter → SeqScan` |
| `test_select_without_where_is_project_over_scan` | 无 `WHERE` 时没有多余的 Filter 层 |
| `test_delete_with_where_preserves_target_and_filtered_scan` | `DELETE` 计划保留目标表名与过滤扫描 |
| `test_delete_without_where_is_delete_over_scan` | 无 `WHERE` 的删除是 Delete 直接套 Scan（全表删） |
| `test_projection_preserves_requested_column_order` | 投影列顺序按用户书写顺序，不按表定义顺序 |
| `test_select_star_is_represented_before_optimization` | 优化前 `SELECT *` 有明确表示（不提前坍缩） |
| `test_unoptimized_plan_preserves_full_predicate` | 未优化的计划保留完整谓词，不偷偷化简 |
| `test_plan_to_json_is_json_serializable_and_repeatable` | `plan_to_json` 可 JSON 序列化且多次调用结果一致 |

**优化器正确性（10 条）**

| 用例 | 验证什么 |
|---|---|
| `test_constant_arithmetic_is_folded_inside_comparison` | `age > 10+8` 折叠成 `age > 18` |
| `test_combined_folding_and_boolean_simplification` | 折叠与布尔化简可叠加生效 |
| `test_constant_true_filter_is_removed_but_projection_is_kept` | `WHERE true` 的 Filter 被摘掉，但 Project 必须留着 |
| `test_redundant_star_projection_is_removed` | 冗余的 `SELECT *` 投影被消除 |
| `test_true_and_predicate_is_simplified_on_either_side` | `true AND p` 与 `p AND true` 都能化简 |
| `test_nonconstant_and_is_not_incorrectly_dropped` | 非常量的 `AND` 不会被误删 |
| `test_delete_optimization_keeps_delete_target_and_scan` | 优化删除计划时不能动目标表与扫描 |
| `test_already_simple_plan_is_preserved` | 已经最简的计划不被画蛇添足 |
| `test_optimizing_twice_has_the_same_result` | **幂等**：优化两次结果相同 |
| `test_optimization_preserves_predicate_results_at_and_around_boundary` | 边界值前后（18、19、20）优化前后选出的行一致 |

**恒假谓词防线（8 条）** ⚠️ 这一组守的是**灾难级 bug**

| 用例 | 验证什么 |
|---|---|
| `test_constant_false_delete_is_not_turned_into_a_full_table_delete` | **`DELETE ... WHERE false` 绝不能变成全表删除**——优化器在这里犯错就是数据全丢 |
| `test_constant_false_delete_filter_is_not_dropped` | 恒假的删除过滤条件不能被摘掉 |
| `test_constant_false_select_filter_is_not_dropped` | 恒假的查询过滤条件不能被摘掉 |
| `test_constant_false_select_star_filter_is_not_dropped` | 同上，`SELECT *` 路径也要守住 |
| `test_false_and_condition_still_selects_no_rows` | `false AND p` 仍然选不出任何行 |
| `test_false_or_condition_keeps_the_surviving_condition` | `false OR p` 化简后保留 `p` |
| `test_negated_constant_true_selects_no_rows` | `NOT true` 选不出行 |
| `test_true_or_condition_selects_every_row` | `true OR p` 选出全部行 |

**优化等价性（4 条）**

| 用例 | 验证什么 |
|---|---|
| `test_equivalence_holds_for_representative_predicates` | 一组代表性谓词优化前后结果集相同 |
| `test_folding_keeps_integer_division_semantics` | 折叠遵守整数除法语义（向零截断），不变成浮点除 |
| `test_folding_negative_literals_keeps_the_same_rows` | 负数折叠不改变结果 |
| `test_unary_minus_on_a_literal_is_folded_without_changing_rows` | 字面量一元负号可折叠且结果不变 |

**折叠安全性（10 条）**

| 用例 | 验证什么 |
|---|---|
| `test_division_by_zero_is_not_folded_and_does_not_raise` | 常量除零**不折叠也不抛异常**（留到执行期按行报错） |
| `test_division_by_zero_inside_a_constant_filter_does_not_raise` | 恒量过滤里的除零同样不炸 |
| `test_division_by_zero_in_delete_does_not_raise_or_drop_the_filter` | 删除语句里的除零不能抛异常、也不能把过滤条件丢掉 |
| `test_float_literals_are_not_folded` | 浮点不折叠（避免精度语义漂移） |
| `test_string_arithmetic_is_left_untouched` | 字符串算术原样保留，交给后续报错 |
| `test_string_comparison_folds_to_a_boolean_without_raising` | 字符串比较可安全折叠为布尔 |
| `test_unequal_string_comparison_selects_no_rows` | 常量字符串不等比较选出零行 |
| `test_mixed_type_comparison_is_left_untouched` | 跨类型比较不动它 |
| `test_optimizer_does_not_mutate_the_input_plan` | **优化器不改动传入的计划对象**（纯函数） |
| `test_unsupported_plan_node_is_reported_as_a_type_error` | 不支持的节点报 `TypeError`，不静默通过 |

**折叠后布尔表示（7 条）**

| 用例 | 验证什么 |
|---|---|
| `test_folded_false_predicate_is_a_bool_typed_literal` | 折叠出的 `false` 是 `BOOL` 类型字面量 |
| `test_folded_true_predicate_is_the_integer_one` | 折叠出的 `true` 编码为整数 1 |
| `test_folded_false_predicate_is_the_integer_zero_not_a_python_bool` | **是整数 0，不是 Python 的 `False`**——序列化契约要求 |
| `test_folded_false_predicate_uses_the_integer_source_form` | 用整数源码形式表示，保证往返一致 |
| `test_folded_boolean_serializes_as_its_integer_encoding` | 序列化输出为整数编码 |
| `test_folded_arithmetic_stays_an_int_typed_integer_literal` | 算术折叠的结果仍是 `INT` 整数字面量 |
| `test_arithmetic_folding_is_never_mistaken_for_a_truth_value` | **算术结果不能被当成真值**（`0` 不等于 `false`） |

---

## 3. 存储层

### 3.1 页与文件 `tests/test_storage.py`（9）

| 用例 | 验证什么 |
|---|---|
| `test_insert_and_get_row` | 插入一行返回槽号 0，按槽号读回内容一致 |
| `test_full_page_returns_none` | 连续插入直到装不下，`insert_row` 返回 `None`（页满判定），已有行仍可读 |
| `test_delete_removes_from_rows` | `delete_row` 后 `rows()` 不再产出该行，其它行不受影响 |
| `test_to_from_bytes_roundtrip` | `to_bytes()` 长度恰好 4096；`from_bytes` 还原后 `page_id` 与各行内容一致 |
| `test_update_row_same_length_in_place` | `update_row` 同长度时**原地覆盖**，槽号不变 |
| `test_update_row_length_change_moves_slot` | `update_row` 长度变化时退化为删除+插入，返回新槽号 |
| `test_update_row_on_full_page_same_length_still_works` | 页满时仍可对已有行做同长度原地改写 |
| `test_file_write_read` | 新文件 `page_count()==1`（仅文件头页）；分配页→写页→按页号读回一致 |
| `test_free_reuse_and_restart` | 分配 3 页→释放页 2→关闭→重开；`page_count()` 正确，再次分配复用页 2 |

### 3.2 缓冲池 `tests/test_buffer.py`（5）

| 用例 | 验证什么 |
|---|---|
| `test_lru_evicts_least_recent` | LRU 固定序列下淘汰最久未使用的页；命中/未命中计数正确 |
| `test_fifo_evicts_oldest` | FIFO 固定序列下淘汰最早进入的页；计数正确 |
| `test_pinned_page_not_evicted` | 被 pin 的页不淘汰；全部帧被 pin 时抛 `StorageError` |
| `test_dirty_page_flushed_on_eviction` | 脏页淘汰前写回磁盘，`evictions`/`flushes` 计数正确 |
| `test_flush_all_writes_dirty_pages` | `flush_all()`（CLI 退出前调用）把脏页写回磁盘 |

### 3.3 持久化 `tests/test_storage_persist.py`（1）

| 用例 | 验证什么 |
|---|---|
| `test_restart_persistence` | 独立进程写入并退出后，新进程重新打开文件能读回全部数据（页 0 文件头与数据页均持久） |

辅助脚本：`tests/_persist_helper.py`（不属于测试用例，供持久化测试以独立进程调用）。

---

## 4. 引擎与目录

### 4.1 系统目录持久化 `tests/test_engine.py`（38）

**引导与重建（3 条）**

| 用例 | 验证什么 |
|---|---|
| `test_fresh_manager_bootstraps_queryable_catalog` | 全新数据目录自动引导 `__catalog__` 且可立即查询 |
| `test_register_table_writes_one_catalog_row_per_column` | 登记一张表 → 目录里一行对应一列 |
| `test_reopening_reconstructs_exact_schema` | 重启后重建出的 schema 与原定义逐字段一致 |

**损坏数据拒绝（13 条）** ⚠️ 数据损坏必须干净报错，不能崩

| 用例 | 验证什么 |
|---|---|
| `test_load_rejects_invalid_catalog_type` | 目录里出现不支持的类型标识 → 拒绝加载 |
| `test_load_rejects_non_contiguous_catalog_order[duplicate]` | 列序号重复 → 拒绝 |
| `test_load_rejects_non_contiguous_catalog_order[gapped]` | 列序号有空洞 → 拒绝 |
| `test_load_rejects_duplicate_catalog_column` | 同表同列登记两次 → 拒绝 |
| `test_load_rejects_missing_table_file` | 目录说有某表、`.dat` 文件却不在 → 拒绝 |
| `test_load_reports_corrupt_catalog_file_as_storage_error` | 目录文件本身损坏 → 报 `StorageError` |
| `test_load_rejects_truncated_existing_file_without_overwriting[catalog]` | 目录文件被截断 → 拒绝**且不覆盖**原文件 |
| `test_load_rejects_truncated_existing_file_without_overwriting[table]` | 数据表文件被截断 → 拒绝**且不覆盖** |
| `test_load_wraps_catalog_scan_and_decode_corruption[invalid-utf8-UnicodeDecodeError]` | 目录里 UTF-8 非法 → 包装成 `StorageError` |
| `test_load_wraps_catalog_scan_and_decode_corruption[invalid-slot-count-error]` | 槽数非法 → 包装 |
| `test_load_wraps_catalog_scan_and_decode_corruption[missing-declared-page-ValueError]` | 声明的页不存在 → 包装 |
| `test_load_adds_catalog_context_to_storage_read_failures[os-error]` | 底层 OS 错误补上目录上下文后抛出 |
| `test_load_adds_catalog_context_to_storage_read_failures[storage-error]` | 同上，`StorageError` 路径 |

**建表原子性与回滚（5 条）**

| 用例 | 验证什么 |
|---|---|
| `test_create_table_rolls_back_only_new_file_when_catalog_write_fails` | 目录写入失败时只回滚**新建的数据文件**，不误伤已有文件 |
| `test_create_table_removes_partial_catalog_rows_when_second_insert_fails` | 登记到一半失败 → 清掉已写入的半截目录行 |
| `test_create_table_reports_registration_and_cleanup_failures` | 登记失败与清理失败都要如实上报 |
| `test_storage_create_rejects_an_existing_table_file` | 同名数据文件已存在时拒绝创建 |
| `test_storage_remove_rejects_system_catalog` | **`__catalog__` 不允许被删**（系统表保护） |

**长名与边界（2 条）**

| 用例 | 验证什么 |
|---|---|
| `test_register_rejects_names_over_255_utf8_bytes_before_writing[table-name]` | 表名超 255 字节 → **写入前**就拒绝 |
| `test_register_rejects_names_over_255_utf8_bytes_before_writing[later-column-name]` | 后续列名超限同样在写入前拒绝 |

**执行器与端到端（15 条）**

| 用例 | 验证什么 |
|---|---|
| `test_minidb_create_survives_close_and_restart` | `MiniDB` 建表 → 关闭 → 重启，表还在 |
| `test_executor_two_argument_constructor_remains_supported` | 两参数构造器（无 CatalogManager）仍可用，向后兼容 |
| `test_unimplemented_plan_reports_exec_error_instead_of_crashing` | **前端能解析、执行器没实现的节点必须干净报错**，且数据不被改动（当前以 `UPDATE` 为哨兵） |
| `test_insert_int_out_of_range_raises_storage_error` | 超出 `INT` 范围的值报 `StorageError` |
| `test_insert_row_wider_than_a_page_raises_storage_error` | 单行宽度超过一页 → 报 `StorageError` |
| `test_insert_maps_values_by_column_name_not_source_order` | 值的落位按**列名**而非书写顺序 |
| `test_insert_reordered_columns_works_across_types` | 打乱列名顺序、跨类型插入仍然正确 |
| `test_drop_table_removes_file_and_metadata` | `DROP TABLE` 同时删掉文件与目录登记 |
| `test_dropped_table_stays_dropped_after_restart` | 重启后不复活 |
| `test_recreating_a_dropped_table_starts_empty` | 删表后重建同名表是**空表**（没读到旧数据） |
| `test_limit_takes_the_first_n_rows` | `LIMIT n` 取前 n 行，顺序为存储顺序 |
| `test_limit_zero_returns_nothing` | `LIMIT 0` 返回空 |
| `test_limit_beyond_the_table_returns_everything` | `LIMIT` 超过总行数 → 返回全部 |
| `test_limit_applies_after_order_by` | **先排序再截断**——若顺序反了会拿到「最小的 n 个」而不是「前 n 个」 |
| `test_limit_applies_after_where` | 先过滤再截断 |

### 4.2 内存目录 `tests/test_catalog.py`（13）

| 用例 | 验证什么 |
|---|---|
| `test_create_and_find_preserve_name_types_and_column_order` | 建表后名字、类型、列顺序原样保存 |
| `test_lookup_preserves_identifier_case` | 查询保留标识符大小写（大小写不敏感但不改写） |
| `test_missing_table_and_column_return_none` | 找不到时返回 `None`，不抛异常（存在性判定归上层） |
| `test_duplicate_table_does_not_replace_original` | 重名建表**不会覆盖**原表 |
| `test_duplicate_columns_fail_atomically_and_report_position` | 列名重复时原子失败，并报出重复列的位置 |
| `test_empty_schema_is_rejected` | 零列的表被拒绝 |
| `test_bool_is_not_a_supported_column_type` | `BOOL` 不能作为列类型（只能作表达式结果） |
| `test_varchar_accepts_inclusive_length_boundaries` | 长度 1 与 255 均可 |
| `test_varchar_revalidates_mutable_column_definitions` | 传入可变列定义被改动后，再次校验能发现 |
| `test_input_mutation_does_not_change_catalog` | **外部改动传入对象不影响目录内部**（深拷贝防线） |
| `test_lookup_mutation_does_not_change_catalog` | 外部改动查出的对象同样不影响内部 |
| `test_catalog_instances_are_independent` | 两个 Catalog 实例互不干扰 |
| `test_same_column_name_in_different_tables_is_allowed` | 不同表可以有同名列 |

---

## 5. 组合验证

### 5.1 新增特性 `tests/test_new_features.py`（20）

**DROP TABLE 语义（3 条）**

| 用例 | 验证什么 |
|---|---|
| `test_drop_existing_table_succeeds` | 删存在的表成功 |
| `test_drop_nonexistent_table_fails` | 删不存在的表报语义错误 |
| `test_drop_catalog_table_is_forbidden` | `DROP __catalog__` 被语义层拦住 |

**UPDATE 语义（9 条）**

| 用例 | 验证什么 |
|---|---|
| `test_update_with_valid_assignments` | 合法赋值通过分析 |
| `test_update_nonexistent_table_fails` | 表不存在 |
| `test_update_nonexistent_column_fails` | 列不存在 |
| `test_update_duplicate_column_assignment_fails` | 同一列被赋值两次 |
| `test_update_type_mismatch_fails` | 值类型与列类型不匹配 |
| `test_update_varchar_length_check` | 字符串长度在限内通过 |
| `test_update_varchar_exceeds_length_fails` | 超长报错 |
| `test_update_where_non_bool_fails` | `WHERE` 不是布尔表达式 |
| `test_update_where_bool_expression_succeeds` | `WHERE` 是布尔表达式则通过 |

**LIMIT 语义（2 条）**

| 用例 | 验证什么 |
|---|---|
| `test_select_with_limit` | `LIMIT` 合法值通过 |
| `test_select_with_limit_zero` | `LIMIT 0` 通过（不是错误） |

**新特性计划树（6 条）**

| 用例 | 验证什么 |
|---|---|
| `test_drop_table_plan` | `DROP TABLE` → `DropTable` 节点 |
| `test_select_with_limit_plan` | `LIMIT` 在最外层（最后截断） |
| `test_select_with_order_and_limit_plan` | `Limit → Sort` 的嵌套顺序 |
| `test_select_with_where_order_limit_plan` | `Limit → Sort → Filter → SeqScan` 完整链 |
| `test_update_with_where_plan` | `UPDATE` 带 `WHERE` 的计划结构 |
| `test_update_without_where_plan` | `UPDATE` 不带 `WHERE`（全表更新）的计划结构 |

### 5.2 SHOW 与 ORDER BY `tests/test_show_order.py`（6）

| 用例 | 验证什么 |
|---|---|
| `test_new_words_are_case_insensitive_keywords` | 新关键词大小写不敏感 |
| `test_parser_supports_show_statements` | `SHOW DATABASES` / `SHOW TABLES` 可解析 |
| `test_parser_supports_multiple_order_items_and_directions` | 多列 `ORDER BY` 与 `ASC`/`DESC` 混合 |
| `test_order_by_rejects_missing_column` | 排序列不存在报错 |
| `test_order_by_executes_before_projection_and_supports_mixed_directions` | **排序发生在投影之前**（否则排序列不在结果里就排不了），多方向结果正确 |
| `test_show_returns_current_database_and_sorted_user_tables` | `SHOW` 返回当前库名与**已排序**的用户表（不含系统表） |

### 5.3 错误契约 `tests/test_errors.py`（15）

**继承关系（4 条）**

| 用例 | 验证什么 |
|---|---|
| `test_every_error_shares_the_common_base` | 五类错误都继承 `MiniSQLError` |
| `test_base_is_not_a_bare_exception_catch_all` | 基类不是裸 `Exception`——**CLI 只 `except MiniSQLError`，实现缺陷不能伪装成业务错误** |
| `test_error_classes_are_distinct_from_each_other` | 五类互不继承（不会误捕获） |
| `test_every_error_class_is_exported` | 全部在 `__all__` 中导出 |

**字段契约（11 条）**

| 用例 | 验证什么 |
|---|---|
| `test_every_error_exposes_type_line_column_message` | 都具备 `type`/`line`/`column`/`message` 四个字段 |
| `test_positions_must_be_one_based` | 位置必须从 1 开始（0 是非法值） |
| `test_position_defaults_to_one_based_origin` | 不传位置时默认 1 起始 |
| `test_message_is_required` | `message` 必填 |
| `test_message_is_accepted_positionally_and_by_keyword` | 位置参数与关键字参数两种写法都支持 |
| `test_reason_is_accepted_as_a_contract_alias_for_message` | `reason` 作为 `message` 的契约别名可接受 |
| `test_message_and_reason_cannot_disagree` | 两个别名同时给出且不一致时报错 |
| `test_str_contains_type_position_and_message` | `str(err)` 含类型、位置、原因三要素 |
| `test_existing_positional_call_style_is_unchanged` | 原有的位置参数调用方式未被破坏 |
| `test_message_only_call_style_is_unchanged` | 只传 `message` 的调用方式未被破坏 |
| `test_semantic_error_is_still_catchable_as_exception` | 仍可作为普通异常捕获 |

### 5.4 编译管线 `tests/test_demo.py`（19）

**错误呈现（5 条）**

| 用例 | 验证什么 |
|---|---|
| `test_demo_shows_all_backend_stages_for_valid_statement` | 合法语句完整打印各阶段产物 |
| `test_demo_reports_semantic_error_and_continues` | 语义错误逐条汇报，后续语句继续跑 |
| `test_semantic_error_message_carries_its_position` | 错误信息带位置 |
| `test_a_failed_statement_does_not_stop_the_next_one` | **一条失败不中断下一条** |
| `test_implementation_bugs_are_not_disguised_as_semantic_errors` | 实现缺陷不被伪装成 `SemanticError` |

**管线阶段（9 条）**

| 用例 | 验证什么 |
|---|---|
| `test_pipeline_tokenizes_real_sql_text` | 真实 SQL 文本可切出 Token |
| `test_pipeline_reaches_the_optimized_plan` | 管线一路走到优化后的计划 |
| `test_pipeline_registers_created_tables_so_later_statements_resolve` | 同次输入里 `CREATE TABLE` 后，后续语句能解析该表 |
| `test_lex_errors_are_reported_as_structured_diagnostics` | 词法错误以结构化诊断呈现 |
| `test_parse_errors_are_reported_as_structured_diagnostics` | 语法错误同上 |
| `test_missing_parser_is_reported_as_a_pending_dependency` | 缺 parser 时报告为「待接入依赖」而非崩溃 |
| `test_tokens_are_still_shown_when_the_parser_is_missing` | parser 缺失时 Token 仍然照常展示 |
| `test_default_parser_factory_does_not_crash_the_pipeline` | 默认 parser 工厂不会把管线炸掉 |
| `test_implementation_bugs_in_the_frontend_are_not_swallowed` | 前端实现缺陷不被吞掉 |

**`--compile-only` 入口（5 条）**

| 用例 | 验证什么 |
|---|---|
| `test_compile_only_flag_runs_the_pipeline_over_a_file` | 对文件跑管线 |
| `test_compile_only_flag_runs_the_pipeline_over_inline_sql` | 对命令行内联 SQL 跑管线 |
| `test_missing_compile_only_flag_is_a_usage_error` | 缺标志 → 用法错误 |
| `test_missing_input_is_a_usage_error` | 缺输入 → 用法错误 |
| `test_unreadable_file_is_reported_without_a_traceback` | 文件不可读 → 干净报错，无 traceback |

---

## 6. 端到端与 CLI

### 6.1 端到端 `tests/test_e2e.py`（3）

| 用例 | 验证什么 |
|---|---|
| `test_demo_script_prints_expected_output` | 真实子进程跑 `tests/sql/demo_e2e.sql`，输出逐行比对 |
| `test_demo_data_survives_a_restart` | 脚本跑完 → 重启进程 → 数据仍在 |
| `test_hundred_rows_survive_query_delete_and_restart` | **SC-006**：建表 → 插入 ≥100 行 → 条件查询 → 删除 → 重启再查，一次通过 |

### 6.2 命令行 `tests/test_cli.py`（7）

| 用例 | 验证什么 |
|---|---|
| `test_help_lists_the_three_supported_modes` | `--help` 列出三种模式 |
| `test_file_executes_sql_using_the_selected_data_directory` | `--file` 在指定数据目录上执行 |
| `test_compile_only_reads_a_file_without_creating_the_data_directory` | **`--compile-only` 只读不建目录**（不产生副作用） |
| `test_missing_file_is_a_clean_cli_error` | 文件不存在 → 干净错误，无 traceback |
| `test_history_is_written_and_read_back` | readline 历史能写入并读回 |
| `test_missing_history_file_is_not_an_error` | 首次运行没有历史文件 → 安静跳过 |
| `test_unwritable_history_file_is_not_an_error` | 历史文件不可写 → 不影响 REPL 启动 |

### 6.3 SQL 用例集驱动 `tests/test_sql_cases.py`（3）

| 用例 | 验证什么 |
|---|---|
| `test_case_set_contains_at_least_thirty_named_cases` | 用例集至少 30 条具名用例 |
| `test_cases_exercise_every_required_compiler_outcome` | 覆盖全部要求的编译结果类别（合法 / 词法错 / 语法错 / 语义错） |
| `test_each_sql_case_reaches_its_declared_outcome` | **逐条**跑并断言达到声明的结果 |

---

## 7. 灾难级 bug 的守门员

以下用例守的不是「功能对不对」，而是「出事就是大事」，改优化器或执行器前先看这一组：

| 用例 | 一旦失守的后果 |
|---|---|
| `test_constant_false_delete_is_not_turned_into_a_full_table_delete` | `DELETE ... WHERE false` 变成**全表删除**，数据全丢 |
| `test_load_rejects_truncated_existing_file_without_overwriting[table]` | 启动时把截断的库当空库重建，**覆盖掉仅存的数据** |
| `test_dropped_table_stays_dropped_after_restart` | 删表在重启后复活，目录与文件不一致 |
| `test_limit_applies_after_order_by` | `ORDER BY ... LIMIT n` 取到错的行（顺序反了） |
| `test_division_by_zero_in_delete_does_not_raise_or_drop_the_filter` | 除零把 `WHERE` 条件丢掉 → 变成全表删 |
| `test_optimizer_does_not_mutate_the_input_plan` | 优化器改坏输入计划，同一条语句重跑结果不同 |
| `test_drop_catalog_table_is_forbidden` | 系统目录被删，整个数据库打不开 |
| `test_base_is_not_a_bare_exception_catch_all` | 实现缺陷被当成业务错误吞掉，故障被掩盖 |

---

## 8. 已知覆盖缺口

诚实记录当前**没有测试覆盖**的地方（非交付缺陷，但答辩可能被问到）：

| 缺口 | 现状 | 说明 |
|---|---|---|
| **CLI 异常出口** | 无覆盖 | `cli/main.py` 的 `main()` 里 `db = MiniDB(arguments.data)` 在 `try` **之外**。数据目录损坏时抛 `StorageError` 会甩 traceback（引擎层有测试证明会抛 `StorageError`，但**没有一条测试从 CLI 喂过坏目录**） |
| **SC-002 Fuzz** | 无覆盖 | 验收标准要求「固定随机种子 ≥10,000 条非法/随机输入，崩溃 0 次，错误归类且有有效行列号」。目前只有一次性手工探针，仓库内无正式用例 |
| **深嵌套表达式** | 部分覆盖 | 前端有 `test_excessive_parentheses_raise_parse_error_not_recursion_error`，但**执行器侧没有对应防护**：`WHERE` 里 300 层 `AND` 链会 `RecursionError` |
| **UPDATE 执行** | 语义/计划层已覆盖，执行层无 | Executor 尚未接入 `Update` 分支，见 `tasks.md` T038 |
| **JOIN** | 无 | `spec.md:169` 明确列为不在当前范围 |

---

## 9. SQL 用例集 `tests/sql/compiler_cases.json`

34 条具名用例，由 `tests/test_sql_cases.py` 驱动，每条声明**期望结果**（`valid` / `lex_error` / `parse_error` / `semantic_error`）。

| 类别 | 条数 | 代表用例 |
|---|---|---|
| 合法语句 | 13 | `create_int_table`、`create_varchar_min`、`create_varchar_max`（边界 1/255）、`insert_implicit_columns`、`insert_explicit_columns`、`select_star`、`select_precedence`、`select_parentheses`、`delete_all`、`delete_where`、`multiple_statements`、`mixed_case_and_comments` |
| 词法错误 | 7 | `illegal_at_character`（`@`）、`illegal_bang_operator`（`!`）、`leading_decimal_point`（`.5`）、`trailing_decimal_point`（`1.`）、`number_joined_to_identifier`（`12abc`）、`unterminated_string`、`unterminated_comment` |
| 语法错误 | 10 | `missing_semicolon`、`missing_from`、`missing_where_expression`、`missing_and_operand`、`empty_statement`、`consecutive_semicolons`、`varchar_missing_length`、`varchar_zero_length`、`varchar_oversized`、`chained_comparison` |
| 语义错误 | 4 | `semantic_missing_table`、`semantic_duplicate_columns`、`semantic_float_value`、`semantic_type_mismatch` |

配套 SQL 文件：

| 文件 | 用途 |
|---|---|
| `tests/sql/demo_compiler.sql` | `--compile-only` 演示（4 条语句，走完整编译管线） |
| `tests/sql/demo_e2e.sql` | 端到端演示（建表→插入→条件查询→删除→全表查询），由 `test_e2e.py` 逐行比对输出 |

---

## 10. 复现方式

```bash
# 全量
PYTHONPATH=. .venv/bin/python -m pytest tests -q

# 按层跑
PYTHONPATH=. .venv/bin/python -m pytest tests/test_lexer.py tests/test_parser.py tests/test_semantic.py tests/test_planner.py -v   # 编译器
PYTHONPATH=. .venv/bin/python -m pytest tests/test_storage.py tests/test_buffer.py -v                                            # 存储
PYTHONPATH=. .venv/bin/python -m pytest tests/test_engine.py tests/test_catalog.py -v                                            # 引擎
PYTHONPATH=. .venv/bin/python -m pytest tests/test_e2e.py tests/test_cli.py -v                                                   # 端到端

# 用例清单（不执行）
PYTHONPATH=. .venv/bin/python -m pytest tests --collect-only -q
```
