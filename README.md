# FindSourceURL.com - 面向下一代Web交互的AI Agent探索与UI自动化实践

## 简介 (Executive Summary)

`FindSourceURL.com` (概念验证) 起源于一项面试挑战，旨在通过创新的自动化技术解决"根据网页截图反向查找其原始URL"的问题。本项目不仅成功实现了一个基于 **`pyautogui` 和图像模板匹配** 的稳定、高效的桌面自动化解决方案，更重要的是，它深入探索了利用 **大型语言模型 (LLM) 和多模态 AI (GPT-4o Vision) 构建智能代理 (AI Agent)** 来模拟人类与复杂网页交互的先进方法。

虽然最终演示采用了更直接的 `pyautogui` 方案以确保演示的鲁棒性，但项目的大量时间和精力投入在 **AI Agent 的设计、工具构建和流程编排** 上（使用 LangChain/LangGraph）。这段探索深刻揭示了 AI Agent 在理解视觉信息、进行多步推理和适应动态界面方面的巨大潜力，同时也暴露了当前技术在像素级精确控制和复杂状态同步方面的挑战。

这份文档将详细介绍这两个阶段的探索历程，重点突出 **AI Agent 的设计理念、为 Agent 量身打造的交互工具集、以及多模态能力在自动化任务中的应用**，旨在全面展示作者在 LLM 应用、Agent 构建及复杂问题解决方面的实践与思考，这与大模型工程师所需的核心能力高度契合。

## 演示 (Demo)

项目演示视频 (`findsourceurl-agent/findsourceurl.mp4`) 已包含在此仓库中，展示了最终 PyAutoGUI 方案的自动化流程。

## 项目目标 (Project Goal)

*   **核心任务**: 完成根据图片（网页截图）自动查找其原始来源网站 URL 的面试任务。
*   **技术探索**: 深入研究并实践 **AI Agent** 在复杂、动态网页自动化任务中的应用潜力，特别是结合 **多模态视觉理解** 能力。
*   **能力展示**: 体现 Python 编程、**LLM 应用（Agent设计、工具使用、Prompt工程）**、UI 自动化、问题解决和迭代开发能力，符合大模型工程师岗位要求。
*   **原型构建**: 创建一个可扩展的自动化工具原型，为未来部署到 `findsourceurl.com` 奠定基础。

## AI Agent 探索与设计 (AI Agent Exploration & Design)

认识到传统基于固定选择器或规则的Web自动化方案在面对现代Web应用的动态性和复杂性时的脆弱性，本项目将 **AI Agent** 作为核心探索方向。我们旨在构建一个能够 **像人一样"观察"和"操作"** 浏览器的智能体。

**1. 设计理念:**

*   **视觉驱动**: 摒弃对脆弱DOM结构的依赖，利用 **GPT-4o Vision** 的多模态能力，让 Agent 直接分析浏览器截图，理解页面布局和元素含义。
*   **工具化交互**: 将所有与环境（浏览器、桌面）的交互封装成 **Agent 可调用的工具 (Tools)**。Agent 的核心任务是根据目标和视觉分析结果，决定调用哪个工具以及传递什么参数。
*   **任务分解与推理**: Agent 需要具备将"查找图片来源URL"这个复杂任务分解为一系列子任务（打开网站、点击相机、上传图片、分析结果等）并按逻辑顺序执行的能力。
*   **状态管理与流程控制**: 对于多步骤任务，需要有效管理 Agent 的状态和执行流程。我们探索了使用 **LangChain Agents** 和 **LangGraph** 来构建状态机和任务图，实现更灵活的控制流。

**2. 为 Agent 设计的核心工具集:**

为了让 Agent 能够与浏览器环境交互，我们设计并实现了以下关键工具（基于 Python 和 Playwright/PyAutoGUI 的早期探索）：

*   `browse_web_page(url: str)`: 打开指定URL，并返回页面的文本内容和关键的屏幕截图 (Base64编码)，供 Agent 进行视觉分析。
*   `analyze_vision(screenshot: str, objective: str)`: 调用 GPT-4o Vision API，分析截图，根据当前目标（如"找到相机图标"、"找到上传按钮"）输出下一步操作指令或需要交互的目标元素的描述/大致位置。
*   `click_element_by_visual_description(description: str)`: 接收来自 `analyze_vision` 的自然语言描述，并尝试使用多种策略来定位并点击目标元素。
*   `type_text(text: str, element_description: Optional[str] = None)`: 在指定的元素或当前焦点处输入文本。
*   `upload_file(file_path: str, element_description: str)`: 处理文件上传交互并自动化后续的文件对话框操作。
*   `scroll_page(direction: str)`: 向下或向上滚动页面。

**3. 多模态能力的应用:**

项目的核心亮点在于利用 **GPT-4o Vision**。通过向模型提供页面截图和精确的 Prompt，Agent 得以理解非结构化信息、定位视觉元素和判断操作状态。

尽管 AI Agent 展示了巨大的潜力，但在实践中我们也遇到了挑战（详见下一节），这促使我们最终选择 `pyautogui` + 模板匹配作为更稳定可靠的演示方案。然而，设计和实现这些 Agent 工具和流程的经验，对于理解 LLM 的实际应用和局限性非常有价值。

## 技术栈 (Tech Stack)

*   **核心实现 (最终演示)**:
    *   Python 3.x
    *   PyAutoGUI
    *   OpenCV (cv2)
    *   Pyperclip
    *   Webbrowser
*   **AI Agent 探索阶段**:
    *   LangChain / LangGraph
    *   OpenAI API (gpt-4o)
    *   Playwright
*   **通用**:
    *   python-dotenv
    *   Pillow

## 项目结构 (Project Structure)

```
FindSourceURL/                  # 项目根目录
├── findsourceurl-agent/        # 核心自动化脚本及相关文件
│   ├── mouse_vision_agent.py   # 主执行脚本 (最终PyAutoGUI版本)
│   ├── camera_icon_template.png
│   ├── upload_button_template.png
│   ├── open_button_template.png
│   ├── data/                   # 示例图片目录
│   │   └── github.png
│   │   └── ...
│   ├── requirements.txt
│   └── .env                    # (可选)
│   └── findsourceurl.mp4       # 演示视频在此目录
├── README.md                   # 本文档
├── index.html                  # 网站演示前端 HTML
├── style.css                   # 网站演示前端 CSS
```

## 安装与运行 (Installation & Usage)

**1. 环境准备:**

*   Python 3.7+.
*   虚拟环境 (conda 或 venv).
    ```bash
    # conda
    conda create -n findsourceurl_env python=3.9
    conda activate findsourceurl_env
    # venv
    # python -m venv venv
    # .env\Scripts\activate (Windows)
    ```

**2. 安装依赖:**

   在 `findsourceurl-agent/` 目录下运行:
   ```bash
   pip install -r requirements.txt
   ```

**3. 准备模板图片:**

   *   确保 `findsourceurl-agent/` 目录下有准确的 `camera_icon_template.png`, `upload_button_template.png`, `open_button_template.png`。
   *   UI变化或系统不同可能需要重新截取。

**4. 准备待搜索的图片:**

   *   图片放在 `findsourceurl-agent/data/` 目录。
   *   修改 `mouse_vision_agent.py` 中的 `YOUR_IMAGE_TO_UPLOAD_PATH` 指向目标图片。

**5. (可选) 配置环境变量:**

   *   如需使用API密钥，创建 `.env` 文件于 `findsourceurl-agent/` 并添加 `OPENAI_API_KEY="..."`。

**6. 运行脚本:**

   *   激活虚拟环境。
   *   执行 (`findsourceurl-agent/` 目录下):
     ```bash
     python mouse_vision_agent.py
     ```
   *   脚本启动后，按提示手动确保浏览器窗口最大化并处于活动状态。

## 实现过程中的关键挑战与解决方案 (Key Challenges & Solutions)

本项目是一次从先进理念到务实落地的完整探索，挑战与迭代贯穿始终：

1.  **初始方案遇阻 (Web Automation APIs)**:
    *   **挑战**: 早期使用 Playwright/Puppeteer 等标准库，直面 reCAPTCHA 等反爬虫机制，难以稳定自动化。
    *   **反思**: 促使思考转向更接近人类交互的桌面自动化模式。

2.  **AI Agent + Vision 的希望与现实**:
    *   **探索**: 引入 LangChain/LangGraph 和 GPT-4o Vision，构想视觉驱动的 Agent，设计多种工具 (如 `analyze_vision`, `click_element_by_visual_description`)。
    *   **挑战**: 定位精度不足（视觉坐标误差）、动态元素干扰状态判断、多步流程稳定性差、调试复杂。
    *   **收获**: 深入实践了多模态LLM应用、Agent工具设计、状态管理和流程编排，积累了宝贵经验，认清了当前技术边界。

3.  **回归稳健：PyAutoGUI + 模板匹配**:
    *   **决策**: 为保证演示稳定性和任务完成度，切换到 `pyautogui` + 图像模板匹配方案，牺牲智能性换取精度和可靠性。
    *   **挑战**: 强依赖UI视觉稳定性（模板维护）、引入OpenCV依赖、文件对话框自动化（最终通过剪贴板+模板点击解决）。
    *   **最终成果**: 实现完整、流畅、可靠的自动化流程。

4.  **效率与体验优化**:
    *   **挑战**: 初版 `time.sleep()` 冗长导致执行慢。
    *   **解决方案**: 稳定后通过测试逐步优化等待时间，提升流畅度。

**总结**: 本项目从"完全智能"设想出发，深度实践AI Agent后，最终落地"精确可靠"的自动化方案，提供了关于AI Agent能力边界、多模态应用挑战及工程权衡的案例分析。

## 未来展望/可改进点 (Future Work/Potential Improvements)

*   **真正的搜索结果解析**: 当前仅模拟滚动。未来可结合HTML解析或再引入多模态AI分析结果页，提取源URL。
*   **批量处理**: 自动处理 `data/` 目录下所有图片并存储结果。
*   **Web服务化与前端集成**: 封装为Web API (Flask/FastAPI)，构建前端界面部署于 `findsourceurl.com`。
*   **更高级的浏览器控制**: 如需无头模式等精细控制，可考虑 Playwright/Selenium。
*   **错误处理与重试**: 增强脚本健壮性。
*   **配置化模板坐标**: 允许用户配置模板大致区域以提高效率。
*   **多语言/区域适应性**: 当前模板依赖特定UI，需更新以适应其他环境。

## 作者与致谢 (Author & Acknowledgements)

*   **项目作者**: [您的名字/GitHub用户名]
*   **灵感与任务来源**: 本项目最初的灵感来源于一个面试任务，感谢提供这个富有挑战性和学习价值的项目机会。
*   **AI辅助**: 在开发过程中，部分思路的梳理、代码片段的生成与调试得到了AI编程助手（如Gemini）的支持。

---
*这个README文档现在基本完成了。请您仔细审阅所有内容，并替换掉占位符信息（如您的名字和视频链接）。* 