# pdd-comment-analyzer

基于 **PySide6 + SeleniumBase + 大模型** 的商品评论质量分析工具：粘贴商品链接，自动抓取评论、逐条打分、过滤无效评论，输出一个 0–100 的商品质量分与各维度得分。

- 版本：0.1.0　|　运行环境：Python 3.13 + Windows（macOS/Linux 未测试）
- 界面：桌面 GUI（MVVM 架构，支持浅色 / 深色主题）

---

## 一、快速开始


### 方式 A 源码运行

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python src/main.py
```

---

## 二、使用步骤

1. **配置 API Key**：打开「系统设置」页，填入 DeepSeek API Key（`baseUrl` 默认 `https://api.deepseek.com`，模型默认 `deepseek-flash`）。Key 仅存本地配置文件。
2. **准备分析策略**：「策略管理」页可选三种来源
   - `默认`：随程序分发的策略（`config/strategies/`）
   - `自建`：手动新建/编辑维度与权重，保存在本地数据库
   - `AI 生成`：输入一句自然语言需求，由大模型生成维度体系，确认后保存
3. **开始分析**：「新建分析」页粘贴商品链接 → 选择策略 → 点击开始。
4. **手动登录**：程序会打开浏览器，若未登录请在浏览器中完成登录（最长等待 180 秒），登录后自动继续。
5. **查看结果**：得到最终质量分、各维度平均分/加权分、有效评论数与过滤统计；需要时可对少量样本启用「修正因子」人工校准。
6. **历史与日志**：「历史记录」页查看过往分析，「日志」页实时查看运行日志。

---

## 三、核心机制（怎么算出这个分）

| 环节 | 做法 |
| --- | --- |
| 评论抓取 | SeleniumBase UC 模式 + BrowserForge 浏览器指纹，滚动加载至上限（默认 600 条） |
| 维度重构 | 抓到的评论数低于阈值（默认 20）时，自动将原策略维度重构为少量强调维度，避免小样本失真 |
| LLM 打分 | 按批（默认 50 条/批）并发（默认 4）调用模型，输出各维度分 + 可信度 |
| 置信度过滤 | 可信度低于阈值（默认 0.5）的评论直接排除 |
| 截尾平均 | 按加权总分去掉两端各 5%，再算各维度平均分，抑制极端值 |
| 修正因子 | 有效评论数低于阈值（默认 10）时弹出询问，可人工介入校准 |
| 加权出分 | 各维度平均分 × 维度权重求和，得到 0–100 质量分 |

关键参数集中在 `config/settings.toml`（也可在「系统设置」页修改）：

```toml
[crawl]   commentThreshold=20   commentMaxCount=600   loginTimeoutSeconds=180
[analysis] credibilityThreshold=0.5   trimPercent=5.0   validCommentThreshold=10
[llm]     model="deepseek-flash"   maxConcurrency=4   batchSize=50
```

---

## 四、数据存储

配置、数据库、日志统一写入（与安装目录无关，卸载不删除）：

```
%LOCALAPPDATA%\pdd-comment-analyzer\
├─ config\settings.toml        # 系统参数与 API Key
└─ data\analysis.db            # 历史分析记录、自建策略
   └─ data\logs\app.log        # 运行日志
```

---

## 五、目录结构

```
src/
├─ data/       配置读写、SQLite 仓储、路径与日志
├─ work/       抓取（browserTools）、LLM 服务、打分聚合、流程编排
└─ interface/  MVVM：view / viewModel / model / tools（QSS 主题、公共控件）
config/        settings.toml 与默认策略
resources/     QSS 主题样式、应用图标
packaging/     PyInstaller spec 与 Inno Setup 安装器脚本
```

---

## 六、重新打包

```bash
python -m PyInstaller packaging/pdd-comment-analyzer.spec --noconfirm
iscc packaging/installer.iss      # Inno Setup 6
```

产物分别输出到 `dist/原始程序/` 与 `dist/安装程序/`。

---

## 备注

- 首次运行需联网：拉取 chromedriver、调用大模型接口。
- 评论抓取依赖平台页面结构，页面改版可能导致抓取失效。
- 请遵守目标平台的服务条款，账号由使用者自行登录与保管，程序仅在本地运行与存储数据；本项目仅供商品质量自助分析使用。
