# FindSourceURL.com - AI-Powered Reverse Image Search Automator

## 简介 (Short Description)

`FindSourceURL.com` (概念验证) 是一个旨在自动化反向图片搜索流程的Python应用。用户提供一张图片（通常是网站截图），该工具能够模拟人类操作，自动打开Google图片搜索，上传指定的图片，并浏览搜索结果，为最终找到图片原始来源网站URL的核心功能奠定基础。本项目主要通过UI自动化（`pyautogui`）和图像模板匹配（`opencv-python`）实现，展示了在复杂网页交互场景下不依赖特定API进行自动化操作的能力。

## 演示 (Demo)

*在此处嵌入您录制的项目演示视频链接。例如：*
`[项目演示视频](https://www.your-video-link.com)`

## 项目目标 (Project Goal)

*   完成一项富有挑战性的面试任务，展示Python编程、UI自动化、问题解决和项目管理能力。
*   探索在不直接调用搜索引擎API（避免复杂的API密钥管理和请求限制）的情况下，通过模拟用户操作实现反向图片搜索的可行性。
*   构建一个可以未来扩展并部署到个人域名 `findsourceurl.com` 的自动化工具原型。

## 技术栈 (Tech Stack)

*   **Python 3.x**
*   **PyAutoGUI**: 用于跨平台的图形用户界面自动化，控制鼠标和键盘。
*   **OpenCV (cv2)**: `pyautogui`进行图像模板匹配时依赖此库来提高识别精度（例如，使用`confidence`参数）。
*   **Pillow (PIL)**: `pyautogui`的依赖，用于图像处理。
*   **Pyperclip**: 用于跨平台复制和粘贴文本到剪贴板，解决了文件对话框路径输入的稳定性问题。
*   **Webbrowser**: Python内置模块，用于在脚本开始时自动打开指定的URL到系统默认浏览器。
*   **python-dotenv**: 用于管理环境变量（例如API密钥，虽然本项目最终阶段未使用AI进行结果分析，但在开发初期用于OpenAI API）。

## 项目结构 (Project Structure)

```
findsourceurl-agent/
├── mouse_vision_agent.py       # 主执行脚本
├── camera_icon_template.png    # Google图片"以图搜图"相机图标的模板
├── upload_button_template.png  # Google图片上传对话框中"上传文件"按钮的模板
├── open_button_template.png    # 操作系统文件选择对话框中"打开"按钮的模板
├── data/
│   └── github.png              # (示例) 待上传进行反向搜索的图片
│   └── ...                     # 其他测试图片可以放在这里
├── requirements.txt            # 项目Python依赖
└── .env                        # (可选) 用于存放环境变量，例如OPENAI_API_KEY
```

## 安装与运行 (Installation & Usage)

**1. 环境准备:**

*   确保您已安装 Python 3.7 或更高版本。
*   建议创建一个虚拟环境（例如使用 `conda` 或 `venv`）：
    ```bash
    conda create -n findsourceurl_env python=3.9
    conda activate findsourceurl_env
    ```
    或者
    ```bash
    python -m venv venv
    source venv/bin/activate  # macOS/Linux
    .\venv\Scripts\activate # Windows
    ```

**2. 安装依赖:**

   克隆项目仓库后，在项目根目录 (`findsourceurl-agent/`) 下打开终端，然后运行：
   ```bash
   pip install -r requirements.txt
   ```

**3. 准备模板图片:**

   *   确保以下三个模板图片文件与 `mouse_vision_agent.py` 在同一目录下，并且内容准确：
        *   `camera_icon_template.png`: Google图片主页上"以图搜图"的相机图标。
        *   `upload_button_template.png`: 点击相机图标后，出现的"上传文件"或类似文本的按钮/链接的截图。
        *   `open_button_template.png`: 操作系统文件选择对话框中的"打开"按钮的截图。
   *   这些模板的准确性对脚本能否成功定位UI元素至关重要。如果Google的UI发生变化，或者您的系统对话框样式不同，您可能需要重新截取这些模板。

**4. 准备待搜索的图片:**

   *   在 `findsourceurl-agent` 目录下创建一个名为 `data` 的子目录。
   *   将您想要进行反向搜索的图片放入 `data` 目录中。
   *   修改 `mouse_vision_agent.py` 脚本顶部的 `YOUR_IMAGE_TO_UPLOAD_PATH` 变量，使其指向您希望本次运行处理的图片，例如：
     ```python
     YOUR_IMAGE_TO_UPLOAD_PATH = os.path.join("data", "your_image_name.png")
     ```

**5. (可选) 配置环境变量:**

   *   如果未来重新启用或添加了依赖API密钥的功能（例如OpenAI GPT分析），请在 `findsourceurl-agent` 目录下创建一个 `.env` 文件，并按以下格式添加您的密钥：
     ```
     OPENAI_API_KEY="sk-YourActualOpenAIKey"
     ```

**6. 运行脚本:**

   *   打开终端，激活您的虚拟环境，并确保您的屏幕分辨率、浏览器窗口大小等与截取模板时保持一致，以获得最佳识别效果。
   *   执行脚本：
     ```bash
     python mouse_vision_agent.py
     ```
   *   脚本会尝试自动打开浏览器并导航到Google图片。**重要**：请在页面加载后，按照脚本提示，手动确保浏览器窗口是活动且最大化的，以保证后续图像识别的准确性。
   *   观察脚本执行每个步骤，它会模拟鼠标点击和键盘输入来完成图片上传和结果浏览。

## 核心功能 (Core Features)

*   **浏览器自动化启动**: 使用 `webbrowser` 模块自动在系统默认浏览器中打开 Google 图片搜索页面。
*   **多模板图像识别定位**: 
    *   精确查找 Google 图片主页上的"相机图标"（用于以图搜图）。
    *   精确定位点击相机图标后出现的"上传文件"按钮/链接。
    *   精确定位操作系统文件选择对话框中的"打开"按钮。
    *   依赖 `pyautogui` 和 `opencv-python` (提供 `confidence` 参数支持) 实现高精度模板匹配。
*   **自动化文件对话框交互**:
    *   使用 `pyperclip` 模块将待上传图片的绝对路径复制到系统剪贴板。
    *   模拟键盘 `Ctrl+V` 操作将路径粘贴到文件对话框的"文件名"输入框中。
    *   通过图像模板匹配点击对话框中的"打开"按钮，确认文件选择。
*   **动态路径处理**: 使用 `os.path.join` 和 `os.path.abspath` 构建和转换图片文件路径，增强脚本的健壮性。
*   **模拟用户操作**: 
    *   通过 `pyautogui` 控制鼠标进行平滑移动和精确点击。
    *   通过 `pyautogui.scroll()` 模拟用户在搜索结果页面向下滚动浏览内容。
*   **灵活的配置与调试**: 
    *   通过脚本顶部的变量轻松配置待上传图片路径和模板文件名。
    *   脚本执行过程中输出详细的日志信息，方便追踪运行状态和调试问题。
    *   精心调校的 `time.sleep()`间隔，平衡了操作速度、流畅度与系统响应的稳定性。

## 实现过程中的关键挑战与解决方案 (Key Challenges & Solutions)

本项目在开发过程中遇到并克服了多个技术挑战，体现了迭代开发和问题解决的重要性：

1.  **初步方案的局限 (Node.js + Puppeteer)**:
    *   **挑战**: 最初尝试使用 Node.js 和 Puppeteer 进行浏览器自动化，但在尝试与 Google 图片搜索交互时，频繁遭遇 reCAPTCHA 人机验证，且难以通过自动化手段稳定解决。
    *   **解决方案**: 决定转换技术栈，采用更侧重于模拟真实用户桌面操作的 Python 及 `pyautogui` 方案，从根本上改变了与页面的交互方式。

2.  **AI视觉分析的尝试与转向 (GPT-4o Vision)**:
    *   **挑战**: 在转向 Python 后，曾尝试结合多模态AI（如GPT-4o Vision）分析页面截图来定位UI元素。虽然AI能理解截图内容，但直接输出精确可用的屏幕坐标存在较大误差，难以直接用于 `pyautogui` 控制。
    *   **解决方案**: 保留AI视觉分析作为一种可能的辅助手段，但将核心的UI元素定位方案调整为基于图像模板匹配。这被证明是更可靠和精确的方法。

3.  **图像模板匹配的精度与依赖**: 
    *   **挑战**: `pyautogui.locateCenterOnScreen()` 在未使用 `confidence` 参数时，或模板不够清晰时，识别精度不足。
    *   **解决方案**: 
        *   引入 `opencv-python` 依赖，使得 `pyautogui` 可以使用 `confidence` 参数，大幅提升模板匹配的准确性和鲁棒性。
        *   强调了创建清晰、小巧、特征明显的模板图片的重要性。
        *   逐步为流程中的关键交互点（相机图标、上传按钮、对话框打开按钮）创建了专用模板。

4.  **自动化文件选择对话框**: 
    *   **挑战**: 这是UI自动化中的经典难题。最初尝试直接通过 `pyautogui.write()` 输入文件路径后模拟按 `Enter` 键，但发现因为路径分隔符（反斜杠 `\` 在 `pyautogui.write` 中可能被特殊处理或丢失）或焦点问题，导致路径无效或 `Enter` 键未作用于预期目标。
    *   **解决方案**: 
        *   尝试将路径中的 `\` 替换为 `/`，但问题依旧。
        *   最终采用"复制到剪贴板 (`pyperclip`) + 模拟粘贴 (`Ctrl+V`)""的方式输入文件路径，这被证明是非常稳定和可靠的方法。
        *   并且，不再依赖模拟按 `Enter` 确认对话框，而是为对话框的"打开"按钮创建了专门的图像模板进行点击。

5.  **操作流畅度与稳定性的平衡**: 
    *   **挑战**: 大量的 `time.sleep()` 虽然保证了稳定性，但使得脚本执行缓慢，体验不佳。
    *   **解决方案**: 在核心功能稳定跑通后，根据实际测试反馈，逐步、精细地调整了各个操作环节的等待时间，在保证稳定性的前提下，显著提升了脚本的执行速度和操作的流畅感。

6.  **环境配置与依赖管理**: 
    *   **挑战**: 项目依赖多个第三方库，需要确保其他用户能够方便地搭建运行环境。
    *   **解决方案**: 创建了 `requirements.txt` 文件，并提供了详细的环境设置和依赖安装说明。

## 未来展望/可改进点 (Future Work/Potential Improvements)

*   **真正的搜索结果解析**: 当前脚本在上传图片并跳转到结果页后，仅模拟滚动浏览。未来的关键改进是实现对搜索结果页面的智能解析，尝试提取出"最佳猜测"的原始图片来源URL或相关信息。
    *   这可能需要结合更复杂的HTML解析（如 `BeautifulSoup` 或 `lxml`）。
    *   或者，可以尝试再次引入多模态AI（如GPT-4 Vision API）分析结果页面的截图，让AI辅助判断哪些链接最可能是原始来源。这需要仔细设计prompt并处理AI的输出。
*   **批量处理**: 实现一个功能，允许脚本自动处理 `data/` 目录下的所有图片，并将每张图片的反向搜索结果（例如，找到的源URL）保存到CSV文件、JSON文件或数据库中。
*   **Web服务化与前端集成**: 
    *   将核心的Python自动化脚本封装成一个Web API（例如使用 Flask 或 FastAPI）。
    *   构建一个用户友好的前端界面（部署在 `findsourceurl.com`），允许用户直接通过网页上传图片，后端调用API执行反向搜索，并将结果展示给用户。
*   **更高级的浏览器控制 (可选)**: 如果需要更精细的浏览器操作（例如，在无头模式下运行、处理更复杂的网页动态内容、或者不希望UI操作干扰当前用户桌面），可以考虑重新引入或替换为更专业的浏览器自动化库，如 `Selenium` 或 `Playwright`。但需要权衡其带来的额外复杂性。
*   **错误处理与重试机制**: 增强脚本的健壮性，为可能出现的网络波动、UI元素短暂未找到等情况添加更完善的错误捕获和自动重试逻辑。
*   **配置化模板坐标 (高级)**: 对于更固定的UI，可以考虑允许用户通过配置文件或一个简单的校准程序来指定模板图片在屏幕上的大致区域，以缩小 `pyautogui.locateCenterOnScreen` 的搜索范围，提高效率和在某些情况下的准确性。
*   **多语言/多区域适应性**: 当前的模板和流程是基于特定语言（例如中文文件对话框的"打开"按钮）和Google特定区域的UI。如果要适应其他语言或区域，模板可能需要更新。

## 作者与致谢 (Author & Acknowledgements)

*   **项目作者**: [您的名字/GitHub用户名] (请在此处填写)
*   **灵感与任务来源**: 本项目最初的灵感来源于一个面试任务，感谢提供这个富有挑战性和学习价值的项目机会。
*   **AI辅助**: 在开发过程中，部分思路的梳理、代码片段的生成与调试得到了AI编程助手（如Gemini）的支持。

---
*这个README文档现在基本完成了。请您仔细审阅所有内容，并替换掉占位符信息（如您的名字和视频链接）。* 