import pyautogui
import openai
import base64
import os
import time
import re # 导入正则表达式模块
import webbrowser # 导入webbrowser模块
import pyperclip # 导入 pyperclip
from dotenv import load_dotenv

# 加载 .env 文件中的环境变量
load_dotenv()

# 从环境变量中获取 OpenAI API Key
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    print("错误：请确保 .env 文件中已设置 OPENAI_API_KEY")
    exit()

client = openai.OpenAI(api_key=OPENAI_API_KEY)

# 全局变量，用于模板图片名称
CAMERA_ICON_TEMPLATE_PATH = "camera_icon_template.png"
UPLOAD_BUTTON_TEMPLATE_PATH = "upload_button_template.png" # 新增上传按钮模板路径
DIALOG_OPEN_BUTTON_TEMPLATE_PATH = "open_button_template.png" # 新增打开按钮模板
# 将使用 data 目录下的 github.png
YOUR_IMAGE_TO_UPLOAD_PATH = os.path.join("data", "github.png") 

def capture_and_encode_screenshot(filename="screenshot.png", use_manual_file=None, for_ai_analysis=True):
    """
    捕获全屏截图或加载指定文件。
    如果 for_ai_analysis 为 True, 则编码为 Base64 字符串并返回。
    如果 for_ai_analysis 为 False, 则只保存文件并返回文件名 (主要用于pyautogui图像识别前的准备，虽然pyautogui可以直接操作屏幕)。
    """
    try:
        if use_manual_file:
            if os.path.exists(use_manual_file):
                print(f"正在加载手动提供的截图: {use_manual_file}")
                if for_ai_analysis:
                    with open(use_manual_file, "rb") as image_file:
                        return base64.b64encode(image_file.read()).decode('utf-8')
                else:
                    return use_manual_file # 返回文件名供后续使用或确认
            else:
                print(f"错误：手动提供的截图文件不存在: {use_manual_file}")
                return None
        else:
            # print("准备实时截图，请确保目标窗口在前台且内容已加载。等待0.5秒...") # 可以更短或省略，因为后续有等待
            time.sleep(0.2) # 略微等待
            screenshot = pyautogui.screenshot()
            # 将实时截图始终保存，以便调试或后续模板匹配 (如果需要基于特定截图)
            saved_filename = f"realtime__{filename}"
            screenshot.save(saved_filename)
            print(f"实时截图已保存为 {saved_filename}")
            if for_ai_analysis:
                with open(saved_filename, "rb") as image_file:
                    encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
                # os.remove(saved_filename) # 调试时可保留
                return encoded_string
            else:
                return saved_filename # 返回保存的文件名
    except Exception as e:
        print(f"处理图像时出错: {e}")
        return None

def analyze_image_with_gpt4o(base64_image, prompt_text):
    """
    使用 GPT-4o Vision API 分析图像。

    Args:
        base64_image (str): Base64 编码的图像字符串。
        prompt_text (str): 给模型的提示文本。

    Returns:
        str: 模型的文本响应。
    """
    if not base64_image:
        return "无法分析图像，因为截图未成功生成。"
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {OPENAI_API_KEY}"
    }

    payload = {
        "model": "gpt-4o",
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": prompt_text
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{base64_image}"
                        }
                    }
                ]
            }
        ],
        "max_tokens": 350 # 稍微增加token，以便获取更详细描述和坐标
    }

    try:
        response = client.chat.completions.create(
            model=payload["model"],
            messages=payload["messages"],
            max_tokens=payload["max_tokens"]
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"调用 OpenAI API 时出错: {e}")
        return f"调用 OpenAI API 时出错: {e}"

def extract_coordinates(text):
    """
    从文本中提取 (x, y) 格式的坐标。
    例如："相机图标大约在坐标 (123, 456)。" -> (123, 456)
    Args:
        text (str): 包含坐标信息的文本。
    Returns:
        tuple: (x, y) 坐标，如果找到的话；否则返回 None。
    """
    # 正则表达式查找括号中的两个数字，用逗号分隔，允许空格
    match = re.search(r"\(\s*(\d+)\s*,\s*(\d+)\s*\)", text)
    if match:
        x = int(match.group(1))
        y = int(match.group(2))
        return (x, y)
    return None

if __name__ == "__main__":
    google_images_url = "https://images.google.com/"
    print(f"正在尝试自动打开浏览器并导航到: {google_images_url}")
    webbrowser.open_new_tab(google_images_url)
    print("已发送打开网页的指令。请等待页面加载（约10-12秒）。") 
    print("重要提示：请在页面加载后，手动确保浏览器窗口是活动且最大化的...")
    time.sleep(12) # 增加浏览器初始加载等待

    print("\n--- 步骤 1: 定位并点击相机图标 --- ")
    if not os.path.exists(CAMERA_ICON_TEMPLATE_PATH):
        print(f"错误：相机图标模板 '{CAMERA_ICON_TEMPLATE_PATH}' 未找到！")
        exit()
    camera_clicked_successfully = False
    try:
        print(f"查找相机图标模板: '{CAMERA_ICON_TEMPLATE_PATH}'...")
        confidence_level_camera = 0.8 
        camera_coords = pyautogui.locateCenterOnScreen(CAMERA_ICON_TEMPLATE_PATH, confidence=confidence_level_camera)
        if camera_coords:
            print(f"找到相机图标: {camera_coords}")
            time.sleep(1.5) # 增加第一次鼠标移动前的等待
            pyautogui.moveTo(camera_coords[0], camera_coords[1], duration=0.25) 
            pyautogui.click(camera_coords[0], camera_coords[1])
            print("已点击相机图标。")
            camera_clicked_successfully = True
            print("等待'上传文件'对话框加载...")
            time.sleep(1.5) 
        else:
            print(f"未能通过模板找到相机图标 (confidence={confidence_level_camera})。")
    except pyautogui.ImageNotFoundException:
        print(f"错误：屏幕上找不到相机图标模板 '{CAMERA_ICON_TEMPLATE_PATH}'。")
    except Exception as e:
        print(f"相机图标处理错误: {e}")

    upload_button_clicked_successfully = False
    if camera_clicked_successfully:
        print("\n--- 步骤 2: 定位并点击上传按钮 --- ")
        if not os.path.exists(UPLOAD_BUTTON_TEMPLATE_PATH):
            print(f"错误：上传按钮模板 '{UPLOAD_BUTTON_TEMPLATE_PATH}' 未找到！")
            print(f"请先创建 '{UPLOAD_BUTTON_TEMPLATE_PATH}' 文件后再试。")
        else:
            try:
                print(f"查找上传按钮模板: '{UPLOAD_BUTTON_TEMPLATE_PATH}'...")
                time.sleep(0.5) # 查找前略微等待，确保对话框元素稳定
                confidence_level_upload = 0.8 
                upload_coords = pyautogui.locateCenterOnScreen(UPLOAD_BUTTON_TEMPLATE_PATH, confidence=confidence_level_upload)
                
                if upload_coords:
                    print(f"找到上传按钮: {upload_coords}")
                    pyautogui.moveTo(upload_coords[0], upload_coords[1], duration=0.25) # 加快移动
                    # print("已移动到上传按钮，准备点击 (0.5秒后执行)。") # 简化提示
                    time.sleep(0.5) # 缩短等待
                    pyautogui.click(upload_coords[0], upload_coords[1])
                    print("已点击上传按钮。")
                    upload_button_clicked_successfully = True
                    print("等待文件选择对话框出现并获取焦点...")
                    time.sleep(2) # 缩短等待文件对话框
                else:
                    print(f"未能通过模板找到上传按钮 (confidence={confidence_level_upload})。")
                    print("请检查模板图片是否准确，以及上传对话框是否在屏幕上清晰可见。")
            except pyautogui.ImageNotFoundException:
                print(f"错误：屏幕上找不到上传按钮模板 '{UPLOAD_BUTTON_TEMPLATE_PATH}'。")
            except Exception as e:
                print(f"上传按钮处理错误: {e}")
    else:
        if camera_clicked_successfully: # 只有在相机点击成功但上传按钮失败时才显示此消息
             print("前序步骤未能成功点击相机图标，脚本终止。")   

    file_selected_successfully = False
    if upload_button_clicked_successfully:
        print("\n--- 步骤 3: 处理文件上传（选择文件） --- ")
        
        # 获取要上传图片的绝对路径，以提高可靠性
        try:
            image_to_upload_abs_path = os.path.abspath(YOUR_IMAGE_TO_UPLOAD_PATH)
            print(f"将要上传的图片绝对路径 (用于剪贴板): {image_to_upload_abs_path}")

            if not os.path.exists(image_to_upload_abs_path): # 检查原始路径是否存在
                print(f"错误：要上传的图片 '{image_to_upload_abs_path}' 不存在！")
            else:
                print(f"准备将路径复制到剪贴板并粘贴 (确保对话框焦点)... ")
                time.sleep(1) # 确保对话框已获取焦点
                
                pyperclip.copy(image_to_upload_abs_path) # 复制路径到剪贴板
                print("路径已复制到剪贴板。")
                time.sleep(0.5) # 短暂等待剪贴板操作完成

                pyautogui.hotkey('ctrl', 'v') # 模拟粘贴
                print("已模拟粘贴 (Ctrl+V)。")
                time.sleep(1.0) # 允许路径在对话框中显示和注册
                
                print(f"正在查找并点击'打开'按钮模板: '{DIALOG_OPEN_BUTTON_TEMPLATE_PATH}'...")
                confidence_level_dialog_open = 0.8 # 可调整的置信度
                open_button_coords = pyautogui.locateCenterOnScreen(DIALOG_OPEN_BUTTON_TEMPLATE_PATH, confidence=confidence_level_dialog_open)
                
                if open_button_coords:
                    print(f"找到'打开'按钮: {open_button_coords}")
                    pyautogui.moveTo(open_button_coords[0], open_button_coords[1], duration=0.25)
                    pyautogui.click(open_button_coords[0], open_button_coords[1])
                    print("已点击'打开'按钮。")
                    file_selected_successfully = True
                else:
                    print(f"未能通过模板找到'打开'按钮。尝试模拟按 Enter 键作为后备方案...")
                    # Fallback to pressing Enter if open button template not found
                    time.sleep(0.5)
                    pyautogui.press('enter')
                    print("已尝试模拟按 Enter 键。")
                    # We can't be sure if Enter worked, so we don't set file_selected_successfully to True here
                    # unless we have a way to verify. For now, we assume it might have worked if button wasn't found.
                    # This part needs careful observation.
                    print("请观察文件是否开始上传。如果失败，主要问题可能在于'打开'按钮的模板或定位。")
                    file_selected_successfully = True # Temporarily assume it works for now to proceed

                if file_selected_successfully: # Check if either button click or Enter (assumed) worked
                    print("等待图片上传和页面跳转 (约10秒)... 请观察浏览器。")
                    time.sleep(10) 
                    print("\n--- 步骤 4: 模拟浏览搜索结果页面 --- ")
                    print("图片已上传，结果页面应已加载。现在模拟向下滚动浏览。")
                    scroll_amount = -500  # 增加每次滚动幅度
                    scroll_iterations = 5 # 增加滚动次数
                    for i in range(scroll_iterations):
                        pyautogui.scroll(scroll_amount)
                        print(f"已向下滚动 ({i+1}/{scroll_iterations})")
                        time.sleep(0.6) # 略微减少滚动间隙，但保持平滑感
                    print("已完成模拟滚动浏览。")

        except pyautogui.ImageNotFoundException as e:
             print(f"PyAutoGUI错误：在步骤3中找不到模板: {e}") # More specific error
        except Exception as e:
            print(f"在处理文件上传步骤中发生错误: {e}")
            
    else:
        if camera_clicked_successfully: # 只有在相机点击成功但上传按钮失败时才显示此消息
             print("未能成功点击上传按钮，无法继续文件上传步骤。")   

    print("\n脚本所有自动化步骤演示完毕。")


    print("\n脚本执行完毕 (目前仅移动鼠标，未实际点击)。")
    # print("重要提示：pyautogui 有一个安全特性，快速将鼠标移动到屏幕任一角落可以强制停止脚本运行。") 