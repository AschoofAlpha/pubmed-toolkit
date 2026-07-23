# pubmed-toolkit

从 PubMed 记录得到的事实，判断要不要进某位导师的组。

[English](README.md) | 简体中文

你在选博导或硕导。手上只有一个名字、一个由课题组自己写的主页，没有任何独立渠道可以核实。
`profile` 拿这一个名字，产出一份报告，说明发表记录**实际显示**出的「当这个人的学生是什么样」：
论文的第一作者都是谁、人在组里能被观察到多久、一个新人多久才能拿到第一篇一作——
每个数字都带着它自己的分母。

它不打分、不排名、不做人与人的比较，也不输出任何总评数字。
更重要的是[它不会告诉你什么](#它不会告诉你什么)。

| 命令 | 作用 |
| --- | --- |
| `profile` | **本仓库的目的**。给定一位 PI → 关于其课题组发表记录的事实报告 |
| `fetch` | 为 `profile` 准备语料：检索 PubMed → 只保留这位研究者本人的论文 → 可选地并发下载 OA PDF |
| `verify` | 与上面无关，如实说明：把 `.bib` 与 CrossRef、PubMed 交叉核验。它只是共用同一套 HTTP 层 |

---

## 这个工具不是什么

**不是文献检索工具。** 没有主题检索、没有关键词模式、没有「帮我找 X 方向的论文」。
唯一支持的查询对象是**一个人**。要做通用检索请用 `metapub`、`pyalex` 或 `paperscraper`——
它们覆盖的源更多、在 PyPI 上、维护更好，本工具在这个比较里每一项都输。

**不是评价排名工具。** 引用数、h-index、影响因子、分区、中科院分区都在范围之外，
不计算、不存储、也不写进任何中间文件。每份报告的 Section 14 会列出**刻意没做的指标及其原因**，
这样「有意省略」才能和「疏漏」区分开。

范围窄本身就是设计。下面所有东西之所以成立，是因为准学生问的是**某一个人**——
这个问题有可辩护的答案，而「哪个组更好」没有。

---

## 报告为什么长这样

**PubMed 里只有发表过的人。** 一个进了组、挣扎三年、没有论文就离开的学生，
在报告的每一个数字里都不存在——分子里没有，**分母里也没有**。
这部分缺失人群的规模，无法从文献元数据里还原，也没有任何统计手段能修补。
因此报告在 Section 0 用正文而非脚注说明这一点，因为它改变了后面每个数字的读法。

**按姓名检索 PubMed 会返回好几个不同的人。** 中文拼音姓名重合度极高：
一次 `"姓 名"[Author]` 检索常常同时命中临床医生、环境科学研究者和计算机视觉研究者——
他们只是同名。基于这种语料做出来的画像，同时描述了三个人。
这就是为什么 `fetch` 的作者消歧在这里是**承重结构**而不是锦上添花，
也是为什么没有配置身份证据时报告会直接拒绝生成。

**小组必然带来小分母。** 四个人算出来的中位数不是中位数。
低于最小样本量时，报告直接列出原始行而不给聚合值；n 低于 20 时完全不给百分比。
这些阈值写在规范里，**刻意不做成命令行参数**。

---

## 安装

```bash
git clone https://github.com/AschoofAlpha/pubmed-toolkit.git
cd pubmed-toolkit

pip install -e ".[fetch]"         # profile + fetch：PDF 下载与身份校验
pip install -e ".[analysis]"      # + 活跃期甘特图 PNG（matplotlib）
pip install -e .                  # 仅 verify —— 无任何第三方依赖
```

需要 Python 3.10+。**未发布到 PyPI**，请从源码安装。

语料就绪之后，`profile` 本身只用标准库——matplotlib 只用于画时间线图，
缺少它时会告警并跳过 PNG，报告其余部分照常产出。

PyMuPDF 刻意不设为硬依赖：它是 AGPL-3.0，而本项目是 MIT——
一个 MIT 包不该在用户没主动选择的情况下把 copyleft 拉进其环境。

---

## `profile` — 发表记录反映出的「当这个人的学生是什么样」

```bash
cp config.example.json config.json   # 填好 author_name 与 author_identity
python -m pubmed_toolkit fetch --config config.json --no-download
python -m pubmed_toolkit profile --config config.json
```

在输出目录下生成 `advisor_profile_<时间戳>.md` 与 `.json`；
装了 matplotlib 时还会有 `student_activity_gantt.png`。

```bash
--config PATH          # 身份配置与 advisor 配置
--output-dir DIR       # 默认 pubmed_results，与 fetch 一致
--papers-json PATH     # 默认取 --output-dir 下最新一份 papers_*.json
--pi-name NAME         # 覆盖 config 里的 author_name
--log-level LEVEL
```

报告被门禁拒绝时退出码为 1（见[门禁](#门禁)），否则为 0。

### 报告里有什么

15 个小节，每个数字都带分母，并配一条说明「这个数字不能代表什么」的告诫：

| 小节 | 回答什么 |
| --- | --- |
| 0 | 这份报告是什么、不是什么——**先读这节** |
| 1 | 语料来源：检索式、身份证据、每一条被排除的记录 |
| 2 | 人员名单、活跃期时间线，以及每个人的位置标签 |
| 3 | 一作位置被谁占据——分别从「论文侧」和「人员侧」看 |
| 4 | 一个人从首次出现到拿下第一个一作，间隔多少年 |
| 5 | 人在记录中可被观察到多久，并标出截尾情况 |
| 6 | 逐年的在组规模与人员进出 |
| 7 | PI 本人在自己论文署名里的位置 |
| 8 | 共同署名标记，以及它标的是共同一作还是共同通讯 |
| 9 | 逐年记录数，标出不完整年份与受索引滞后影响的年份 |
| 10 | 每篇论文的作者数 |
| 11 | 期刊名，原样列出、不做归一化——**永远不含影响因子** |
| 12 | Affiliation 字符串，原样列出、不做归并 |
| 13 | 全部标题，按年份列出——主题由你来判断，工具不替你分类 |
| 14 | 刻意没有计算的指标，以及为什么 |

位置标签只有四种：`lead-trainee candidate`、`support candidate`、
`single appearance`、`senior collaborator`。
它们是**从署名位置做的推断，不是关于某个人的事实**：
博士生、博士后、技术员、研究助理、专职科研、临床 fellow、轮转学生、访问学者
在署名上呈现同一种形态，PubMed 没有任何字段能把他们分开。

### 门禁

有五种情况会让整份报告失去意义，而不只是变吵。
每一种都产出一份「拒绝文档」，里面只有门禁名称、观测到的值和修复方式，**别的什么都没有**。
没有「带警告降级」这条路——警告会被滑过去，缺失的报告不会。

| 门禁 | 触发条件 |
| --- | --- |
| G1 截断 | `esearch` 命中数大于实际取回数，此时每个计数都错得没有上界 |
| G2 身份回退 | 没有任何论文通过身份验证，语料退化成「所有同名者的全部论文」 |
| G3 身份配置过弱 | ORCID、机构关键词、邮箱域**一个都没配** |
| G4 无结构化作者 | 输入没有逐作者记录——包括任何试图从 `papers_*.xlsx` 出报告的情况 |
| G5 空语料 | 记录级排除之后什么都不剩 |

G4 **只看扩展名就拒绝 Excel，根本不打开文件**。原因是
`build_author_records` 在记录匹配不上 PMID 时会静默退回到「按作者字符串切分」，
于是所有作者被强制写成 `equal_contrib=False`、`is_corresponding=False`、`affiliation=""`。
那条路径把「未知」变成了「确凿的零」，是整条流水线里最危险的静默失败。

### 它不会告诉你什么

这是对一份**发表记录**的描述，不是对一个**人**的描述，两者之间差得很远：

- **它对指导本身一无所知。** 指导风格、有没有人顺利毕业、经费是否稳定、作息强度、组内氛围、出了矛盾怎么处理、离开的人后来怎么样了——PubMed 里全都没有。而这些恰恰是你真正想知道的
- **所有没发表就离开的人是不可见的。** 他们在每个比值的两侧都缺席。一个走掉一半学生、靠另一半发得不错的组，和一个把所有人都留住的组，在数据上无法区分
- **课题组成员的判定天然不准确。** PubMed 的 affiliation 覆盖稀疏且随年代变化：早期记录常常只有第一作者的单位。因此 affiliation 只作为**逐人报告的属性**，绝不用来判定谁是组里的人。合作者不是组员，而 PubMed 没有字段能区分
- **人是按姓名字符串识别的。** 两个同名的人会合并成一行，计数虚高、活跃期虚长；一个人的两种写法会拆成两行短记录。报告把「严格键」和「宽松键」两种口径下的人数并排打印——**那个差值就是本节所有人员计数的误差范围**
- **小组必然带来小分母。** 低于阈值的聚合值会被替换成原始行。这不是需要绕过的缺陷；四个数据点撑不起一个中位数
- **所有「活跃期」都是两个发表日期之间的间隔**，不是在组时间。博士前两三年在构造上就不可见，而一篇论文可能在人离开一年多之后才出现
- **刻意不输出任何总评分。** 任何加权指数都会编码进这份数据无法支撑的权重，并重新造出本工具要避免的「给人排序」
- **PI 自己的署名位置无法从 `fetch` 语料测量。** `fetch` 只保留第一/末位/通讯作者的论文，于是答案是被那个过滤器决定的，不是被数据决定的。报告会识别出这一点，打印告诫而不是给数字

请把输出**按具名个人数据对待**：留在本地，未经被描述者同意不要公开发布。

---

## `fetch` — 准备语料

```bash
python -m pubmed_toolkit fetch --config config.json --no-download
```

`--no-download` 跳过 PDF，`profile` 并不需要它们。
不加这个参数则同时得到 PDF、逐篇校验报告和运行日志。

### 作者消歧

**这是画像值不值得读的前提。** 仅姓名匹配不够，还必须命中以下之一：

| 优先级 | 信号 | 强度 |
| --- | --- | --- |
| 1 | ORCID（`<Identifier Source="ORCID">`） | 最强，全球唯一 |
| 2 | 邮箱域 | 强，但 PubMed 通常不含邮箱 |
| 3 | 机构关键词模糊匹配 | 主力手段 |

设 `require_affiliation: true` 进入严格模式：三者全不命中则拒绝。
**机构关键词要把该机构在 PubMed affiliation 字段里的各种写法都列全**——
缩写、附属医院、英译名。PubMed 不做归一化。

在一次针对常见姓名的真实运行中，这套过滤把 54 条 PubMed 原始命中收敛到属于目标研究者的 10 条，
其中 ORCID 命中 6 条、机构关键词命中 4 条，其余 44 条是别人。
**这是一个数据点，不是基准测试**，你的结果会不同。

### PDF 下载与身份校验

8 个开放获取源并发竞速，第一个通过身份校验的胜出，其余取消。
下载后抽取 PDF 正文，比对目标 DOI 与标题 token；
不匹配的移入 `pdfs/suspect/` 并把原因记进 `pdf_validation_report_*.csv`，而不是当成成功。

会做校验的下载器基本只验 `%PDF` 魔数——那是**格式**，不是**身份**。
`pdf2doi` 这件事做得不错，但它是独立工具，针对你已有的文件。

### 其他子命令

```bash
python -m pubmed_toolkit download                  # 从已有 papers_*.json 重试下载
python -m pubmed_toolkit analyze --pi-name "..."   # 作者矩阵 / 活跃期甘特 / 主题图
python -m pubmed_toolkit clean-cache --max-age-days 30
```

`analyze` 早于 `profile` 存在，功能上有重叠。它**不设样本量下限、也不附任何告诫**，
所以凡是你打算据以做决定的场景，请用 `profile`。

---

## `verify` — 核验参考文献

一个恰好住在同一个仓库里的独立工具。它与 `fetch` 共用 HTTP 与归一化层，
和导师画像没有任何关系；之所以在这里，只是因为它当初就是基于同一套 PubMed 客户端写的。

```bash
python -m pubmed_toolkit verify references.bib --email you@example.com
```

在 `verify_results/` 下生成 Markdown 报告和完整 JSON 记录。

| 状态 | 含义 |
| --- | --- |
| `verified` | 已解析，**所有检查都实际执行**，且全部一致 |
| `partial` | 已解析且无矛盾，但某次查询失败，意味着至少一项检查（可能就是双向反查）**根本没跑** |
| `mismatch` | 已解析，但某字段与权威记录不符 |
| `not_found` | 查无记录，且没有任何标识符被证伪。**常常是正常的**——教科书、国家指南、许多中文期刊本就不在库里 |
| `error` | 什么都没解析出来且查询失败。结论未知，而非否定 |

另有两类发现独立于状态计数，因为它们可能挂在任何状态的条目上：
**conflicts**（DOI 与 PMID 指向不同论文）与 **unregistered**（DOI 从未注册，或 PMID 无记录）。

它针对的问题：在 LLM 参与起草参考文献之后，真正棘手的已经不是凭空捏造的条目，
而是**用两篇真实论文拼接出来的条目**——DOI 能解析、PMID 也能解析，但它们指向不同的文章。
对 NeurIPS 2025 的分析发现至少 53 篇录用论文带有 100+ 条幻觉引文¹，
ICML 2026 因 LLM 政策违规桌拒了 497 篇投稿²。

### 双向反查

对同时带两个标识符的条目，各自独立解析，并要求两个方向都吻合：

```
所给 DOI  --Entrez ESearch-->   PMID'   ==  所给 PMID ?
所给 PMID --Entrez ESummary-->  DOI'    ==  所给 DOI  ?
```

一条「DOI 写 Bass 2014、PMID 写 Dixon 2012」的引文，能通过任何只查存在性的检查——
两个标识符都是真的、都能解析。这里会被判为 `conflict`，比任何单字段不符都更强：
**至少有一个标识符不是从被引论文上取来的**。

解析不出来**永远不会**被报成冲突。DOI 反查不到 PMID，那是缺证据，不是反证据。

另有三处刻意的区分，**每一处都是先出过 bug 才有的**：

- **`partial` 不等于 `verified`。** CrossRef 答了、Entrez 超时，双向反查就没发生过。把它判为已验证，正是本工具要消灭的「成功但错误」，而且**文献量越大越严重**——NCBI 恰恰在高负载时返回 429
- **未注册的 DOI 不等于「查无此文」。** 指向虚无的引用是伪造的特征；教科书不在 CrossRef 只是收录缺口。二者分节呈现，前者绝不会被归进后者那句安慰性的说明里
- **`not_found` 不等于 `error`。** 前者是结论，后者是没能得出结论

先拿示例文件试试（含 3 条正确 + 4 条故意埋错的条目）：

```bash
python -m pubmed_toolkit verify examples/references.example.bib --email you@example.com
```

常用参数：

```bash
--fail-on-mismatch     # 有问题就退出码 1(供 CI 用)
--no-pubmed            # 只用 CrossRef,会跳过双向反查
--ncbi-api-key KEY     # Entrez 限速从 3/s 提到 10/s
--max-workers 6        # 并发查询数
--timeout 12           # 单请求硬超时(秒)
```

支持 `.bib` 或 JSON 输入。

### 如何避免误报

核验工具一旦频繁误报就会被关掉，所以以下「写法不同但含义相同」的情况一律视为一致：
缩写页码（`202-9` 与 `202-209`）、联盟署名、作者顺序差异、
变音符号与期刊缩写（`Følling`/`Folling`、`Lancet`/`The Lancet`）。

仍会被标记的，是真正说明引文有问题的情况：署名的人根本不在该论文作者列表里、
年份或期刊写错、两个标识符指向不同作品。

---

## 适用范围

**只用开放获取源**：PMC、Unpaywall、Europe PMC、Semantic Scholar、CORE、OA Button、
bioRxiv/medRxiv、DOI 直连。

**不含 Sci-Hub / LibGen，也不会加入。** 付费墙后且无 OA 副本的论文会下载失败——
这类请用你所在机构的正规访问权限。这样做的直接好处是工具在高校与医院网络内可用，
那些网络通常会封禁上述域名。

请遵守所用各 API 的速率限制。务必设置联系邮箱：CrossRef 与 NCBI 都要求，匿名流量可能被限速。

---

## 测试

553 条断言，全部离线——权威记录均为合成 fixture，CI 不依赖 CrossRef / NCBI 可达。
纯脚本，不用 pytest。

```bash
python tests/test_profile.py            # 226 — 门禁、分层、每个指标、抑制阈值
python tests/test_verify_regressions.py #  96 — 代码审查与实跑中发现的每一个 bug
python tests/test_verify.py             #  71 — 归一化、双向反查、BibTeX 解析
python tests/test_bibtex_pmid_sources.py #  50 — PMID 可能合法藏在 .bib 的哪些位置
python tests/test_name_matching.py      #  45 — 姓氏 vs 缩写、CJK 姓名
python tests/test_pubmed_parse.py       #  35 — XML 解析边界情况
python tests/test_search_query.py       #  21 — PubMed 检索式构造
python tests/test_identity_filter.py    #   6 — 作者消歧
python tests/test_pdf_validation.py     #   3 — PDF 身份校验
```

回归测试之所以存在，是因为那几块**确实带着 bug 发布过**。
检索式那组尤其锁住了一个单元测试抓不到的召回 bug：原实现总是给检索式加引号，
而加引号会关闭 PubMed 的词条展开，导致索引为 `Stockwell BR` 的作者只命中 6 条而非 253 条。

---

## 已知局限

画像相关的局限见[它不会告诉你什么](#它不会告诉你什么)。整个工具层面：

- 消歧质量**完全取决于**你提供的机构关键词列表。研究者换过单位的，每个单位都要列上，否则早年论文会静默地掉出语料
- 消歧过滤器**未在标注数据集上做过基准评测**。S2AND 提供了合适的评测框架；本项目不宣称任何 precision/recall 数字，因为确实没有测过
- PubMed 很少包含作者邮箱，这个信号实际上很少触发
- 作者检索式刻意放宽，常见姓氏可能超出 `retmax`。此时工具会用你的机构关键词做服务端收窄并明确告知；未配置关键词时会告警而不是静默截断。**语料一旦截断，画像报告会直接拒绝出报告**
- **元数据源只有两个**：CrossRef 与 PubMed。只被 arXiv、DBLP、ACL Anthology 收录的文献会返回 `not_found`
- CrossRef 对许多联盟署名论文不记录个人作者，这类论文的作者校验只能依赖 PubMed
- **`verify` 的吞吐受 NCBI 限速约束，而非 `--max-workers`。** 标识符解析已批量化——DOI 合并进一次 ESearch、PMID 每 200 个一批取回——500 条参考文献只需几次 Entrez 请求而非上千次。仍然逐条串行的是 CrossRef（每条一次请求）
- 批量化**刻意不使用** NCBI 的 PMC ID Converter，尽管它能一次调用完成 DOI→PMID。它只覆盖 PMC：Lancet、NEJM、JAMA 的 DOI 全部返回「not found in PMC」，而 ESearch 都能正确解析。用它等于在最需要双向反查的临床文献上悄悄关掉这项检查

---

## 相关项目

**导师 / 课题组评估方向：** 没有找到从发表记录回答这个问题的工具。
相邻的工具回答的是另一个问题：OpenAlex、Scopus、Web of Science 按引用类指标给研究者排名，
而那正是本工具排除的用途；`scholarly`、`pybliometrics` 能取到那些指标但不做课题组层面的分析；
ORCID 与 ResearchGate 呈现的是**自述**画像而非推导出的画像。

**抓取与消歧：**

- [pypaperretriever](https://github.com/JosephIsaacTurner/pypaperretriever) — DOI/PMID → PDF
- [paperscraper](https://github.com/jannisborn/paperscraper) — 跨 PubMed/arXiv/*Rxiv 的元数据
- [metapub](https://github.com/metapub/metapub) — NCBI eutils 元数据与全文挖掘
- [pdf2doi](https://github.com/MicheleCotrufo/pdf2doi) — 从已有 PDF 中提取并验证 DOI
- [S2AND](https://github.com/allenai/S2AND) — Semantic Scholar 的作者消歧算法与评测集
- [pyalex](https://github.com/J535D165/pyalex) — OpenAlex 客户端，作者实体已由上游消歧

作者消歧在别处只以**独立系统**形式存在（S2AND、ReCiter、`beard`），
或作为上游已解析的 ID 供消费（OpenAlex、Semantic Scholar）。
把它放进抓取环节内部，才让「单人语料」可信到足以在其上做画像。

**引文核验方向最接近的先行工作**（这两个会与权威元数据比对）：

- [VeraCite](https://github.com/Shannon-Whitlock/VeraCite) — 对 CrossRef/OpenAlex/arXiv/DataCite 报告字段级不符，并对同一 DOI 做多源互比。**完全不接 PubMed，也不使用 PMID**
- [evidentia](https://github.com/kgraph57/evidentia) — 解析文本中的每个标识符，与**被引的标题、作者、年份**比对，标记「真标题上嫁接伪造标识符」。但其检查是「标识符 vs 文本」，依赖条目带有准确标题；本项目是「标识符 vs 标识符」，在标题缺失、写错、甚至本身就是伪造时依然有效
- [sciwrite-lint](https://github.com/authentic-research-partners/sciwrite-lint) — 广谱稿件核查，含撤稿检测；会标记条目内标识符冲突

---

## 许可

MIT。仅供研究使用，请遵守所查询各来源的服务条款与 `robots.txt`。

---

¹ GPTZero 对 4,841 篇 NeurIPS 2025 录用论文的分析，见 [Fortune 2026-01-21 报道](https://fortune.com/2026/01/21/neurips-ai-conferences-research-papers-hallucinations/)；失效模式分类见 [arXiv:2602.05930](https://arxiv.org/abs/2602.05930)。

² [ICML 2026 Program Chairs, "On Violations of LLM Review Policies", 2026-03-18](https://blog.icml.cc/2026/03/18/on-violations-of-llm-review-policies/)。
