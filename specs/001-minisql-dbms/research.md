# Phase 0 Research: MiniSQL 教学数据库系统

所有 Technical Context 项均已确定，无遗留 NEEDS CLARIFICATION。以下为关键
技术决策及理由。

## 决策 1：Parser 实现策略

- **Decision**: 递归下降（Recursive Descent）
- **Rationale**: 结构清晰、每个非终结符对应一个函数，天然便于构造 AST 与
  错误恢复（带期望符号集合）；课程允许 LL(1) 表驱动/递归下降/LR 三选一，
  递归下降最利于 4 人协作与现场讲解。
- **Alternatives considered**: LL(1) 表驱动（与理论对应好但文法改造与表维护
  成本高）；LR/工具生成（课程要求不能只调库，性价比低，列为挑战项）。

## 决策 2：页内布局

- **Decision**: Slotted page——页头（页号、类型、槽数、空闲指针）+ 槽数组
  （从页首向后生长）+ 行数据（从页尾向前生长）
- **Rationale**: 行在页内移动只需改槽指针，删除/插入简单；与课程 PPT 的
  页结构描述一致，讲解时有据可依。
- **Alternatives considered**: 定长顺序追加（最简单但删除后空间复用麻烦）。

## 决策 3：行序列化

- **Decision**: `struct.pack` 定长编码——INT 4 字节定长；VARCHAR 按
  声明长度上限定长存储（不足补零）
- **Rationale**: 定长行使槽偏移计算 O(1)，序列化/反序列化代码极简且可靠。
- **Alternatives considered**: 变长编码（省空间但偏移计算复杂，教学收益低）；
  JSON/pickle（体积大、不"数据库"）。
- **Boundary**: SQL 文法要求 `VARCHAR(n)`，`1 <= n <= 255`；写入前按 UTF-8
  字节数校验，超长值返回 SemanticError，不截断数据。

## 决策 4：缓冲池 LRU 实现

- **Decision**: `collections.OrderedDict`（move_to_end / popitem）实现 LRU；
  FIFO 用同一结构的纯插入序模式，策略参数化
- **Rationale**: 标准库即 O(1)，无外部依赖，测试时可用固定访问序列精确
  推演命中/淘汰顺序。
- **Alternatives considered**: 手写双向链表 + 哈希表（有讲解价值，列为扩展/
  答辩加分项）。

## 决策 5：Catalog 持久化

- **Decision**: 系统目录作为特殊表（`__catalog__`）存储，复用存储引擎的
  行/页机制；内存中用 dict 缓存加速查找
- **Rationale**: 满足指导书"元数据作为特殊表存储"的硬性要求，避免引入第
  二套持久化格式；启动时扫描目录表重建内存缓存。
- **Alternatives considered**: JSON 文件单独存元数据（简单但不符合指导书
  要求，仅作降级方案）。
- **Bootstrap**: 首次启动由 CatalogManager 创建固定模式的 `__catalog__` 文件，
  此步骤不调用普通 `register_table`，避免目录登记自身造成递归；之后普通表按
  “创建数据文件 → 写目录行 → 更新内存 Catalog”的顺序创建。

## 决策 6：Logical Plan 输出形式

- **Decision**: 树形结构 + JSON 双输出（树形用于演示/讲解，JSON 用于测试断言）
- **Rationale**: 课程允许树形/JSON/S-表达式任选，双输出同时服务"可演示"
  与"可自动化验证"。

## 决策 7：优化规则范围

- **Decision**: 必做 3 条：常量折叠、布尔化简、冗余节点消除（Project[*] /
  恒真 Filter 移除）；谓词下推留给 JOIN 扩展
- **Rationale**: 超过"至少 2 条"的验收线且每条都可用结构对比验证等价性。
